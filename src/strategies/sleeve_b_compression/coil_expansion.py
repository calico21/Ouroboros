"""
Strategy 3: coil_expansion (Sleeve B: Compression & Volatility Expansion).
Captures breakout expansion following multi-day volatility compression.
"""
from typing import Optional, Dict, Any, List
from datetime import time
from src.core.events import BarEvent, TradeSetup
from src.core.enums import OrderSide, OrderType
from src.strategies.base import BaseStrategy
from src.data.cme_session_clock import ensure_ny_tz


class CoilExpansionStrategy(BaseStrategy):
    STRATEGY_NAME = "coil_expansion"

    def __init__(self, config_overrides: Optional[Dict[str, Any]] = None):
        super().__init__(config_overrides)
        self.reset_session()

    def reset_session(self) -> None:
        self.eth_bars: List[BarEvent] = []
        self.trade_taken_today = False
        self.bracket_armed = False

    def on_bar(self, bar: BarEvent) -> Optional[TradeSetup]:
        if self.trade_taken_today:
            return None

        et = ensure_ny_tz(bar.timestamp)
        t = et.time()

        # Collect ETH bars for overnight range
        if t < time(9, 30):
            self.eth_bars.append(bar)
            return None

        # Window: 09:45 - 12:30 ET
        if time(9, 45) <= t <= time(12, 30):
            meta = bar.metadata or {}
            atr = bar.atr_14 or meta.get("atr_20", 30.0)
            prev_range = meta.get("prev_day_range", 50.0)
            is_inside = meta.get("is_inside_day", False)
            is_nr7 = meta.get("is_nr7", False)

            # Gate 1: Prior-day range < 0.55 * ATR_20 AND (Inside Day or NR7)
            if not (prev_range < 0.55 * atr and (is_inside or is_nr7 or prev_range < 0.45 * atr)):
                return None

            # Gate 3: Overnight ETH range < 0.40 * ATR_20
            if self.eth_bars:
                eth_range = max(b.high for b in self.eth_bars) - min(b.low for b in self.eth_bars)
                if eth_range > 0.40 * atr:
                    return None

            prev_high = meta.get("prev_day_high")
            prev_low = meta.get("prev_day_low")
            if prev_high is None or prev_low is None:
                return None

            # Execution: Buy-stop at prior-day High + 3 ticks, Sell-stop at prior-day Low - 3 ticks
            # On 5m bar, check if bar breaks out
            buy_trigger = prev_high + 0.75
            sell_trigger = prev_low - 0.75
            stop_distance = min(0.5 * prev_range, 35.0)
            if stop_distance < 8.0:
                stop_distance = 12.0

            if bar.high >= buy_trigger and bar.close > prev_high:
                entry = bar.close
                sl = entry - stop_distance
                tp = entry + (1.5 * stop_distance)
                self.trade_taken_today = True

                return TradeSetup(
                    strategy_name=self.STRATEGY_NAME,
                    symbol=bar.symbol,
                    direction=OrderSide.LONG,
                    order_type=OrderType.MARKET,
                    stop_loss=round(sl * 4) / 4,
                    take_profit=round(tp * 4) / 4,
                    time_stop_bars=50,  # Flatten around 14:30 ET
                    protect_at_1r=True,
                    tag="COIL_EXPANSION_BREAKOUT_LONG"
                )
            elif bar.low <= sell_trigger and bar.close < prev_low:
                entry = bar.close
                sl = entry + stop_distance
                tp = entry - (1.5 * stop_distance)
                self.trade_taken_today = True

                return TradeSetup(
                    strategy_name=self.STRATEGY_NAME,
                    symbol=bar.symbol,
                    direction=OrderSide.SHORT,
                    order_type=OrderType.MARKET,
                    stop_loss=round(sl * 4) / 4,
                    take_profit=round(tp * 4) / 4,
                    time_stop_bars=50,
                    protect_at_1r=True,
                    tag="COIL_EXPANSION_BREAKOUT_SHORT"
                )

        return None
