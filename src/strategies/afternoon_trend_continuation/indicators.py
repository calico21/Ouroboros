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


class ADXTracker:
    """
    Standard 14-period Average Directional Index (ADX) tracker.
    Used to verify directional momentum presence (> 18.0) before breakouts.
    """

    def __init__(self, period: int = 14):
        self.period = period
        self.prev_high: Optional[float] = None
        self.prev_low: Optional[float] = None
        self.prev_close: Optional[float] = None
        self.tr_list: list[float] = []
        self.plus_dm_list: list[float] = []
        self.minus_dm_list: list[float] = []
        self.dx_list: list[float] = []
        self.adx: float = 0.0

    def reset(self) -> None:
        self.prev_high = None
        self.prev_low = None
        self.prev_close = None
        self.tr_list = []
        self.plus_dm_list = []
        self.minus_dm_list = []
        self.dx_list = []
        self.adx = 0.0

    def update_bar(self, high: float, low: float, close: float) -> float:
        if self.prev_close is None:
            self.prev_high = high
            self.prev_low = low
            self.prev_close = close
            return 0.0

        tr = max(high - low, abs(high - self.prev_close), abs(low - self.prev_close))
        up_move = high - self.prev_high
        down_move = self.prev_low - low

        plus_dm = up_move if (up_move > down_move and up_move > 0) else 0.0
        minus_dm = down_move if (down_move > up_move and down_move > 0) else 0.0

        self.tr_list.append(tr)
        self.plus_dm_list.append(plus_dm)
        self.minus_dm_list.append(minus_dm)

        if len(self.tr_list) > self.period:
            self.tr_list.pop(0)
            self.plus_dm_list.pop(0)
            self.minus_dm_list.pop(0)

        sum_tr = sum(self.tr_list)
        if sum_tr > 0 and len(self.tr_list) >= self.period:
            plus_di = 100.0 * (sum(self.plus_dm_list) / sum_tr)
            minus_di = 100.0 * (sum(self.minus_dm_list) / sum_tr)
            di_sum = plus_di + minus_di
            dx = (100.0 * abs(plus_di - minus_di) / di_sum) if di_sum > 0 else 0.0
            self.dx_list.append(dx)
            if len(self.dx_list) > self.period:
                self.dx_list.pop(0)
            self.adx = sum(self.dx_list) / len(self.dx_list)

        self.prev_high = high
        self.prev_low = low
        self.prev_close = close
        return self.adx


class ATRTracker:
    """
    14-period True Range / ATR tracker.
    Monitors relative intraday expansion and identifies Quintile 5 crisis spikes.
    """

    def __init__(self, period: int = 14):
        self.period = period
        self.prev_close: Optional[float] = None
        self.tr_history: list[float] = []

    def reset(self) -> None:
        self.prev_close = None
        self.tr_history = []

    def update_bar(self, high: float, low: float, close: float) -> float:
        if self.prev_close is None:
            tr = high - low
        else:
            tr = max(high - low, abs(high - self.prev_close), abs(low - self.prev_close))
        self.prev_close = close
        self.tr_history.append(tr)
        if len(self.tr_history) > 100:
            self.tr_history.pop(0)
        return self.atr

    @property
    def atr(self) -> float:
        if not self.tr_history:
            return 10.0
        recent = self.tr_history[-self.period:]
        return sum(recent) / len(recent)

    def is_quintile_5_crisis(self) -> bool:
        # On 5m MNQ, an ATR > 35 points indicates extreme crisis volatility (VIX proxy >= 32)
        return self.atr >= 35.0
