"""
Strategy 2: thin_eth_gap_failure (Sleeve A: ETH Structural Imbalances).
Fades uninformed overnight gaps built on thin, news-free ETH volume.
"""
from typing import Optional, Dict, Any, List
from datetime import time
from src.core.events import BarEvent, TradeSetup
from src.core.enums import OrderSide, OrderType
from src.strategies.base import BaseStrategy
from src.data.cme_session_clock import ensure_ny_tz


class ThinEthGapFailureStrategy(BaseStrategy):
    STRATEGY_NAME = "thin_eth_gap_failure"

    def __init__(self, config_overrides: Optional[Dict[str, Any]] = None):
        super().__init__(config_overrides)
        self.reset_session()

    def reset_session(self) -> None:
        self.eth_bars: List[BarEvent] = []
        self.or_bars: List[BarEvent] = []
        self.trade_taken_today = False
        self.gap_direction: Optional[int] = None  # +1 gap up, -1 gap down
        self.gap_size: float = 0.0

    def on_bar(self, bar: BarEvent) -> Optional[TradeSetup]:
        if self.trade_taken_today:
            return None

        et = ensure_ny_tz(bar.timestamp)
        t = et.time()

        # Collect ETH bars before 09:30
        if t < time(9, 30):
            self.eth_bars.append(bar)
            return None

        # Collect Opening Range bars 09:30 - 09:45 (first three 5m bars)
        if time(9, 30) <= t < time(9, 45):
            self.or_bars.append(bar)
            return None

        # Armed at 09:45 ET, evaluate until 11:00 ET
        if time(9, 45) <= t <= time(11, 0):
            if not self.or_bars or self.trade_taken_today:
                return None

            meta = bar.metadata or {}
            prev_close = meta.get("prev_day_close")
            atr = bar.atr_14 or meta.get("atr_20", 30.0)

            if prev_close is None or atr <= 0:
                return None

            rth_open = self.or_bars[0].open
            gap = rth_open - prev_close
            gap_abs = abs(gap)

            # Gate 1: Overnight gap magnitude in [0.25, 0.90] * ATR_20
            if not (0.25 * atr <= gap_abs <= 0.90 * atr):
                return None

            # Gate 2: ETH session volume < 40th percentile (or low ETH volume)
            eth_vol = sum(b.volume for b in self.eth_bars) if self.eth_bars else 5000
            vol_pct = meta.get("vol_pct_60", 35.0)
            if vol_pct > 55.0 and eth_vol > 50000:
                return None

            # OR high, low, midpoint
            or_high = max(b.high for b in self.or_bars)
            or_low = min(b.low for b in self.or_bars)
            or_mid = (or_high + or_low) / 2.0

            if gap > 0:
                # Gap Up: Expect failure to extend up -> Fade short to close gap
                # Gate 4: OR fails to extend strongly up
                last_or_bar = self.or_bars[-1]
                if last_or_bar.close < or_mid or bar.close < or_mid:
                    entry = or_mid
                    sl = min(entry + 35.0, or_high + 0.50)
                    risk = sl - entry
                    if risk > 35.0:
                        sl = entry + 35.0

                    tp = prev_close  # 100% gap fill (scale 50% at 50% gap fill)
                    self.trade_taken_today = True

                    return TradeSetup(
                        strategy_name=self.STRATEGY_NAME,
                        symbol=bar.symbol,
                        direction=OrderSide.SHORT,
                        order_type=OrderType.LIMIT,
                        limit_price=round(entry * 4) / 4,
                        stop_loss=round(sl * 4) / 4,
                        take_profit=round(tp * 4) / 4,
                        ttl_bars=6,
                        time_stop_bars=15,  # Flatten before 11:00 ET
                        protect_at_1r=True,
                        tag="THIN_ETH_GAP_FADE_SHORT"
                    )
            else:
                # Gap Down: Expect failure to extend down -> Fade long to fill gap
                last_or_bar = self.or_bars[-1]
                if last_or_bar.close > or_mid or bar.close > or_mid:
                    entry = or_mid
                    sl = max(entry - 35.0, or_low - 0.50)
                    risk = entry - sl
                    if risk > 35.0:
                        sl = entry - 35.0

                    tp = prev_close
                    self.trade_taken_today = True

                    return TradeSetup(
                        strategy_name=self.STRATEGY_NAME,
                        symbol=bar.symbol,
                        direction=OrderSide.LONG,
                        order_type=OrderType.LIMIT,
                        limit_price=round(entry * 4) / 4,
                        stop_loss=round(sl * 4) / 4,
                        take_profit=round(tp * 4) / 4,
                        ttl_bars=6,
                        time_stop_bars=15,
                        protect_at_1r=True,
                        tag="THIN_ETH_GAP_FADE_LONG"
                    )

        return None
