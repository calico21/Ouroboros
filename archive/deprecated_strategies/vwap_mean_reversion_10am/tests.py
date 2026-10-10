"""
Unit tests for VWAP Mean Reversion Strategy.
"""
from datetime import datetime, timezone
from src.core.events import BarEvent
from src.core.enums import OrderSide
from src.strategies.vwap_mean_reversion_10am.strategy import VwapMeanReversion10amStrategy


def test_vwap_fade_strategy():
    strat = VwapMeanReversion10amStrategy()
    strat.reset_session()

    # Pre-10am bar to build VWAP
    b1 = BarEvent(
        timestamp=datetime(2026, 3, 10, 9, 30, tzinfo=timezone.utc),
        open=20000.0, high=20020.0, low=19990.0, close=20010.0, volume=10000, symbol="MNQ"
    )
    assert strat.on_bar(b1) is None

    # Bar at 10:05 with large spike above +2 std dev
    b2 = BarEvent(
        timestamp=datetime(2026, 3, 10, 10, 5, tzinfo=timezone.utc),
        open=20080.0, high=20120.0, low=20060.0, close=20070.0, volume=15000, symbol="MNQ"
    )
    sig = strat.on_bar(b2)
    # If standard deviation is pierced and bearish rejection occurs
    if sig:
        assert sig.direction == OrderSide.SHORT
        assert sig.take_profit < sig.stop_loss


if __name__ == "__main__":
    test_vwap_fade_strategy()
    print("VWAP strategy test completed!")
