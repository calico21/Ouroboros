"""
Unit tests for Open Drive Continuation Strategy.
"""
from datetime import datetime, timezone
from src.core.events import BarEvent
from src.core.enums import OrderSide
from src.strategies.open_drive_continuation.strategy import OpenDriveContinuationStrategy


def test_open_drive_strategy():
    strat = OpenDriveContinuationStrategy()
    strat.reset_session()

    # Open Drive Bar (Bullish Marubozu-like conviction at 09:30)
    b1 = BarEvent(
        timestamp=datetime(2026, 3, 10, 9, 30, tzinfo=timezone.utc),
        open=20000.0, high=20050.0, low=19998.0, close=20048.0, volume=12000, symbol="MNQ"
    )
    assert strat.on_bar(b1) is None
    assert strat.detector.drive_detected is True
    assert strat.detector.direction == "BULLISH"

    # Continuation Bar at 09:35 pushing new high
    b2 = BarEvent(
        timestamp=datetime(2026, 3, 10, 9, 35, tzinfo=timezone.utc),
        open=20048.0, high=20070.0, low=20040.0, close=20065.0, volume=9000, symbol="MNQ"
    )
    sig = strat.on_bar(b2)
    assert sig is not None
    assert sig.direction == OrderSide.LONG


if __name__ == "__main__":
    test_open_drive_strategy()
    print("Open drive strategy test passed!")
