"""
Strategy 9: midday_equilibrium_fade (Sleeve E: Bounded Intraday Mean Reversion).
Fades lunchtime liquidity vacuum noise between 11:45 and 13:45 ET when Europe has closed
and directional momentum is exhausted.
"""
from typing import Optional, Dict, Any, List
from datetime import time
from src.core.events import BarEvent, TradeSetup
from src.core.enums import OrderSide, OrderType
from src.strategies.base import BaseStrategy
from src.data.cme_session_clock import ensure_ny_tz


class MiddayEquilibriumFadeStrategy(BaseStrategy):
    STRATEGY_NAME = "midday_equilibrium_fade"

    def __init__(self, config_overrides: Optional[Dict[str, Any]] = None):
        super().__init__(config_overrides)
        self.reset_session()

    def reset_session(self) -> None:
        self.morning_bars: List[BarEvent] = []
        self.trade_taken_today = False

    def on_bar(self, bar: BarEvent) -> Optional[TradeSetup]:
        if self.trade_taken_today:
            return None

        et = ensure_ny_tz(bar.timestamp)
        t = et.time()

        # Collect 09:30 to 11:30 ET morning bars to assess range
        if time(9, 30) <= t < time(11, 30):
            self.morning_bars.append(bar)
            return None

        # Window: 11:45 to 13:45 ET
        if time(11, 45) <= t <= time(13, 45):
            if not self.morning_bars:
                return None

            meta = bar.metadata or {}
            atr = bar.atr_14 or meta.get("atr_20", 30.0)

            # Gate 1: Morning range < 0.60 * ATR_20 (compressed morning)
            m_high = max(b.high for b in self.morning_bars)
            m_low = min(b.low for b in self.morning_bars)
            m_range = m_high - m_low

            if m_range > 0.65 * atr:
                return None

            vwap = meta.get("vwap", bar.close)
            vwap_upper = meta.get("vwap_upper_2", vwap + 15.0)
            vwap_lower = meta.get("vwap_lower_2", vwap - 15.0)

            # Excursion to VWAP +2 sigma -> Fade short back to VWAP
            if bar.high >= vwap_upper and bar.close >= vwap_upper - 2.0:
                entry = bar.close
                sl = entry + min(20.0, max(10.0, 0.3 * (entry - vwap)))
                tp = vwap
                self.trade_taken_today = True

                return TradeSetup(
                    strategy_name=self.STRATEGY_NAME,
                    symbol=bar.symbol,
                    direction=OrderSide.SHORT,
                    order_type=OrderType.MARKET,
                    stop_loss=round(sl * 4) / 4,
                    take_profit=round(tp * 4) / 4,
                    time_stop_bars=20,  # Exit before 14:00 ET
                    protect_at_1r=True,
                    tag="MIDDAY_EQUILIBRIUM_UPPER_FADE_SHORT"
                )

            # Excursion to VWAP -2 sigma -> Fade long back to VWAP
            elif bar.low <= vwap_lower and bar.close <= vwap_lower + 2.0:
                entry = bar.close
                sl = entry - min(20.0, max(10.0, 0.3 * (vwap - entry)))
                tp = vwap
                self.trade_taken_today = True

                return TradeSetup(
                    strategy_name=self.STRATEGY_NAME,
                    symbol=bar.symbol,
                    direction=OrderSide.LONG,
                    order_type=OrderType.MARKET,
                    stop_loss=round(sl * 4) / 4,
                    take_profit=round(tp * 4) / 4,
                    time_stop_bars=20,
                    protect_at_1r=True,
                    tag="MIDDAY_EQUILIBRIUM_LOWER_FADE_LONG"
                )

        return None
