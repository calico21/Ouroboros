"""
Afternoon Trend Continuation Strategy for CME Globex Futures (MNQ).
Targets post-midday institutional rebalancing and MOC flows breaking out of the 11:30–13:30 EST bracket.
"""
from datetime import time
from typing import Optional
from src.core.events import BarEvent, TradeSetup
from src.core.enums import OrderSide, OrderType
from src.strategies.base import BaseStrategy
from src.strategies.afternoon_trend_continuation.indicators import MiddayConsolidationTracker


class AfternoonTrendContinuationStrategy(BaseStrategy):
    """
    Afternoon Trend Continuation Strategy (13:30 - 15:30 EST).
    Capitalizes on institutional directional expansion after midday lunch chop.
    Monitors 11:30-13:30 EST consolidation boundaries and enters on breakout with 1.5R target.
    """

    def __init__(self, config_overrides: Optional[dict] = None):
        super().__init__(config_overrides)
        self.tracker = MiddayConsolidationTracker()
        self.trades_this_session = 0

    def reset_session(self) -> None:
        self.tracker.reset()
        self.trades_this_session = 0

    def on_bar(self, bar: BarEvent) -> Optional[TradeSetup]:
        self.check_session_boundary(bar)

        t = bar.timestamp.time()

        # 1. Midday Consolidation Window: 11:30 to 13:30 EST
        if time(11, 30) <= t < time(13, 30):
            self.tracker.update_bar(bar.high, bar.low, bar.volume)
            return None

        # 2. Trigger Window: 13:30 to 15:15 EST
        if not (time(13, 30) <= t <= time(15, 15)):
            return None

        # Max trades per day constraint
        if self.trades_this_session >= self.config.get("max_trades_per_day", 1):
            return None

        # Consolidation range validity check
        if not self.tracker.is_valid_range:
            return None

        range_pts = self.tracker.range_pts
        min_pts = float(self.config.get("min_consolidation_pts", 10.0))
        max_pts = float(self.config.get("max_consolidation_pts", 80.0))
        if range_pts < min_pts or range_pts > max_pts:
            return None

        high_lvl = self.tracker.high
        low_lvl = self.tracker.low
        mid_lvl = self.tracker.midpoint

        stop_mode = self.config.get("stop_mode", "midpoint")
        rr = float(self.config.get("risk_reward", 1.50))
        time_stop = self.config.get("time_stop_bars", 12)

        # 3. Bullish Breakout above Midday High
        if bar.close > high_lvl:
            stop_loss = mid_lvl if stop_mode == "midpoint" else low_lvl
            risk_pts = bar.close - stop_loss
            if risk_pts <= 0:
                return None
            take_profit = bar.close + (risk_pts * rr)

            self.trades_this_session += 1
            return TradeSetup(
                direction=OrderSide.LONG,
                order_type=OrderType.MARKET,
                stop_loss=round(stop_loss, 2),
                take_profit=round(take_profit, 2),
                ttl_bars=self.config.get("ttl_bars", 8),
                time_stop_bars=time_stop,
                tag="PM_BREAKOUT_LONG",
                metadata={
                    "midday_high": high_lvl,
                    "midday_low": low_lvl,
                    "midpoint": mid_lvl,
                    "risk_pts": risk_pts
                }
            )

        # 4. Bearish Breakdown below Midday Low
        elif bar.close < low_lvl:
            stop_loss = mid_lvl if stop_mode == "midpoint" else high_lvl
            risk_pts = stop_loss - bar.close
            if risk_pts <= 0:
                return None
            take_profit = bar.close - (risk_pts * rr)

            self.trades_this_session += 1
            return TradeSetup(
                direction=OrderSide.SHORT,
                order_type=OrderType.MARKET,
                stop_loss=round(stop_loss, 2),
                take_profit=round(take_profit, 2),
                ttl_bars=self.config.get("ttl_bars", 8),
                time_stop_bars=time_stop,
                tag="PM_BREAKOUT_SHORT",
                metadata={
                    "midday_high": high_lvl,
                    "midday_low": low_lvl,
                    "midpoint": mid_lvl,
                    "risk_pts": risk_pts
                }
            )

        return None
