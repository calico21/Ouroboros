"""
Opening Range Breakout 5M Binary Strategy for Intraday CME Futures.
Folder-isolated strategy implementation adhering strictly to BaseStrategy interface.
"""
from datetime import time
from typing import Optional
from src.core.events import BarEvent, TradeSetup
from src.core.enums import OrderSide, OrderType
from src.strategies.base import BaseStrategy
from src.strategies.orb_5m_binary.indicators import OpeningRangeTracker


class Orb5mBinaryStrategy(BaseStrategy):
    """
    Opening Range Breakout 5-Minute Binary Strategy.
    Defines the first 5m bar range (09:30 - 09:35 EST) as reference bracket.
    Enters on breakout close outside the range with midpoint stop and 2.0R target.
    """

    def __init__(self, config_overrides: Optional[dict] = None):
        super().__init__(config_overrides)
        self.tracker = OpeningRangeTracker()
        self.trades_this_session = 0
        self.or_formed = False

    def reset_session(self) -> None:
        self.tracker.reset()
        self.trades_this_session = 0
        self.or_formed = False

    def on_bar(self, bar: BarEvent) -> Optional[TradeSetup]:
        self.check_session_boundary(bar)

        t = bar.timestamp.time()
        # Session start check: bar at 09:30 (representing 09:30 - 09:35) defines OR
        if t == time(9, 30) or (t.hour == 9 and t.minute == 30):
            self.tracker.update(bar.high, bar.low)
            self.or_formed = True
            return None

        # Only trade during allowed window
        if not self.or_formed or self.trades_this_session >= self.config.get("max_trades_per_session", 1):
            return None

        if t >= time(11, 30):
            return None

        or_range = self.tracker.range_pts
        if or_range < self.config.get("min_range_pts", 10.0) or or_range > self.config.get("max_range_pts", 120.0):
            return None

        or_high = self.tracker.or_high
        or_low = self.tracker.or_low
        mid = self.tracker.midpoint

        target_r = self.config.get("target_r_multiple", 2.0)
        stop_type = self.config.get("stop_type", "midpoint")

        # Bullish Breakout
        if bar.close > or_high:
            stop_loss = mid if stop_type == "midpoint" else or_low
            risk = bar.close - stop_loss
            if risk <= 0:
                return None
            take_profit = bar.close + (risk * target_r)

            self.trades_this_session += 1
            return TradeSetup(
                direction=OrderSide.LONG,
                order_type=OrderType.MARKET,
                stop_loss=round(stop_loss, 2),
                take_profit=round(take_profit, 2),
                ttl_bars=self.config.get("ttl_bars", 6),
                tag=self.config.get("tag", "ORB_5M_LONG"),
                metadata={"or_high": or_high, "or_low": or_low, "risk_pts": risk}
            )

        # Bearish Breakdown
        elif bar.close < or_low:
            stop_loss = mid if stop_type == "midpoint" else or_high
            risk = stop_loss - bar.close
            if risk <= 0:
                return None
            take_profit = bar.close - (risk * target_r)

            self.trades_this_session += 1
            return TradeSetup(
                direction=OrderSide.SHORT,
                order_type=OrderType.MARKET,
                stop_loss=round(stop_loss, 2),
                take_profit=round(take_profit, 2),
                ttl_bars=self.config.get("ttl_bars", 6),
                tag=self.config.get("tag", "ORB_5M_SHORT"),
                metadata={"or_high": or_high, "or_low": or_low, "risk_pts": risk}
            )

        return None
