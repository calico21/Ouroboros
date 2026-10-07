"""
Trapped Liquidity Sweep Strategy for CME Globex Futures (MNQ).
Capitalizes on failed 15-minute Opening Range breakouts by fading retail breakout
traps upon confirmed institutional re-entry back into the range.
"""
from datetime import time
from typing import Optional, Dict, Any
from src.core.events import BarEvent, TradeSetup
from src.core.enums import OrderSide, OrderType
from src.strategies.base import BaseStrategy
from src.strategies.trapped_liquidity_sweep.indicators import (
    TrappedLiquidityTracker,
    SweepState,
)


class TrappedLiquiditySweepStrategy(BaseStrategy):
    """
    Trapped Liquidity Sweep (Opening Range Reversal) Strategy.
    Monitors 09:30-09:45 EST Opening Range. When price pierces the boundary
    by 2.0 to 25.0 points and closes back inside within 1-3 bars, enters counter-trend
    targeting the range midpoint with risk anchored to the sweep wick extreme.
    """

    def __init__(self, config_overrides: Optional[Dict[str, Any]] = None):
        super().__init__(config_overrides)
        min_sweep = float(self.config.get("min_sweep_extension_pts", 2.0))
        max_sweep = float(self.config.get("max_sweep_extension_pts", 25.0))
        timeout_bars = int(self.config.get("re_entry_timeout_bars", 3))

        self.tracker = TrappedLiquidityTracker(
            min_sweep_pts=min_sweep,
            max_sweep_pts=max_sweep,
            re_entry_timeout_bars=timeout_bars
        )
        self.trades_this_session = 0
        self.trade_executed_today = False

    def reset_session(self) -> None:
        self.tracker.reset()
        self.trades_this_session = 0
        self.trade_executed_today = False

    def on_bar(self, bar: BarEvent) -> Optional[TradeSetup]:
        self.check_session_boundary(bar)

        t = bar.timestamp.time()

        # 1. OR Formation Window: 09:30 to 09:45 EST
        # Bars at 09:30, 09:35, 09:40 define the 15-minute range
        if time(9, 30) <= t < time(9, 45):
            self.tracker.update_range_bar(bar.high, bar.low)
            return None

        # Lock the 15m range at 09:45 EST bar
        if not self.tracker.orb.is_formed:
            if time(9, 45) <= t <= time(10, 45):
                self.tracker.lock_range()
                min_range = float(self.config.get("min_orb_range_pts", 10.0))
                max_range = float(self.config.get("max_orb_range_pts", 90.0))
                if not (min_range <= self.tracker.orb.range_pts <= max_range):
                    return None
            else:
                return None

        # 2. Execution Window: 09:45 to 10:45 EST
        if not (time(9, 45) <= t <= time(10, 45)):
            return None

        # Maximum trades constraint
        if self.trades_this_session >= self.config.get("max_trades_per_day", 1) or self.trade_executed_today:
            return None

        # 3. Process bar through sweep state machine
        state, wick_extreme = self.tracker.process_monitoring_bar(
            bar_open=bar.open,
            bar_high=bar.high,
            bar_low=bar.low,
            bar_close=bar.close
        )

        buffer_ticks = float(self.config.get("buffer_ticks", 1))
        tick_size = 0.25
        buffer_pts = buffer_ticks * tick_size
        target_mode = self.config.get("target_mode", "range_midpoint")
        rr = float(self.config.get("risk_reward", 1.25))
        time_stop = int(self.config.get("time_stop_bars", 8))

        # Scenario A: BEAR TRAP CONFIRMED (Sweep below Low -> Re-entered above Low -> LONG)
        if state == SweepState.RE_ENTERED_BEAR_TRAP:
            entry_price = bar.close
            stop_loss = wick_extreme - buffer_pts
            risk_pts = entry_price - stop_loss

            if risk_pts <= 0.5:  # Invalid geometry
                return None

            # Determine Take Profit
            midpoint = self.tracker.orb.midpoint
            if target_mode == "range_midpoint" and midpoint > entry_price + (risk_pts * 0.75):
                take_profit = midpoint
            else:
                take_profit = entry_price + (risk_pts * rr)

            self.trades_this_session += 1
            self.trade_executed_today = True

            setup = TradeSetup(
                direction=OrderSide.LONG,
                order_type=OrderType.MARKET,
                stop_loss=round(stop_loss, 2),
                take_profit=round(take_profit, 2),
                time_stop_bars=time_stop,
                tag="bear_trap_long",
                metadata={
                    "orb_high": self.tracker.orb.high,
                    "orb_low": self.tracker.orb.low,
                    "orb_midpoint": self.tracker.orb.midpoint,
                    "sweep_wick_low": wick_extreme,
                    "extension_pts": self.tracker.orb.low - wick_extreme,
                    "risk_pts": risk_pts
                }
            )
            return setup

        # Scenario B: BULL TRAP CONFIRMED (Sweep above High -> Re-entered below High -> SHORT)
        elif state == SweepState.RE_ENTERED_BULL_TRAP:
            entry_price = bar.close
            stop_loss = wick_extreme + buffer_pts
            risk_pts = stop_loss - entry_price

            if risk_pts <= 0.5:  # Invalid geometry
                return None

            midpoint = self.tracker.orb.midpoint
            if target_mode == "range_midpoint" and midpoint < entry_price - (risk_pts * 0.75):
                take_profit = midpoint
            else:
                take_profit = entry_price - (risk_pts * rr)

            self.trades_this_session += 1
            self.trade_executed_today = True

            setup = TradeSetup(
                direction=OrderSide.SHORT,
                order_type=OrderType.MARKET,
                stop_loss=round(stop_loss, 2),
                take_profit=round(take_profit, 2),
                time_stop_bars=time_stop,
                tag="bull_trap_short",
                metadata={
                    "orb_high": self.tracker.orb.high,
                    "orb_low": self.tracker.orb.low,
                    "orb_midpoint": self.tracker.orb.midpoint,
                    "sweep_wick_high": wick_extreme,
                    "extension_pts": wick_extreme - self.tracker.orb.high,
                    "risk_pts": risk_pts
                }
            )
            return setup

        return None
