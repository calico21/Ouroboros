"""
Unit tests for Opening Range Breakout strategy.
"""
from datetime import datetime, timezone
from src.core.events import BarEvent
from src.core.enums import OrderSide
from src.strategies.orb_5m_binary.strategy import Orb5mBinaryStrategy


def test_orb_strategy_signal_generation():
    strategy = Orb5mBinaryStrategy()
    strategy.reset_session()

    # Bar 1: 09:30 RTH Open (defines OR)
    b1 = BarEvent(
        timestamp=datetime(2026, 3, 10, 9, 30, tzinfo=timezone.utc),
        open=20000.0,
        high=20050.0,
        low=19980.0,
        close=20020.0,
        volume=5000,
        symbol="MNQ"
    )
    s1 = strategy.on_bar(b1)
    assert s1 is None
    assert strategy.or_formed is True
    assert strategy.tracker.or_high == 20050.0
    assert strategy.tracker.or_low == 19980.0

    # Bar 2: Inside bar (no breakout)
    b2 = BarEvent(
        timestamp=datetime(2026, 3, 10, 9, 35, tzinfo=timezone.utc),
        open=20020.0,
        high=20045.0,
        low=20010.0,
        close=20030.0,
        volume=3000,
        symbol="MNQ"
    )
    s2 = strategy.on_bar(b2)
    assert s2 is None

    # Bar 3: Breakout above OR High
    b3 = BarEvent(
        timestamp=datetime(2026, 3, 10, 9, 40, tzinfo=timezone.utc),
        open=20030.0,
        high=20070.0,
        low=20025.0,
        close=20060.0,
        volume=8000,
        symbol="MNQ"
    )
    s3 = strategy.on_bar(b3)
    assert s3 is not None
    assert s3.direction == OrderSide.LONG
    assert s3.stop_loss == 20015.0  # Midpoint: (20050 + 19980) / 2 = 20015
    assert s3.take_profit > 20060.0


if __name__ == "__main__":
    test_orb_strategy_signal_generation()
    print("ORB Strategy test passed!")
