import pytest
from datetime import datetime, timezone
import pytz

from app.market_calendar import USMarketCalendar


class TestUSMarketCalendar:
    """Test market calendar functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.calendar = USMarketCalendar()
    
    def test_is_market_day(self):
        """Test market day detection."""
        # Monday (weekday 0)
        monday = datetime(2024, 1, 8, 10, 0, tzinfo=timezone.utc)  # Monday
        assert self.calendar.is_market_day(monday) is True
        
        # Saturday (weekday 5)
        saturday = datetime(2024, 1, 6, 10, 0, tzinfo=timezone.utc)  # Saturday
        assert self.calendar.is_market_day(saturday) is False
        
        # Sunday (weekday 6)
        sunday = datetime(2024, 1, 7, 10, 0, tzinfo=timezone.utc)  # Sunday
        assert self.calendar.is_market_day(sunday) is False
    
    def test_is_regular_hours(self):
        """Test regular trading hours detection."""
        et_tz = pytz.timezone('America/New_York')
        
        # 10:00 AM ET on a Monday - should be regular hours
        dt_regular = et_tz.localize(datetime(2024, 1, 8, 10, 0))  # Monday 10 AM ET
        assert self.calendar.is_regular_hours(dt_regular) is True
        
        # 3:30 PM ET on a Monday - should be regular hours
        dt_regular_pm = et_tz.localize(datetime(2024, 1, 8, 15, 30))  # Monday 3:30 PM ET
        assert self.calendar.is_regular_hours(dt_regular_pm) is True
        
        # 5:00 PM ET on a Monday - should NOT be regular hours
        dt_after = et_tz.localize(datetime(2024, 1, 8, 17, 0))  # Monday 5 PM ET
        assert self.calendar.is_regular_hours(dt_after) is False
        
        # 8:00 AM ET on a Monday - should NOT be regular hours
        dt_before = et_tz.localize(datetime(2024, 1, 8, 8, 0))  # Monday 8 AM ET
        assert self.calendar.is_regular_hours(dt_before) is False
        
        # Saturday - should NOT be regular hours regardless of time
        dt_weekend = et_tz.localize(datetime(2024, 1, 6, 10, 0))  # Saturday 10 AM ET
        assert self.calendar.is_regular_hours(dt_weekend) is False
    
    def test_is_extended_hours(self):
        """Test extended hours detection."""
        et_tz = pytz.timezone('America/New_York')
        
        # 7:00 AM ET on a Monday - should be extended hours (pre-market)
        dt_premarket = et_tz.localize(datetime(2024, 1, 8, 7, 0))  # Monday 7 AM ET
        assert self.calendar.is_extended_hours(dt_premarket) is True
        
        # 5:00 PM ET on a Monday - should be extended hours (post-market)
        dt_postmarket = et_tz.localize(datetime(2024, 1, 8, 17, 0))  # Monday 5 PM ET
        assert self.calendar.is_extended_hours(dt_postmarket) is True
        
        # 10:00 AM ET on a Monday - should NOT be extended hours (regular)
        dt_regular = et_tz.localize(datetime(2024, 1, 8, 10, 0))  # Monday 10 AM ET
        assert self.calendar.is_extended_hours(dt_regular) is False
        
        # 9:00 PM ET on a Monday - should NOT be extended hours (closed)
        dt_closed = et_tz.localize(datetime(2024, 1, 8, 21, 0))  # Monday 9 PM ET
        assert self.calendar.is_extended_hours(dt_closed) is False
    
    def test_should_include_in_session(self):
        """Test session inclusion logic."""
        et_tz = pytz.timezone('America/New_York')
        
        # Regular hours
        dt_regular = et_tz.localize(datetime(2024, 1, 8, 10, 0))  # Monday 10 AM ET
        
        # With extended hours enabled
        assert self.calendar.should_include_in_session(dt_regular, True) is True
        
        # With extended hours disabled
        assert self.calendar.should_include_in_session(dt_regular, False) is True
        
        # Extended hours
        dt_extended = et_tz.localize(datetime(2024, 1, 8, 7, 0))  # Monday 7 AM ET
        
        # With extended hours enabled
        assert self.calendar.should_include_in_session(dt_extended, True) is True
        
        # With extended hours disabled
        assert self.calendar.should_include_in_session(dt_extended, False) is False
    
    def test_get_session_open(self):
        """Test session open time calculation."""
        et_tz = pytz.timezone('America/New_York')
        
        # Afternoon on a trading day
        dt_afternoon = et_tz.localize(datetime(2024, 1, 8, 14, 30))  # Monday 2:30 PM ET
        session_open = self.calendar.get_session_open(dt_afternoon)
        
        # Should be 9:30 AM ET same day, converted to UTC
        expected_et = et_tz.localize(datetime(2024, 1, 8, 9, 30))
        expected_utc = expected_et.astimezone(timezone.utc)
        
        assert session_open == expected_utc
    
    def test_is_new_session(self):
        """Test session boundary detection."""
        et_tz = pytz.timezone('America/New_York')
        
        # Same session
        dt1 = et_tz.localize(datetime(2024, 1, 8, 10, 0))  # Monday 10 AM ET
        dt2 = et_tz.localize(datetime(2024, 1, 8, 15, 0))  # Monday 3 PM ET
        assert self.calendar.is_new_session(dt2, dt1) is False
        
        # Different sessions (next day)
        dt3 = et_tz.localize(datetime(2024, 1, 9, 10, 0))  # Tuesday 10 AM ET
        assert self.calendar.is_new_session(dt3, dt1) is True
        
        # First call (no last_dt)
        assert self.calendar.is_new_session(dt1, None) is True
    
    def test_align_to_5min_boundary(self):
        """Test 5-minute boundary alignment."""
        et_tz = pytz.timezone('America/New_York')
        
        # 9:32:15 ET should align to 9:30:00 ET
        dt_unaligned = et_tz.localize(datetime(2024, 1, 8, 9, 32, 15))
        aligned = self.calendar.align_to_5min_boundary(dt_unaligned)
        expected = et_tz.localize(datetime(2024, 1, 8, 9, 30, 0))
        
        assert aligned == expected.astimezone(timezone.utc)
        
        # 9:37:45 ET should align to 9:35:00 ET
        dt_unaligned2 = et_tz.localize(datetime(2024, 1, 8, 9, 37, 45))
        aligned2 = self.calendar.align_to_5min_boundary(dt_unaligned2)
        expected2 = et_tz.localize(datetime(2024, 1, 8, 9, 35, 0))
        
        assert aligned2 == expected2.astimezone(timezone.utc)
    
    def test_get_trading_session_bounds(self):
        """Test trading session bounds calculation."""
        et_tz = pytz.timezone('America/New_York')
        dt = et_tz.localize(datetime(2024, 1, 8, 12, 0))  # Monday noon ET
        
        # Regular hours
        start, end = self.calendar.get_trading_session_bounds(dt, include_extended_hours=False)
        expected_start = et_tz.localize(datetime(2024, 1, 8, 9, 30))
        expected_end = et_tz.localize(datetime(2024, 1, 8, 16, 0))
        
        assert start == expected_start.astimezone(timezone.utc)
        assert end == expected_end.astimezone(timezone.utc)
        
        # Extended hours
        start_ext, end_ext = self.calendar.get_trading_session_bounds(dt, include_extended_hours=True)
        expected_start_ext = et_tz.localize(datetime(2024, 1, 8, 4, 0))
        expected_end_ext = et_tz.localize(datetime(2024, 1, 8, 20, 0))
        
        assert start_ext == expected_start_ext.astimezone(timezone.utc)
        assert end_ext == expected_end_ext.astimezone(timezone.utc)