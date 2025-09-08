import pytest
import pandas as pd
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, AsyncMock, patch
from app.data_access import CandleStorage
from app.worker import FinnhubWorker
import tempfile
import os

class TestGapBackfill:
    def setup_method(self):
        # Use temporary directory for testing
        self.temp_dir = tempfile.mkdtemp()
        self.storage = CandleStorage(self.temp_dir)
        
    def teardown_method(self):
        # Clean up temporary files
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def create_sample_candles(self, start_time: datetime, count: int, interval_minutes: int = 5):
        """Create sample candle data for testing."""
        candles = []
        current_time = start_time
        
        for i in range(count):
            candles.append({
                'ts': current_time,
                'o': 100.0 + i * 0.1,
                'h': 100.5 + i * 0.1,
                'l': 99.5 + i * 0.1,
                'c': 100.2 + i * 0.1,
                'v': 1000 + i * 10
            })
            current_time += timedelta(minutes=interval_minutes)
        
        return pd.DataFrame(candles)
    
    def test_write_and_read_candles(self):
        """Test basic candle storage functionality."""
        symbol = "AAPL"
        tf = "5m"
        
        # Create sample data
        start_time = datetime(2022, 1, 1, tzinfo=timezone.utc)
        df = self.create_sample_candles(start_time, 10)
        
        # Write candles
        self.storage.write_candles(symbol, tf, df)
        
        # Read candles back
        result = self.storage.read_candles(symbol, tf)
        
        assert len(result) == 10
        assert result.index[0] == start_time
        assert result.iloc[0]['o'] == 100.0
        assert result.iloc[0]['v'] == 1000
    
    def test_upsert_behavior(self):
        """Test that writing candles upserts (updates existing, adds new)."""
        symbol = "AAPL"
        tf = "5m"
        
        # Initial data
        start_time = datetime(2022, 1, 1, tzinfo=timezone.utc)
        df1 = self.create_sample_candles(start_time, 5)
        self.storage.write_candles(symbol, tf, df1)
        
        # Read initial data
        initial = self.storage.read_candles(symbol, tf)
        assert len(initial) == 5
        
        # New data that overlaps and extends
        # First 2 candles overlap (should update), next 3 are new
        overlap_start = start_time
        df2 = self.create_sample_candles(overlap_start, 5)
        df2.iloc[0, df2.columns.get_loc('o')] = 200.0  # Change first candle
        df2.iloc[1, df2.columns.get_loc('o')] = 201.0  # Change second candle
        
        self.storage.write_candles(symbol, tf, df2)
        
        # Read updated data
        result = self.storage.read_candles(symbol, tf)
        
        # Should still have 5 candles (no duplicates)
        assert len(result) == 5
        
        # First candle should be updated
        assert result.iloc[0]['o'] == 200.0
        assert result.iloc[1]['o'] == 201.0
    
    def test_time_range_filtering(self):
        """Test reading candles with time range filters."""
        symbol = "AAPL"
        tf = "5m"
        
        # Create 20 candles starting from 2022-01-01
        start_time = datetime(2022, 1, 1, tzinfo=timezone.utc)
        df = self.create_sample_candles(start_time, 20)
        self.storage.write_candles(symbol, tf, df)
        
        # Read with start_time filter
        filter_start = start_time + timedelta(minutes=25)  # Skip first 5 candles
        result = self.storage.read_candles(symbol, tf, start_time=filter_start)
        
        assert len(result) == 15  # Should get last 15 candles
        assert result.index[0] == filter_start
        
        # Read with end_time filter
        filter_end = start_time + timedelta(minutes=50)  # First 10 candles
        result = self.storage.read_candles(symbol, tf, end_time=filter_end)
        
        assert len(result) == 10
        assert result.index[-1] <= filter_end
        
        # Read with both filters
        result = self.storage.read_candles(
            symbol, tf, 
            start_time=filter_start, 
            end_time=filter_end
        )
        
        assert len(result) == 5  # Candles between 25min and 50min marks
    
    def test_get_last_timestamp(self):
        """Test getting the last timestamp for gap detection."""
        symbol = "AAPL"
        tf = "5m"
        
        # Initially no data
        last_ts = self.storage.get_last_timestamp(symbol, tf)
        assert last_ts is None
        
        # Add some data
        start_time = datetime(2022, 1, 1, tzinfo=timezone.utc)
        df = self.create_sample_candles(start_time, 10)
        self.storage.write_candles(symbol, tf, df)
        
        # Should get the last timestamp
        last_ts = self.storage.get_last_timestamp(symbol, tf)
        expected_last = start_time + timedelta(minutes=45)  # 9 * 5 minutes after start
        
        assert last_ts == expected_last
    
    @pytest.mark.asyncio
    async def test_gap_detection_and_backfill(self):
        """Test that gaps are detected and backfilled correctly."""
        
        # Mock the HTTP client and API responses
        with patch('httpx.AsyncClient') as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            # Mock API response for gap backfill
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                's': 'ok',
                't': [1640995200, 1640995260, 1640995320],  # 3 timestamps (5min apart)
                'o': [100.0, 100.1, 100.2],
                'h': [100.5, 100.6, 100.7],
                'l': [99.5, 99.6, 99.7],
                'c': [100.2, 100.3, 100.4],
                'v': [1000, 1100, 1200]
            }
            mock_client.get.return_value = mock_response
            
            # Create worker instance
            worker = FinnhubWorker()
            worker.api_key = "test_key"
            
            # Set up initial data with a gap
            symbol = "AAPL"
            start_time = datetime(2022, 1, 1, tzinfo=timezone.utc)
            
            # Initial data: first 5 candles
            df_initial = self.create_sample_candles(start_time, 5)
            self.storage.write_candles(symbol, "5m", df_initial)
            
            # Simulate gap: backfill should start from last timestamp + 1 interval
            end_time = start_time + timedelta(hours=1)  # 1 hour later
            
            # Call the backfill method
            await worker._backfill_symbol(mock_client, symbol, start_time, end_time)
            
            # Verify HTTP call was made with correct parameters
            mock_client.get.assert_called_once()
            call_args = mock_client.get.call_args
            
            assert 'stock/candle' in call_args[0][0]
            params = call_args[1]['params']
            assert params['symbol'] == symbol
            assert params['resolution'] == '1'  # 1-minute resolution
            assert params['token'] == 'test_key'
    
    def test_empty_data_handling(self):
        """Test handling of empty datasets."""
        symbol = "AAPL"
        tf = "5m"
        
        # Try to read from non-existent file
        result = self.storage.read_candles(symbol, tf)
        assert len(result) == 0
        assert list(result.columns) == ['o', 'h', 'l', 'c', 'v']
        
        # Write empty DataFrame
        empty_df = pd.DataFrame(columns=['ts', 'o', 'h', 'l', 'c', 'v'])
        self.storage.write_candles(symbol, tf, empty_df)
        
        # Should still return empty DataFrame
        result = self.storage.read_candles(symbol, tf)
        assert len(result) == 0
    
    def test_concurrent_writes(self):
        """Test that concurrent writes don't corrupt data."""
        symbol = "AAPL"
        tf = "5m"
        
        # Simulate multiple writers (this is a simplified test)
        start_time = datetime(2022, 1, 1, tzinfo=timezone.utc)
        
        # Writer 1: candles 0-4
        df1 = self.create_sample_candles(start_time, 5)
        self.storage.write_candles(symbol, tf, df1)
        
        # Writer 2: candles 3-7 (overlaps with writer 1)
        overlap_start = start_time + timedelta(minutes=15)  # 3rd candle
        df2 = self.create_sample_candles(overlap_start, 5)
        self.storage.write_candles(symbol, tf, df2)
        
        # Read final result
        result = self.storage.read_candles(symbol, tf)
        
        # Should have 8 unique timestamps (0-7)
        assert len(result) == 8
        assert result.index.is_unique
        assert result.index.is_monotonic_increasing
    
    def test_data_integrity_after_error(self):
        """Test that data remains intact if write operation fails partially."""
        symbol = "AAPL"
        tf = "5m"
        
        # Write initial good data
        start_time = datetime(2022, 1, 1, tzinfo=timezone.utc)
        df_good = self.create_sample_candles(start_time, 5)
        self.storage.write_candles(symbol, tf, df_good)
        
        # Verify initial data
        initial = self.storage.read_candles(symbol, tf)
        assert len(initial) == 5
        
        # Try to write bad data (this should be handled gracefully)
        try:
            df_bad = pd.DataFrame({
                'ts': [start_time + timedelta(minutes=25)],
                'o': ['invalid'],  # String instead of float
                'h': [100.5],
                'l': [99.5],
                'c': [100.0],
                'v': [1000]
            })
            self.storage.write_candles(symbol, tf, df_bad)
        except Exception:
            pass  # Expected to fail
        
        # Original data should still be intact
        result = self.storage.read_candles(symbol, tf)
        assert len(result) == 5  # Should still have original 5 candles
        pd.testing.assert_frame_equal(result, initial)