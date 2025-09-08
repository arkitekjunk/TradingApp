import pandas as pd
import numpy as np
from datetime import datetime, timezone, time
from typing import Dict, Any, Optional, List, Tuple
from loguru import logger

from app.config import get_config_value
from app.data_access import db, storage
from app.market_calendar import market_calendar

class IndicatorCalculator:
    def __init__(self):
        self.ema_fast = get_config_value("indicators.ema_fast", 9)
        self.ema_slow = get_config_value("indicators.ema_slow", 21)
        self.rsi_period = get_config_value("indicators.rsi_period", 14)
        self.bb_period = get_config_value("indicators.bb_period", 20)
        self.bb_std = get_config_value("indicators.bb_std", 2.0)
        self.rsi_overbought = get_config_value("indicators.rsi_overbought", 70)
        self.rsi_oversold = get_config_value("indicators.rsi_oversold", 30)
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate all technical indicators for the given OHLCV data."""
        if df.empty or len(df) < self.ema_slow:
            return df
        
        df = df.copy()
        
        try:
            # EMAs
            df[f'ema_{self.ema_fast}'] = self._calculate_ema(df['c'], self.ema_fast)
            df[f'ema_{self.ema_slow}'] = self._calculate_ema(df['c'], self.ema_slow)
            
            # RSI
            df['rsi'] = self._calculate_rsi(df['c'], self.rsi_period)
            
            # Bollinger Bands
            bb_upper, bb_middle, bb_lower = self._calculate_bollinger_bands(df['c'], self.bb_period, self.bb_std)
            df['bb_upper'] = bb_upper
            df['bb_middle'] = bb_middle
            df['bb_lower'] = bb_lower
            
            # Session VWAP (resets daily)
            df['vwap'] = self._calculate_session_vwap(df)
            
            # ATR (Average True Range)
            df['atr'] = self._calculate_atr(df['h'], df['l'], df['c'], 14)
            
            # Relative Volume
            df['rvol'] = self._calculate_rvol(df)
            
            logger.debug(f"Calculated indicators for {len(df)} bars")
            
        except Exception as e:
            logger.error(f"Error calculating indicators: {e}")
        
        return df
    
    def _calculate_ema(self, prices: pd.Series, period: int) -> pd.Series:
        """Calculate Exponential Moving Average."""
        return prices.ewm(span=period, adjust=False).mean()
    
    def _calculate_rsi(self, prices: pd.Series, period: int) -> pd.Series:
        """Calculate Relative Strength Index."""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    
    def _calculate_bollinger_bands(self, prices: pd.Series, period: int, std: float):
        """Calculate Bollinger Bands."""
        sma = prices.rolling(window=period).mean()
        rolling_std = prices.rolling(window=period).std()
        upper = sma + (rolling_std * std)
        lower = sma - (rolling_std * std)
        return upper, sma, lower
    
    def _calculate_atr(self, high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
        """Calculate Average True Range."""
        prev_close = close.shift(1)
        tr1 = high - low
        tr2 = abs(high - prev_close)
        tr3 = abs(low - prev_close)
        true_range = pd.DataFrame({'tr1': tr1, 'tr2': tr2, 'tr3': tr3}).max(axis=1)
        return true_range.rolling(window=period).mean()
    
    def _calculate_session_vwap(self, df: pd.DataFrame) -> pd.Series:
        """Calculate session-aware VWAP that resets at 9:30 AM ET and respects extended hours setting."""
        if df.empty:
            return pd.Series(dtype=float, index=df.index)
        
        try:
            # Get extended hours setting
            include_extended_hours = db.get_setting('INCLUDE_EXTENDED_HOURS', 'false').lower() == 'true'
            
            # Create a copy with timezone-aware index
            df_copy = df.copy()
            if df_copy.index.tz is None:
                df_copy.index = df_copy.index.tz_localize('UTC')
            
            # Initialize VWAP series
            vwap_values = pd.Series(index=df.index, dtype=float)
            
            # Track session state
            cum_pv = 0
            cum_vol = 0
            last_session_open = None
            
            for timestamp, row in df_copy.iterrows():
                # Check if we should include this bar based on extended hours setting
                if not market_calendar.should_include_in_session(timestamp, include_extended_hours):
                    # For excluded bars, carry forward the last VWAP value
                    if len(vwap_values.dropna()) > 0:
                        vwap_values.loc[timestamp] = vwap_values.dropna().iloc[-1]
                    else:
                        vwap_values.loc[timestamp] = row['c']  # Use close price if no VWAP yet
                    continue
                
                # Check for session reset (9:30 AM ET)
                current_session_open = market_calendar.get_session_open(timestamp)
                
                if last_session_open is None or current_session_open != last_session_open:
                    # New session - reset VWAP calculation
                    cum_pv = 0
                    cum_vol = 0
                    last_session_open = current_session_open
                    logger.debug(f"VWAP reset at session open: {current_session_open}")
                
                # Calculate typical price and accumulate
                typical_price = (row['h'] + row['l'] + row['c']) / 3
                pv = typical_price * row['v']
                
                cum_pv += pv
                cum_vol += row['v']
                
                # Calculate VWAP
                if cum_vol > 0:
                    vwap_values.loc[timestamp] = cum_pv / cum_vol
                else:
                    vwap_values.loc[timestamp] = typical_price
            
            # Forward fill any remaining NaN values
            vwap_values = vwap_values.fillna(method='ffill')
            
            return vwap_values
            
        except Exception as e:
            logger.warning(f"Error calculating session-aware VWAP: {e}")
            # Fallback to simple VWAP
            if 'v' in df.columns and df['v'].sum() > 0:
                typical_price = (df['h'] + df['l'] + df['c']) / 3
                pv_cum = (typical_price * df['v']).cumsum()
                v_cum = df['v'].cumsum()
                return pv_cum / v_cum.replace(0, np.nan)
            else:
                return pd.Series(df['c'], index=df.index)  # Fallback to close price
    
    def _calculate_rvol(self, df: pd.DataFrame, lookback_days: int = 20) -> pd.Series:
        """Calculate Relative Volume (current volume vs average volume)."""
        if df.empty or 'v' not in df.columns:
            return pd.Series(1.0, index=df.index)
        
        try:
            # Calculate 20-day average volume
            avg_volume = df['v'].rolling(window=lookback_days * 78, min_periods=10).mean()  # ~78 bars per day (5min)
            
            # Calculate relative volume
            rvol = df['v'] / avg_volume
            
            # Handle NaN and infinite values
            rvol = rvol.fillna(1.0).replace([np.inf, -np.inf], 1.0)
            
            return rvol
            
        except Exception as e:
            logger.warning(f"Error calculating RVOL: {e}")
            return pd.Series(1.0, index=df.index)

class SignalProcessor:
    def __init__(self):
        self.indicator_calc = IndicatorCalculator()
        self.signal_config = get_config_value("signals.long_trigger", {})
    
    def process_candles(self, symbol: str, tf: str, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Process candles and generate signals."""
        if df.empty:
            return []
        
        # Calculate indicators
        df_with_indicators = self.indicator_calc.calculate_indicators(df)
        
        # Check for signals on the latest few bars
        signals = []
        recent_bars = df_with_indicators.tail(5)  # Check last 5 bars for signals
        
        for idx, row in recent_bars.iterrows():
            if pd.isna(row.get('ema_9')) or pd.isna(row.get('ema_21')):
                continue
                
            signal = self._check_long_signal(symbol, tf, idx, row, df_with_indicators)
            if signal:
                signals.append(signal)
        
        return signals
    
    def _check_long_signal(self, symbol: str, tf: str, timestamp: datetime, 
                          current_row: pd.Series, df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """Check if long signal conditions are met."""
        try:
            # Get the current bar index
            current_idx = df.index.get_loc(timestamp)
            
            # Need at least 2 bars for crossover
            if current_idx < 1:
                return None
            
            prev_row = df.iloc[current_idx - 1]
            
            # Signal conditions
            conditions = {}
            
            # 1. EMA crossover - EMA9 crosses above EMA21
            if self.signal_config.get("ema_cross_above", True):
                ema9_cross = (current_row['ema_9'] > current_row['ema_21'] and 
                            prev_row['ema_9'] <= prev_row['ema_21'])
                conditions['ema_cross_above'] = ema9_cross
            else:
                conditions['ema_cross_above'] = True
            
            # 2. RSI > 50
            rsi_min = self.signal_config.get("rsi_min", 50)
            conditions['rsi_above_min'] = current_row['rsi'] > rsi_min
            
            # 3. Price above session VWAP
            if self.signal_config.get("price_above_vwap", True):
                conditions['price_above_vwap'] = current_row['c'] >= current_row['vwap']
            else:
                conditions['price_above_vwap'] = True
            
            # 4. Relative Volume >= threshold
            min_rvol = self.signal_config.get("min_rvol", 2.0)
            conditions['rvol_above_min'] = current_row['rvol'] >= min_rvol
            
            # Check if all conditions are met
            all_conditions_met = all(conditions.values())
            
            if all_conditions_met:
                signal_details = {
                    'price': float(current_row['c']),
                    'ema_9': float(current_row['ema_9']),
                    'ema_21': float(current_row['ema_21']),
                    'rsi': float(current_row['rsi']),
                    'vwap': float(current_row['vwap']),
                    'rvol': float(current_row['rvol']),
                    'volume': int(current_row['v']),
                    'conditions': conditions
                }
                
                # Store signal in database
                db.add_signal(
                    symbol=symbol,
                    tf=tf,
                    ts=timestamp,
                    rule="long_trigger",
                    details=signal_details
                )
                
                logger.info(f"Long signal fired for {symbol} at {timestamp}: "
                          f"price={current_row['c']:.2f}, rsi={current_row['rsi']:.1f}, "
                          f"rvol={current_row['rvol']:.1f}")
                
                return {
                    'symbol': symbol,
                    'tf': tf,
                    'timestamp': timestamp.isoformat(),
                    'rule': 'long_trigger',
                    'details': signal_details
                }
            
        except Exception as e:
            logger.error(f"Error checking long signal for {symbol}: {e}")
        
        return None
    
    def get_latest_signals(self, symbol: str = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Get the latest signals from database."""
        return db.get_signals(symbol=symbol, limit=limit)

# Global instances
indicator_calculator = IndicatorCalculator()
signal_processor = SignalProcessor()