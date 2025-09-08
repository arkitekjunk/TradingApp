import asyncio
import json
import websocket
import threading
import time
import random
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Callable, Any
from collections import defaultdict, deque
import pandas as pd
import httpx
from loguru import logger

from app.config import settings, get_config_value
from app.data_access import storage, db
from app.universe import universe_manager
from app.indicators import signal_processor
from app.rate_limiter import rate_limiter
from app.market_calendar import market_calendar

class CandleAggregator:
    """Aggregates trade ticks into OHLCV candles."""
    
    def __init__(self, timeframe_minutes: int = 5):
        self.timeframe_minutes = timeframe_minutes
        self.timeframe_ms = timeframe_minutes * 60 * 1000
        
        # Store incomplete candles for each symbol
        self.current_candles: Dict[str, Dict] = {}
        
        # Store completed candles to batch write
        self.completed_candles: Dict[str, List[Dict]] = defaultdict(list)
        
        # Callbacks for completed candles
        self.candle_callbacks: List[Callable] = []
    
    def add_candle_callback(self, callback: Callable):
        """Add a callback to be called when candles are completed."""
        self.candle_callbacks.append(callback)
    
    def process_trade(self, symbol: str, price: float, volume: int, timestamp_ms: int):
        """Process a trade tick and update the current candle."""
        try:
            # Calculate which candle bucket this trade belongs to
            bucket_ms = (timestamp_ms // self.timeframe_ms) * self.timeframe_ms
            bucket_datetime = datetime.fromtimestamp(bucket_ms / 1000, tz=timezone.utc)
            
            # Get or create current candle for this symbol
            if symbol not in self.current_candles:
                self.current_candles[symbol] = {
                    'timestamp': bucket_datetime,
                    'bucket_ms': bucket_ms,
                    'o': price,
                    'h': price,
                    'l': price,
                    'c': price,
                    'v': 0,
                    'trade_count': 0
                }
            
            candle = self.current_candles[symbol]
            
            # Check if this trade belongs to a different bucket
            if bucket_ms != candle['bucket_ms']:
                # Complete the current candle
                self._complete_candle(symbol, candle)
                
                # Start new candle
                self.current_candles[symbol] = {
                    'timestamp': bucket_datetime,
                    'bucket_ms': bucket_ms,
                    'o': price,
                    'h': price,
                    'l': price,
                    'c': price,
                    'v': volume,
                    'trade_count': 1
                }
            else:
                # Update existing candle
                candle['h'] = max(candle['h'], price)
                candle['l'] = min(candle['l'], price)
                candle['c'] = price
                candle['v'] += volume
                candle['trade_count'] += 1
                
        except Exception as e:
            logger.error(f"Error processing trade for {symbol}: {e}")
    
    def _complete_candle(self, symbol: str, candle: Dict):
        """Complete a candle and add it to the batch."""
        try:
            completed_candle = {
                'ts': candle['timestamp'],
                'o': candle['o'],
                'h': candle['h'],
                'l': candle['l'],
                'c': candle['c'],
                'v': candle['v']
            }
            
            self.completed_candles[symbol].append(completed_candle)
            
            logger.debug(f"Completed {self.timeframe_minutes}m candle for {symbol}: "
                        f"OHLCV({completed_candle['o']:.2f}, {completed_candle['h']:.2f}, "
                        f"{completed_candle['l']:.2f}, {completed_candle['c']:.2f}, {completed_candle['v']})")
            
            # Notify callbacks
            for callback in self.candle_callbacks:
                try:
                    callback(symbol, completed_candle)
                except Exception as e:
                    logger.error(f"Error in candle callback: {e}")
                    
        except Exception as e:
            logger.error(f"Error completing candle for {symbol}: {e}")
    
    def flush_completed_candles(self):
        """Write all completed candles to storage and clear the buffer."""
        try:
            for symbol, candles in self.completed_candles.items():
                if candles:
                    # Convert to DataFrame
                    df = pd.DataFrame(candles)
                    
                    # Write to storage
                    tf = f"{self.timeframe_minutes}m"
                    storage.write_candles(symbol, tf, df)
                    
                    logger.debug(f"Flushed {len(candles)} candles for {symbol}")
            
            # Clear completed candles
            self.completed_candles.clear()
            
        except Exception as e:
            logger.error(f"Error flushing completed candles: {e}")
    
    def force_complete_current_candles(self):
        """Force complete all current candles (useful for shutdown)."""
        for symbol, candle in list(self.current_candles.items()):
            self._complete_candle(symbol, candle)
        
        self.current_candles.clear()

class FinnhubWorker:
    """Main worker class that handles backfilling and live streaming."""
    
    def __init__(self):
        self._refresh_api_key()
        self.is_running = False
        self.ws_connected = False
        self.ws = None
        self.ws_thread = None
        
        # Aggregator for 5-minute candles
        self.aggregator = CandleAggregator(timeframe_minutes=5)
        self.aggregator.add_candle_callback(self._on_candle_completed)
        
        # Current universe symbols
        self.universe_symbols: List[str] = []
        
        # Reconnection settings
        self.reconnect_delay = get_config_value("defaults.websocket_reconnect_delay", 5)
        self.max_reconnect_attempts = get_config_value("defaults.max_reconnect_attempts", 10)
        self.reconnect_attempts = 0
        
        # Statistics
        self.stats = {
            'ws_messages_received': 0,
            'trades_processed': 0,
            'last_trade_time': None,
            'symbols_subscribed': 0,
            'backfill_progress': {'current': 0, 'total': 0, 'status': 'idle'},
            'last_ws_tick_ts': None,
            'last_backfill_ts': None
        }
        
        # Session state for VWAP resets
        self.last_vwap_reset_time = None
    
    def _refresh_api_key(self):
        """Refresh API key from database settings or fallback to env."""
        from app.data_access import db
        self.api_key = db.get_setting("FINNHUB_API_KEY") or settings.finnhub_api_key
        
        if not self.api_key or self.api_key == "your_finnhub_api_key_here":
            raise ValueError("Valid Finnhub API key is required. Please set it in the settings.")
        
        # Graceful shutdown handling
        self.shutdown_requested = False
        import signal
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
    
    async def start(self) -> Dict[str, str]:
        """Start the worker - backfill data and begin live streaming."""
        if self.is_running:
            return {'status': 'error', 'message': 'Worker is already running'}
        
        try:
            logger.info("Starting Finnhub worker...")
            self.is_running = True
            
            # Refresh API key from latest settings
            self._refresh_api_key()
            logger.info("API key refreshed from settings")
            
            # 1. Fetch universe symbols
            logger.info("Fetching universe symbols...")
            self.universe_symbols = await universe_manager.get_universe_symbols()
            
            if not self.universe_symbols:
                return {'status': 'error', 'message': 'No universe symbols found'}
            
            logger.info(f"Got {len(self.universe_symbols)} universe symbols")
            
            # 2. Start backfill process
            backfill_task = asyncio.create_task(self._backfill_data())
            
            # 3. Start WebSocket connection
            self._start_websocket()
            
            # Wait for backfill to complete
            await backfill_task
            
            # 4. Set up periodic tasks
            asyncio.create_task(self._periodic_flush())
            asyncio.create_task(self._periodic_universe_refresh())
            
            self.stats['symbols_subscribed'] = len(self.universe_symbols)
            
            return {'status': 'success', 'message': f'Worker started with {len(self.universe_symbols)} symbols'}
            
        except Exception as e:
            logger.error(f"Error starting worker: {e}")
            self.is_running = False
            return {'status': 'error', 'message': str(e)}
    
    def stop(self) -> Dict[str, str]:
        """Stop the worker and clean up resources."""
        logger.info("Stopping Finnhub worker...")
        
        self.is_running = False
        
        # Close WebSocket
        if self.ws:
            self.ws.close()
        
        # Force complete any pending candles
        self.aggregator.force_complete_current_candles()
        self.aggregator.flush_completed_candles()
        
        return {'status': 'success', 'message': 'Worker stopped'}
    
    async def _backfill_data(self):
        """Backfill historical data with quota-aware scheduling."""
        try:
            include_extended_hours = db.get_setting('INCLUDE_EXTENDED_HOURS', 'false').lower() == 'true'
            lookback_days = min(int(db.get_setting('LOOKBACK_DAYS', '30')), settings.max_lookback_days)
            
            # Check rate limiter budget
            rate_stats = rate_limiter.get_stats()
            estimated_calls_needed = len(self.universe_symbols) * lookback_days  # Rough estimate
            
            if estimated_calls_needed > rate_stats.budget_remaining_today:
                logger.warning(f"Estimated backfill needs {estimated_calls_needed} calls, "
                             f"but only {rate_stats.budget_remaining_today} remaining today. "
                             f"Scheduling symbols for future processing.")
                             
                # Schedule remaining symbols for future days
                await self._schedule_backfill_queue()
                return
            
            total_symbols = len(self.universe_symbols)
            self.stats['backfill_progress'] = {
                'current': 0, 
                'total': total_symbols, 
                'status': 'running'
            }
            
            logger.info(f"Starting quota-aware backfill for {total_symbols} symbols (lookback: {lookback_days} days)")
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                for i, symbol in enumerate(self.universe_symbols):
                    if not self.is_running or self.shutdown_requested:
                        break
                    
                    try:
                        await self._backfill_symbol_chunked(client, symbol, lookback_days, include_extended_hours)
                        self.stats['backfill_progress']['current'] = i + 1
                        self.stats['last_backfill_ts'] = datetime.now(timezone.utc).isoformat()
                        
                    except Exception as e:
                        logger.error(f"Error backfilling {symbol}: {e}")
                        # Add to backfill queue for retry
                        db.add_to_backfill_queue(symbol, priority=1)
                        continue
            
            self.stats['backfill_progress']['status'] = 'completed'
            logger.info("Backfill process completed")
            
        except Exception as e:
            logger.error(f"Error in backfill process: {e}")
            self.stats['backfill_progress']['status'] = 'error'
    
    async def _backfill_symbol_chunked(self, client: httpx.AsyncClient, symbol: str, 
                                     lookback_days: int, include_extended_hours: bool):
        """Backfill data for a single symbol using chunked per-day requests."""
        try:
            # Check if we already have recent data
            last_timestamp = storage.get_last_timestamp(symbol, "5m")
            end_time = datetime.now(timezone.utc)
            
            if last_timestamp:
                # Incremental top-up: only fetch from last timestamp + 60s to now
                start_time = last_timestamp + timedelta(seconds=60)
                if (end_time - start_time).total_seconds() < 300:  # Less than 5 minutes
                    logger.debug(f"Skipping {symbol} - very recent data exists")
                    return
                    
                logger.info(f"Incremental backfill for {symbol} from {start_time} to {end_time}")
                
                # Single request for incremental data
                await self._fetch_and_store_chunk(client, symbol, start_time, end_time, include_extended_hours)
                
            else:
                # Full backfill using per-day chunks
                start_time = end_time - timedelta(days=lookback_days)
                logger.info(f"Full backfill for {symbol} from {start_time} to {end_time} ({lookback_days} days)")
                
                # Generate per-day slices
                async for day_start, day_end in self._generate_day_slices(start_time, end_time):
                    if not self.is_running or self.shutdown_requested:
                        break
                        
                    await self._fetch_and_store_chunk(client, symbol, day_start, day_end, include_extended_hours)
                    
                    # Small delay between days to be API-friendly
                    await asyncio.sleep(0.1)
                    
            logger.debug(f"Completed backfill for {symbol}")
            
        except Exception as e:
            logger.error(f"Error in chunked backfill for {symbol}: {e}")
            raise
    
    async def _generate_day_slices(self, start_time: datetime, end_time: datetime):
        """Generate per-day time slices for chunked backfill."""
        current = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
        
        while current < end_time:
            day_end = min(
                current + timedelta(days=1) - timedelta(seconds=1),
                end_time
            )
            
            yield current, day_end
            current += timedelta(days=1)
    
    async def _fetch_and_store_chunk(self, client: httpx.AsyncClient, symbol: str,
                                   chunk_start: datetime, chunk_end: datetime,
                                   include_extended_hours: bool):
        """Fetch and store a single time chunk with rate limiting and retry logic."""
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                # Acquire rate limit permission
                await rate_limiter.acquire_with_backoff()
                
                # Call Finnhub stock/candle API
                url = "https://finnhub.io/api/v1/stock/candle"
                params = {
                    'symbol': symbol,
                    'resolution': '1',  # 1-minute resolution for accuracy
                    'from': int(chunk_start.timestamp()),
                    'to': int(chunk_end.timestamp()),
                    'token': self.api_key,
                    'adjusted': 'true'  # Ensure split/dividend adjustments
                }
                
                response = await client.get(url, params=params)
                
                if response.status_code == 429:
                    # Rate limit hit - exponential backoff
                    backoff_delay = (2 ** attempt) + random.uniform(0, 2)
                    logger.warning(f"Rate limited for {symbol}, attempt {attempt + 1}, waiting {backoff_delay:.1f}s")
                    await asyncio.sleep(backoff_delay)
                    continue
                    
                response.raise_for_status()
                data = response.json()
                
                if data.get('s') != 'ok':
                    logger.debug(f"No data for {symbol} in chunk {chunk_start} to {chunk_end}: {data}")
                    return
                
                # Convert to DataFrame
                df = pd.DataFrame({
                    'ts': pd.to_datetime(data['t'], unit='s', utc=True),
                    'o': data['o'],
                    'h': data['h'],
                    'l': data['l'],
                    'c': data['c'],
                    'v': data['v']
                })
                
                if df.empty:
                    return
                
                # Filter for extended hours if needed
                if not include_extended_hours:
                    df = df[df['ts'].apply(lambda x: market_calendar.is_regular_hours(x))]
                
                if df.empty:
                    return
                
                # Resample 1-minute to 5-minute bars with proper alignment
                df_5m = self._resample_to_5min_aligned(df)
                
                # Store 5-minute candles
                if not df_5m.empty:
                    storage.write_candles(symbol, "5m", df_5m)
                    logger.debug(f"Stored {len(df_5m)} 5m candles for {symbol} (chunk: {chunk_start.date()})")
                
                return  # Success, exit retry loop
                
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(f"Failed to fetch chunk for {symbol} after {max_retries} attempts: {e}")
                    raise
                else:
                    backoff_delay = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(f"Error fetching chunk for {symbol}, attempt {attempt + 1}, retrying in {backoff_delay:.1f}s: {e}")
                    await asyncio.sleep(backoff_delay)
    
    async def _schedule_backfill_queue(self):
        """Schedule symbols that couldn't be processed today into backfill queue."""
        try:
            rate_stats = rate_limiter.get_stats()
            symbols_per_day = max(1, rate_stats.budget_remaining_today // 30)  # Conservative estimate
            
            # Calculate when to schedule remaining symbols
            tomorrow = datetime.now(timezone.utc).replace(
                hour=1, minute=0, second=0, microsecond=0
            ) + timedelta(days=1)
            
            scheduled_count = 0
            for i, symbol in enumerate(self.universe_symbols[symbols_per_day:]):
                # Spread symbols across multiple days
                days_offset = i // symbols_per_day
                scheduled_for = tomorrow + timedelta(days=days_offset)
                
                db.add_to_backfill_queue(symbol, priority=0, scheduled_for=scheduled_for)
                scheduled_count += 1
            
            logger.info(f"Scheduled {scheduled_count} symbols for future backfill processing")
            
        except Exception as e:
            logger.error(f"Error scheduling backfill queue: {e}")
    
    def _resample_to_5min_aligned(self, df_1m: pd.DataFrame) -> pd.DataFrame:
        """Resample 1-minute bars to 5-minute bars with proper ET timezone alignment."""
        if df_1m.empty:
            return df_1m
        
        df_1m = df_1m.set_index('ts')
        
        # Convert to ET timezone for proper market session alignment
        df_1m_et = df_1m.tz_convert('America/New_York')
        
        # Resample to 5-minute bars aligned to market session boundaries
        # This ensures bars start at 09:30:00, 09:35:00, etc. in ET
        df_5m_et = df_1m_et.resample('5T', origin='start').agg({
            'o': 'first',
            'h': 'max', 
            'l': 'min',
            'c': 'last',
            'v': 'sum'
        }).dropna()
        
        # Convert back to UTC
        df_5m = df_5m_et.tz_convert('UTC')
        
        # Reset index to get timestamp as column
        df_5m = df_5m.reset_index()
        
        return df_5m
    
    def _start_websocket(self):
        """Start WebSocket connection in a separate thread."""
        def ws_thread():
            while self.is_running:
                try:
                    self._connect_websocket()
                    break
                except Exception as e:
                    logger.error(f"WebSocket connection failed: {e}")
                    if self.reconnect_attempts < self.max_reconnect_attempts:
                        self.reconnect_attempts += 1
                        time.sleep(self.reconnect_delay * self.reconnect_attempts)
                    else:
                        logger.error("Max reconnection attempts reached")
                        break
        
        self.ws_thread = threading.Thread(target=ws_thread, daemon=True)
        self.ws_thread.start()
    
    def _connect_websocket(self):
        """Connect to Finnhub WebSocket and subscribe to symbols."""
        ws_url = f"wss://ws.finnhub.io?token={self.api_key}"
        
        def on_open(ws):
            logger.info("WebSocket connected")
            self.ws_connected = True
            self.reconnect_attempts = 0
            
            # Subscribe to all universe symbols
            for symbol in self.universe_symbols:
                subscribe_msg = json.dumps({'type': 'subscribe', 'symbol': symbol})
                ws.send(subscribe_msg)
                
            logger.info(f"Subscribed to {len(self.universe_symbols)} symbols")
        
        def on_message(ws, message):
            try:
                data = json.loads(message)
                self._handle_ws_message(data)
            except Exception as e:
                logger.error(f"Error handling WebSocket message: {e}")
        
        def on_error(ws, error):
            logger.error(f"WebSocket error: {error}")
            self.ws_connected = False
        
        def on_close(ws, close_status_code, close_msg):
            logger.warning(f"WebSocket closed: {close_status_code} - {close_msg}")
            self.ws_connected = False
            
            # Attempt to reconnect if still running
            if self.is_running and not self.shutdown_requested:
                logger.info("Attempting to reconnect WebSocket...")
                
                # Fill gap on reconnect if we were previously connected
                if self.stats.get('last_ws_tick_ts'):
                    asyncio.create_task(self._fill_websocket_gap())
                
                time.sleep(self.reconnect_delay)
        
        self.ws = websocket.WebSocketApp(
            ws_url,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        )
        
        self.ws.run_forever()
    
    def _handle_ws_message(self, data: Dict):
        """Handle incoming WebSocket message."""
        try:
            if data.get('type') == 'trade':
                # Handle trade data
                trades = data.get('data', [])
                
                for trade in trades:
                    symbol = trade.get('s', '')
                    price = float(trade.get('p', 0))
                    volume = int(trade.get('v', 0))
                    timestamp_ms = int(trade.get('t', 0))
                    
                    # Process the trade through aggregator
                    self.aggregator.process_trade(symbol, price, volume, timestamp_ms)
                    
                    self.stats['trades_processed'] += 1
                    self.stats['last_trade_time'] = datetime.now(timezone.utc).isoformat()
                    self.stats['last_ws_tick_ts'] = datetime.now(timezone.utc).isoformat()
                
                self.stats['ws_messages_received'] += 1
                
        except Exception as e:
            logger.error(f"Error handling WebSocket message: {e}")
    
    def _on_candle_completed(self, symbol: str, candle: Dict):
        """Callback when a 5-minute candle is completed."""
        try:
            # Process indicators and signals
            df = storage.read_candles(symbol, "5m")
            if not df.empty:
                signals = signal_processor.process_candles(symbol, "5m", df)
                
                # Handle any new signals (webhook notifications will be sent from API layer)
                if signals:
                    logger.info(f"Generated {len(signals)} signals for {symbol}")
                    
        except Exception as e:
            logger.error(f"Error processing completed candle for {symbol}: {e}")
    
    async def _periodic_flush(self):
        """Periodically flush completed candles to storage."""
        while self.is_running:
            try:
                await asyncio.sleep(30)  # Flush every 30 seconds
                self.aggregator.flush_completed_candles()
            except Exception as e:
                logger.error(f"Error in periodic flush: {e}")
    
    async def _periodic_universe_refresh(self):
        """Periodically refresh universe symbols."""
        while self.is_running:
            try:
                await asyncio.sleep(3600)  # Check every hour
                
                # Refresh universe if cache is stale
                new_symbols = await universe_manager.get_universe_symbols()
                
                if set(new_symbols) != set(self.universe_symbols):
                    logger.info(f"Universe changed: {len(new_symbols)} symbols")
                    self.universe_symbols = new_symbols
                    
                    # Re-subscribe to WebSocket if connected
                    if self.ws_connected and self.ws:
                        for symbol in new_symbols:
                            subscribe_msg = json.dumps({'type': 'subscribe', 'symbol': symbol})
                            self.ws.send(subscribe_msg)
                    
                    self.stats['symbols_subscribed'] = len(self.universe_symbols)
                    
            except Exception as e:
                logger.error(f"Error refreshing universe: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current worker status with enhanced metrics."""
        rate_stats = rate_limiter.get_stats()
        
        status = {
            'running': self.is_running,
            'ws_connected': self.ws_connected,
            'symbols_count': len(self.universe_symbols),
            'stats': self.stats.copy()
        }
        
        # Add rate limiting stats
        status['stats']['rest_calls_today'] = rate_stats.calls_today
        status['stats']['rest_calls_minute'] = rate_stats.calls_this_minute
        status['stats']['budget_remaining_today'] = rate_stats.budget_remaining_today
        status['stats']['backfill_queue_size'] = db.get_backfill_queue_size()
        
        return status
    
    def _signal_handler(self, signum, frame):
        """Handle graceful shutdown signals."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.shutdown_requested = True
        
        # Force complete any current candles to avoid data loss
        self.aggregator.force_complete_current_candles()
        self.aggregator.flush_completed_candles()
        
        # Stop the worker
        self.stop()
    
    async def _fill_websocket_gap(self):
        """Fill gaps in 5-minute candles when WebSocket reconnects."""
        try:
            if not self.stats.get('last_ws_tick_ts'):
                return
                
            last_tick_time = datetime.fromisoformat(
                self.stats['last_ws_tick_ts'].replace('Z', '+00:00')
            )
            reconnect_time = datetime.now(timezone.utc)
            gap_duration = (reconnect_time - last_tick_time).total_seconds()
            
            if gap_duration < 300:  # Less than 5 minutes, no gap fill needed
                return
                
            logger.info(f"Filling WebSocket gap of {gap_duration:.0f} seconds")
            
            include_extended_hours = db.get_setting('INCLUDE_EXTENDED_HOURS', 'false').lower() == 'true'
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                for symbol in self.universe_symbols[:10]:  # Limit to avoid quota exhaustion
                    try:
                        gap_start = last_tick_time + timedelta(seconds=60)
                        await self._fetch_and_store_chunk(
                            client, symbol, gap_start, reconnect_time, include_extended_hours
                        )
                    except Exception as e:
                        logger.error(f"Error filling gap for {symbol}: {e}")
                        
            logger.info("WebSocket gap fill completed")
            
        except Exception as e:
            logger.error(f"Error in WebSocket gap fill: {e}")

# Global worker instance
worker = FinnhubWorker()