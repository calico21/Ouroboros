"""
CME Globex Session Clock and Trade Date Rollover Engine for AlphaForge.
Standardizes all market timestamps to US Eastern Time (America/New_York)
and strictly enforces CME 18:00 ET Trade Date accounting.
"""
from datetime import datetime, date, time, timedelta
from typing import Optional, Tuple
import zoneinfo

NY_TZ = zoneinfo.ZoneInfo("America/New_York")
UTC_TZ = zoneinfo.ZoneInfo("UTC")

# CME Globex Core Times (ET)
CME_SESSION_OPEN_TIME = time(18, 0, 0)      # 18:00:00 ET
CME_SETTLEMENT_CUTOFF = time(16, 59, 59)    # 16:59:59 ET
CME_MAINTENANCE_START = time(17, 0, 0)      # 17:00:00 ET
CME_MAINTENANCE_END = time(17, 59, 59)      # 17:59:59 ET

RTH_OPEN_TIME = time(9, 30, 0)              # 09:30:00 ET
RTH_CLOSE_TIME = time(16, 0, 0)             # 16:00:00 ET
EOD_CANCEL_ORDERS_TIME = time(15, 50, 0)    # 15:50:00 ET
EOD_LIQUIDATION_TIME = time(15, 55, 0)      # 15:55:00 ET
EOD_MOC_LIQUIDATION_TIME = time(15, 58, 0)  # 15:58:00 ET (Exclusively for MOC strategy)


def ensure_ny_tz(dt: datetime) -> datetime:
    """Ensure timestamp is localized or converted to America/New_York."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=NY_TZ)
    return dt.astimezone(NY_TZ)


def get_cme_trade_date(dt: datetime) -> date:
    """
    Returns the official CME Globex Trade Date for a given timestamp.
    Any bar from 18:00:00 ET on Sunday/weekday to 16:59:59 ET next calendar day
    belongs to that next CME Trade Date.
    
    Examples:
      - Sunday 18:05 ET -> Trade Date is Monday
      - Monday 03:00 ET -> Trade Date is Monday
      - Monday 15:30 ET -> Trade Date is Monday
      - Monday 18:05 ET -> Trade Date is Tuesday
      - Friday 15:00 ET -> Trade Date is Friday
    """
    et = ensure_ny_tz(dt)
    cal_date = et.date()
    t = et.time()
    weekday = et.weekday()  # 0=Monday, 4=Friday, 5=Saturday, 6=Sunday

    if t >= CME_SESSION_OPEN_TIME:
        # 18:00 ET onwards belongs to the next trade date
        if weekday == 6:  # Sunday evening -> Monday trade date
            return cal_date + timedelta(days=1)
        elif weekday == 4:  # Friday evening (maintenance/edge case) -> Monday
            return cal_date + timedelta(days=3)
        elif weekday == 5:  # Saturday (closed, but if data exists) -> Monday
            return cal_date + timedelta(days=2)
        else:  # Monday - Thursday evening -> next calendar day
            return cal_date + timedelta(days=1)
    else:
        # Before 18:00 ET
        # Bars up to 16:59:59 belong to the current calendar date's trade date
        # If Saturday or Sunday morning (market closed), assign to Monday trade date
        if weekday == 5:
            return cal_date + timedelta(days=2)
        elif weekday == 6:
            return cal_date + timedelta(days=1)
        else:
            return cal_date


def get_cme_trade_date_str(dt: datetime) -> str:
    """Format CME trade date as ISO YYYY-MM-DD string."""
    return get_cme_trade_date(dt).strftime("%Y-%m-%d")


def is_cme_session_boundary(prev_dt: Optional[datetime], curr_dt: datetime) -> bool:
    """
    Returns True if curr_dt rolled into a new CME Trade Date compared to prev_dt.
    Used by strategies and account managers to reset daily state at 18:00 ET.
    """
    if prev_dt is None:
        return True
    return get_cme_trade_date(prev_dt) != get_cme_trade_date(curr_dt)


def is_cme_market_open(dt: datetime) -> bool:
    """Check if CME Globex is currently open for trading."""
    et = ensure_ny_tz(dt)
    weekday = et.weekday()
    t = et.time()

    # Friday after 17:00 ET to Sunday before 18:00 ET is closed
    if weekday == 4 and t >= CME_MAINTENANCE_START:
        return False
    if weekday == 5:
        return False
    if weekday == 6 and t < CME_SESSION_OPEN_TIME:
        return False

    # Weekday maintenance halt (17:00 to 18:00 ET)
    if CME_MAINTENANCE_START <= t < CME_SESSION_OPEN_TIME:
        return False

    return True


def is_rth(dt: datetime) -> bool:
    """Check if timestamp falls within Regular Trading Hours (09:30:00 - 16:00:00 ET)."""
    et = ensure_ny_tz(dt)
    if et.weekday() >= 5:
        return False
    t = et.time()
    return RTH_OPEN_TIME <= t < RTH_CLOSE_TIME


def is_eth(dt: datetime) -> bool:
    """Check if timestamp falls within Electronic Overnight Trading Hours."""
    return is_cme_market_open(dt) and not is_rth(dt)


def get_session_phase(dt: datetime) -> str:
    """
    Returns granular CME session phase:
    - ETH_OVERNIGHT (18:00 - 08:30)
    - PRE_MARKET_AUCTION (08:30 - 09:30)
    - RTH_OPEN_DRIVE (09:30 - 10:00)
    - RTH_MORNING_TREND (10:00 - 11:30)
    - RTH_MIDDAY_EQUILIBRIUM (11:30 - 13:30)
    - RTH_AFTERNOON_SESSION (13:30 - 15:30)
    - RTH_CASH_CLOSE (15:30 - 16:00)
    - POST_CLOSE (16:00 - 17:00)
    - MAINTENANCE_HALT (17:00 - 18:00)
    - WEEKEND_HALT
    """
    if not is_cme_market_open(dt):
        return "WEEKEND_HALT"

    et = ensure_ny_tz(dt)
    t = et.time()

    if t >= CME_MAINTENANCE_START and t < CME_SESSION_OPEN_TIME:
        return "MAINTENANCE_HALT"

    if t >= CME_SESSION_OPEN_TIME or t < time(8, 30):
        return "ETH_OVERNIGHT"
    elif time(8, 30) <= t < RTH_OPEN_TIME:
        return "PRE_MARKET_AUCTION"
    elif RTH_OPEN_TIME <= t < time(10, 0):
        return "RTH_OPEN_DRIVE"
    elif time(10, 0) <= t < time(11, 30):
        return "RTH_MORNING_TREND"
    elif time(11, 30) <= t < time(13, 30):
        return "RTH_MIDDAY_EQUILIBRIUM"
    elif time(13, 30) <= t < time(15, 30):
        return "RTH_AFTERNOON_SESSION"
    elif time(15, 30) <= t < RTH_CLOSE_TIME:
        return "RTH_CASH_CLOSE"
    else:
        return "POST_CLOSE"
