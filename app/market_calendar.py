"""
US market calendar utilities for session-aware processing.
Handles regular trading hours, extended hours, and VWAP session resets.
"""
from datetime import datetime, timezone, time as dt_time, timedelta
from typing import Tuple, Optional
import pytz


class USMarketCalendar:
    """
    Comprehensive US market calendar with NYSE/NASDAQ holidays.
    Uses America/New_York timezone for all calculations.
    """
    
    def __init__(self):
        self.eastern_tz = pytz.timezone('America/New_York')
        
        # NYSE/NASDAQ Market Holidays (2024-2026)
        # Updated annually from: https://www.nyse.com/markets/hours-calendars
        self.market_holidays = {
            # 2024 Holidays
            '2024-01-01': "New Year's Day",
            '2024-01-15': "Martin Luther King Jr. Day", 
            '2024-02-19': "Presidents' Day",
            '2024-03-29': "Good Friday",
            '2024-05-27': "Memorial Day",
            '2024-06-19': "Juneteenth",
            '2024-07-04': "Independence Day",
            '2024-09-02': "Labor Day",
            '2024-11-28': "Thanksgiving Day",
            '2024-12-25': "Christmas Day",
            
            # 2025 Holidays
            '2025-01-01': "New Year's Day",
            '2025-01-20': "Martin Luther King Jr. Day",
            '2025-02-17': "Presidents' Day", 
            '2025-04-18': "Good Friday",
            '2025-05-26': "Memorial Day",
            '2025-06-19': "Juneteenth",
            '2025-07-04': "Independence Day",
            '2025-09-01': "Labor Day",
            '2025-11-27': "Thanksgiving Day",
            '2025-12-25': "Christmas Day",
            
            # 2026 Holidays
            '2026-01-01': "New Year's Day",
            '2026-01-19': "Martin Luther King Jr. Day",
            '2026-02-16': "Presidents' Day",
            '2026-04-03': "Good Friday",
            '2026-05-25': "Memorial Day", 
            '2026-06-19': "Juneteenth",
            '2026-07-04': "Independence Day (Observed)",  # Falls on Saturday
            '2026-09-07': "Labor Day",
            '2026-11-26': "Thanksgiving Day",
            '2026-12-25': "Christmas Day"
        }
        
        # Regular trading session times (ET)
        self.regular_open = dt_time(9, 30)  # 9:30 AM ET
        self.regular_close = dt_time(16, 0)  # 4:00 PM ET
        
        # Extended hours (pre/post market)
        self.premarket_open = dt_time(4, 0)   # 4:00 AM ET
        self.postmarket_close = dt_time(20, 0)  # 8:00 PM ET
        
    def is_market_day(self, dt: datetime) -> bool:
        """
        Check if given date is a trading day (Mon-Fri, excluding holidays).
        Accounts for all NYSE/NASDAQ market holidays.
        """
        # Convert to ET for consistency
        et_dt = dt.astimezone(self.eastern_tz)
        
        # Check if it's a weekend
        if et_dt.weekday() >= 5:  # Saturday = 5, Sunday = 6
            return False
            
        # Check if it's a market holiday
        date_str = et_dt.strftime('%Y-%m-%d')
        if date_str in self.market_holidays:
            return False
            
        return True
        
    def is_regular_hours(self, dt: datetime) -> bool:
        """Check if given datetime falls within regular trading hours."""
        if not self.is_market_day(dt):
            return False
            
        et_dt = dt.astimezone(self.eastern_tz)
        current_time = et_dt.time()
        
        return self.regular_open <= current_time < self.regular_close
        
    def is_extended_hours(self, dt: datetime) -> bool:
        """Check if given datetime falls within extended trading hours."""
        if not self.is_market_day(dt):
            return False
            
        et_dt = dt.astimezone(self.eastern_tz)
        current_time = et_dt.time()
        
        # Pre-market: 4:00 AM - 9:30 AM ET
        # Post-market: 4:00 PM - 8:00 PM ET
        return ((self.premarket_open <= current_time < self.regular_open) or
                (self.regular_close <= current_time < self.postmarket_close))
        
    def should_include_in_session(self, dt: datetime, include_extended_hours: bool) -> bool:
        """
        Determine if a timestamp should be included in session calculations
        based on the include_extended_hours setting.
        """
        if include_extended_hours:
            return self.is_regular_hours(dt) or self.is_extended_hours(dt)
        else:
            return self.is_regular_hours(dt)
            
    def get_session_open(self, dt: datetime) -> datetime:
        """
        Get the session open time for a given datetime.
        Returns 9:30 AM ET for the trading day.
        """
        et_dt = dt.astimezone(self.eastern_tz)
        session_date = et_dt.date()
        
        # Create session open datetime (9:30 AM ET)
        session_open_et = self.eastern_tz.localize(
            datetime.combine(session_date, self.regular_open)
        )
        
        # Convert back to UTC
        return session_open_et.astimezone(timezone.utc)
        
    def is_new_session(self, current_dt: datetime, last_dt: Optional[datetime] = None) -> bool:
        """
        Check if we've crossed into a new trading session (past 9:30 AM ET).
        Used for VWAP resets.
        """
        if last_dt is None:
            return True
            
        current_session_open = self.get_session_open(current_dt)
        last_session_open = self.get_session_open(last_dt)
        
        return current_session_open != last_session_open
        
    def align_to_5min_boundary(self, dt: datetime) -> datetime:
        """
        Align timestamp to exact 5-minute boundaries in ET timezone.
        E.g., 09:32:15 becomes 09:30:00, 09:37:45 becomes 09:35:00
        """
        et_dt = dt.astimezone(self.eastern_tz)
        
        # Round down to nearest 5-minute boundary
        minute = (et_dt.minute // 5) * 5
        aligned_et = et_dt.replace(minute=minute, second=0, microsecond=0)
        
        # Convert back to UTC
        return aligned_et.astimezone(timezone.utc)
        
    def get_trading_session_bounds(self, dt: datetime, include_extended_hours: bool) -> Tuple[datetime, datetime]:
        """
        Get the start and end bounds for a trading session.
        """
        et_dt = dt.astimezone(self.eastern_tz)
        session_date = et_dt.date()
        
        if include_extended_hours:
            # Extended session: 4:00 AM - 8:00 PM ET
            session_start_et = self.eastern_tz.localize(
                datetime.combine(session_date, self.premarket_open)
            )
            session_end_et = self.eastern_tz.localize(
                datetime.combine(session_date, self.postmarket_close)
            )
        else:
            # Regular session: 9:30 AM - 4:00 PM ET
            session_start_et = self.eastern_tz.localize(
                datetime.combine(session_date, self.regular_open)
            )
            session_end_et = self.eastern_tz.localize(
                datetime.combine(session_date, self.regular_close)
            )
            
        return (
            session_start_et.astimezone(timezone.utc),
            session_end_et.astimezone(timezone.utc)
        )
    
    def get_next_trading_day(self, dt: datetime) -> datetime:
        """Get the next trading day after the given date."""
        next_day = dt + timedelta(days=1)
        
        # Keep looking until we find a trading day
        while not self.is_market_day(next_day):
            next_day += timedelta(days=1)
            
        return next_day
    
    def get_previous_trading_day(self, dt: datetime) -> datetime:
        """Get the previous trading day before the given date."""
        prev_day = dt - timedelta(days=1)
        
        # Keep looking until we find a trading day
        while not self.is_market_day(prev_day):
            prev_day -= timedelta(days=1)
            
        return prev_day
    
    def is_early_close_day(self, dt: datetime) -> bool:
        """
        Check if market closes early (1:00 PM ET) on this day.
        Typically day after Thanksgiving, Christmas Eve, etc.
        """
        et_dt = dt.astimezone(self.eastern_tz)
        date_str = et_dt.strftime('%Y-%m-%d')
        
        # Early close days (1:00 PM ET close)
        early_close_days = {
            '2024-11-29': "Day after Thanksgiving",  # Friday after Thanksgiving 2024
            '2024-12-24': "Christmas Eve",
            '2025-11-28': "Day after Thanksgiving",  # Friday after Thanksgiving 2025
            '2025-12-24': "Christmas Eve",
            '2026-11-27': "Day after Thanksgiving",  # Friday after Thanksgiving 2026
            '2026-12-24': "Christmas Eve"
        }
        
        return date_str in early_close_days
    
    def get_market_close_time(self, dt: datetime) -> datetime:
        """
        Get the market close time for a given date.
        Returns 4:00 PM ET normally, 1:00 PM ET on early close days.
        """
        et_dt = dt.astimezone(self.eastern_tz)
        session_date = et_dt.date()
        
        if self.is_early_close_day(dt):
            # Early close at 1:00 PM ET
            close_time_et = self.eastern_tz.localize(
                datetime.combine(session_date, dt_time(13, 0))
            )
        else:
            # Normal close at 4:00 PM ET
            close_time_et = self.eastern_tz.localize(
                datetime.combine(session_date, self.regular_close)
            )
            
        return close_time_et.astimezone(timezone.utc)


# Global market calendar instance
market_calendar = USMarketCalendar()