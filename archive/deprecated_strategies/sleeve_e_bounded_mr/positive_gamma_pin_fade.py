"""
Strategy 10: positive_gamma_pin_fade (Sleeve E: Bounded Intraday Mean Reversion).
Exploits dealer long-gamma hedging (buying dips, selling rallies) to fade excursions around the max-gamma pin strike.
"""
from typing import Optional, Dict, Any, List
from datetime import time
from src.core.events import BarEvent, TradeSetup
from src.core.enums import OrderSide, OrderType
from src.strategies.base import BaseStrategy
from src.data.cme_session_clock import ensure_ny_tz


class PositiveGammaPinFadeStrategy(BaseStrategy):
    STRATEGY_NAME = "positive_gamma_pin_fade"

    def __init__(self, config_overrides: Optional[Dict[str, Any]] = None):
        super().__init__(config_overrides)
        self.reset_session()

    def reset_session(self) -> None:
        self.pin_strike: Optional[float] = None
        self.trade_taken_today = False

    def on_bar(self, bar: BarEvent) -> Optional[TradeSetup]:
        if self.trade_taken_today:
            return None

        et = ensure_ny_tz(bar.timestamp)
        t = et.time()

        # Anchor max-gamma pin strike around 10:30 ET using VWAP / Session Open
        if time(10, 0) <= t < time(10, 30):
            meta = bar.metadata or {}
            self.pin_strike = meta.get("vwap", bar.close)
            return None

        # Window: 10:30 to 15:15 ET
        if time(10, 30) <= t <= time(15, 15):
            if self.pin_strike is None:
                return None

            meta = bar.metadata or {}
            atr = bar.atr_14 or meta.get("atr_20", 30.0)

            # Look for 0.35% - 0.50% excursion from pin strike
            excursion_pts = bar.close - self.pin_strike
            excursion_pct = excursion_pts / self.pin_strike

            # Fade upside excursion back to pin strike
            if 0.0035 <= excursion_pct <= 0.0065:
                entry = bar.close
                sl = entry + min(28.0, 0.4 * atr)
                tp = self.pin_strike
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
                    tag="GAMMA_PIN_UPPER_FADE_SHORT"
                )

            # Fade downside excursion back to pin strike
            elif -0.0065 <= excursion_pct <= -0.0035:
                entry = bar.close
                sl = entry - min(28.0, 0.4 * atr)
                tp = self.pin_strike
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
                    tag="GAMMA_PIN_LOWER_FADE_LONG"
                )

        return None
