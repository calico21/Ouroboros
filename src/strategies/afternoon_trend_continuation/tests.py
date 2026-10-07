"""
Unit tests for Afternoon Trend Continuation Strategy.
Verifies midday consolidation formation (11:30-13:30 EST) and afternoon breakout execution.
"""
from datetime import datetime, time, timedelta
import zoneinfo
from src.core.events import BarEvent
from src.core.enums import OrderSide
from src.strategies.afternoon_trend_continuation.strategy import AfternoonTrendContinuationStrategy

NY_TZ = zoneinfo.ZoneInfo("America/New_York")


def test_afternoon_consolidation_and_breakout():
    strat = AfternoonTrendContinuationStrategy(config_overrides={
        "risk_reward": 1.50,
        "stop_mode": "midpoint"
    })
    strat.reset_session()

    base_date = datetime(2026, 3, 10, 0, 0, tzinfo=NY_TZ)

    # 1. Feed consolidation bars from 11:30 to 13:25 EST (24 bars)
    # Range will be: High 20050.0, Low 20020.0, Midpoint 20035.0 (30 pts range)
    for i in range(24):
        bar_time = base_date.replace(hour=11, minute=30) + timedelta(minutes=i * 5)
        b = BarEvent(
            timestamp=bar_time,
            open=20030.0,
            high=20050.0 if i == 5 else 20040.0,
            low=20020.0 if i == 10 else 20025.0,
            close=20035.0,
            volume=1500,
            symbol="MNQ"
        )
        sig = strat.on_bar(b)
        assert sig is None  # No signals during consolidation

    assert strat.tracker.is_valid_range is True
    assert strat.tracker.high == 20050.0
    assert strat.tracker.low == 20020.0
    assert strat.tracker.midpoint == 20035.0
    assert strat.tracker.range_pts == 30.0

    # 2. Bar at 13:30 EST still inside range
    b_inside = BarEvent(
        timestamp=base_date.replace(hour=13, minute=30),
        open=20035.0,
        high=20045.0,
        low=20030.0,
        close=20040.0,
        volume=2000,
        symbol="MNQ"
    )
    sig_inside = strat.on_bar(b_inside)
    assert sig_inside is None

    # 3. Bar at 13:35 EST: Breakout close > 20050.0 (prints 20055.0)
    b_breakout = BarEvent(
        timestamp=base_date.replace(hour=13, minute=35),
        open=20045.0,
        high=20060.0,
        low=20042.0,
        close=20055.0,
        volume=4000,
        symbol="MNQ"
    )
    sig = strat.on_bar(b_breakout)
    assert sig is not None
    assert sig.direction == OrderSide.LONG
    assert sig.tag == "PM_BREAKOUT_LONG"
    assert sig.stop_loss == 20035.0  # Midpoint of 20050 and 20020
    risk = 20055.0 - 20035.0  # 20.0 pts
    assert sig.take_profit == 20055.0 + (risk * 1.50)  # 20085.0

    # 4. Bar at 13:40 EST: Second breakout should be blocked (max 1 trade per day)
    b_second = BarEvent(
        timestamp=base_date.replace(hour=13, minute=40),
        open=20055.0,
        high=20070.0,
        low=20050.0,
        close=20065.0,
        volume=3500,
        symbol="MNQ"
    )
    sig2 = strat.on_bar(b_second)
    assert sig2 is None


if __name__ == "__main__":
    test_afternoon_consolidation_and_breakout()
    print("Afternoon trend continuation tests passed!")
