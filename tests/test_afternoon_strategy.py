"""
PyTest discovery test for Afternoon Trend Continuation Strategy.
"""
from datetime import datetime, timedelta
import zoneinfo
from src.core.events import BarEvent
from src.core.enums import OrderSide
from src.strategies.afternoon_trend_continuation.strategy import AfternoonTrendContinuationStrategy
from src.strategies.afternoon_trend_continuation.tests import test_afternoon_consolidation_and_breakout

NY_TZ = zoneinfo.ZoneInfo("America/New_York")


def test_afternoon_strategy_integration():
    test_afternoon_consolidation_and_breakout()


def test_afternoon_strategy_cpi_blackout():
    """Verify that CPI release days (e.g. 2026-01-14) suppress trade entry."""
    strat = AfternoonTrendContinuationStrategy()
    strat.reset_session()

    # 2026-01-14 is a scheduled CPI date in MacroCalendar
    cpi_date = datetime(2026, 1, 14, 0, 0, tzinfo=NY_TZ)

    # Feed consolidation bars
    for i in range(24):
        bar_time = cpi_date.replace(hour=11, minute=30) + timedelta(minutes=i * 5)
        b = BarEvent(
            timestamp=bar_time,
            open=20030.0,
            high=20050.0 if i == 5 else 20040.0,
            low=20020.0 if i == 10 else 20025.0,
            close=20035.0,
            volume=1500,
            symbol="MNQ"
        )
        strat.on_bar(b)

    # Breakout bar at 13:35 EST
    b_breakout = BarEvent(
        timestamp=cpi_date.replace(hour=13, minute=35),
        open=20045.0,
        high=20060.0,
        low=20042.0,
        close=20055.0,
        volume=4000,
        symbol="MNQ"
    )
    sig = strat.on_bar(b_breakout)
    assert sig is None, "Expected trade suppression on CPI day"
