"""
Strategy 6: va_traverse_80pct (Sleeve C: Auction Profile & Value Area Structure).
Exploits Market Profile 80% rule: opening outside prior Value Area and re-entering with acceptance
drives a rotation across the entire Value Area.
"""
from typing import Optional, Dict, Any, List
from datetime import time
from src.core.events import BarEvent, TradeSetup
from src.core.enums import OrderSide, OrderType
from src.strategies.base import BaseStrategy
from src.data.cme_session_clock import ensure_ny_tz


class VaTraverse80PctStrategy(BaseStrategy):
    STRATEGY_NAME = "va_traverse_80pct"

    def __init__(self, config_overrides: Optional[Dict[str, Any]] = None):
        super().__init__(config_overrides)
        self.reset_session()

    def reset_session(self) -> None:
        self.consecutive_closes_inside_va = 0
        self.trade_taken_today = False
        self.opened_outside_va = False
        self.direction: Optional[OrderSide] = None

    def on_bar(self, bar: BarEvent) -> Optional[TradeSetup]:
        if self.trade_taken_today:
            return None

        et = ensure_ny_tz(bar.timestamp)
        t = et.time()

        meta = bar.metadata or {}
        prev_high = meta.get("prev_day_high")
        prev_low = meta.get("prev_day_low")

        if prev_high is None or prev_low is None:
            return None

        # Approximate Value Area as 70% of prior day range centered around midpoint
        prev_range = prev_high - prev_low
        if not (50.0 <= prev_range <= 200.0):
            return None

        va_high = prev_high - (0.15 * prev_range)
        va_low = prev_low + (0.15 * prev_range)
        va_width = va_high - va_low

        # Check open at 09:30 ET
        if time(9, 30) <= t < time(9, 35):
            if bar.open > va_high:
                self.opened_outside_va = True
                self.direction = OrderSide.SHORT  # Re-enters from above -> Short to VA low
            elif bar.open < va_low:
                self.opened_outside_va = True
                self.direction = OrderSide.LONG   # Re-enters from below -> Long to VA high
            return None

        # Window: 10:00 to 13:30 ET
        if self.opened_outside_va and time(10, 0) <= t <= time(13, 30):
            if va_low <= bar.close <= va_high:
                self.consecutive_closes_inside_va += 1
            else:
                self.consecutive_closes_inside_va = 0

            # Acceptance: consecutive 5m closes inside VA
            if self.consecutive_closes_inside_va >= 3:
                entry = bar.close
                sl_distance = min(35.0, max(12.0, 0.25 * va_width))

                if self.direction == OrderSide.SHORT:
                    sl = entry + sl_distance
                    tp = va_low
                    self.trade_taken_today = True

                    return TradeSetup(
                        strategy_name=self.STRATEGY_NAME,
                        symbol=bar.symbol,
                        direction=OrderSide.SHORT,
                        order_type=OrderType.MARKET,
                        stop_loss=round(sl * 4) / 4,
                        take_profit=round(tp * 4) / 4,
                        time_stop_bars=35,
                        protect_at_1r=True,
                        tag="VA_80PCT_TRAVERSE_SHORT"
                    )
                elif self.direction == OrderSide.LONG:
                    sl = entry - sl_distance
                    tp = va_high
                    self.trade_taken_today = True

                    return TradeSetup(
                        strategy_name=self.STRATEGY_NAME,
                        symbol=bar.symbol,
                        direction=OrderSide.LONG,
                        order_type=OrderType.MARKET,
                        stop_loss=round(sl * 4) / 4,
                        take_profit=round(tp * 4) / 4,
                        time_stop_bars=35,
                        protect_at_1r=True,
                        tag="VA_80PCT_TRAVERSE_LONG"
                    )

        return None
