"""
Strategy 5: ib_failed_extension_rotation (Sleeve C: Auction Profile & Value Area Structure).
Fades Initial Balance (09:30–10:30 ET) breakouts that lack institutional initiative volume.
"""
from typing import Optional, Dict, Any, List
from datetime import time
from src.core.events import BarEvent, TradeSetup
from src.core.enums import OrderSide, OrderType
from src.strategies.base import BaseStrategy
from src.data.cme_session_clock import ensure_ny_tz


class IbFailedExtensionRotationStrategy(BaseStrategy):
    STRATEGY_NAME = "ib_failed_extension_rotation"

    def __init__(self, config_overrides: Optional[Dict[str, Any]] = None):
        super().__init__(config_overrides)
        self.reset_session()

    def reset_session(self) -> None:
        self.ib_bars: List[BarEvent] = []
        self.ib_locked = False
        self.ib_high = 0.0
        self.ib_low = 0.0
        self.ib_mid = 0.0
        self.extended_high = False
        self.extended_low = False
        self.extension_extreme = 0.0
        self.trade_taken_today = False

    def on_bar(self, bar: BarEvent) -> Optional[TradeSetup]:
        if self.trade_taken_today:
            return None

        et = ensure_ny_tz(bar.timestamp)
        t = et.time()

        # Collect 60m Initial Balance: 09:30 to 10:30 ET
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
            meta = bar.metadata or {}
            atr = bar.atr_14 or meta.get("atr_20", 30.0)
            ib_range = self.ib_high - self.ib_low

            # Gate 3: IB range in [0.35, 0.80] * ATR_20
            if not (0.35 * atr <= ib_range <= 0.85 * atr):
                return None

            vol_pct = meta.get("vol_pct_60", 45.0)

            # Check High extension and failure
            if bar.high >= self.ib_high + 5.0:
                self.extended_high = True
                self.extension_extreme = max(self.extension_extreme, bar.high)

            # Fade short when 5m bar closes back inside IB High
            if self.extended_high and bar.close < self.ib_high and vol_pct < 60.0:
                entry = bar.close
                sl = min(entry + 35.0, self.extension_extreme + 0.50)
                tp = self.ib_mid
                self.trade_taken_today = True

                return TradeSetup(
                    strategy_name=self.STRATEGY_NAME,
                    symbol=bar.symbol,
                    direction=OrderSide.SHORT,
                    order_type=OrderType.MARKET,
                    stop_loss=round(sl * 4) / 4,
                    take_profit=round(tp * 4) / 4,
                    time_stop_bars=30,  # 13:30 ET hard stop
                    protect_at_1r=True,
                    tag="IB_FAILED_HIGH_ROTATION_SHORT"
                )

            # Check Low extension and failure
            if bar.low <= self.ib_low - 5.0:
                self.extended_low = True
                self.extension_extreme = min(self.extension_extreme or 999999.0, bar.low)

            # Fade long when 5m bar closes back inside IB Low
            if self.extended_low and bar.close > self.ib_low and vol_pct < 60.0:
                entry = bar.close
                sl = max(entry - 35.0, self.extension_extreme - 0.50)
                tp = self.ib_mid
                self.trade_taken_today = True

                return TradeSetup(
                    strategy_name=self.STRATEGY_NAME,
                    symbol=bar.symbol,
                    direction=OrderSide.LONG,
                    order_type=OrderType.MARKET,
                    stop_loss=round(sl * 4) / 4,
                    take_profit=round(tp * 4) / 4,
                    time_stop_bars=30,
                    protect_at_1r=True,
                    tag="IB_FAILED_LOW_ROTATION_LONG"
                )

        return None
