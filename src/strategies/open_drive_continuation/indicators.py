"""
Indicators for Open Drive Continuation Strategy.
Detects institutional opening auction momentum, conviction ratios, and retracement levels.
"""
from typing import Optional, Tuple


class OpenDriveDetector:
    """Tracks the initial session open drive impulse."""

    def __init__(self, conviction_threshold: float = 0.65, min_drive_points: float = 20.0):
        self.conviction_threshold = conviction_threshold
        self.min_drive_points = min_drive_points
        self.reset()

    def reset(self) -> None:
        self.drive_detected: bool = False
        self.direction: Optional[str] = None  # 'BULLISH' or 'BEARISH'
        self.drive_high: Optional[float] = None
        self.drive_low: Optional[float] = None
        self.drive_open: Optional[float] = None
        self.drive_close: Optional[float] = None

    def evaluate_open_bar(self, open_p: float, high: float, low: float, close: float) -> bool:
        rng = high - low
        body = abs(close - open_p)
        if rng < self.min_drive_points:
            return False

        conviction = body / rng if rng > 0 else 0

        if conviction >= self.conviction_threshold:
            self.drive_detected = True
            self.drive_high = high
            self.drive_low = low
            self.drive_open = open_p
            self.drive_close = close
            self.direction = "BULLISH" if close > open_p else "BEARISH"
            return True
        return False

    @property
    def retracement_level_50(self) -> Optional[float]:
        if self.drive_high is not None and self.drive_low is not None:
            return (self.drive_high + self.drive_low) / 2.0
        return None
