"""
Indicators & Range Analytics for Opening Range Breakout (ORB) Strategy.
Tracks Opening Range geometry, midpoint levels, target geometries, 
time-of-day rolling Relative Volume (RVOL), and candle breakout quality (Clutch Factor).
"""
from datetime import time, datetime, date
from typing import Optional, Tuple, Dict, List
import statistics


class TimeBucketVolumeTracker:
    """
    Tracks historical intraday volume by time bucket (e.g. 09:45 EST) across trading days
    to compute Relative Volume (RVOL) against a rolling 15-day median baseline without lookahead bias.
    """

    def __init__(self, lookback_days: int = 15):
        self.lookback_days = lookback_days
        # Maps time -> list of historical volumes from prior days (most recent last, maxlen=lookback_days)
        self.history: Dict[time, List[float]] = {}
        # Stores volumes recorded in the current active session
        self._current_day_volumes: Dict[time, float] = {}
        self._current_date: Optional[date] = None

    def on_bar(self, bar_time: datetime, volume: float) -> None:
        """
        Record volume for a bar, handling session date roll transitions.
        When a new date is encountered, commit yesterday's recorded volumes into rolling history.
        """
        b_date = bar_time.date() if isinstance(bar_time, datetime) else None
        b_time = bar_time.time() if isinstance(bar_time, datetime) else bar_time

        if self._current_date is not None and b_date is not None and b_date != self._current_date:
            # End of previous day: commit day's volumes into historical rolling window
            self.commit_session()
            self._current_date = b_date

        if self._current_date is None and b_date is not None:
            self._current_date = b_date

        # Store today's volume for this bucket
        self._current_day_volumes[b_time] = volume

    def commit_session(self) -> None:
        """Commits current day volumes to the historical rolling window."""
        for t_bucket, vol in self._current_day_volumes.items():
            if t_bucket not in self.history:
                self.history[t_bucket] = []
            self.history[t_bucket].append(vol)
            if len(self.history[t_bucket]) > self.lookback_days:
                self.history[t_bucket].pop(0)
        self._current_day_volumes.clear()

    def reset_session(self) -> None:
        """Called at start of day. Commits any uncommitted day volumes."""
        self.commit_session()

    def get_median_volume(self, bucket_time: time) -> Optional[float]:
        """Calculates rolling median volume for the given time bucket from prior days."""
        hist = self.history.get(bucket_time, [])
        if not hist:
            return None
        return float(statistics.median(hist))

    def get_rvol(self, bucket_time: time, current_volume: float) -> Optional[float]:
        """
        Calculates RVOL = current_volume / rolling_median_volume.
        Returns None if no historical baseline exists yet (e.g. warmup period).
        """
        med = self.get_median_volume(bucket_time)
        if med is None or med <= 0:
            return None
        return current_volume / med

    def set_baseline(self, bucket_time: time, median_volume: float) -> None:
        """Convenience method for tests / pre-calibration."""
        self.history[bucket_time] = [median_volume] * self.lookback_days


def check_breakout_candle_quality(
    open_price: float,
    high_price: float,
    low_price: float,
    close_price: float,
    is_long: bool,
    min_bar_body_pct: float = 0.55,
    min_close_extremity_pct: float = 0.75
) -> Tuple[bool, float, float]:
    """
    Verifies the breakout candle's structural conviction (Clutch Factor).
    1. Body Ratio: |Close - Open| / (High - Low) >= min_bar_body_pct
    2. Extremity Ratio:
       - Long: (Close - Low) / (High - Low) >= min_close_extremity_pct (closes in top quartile)
       - Short: (High - Close) / (High - Low) >= min_close_extremity_pct (closes in bottom quartile)
    Returns: (is_passed, body_pct, extremity_pct)
    """
    candle_range = high_price - low_price
    if candle_range <= 0:
        return False, 0.0, 0.0

    body = abs(close_price - open_price)
    body_pct = body / candle_range

    if is_long:
        extremity_pct = (close_price - low_price) / candle_range
    else:
        extremity_pct = (high_price - close_price) / candle_range

    passed = (body_pct >= min_bar_body_pct) and (extremity_pct >= min_close_extremity_pct)
    return passed, round(body_pct, 4), round(extremity_pct, 4)


class OpeningRangeTracker:
    """Tracks Opening Range (OR) high and low during the initial session window and computes target levels."""

    def __init__(self):
        self.or_high: Optional[float] = None
        self.or_low: Optional[float] = None
        self.is_defined: bool = False
        self.bars_in_range: int = 0

    def reset(self) -> None:
        self.or_high = None
        self.or_low = None
        self.is_defined = False
        self.bars_in_range = 0

    def update(self, high: float, low: float) -> Tuple[Optional[float], Optional[float]]:
        """Update or initialize the opening range extremes."""
        if not self.is_defined:
            self.or_high = high
            self.or_low = low
            self.is_defined = True
        else:
            self.or_high = max(self.or_high, high)
            self.or_low = min(self.or_low, low)
        self.bars_in_range += 1
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

    def calculate_take_profit(
        self,
        entry_price: float,
        is_long: bool,
        risk_pts: float,
        target_mode: str = "fixed_rr",
        risk_reward: float = 1.0,
        range_mult: float = 0.80
    ) -> float:
        """
        Calculates Take Profit price based on selected geometry:
        1. fixed_rr: Entry +/- (risk_reward * risk_pts)
        2. orb_range_multiple: Entry +/- (range_mult * OR_Range_Pts)
        """
        if target_mode == "orb_range_multiple":
            target_distance = range_mult * self.range_pts
        else:
            target_distance = risk_reward * risk_pts

        if is_long:
            return round(entry_price + target_distance, 2)
        else:
            return round(entry_price - target_distance, 2)

