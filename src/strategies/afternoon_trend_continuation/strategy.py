"""
Afternoon Trend Continuation Strategy for CME Globex Futures (MNQ).
Targets post-midday institutional rebalancing and MOC flows breaking out of the 11:30–13:30 EST bracket.
"""
from datetime import time
from typing import Optional
from src.core.events import BarEvent, TradeSetup
from src.core.enums import OrderSide, OrderType
from src.strategies.base import BaseStrategy
from src.strategies.afternoon_trend_continuation.indicators import (
    MiddayConsolidationTracker,
    ADXTracker,
    ATRTracker,
)
from src.data.macro_calendar import MacroCalendar


class AfternoonTrendContinuationStrategy(BaseStrategy):
    """
    Afternoon Trend Continuation Strategy (13:30 - 15:30 EST).
    Capitalizes on institutional directional expansion after midday lunch chop.
    Monitors 11:30-13:30 EST consolidation boundaries and enters on breakout with adaptive geometry.
    Equipped with institutional macro blackout gates, volatility conditioning, and momentum thresholds.
    """

    def __init__(self, config_overrides: Optional[dict] = None):
        super().__init__(config_overrides)
        self.tracker = MiddayConsolidationTracker()
        self.adx_tracker = ADXTracker(period=14)
        self.atr_tracker = ATRTracker(period=14)
        self.calendar = MacroCalendar()
        self.trades_this_session = 0

    def reset_session(self) -> None:
        self.tracker.reset()
        self.adx_tracker.reset()
        self.atr_tracker.reset()
        self.trades_this_session = 0

    def on_bar(self, bar: BarEvent) -> Optional[TradeSetup]:
        self.check_session_boundary(bar)

        # Update continuous technical trackers
        self.adx_tracker.update_bar(bar.high, bar.low, bar.close)
        self.atr_tracker.update_bar(bar.high, bar.low, bar.close)

        t = bar.timestamp.time()
        bar_date = bar.timestamp.date()

        # 1. Midday Consolidation Window: 11:30 to 13:30 EST
        if time(11, 30) <= t < time(13, 30):
            self.tracker.update_bar(bar.high, bar.low, bar.volume)
            return None

        # 2. Trigger Window: 13:30 to 15:15 EST
        if not (time(13, 30) <= t <= time(15, 15)):
            return None

        # Max trades per day constraint
        if self.trades_this_session >= self.config.get("max_trades_per_day", 1):
            return None

        # Consolidation range validity check
        if not self.tracker.is_valid_range:
            return None

        # --- INSTITUTIONAL FILTER 1: MACRO EVENT BLACKOUT ENGINE ---
        if self.config.get("macro_blackout_enabled", True):
            # CPI Blackout Check
            if self.config.get("blackout_cpi", True) and self.calendar.is_cpi_day(bar_date):
                return None

            # Announcement Window Check (e.g. FOMC 14:00/14:30 EST)
            window_mins = self.config.get("blackout_announcement_window_mins", 30)
            t_str = f"{t.hour:02d}:{t.minute:02d}"
            suppressed, _ = self.calendar.should_suppress_strategy_entry(
                bar_date, t_str, buffer_minutes_before=15, buffer_minutes_after=window_mins
            )
            if suppressed:
                return None

        # --- INSTITUTIONAL FILTER 2: VOLATILITY & TREND REGIME CONDITIONING ---
        # Suppress entries in Quintile 5 extreme crisis volatility
        allowed_quintiles = self.config.get("allowed_atr_quintiles", [1, 2, 3, 4])
        if 5 not in allowed_quintiles and self.atr_tracker.is_quintile_5_crisis():
            return None

        # Directional Momentum Gate (ADX > 18.0)
        adx_thresh = float(self.config.get("adx_threshold", 18.0))
        if self.config.get("trend_alignment_enabled", True) and self.adx_tracker.adx > 0:
            if self.adx_tracker.adx < adx_thresh:
                return None

        range_pts = self.tracker.range_pts
        min_pts = float(self.config.get("min_consolidation_pts", 10.0))
        max_pts = float(self.config.get("max_consolidation_pts", 80.0))
        if range_pts < min_pts or range_pts > max_pts:
            return None

        high_lvl = self.tracker.high
        low_lvl = self.tracker.low
        mid_lvl = self.tracker.midpoint

        stop_mode = self.config.get("stop_mode", "midpoint")
        rr = float(self.config.get("risk_reward", self.config.get("target_rr", 1.20)))
        time_stop = self.config.get("time_stop_bars", 12)
        be_trigger_r = float(self.config.get("breakeven_trigger_r", 0.85))

        # 3. Bullish Breakout above Midday High
        if bar.close > high_lvl:
            stop_loss = mid_lvl if stop_mode == "midpoint" else low_lvl
            risk_pts = bar.close - stop_loss
            if risk_pts <= 0:
                return None
            take_profit = bar.close + (risk_pts * rr)

            self.trades_this_session += 1
            return TradeSetup(
                direction=OrderSide.LONG,
                order_type=OrderType.MARKET,
                stop_loss=round(stop_loss, 2),
                take_profit=round(take_profit, 2),
                ttl_bars=self.config.get("ttl_bars", 8),
                time_stop_bars=time_stop,
                tag="PM_BREAKOUT_LONG",
                metadata={
                    "midday_high": high_lvl,
                    "midday_low": low_lvl,
                    "midpoint": mid_lvl,
                    "risk_pts": risk_pts,
                    "target_rr": rr,
                    "breakeven_trigger_r": be_trigger_r,
                    "adx": round(self.adx_tracker.adx, 2),
                    "atr": round(self.atr_tracker.atr, 2),
                }
            )

        # 4. Bearish Breakdown below Midday Low
        elif bar.close < low_lvl:
            stop_loss = mid_lvl if stop_mode == "midpoint" else high_lvl
            risk_pts = stop_loss - bar.close
            if risk_pts <= 0:
                return None
            take_profit = bar.close - (risk_pts * rr)

            self.trades_this_session += 1
            return TradeSetup(
                direction=OrderSide.SHORT,
                order_type=OrderType.MARKET,
                stop_loss=round(stop_loss, 2),
                take_profit=round(take_profit, 2),
                ttl_bars=self.config.get("ttl_bars", 8),
                time_stop_bars=time_stop,
                tag="PM_BREAKOUT_SHORT",
                metadata={
                    "midday_high": high_lvl,
                    "midday_low": low_lvl,
                    "midpoint": mid_lvl,
                    "risk_pts": risk_pts,
                    "target_rr": rr,
                    "breakeven_trigger_r": be_trigger_r,
                    "adx": round(self.adx_tracker.adx, 2),
                    "atr": round(self.atr_tracker.atr, 2),
                }
            )

        return None
