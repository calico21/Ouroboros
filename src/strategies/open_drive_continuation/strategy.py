"""
Open Drive Continuation Strategy for Intraday CME Futures.
Identifies high-conviction directional imbalance out of the 09:30 open and trades continuation.
"""
from datetime import time
from typing import Optional
from src.core.events import BarEvent, TradeSetup
from src.core.enums import OrderSide, OrderType
from src.strategies.base import BaseStrategy
from src.strategies.open_drive_continuation.indicators import OpenDriveDetector


class OpenDriveContinuationStrategy(BaseStrategy):
    """
    Open Drive Continuation Strategy.
    Detects institutional aggression on the open bar (09:30 EST),
    awaits a shallow test/flag, and enters on continuation toward 2.2R.
    """

    def __init__(self, config_overrides: Optional[dict] = None):
        super().__init__(config_overrides)
        self.detector = OpenDriveDetector(
            conviction_threshold=self.config.get("conviction_threshold", 0.65),
            min_drive_points=self.config.get("min_drive_points", 15.0)
        )
        self.bars_since_drive = 0
        self.has_entered = False

    def reset_session(self) -> None:
        self.detector.reset()
        self.bars_since_drive = 0
        self.has_entered = False

    def on_bar(self, bar: BarEvent) -> Optional[TradeSetup]:
        self.check_session_boundary(bar)

        t = bar.timestamp.time()
        # Bar 1 at 09:30 EST
        if t == time(9, 30) or (t.hour == 9 and t.minute == 30):
            self.detector.evaluate_open_bar(bar.open, bar.high, bar.low, bar.close)
            self.bars_since_drive = 0
            return None

        if not self.detector.drive_detected or self.has_entered:
            return None

        self.bars_since_drive += 1
        if self.bars_since_drive > self.config.get("entry_timeout_bars", 6):
            return None

        direction = self.detector.direction
        half_lvl = self.detector.retracement_level_50
        target_r = self.config.get("target_r_multiple", 2.2)

        # Bullish Continuation
        if direction == "BULLISH":
            # Condition: pulled back near 50% or testing above drive_high
            if bar.close > self.detector.drive_close:
                stop_loss = half_lvl if self.config.get("stop_type") == "half_drive" else self.detector.drive_low
                risk = bar.close - stop_loss
                if risk <= 0:
                    return None
                take_profit = bar.close + (risk * target_r)

                self.has_entered = True
                return TradeSetup(
                    direction=OrderSide.LONG,
                    order_type=OrderType.MARKET,
                    stop_loss=round(stop_loss, 2),
                    take_profit=round(take_profit, 2),
                    ttl_bars=6,
                    tag="OPEN_DRIVE_LONG"
                )

        # Bearish Continuation
        elif direction == "BEARISH":
            if bar.close < self.detector.drive_close:
                stop_loss = half_lvl if self.config.get("stop_type") == "half_drive" else self.detector.drive_high
                risk = stop_loss - bar.close
                if risk <= 0:
                    return None
                take_profit = bar.close - (risk * target_r)

                self.has_entered = True
                return TradeSetup(
                    direction=OrderSide.SHORT,
                    order_type=OrderType.MARKET,
                    stop_loss=round(stop_loss, 2),
                    take_profit=round(take_profit, 2),
                    ttl_bars=6,
                    tag="OPEN_DRIVE_SHORT"
                )

        return None
