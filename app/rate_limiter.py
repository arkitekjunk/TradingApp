"""
Rate limiting and quota tracking for Finnhub API calls.
Ensures we stay within 500 REST calls/day and 60 calls/minute limits.
"""
import asyncio
import time
import random
from datetime import datetime, timezone, timedelta
from typing import Dict, Any
from dataclasses import dataclass
from loguru import logger

from app.data_access import db


@dataclass
class RateLimitStats:
    """Rate limiting statistics."""
    calls_today: int
    calls_this_minute: int
    budget_remaining_today: int
    last_call_time: float
    daily_reset_time: datetime


class RateLimiter:
    """
    Rate limiter that enforces:
    - 500 API calls per day (resets at UTC midnight)
    - 60 API calls per minute
    """
    
    def __init__(self, daily_limit: int = 500, minute_limit: int = 60):
        self.daily_limit = daily_limit
        self.minute_limit = minute_limit
        self.calls_this_minute = 0
        self.minute_window_start = time.time()
        
        # Load today's call count from persistent storage
        self._load_daily_count()
        
    def _load_daily_count(self):
        """Load today's call count from database."""
        today_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        stored_date = db.get_setting('rate_limiter_date', '')
        stored_count = db.get_setting('rate_limiter_count', '0')
        
        if stored_date == today_str:
            self.calls_today = int(stored_count)
        else:
            # New day, reset counter
            self.calls_today = 0
            db.set_setting('rate_limiter_date', today_str)
            db.set_setting('rate_limiter_count', '0')
            
    def _save_daily_count(self):
        """Save today's call count to database."""
        today_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        db.set_setting('rate_limiter_date', today_str)
        db.set_setting('rate_limiter_count', str(self.calls_today))
        
    def _reset_minute_window_if_needed(self):
        """Reset minute window if 60 seconds have passed."""
        now = time.time()
        if now - self.minute_window_start >= 60:
            self.calls_this_minute = 0
            self.minute_window_start = now
            
    def can_make_call(self) -> bool:
        """Check if we can make an API call without exceeding limits."""
        self._reset_minute_window_if_needed()
        
        # Check daily limit
        if self.calls_today >= self.daily_limit:
            return False
            
        # Check minute limit
        if self.calls_this_minute >= self.minute_limit:
            return False
            
        return True
        
    def get_delay_until_next_call(self) -> float:
        """Get seconds to wait before next call is allowed."""
        self._reset_minute_window_if_needed()
        
        # If we can make a call now, return 0
        if self.can_make_call():
            return 0
            
        # If we've hit daily limit, wait until tomorrow
        if self.calls_today >= self.daily_limit:
            tomorrow = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            ) + timedelta(days=1)
            return (tomorrow - datetime.now(timezone.utc)).total_seconds()
            
        # If we've hit minute limit, wait until next minute window
        if self.calls_this_minute >= self.minute_limit:
            return 60 - (time.time() - self.minute_window_start)
            
        return 0
        
    def record_call(self):
        """Record that an API call was made."""
        self._reset_minute_window_if_needed()
        self.calls_today += 1
        self.calls_this_minute += 1
        self._save_daily_count()
        
    async def wait_for_availability(self):
        """Wait until we can make an API call."""
        delay = self.get_delay_until_next_call()
        if delay > 0:
            logger.info(f"Rate limit hit, waiting {delay:.1f} seconds")
            await asyncio.sleep(delay)
            
    async def acquire_with_backoff(self, max_retries: int = 3):
        """
        Acquire permission to make API call with exponential backoff on 429.
        Should be called before making any Finnhub API request.
        """
        for attempt in range(max_retries):
            await self.wait_for_availability()
            
            if self.can_make_call():
                self.record_call()
                return
                
            # Exponential backoff with jitter for fairness
            backoff_delay = (2 ** attempt) + random.uniform(0, 1)
            logger.warning(f"Rate limit acquisition failed, attempt {attempt + 1}, "
                         f"waiting {backoff_delay:.1f} seconds")
            await asyncio.sleep(backoff_delay)
            
        raise Exception("Failed to acquire rate limit after maximum retries")
        
    def get_stats(self) -> RateLimitStats:
        """Get current rate limiting statistics."""
        self._reset_minute_window_if_needed()
        
        # Calculate next daily reset time
        tomorrow = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ) + timedelta(days=1)
        
        return RateLimitStats(
            calls_today=self.calls_today,
            calls_this_minute=self.calls_this_minute,
            budget_remaining_today=max(0, self.daily_limit - self.calls_today),
            last_call_time=time.time(),
            daily_reset_time=tomorrow
        )


# Global rate limiter instance
rate_limiter = RateLimiter()