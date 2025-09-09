from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone, timedelta
import asyncio
import pandas as pd
from pathlib import Path

from app.config import settings, validate_settings
from app.logging import logger
from app.data_access import db, storage
from app.universe import universe_manager
from app.worker import worker
from app.indicators import signal_processor
from app.alerts import alert_manager
from app.reconciliation import reconciliation_service
from app.rate_limiter import rate_limiter

def aggregate_timeframe(df: pd.DataFrame, tf: str) -> pd.DataFrame:
    """Aggregate 5m data to higher timeframes."""
    if df.empty:
        return df
    
    logger.info(f"Aggregating {len(df)} bars to {tf}")
    logger.info(f"DataFrame columns: {list(df.columns)}")
    logger.info(f"Index type: {type(df.index)}")
    
    # DataFrame already has timestamp as index from storage.read_candles()
    
    # Map timeframes to pandas frequency strings
    tf_map = {
        '15m': '15T',
        '30m': '30T', 
        '1h': '1H',
        '4h': '4H',
        '1d': '1D'
    }
    
    if tf not in tf_map:
        return df.reset_index()
    
    freq = tf_map[tf]
    
    # Aggregate OHLCV data
    agg_dict = {
        'o': 'first',
        'h': 'max',
        'l': 'min', 
        'c': 'last',
        'v': 'sum'
    }
    
    # Add any indicator columns that exist
    for col in df.columns:
        if col not in agg_dict:
            if col.startswith(('ema_', 'sma_', 'rsi', 'bb_', 'vwap', 'atr')):
                agg_dict[col] = 'last'  # Use last value for indicators
            elif col in ['rvol']:
                agg_dict[col] = 'mean'  # Average for volume-based indicators
    
    # Resample and aggregate
    df_agg = df.resample(freq).agg(agg_dict).dropna()
    
    # Reset index to get timestamp back as column
    df_agg = df_agg.reset_index()
    
    return df_agg

# Pydantic models for request/response
class SettingsRequest(BaseModel):
    finnhub_api_key: Optional[str] = None
    lookback_days: Optional[int] = None
    base_timeframe: Optional[str] = None
    universe_symbol: Optional[str] = None
    discord_webhook_url: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    include_extended_hours: Optional[bool] = None

class CandleQuery(BaseModel):
    symbol: str
    tf: str = "5m"
    from_time: Optional[str] = None
    to_time: Optional[str] = None
    limit: Optional[int] = 1000

class SignalQuery(BaseModel):
    symbol: Optional[str] = None
    tf: Optional[str] = None
    limit: Optional[int] = 100

# Create FastAPI app
app = FastAPI(
    title="Trading App API",
    description="Real-time trading data and signal processing",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (built React app)
static_dir = Path("static")
if static_dir.exists():
    # Mount the static directory to serve assets
    app.mount("/assets", StaticFiles(directory="static/assets"), name="assets")
    app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def serve_app():
    """Serve the React application."""
    static_index = Path("static/index.html")
    if static_index.exists():
        return FileResponse(static_index, headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
    else:
        return HTMLResponse("""
        <html>
            <head><title>Trading App</title></head>
            <body>
                <h1>Trading App Backend</h1>
                <p>Backend is running. Build the frontend to see the full application.</p>
                <ul>
                    <li><a href="/docs">API Documentation</a></li>
                    <li><a href="/healthz">Health Check</a></li>
                </ul>
            </body>
        </html>
        """)

@app.get("/charts")
async def serve_charts():
    """Serve the new charts interface with cache-busting."""
    static_index = Path("static/index.html")
    if static_index.exists():
        return FileResponse(static_index, headers={
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache", 
            "Expires": "0"
        })
    else:
        return HTMLResponse("Charts interface not built yet.")

@app.get("/api/settings")
async def get_settings():
    """Get current settings."""
    try:
        settings_dict = db.get_all_settings()
        
        # Add universe cache info
        universe_info = universe_manager.get_cache_info()
        
        return {
            "settings": settings_dict,
            "universe": universe_info,
            "alert_channels": alert_manager.get_configured_channels()
        }
    except Exception as e:
        logger.error(f"Error getting settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/settings")
async def update_settings(request: SettingsRequest):
    """Update application settings."""
    try:
        updated_keys = []
        
        # Update database settings
        if request.finnhub_api_key is not None:
            db.set_setting("FINNHUB_API_KEY", request.finnhub_api_key)
            updated_keys.append("FINNHUB_API_KEY")
        
        if request.lookback_days is not None:
            db.set_setting("LOOKBACK_DAYS", str(request.lookback_days))
            updated_keys.append("LOOKBACK_DAYS")
        
        if request.base_timeframe is not None:
            db.set_setting("BASE_TIMEFRAME", request.base_timeframe)
            updated_keys.append("BASE_TIMEFRAME")
        
        if request.universe_symbol is not None:
            db.set_setting("UNIVERSE_SYMBOL", request.universe_symbol)
            updated_keys.append("UNIVERSE_SYMBOL")
        
        # Update alert settings
        alert_manager.update_settings(
            discord_webhook=request.discord_webhook_url,
            telegram_bot_token=request.telegram_bot_token,
            telegram_chat_id=request.telegram_chat_id
        )
        
        if request.discord_webhook_url is not None:
            db.set_setting("DISCORD_WEBHOOK_URL", request.discord_webhook_url)
            updated_keys.append("DISCORD_WEBHOOK_URL")
        
        if request.telegram_bot_token is not None:
            db.set_setting("TELEGRAM_BOT_TOKEN", request.telegram_bot_token)
            updated_keys.append("TELEGRAM_BOT_TOKEN")
        
        if request.telegram_chat_id is not None:
            db.set_setting("TELEGRAM_CHAT_ID", request.telegram_chat_id)
            updated_keys.append("TELEGRAM_CHAT_ID")
            
        if request.include_extended_hours is not None:
            db.set_setting("INCLUDE_EXTENDED_HOURS", str(request.include_extended_hours).lower())
            updated_keys.append("INCLUDE_EXTENDED_HOURS")
        
        # Validate settings after update
        if request.lookback_days is not None:
            lookback_days = request.lookback_days
            if lookback_days > settings.max_lookback_days and not settings.enable_backlog_scheduling:
                raise HTTPException(
                    status_code=400,
                    detail=f"Lookback days cannot exceed {settings.max_lookback_days} unless backlog scheduling is enabled"
                )
        
        logger.info(f"Updated settings: {updated_keys}")
        
        return {
            "status": "success",
            "message": f"Updated {len(updated_keys)} settings",
            "updated": updated_keys
        }
        
    except Exception as e:
        logger.error(f"Error updating settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/control/start")
async def start_worker(background_tasks: BackgroundTasks):
    """Start the trading worker (backfill + streaming)."""
    try:
        # Validate that we have an API key
        api_key = db.get_setting("FINNHUB_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=400, 
                detail="FINNHUB_API_KEY is required. Please configure it in settings."
            )
        
        # Update worker's API key
        worker.api_key = api_key
        
        # Set API key for reconciliation service
        reconciliation_service.set_api_key(api_key)
        
        # Start the worker
        result = await worker.start()
        
        # Send status alert
        if result['status'] == 'success':
            background_tasks.add_task(
                alert_manager.send_status_alert, 
                "started", 
                result['message']
            )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting worker: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/control/stop")
async def stop_worker(background_tasks: BackgroundTasks):
    """Stop the trading worker."""
    try:
        result = worker.stop()
        
        # Send status alert
        background_tasks.add_task(
            alert_manager.send_status_alert, 
            "stopped", 
            result['message']
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error stopping worker: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/universe")
async def get_universe():
    """Get current universe symbols."""
    try:
        symbols = await universe_manager.get_universe_symbols()
        cache_info = universe_manager.get_cache_info()
        
        return {
            "symbols": symbols,
            "count": len(symbols),
            "cache_info": cache_info
        }
        
    except Exception as e:
        logger.error(f"Error getting universe: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/universe/refresh")
async def refresh_universe():
    """Force refresh universe symbols."""
    try:
        symbols = await universe_manager.refresh_universe()
        
        return {
            "status": "success",
            "symbols": symbols,
            "count": len(symbols),
            "message": "Universe refreshed successfully"
        }
        
    except Exception as e:
        logger.error(f"Error refreshing universe: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/candles")
async def get_candles(
    symbol: str,
    tf: str = "5m",
    from_time: Optional[str] = None,
    to_time: Optional[str] = None,
    limit: Optional[int] = 1000
):
    """Get candle data for a symbol and timeframe."""
    try:
        # Parse time parameters
        start_time = None
        end_time = None
        
        if from_time:
            start_time = datetime.fromisoformat(from_time.replace('Z', '+00:00'))
        
        if to_time:
            end_time = datetime.fromisoformat(to_time.replace('Z', '+00:00'))
        
        # Read candles from storage - always get 5m data first
        base_tf = "5m"
        df = storage.read_candles(symbol, base_tf, start_time, end_time)
        
        logger.info(f"Read {len(df)} candles for {symbol} from storage")
        if not df.empty:
            logger.info(f"DataFrame index type: {type(df.index)}")
            logger.info(f"DataFrame columns: {list(df.columns)}")
            logger.info(f"Index name: {df.index.name}")
            logger.info(f"First few timestamps: {df.index[:3].tolist()}")
        
        if df.empty:
            return {
                "symbol": symbol,
                "tf": tf,
                "candles": [],
                "count": 0
            }
        
        # For 5m timeframe, we need to reset index to convert timestamp index to column
        if tf == "5m":
            df = df.reset_index()
            # Rename the timestamp column to a consistent name
            if df.index.name == 'ts' or 'ts' in df.columns:
                pass  # Already has ts column
            else:
                df = df.rename(columns={df.columns[0]: 'ts'})  # First column should be timestamp
        
        # Aggregate to requested timeframe if not 5m
        if tf != "5m":
            df = aggregate_timeframe(df, tf)
        
        # Ensure we have a ts column for consistency
        if 'ts' not in df.columns and len(df.columns) > 0:
            # If first column looks like timestamp, rename it
            first_col = df.columns[0]
            if 'time' in first_col.lower() or first_col == df.index.name:
                df = df.rename(columns={first_col: 'ts'})
        
        # Apply limit
        if limit and len(df) > limit:
            df = df.tail(limit)
        
        # Calculate indicators (this expects DataFrame with ts column, not index)
        df_with_indicators = signal_processor.indicator_calc.calculate_indicators(df)
        
        # Convert to list of records
        candles = []
        for _, row in df_with_indicators.iterrows():
            candle = {
                "time": int(pd.to_datetime(row['ts']).timestamp()),
                "open": float(row['o']),
                "high": float(row['h']),
                "low": float(row['l']),
                "close": float(row['c']),
                "volume": int(row['v'])
            }
            
            # Add indicators if they exist
            for col in ['ema_9', 'ema_21', 'rsi', 'bb_upper', 'bb_middle', 'bb_lower', 'vwap', 'atr', 'rvol']:
                if col in row and not pd.isna(row[col]):
                    candle[col] = float(row[col])
            
            candles.append(candle)
        
        return {
            "symbol": symbol,
            "tf": tf,
            "candles": candles,
            "count": len(candles)
        }
        
    except Exception as e:
        logger.error(f"Error getting candles for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/signals")
async def get_signals(
    symbol: Optional[str] = None,
    tf: Optional[str] = None,
    limit: Optional[int] = 100
):
    """Get recent signals."""
    try:
        signals = db.get_signals(symbol=symbol, tf=tf, limit=limit)
        
        return {
            "signals": signals,
            "count": len(signals)
        }
        
    except Exception as e:
        logger.error(f"Error getting signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/signals/{signal_id}/alert")
async def resend_signal_alert(signal_id: int, background_tasks: BackgroundTasks):
    """Resend alert for a specific signal."""
    try:
        # Get signal from database
        signals = db.get_signals(limit=1000)  # Get all recent signals
        signal = None
        
        for s in signals:
            if s['id'] == signal_id:
                signal = s
                break
        
        if not signal:
            raise HTTPException(status_code=404, detail="Signal not found")
        
        # Send alert
        background_tasks.add_task(alert_manager.send_signal_alert, signal)
        
        return {
            "status": "success",
            "message": f"Alert queued for signal {signal_id}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resending alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/healthz")
async def health_check():
    """Enhanced health check endpoint with comprehensive metrics."""
    try:
        worker_status = worker.get_status()
        universe_info = universe_manager.get_cache_info()
        rate_stats = rate_limiter.get_stats()
        reconciliation_stats = reconciliation_service.get_reconciliation_stats()
        
        # Check database connectivity
        try:
            db.get_setting("health_check", "ok")
            db_status = "healthy"
        except Exception as e:
            db_status = f"error: {e}"
        
        # Check data storage
        try:
            symbols_with_data = storage.get_symbols_with_data()
            storage_status = f"healthy - {len(symbols_with_data)} symbols"
        except Exception as e:
            storage_status = f"error: {e}"
        
        # Extended hours setting
        include_extended_hours = db.get_setting('INCLUDE_EXTENDED_HOURS', 'false').lower() == 'true'
        
        return {
            "status": "healthy" if worker_status['running'] else "stopped",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "worker": worker_status,
            "database": db_status,
            "storage": storage_status,
            "universe": universe_info,
            "alerts": alert_manager.get_configured_channels(),
            
            # New enhanced metrics
            "rest_calls_today": rate_stats.calls_today,
            "rest_calls_minute": rate_stats.calls_this_minute,
            "budget_remaining_today": rate_stats.budget_remaining_today,
            "last_ws_tick_ts": worker_status['stats'].get('last_ws_tick_ts'),
            "ws_connected": worker_status['ws_connected'],
            "backfill_queue_size": worker_status['stats'].get('backfill_queue_size', 0),
            "last_backfill_ts": worker_status['stats'].get('last_backfill_ts'),
            "last_reconcile_date": reconciliation_stats['last_reconcile_date'],
            "include_extended_hours": include_extended_hours,
            
            # Reconciliation metrics
            "reconciliation": reconciliation_stats
        }
        
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return {
            "status": "error",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": str(e)
        }

@app.get("/api/stats")
async def get_stats():
    """Get application statistics."""
    try:
        worker_status = worker.get_status()
        symbols_with_data = storage.get_symbols_with_data()
        
        # Get signal counts
        recent_signals = db.get_signals(limit=1000)
        signal_counts = {}
        for signal in recent_signals:
            symbol = signal['symbol']
            if symbol not in signal_counts:
                signal_counts[symbol] = 0
            signal_counts[symbol] += 1
        
        return {
            "worker": worker_status,
            "data_symbols_count": len(symbols_with_data),
            "data_symbols": symbols_with_data[:20],  # First 20 symbols
            "recent_signals_count": len(recent_signals),
            "signals_by_symbol": dict(sorted(signal_counts.items(), key=lambda x: x[1], reverse=True)[:10])
        }
        
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.on_event("startup")
async def startup_event():
    """Application startup tasks."""
    try:
        # Validate configuration
        validate_settings(settings)
        logger.info("Settings validation passed")
        
        # Initialize reconciliation service
        api_key = db.get_setting("FINNHUB_API_KEY")
        if api_key:
            reconciliation_service.set_api_key(api_key)
            
        logger.info("Application startup completed")
        
    except Exception as e:
        logger.error(f"Application startup failed: {e}")
        raise

@app.post("/api/reconciliation/run")
async def run_reconciliation():
    """Manually trigger reconciliation for the previous session."""
    try:
        # Get current universe symbols
        symbols = await universe_manager.get_universe_symbols()
        
        if not symbols:
            return {
                "status": "error",
                "message": "No universe symbols available for reconciliation"
            }
        
        results = await reconciliation_service.reconcile_previous_session(symbols[:50])  # Limit to avoid quota issues
        
        total_updated = sum(results.values())
        
        return {
            "status": "success",
            "message": f"Reconciliation completed: {total_updated} bars updated across {len(results)} symbols",
            "results": results
        }
        
    except Exception as e:
        logger.error(f"Error running manual reconciliation: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info"
    )