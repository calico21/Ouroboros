"""
Unit tests for Evolved Opening Range Breakout strategy.
Tests target geometry (fixed_rr vs orb_range_multiple), time-stops, and session window cutoffs.
"""
from datetime import datetime, time
import zoneinfo
from src.core.events import BarEvent
from src.core.enums import OrderSide
from src.strategies.orb_5m_binary.strategy import Orb5mBinaryStrategy
from src.strategies.orb_5m_binary.indicators import OpeningRangeTracker

NY_TZ = zoneinfo.ZoneInfo("America/New_York")


def test_orb_tracker_target_modes():
    """Verify target calculation under fixed_rr vs orb_range_multiple."""
    tracker = OpeningRangeTracker()
    tracker.update(high=20050.0, low=20000.0)  # 50 pt range
    assert tracker.range_pts == 50.0
    assert tracker.midpoint == 20025.0

    entry = 20055.0
    risk = entry - 20025.0  # 30 pts risk to midpoint

    # 1. Fixed R:R Mode (1.0R)
    tp_fixed = tracker.calculate_take_profit(
        entry_price=entry,
        is_long=True,
        risk_pts=risk,
        target_mode="fixed_rr",
        risk_reward=1.0
    )
    assert tp_fixed == entry + 30.0  # 20085.0

    # 2. ORB Range Multiple Mode (0.80x OR Range)
    tp_range = tracker.calculate_take_profit(
        entry_price=entry,
        is_long=True,
        risk_pts=risk,
        target_mode="orb_range_multiple",
        range_mult=0.80
    )
    assert tp_range == entry + (0.80 * 50.0)  # 20055 + 40 = 20095.0


def test_orb_strategy_signal_with_evolved_params():
    """Verify strategy outputs trade setup with time_stop_bars and target."""
    strategy = Orb5mBinaryStrategy(config_overrides={
        "target_mode": "fixed_rr",
        "risk_reward": 1.0,
        "time_stop_bars": 3,
        "protect_at_1r": True
    })
    strategy.reset_session()

    # Bar 1: 09:30 RTH Open (defines OR)
    b1 = BarEvent(
        timestamp=datetime(2026, 3, 10, 9, 30, tzinfo=NY_TZ),
        open=20000.0,
        high=20050.0,
        low=20000.0,
        close=20020.0,
        volume=5000,
        symbol="MNQ"
    )
    s1 = strategy.on_bar(b1)
    assert s1 is None
    assert strategy.or_formed is True

    # Bar 2: 09:35 Breakout Bar > OR High (20050)
    b2 = BarEvent(
        timestamp=datetime(2026, 3, 10, 9, 35, tzinfo=NY_TZ),
        open=20025.0,
        high=20065.0,
        low=20020.0,
        close=20060.0,
        volume=8000,
        symbol="MNQ"
    )
    s2 = strategy.on_bar(b2)
    assert s2 is not None
    assert s2.direction == OrderSide.LONG
    assert s2.time_stop_bars == 3
    assert s2.protect_at_1r is True
    assert s2.stop_loss == 20025.0  # Midpoint
    risk = 20060.0 - 20025.0  # 35 pts
    assert s2.take_profit == 20060.0 + 35.0  # 1.0R = 20095.0


def test_orb_strategy_cutoff_after_1130():
    """Verify no new breakout trades after 11:30 EST expiration cutoff."""
    strategy = Orb5mBinaryStrategy()
    strategy.reset_session()

    # Define OR
    b1 = BarEvent(
        timestamp=datetime(2026, 3, 10, 9, 30, tzinfo=NY_TZ),
        open=20000.0, high=20050.0, low=20000.0, close=20020.0, volume=5000, symbol="MNQ"
    )
    strategy.on_bar(b1)

    # Late bar at 11:35 EST
    b_late = BarEvent(
        timestamp=datetime(2026, 3, 10, 11, 35, tzinfo=NY_TZ),
        open=20040.0, high=20070.0, low=20030.0, close=20065.0, volume=3000, symbol="MNQ"
    )
    s_late = strategy.on_bar(b_late)
    assert s_late is None


def test_orb_strategy_rvol_and_candle_quality_gates():
    """Verify RVOL gate and candle structural conviction (Clutch Factor) filters."""
    strategy = Orb5mBinaryStrategy(config_overrides={
        "min_breakout_rvol": 1.25,
        "min_bar_body_pct": 0.55,
        "min_close_extremity_pct": 0.75,
    })
    strategy.reset_session()

    # Pre-calibrate a 15-day median baseline of 10,000 for 09:45 EST
    strategy.volume_tracker.set_baseline(time(9, 45), 10000.0)

    # 1. OR definition bar at 09:30 (OR High = 20050.0, OR Low = 20000.0)
    b1 = BarEvent(
        timestamp=datetime(2026, 3, 10, 9, 30, tzinfo=NY_TZ),
        open=20010.0, high=20050.0, low=20000.0, close=20040.0, volume=12000, symbol="MNQ"
    )
    strategy.on_bar(b1)

    # 2. Test Low-Volume Fakeout: Breakout occurs at 09:45 but volume is only 11,000 (RVOL = 1.10 < 1.25 gate)
    b_low_vol = BarEvent(
        timestamp=datetime(2026, 3, 10, 9, 45, tzinfo=NY_TZ),
        open=20045.0, high=20070.0, low=20040.0, close=20068.0,
        volume=11000, symbol="MNQ"  # 11000 / 10000 = 1.10x RVOL (< 1.25)
    )
    s_low_vol = strategy.on_bar(b_low_vol)
    assert s_low_vol is None, "Should reject breakout due to insufficient RVOL (< 1.25x)"

    # Reset session for next test
    strategy.reset_session()
    strategy.volume_tracker.set_baseline(time(9, 45), 10000.0)
    strategy.on_bar(b1)

    # 3. Test Wicky / Rejection Candle: High volume (15,000, RVOL = 1.50x), but massive upper wick!
    # Open=20030, Close=20052, High=20085, Low=20025 -> Range=60, Body=22 (36.7% < 55%), Extremity=27/60=45% (< 75%)
    b_wicky = BarEvent(
        timestamp=datetime(2026, 3, 10, 9, 45, tzinfo=NY_TZ),
        open=20030.0, high=20085.0, low=20025.0, close=20052.0,
        volume=15000, symbol="MNQ"
    )
    s_wicky = strategy.on_bar(b_wicky)
    assert s_wicky is None, "Should reject breakout due to wicky candle lacking conviction"

    # Reset session for next test
    strategy.reset_session()
    strategy.volume_tracker.set_baseline(time(9, 45), 10000.0)
    strategy.on_bar(b1)

    # 4. Valid High-Conviction Clutch Breakout:
    # Volume=16,000 (1.60x RVOL >= 1.25), Open=20042, High=20075, Low=20040, Close=20072
    # Range=35, Body=30 (85.7% >= 55%), Close Extremity=(20072-20040)/35 = 32/35 = 91.4% (>= 75%)
    b_valid = BarEvent(
        timestamp=datetime(2026, 3, 10, 9, 45, tzinfo=NY_TZ),
        open=20042.0, high=20075.0, low=20040.0, close=20072.0,
        volume=16000, symbol="MNQ"
    )
    s_valid = strategy.on_bar(b_valid)
    assert s_valid is not None, "Valid high-volume clutch breakout should emit TradeSetup"
    assert s_valid.direction == OrderSide.LONG
    assert s_valid.metadata["rvol"] >= 1.25
    assert s_valid.metadata["body_pct"] >= 0.55
    assert s_valid.metadata["close_extremity"] >= 0.75


if __name__ == "__main__":
    test_orb_tracker_target_modes()
    test_orb_strategy_signal_with_evolved_params()
    test_orb_strategy_cutoff_after_1130()
    test_orb_strategy_rvol_and_candle_quality_gates()
    print("All ORB tests passed successfully!")
