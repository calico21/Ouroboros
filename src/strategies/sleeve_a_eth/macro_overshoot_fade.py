"""
Strategy 1: macro_overshoot_fade (Sleeve A: ETH Structural Imbalances).
Fades liquidity vacuum stop-runs at 08:30 ET economic releases.
"""
from typing import Optional, Dict, Any
from datetime import time
from src.core.events import BarEvent, TradeSetup
from src.core.enums import OrderSide, OrderType
from src.strategies.base import BaseStrategy
from src.data.cme_session_clock import ensure_ny_tz


class MacroOvershootFadeStrategy(BaseStrategy):
    STRATEGY_NAME = "macro_overshoot_fade"

    def __init__(self, config_overrides: Optional[Dict[str, Any]] = None):
        super().__init__(config_overrides)
        self.reset_session()

    def reset_session(self) -> None:
        self.impulse_bar: Optional[BarEvent] = None
        self.reversal_bar: Optional[BarEvent] = None
        self.trade_taken_today = False
        self.catalyst_triggered = False
        self.pre_print_vwap: Optional[float] = None

    def on_bar(self, bar: BarEvent) -> Optional[TradeSetup]:
        if self.trade_taken_today:
            return None

        et = ensure_ny_tz(bar.timestamp)
        t = et.time()

        # Track pre-print VWAP before 08:30 ET
        if t < time(8, 30):
            meta = bar.metadata or {}
            self.pre_print_vwap = meta.get("vwap", bar.close)
            return None

        # Capture 08:30–08:35 ET impulse bar
        if time(8, 30) <= t < time(8, 35):
            self.impulse_bar = bar
            return None

        # Analyze 08:35–08:40 ET reaction bar
        if time(8, 35) <= t < time(8, 40):
            if self.impulse_bar is None:
                return None
            self.reversal_bar = bar

            atr = bar.atr_14 or (bar.metadata.get("atr_20", 30.0) if bar.metadata else 30.0)
            impulse_range = self.impulse_bar.high - self.impulse_bar.low

            # Gate 1 & 3: 08:30-08:35 bar range >= 0.40 * ATR_20
            if impulse_range < 0.40 * atr:
                return None

            # Gate 4: 08:35-08:40 fails to extend extreme (inside bar or rejection wick)
            imp_up = self.impulse_bar.close > self.impulse_bar.open
            if imp_up:
                # Upward impulse -> Looking to fade short
                failed_to_extend = bar.high <= self.impulse_bar.high + 1.0 or bar.close < bar.open
                if not failed_to_extend:
                    return None

                # 38.2% Fibonacci retrace entry
                entry_level = self.impulse_bar.high - 0.382 * impulse_range
                sl = self.impulse_bar.high + 0.50  # 2 ticks
                risk = sl - entry_level
                if risk > 40.0:
                    return None  # Skip if risk exceeds 40 pts

                target = entry_level - (0.50 * impulse_range)
                self.trade_taken_today = True

                return TradeSetup(
                    strategy_name=self.STRATEGY_NAME,
                    symbol=bar.symbol,
                    direction=OrderSide.SHORT,
                    order_type=OrderType.LIMIT,
                    limit_price=round(entry_level * 4) / 4,
                    stop_loss=round(sl * 4) / 4,
                    take_profit=round(target * 4) / 4,
                    ttl_bars=3,            # Valid 08:35 - 08:50
                    time_stop_bars=5,      # Hard exit around 09:00 ET
                    protect_at_1r=True,
                    tag="MACRO_OVERSHOOT_FADE_SHORT"
                )
            else:
                # Downward impulse -> Looking to fade long
                failed_to_extend = bar.low >= self.impulse_bar.low - 1.0 or bar.close > bar.open
                if not failed_to_extend:
                    return None

                entry_level = self.impulse_bar.low + 0.382 * impulse_range
                sl = self.impulse_bar.low - 0.50  # 2 ticks
                risk = entry_level - sl
                if risk > 40.0:
                    return None

                target = entry_level + (0.50 * impulse_range)
                self.trade_taken_today = True

                return TradeSetup(
                    strategy_name=self.STRATEGY_NAME,
                    symbol=bar.symbol,
                    direction=OrderSide.LONG,
                    order_type=OrderType.LIMIT,
                    limit_price=round(entry_level * 4) / 4,
                    stop_loss=round(sl * 4) / 4,
                    take_profit=round(target * 4) / 4,
                    ttl_bars=3,
                    time_stop_bars=5,
                    protect_at_1r=True,
                    tag="MACRO_OVERSHOOT_FADE_LONG"
                )

        return None
