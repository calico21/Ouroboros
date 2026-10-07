"""
VWAP and Standard Deviation Bands Indicator.
Calculates session-anchored Volume Weighted Average Price and dispersion bands.
"""
import math
from typing import Optional, Tuple


class SessionVWAPTracker:
    """Session-anchored VWAP and standard deviation bands calculator."""

    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self.cum_pv: float = 0.0
        self.cum_volume: float = 0.0
        self.cum_p2v: float = 0.0
        self.vwap: Optional[float] = None
        self.std_dev: float = 0.0

    def update(self, high: float, low: float, close: float, volume: float) -> Tuple[Optional[float], float]:
        typical_price = (high + low + close) / 3.0
        if volume <= 0:
            volume = 1.0

        self.cum_pv += typical_price * volume
        self.cum_volume += volume
        self.cum_p2v += (typical_price ** 2) * volume

        if self.cum_volume > 0:
            self.vwap = self.cum_pv / self.cum_volume
            variance = max(0.0, (self.cum_p2v / self.cum_volume) - (self.vwap ** 2))
            self.std_dev = math.sqrt(variance)

        return self.vwap, self.std_dev
