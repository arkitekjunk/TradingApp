"""
Integration tests for end-to-end trading app workflows.
Tests multiple components working together as a system.
"""
import pytest
import asyncio
import tempfile
import shutil
import pandas as pd
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from app.worker import FinnhubWorker
from app.data_access import DatabaseManager, CandleStorage
from app.rate_limiter import RateLimiter
from app.market_calendar import USMarketCalendar
from app.reconciliation import ReconciliationService


@pytest.fixture
def temp_data_dir():
    """Create temporary directory for test data."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def test_db():
    """Create test database instance."""
    db = DatabaseManager("sqlite:///:memory:")
    return db


@pytest.fixture
def test_storage(temp_data_dir):
    """Create test storage instance."""
    storage = CandleStorage(temp_data_dir)
    return storage


@pytest.fixture
def test_rate_limiter():
    """Create test rate limiter with small limits."""
    return RateLimiter(daily_limit=10, minute_limit=3)


@pytest.fixture
def mock_api_responses():
    """Mock Finnhub API responses."""
    return {
        'universe': ['AAPL', 'MSFT', 'GOOGL'],
        'candle_data': {
            's': 'ok',
            't': [1640995200, 1640995500, 1640995800],  # Unix timestamps
            'o': [150.0, 150.5, 151.0],
            'h': [150.5, 151.0, 151.5],
            'l': [149.5, 150.0, 150.5],
            'c': [150.25, 150.75, 151.25],
            'v': [10000, 12000, 11000]
        }
    }


class TestEndToEndWorkflows:
    """Integration tests for complete system workflows."""
    
    @pytest.mark.asyncio
    async def test_full_backfill_to_storage_flow(
        self, test_db, test_storage, test_rate_limiter, mock_api_responses
    ):
        """Test complete backfill workflow: API -> Storage -> Indicators."""
        
        with patch('httpx.AsyncClient') as mock_client:
            # Mock API responses
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_api_responses['candle_data']
            mock_response.raise_for_status = MagicMock()
            
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
            
            # Create worker instance
            worker = FinnhubWorker()
            worker.api_key = "test_key"
            worker.universe_symbols = ["AAPL"]
            
            # Mock storage and db for this test
            with patch('app.worker.storage', test_storage), \
                 patch('app.worker.db', test_db), \
                 patch('app.worker.rate_limiter', test_rate_limiter):
                
                # Run chunked backfill
                include_extended_hours = False
                await worker._backfill_symbol_chunked(
                    mock_client.return_value.__aenter__.return_value,
                    "AAPL", 
                    1,  # 1 day lookback
                    include_extended_hours
                )
                
                # Verify data was stored
                stored_data = test_storage.read_candles("AAPL", "5m")
                assert not stored_data.empty
                assert len(stored_data) == 3  # Should have 3 candles
                
                # Verify rate limiter was used
                assert test_rate_limiter.calls_today > 0
                
                # Verify columns are correct
                expected_columns = ['o', 'h', 'l', 'c', 'v']
                for col in expected_columns:
                    assert col in stored_data.columns
    
    @pytest.mark.asyncio
    async def test_websocket_gap_fill_integration(
        self, test_db, test_storage, mock_api_responses
    ):
        """Test WebSocket gap filling with real storage integration."""
        
        # Pre-populate storage with some data
        initial_data = pd.DataFrame({
            'ts': pd.to_datetime(['2024-01-01 10:00:00'], utc=True),
            'o': [100.0], 'h': [101.0], 'l': [99.0], 'c': [100.5], 'v': [1000]
        })
        test_storage.write_candles("AAPL", "5m", initial_data)
        
        with patch('httpx.AsyncClient') as mock_client:
            # Mock gap-fill API response
            gap_data = {
                's': 'ok',
                't': [1640995500, 1640995800],  # 2 more candles
                'o': [100.5, 101.0],
                'h': [101.5, 102.0],
                'l': [100.0, 100.5],
                'c': [101.0, 101.5],
                'v': [1500, 1200]
            }
            
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json.return_value = gap_data
            mock_response.raise_for_status = MagicMock()
            
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
            
            # Create worker and simulate gap fill
            worker = FinnhubWorker()
            worker.api_key = "test_key"
            worker.universe_symbols = ["AAPL"]
            worker.stats['last_ws_tick_ts'] = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
            
            with patch('app.worker.storage', test_storage), \
                 patch('app.worker.db', test_db):
                
                # Trigger gap fill
                await worker._fill_websocket_gap()
                
                # Verify gap was filled
                all_data = test_storage.read_candles("AAPL", "5m")
                assert len(all_data) == 3  # Original 1 + 2 gap-filled
                
                # Verify no duplicates
                assert len(all_data.index.unique()) == len(all_data)
    
    @pytest.mark.asyncio
    async def test_quota_exhaustion_and_queue_management(
        self, test_db, test_storage
    ):
        """Test quota management and backfill queue integration."""
        
        # Create rate limiter that's almost at daily limit
        rate_limiter = RateLimiter(daily_limit=5, minute_limit=10)
        rate_limiter.calls_today = 4  # Almost at limit
        
        worker = FinnhubWorker()
        worker.api_key = "test_key" 
        worker.universe_symbols = ["AAPL", "MSFT", "GOOGL", "TSLA", "AMZN"]  # 5 symbols
        
        with patch('app.worker.rate_limiter', rate_limiter), \
             patch('app.worker.db', test_db), \
             patch('app.worker.storage', test_storage):
            
            # Should detect insufficient quota and schedule symbols
            await worker._schedule_backfill_queue()
            
            # Verify queue was populated
            queue_size = test_db.get_backfill_queue_size()
            assert queue_size > 0
            
            # Verify we can get next symbols to process
            next_symbols = test_db.get_next_backfill_symbols(limit=2)
            assert len(next_symbols) <= 2
    
    @pytest.mark.asyncio
    async def test_eod_reconciliation_workflow(
        self, test_db, test_storage, mock_api_responses
    ):
        """Test end-of-day reconciliation with storage integration."""
        
        # Pre-populate storage with 'live' data
        live_data = pd.DataFrame({
            'ts': pd.to_datetime(['2024-01-01 10:00:00', '2024-01-01 10:05:00'], utc=True),
            'o': [100.0, 100.5], 'h': [101.0, 101.5], 'l': [99.0, 99.5], 
            'c': [100.5, 101.0], 'v': [1000, 1200]
        })
        test_storage.write_candles("AAPL", "5m", live_data)
        
        # Mock 'official' data with slight differences (adjustments)
        official_data = {
            's': 'ok',
            't': [1640995200, 1640995500],
            'o': [100.0, 100.6],  # Slightly different due to adjustment
            'h': [101.0, 101.6],
            'l': [99.0, 99.6],
            'c': [100.5, 101.1],  # Slightly different
            'v': [1000, 1200]
        }
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json.return_value = official_data
            mock_response.raise_for_status = MagicMock()
            
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
            
            # Create reconciliation service
            reconciliation = ReconciliationService()
            reconciliation.set_api_key("test_key")
            
            with patch('app.reconciliation.storage', test_storage), \
                 patch('app.reconciliation.db', test_db), \
                 patch('app.reconciliation.market_calendar') as mock_calendar:
                
                # Mock previous session detection
                mock_calendar.get_previous_session_bounds.return_value = (
                    '2024-01-01',
                    datetime(2024, 1, 1, 14, 30, tzinfo=timezone.utc),  # Session start
                    datetime(2024, 1, 1, 21, 0, tzinfo=timezone.utc)    # Session end
                )
                
                # Run reconciliation
                results = await reconciliation.reconcile_previous_session(["AAPL"])
                
                # Verify reconciliation occurred
                assert "AAPL" in results
                assert results["AAPL"] > 0  # Some bars were updated
                
                # Verify reconciliation was recorded
                last_reconcile = test_db.get_last_reconcile_date()
                assert last_reconcile == '2024-01-01'
    
    @pytest.mark.asyncio 
    async def test_session_aware_vwap_integration(
        self, test_storage
    ):
        """Test session-aware VWAP calculation with market calendar integration."""
        
        from app.indicators import IndicatorCalculator
        
        # Create data spanning across session boundary (9:30 AM ET)
        import pytz
        et_tz = pytz.timezone('America/New_York')
        
        timestamps = [
            et_tz.localize(datetime(2024, 1, 8, 15, 55)).astimezone(timezone.utc),  # Previous session
            et_tz.localize(datetime(2024, 1, 9, 9, 30)).astimezone(timezone.utc),   # New session start
            et_tz.localize(datetime(2024, 1, 9, 9, 35)).astimezone(timezone.utc),   # New session continue
        ]
        
        test_data = pd.DataFrame({
            'o': [100.0, 101.0, 102.0],
            'h': [100.5, 101.5, 102.5],
            'l': [99.5, 100.5, 101.5], 
            'c': [100.0, 101.0, 102.0],
            'v': [1000, 1000, 1000]
        }, index=pd.DatetimeIndex(timestamps, tz='UTC'))
        
        # Mock the database setting
        with patch('app.indicators.db') as mock_db:
            mock_db.get_setting.return_value = 'false'  # Regular hours only
            
            indicator_calc = IndicatorCalculator()
            
            # Calculate session-aware VWAP
            vwap_series = indicator_calc._calculate_session_vwap(test_data)
            
            # Verify VWAP reset at session boundary
            assert len(vwap_series) == 3
            
            # First bar should have its own VWAP
            typical_price_1 = (100.5 + 99.5 + 100.0) / 3
            assert abs(vwap_series.iloc[0] - typical_price_1) < 0.1
            
            # Second bar (new session) should start fresh
            typical_price_2 = (101.5 + 100.5 + 101.0) / 3  
            assert abs(vwap_series.iloc[1] - typical_price_2) < 0.1
            
            # Third bar should accumulate from second bar only
            expected_vwap_3 = (typical_price_2 * 1000 + ((102.5 + 101.5 + 102.0) / 3) * 1000) / 2000
            assert abs(vwap_series.iloc[2] - expected_vwap_3) < 0.1
    
    def test_market_calendar_holiday_integration(self):
        """Test market calendar properly excludes holidays."""
        
        calendar = USMarketCalendar()
        
        # Test known holiday (Christmas 2024)
        christmas_2024 = datetime(2024, 12, 25, 10, 0, tzinfo=timezone.utc)
        assert calendar.is_market_day(christmas_2024) is False
        
        # Test day before holiday (should be trading day)
        christmas_eve_2024 = datetime(2024, 12, 24, 10, 0, tzinfo=timezone.utc)
        assert calendar.is_market_day(christmas_eve_2024) is True
        
        # Test early close day
        assert calendar.is_early_close_day(christmas_eve_2024) is True
        
        # Test next/previous trading day navigation
        next_trading_day = calendar.get_next_trading_day(christmas_2024)
        assert next_trading_day.day == 26  # Day after Christmas
        
        prev_trading_day = calendar.get_previous_trading_day(christmas_2024)
        assert prev_trading_day.day == 24  # Christmas Eve
    
    @pytest.mark.asyncio
    async def test_configuration_validation_integration(self):
        """Test configuration validation across components."""
        
        from app.config import validate_settings, Settings
        
        # Test valid configuration
        valid_settings = Settings(
            finnhub_api_key="valid_key",
            include_extended_hours=False,
            max_lookback_days=30
        )
        
        # Should not raise exception
        validate_settings(valid_settings)
        
        # Test invalid configuration (missing API key)
        with pytest.raises(ValueError, match="FINNHUB_API_KEY is required"):
            invalid_settings = Settings(
                finnhub_api_key="",
                include_extended_hours=False,
                max_lookback_days=30
            )
            validate_settings(invalid_settings)
    
    @pytest.mark.asyncio
    async def test_graceful_shutdown_integration(
        self, test_storage
    ):
        """Test graceful shutdown preserves partial candle data."""
        
        worker = FinnhubWorker()
        
        # Simulate partial candles in aggregator
        worker.aggregator.current_candles["AAPL"] = {
            'timestamp': datetime.now(timezone.utc),
            'bucket_ms': int(datetime.now(timezone.utc).timestamp() * 1000),
            'o': 100.0, 'h': 101.0, 'l': 99.0, 'c': 100.5, 'v': 1000,
            'trade_count': 5
        }
        
        with patch('app.worker.storage', test_storage):
            # Trigger graceful shutdown
            worker._signal_handler(15, None)  # SIGTERM
            
            # Verify partial candle was flushed to storage
            stored_data = test_storage.read_candles("AAPL", "5m")
            assert not stored_data.empty
            assert len(stored_data) == 1
            assert stored_data.iloc[0]['c'] == 100.5  # Close price preserved


class TestSystemPerformance:
    """Integration tests for system performance and reliability."""
    
    @pytest.mark.asyncio
    async def test_large_symbol_universe_performance(
        self, test_db, test_storage
    ):
        """Test system performance with large symbol universe."""
        
        # Create large symbol list
        large_universe = [f"SYM{i:03d}" for i in range(100)]
        
        worker = FinnhubWorker()
        worker.universe_symbols = large_universe
        
        # Test backfill queue scheduling performance
        start_time = datetime.now()
        
        with patch('app.worker.db', test_db):
            await worker._schedule_backfill_queue()
            
        end_time = datetime.now()
        processing_time = (end_time - start_time).total_seconds()
        
        # Should complete queue scheduling in under 1 second
        assert processing_time < 1.0
        
        # Verify queue was populated
        queue_size = test_db.get_backfill_queue_size() 
        assert queue_size > 0
    
    @pytest.mark.asyncio
    async def test_concurrent_storage_operations(
        self, test_storage
    ):
        """Test storage can handle concurrent read/write operations."""
        
        # Simulate concurrent writes to different symbols
        symbols = ["AAPL", "MSFT", "GOOGL", "TSLA"]
        
        async def write_symbol_data(symbol):
            data = pd.DataFrame({
                'ts': pd.to_datetime(['2024-01-01 10:00:00'], utc=True),
                'o': [100.0], 'h': [101.0], 'l': [99.0], 'c': [100.5], 'v': [1000]
            })
            test_storage.write_candles(symbol, "5m", data)
        
        # Run concurrent writes
        await asyncio.gather(*[write_symbol_data(symbol) for symbol in symbols])
        
        # Verify all data was written correctly
        for symbol in symbols:
            stored_data = test_storage.read_candles(symbol, "5m")
            assert not stored_data.empty
            assert len(stored_data) == 1
        
        # Test concurrent reads
        async def read_symbol_data(symbol):
            return test_storage.read_candles(symbol, "5m")
        
        results = await asyncio.gather(*[read_symbol_data(symbol) for symbol in symbols])
        
        # All reads should succeed
        assert len(results) == 4
        for result in results:
            assert not result.empty


if __name__ == "__main__":
    pytest.main([__file__, "-v"])