"""
Yahoo Finance data provider for historical stock data.
Provides free historical data as an alternative to paid APIs.
"""
import yfinance as yf
import pandas as pd
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from loguru import logger
import asyncio
from concurrent.futures import ThreadPoolExecutor


class YahooFinanceProvider:
    """Yahoo Finance data provider for historical stock data."""
    
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=4)
    
    async def get_historical_data(self, symbol: str, start_time: datetime, 
                                end_time: datetime, interval: str = "5m") -> Optional[pd.DataFrame]:
        """
        Get historical stock data from Yahoo Finance.
        
        Args:
            symbol: Stock symbol (e.g., 'AAPL')
            start_time: Start datetime (UTC)
            end_time: End datetime (UTC) 
            interval: Data interval ('1m', '5m', '15m', '30m', '1h', '1d')
            
        Returns:
            DataFrame with columns: ts, o, h, l, c, v
        """
        try:
            # Run Yahoo Finance API call in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(
                self.executor, 
                self._fetch_yahoo_data, 
                symbol, start_time, end_time, interval
            )
            
            if data is None or data.empty:
                logger.debug(f"No Yahoo Finance data for {symbol}")
                return None
                
            # Convert to our standard format
            df = pd.DataFrame({
                'ts': data.index.tz_convert('UTC'),
                'o': data['Open'],
                'h': data['High'], 
                'l': data['Low'],
                'c': data['Close'],
                'v': data['Volume']
            })
            
            # Reset index to make timestamp a column
            df = df.reset_index(drop=True)
            
            logger.info(f"Retrieved {len(df)} {interval} bars for {symbol} from Yahoo Finance")
            return df
            
        except Exception as e:
            logger.error(f"Error fetching Yahoo Finance data for {symbol}: {e}")
            return None
    
    def _fetch_yahoo_data(self, symbol: str, start_time: datetime, 
                         end_time: datetime, interval: str) -> Optional[pd.DataFrame]:
        """Synchronous Yahoo Finance data fetch (runs in thread pool)."""
        try:
            # Use the correct yfinance syntax for maximum data retrieval
            ticker = yf.Ticker(symbol)
            
            # For intraday intervals, use period-based approach for maximum data
            if interval in ['1m', '2m', '5m', '15m', '30m', '60m', '1h']:
                if interval == '1m':
                    period = "7d"  # 1-minute bars: only 7 days available
                else:
                    period = "60d"  # Get full 60 days for other intraday intervals
                
                # This should return ~3,000-3,500 bars for 5m interval
                data = ticker.history(
                    period=period,
                    interval=interval,
                    prepost=False,  # Regular market hours only 
                    repair=True,    # Fix stock splits/dividends
                    auto_adjust=True  # Adjust for splits and dividends
                )
                
                logger.debug(f"Yahoo Finance returned {len(data) if not data.empty else 0} bars for {symbol} with period={period}, interval={interval}")
                
            else:
                # For daily/weekly/monthly, use start/end dates
                data = ticker.history(
                    start=start_time.date(),
                    end=end_time.date(),
                    interval=interval,
                    prepost=False,
                    repair=True,
                    auto_adjust=True
                )
            
            if data.empty:
                logger.debug(f"No Yahoo data returned for {symbol}")
                return None
            
            # Filter to exact time range requested
            # Convert datetime objects to naive for comparison with yfinance index
            start_naive = start_time.replace(tzinfo=None) if start_time.tzinfo else start_time
            end_naive = end_time.replace(tzinfo=None) if end_time.tzinfo else end_time
            
            # Convert data index to naive if needed
            if hasattr(data.index, 'tz') and data.index.tz is not None:
                data_index = data.index.tz_convert(None)
            else:
                data_index = data.index
            
            # Filter using naive timestamps
            mask = (data_index >= start_naive) & (data_index <= end_naive)
            data = data[mask]
            
            return data
            
        except Exception as e:
            logger.error(f"Yahoo Finance fetch error for {symbol}: {e}")
            return None
    
    async def get_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get real-time quote from Yahoo Finance.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Quote data dict with current price info
        """
        try:
            loop = asyncio.get_event_loop()
            ticker = yf.Ticker(symbol)
            
            # Get current quote data
            info = await loop.run_in_executor(self.executor, ticker.info)
            
            if not info or 'regularMarketPrice' not in info:
                return None
                
            return {
                'c': info.get('regularMarketPrice', 0),         # Current price
                'h': info.get('regularMarketDayHigh', 0),       # Day high  
                'l': info.get('regularMarketDayLow', 0),        # Day low
                'o': info.get('regularMarketOpen', 0),          # Day open
                'pc': info.get('regularMarketPreviousClose', 0), # Previous close
                'd': info.get('regularMarketPrice', 0) - info.get('regularMarketPreviousClose', 0),  # Change
                'dp': ((info.get('regularMarketPrice', 0) - info.get('regularMarketPreviousClose', 0)) / 
                      info.get('regularMarketPreviousClose', 1)) * 100,  # Change percent
                't': int(datetime.now().timestamp())  # Current timestamp
            }
            
        except Exception as e:
            logger.error(f"Error fetching Yahoo quote for {symbol}: {e}")
            return None
    
    def close(self):
        """Clean up resources."""
        if self.executor:
            self.executor.shutdown(wait=False)


# Global Yahoo Finance provider instance
yahoo_provider = YahooFinanceProvider()