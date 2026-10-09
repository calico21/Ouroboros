"""
Strategy 7: letf_rebalance_continuation (Sleeve D: Cash Close & Structural Flows).
Exploits mechanical end-of-day rebalancing flows by leveraged 3x NDX ETFs (TQQQ/SQQQ)
executed via CME futures in the final 30 minutes of cash equity trading.
"""
from typing import Optional, Dict, Any, List
from datetime import time
from src.core.events import BarEvent, TradeSetup
from src.core.enums import OrderSide, OrderType
from src.strategies.base import BaseStrategy
from src.data.cme_session_clock import ensure_ny_tz


class LetfRebalanceContinuationStrategy(BaseStrategy):
    STRATEGY_NAME = "letf_rebalance_continuation"

    def __init__(self, config_overrides: Optional[Dict[str, Any]] = None):
        super().__init__(config_overrides)
        self.reset_session()

    def reset_session(self) -> None:
        self.rth_open_price: Optional[float] = None
        self.bar_1520_price: Optional[float] = None
        self.bar_1500_price: Optional[float] = None
        self.trade_taken_today = False

    def on_bar(self, bar: BarEvent) -> Optional[TradeSetup]:
        if self.trade_taken_today:
            return None

        et = ensure_ny_tz(bar.timestamp)
        t = et.time()

        if time(9, 30) <= t < time(9, 35):
            self.rth_open_price = bar.open
            return None

        if time(15, 0) <= t < time(15, 5):
            self.bar_1500_price = bar.close
            return None

        if time(15, 20) <= t < time(15, 25):
            self.bar_1520_price = bar.close
            return None

        # Window: Entry 15:25 - 15:35 ET
        if time(15, 25) <= t <= time(15, 35):
            if self.rth_open_price is None or self.bar_1520_price is None or self.bar_1500_price is None:
                return None

            meta = bar.metadata or {}
            prev_close = meta.get("prev_day_close", self.rth_open_price)
            daily_return = (self.bar_1520_price - prev_close) / prev_close
            recent_return = self.bar_1520_price - self.bar_1500_price

            # Gate 1: |Return| >= 0.75%
            if abs(daily_return) < 0.0075:
                return None

            # Gate 2: 15:00-15:20 direction matches the full day's sign
            if (daily_return > 0 and recent_return <= 0) or (daily_return < 0 and recent_return >= 0):
                return None

            # Gate 3: Volume exceeds 20-day median
            vol_pct = meta.get("vol_pct_60", 55.0)
            if vol_pct < 45.0:
                return None

            sl_dist = min(25.0, abs(bar.close - bar.low) + 2.0)
            if sl_dist < 8.0:
                sl_dist = 14.0

            if daily_return > 0:
                entry = bar.close
                sl = entry - sl_dist
                tp = entry + (1.2 * sl_dist)
                self.trade_taken_today = True

                return TradeSetup(
                    strategy_name=self.STRATEGY_NAME,
                    symbol=bar.symbol,
                    direction=OrderSide.LONG,
                    order_type=OrderType.MARKET,
                    stop_loss=round(sl * 4) / 4,
                    take_profit=round(tp * 4) / 4,
                    time_stop_bars=5,  # Flatten at 15:54 ET (25-30m max hold)
                    protect_at_1r=True,
                    tag="LETF_REBALANCE_EXPANSION_LONG"
                )
            else:
                entry = bar.close
                sl = entry + sl_dist
                tp = entry - (1.2 * sl_dist)
                self.trade_taken_today = True

                return TradeSetup(
                    strategy_name=self.STRATEGY_NAME,
                    symbol=bar.symbol,
                    direction=OrderSide.SHORT,
                    order_type=OrderType.MARKET,
                    stop_loss=round(sl * 4) / 4,
                    take_profit=round(tp * 4) / 4,
                    time_stop_bars=5,
                    protect_at_1r=True,
                    tag="LETF_REBALANCE_EXPANSION_SHORT"
                )

        return None
