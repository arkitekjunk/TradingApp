import pytest
from datetime import datetime, timezone
from app.worker import CandleAggregator

class TestCandleAggregator:
    def setup_method(self):
        self.aggregator = CandleAggregator(timeframe_minutes=5)
        self.completed_candles = []
        
        def on_candle_complete(symbol, candle):
            self.completed_candles.append((symbol, candle))
        
        self.aggregator.add_candle_callback(on_candle_complete)
    
    def test_single_trade_in_bucket(self):
        """Test that a single trade creates the correct candle structure."""
        symbol = "AAPL"
        price = 150.50
        volume = 100
        timestamp_ms = 1640995200000  # 2022-01-01 00:00:00 UTC
        
        self.aggregator.process_trade(symbol, price, volume, timestamp_ms)
        
        # Should have current candle but no completed candles yet
        assert symbol in self.aggregator.current_candles
        assert len(self.completed_candles) == 0
        
        candle = self.aggregator.current_candles[symbol]
        assert candle['o'] == price
        assert candle['h'] == price
        assert candle['l'] == price
        assert candle['c'] == price
        assert candle['v'] == volume
    
    def test_multiple_trades_same_bucket(self):
        """Test that multiple trades in the same 5-minute bucket aggregate correctly."""
        symbol = "AAPL"
        timestamp_ms = 1640995200000  # 2022-01-01 00:00:00 UTC
        
        # Trade 1
        self.aggregator.process_trade(symbol, 150.00, 100, timestamp_ms)
        # Trade 2 - higher
        self.aggregator.process_trade(symbol, 151.00, 50, timestamp_ms + 60000)  # 1 minute later
        # Trade 3 - lower
        self.aggregator.process_trade(symbol, 149.50, 75, timestamp_ms + 120000)  # 2 minutes later
        # Trade 4 - final
        self.aggregator.process_trade(symbol, 150.75, 25, timestamp_ms + 180000)  # 3 minutes later
        
        candle = self.aggregator.current_candles[symbol]
        assert candle['o'] == 150.00  # First trade price
        assert candle['h'] == 151.00  # Highest price
        assert candle['l'] == 149.50  # Lowest price
        assert candle['c'] == 150.75  # Last trade price
        assert candle['v'] == 250     # Sum of volumes
        
        # Still no completed candles (all in same bucket)
        assert len(self.completed_candles) == 0
    
    def test_trades_different_buckets(self):
        """Test that trades in different 5-minute buckets complete candles."""
        symbol = "AAPL"
        
        # First bucket: 2022-01-01 00:00:00 UTC
        timestamp1 = 1640995200000
        self.aggregator.process_trade(symbol, 150.00, 100, timestamp1)
        
        # Second bucket: 2022-01-01 00:05:00 UTC (5 minutes later)
        timestamp2 = 1640995500000
        self.aggregator.process_trade(symbol, 151.00, 50, timestamp2)
        
        # Should have completed the first candle
        assert len(self.completed_candles) == 1
        completed_symbol, completed_candle = self.completed_candles[0]
        
        assert completed_symbol == symbol
        assert completed_candle['o'] == 150.00
        assert completed_candle['h'] == 150.00
        assert completed_candle['l'] == 150.00
        assert completed_candle['c'] == 150.00
        assert completed_candle['v'] == 100
        
        # Current candle should be the new one
        current_candle = self.aggregator.current_candles[symbol]
        assert current_candle['o'] == 151.00
        assert current_candle['v'] == 50
    
    def test_multiple_symbols(self):
        """Test that multiple symbols are handled independently."""
        timestamp_ms = 1640995200000
        
        # Trade for AAPL
        self.aggregator.process_trade("AAPL", 150.00, 100, timestamp_ms)
        # Trade for MSFT
        self.aggregator.process_trade("MSFT", 300.00, 50, timestamp_ms + 60000)
        
        # Both symbols should have current candles
        assert "AAPL" in self.aggregator.current_candles
        assert "MSFT" in self.aggregator.current_candles
        
        aapl_candle = self.aggregator.current_candles["AAPL"]
        msft_candle = self.aggregator.current_candles["MSFT"]
        
        assert aapl_candle['c'] == 150.00
        assert msft_candle['c'] == 300.00
        assert aapl_candle['v'] == 100
        assert msft_candle['v'] == 50
    
    def test_bucket_calculation(self):
        """Test that trades are correctly assigned to 5-minute buckets."""
        symbol = "AAPL"
        
        # Test various timestamps within the same 5-minute bucket
        base_time = 1640995200000  # 2022-01-01 00:00:00 UTC
        
        # These should all be in the same bucket (00:00-00:05)
        timestamps_same_bucket = [
            base_time,          # 00:00:00
            base_time + 60000,  # 00:01:00
            base_time + 240000, # 00:04:00
            base_time + 299000, # 00:04:59
        ]
        
        for i, ts in enumerate(timestamps_same_bucket):
            self.aggregator.process_trade(symbol, 150.00 + i, 100, ts)
            # Should still be the same candle
            assert len(self.completed_candles) == 0
        
        # This should trigger a new bucket (00:05:00)
        self.aggregator.process_trade(symbol, 155.00, 100, base_time + 300000)
        
        # Now we should have completed one candle
        assert len(self.completed_candles) == 1
        
        completed_candle = self.completed_candles[0][1]
        assert completed_candle['o'] == 150.00  # First trade
        assert completed_candle['c'] == 153.00  # Last trade in bucket
        assert completed_candle['v'] == 400     # 4 trades * 100 volume each
    
    def test_force_complete_candles(self):
        """Test that force completing candles works correctly."""
        symbol = "AAPL"
        timestamp_ms = 1640995200000
        
        # Add some trades
        self.aggregator.process_trade(symbol, 150.00, 100, timestamp_ms)
        self.aggregator.process_trade(symbol, 151.00, 50, timestamp_ms + 60000)
        
        # Should have no completed candles yet
        assert len(self.completed_candles) == 0
        
        # Force complete current candles
        self.aggregator.force_complete_current_candles()
        
        # Now should have one completed candle
        assert len(self.completed_candles) == 1
        completed_candle = self.completed_candles[0][1]
        assert completed_candle['o'] == 150.00
        assert completed_candle['c'] == 151.00
        assert completed_candle['v'] == 150
        
        # Current candles should be cleared
        assert len(self.aggregator.current_candles) == 0