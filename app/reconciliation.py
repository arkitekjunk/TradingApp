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
        
    async def reconcile_previous_session(self, symbols: List[str]) -> Dict[str, int]:
        """
        Reconcile the previous trading session's data for given symbols.
        
        Args:
            symbols: List of symbols to reconcile
            
        Returns:
            Dict mapping symbol -> number of bars updated
        """
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
            
        logger.info(f"Starting reconciliation for session {session_date} ({len(symbols)} symbols)\")\n        \n        results = {}\n        include_extended_hours = db.get_setting('INCLUDE_EXTENDED_HOURS', 'false').lower() == 'true'\n        \n        async with httpx.AsyncClient(timeout=60.0) as client:\n            for symbol in symbols:\n                try:\n                    # Check if we have data for this session\n                    live_data = storage.get_session_data(\n                        symbol, \"5m\", session_start, session_end\n                    )\n                    \n                    if live_data.empty:\n                        logger.debug(f\"No live data to reconcile for {symbol} on {session_date}\")\n                        continue\n                        \n                    # Fetch official data for the session\n                    official_data = await self._fetch_official_session_data(\n                        client, symbol, session_start, session_end, include_extended_hours\n                    )\n                    \n                    if official_data.empty:\n                        logger.debug(f\"No official data available for {symbol} on {session_date}\")\n                        continue\n                        \n                    # Reconcile the data\n                    bars_updated = storage.reconcile_session_data(\n                        symbol, \"5m\", official_data, session_date\n                    )\n                    \n                    results[symbol] = bars_updated\n                    \n                    if bars_updated > 0:\n                        logger.info(f\"Reconciled {bars_updated} bars for {symbol} on {session_date}\")\n                    \n                except Exception as e:\n                    logger.error(f\"Error reconciling {symbol} for {session_date}: {e}\")\n                    results[symbol] = 0\n                    \n        total_updated = sum(results.values())\n        logger.info(f\"Reconciliation completed: {total_updated} total bars updated across {len(results)} symbols\")\n        \n        return results\n        \n    def _get_previous_session_bounds(self) -> tuple[Optional[str], Optional[datetime], Optional[datetime]]:\n        \"\"\"Get the bounds for the previous trading session.\"\"\"\n        try:\n            now = datetime.now(timezone.utc)\n            \n            # Look back up to 5 days to find the last trading day\n            for days_back in range(1, 6):\n                candidate_date = now - timedelta(days=days_back)\n                \n                if market_calendar.is_market_day(candidate_date):\n                    # Found the last trading day\n                    include_extended_hours = db.get_setting(\n                        'INCLUDE_EXTENDED_HOURS', 'false'\n                    ).lower() == 'true'\n                    \n                    session_start, session_end = market_calendar.get_trading_session_bounds(\n                        candidate_date, include_extended_hours\n                    )\n                    \n                    session_date = candidate_date.strftime('%Y-%m-%d')\n                    return session_date, session_start, session_end\n                    \n            return None, None, None\n            \n        except Exception as e:\n            logger.error(f\"Error determining previous session bounds: {e}\")\n            return None, None, None\n            \n    async def _fetch_official_session_data(self, client: httpx.AsyncClient, symbol: str,\n                                          session_start: datetime, session_end: datetime,\n                                          include_extended_hours: bool) -> pd.DataFrame:\n        \"\"\"Fetch official adjusted data for a trading session.\"\"\"\n        try:\n            # Acquire rate limit permission\n            await rate_limiter.acquire_with_backoff()\n            \n            # Request 1-minute data for accuracy\n            url = \"https://finnhub.io/api/v1/stock/candle\"\n            params = {\n                'symbol': symbol,\n                'resolution': '1',\n                'from': int(session_start.timestamp()),\n                'to': int(session_end.timestamp()),\n                'token': self.api_key,\n                'adjusted': 'true'  # Critical: ensure adjustments for splits/dividends\n            }\n            \n            response = await client.get(url, params=params)\n            \n            if response.status_code == 429:\n                # Rate limit - wait and retry once\n                await asyncio.sleep(5)\n                response = await client.get(url, params=params)\n                \n            response.raise_for_status()\n            data = response.json()\n            \n            if data.get('s') != 'ok':\n                logger.debug(f\"No official data for {symbol}: {data}\")\n                return pd.DataFrame()\n                \n            # Convert to DataFrame\n            df = pd.DataFrame({\n                'ts': pd.to_datetime(data['t'], unit='s', utc=True),\n                'o': data['o'],\n                'h': data['h'],\n                'l': data['l'],\n                'c': data['c'],\n                'v': data['v']\n            })\n            \n            if df.empty:\n                return df\n                \n            # Filter for session hours\n            if not include_extended_hours:\n                df = df[df['ts'].apply(lambda x: market_calendar.is_regular_hours(x))]\n                \n            if df.empty:\n                return df\n                \n            # Resample 1-minute to 5-minute bars with proper alignment\n            df = df.set_index('ts')\n            df_et = df.tz_convert('America/New_York')\n            \n            df_5m_et = df_et.resample('5T', origin='start').agg({\n                'o': 'first',\n                'h': 'max',\n                'l': 'min',\n                'c': 'last',\n                'v': 'sum'\n            }).dropna()\n            \n            # Convert back to UTC\n            df_5m = df_5m_et.tz_convert('UTC')\n            df_5m = df_5m.reset_index()\n            \n            return df_5m\n            \n        except Exception as e:\n            logger.error(f\"Error fetching official data for {symbol}: {e}\")\n            return pd.DataFrame()\n            \n    async def run_reconciliation_check(self, symbols: List[str]) -> bool:\n        \"\"\"Run reconciliation check and return True if reconciliation was performed.\"\"\"\n        try:\n            # Only run reconciliation after market close or early morning\n            now = datetime.now(timezone.utc)\n            et_now = now.astimezone(market_calendar.eastern_tz)\n            \n            # Run reconciliation between 4:30 PM ET and 8:00 AM ET next day\n            current_time = et_now.time()\n            should_reconcile = (\n                current_time >= market_calendar.regular_close or \n                current_time <= market_calendar.regular_open\n            )\n            \n            if not should_reconcile:\n                return False\n                \n            results = await self.reconcile_previous_session(symbols)\n            return len(results) > 0\n            \n        except Exception as e:\n            logger.error(f\"Error in reconciliation check: {e}\")\n            return False\n            \n    def get_reconciliation_stats(self) -> Dict[str, Any]:\n        \"\"\"Get reconciliation statistics.\"\"\"\n        try:\n            last_reconcile_date = db.get_last_reconcile_date()\n            \n            # Get count of reconciliations in last 7 days\n            with db.get_session() as session:\n                from app.data_access import Reconciliation\n                \n                week_ago = datetime.now(timezone.utc) - timedelta(days=7)\n                recent_reconciliations = session.query(Reconciliation).filter(\n                    Reconciliation.reconciled_at >= week_ago\n                ).all()\n                \n                total_bars_updated = sum(r.bars_updated for r in recent_reconciliations)\n                unique_symbols = len(set(r.symbol for r in recent_reconciliations))\n                \n            return {\n                'last_reconcile_date': last_reconcile_date,\n                'reconciliations_last_7_days': len(recent_reconciliations),\n                'bars_updated_last_7_days': total_bars_updated,\n                'symbols_reconciled_last_7_days': unique_symbols\n            }\n            \n        except Exception as e:\n            logger.error(f\"Error getting reconciliation stats: {e}\")\n            return {\n                'last_reconcile_date': None,\n                'reconciliations_last_7_days': 0,\n                'bars_updated_last_7_days': 0,\n                'symbols_reconciled_last_7_days': 0\n            }\n\n\n# Global reconciliation service instance\nreconciliation_service = ReconciliationService()