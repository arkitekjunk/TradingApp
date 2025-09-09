import httpx
import json
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from loguru import logger
from pathlib import Path

from app.config import settings, get_config_value
from app.data_access import db

class UniverseManager:
    def __init__(self):
        self.cache_dir = Path("data/cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_dir / "universe.json"
        self.cache_hours = get_config_value("defaults.universe_cache_hours", 12)
    
    async def get_universe_symbols(self, force_refresh: bool = False) -> List[str]:
        """Get the current universe symbols, using cache if valid."""
        
        # Check if we have a valid cache
        if not force_refresh and self._is_cache_valid():
            logger.debug("Using cached universe data")
            return self._load_cached_universe()
        
        # Fetch fresh data from Finnhub
        logger.info("Fetching fresh universe data from Finnhub")
        try:
            symbols = await self._fetch_universe_from_api()
            if symbols:  # Only cache if we got valid symbols
                self._cache_universe(symbols)
            return symbols
        except Exception as e:
            logger.error(f"Failed to fetch universe: {e}")
            
            # Fall back to cache if API fails
            if self.cache_file.exists():
                logger.warning("API failed, falling back to cached data")
                cached_symbols = self._load_cached_universe()
                if cached_symbols:
                    return cached_symbols
            
            # If no cache, return fallback symbols (Top 50 S&P 500 stocks - respects free plan limit)
            logger.warning("No cached data available, using top 50 fallback symbols")
            fallback_symbols = [
                # Top 10 by market cap
                'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'TSLA', 'META', 'BRK.B', 'UNH', 'JNJ',
                
                # Next 20 largest
                'XOM', 'JPM', 'V', 'WMT', 'PG', 'HD', 'CVX', 'MA', 'BAC', 'ABBV',
                'PFE', 'AVGO', 'KO', 'LLY', 'COST', 'PEP', 'MRK', 'TMO', 'DIS', 'ABT',
                
                # Tech & Growth (top 20)
                'NFLX', 'ADBE', 'CRM', 'ORCL', 'ACN', 'CSCO', 'TXN', 'QCOM', 'INTC', 'AMD',
                'IBM', 'NOW', 'UBER', 'PYPL', 'SHOP', 'SNOW', 'ZM', 'DOCU', 'OKTA', 'TWLO'
            ]
            logger.info(f"Using {len(fallback_symbols)} fallback symbols for testing")
            return fallback_symbols
    
    def _is_cache_valid(self) -> bool:
        """Check if the cached universe data is still valid."""
        if not self.cache_file.exists():
            return False
        
        try:
            cache_time = datetime.fromtimestamp(
                self.cache_file.stat().st_mtime, 
                tz=timezone.utc
            )
            expiry_time = cache_time + timedelta(hours=self.cache_hours)
            return datetime.now(timezone.utc) < expiry_time
        except Exception as e:
            logger.error(f"Error checking cache validity: {e}")
            return False
    
    def _load_cached_universe(self) -> List[str]:
        """Load universe symbols from cache file."""
        try:
            with open(self.cache_file, 'r') as f:
                data = json.load(f)
                return data.get('symbols', [])
        except Exception as e:
            logger.error(f"Error loading cached universe: {e}")
            return []
    
    def _cache_universe(self, symbols: List[str]):
        """Cache universe symbols to file."""
        try:
            cache_data = {
                'symbols': symbols,
                'cached_at': datetime.now(timezone.utc).isoformat(),
                'source': get_config_value("defaults.universe_symbol", "^NDX")
            }
            
            with open(self.cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)
                
            logger.info(f"Cached {len(symbols)} universe symbols")
            
        except Exception as e:
            logger.error(f"Error caching universe: {e}")
    
    async def _fetch_universe_from_api(self) -> List[str]:
        """Fetch universe constituents from Finnhub API."""
        universe_symbol = get_config_value("defaults.universe_symbol", "^NDX")
        
        # Get API key from database settings (updated via UI) or fallback to env
        from app.data_access import db
        api_key = db.get_setting("FINNHUB_API_KEY") or settings.finnhub_api_key
        
        if not api_key or api_key == "your_finnhub_api_key_here":
            raise ValueError("Valid Finnhub API key is required. Please set it in the settings.")
        
        url = "https://finnhub.io/api/v1/index/constituents"
        params = {
            'symbol': universe_symbol,
            'token': api_key
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            # Handle different response formats
            if isinstance(data, dict):
                constituents = data.get('constituents', [])
            else:
                constituents = data if isinstance(data, list) else []
            
            if not constituents:
                logger.warning(f"No constituents found for {universe_symbol}")
                # Return comprehensive fallback symbols for testing (Top 50 - respects free plan limit)
                fallback_symbols = [
                    # Top 10 by market cap
                    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'TSLA', 'META', 'BRK.B', 'UNH', 'JNJ',
                    
                    # Next 20 largest
                    'XOM', 'JPM', 'V', 'WMT', 'PG', 'HD', 'CVX', 'MA', 'BAC', 'ABBV',
                    'PFE', 'AVGO', 'KO', 'LLY', 'COST', 'PEP', 'MRK', 'TMO', 'DIS', 'ABT',
                    
                    # Tech & Growth (top 20)
                    'NFLX', 'ADBE', 'CRM', 'ORCL', 'ACN', 'CSCO', 'TXN', 'QCOM', 'INTC', 'AMD',
                    'IBM', 'NOW', 'UBER', 'PYPL', 'SHOP', 'SNOW', 'ZM', 'DOCU', 'OKTA', 'TWLO'
                ]
                logger.warning(f"Using fallback symbols ({len(fallback_symbols)} stocks): {fallback_symbols[:5]}...")
                return fallback_symbols
            
            # Filter out any invalid symbols
            valid_symbols = []
            for symbol in constituents:
                if isinstance(symbol, str) and len(symbol) > 0 and symbol.replace('.', '').replace('-', '').isalnum():
                    valid_symbols.append(symbol)
            
            logger.info(f"Fetched {len(valid_symbols)} valid symbols from {universe_symbol}")
            
            # Update securities in database
            for symbol in valid_symbols:
                db.update_security(symbol)
            
            return valid_symbols
    
    async def refresh_universe(self) -> List[str]:
        """Force refresh the universe data."""
        return await self.get_universe_symbols(force_refresh=True)
    
    def get_cache_info(self) -> Dict[str, Any]:
        """Get information about the current cache status."""
        if not self.cache_file.exists():
            return {
                'cached': False,
                'cache_valid': False,
                'symbols_count': 0
            }
        
        try:
            with open(self.cache_file, 'r') as f:
                data = json.load(f)
            
            cache_time = datetime.fromtimestamp(
                self.cache_file.stat().st_mtime, 
                tz=timezone.utc
            )
            
            return {
                'cached': True,
                'cache_valid': self._is_cache_valid(),
                'cached_at': cache_time.isoformat(),
                'symbols_count': len(data.get('symbols', [])),
                'source': data.get('source', 'unknown'),
                'expires_at': (cache_time + timedelta(hours=self.cache_hours)).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting cache info: {e}")
            return {
                'cached': False,
                'cache_valid': False,
                'symbols_count': 0,
                'error': str(e)
            }

# Global instance
universe_manager = UniverseManager()