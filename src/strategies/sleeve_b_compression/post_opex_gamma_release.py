"""
Strategy 4: post_opex_gamma_release (Sleeve B: Compression & Volatility Expansion).
Captures trend expansion as monthly OpEx removes long-gamma dealer pinning.
"""
from typing import Optional, Dict, Any, List
from datetime import time, date
from src.core.events import BarEvent, TradeSetup
from src.core.enums import OrderSide, OrderType
from src.strategies.base import BaseStrategy
from src.data.cme_session_clock import ensure_ny_tz


def is_post_opex_window(cal_date: date) -> bool:
    """
    Monthly US equity options expire on the 3rd Friday of the month.
    This strategy targets Monday or Tuesday following that 3rd Friday.
    """
    # 3rd Friday must fall between day 15 and 21
    # Post-OpEx Monday falls between day 18 and 24; Tuesday between 19 and 25
    weekday = cal_date.weekday()
    day = cal_date.day
    if weekday == 0 and (18 <= day <= 24):
        return True
    if weekday == 1 and (19 <= day <= 25):
        return True
    return False


class PostOpexGammaReleaseStrategy(BaseStrategy):
    STRATEGY_NAME = "post_opex_gamma_release"

    def __init__(self, config_overrides: Optional[Dict[str, Any]] = None):
        super().__init__(config_overrides)
        self.reset_session()

    def reset_session(self) -> None:
        self.ib_bars: List[BarEvent] = []
        self.trade_taken_today = False
        self.ib_locked = False
        self.ib_high = 0.0
        self.ib_low = 0.0
        self.ib_mid = 0.0

    def on_bar(self, bar: BarEvent) -> Optional[TradeSetup]:
        if self.trade_taken_today:
            return None

        et = ensure_ny_tz(bar.timestamp)
        t = et.time()

        # Gate 1: Session is 1-2 business days post monthly options expiration
        # (Relax slightly to include bi-weekly opex or high gamma compression sessions for sample size)
        cal_date = et.date()
        is_opex = is_post_opex_window(cal_date)
        # Also qualify if 5-day / 20-day realized range compression occurs
        meta = bar.metadata or {}
        atr = bar.atr_14 or meta.get("atr_20", 30.0)
        prev_range = meta.get("prev_day_range", 50.0)

        # Collect 60-minute Initial Balance: 09:30 to 10:30 ET
        if time(9, 30) <= t < time(10, 30):
            self.ib_bars.append(bar)
            return None

        # Lock IB at 10:30 ET
        if not self.ib_locked and self.ib_bars:
            self.ib_high = max(b.high for b in self.ib_bars)
            self.ib_low = min(b.low for b in self.ib_bars)
            self.ib_mid = (self.ib_high + self.ib_low) / 2.0
            self.ib_locked = True

        # Window: 10:30 to 13:00 ET
        if self.ib_locked and time(10, 30) <= t <= time(13, 0):
            # Gate 2: realized range compression ratio < 0.85
            if prev_range > 0.85 * atr and not is_opex:
                return None

            vwap = meta.get("vwap", bar.close)
            vwap_slope_up = bar.close > vwap

            # Breakout beyond IB
            if bar.high > self.ib_high + 1.0 and vwap_slope_up:
                entry = bar.close
                sl = max(entry - 40.0, self.ib_mid)
                risk = entry - sl
                tp = entry + 1.5 * risk
                self.trade_taken_today = True

                return TradeSetup(
                    strategy_name=self.STRATEGY_NAME,
                    symbol=bar.symbol,
                    direction=OrderSide.LONG,
                    order_type=OrderType.MARKET,
                    stop_loss=round(sl * 4) / 4,
                    take_profit=round(tp * 4) / 4,
                    time_stop_bars=40,  # 14:30 ET time stop
                    protect_at_1r=True,
                    tag="POST_OPEX_GAMMA_RELEASE_LONG"
                )
            elif bar.low < self.ib_low - 1.0 and not vwap_slope_up:
                entry = bar.close
                sl = min(entry + 40.0, self.ib_mid)
                risk = sl - entry
                tp = entry - 1.5 * risk
                self.trade_taken_today = True

                return TradeSetup(
                    strategy_name=self.STRATEGY_NAME,
                    symbol=bar.symbol,
                    direction=OrderSide.SHORT,
                    order_type=OrderType.MARKET,
                    stop_loss=round(sl * 4) / 4,
                    take_profit=round(tp * 4) / 4,
                    time_stop_bars=40,
                    protect_at_1r=True,
                    tag="POST_OPEX_GAMMA_RELEASE_SHORT"
                )

        return None
