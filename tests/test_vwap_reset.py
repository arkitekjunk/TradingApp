import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone
import pytz
from unittest.mock import patch, MagicMock

from app.indicators import IndicatorCalculator


class TestVWAPReset:
    """Test VWAP session reset functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.indicator_calc = IndicatorCalculator()
    
    def create_test_data(self, timestamps, prices, volumes):
        """Create test OHLCV DataFrame."""
        return pd.DataFrame({
            'o': prices,
            'h': [p * 1.01 for p in prices],  # High slightly above open
            'l': [p * 0.99 for p in prices],  # Low slightly below open
            'c': prices,
            'v': volumes
        }, index=pd.to_datetime(timestamps, utc=True))
    
    @patch('app.data_access.db.get_setting')
    def test_vwap_resets_at_session_open(self, mock_get_setting):
        """Test that VWAP resets at 9:30 AM ET."""
        mock_get_setting.return_value = 'false'  # Regular hours only
        
        et_tz = pytz.timezone('America/New_York')
        
        # Create data spanning across session boundary
        timestamps = [
            et_tz.localize(datetime(2024, 1, 8, 15, 55)).astimezone(timezone.utc),  # Previous session end
            et_tz.localize(datetime(2024, 1, 9, 9, 30)).astimezone(timezone.utc),   # New session start
            et_tz.localize(datetime(2024, 1, 9, 9, 35)).astimezone(timezone.utc),   # New session continue
            et_tz.localize(datetime(2024, 1, 9, 9, 40)).astimezone(timezone.utc)    # New session continue
        ]
        
        prices = [100.0, 101.0, 102.0, 103.0]
        volumes = [1000, 1000, 1000, 1000]
        
        df = self.create_test_data(timestamps, prices, volumes)
        vwap_series = self.indicator_calc._calculate_session_vwap(df)
        
        # VWAP should reset at the new session start
        # First bar should be calculated normally
        assert vwap_series.iloc[0] > 0
        
        # Second bar (new session) should start fresh calculation
        # VWAP should be close to the typical price of the second bar
        typical_price_2nd = (df.iloc[1]['h'] + df.iloc[1]['l'] + df.iloc[1]['c']) / 3
        assert abs(vwap_series.iloc[1] - typical_price_2nd) < 0.1
        
        # Third bar should accumulate from second bar, not first
        assert vwap_series.iloc[2] != vwap_series.iloc[0]
    
    @patch('app.data_access.db.get_setting')
    def test_vwap_excludes_extended_hours_when_disabled(self, mock_get_setting):
        """Test VWAP excludes extended hours when setting is false."""
        mock_get_setting.return_value = 'false'  # Regular hours only
        
        et_tz = pytz.timezone('America/New_York')
        
        # Mix of regular and extended hours
        timestamps = [
            et_tz.localize(datetime(2024, 1, 8, 8, 0)).astimezone(timezone.utc),    # Pre-market
            et_tz.localize(datetime(2024, 1, 8, 9, 30)).astimezone(timezone.utc),   # Regular hours start
            et_tz.localize(datetime(2024, 1, 8, 10, 0)).astimezone(timezone.utc),   # Regular hours
            et_tz.localize(datetime(2024, 1, 8, 17, 0)).astimezone(timezone.utc)    # After hours
        ]
        
        prices = [100.0, 101.0, 102.0, 103.0]
        volumes = [1000, 1000, 1000, 1000]
        
        df = self.create_test_data(timestamps, prices, volumes)
        vwap_series = self.indicator_calc._calculate_session_vwap(df)
        
        # Pre-market bar should use close price as fallback
        assert abs(vwap_series.iloc[0] - prices[0]) < 0.1
        
        # Regular hours should calculate VWAP normally
        typical_price_regular = (df.iloc[1]['h'] + df.iloc[1]['l'] + df.iloc[1]['c']) / 3
        assert abs(vwap_series.iloc[1] - typical_price_regular) < 0.1
        
        # After hours should carry forward the last regular hours VWAP
        assert vwap_series.iloc[3] == vwap_series.iloc[2]
    
    @patch('app.data_access.db.get_setting')
    def test_vwap_includes_extended_hours_when_enabled(self, mock_get_setting):
        """Test VWAP includes extended hours when setting is true."""
        mock_get_setting.return_value = 'true'  # Extended hours enabled
        
        et_tz = pytz.timezone('America/New_York')
        
        # Mix of regular and extended hours
        timestamps = [
            et_tz.localize(datetime(2024, 1, 8, 8, 0)).astimezone(timezone.utc),    # Pre-market
            et_tz.localize(datetime(2024, 1, 8, 9, 30)).astimezone(timezone.utc),   # Regular hours start
            et_tz.localize(datetime(2024, 1, 8, 10, 0)).astimezone(timezone.utc),   # Regular hours
            et_tz.localize(datetime(2024, 1, 8, 17, 0)).astimezone(timezone.utc)    # After hours
        ]
        
        prices = [100.0, 101.0, 102.0, 103.0]
        volumes = [1000, 1000, 1000, 1000]
        
        df = self.create_test_data(timestamps, prices, volumes)
        vwap_series = self.indicator_calc._calculate_session_vwap(df)
        
        # All bars should be included in VWAP calculation
        # Each should have a valid VWAP value (not just carried forward)
        for i in range(len(vwap_series)):
            assert vwap_series.iloc[i] > 0
            assert not np.isnan(vwap_series.iloc[i])
        
        # VWAP should be cumulative - later bars should reflect accumulated volume
        assert vwap_series.iloc[3] != vwap_series.iloc[0]  # Should be different due to accumulation
    
    @patch('app.data_access.db.get_setting')
    def test_vwap_accumulates_within_session(self, mock_get_setting):
        """Test VWAP properly accumulates within a session."""
        mock_get_setting.return_value = 'false'  # Regular hours only
        
        et_tz = pytz.timezone('America/New_York')
        
        # All within same session
        timestamps = [
            et_tz.localize(datetime(2024, 1, 8, 9, 30)).astimezone(timezone.utc),   # Session start
            et_tz.localize(datetime(2024, 1, 8, 9, 35)).astimezone(timezone.utc),   # +5 min
            et_tz.localize(datetime(2024, 1, 8, 9, 40)).astimezone(timezone.utc),   # +10 min
        ]
        
        # Prices trending up, equal volumes
        prices = [100.0, 110.0, 120.0]
        volumes = [1000, 1000, 1000]
        
        df = self.create_test_data(timestamps, prices, volumes)
        vwap_series = self.indicator_calc._calculate_session_vwap(df)
        
        # First bar VWAP should equal typical price
        typical_1 = (df.iloc[0]['h'] + df.iloc[0]['l'] + df.iloc[0]['c']) / 3
        assert abs(vwap_series.iloc[0] - typical_1) < 0.1
        
        # Second bar should be weighted average of first two
        typical_2 = (df.iloc[1]['h'] + df.iloc[1]['l'] + df.iloc[1]['c']) / 3
        expected_vwap_2 = (typical_1 * 1000 + typical_2 * 1000) / 2000
        assert abs(vwap_series.iloc[1] - expected_vwap_2) < 0.1
        
        # Third bar should be weighted average of all three
        typical_3 = (df.iloc[2]['h'] + df.iloc[2]['l'] + df.iloc[2]['c']) / 3
        expected_vwap_3 = (typical_1 * 1000 + typical_2 * 1000 + typical_3 * 1000) / 3000
        assert abs(vwap_series.iloc[2] - expected_vwap_3) < 0.1
    
    def test_vwap_handles_empty_dataframe(self):
        """Test VWAP calculation with empty DataFrame."""
        df = pd.DataFrame()
        vwap_series = self.indicator_calc._calculate_session_vwap(df)
        
        assert len(vwap_series) == 0
        assert vwap_series.dtype == float
    
    @patch('app.data_access.db.get_setting')
    def test_vwap_fallback_on_error(self, mock_get_setting):
        """Test VWAP falls back gracefully on calculation errors."""
        mock_get_setting.return_value = 'false'
        
        # Create DataFrame with problematic data
        df = pd.DataFrame({
            'o': [100.0],
            'h': [np.inf],  # Infinite high price
            'l': [100.0],
            'c': [100.0],
            'v': [1000]
        }, index=pd.to_datetime(['2024-01-08 14:30:00'], utc=True))
        
        # Should not raise exception, should return fallback
        vwap_series = self.indicator_calc._calculate_session_vwap(df)
        assert len(vwap_series) == 1
        assert not np.isnan(vwap_series.iloc[0])
        assert not np.isinf(vwap_series.iloc[0])