"""
Indicators for Opening Range Breakout strategy.
"""
from typing import Optional, Tuple


class OpeningRangeTracker:
    """Tracks Opening Range (OR) high and low during the initial session window."""

    def __init__(self):
        self.or_high: Optional[float] = None
        self.or_low: Optional[float] = None
        self.is_defined: bool = False

    def reset(self) -> None:
        self.or_high = None
        self.or_low = None
        self.is_defined = False

    def update(self, high: float, low: float) -> Tuple[Optional[float], Optional[float]]:
        if not self.is_defined:
            self.or_high = high
            self.or_low = low
            self.is_defined = True
        return self.or_high, self.or_low

    @property
    def midpoint(self) -> Optional[float]:
        if self.or_high is not None and self.or_low is not None:
            return (self.or_high + self.or_low) / 2.0
        return None

    @property
    def range_pts(self) -> float:
        if self.or_high is not None and self.or_low is not None:
            return self.or_high - self.or_low
        return 0.0
