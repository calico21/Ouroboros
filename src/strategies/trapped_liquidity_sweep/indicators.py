"""
Microstructure Indicators and State Machine for Trapped Liquidity Sweep Strategy.
Tracks 15-minute Opening Range (09:30-09:45 EST) and detects false breakout liquidity
sweeps with re-entry confirmation, runaway invalidation, and timeout enforcement.
"""
from dataclasses import dataclass
from datetime import time
from enum import Enum
from typing import Optional, Tuple


class SweepState(str, Enum):
    IDLE = "IDLE"
    BREACHED_HIGH = "BREACHED_HIGH"
    BREACHED_LOW = "BREACHED_LOW"
    RUNAWAY_INVALIDATED = "RUNAWAY_INVALIDATED"
    TIMED_OUT = "TIMED_OUT"
    RE_ENTERED_BEAR_TRAP = "RE_ENTERED_BEAR_TRAP"  # Price swept below low, re-entered above low (Long setup)
    RE_ENTERED_BULL_TRAP = "RE_ENTERED_BULL_TRAP"  # Price swept above high, re-entered below high (Short setup)


@dataclass
class OpeningRange15M:
    """Tracks 15-minute Opening Range High, Low, and Midpoint (09:30 - 09:45 EST)."""
    high: float = float("-inf")
    low: float = float("inf")
    is_formed: bool = False

    @property
    def midpoint(self) -> float:
        return (self.high + self.low) / 2.0 if self.is_formed else 0.0

    @property
    def range_pts(self) -> float:
        return (self.high - self.low) if self.is_formed else 0.0

    def update(self, bar_high: float, bar_low: float) -> None:
        self.high = max(self.high, bar_high)
        self.low = min(self.low, bar_low)

    def lock(self) -> None:
        if self.high > self.low and self.high != float("-inf"):
            self.is_formed = True

    def reset(self) -> None:
        self.high = float("-inf")
        self.low = float("inf")
        self.is_formed = False


class TrappedLiquidityTracker:
    """
    Finite state machine monitoring false breakouts beyond 15m OR boundaries.
    Detects when retail breakout stops are triggered and institutional absorption
    forces price back inside the range within a 1-3 bar window.
    """

    def __init__(
        self,
        min_sweep_pts: float = 2.0,
        max_sweep_pts: float = 25.0,
        re_entry_timeout_bars: int = 3
    ):
        self.min_sweep_pts = min_sweep_pts
        self.max_sweep_pts = max_sweep_pts
        self.re_entry_timeout_bars = re_entry_timeout_bars

        self.orb = OpeningRange15M()
        self.state = SweepState.IDLE
        self.sweep_wick_extreme: float = 0.0
        self.bars_since_breach: int = 0
        self.sweep_direction: Optional[str] = None  # "HIGH" or "LOW"

    def reset(self) -> None:
        self.orb.reset()
        self.state = SweepState.IDLE
        self.sweep_wick_extreme = 0.0
        self.bars_since_breach = 0
        self.sweep_direction = None

    def update_range_bar(self, bar_high: float, bar_low: float) -> None:
        """Call during 09:30-09:45 EST formation window."""
        self.orb.update(bar_high, bar_low)

    def lock_range(self) -> None:
        """Locks opening range at 09:45 EST."""
        self.orb.lock()

    def process_monitoring_bar(
        self,
        bar_open: float,
        bar_high: float,
        bar_low: float,
        bar_close: float
    ) -> Tuple[SweepState, float]:
        """
        Processes subsequent bars (09:45 - 10:45 EST) through the sweep state machine.
        Returns: (CurrentState, ExtremeWickPrice)
        """
        if not self.orb.is_formed:
            return SweepState.IDLE, 0.0

        if self.state in (SweepState.RUNAWAY_INVALIDATED, SweepState.TIMED_OUT):
            return self.state, self.sweep_wick_extreme

        # State 1: IDLE - Look for initial boundary breach
        if self.state == SweepState.IDLE:
            # Check high breach
            if bar_high > self.orb.high:
                extension = bar_high - self.orb.high
                if extension > self.max_sweep_pts:
                    self.state = SweepState.RUNAWAY_INVALIDATED
                    self.sweep_wick_extreme = bar_high
                    return self.state, self.sweep_wick_extreme

                self.state = SweepState.BREACHED_HIGH
                self.sweep_direction = "HIGH"
                self.sweep_wick_extreme = bar_high
                self.bars_since_breach = 1

                # Check if this exact same bar closed back inside! (Immediate 1-bar absorption)
                if extension >= self.min_sweep_pts and bar_close < self.orb.high:
                    self.state = SweepState.RE_ENTERED_BULL_TRAP
                    return self.state, self.sweep_wick_extreme

                return self.state, self.sweep_wick_extreme

            # Check low breach
            elif bar_low < self.orb.low:
                extension = self.orb.low - bar_low
                if extension > self.max_sweep_pts:
                    self.state = SweepState.RUNAWAY_INVALIDATED
                    self.sweep_wick_extreme = bar_low
                    return self.state, self.sweep_wick_extreme

                self.state = SweepState.BREACHED_LOW
                self.sweep_direction = "LOW"
                self.sweep_wick_extreme = bar_low
                self.bars_since_breach = 1

                # Check immediate 1-bar absorption
                if extension >= self.min_sweep_pts and bar_close > self.orb.low:
                    self.state = SweepState.RE_ENTERED_BEAR_TRAP
                    return self.state, self.sweep_wick_extreme

                return self.state, self.sweep_wick_extreme

            return SweepState.IDLE, 0.0

        # State 2: BREACHED_HIGH - Tracking high false breakout
        elif self.state == SweepState.BREACHED_HIGH:
            self.bars_since_breach += 1
            self.sweep_wick_extreme = max(self.sweep_wick_extreme, bar_high)
            total_extension = self.sweep_wick_extreme - self.orb.high

            # Runaway filter
            if total_extension > self.max_sweep_pts:
                self.state = SweepState.RUNAWAY_INVALIDATED
                return self.state, self.sweep_wick_extreme

            # Timeout check
            if self.bars_since_breach > self.re_entry_timeout_bars:
                self.state = SweepState.TIMED_OUT
                return self.state, self.sweep_wick_extreme

            # Re-entry confirmation check
            if total_extension >= self.min_sweep_pts and bar_close < self.orb.high:
                self.state = SweepState.RE_ENTERED_BULL_TRAP
                return self.state, self.sweep_wick_extreme

            return self.state, self.sweep_wick_extreme

        # State 3: BREACHED_LOW - Tracking low false breakout
        elif self.state == SweepState.BREACHED_LOW:
            self.bars_since_breach += 1
            self.sweep_wick_extreme = min(self.sweep_wick_extreme, bar_low)
            total_extension = self.orb.low - self.sweep_wick_extreme

            # Runaway filter
            if total_extension > self.max_sweep_pts:
                self.state = SweepState.RUNAWAY_INVALIDATED
                return self.state, self.sweep_wick_extreme

            # Timeout check
            if self.bars_since_breach > self.re_entry_timeout_bars:
                self.state = SweepState.TIMED_OUT
                return self.state, self.sweep_wick_extreme

            # Re-entry confirmation check
            if total_extension >= self.min_sweep_pts and bar_close > self.orb.low:
                self.state = SweepState.RE_ENTERED_BEAR_TRAP
                return self.state, self.sweep_wick_extreme

            return self.state, self.sweep_wick_extreme

        return self.state, self.sweep_wick_extreme
