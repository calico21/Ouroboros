"""
Evolved Opening Range Breakout 5M Binary Strategy for CME Globex Futures.
Addresses the 50% "Trapped Trade" failure mode via calibrated target geometry,
inertia-based time-decay stop, and optional soft profit protection.
"""
from datetime import time
from typing import Optional
from src.core.events import BarEvent, TradeSetup
from src.core.enums import OrderSide, OrderType
from src.strategies.base import BaseStrategy
from src.strategies.orb_5m_binary.indicators import (
    OpeningRangeTracker,
    TimeBucketVolumeTracker,
    check_breakout_candle_quality,
)


class Orb5mBinaryStrategy(BaseStrategy):
    """
    Opening Range Breakout 5-Minute Binary Strategy (Evolved).
    Monetizes the violent opening auction impulse by aligning take-profit geometry
    with empirical MFE distribution, invalidating stagnant trades via time stops,
    and filtering out false-breakout liquidity sweeps via RVOL and Candle Clutch Factor.
    """

    def __init__(self, config_overrides: Optional[dict] = None):
        super().__init__(config_overrides)
        self.tracker = OpeningRangeTracker()
        lookback_days = int(self.config.get("rvol_lookback_days", 15))
        self.volume_tracker = TimeBucketVolumeTracker(lookback_days=lookback_days)
        self.trades_this_session = 0
        self.or_formed = False

    def reset_session(self) -> None:
        self.tracker.reset()
        self.trades_this_session = 0
        self.or_formed = False
        self.volume_tracker.reset_session()

    def on_bar(self, bar: BarEvent) -> Optional[TradeSetup]:
        self.check_session_boundary(bar)

        # 0. Continuously update intraday volume baseline tracker
        self.volume_tracker.on_bar(bar.timestamp, bar.volume)

        t = bar.timestamp.time()
        
        # 1. OR Formation Window: Bars between 09:30 and 09:45 EST
        # First bar at or before 09:35 defines initial opening range
        if not self.or_formed and (t <= time(9, 35)):
            self.tracker.update(bar.high, bar.low)
            self.or_formed = True
            return None

        # 2. Execution Gate: Must have formed OR, within daily trade budget, and before expiration cutoff
        if not self.or_formed or self.trades_this_session >= self.config.get("max_trades_per_session", 1):
            return None

        # Expiration cutoff (default: 11:30 EST)
        if t >= time(11, 30):
            return None

        or_range = self.tracker.range_pts
        min_pts = float(self.config.get("min_range_pts", 4.0))
        max_pts = float(self.config.get("max_range_pts", 120.0))
        if or_range < min_pts or or_range > max_pts:
            return None

        or_high = self.tracker.or_high
        or_low = self.tracker.or_low
        mid = self.tracker.midpoint

        target_mode = self.config.get("target_mode", "fixed_rr")
        risk_reward = float(self.config.get("risk_reward", 1.0))
        range_mult = float(self.config.get("range_mult", 0.80))
        time_stop = self.config.get("time_stop_bars", 3)
        protect_at_1r = bool(self.config.get("protect_at_1r", False))
        stop_type = self.config.get("stop_type", "midpoint")

        min_bar_body_pct = float(self.config.get("min_bar_body_pct", 0.55))
        min_close_extremity_pct = float(self.config.get("min_close_extremity_pct", 0.75))
        min_breakout_rvol = float(self.config.get("min_breakout_rvol", 1.25))

        # 3. Bullish Breakout
        if bar.close > or_high:
            # Quality Gate A: Candle Structural Conviction (Clutch Factor)
            is_quality, body_pct, extremity_pct = check_breakout_candle_quality(
                open_price=bar.open,
                high_price=bar.high,
                low_price=bar.low,
                close_price=bar.close,
                is_long=True,
                min_bar_body_pct=min_bar_body_pct,
                min_close_extremity_pct=min_close_extremity_pct
            )
            if not is_quality:
                return None

            # Quality Gate B: Relative Volume (RVOL) vs 15-day median for exact time bucket (09:45-09:50 fakeout gate)
            rvol = self.volume_tracker.get_rvol(t, bar.volume)
            if (time(9, 45) <= t <= time(9, 50)) and (rvol is not None) and (rvol < min_breakout_rvol):
                return None

            stop_loss = mid if stop_type == "midpoint" else or_low
            risk_pts = bar.close - stop_loss
            if risk_pts <= 0:
                return None

            take_profit = self.tracker.calculate_take_profit(
                entry_price=bar.close,
                is_long=True,
                risk_pts=risk_pts,
                target_mode=target_mode,
                risk_reward=risk_reward,
                range_mult=range_mult
            )

            self.trades_this_session += 1
            return TradeSetup(
                direction=OrderSide.LONG,
                order_type=OrderType.MARKET,
                stop_loss=round(stop_loss, 2),
                take_profit=round(take_profit, 2),
                ttl_bars=self.config.get("ttl_bars", 6),
                time_stop_bars=time_stop,
                protect_at_1r=protect_at_1r,
                tag=self.config.get("tag", "ORB_5M_LONG"),
                metadata={
                    "or_high": or_high,
                    "or_low": or_low,
                    "risk_pts": risk_pts,
                    "target_mode": target_mode,
                    "target_rr": risk_reward,
                    "rvol": round(rvol, 2) if rvol is not None else 1.0,
                    "body_pct": body_pct,
                    "close_extremity": extremity_pct
                }
            )

        # 4. Bearish Breakdown
        elif bar.close < or_low:
            # Quality Gate A: Candle Structural Conviction (Clutch Factor)
            is_quality, body_pct, extremity_pct = check_breakout_candle_quality(
                open_price=bar.open,
                high_price=bar.high,
                low_price=bar.low,
                close_price=bar.close,
                is_long=False,
                min_bar_body_pct=min_bar_body_pct,
                min_close_extremity_pct=min_close_extremity_pct
            )
            if not is_quality:
                return None

            # Quality Gate B: Relative Volume (RVOL) vs 15-day median for exact time bucket (09:45-09:50 fakeout gate)
            rvol = self.volume_tracker.get_rvol(t, bar.volume)
            if (time(9, 45) <= t <= time(9, 50)) and (rvol is not None) and (rvol < min_breakout_rvol):
                return None

            stop_loss = mid if stop_type == "midpoint" else or_high
            risk_pts = stop_loss - bar.close
            if risk_pts <= 0:
                return None

            take_profit = self.tracker.calculate_take_profit(
                entry_price=bar.close,
                is_long=False,
                risk_pts=risk_pts,
                target_mode=target_mode,
                risk_reward=risk_reward,
                range_mult=range_mult
            )

            self.trades_this_session += 1
            return TradeSetup(
                direction=OrderSide.SHORT,
                order_type=OrderType.MARKET,
                stop_loss=round(stop_loss, 2),
                take_profit=round(take_profit, 2),
                ttl_bars=self.config.get("ttl_bars", 6),
                time_stop_bars=time_stop,
                protect_at_1r=protect_at_1r,
                tag=self.config.get("tag", "ORB_5M_SHORT"),
                metadata={
                    "or_high": or_high,
                    "or_low": or_low,
                    "risk_pts": risk_pts,
                    "target_mode": target_mode,
                    "target_rr": risk_reward,
                    "rvol": round(rvol, 2) if rvol is not None else 1.0,
                    "body_pct": body_pct,
                    "close_extremity": extremity_pct
                }
            )

        return None
