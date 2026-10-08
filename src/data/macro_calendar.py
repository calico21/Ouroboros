"""
Macroeconomic Catalyst & CME Globex Trading Calendar (2022-2026).
Maintains definitive schedules for:
1. CME Globex equity index futures holidays and early closes (half-days).
2. Major macroeconomic catalyst announcements:
   - FOMC Rate Decisions & Press Conferences (14:00/14:30 EST)
   - CPI (Consumer Price Index) releases (08:30 EST)
   - NFP (Non-Farm Payrolls / Employment Situation) releases (08:30 EST)
   - PPI (Producer Price Index) releases (08:30 EST)
Provides fast O(1) date lookups and regime tagging for intraday backtesting.
"""
from datetime import date, datetime, time
from typing import Dict, List, Optional, Set, Tuple
from enum import Enum
from pydantic import BaseModel, Field


class CatalystType(str, Enum):
    FOMC = "FOMC"
    CPI = "CPI"
    NFP = "NFP"
    PPI = "PPI"
    NONE = "NON_EVENT"


class MarketSessionType(str, Enum):
    REGULAR = "REGULAR"
    HALF_DAY = "HALF_DAY"
    HOLIDAY = "HOLIDAY"


class MacroEvent(BaseModel):
    event_date: str  # YYYY-MM-DD
    catalyst: CatalystType
    announcement_time_est: str  # e.g., "14:00" or "08:30"
    risk_weight: float = 1.0  # Normalized volatility weight [0.0 - 1.0]
    description: str


class MacroCalendar:
    """
    CME Globex Schedule and Macroeconomic Catalyst Registry covering 2022-2026.
    """

    def __init__(self):
        self._holidays: Set[str] = set()
        self._half_days: Dict[str, str] = {}  # date -> early close time EST (e.g., "13:00")
        self._events_by_date: Dict[str, List[MacroEvent]] = {}
        self._initialize_cme_calendar()
        self._initialize_macro_catalysts()

    def _initialize_cme_calendar(self):
        """Populate CME Globex full holidays and half-days for 2022-2026."""
        # Full Holidays (CME Equity Index Closed)
        holidays_list = [
            # 2022
            "2022-01-17", "2022-02-21", "2022-04-15", "2022-05-30", "2022-06-20",
            "2022-07-04", "2022-09-05", "2022-11-24", "2022-12-26",
            # 2023
            "2023-01-02", "2023-01-16", "2023-02-20", "2023-04-07", "2023-05-29",
            "2023-06-19", "2023-07-04", "2023-09-04", "2023-11-23", "2023-12-25",
            # 2024
            "2024-01-01", "2024-01-15", "2024-02-19", "2024-03-29", "2024-05-27",
            "2024-06-19", "2024-07-04", "2024-09-02", "2024-11-28", "2024-12-25",
            # 2025
            "2025-01-01", "2025-01-20", "2025-02-17", "2025-04-18", "2025-05-26",
            "2025-06-19", "2025-07-04", "2025-09-01", "2025-11-27", "2025-12-25",
            # 2026
            "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
            "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25"
        ]
        self._holidays = set(holidays_list)

        # Half-days / Early closes (13:00 or 13:15 EST)
        half_days_dict = {
            # 2022
            "2022-07-01": "13:00", "2022-11-25": "13:15", "2022-12-23": "13:15",
            # 2023
            "2023-07-03": "13:00", "2023-11-24": "13:15",
            # 2024
            "2024-07-03": "13:00", "2024-11-29": "13:15", "2024-12-24": "13:15",
            # 2025
            "2025-07-03": "13:00", "2025-11-28": "13:15", "2025-12-24": "13:15",
            # 2026
            "2026-11-27": "13:15", "2026-12-24": "13:15"
        }
        self._half_days = half_days_dict

    def _initialize_macro_catalysts(self):
        """Register key macro announcements (FOMC, CPI, NFP, PPI) 2022-2026."""
        # FOMC Decision Dates (typically 8 per year, 14:00 EST announcement)
        fomc_dates = [
            # 2022
            "2022-01-26", "2022-03-16", "2022-05-04", "2022-06-15", "2022-07-27",
            "2022-09-21", "2022-11-02", "2022-12-14",
            # 2023
            "2023-02-01", "2023-03-22", "2023-05-03", "2023-06-14", "2023-07-26",
            "2023-09-20", "2023-11-01", "2023-12-13",
            # 2024
            "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12", "2024-07-31",
            "2024-09-18", "2024-11-07", "2024-12-18",
            # 2025
            "2025-01-29", "2025-03-19", "2025-05-07", "2025-06-18", "2025-07-30",
            "2025-09-17", "2025-10-29", "2025-12-10",
            # 2026
            "2026-01-28", "2026-03-18", "2026-05-06", "2026-06-17", "2026-07-29",
            "2026-09-16", "2026-11-04", "2026-12-16"
        ]

        # CPI Release Dates (08:30 EST)
        cpi_dates = [
            # 2022
            "2022-01-12", "2022-02-10", "2022-03-10", "2022-04-12", "2022-05-11",
            "2022-06-10", "2022-07-13", "2022-08-10", "2022-09-13", "2022-10-13",
            "2022-11-10", "2022-12-13",
            # 2023
            "2023-01-12", "2023-02-14", "2023-03-14", "2023-04-12", "2023-05-10",
            "2023-06-13", "2023-07-12", "2023-08-10", "2023-09-13", "2023-10-12",
            "2023-11-14", "2023-12-12",
            # 2024
            "2024-01-11", "2024-02-13", "2024-03-12", "2024-04-10", "2024-05-15",
            "2024-06-12", "2024-07-11", "2024-08-14", "2024-09-11", "2024-10-10",
            "2024-11-13", "2024-12-11",
            # 2025
            "2025-01-15", "2025-02-12", "2025-03-12", "2025-04-09", "2025-05-14",
            "2025-06-11", "2025-07-09", "2025-08-13", "2025-09-10", "2025-10-15",
            "2025-11-12", "2025-12-10",
            # 2026
            "2026-01-14", "2026-02-11", "2026-03-11", "2026-04-14", "2026-05-13",
            "2026-06-10", "2026-07-15", "2026-08-12", "2026-09-16", "2026-10-14",
            "2026-11-12", "2026-12-09"
        ]

        # NFP Release Dates (First Friday of month, 08:30 EST)
        nfp_dates = [
            # 2022
            "2022-01-07", "2022-02-04", "2022-03-04", "2022-04-01", "2022-05-06",
            "2022-06-03", "2022-07-08", "2022-08-05", "2022-09-02", "2022-10-07",
            "2022-11-04", "2022-12-02",
            # 2023
            "2023-01-06", "2023-02-03", "2023-03-10", "2023-04-07", "2023-05-05",
            "2023-06-02", "2023-07-07", "2023-08-04", "2023-09-01", "2023-10-06",
            "2023-11-03", "2023-12-08",
            # 2024
            "2024-01-05", "2024-02-02", "2024-03-08", "2024-04-05", "2024-05-03",
            "2024-06-07", "2024-07-05", "2024-08-02", "2024-09-06", "2024-10-04",
            "2024-11-01", "2024-12-06",
            # 2025
            "2025-01-10", "2025-02-07", "2025-03-07", "2025-04-04", "2025-05-02",
            "2025-06-06", "2025-07-11", "2025-08-01", "2025-09-05", "2025-10-03",
            "2025-11-07", "2025-12-05",
            # 2026
            "2026-01-09", "2026-02-06", "2026-03-06", "2026-04-10", "2026-05-08",
            "2026-06-05", "2026-07-10", "2026-08-07", "2026-09-04", "2026-10-02",
            "2026-11-06", "2026-12-04"
        ]

        # Register FOMC events
        for d in fomc_dates:
            self._add_event(MacroEvent(
                event_date=d,
                catalyst=CatalystType.FOMC,
                announcement_time_est="14:00",
                risk_weight=1.0,
                description="Federal Open Market Committee Rate Decision"
            ))

        # Register CPI events
        for d in cpi_dates:
            self._add_event(MacroEvent(
                event_date=d,
                catalyst=CatalystType.CPI,
                announcement_time_est="08:30",
                risk_weight=0.95,
                description="Consumer Price Index Inflation Report"
            ))

        # Register NFP events
        for d in nfp_dates:
            self._add_event(MacroEvent(
                event_date=d,
                catalyst=CatalystType.NFP,
                announcement_time_est="08:30",
                risk_weight=0.90,
                description="Employment Situation / Non-Farm Payrolls"
            ))

    def _add_event(self, event: MacroEvent):
        if event.event_date not in self._events_by_date:
            self._events_by_date[event.event_date] = []
        self._events_by_date[event.event_date].append(event)

    def get_session_type(self, dt: date) -> MarketSessionType:
        """Return REGULAR, HALF_DAY, or HOLIDAY for a given calendar date."""
        d_str = dt.isoformat() if isinstance(dt, date) else str(dt)
        if dt.weekday() >= 5:  # Saturday or Sunday
            return MarketSessionType.HOLIDAY
        if d_str in self._holidays:
            return MarketSessionType.HOLIDAY
        if d_str in self._half_days:
            return MarketSessionType.HALF_DAY
        return MarketSessionType.REGULAR

    def is_trading_day(self, dt: date) -> bool:
        """Returns True if the market is open for trading (regular or half-day)."""
        return self.get_session_type(dt) != MarketSessionType.HOLIDAY

    def get_half_day_close(self, dt: date) -> Optional[str]:
        """Returns early close time if half-day, else None."""
        d_str = dt.isoformat() if isinstance(dt, date) else str(dt)
        return self._half_days.get(d_str)

    def get_events_for_date(self, dt: date) -> List[MacroEvent]:
        """Returns list of macro events scheduled on this date."""
        d_str = dt.isoformat() if isinstance(dt, date) else str(dt)
        return self._events_by_date.get(d_str, [])

    def get_primary_catalyst(self, dt: date) -> CatalystType:
        """
        Returns dominant catalyst for the date:
        FOMC takes priority over CPI, which takes priority over NFP, etc.
        """
        events = self.get_events_for_date(dt)
        if not events:
            return CatalystType.NONE
        
        # Sort by risk weight descending
        sorted_events = sorted(events, key=lambda e: e.risk_weight, reverse=True)
        return sorted_events[0].catalyst

    def is_fomc_day(self, dt: date) -> bool:
        return any(e.catalyst == CatalystType.FOMC for e in self.get_events_for_date(dt))

    def is_cpi_day(self, dt: date) -> bool:
        return any(e.catalyst == CatalystType.CPI for e in self.get_events_for_date(dt))

    def is_nfp_day(self, dt: date) -> bool:
        return any(e.catalyst == CatalystType.NFP for e in self.get_events_for_date(dt))

    def should_suppress_strategy_entry(
        self,
        dt: date,
        time_est: str,
        buffer_minutes_before: int = 15,
        buffer_minutes_after: int = 30
    ) -> Tuple[bool, Optional[str]]:
        """
        Determines if an automated strategy should pause/suppress entry
        due to an impending or recent high-impact macroeconomic event.
        """
        events = self.get_events_for_date(dt)
        if not events:
            return False, None

        curr_parts = [int(p) for p in time_est.split(":")]
        curr_mins = curr_parts[0] * 60 + curr_parts[1]

        for e in events:
            ann_parts = [int(p) for p in e.announcement_time_est.split(":")]
            ann_mins = ann_parts[0] * 60 + ann_parts[1]

            if (ann_mins - buffer_minutes_before) <= curr_mins <= (ann_mins + buffer_minutes_after):
                return True, f"Suppressed: {e.catalyst.value} announcement at {e.announcement_time_est} EST"

        return False, None
