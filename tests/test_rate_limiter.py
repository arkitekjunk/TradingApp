import pytest
import asyncio
import time
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from app.rate_limiter import RateLimiter


class TestRateLimiter:
    """Test rate limiting functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Create rate limiter with small limits for testing
        self.rate_limiter = RateLimiter(daily_limit=10, minute_limit=3)
        self.rate_limiter.calls_today = 0
        self.rate_limiter.calls_this_minute = 0
        self.rate_limiter.minute_window_start = time.time()
    
    def test_can_make_call_within_limits(self):
        """Test that calls are allowed within limits."""
        assert self.rate_limiter.can_make_call() is True
        
        # Make some calls
        for i in range(3):
            self.rate_limiter.record_call()
            
        # Should still be able to make calls (daily limit not hit)
        assert self.rate_limiter.can_make_call() is False  # Minute limit hit
        assert self.rate_limiter.calls_today == 3
        assert self.rate_limiter.calls_this_minute == 3
    
    def test_daily_limit_enforcement(self):
        """Test that daily limit is enforced."""
        # Hit daily limit
        self.rate_limiter.calls_today = 10
        assert self.rate_limiter.can_make_call() is False
    
    def test_minute_limit_reset(self):
        """Test that minute window resets properly."""
        # Hit minute limit
        self.rate_limiter.calls_this_minute = 3
        assert self.rate_limiter.can_make_call() is False
        
        # Simulate time passing
        self.rate_limiter.minute_window_start = time.time() - 61
        self.rate_limiter._reset_minute_window_if_needed()
        
        assert self.rate_limiter.calls_this_minute == 0
        assert self.rate_limiter.can_make_call() is True
    
    @pytest.mark.asyncio
    async def test_acquire_with_backoff(self):
        """Test that acquire_with_backoff works correctly."""
        # Should acquire normally when under limits
        await self.rate_limiter.acquire_with_backoff()
        assert self.rate_limiter.calls_today == 1
        assert self.rate_limiter.calls_this_minute == 1
    
    def test_get_delay_until_next_call(self):
        """Test delay calculation."""
        # No delay when under limits
        assert self.rate_limiter.get_delay_until_next_call() == 0
        
        # Hit minute limit - should have delay
        self.rate_limiter.calls_this_minute = 3
        delay = self.rate_limiter.get_delay_until_next_call()
        assert 0 < delay <= 60
        
        # Hit daily limit - should have long delay
        self.rate_limiter.calls_today = 10
        delay = self.rate_limiter.get_delay_until_next_call()
        assert delay > 3600  # More than an hour
    
    def test_get_stats(self):
        """Test statistics retrieval."""
        self.rate_limiter.calls_today = 5
        self.rate_limiter.calls_this_minute = 2
        
        stats = self.rate_limiter.get_stats()
        
        assert stats.calls_today == 5
        assert stats.calls_this_minute == 2
        assert stats.budget_remaining_today == 5
        assert stats.daily_reset_time is not None