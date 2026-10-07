"""
Unit tests for Trapped Liquidity Sweep Strategy.
Validates bull traps, bear traps, runaway trend filters, and timeout invalidations.
"""
import unittest
from datetime import datetime
import pytz

from src.core.events import BarEvent
from src.core.enums import OrderSide, OrderType
from src.strategies.trapped_liquidity_sweep.strategy import TrappedLiquiditySweepStrategy
from src.strategies.trapped_liquidity_sweep.indicators import (
    TrappedLiquidityTracker,
    SweepState,
)


class TestTrappedLiquiditySweep(unittest.TestCase):

    def setUp(self):
        self.est = pytz.timezone("US/Eastern")

    def _make_bar(self, hour: int, minute: int, o: float, h: float, l: float, c: float, vol: float = 1000.0) -> BarEvent:
        dt = datetime(2025, 10, 15, hour, minute, 0)
        dt = self.est.localize(dt)
        return BarEvent(
            timestamp=dt,
            open=o,
            high=h,
            low=l,
            close=c,
            volume=vol,
            symbol="MNQ"
        )

    def test_valid_bull_trap_short(self):
        """Simulates 15m OR formed [20000 - 20050], false breakout above 20050 up to 20058, re-entering at 20045."""
        strat = TrappedLiquiditySweepStrategy()

        # 09:30, 09:35, 09:40 bars define 15m range [20000, 20050]
        strat.on_bar(self._make_bar(9, 30, 20010, 20040, 20000, 20030))
        strat.on_bar(self._make_bar(9, 35, 20030, 20050, 20020, 20040))
        strat.on_bar(self._make_bar(9, 34, 20040, 20048, 20025, 20035))  # Before 09:45

        # 09:45 Bar: Breaches above 20050 up to 20058 (+8 pts extension), closes at 20054 (outside range)
        s1 = strat.on_bar(self._make_bar(9, 45, 20035, 20058, 20030, 20054))
        self.assertIsNone(s1, "Should not enter while still outside range")

        # 09:50 Bar: Re-enters back inside range, closing at 20045 (< 20050 ORB High)
        s2 = strat.on_bar(self._make_bar(9, 50, 20054, 20056, 20040, 20045))
        self.assertIsNotNone(s2, "Should emit short signal on confirmed re-entry")
        self.assertEqual(s2.direction, OrderSide.SHORT)
        self.assertEqual(s2.order_type, OrderType.MARKET)
        # Stop loss should be highest wick (20058) + 1 tick (0.25) = 20058.25
        self.assertAlmostEqual(s2.stop_loss, 20058.25, places=2)
        # Midpoint is (20050 + 20000) / 2 = 20025.0
        self.assertAlmostEqual(s2.take_profit, 20025.0, places=2)

    def test_valid_bear_trap_long(self):
        """Simulates 15m OR formed [20000 - 20060], false breakout below 20000 down to 19992, re-entering at 20005."""
        strat = TrappedLiquiditySweepStrategy()

        # 09:30-09:40 bars define range [20000, 20060]
        strat.on_bar(self._make_bar(9, 30, 20020, 20060, 20010, 20040))
        strat.on_bar(self._make_bar(9, 35, 20040, 20055, 20000, 20030))

        # 09:45 Bar: Pierces low to 19992 (-8 pts extension) and closes back inside at 20005! (1-bar absorption)
        setup = strat.on_bar(self._make_bar(9, 45, 20030, 20035, 19992, 20005))
        self.assertIsNotNone(setup, "Should emit long signal on immediate 1-bar bear trap")
        self.assertEqual(setup.direction, OrderSide.LONG)
        # Stop loss at lowest wick (19992) - 1 tick (0.25) = 19991.75
        self.assertAlmostEqual(setup.stop_loss, 19991.75, places=2)
        # Midpoint is (20060 + 20000) / 2 = 20030.0
        self.assertAlmostEqual(setup.take_profit, 20030.0, places=2)

    def test_runaway_trend_filter(self):
        """If breakout exceeds 25 pts beyond ORB boundary, it is a real breakout, not a sweep."""
        strat = TrappedLiquiditySweepStrategy()

        # Range [20000, 20050]
        strat.on_bar(self._make_bar(9, 30, 20010, 20050, 20000, 20030))
        strat.on_bar(self._make_bar(9, 35, 20030, 20045, 20020, 20040))

        # 09:45: Explodes to 20080 (+30 pts extension > 25 pts max)
        s1 = strat.on_bar(self._make_bar(9, 45, 20040, 20080, 20038, 20078))
        self.assertIsNone(s1)

        # 09:50: Even if price falls back to 20040, runaway filter must invalidate the setup
        s2 = strat.on_bar(self._make_bar(9, 50, 20078, 20078, 20035, 20040))
        self.assertIsNone(s2, "Runaway trend must never trigger counter-trend sweep entry")

    def test_timeout_invalidation(self):
        """If price stays outside range for more than 3 bars, it is invalidated as a consolidation outside range."""
        strat = TrappedLiquiditySweepStrategy()

        strat.on_bar(self._make_bar(9, 30, 20010, 20050, 20000, 20030))
        strat.on_bar(self._make_bar(9, 35, 20030, 20045, 20020, 20040))

        # Bar 1 outside: High 20056, Close 20054
        strat.on_bar(self._make_bar(9, 45, 20040, 20056, 20038, 20054))
        # Bar 2 outside: High 20057, Close 20055
        strat.on_bar(self._make_bar(9, 50, 20054, 20057, 20051, 20055))
        # Bar 3 outside: High 20058, Close 20053
        strat.on_bar(self._make_bar(9, 55, 20055, 20058, 20051, 20053))
        # Bar 4 outside: High 20055, Close 20052 (Timed out!)
        strat.on_bar(self._make_bar(10, 0, 20053, 20055, 20050, 20052))

        # Now bar 5 re-enters at 20042: Should be rejected due to timeout
        s5 = strat.on_bar(self._make_bar(10, 5, 20052, 20052, 20040, 20042))
        self.assertIsNone(s5, "Timed out sweep should not generate setup")

    def test_max_trades_per_day_enforcement(self):
        """Strategy must take at most 1 trade per session."""
        strat = TrappedLiquiditySweepStrategy()

        strat.on_bar(self._make_bar(9, 30, 20020, 20060, 20010, 20040))
        strat.on_bar(self._make_bar(9, 35, 20040, 20055, 20000, 20030))

        # First trade triggers
        s1 = strat.on_bar(self._make_bar(9, 45, 20030, 20035, 19992, 20005))
        self.assertIsNotNone(s1)

        # Subsequent bar tries to trigger again: must be blocked
        s2 = strat.on_bar(self._make_bar(9, 50, 20005, 20070, 20000, 20040))
        self.assertIsNone(s2)


if __name__ == "__main__":
    unittest.main()
