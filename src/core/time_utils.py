"""
Time utilities for CME session handling, RTH boundaries, and regime attribution.
"""
from datetime import datetime, time
from typing import Tuple
import zoneinfo

NY_TZ = zoneinfo.ZoneInfo("America/New_York")
UTC_TZ = zoneinfo.ZoneInfo("UTC")

RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)


def ensure_ny_tz(dt: datetime) -> datetime:
    """Ensure timestamp is localized or converted to America/New_York."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=NY_TZ)
    return dt.astimezone(NY_TZ)


def is_rth(dt: datetime) -> bool:
    """Check if timestamp falls within CME Regular Trading Hours (09:30 - 16:00 EST)."""
    ny_dt = ensure_ny_tz(dt)
    if ny_dt.weekday() >= 5:  # Saturday or Sunday
        return False
    t = ny_dt.time()
    return RTH_OPEN <= t < RTH_CLOSE


def get_session_window(dt: datetime) -> str:
    """
    Classify entry into intraday auction regime windows:
    - 09:30–10:00: Opening Drive / Initial Auction
    - 10:00–11:30: Morning Trend & Institutional Discovery
    - 11:30–13:30: Midday Lunch Chop & Mean Reversion
    - 13:30–15:30: Afternoon Session & Expansion
    - 15:30–16:00: Cash Close Imbalance
    - ETH: Electronic Trading Hours
    """
    ny_dt = ensure_ny_tz(dt)
    t = ny_dt.time()
    
    if not is_rth(dt):
        return "ETH (Overnight)"
    
    if time(9, 30) <= t < time(10, 0):
        return "09:30-10:00 (Open Auction)"
    elif time(10, 0) <= t < time(11, 30):
        return "10:00-11:30 (Morning Trend)"
    elif time(11, 30) <= t < time(13, 30):
        return "11:30-13:30 (Midday Lunch)"
    elif time(13, 30) <= t < time(15, 30):
        return "13:30-15:30 (Afternoon Drive)"
    else:
        return "15:30-16:00 (Market Close)"


def get_day_of_week(dt: datetime) -> str:
    """Return standard weekday name."""
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    return days[dt.weekday()]
