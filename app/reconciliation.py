"""
End-of-day reconciliation system.
Aligns live-built candles with official adjusted REST data after market close.
"""
import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
import pandas as pd
import httpx
from loguru import logger

from app.config import get_config_value
from app.data_access import storage, db
from app.rate_limiter import rate_limiter
from app.market_calendar import market_calendar


class ReconciliationService:
    """
    Service to reconcile live-built bars with official adjusted data daily.
    """
    
    def __init__(self):
        self.api_key = None
        
    def set_api_key(self, api_key: str):
        """Set the Finnhub API key for reconciliation."""
        self.api_key = api_key
    
    def _refresh_api_key(self):
        """Refresh API key from database settings."""
        from app.data_access import db
        self.api_key = db.get_setting("FINNHUB_API_KEY")
        
    async def reconcile_previous_session(self, symbols: List[str]) -> Dict[str, int]:
        """
        Reconcile the previous trading session's data for given symbols.
        
        Args:
            symbols: List of symbols to reconcile
            
        Returns:
            Dict mapping symbol -> number of bars updated
        """
        # Refresh API key from settings
        self._refresh_api_key()
        
        if not self.api_key:
            logger.error("API key not set for reconciliation")
            return {}
            
        # Determine previous trading session
        session_date, session_start, session_end = self._get_previous_session_bounds()
        
        if not session_date:
            logger.info("No previous session to reconcile")
            return {}
            
        # Check if we've already reconciled this session
        last_reconcile = db.get_last_reconcile_date()
        if last_reconcile == session_date:
            logger.info(f"Session {session_date} already reconciled")
            return {}
            
        logger.info(f"Starting reconciliation for session {session_date} ({len(symbols)} symbols)")
        
        results = {}
        include_extended_hours = db.get_setting('INCLUDE_EXTENDED_HOURS', 'false').lower() == 'true'
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            for symbol in symbols:
                try:
                    # Check if we have data for this session
                    live_data = storage.get_session_data(
                        symbol, "5m", session_start, session_end
                    )
                    
                    if live_data.empty:
                        logger.debug(f"No live data to reconcile for {symbol} on {session_date}")
                        continue
                        
                    # Fetch official data for the session
                    official_data = await self._fetch_official_session_data(
                        client, symbol, session_start, session_end, include_extended_hours
                    )
                    
                    if official_data.empty:
                        logger.debug(f"No official data available for {symbol} on {session_date}")
                        continue
                        
                    # Reconcile the data
                    bars_updated = storage.reconcile_session_data(
                        symbol, "5m", official_data, session_date
                    )
                    
                    results[symbol] = bars_updated
                    
                    if bars_updated > 0:
                        logger.info(f"Reconciled {bars_updated} bars for {symbol} on {session_date}")
                    
                except Exception as e:
                    logger.error(f"Error reconciling {symbol} for {session_date}: {e}")
                    results[symbol] = 0
                    
        total_updated = sum(results.values())
        logger.info(f"Reconciliation completed: {total_updated} total bars updated across {len(results)} symbols")
        
        return results
        
    def _get_previous_session_bounds(self) -> tuple[Optional[str], Optional[datetime], Optional[datetime]]:
        """Get the bounds for the previous trading session."""
        try:
            now = datetime.now(timezone.utc)
            
            # Look back up to 5 days to find the last trading day
            for days_back in range(1, 6):
                candidate_date = now - timedelta(days=days_back)
                
                if market_calendar.is_market_day(candidate_date):
                    # Found the last trading day
                    include_extended_hours = db.get_setting(
                        'INCLUDE_EXTENDED_HOURS', 'false'
                    ).lower() == 'true'
                    
                    session_start, session_end = market_calendar.get_trading_session_bounds(
                        candidate_date, include_extended_hours
                    )
                    
                    session_date = candidate_date.strftime('%Y-%m-%d')
                    return session_date, session_start, session_end
                    
            return None, None, None
            
        except Exception as e:
            logger.error(f"Error determining previous session bounds: {e}")
            return None, None, None
            
    async def _fetch_official_session_data(self, client: httpx.AsyncClient, symbol: str,
                                          session_start: datetime, session_end: datetime,
                                          include_extended_hours: bool) -> pd.DataFrame:
        """Fetch official adjusted data for a trading session."""
        try:
            # Acquire rate limit permission
            await rate_limiter.acquire_with_backoff()
            
            # Request 1-minute data for accuracy
            url = "https://finnhub.io/api/v1/stock/candle"
            params = {
                'symbol': symbol,
                'resolution': '1',
                'from': int(session_start.timestamp()),
                'to': int(session_end.timestamp()),
                'token': self.api_key,
                'adjusted': 'true'  # Critical: ensure adjustments for splits/dividends
            }
            
            response = await client.get(url, params=params)
            
            if response.status_code == 429:
                # Rate limit - wait and retry once
                await asyncio.sleep(5)
                response = await client.get(url, params=params)
                
            response.raise_for_status()
            data = response.json()
            
            if data.get('s') != 'ok':
                logger.debug(f"No official data for {symbol}: {data}")
                return pd.DataFrame()
                
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
                return df
                
            # Filter for session hours
            if not include_extended_hours:
                df = df[df['ts'].apply(lambda x: market_calendar.is_regular_hours(x))]
                
            if df.empty:
                return df
                
            # Resample 1-minute to 5-minute bars with proper alignment
            df = df.set_index('ts')
            df_et = df.tz_convert('America/New_York')
            
            df_5m_et = df_et.resample('5T', origin='start').agg({
                'o': 'first',
                'h': 'max',
                'l': 'min',
                'c': 'last',
                'v': 'sum'
            }).dropna()
            
            # Convert back to UTC
            df_5m = df_5m_et.tz_convert('UTC')
            df_5m = df_5m.reset_index()
            
            return df_5m
            
        except Exception as e:
            logger.error(f"Error fetching official data for {symbol}: {e}")
            return pd.DataFrame()
            
    async def run_reconciliation_check(self, symbols: List[str]) -> bool:
        """Run reconciliation check and return True if reconciliation was performed."""
        try:
            # Only run reconciliation after market close or early morning
            now = datetime.now(timezone.utc)
            et_now = now.astimezone(market_calendar.eastern_tz)
            
            # Run reconciliation between 4:30 PM ET and 8:00 AM ET next day
            current_time = et_now.time()
            should_reconcile = (
                current_time >= market_calendar.regular_close or 
                current_time <= market_calendar.regular_open
            )
            
            if not should_reconcile:
                return False
                
            results = await self.reconcile_previous_session(symbols)
            return len(results) > 0
            
        except Exception as e:
            logger.error(f"Error in reconciliation check: {e}")
            return False
            
    def get_reconciliation_stats(self) -> Dict[str, Any]:
        """Get reconciliation statistics."""
        try:
            last_reconcile_date = db.get_last_reconcile_date()
            
            # Get count of reconciliations in last 7 days
            with db.get_session() as session:
                from app.data_access import Reconciliation
                
                week_ago = datetime.now(timezone.utc) - timedelta(days=7)
                recent_reconciliations = session.query(Reconciliation).filter(
                    Reconciliation.reconciled_at >= week_ago
                ).all()
                
                total_bars_updated = sum(r.bars_updated for r in recent_reconciliations)
                unique_symbols = len(set(r.symbol for r in recent_reconciliations))
                
            return {
                'last_reconcile_date': last_reconcile_date,
                'reconciliations_last_7_days': len(recent_reconciliations),
                'bars_updated_last_7_days': total_bars_updated,
                'symbols_reconciled_last_7_days': unique_symbols
            }
            
        except Exception as e:
            logger.error(f"Error getting reconciliation stats: {e}")
            return {
                'last_reconcile_date': None,
                'reconciliations_last_7_days': 0,
                'bars_updated_last_7_days': 0,
                'symbols_reconciled_last_7_days': 0
            }


# Global reconciliation service instance
reconciliation_service = ReconciliationService()