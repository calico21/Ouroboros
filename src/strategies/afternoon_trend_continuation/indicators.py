"""
Indicators & State Trackers for Afternoon Trend Continuation Strategy.
Monitors midday consolidation range (11:30–13:30 EST), volume thresholds, and ATR filters.
"""
from typing import Optional, Tuple


class MiddayConsolidationTracker:
    """
    Tracks the institutional midday consolidation range between 11:30 and 13:30 EST.
    Calculates reference high, low, midpoint, and volume metrics.
    """

    def __init__(self):
        self.high: Optional[float] = None
        self.low: Optional[float] = None
        self.bars_count: int = 0
        self.cumulative_volume: float = 0.0
        self.is_finalized: bool = False

    def reset(self) -> None:
        self.high = None
        self.low = None
        self.bars_count = 0
        self.cumulative_volume = 0.0
        self.is_finalized = False

    def update_bar(self, high: float, low: float, volume: float) -> None:
        """Update midday consolidation boundaries with incoming 5m bar."""
        if self.high is None or high > self.high:
            self.high = high
        if self.low is None or low < self.low:
            self.low = low
        self.bars_count += 1
        self.cumulative_volume += volume

    def finalize(self) -> None:
        """Lock consolidation boundary once 13:30 EST is reached."""
        self.is_finalized = True

    @property
    def midpoint(self) -> Optional[float]:
        if self.high is not None and self.low is not None:
            return (self.high + self.low) / 2.0
        return None

    @property
    def range_pts(self) -> float:
        if self.high is not None and self.low is not None:
            return self.high - self.low
        return 0.0

    @property
    def is_valid_range(self) -> bool:
        return self.high is not None and self.low is not None and self.bars_count >= 6
