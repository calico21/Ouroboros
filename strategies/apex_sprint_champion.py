"""
Ouroboros - Apex 50k 21-Session Sprint Champion Strategy
=========================================================
Strategy ID: APEX_SPRINT_CHAMPION (Unconstrained Pass-Frontier Champion)
Asset: CME Globex Micro E-mini Nasdaq-100 (MNQ)
Intermarket Anchor: CME Globex Micro E-mini S&P 500 (MES)
Version: 3.0.0

Core Architectural Thesis:
  To maximize single-account pass probability under the strict Apex 21-trading-session
  horizon (30 calendar days) where Timeout is terminally identical to Ruin ($0 payoff),
  the system deploys the Unconstrained Pass-Frontier Architecture:

  1. High-Expectancy Morning Auction Core (09:30 - 11:30 EST):
     - Dalton 70% Value Area traverse and Macro PDH/PDL sweeps confirmed with NQ vs ES SMT.
     - Unconstrained fixed asymmetric targets: 20.0 pt SL / 48.0 pt TP (R:R = 1:2.40).
     - No premature breakeven or trailing ratchets (preserving runner momentum).
     - Day Sequencing: Up to 3 trades per day, taking subsequent trades after winning runs.

  2. Full Dynamic Programming (DP_V1_ADAPTIVE) Optimal Control Sizing:
     - Base Stride: 7 MNQ ($14/pt) when D_t >= $1,500.
     - Traction Acceleration: 8 MNQ ($16/pt) when profit >= $600.
     - SMT Conviction Sprint: 10 MNQ ($20/pt) on intermarket order flow absorption.
     - Locked Floor Sprint: 10 MNQ ($20/pt) once HWM >= $52,600 (floor frozen at +$100).
     - Endgame Escalation: 10 MNQ ($20/pt) when k <= 5 sessions or k <= 7 sessions with gap.
     - Multi-Tier Defensive Clamp: 5 MNQ for D_t in [$1,200, $1,500], 3 MNQ for D_t < $1,200.
"""

from __future__ import annotations
import math
from datetime import datetime, time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src.core.enums import OrderSide, OrderType
from src.core.events import BarEvent, TradeSetup
from src.strategies.base import BaseStrategy
from src.data.cme_session_clock import ensure_ny_tz, get_cme_trade_date_str


@dataclass
class ChampionExecutionParameters:
    symbol: str = "MNQ"
    intermarket_symbol: str = "MES"
    point_value: float = 2.00
    tick_size: float = 0.25
    commission_rt: float = 1.24
    slippage_ticks: float = 1.0

    # Risk & Target Parameters (Baseline / Sleeve 2 Anchor)
    stop_loss_pts: float = 20.0
    take_profit_pts: float = 48.0         # Default R:R = 1:2.40
    use_adaptive_atr: bool = False         # When True: SL = 1.0x ATR, TP = 2.4x ATR
    daily_circuit_breaker: float = 220.0  # Max daily loss in dollars (halts after 1 loss)

    # Tri-Sleeve Execution Parameters
    enable_multi_sleeve: bool = True
    sleeve_1_sl_pts: float = 18.0
    sleeve_1_tp_pts: float = 36.0
    sleeve_2_sl_pts: float = 20.0
    sleeve_2_tp_pts: float = 48.0
    sleeve_3_sl_pts: float = 16.0
    sleeve_3_tp_pts: float = 32.0

    # Position Sizing & Bellman Protocols
    sizing_model: str = "DYNAMIC_DISTANCE_TO_FLOOR_KELLY"
    base_contracts: int = 5
    ratchet_contracts: int = 8
    max_contracts: int = 10
    ratchet_trigger_profit: float = 1300.0  # Threshold to engage sprint phase
    floor_clamp_buffer: float = 1750.0      # Buffer threshold below which sizing clamps to 4c
    floor_clamp_contracts: int = 4
    endgame_sprint_sessions: int = 6
    endgame_sprint_contracts: int = 9

    # SMT Intermarket Filter
    enable_smt_divergence: bool = False
    smt_conviction_boost: bool = True       # Boost size by +1 contract on confirmed SMT

    # Session Windows (EST)
    session_start: time = field(default_factory=lambda: time(9, 30))
    entry_cutoff: time = field(default_factory=lambda: time(13, 0))
    hard_flatten_time: time = field(default_factory=lambda: time(15, 55))

    # Multi-Sleeve Specific Windows
    s1_start: time = field(default_factory=lambda: time(8, 0))
    s1_end: time = field(default_factory=lambda: time(9, 20))
    s2_start: time = field(default_factory=lambda: time(9, 30))
    s2_end: time = field(default_factory=lambda: time(11, 30))
    s3_start: time = field(default_factory=lambda: time(14, 0))
    s3_end: time = field(default_factory=lambda: time(15, 35))


class ApexSprintChampionStrategy(BaseStrategy):
    """
    Production Quantitative Strategy for Apex 50k 21-Session Sprint.
    Implements BaseStrategy interface for seamless live/paper execution in Ouroboros.
    """
    STRATEGY_NAME = "apex_sprint_champion"

    def __init__(self, config_overrides: Optional[Dict[str, Any]] = None):
        super().__init__(config_overrides)
        self.params = ChampionExecutionParameters()
        self._apply_config_overrides()
        self.reset_session()

        # Multi-session tracking for zero-lookahead reference levels
        self.daily_rth_bars: Dict[Any, List[BarEvent]] = {}
        self.daily_rth_es_bars: Dict[Any, List[BarEvent]] = {}
        self.prev_day_high: Optional[float] = None
        self.prev_day_low: Optional[float] = None
        self.prev_day_close: Optional[float] = None
        self.prev_vah: Optional[float] = None
        self.prev_val: Optional[float] = None

        # Intermarket ES reference levels
        self.prev_day_high_es: Optional[float] = None
        self.prev_day_low_es: Optional[float] = None
        self.prev_vah_es: Optional[float] = None
        self.prev_val_es: Optional[float] = None
        self.latest_es_bar: Optional[BarEvent] = None

        # Account Equity & Distance-to-Floor Tracking
        self.account_equity: float = 50000.0
        self.high_water_mark: float = 50000.0
        self.trailing_floor: float = 47500.0
        self.sessions_remaining: int = 21

        # Intraday rolling bars for afternoon and premarket swings
        self.intraday_bars: List[BarEvent] = []

    def _apply_config_overrides(self) -> None:
        if not self.config:
            return
        if "stop_loss_pts" in self.config:
            self.params.stop_loss_pts = float(self.config["stop_loss_pts"])
        if "take_profit_pts" in self.config:
            self.params.take_profit_pts = float(self.config["take_profit_pts"])
        if "base_contracts" in self.config:
            self.params.base_contracts = int(self.config["base_contracts"])
        if "ratchet_contracts" in self.config:
            self.params.ratchet_contracts = int(self.config["ratchet_contracts"])
        if "max_contracts" in self.config:
            self.params.max_contracts = int(self.config["max_contracts"])
        if "daily_circuit_breaker" in self.config:
            self.params.daily_circuit_breaker = float(self.config["daily_circuit_breaker"])
        if "use_adaptive_atr" in self.config:
            self.params.use_adaptive_atr = bool(self.config["use_adaptive_atr"])
        if "enable_smt_divergence" in self.config:
            self.params.enable_smt_divergence = bool(self.config["enable_smt_divergence"])
        if "enable_multi_sleeve" in self.config:
            self.params.enable_multi_sleeve = bool(self.config["enable_multi_sleeve"])
        if "floor_clamp_buffer" in self.config:
            self.params.floor_clamp_buffer = float(self.config["floor_clamp_buffer"])
        if "floor_clamp_contracts" in self.config:
            self.params.floor_clamp_contracts = int(self.config["floor_clamp_contracts"])
        if "endgame_sprint_sessions" in self.config:
            self.params.endgame_sprint_sessions = int(self.config["endgame_sprint_sessions"])
        if "endgame_sprint_contracts" in self.config:
            self.params.endgame_sprint_contracts = int(self.config["endgame_sprint_contracts"])
        if "sizing_model" in self.config:
            self.params.sizing_model = str(self.config["sizing_model"])
        if "smt_conviction_boost" in self.config:
            self.params.smt_conviction_boost = bool(self.config["smt_conviction_boost"])

    def reset_session(self) -> None:
        """Resets intraday session indicators and circuit breakers."""
        self.current_trade_date: Optional[str] = None
        self.today_open: Optional[float] = None
        self.today_cum_tp_vol: float = 0.0
        self.today_cum_vol: float = 0.0
        self.current_vwap: Optional[float] = None
        self.daily_realized_pnl: float = 0.0
        self.trades_taken_today: int = 0
        self.consecutive_losses_today: int = 0
        self.active_position_dir: Optional[OrderSide] = None
        self.daily_traded_sleeves: set = set()
        self.intraday_bars = []

    def update_es_bar(self, bar_es: BarEvent) -> None:
        """Updates intermarket ES order flow bar for SMT divergence evaluation."""
        self.latest_es_bar = bar_es
        ny_time = ensure_ny_tz(bar_es.timestamp)
        t = ny_time.time()
        d = ny_time.date()
        if time(9, 30) <= t <= time(16, 0):
            if d not in self.daily_rth_es_bars:
                self.daily_rth_es_bars[d] = []
            self.daily_rth_es_bars[d].append(bar_es)

    def compute_position_size(
        self,
        is_smt_confirmed: bool = False,
        sessions_remaining: Optional[int] = None,
        d_t: Optional[float] = None
    ) -> int:
        """
        Computes dynamic position sizing using Finite-Horizon Bang-Bang Sizing or Discrete Kelly.
        D_t = Equity_t - TrailingFloor_t (Capital cushion available before liquidation).
        k = sessions_remaining (Horizon countdown to calendar timeout).
        """
        if d_t is None:
            d_t = self.account_equity - self.trailing_floor
        profit = self.account_equity - 50000.0
        k = sessions_remaining if sessions_remaining is not None else self.sessions_remaining
        gap = 3000.0 - profit

        # Optimal DP Adaptive Sizing (v3.0.0 Champion):
        if self.params.sizing_model in ("DP_V1_ADAPTIVE", "DYNAMIC_PROGRAMMING_V1", "DP_V1"):
            # 1. Locked floor or near-locking: full sprint
            if self.high_water_mark >= 52600.0 or profit >= 1800.0:
                return self.params.max_contracts
            # 2. High conviction SMT: full sprint
            if is_smt_confirmed and self.params.smt_conviction_boost:
                return self.params.max_contracts
            # 3. Endgame escalation (monotonically increasing with urgency)
            if k <= 5:
                return self.params.max_contracts if gap > 800.0 else 8
            if k <= 7:
                return self.params.max_contracts if gap > 1200.0 else 8
            # 4. Multi-tier defensive clamp
            if d_t < 1200.0:
                return 3
            if d_t < 1500.0:
                return 5
            # 5. Traction acceleration
            if profit >= 600.0:
                return 8
            # 6. Base stride
            return self.params.base_contracts

        # Phase B: Defensive Floor Guard (Protect buffer when depleted below threshold)
        if d_t < self.params.floor_clamp_buffer:
            return self.params.floor_clamp_contracts

        # Pure Pass Maximizer Bang-Bang Architecture:
        if self.params.sizing_model in ("BANG_BANG_MAXIMIZER", "PURE_PASS_FRONTIER"):
            # 1. Floor Freeze Sprint (Floor permanently locked at $50,100 or near locking)
            if self.high_water_mark >= 52600.0 or profit >= 1800.0:
                return self.params.max_contracts
            # 2. SMT Conviction Sprint (Institutional order flow divergence confirmation)
            if is_smt_confirmed and self.params.smt_conviction_boost:
                return self.params.max_contracts
            # 3. Endgame Escalation (Horizon countdown timeout avoidance)
            if k <= self.params.endgame_sprint_sessions and gap > 1000.0:
                return self.params.endgame_sprint_contracts
            # 4. Traction acceleration (Equity >= $50,900)
            if profit >= 900.0:
                return min(self.params.max_contracts, self.params.base_contracts + 1)
            # 5. Initial Stride
            return self.params.base_contracts

        # Default / Kelly Sizing Model:
        # Phase D: Locked Floor Sprint (Floor permanently locked at $50,100)
        if self.high_water_mark >= 52600.0 or profit >= 2200.0:
            return self.params.max_contracts

        # Phase E: Endgame Sprint (Avoid calendar timeout ruin when window is closing)
        if k <= self.params.endgame_sprint_sessions and gap > 1000.0:
            return self.params.endgame_sprint_contracts

        # Phase C: Traction Acceleration Phase
        if profit >= 1400.0:
            return 9 if (is_smt_confirmed and self.params.smt_conviction_boost) else 8
        elif profit >= 600.0:
            return 8 if (is_smt_confirmed and self.params.smt_conviction_boost) else 7
        else:
            # Phase A: Buffer Conservation Phase
            return 6 if (is_smt_confirmed and self.params.smt_conviction_boost) else self.params.base_contracts

    def on_bar(self, bar: BarEvent) -> Optional[TradeSetup]:
        """
        Processes new 5-minute bar and generates abstract TradeSetup if conditions are met.
        Strict zero look-ahead bias: all decisions based strictly on completed bars.
        """
        ny_time = ensure_ny_tz(bar.timestamp)
        t = ny_time.time()
        d = ny_time.date()
        trade_date_str = get_cme_trade_date_str(bar.timestamp)

        # Session boundary check
        if self.current_trade_date != trade_date_str:
            self._finalize_prior_session()
            self.current_trade_date = trade_date_str
            self.reset_session()

        self.intraday_bars.append(bar)

        # Update Session VWAP (09:30 - 16:00 EST)
        if time(9, 30) <= t <= time(16, 0):
            tp = (bar.high + bar.low + bar.close) / 3.0
            vol = bar.volume if bar.volume > 0 else 1.0
            self.today_cum_tp_vol += tp * vol
            self.today_cum_vol += vol
            self.current_vwap = self.today_cum_tp_vol / self.today_cum_vol

            if self.today_open is None and t >= time(9, 30):
                self.today_open = bar.open

            if d not in self.daily_rth_bars:
                self.daily_rth_bars[d] = []
            self.daily_rth_bars[d].append(bar)

        # Daily Circuit Breaker: Halt trading if daily loss limit hit
        if self.daily_realized_pnl <= -self.params.daily_circuit_breaker:
            return None

        # Maximum trades per day guard
        if self.trades_taken_today >= 3:
            return None
        if self.trades_taken_today >= 2 and self.daily_realized_pnl < 0.0:
            return None

        # Check required prior day levels
        if (self.prev_day_high is None or self.prev_day_low is None):
            return None

        atr = bar.atr_14 or (bar.high - bar.low)
        if atr <= 0:
            return None

        bar_range = max(0.25, bar.high - bar.low)
        upper_wick = bar.high - max(bar.open, bar.close)
        lower_wick = min(bar.open, bar.close) - bar.low
        up_wick_ratio = upper_wick / bar_range
        dn_wick_ratio = lower_wick / bar_range

        # SMT Divergence Check against ES
        is_smt_bearish = False
        is_smt_bullish = False
        if self.latest_es_bar is not None and self.prev_day_high_es is not None:
            es_b = self.latest_es_bar
            nq_swept_h = (bar.high > self.prev_day_high) or (self.prev_vah is not None and bar.high > self.prev_vah)
            es_swept_h = (es_b.high > self.prev_day_high_es) or (self.prev_vah_es is not None and es_b.high > self.prev_vah_es)
            is_smt_bearish = (nq_swept_h and not es_swept_h) or (es_swept_h and not nq_swept_h)

            nq_swept_l = (bar.low < self.prev_day_low) or (self.prev_val is not None and bar.low < self.prev_val)
            es_swept_l = (es_b.low < self.prev_day_low_es) or (self.prev_val_es is not None and es_b.low < self.prev_val_es)
            is_smt_bullish = (nq_swept_l and not es_swept_l) or (es_swept_l and not nq_swept_l)

        direction: Optional[OrderSide] = None
        tag = ""
        sleeve_name = ""
        smt_confirmed = False
        sl_dist = self.params.stop_loss_pts
        tp_dist = self.params.take_profit_pts

        # -------------------------------------------------------------
        # SLEEVE 1: Pre-Market Sweep (08:00 - 09:20 EST)
        # -------------------------------------------------------------
        if (self.params.enable_multi_sleeve and
            self.params.s1_start <= t <= self.params.s1_end and
            "SLEEVE_1" not in self.daily_traded_sleeves):
            if bar.high > self.prev_day_high and bar.close < self.prev_day_high and up_wick_ratio >= 0.25 and (bar.high - self.prev_day_high) <= 1.2 * atr:
                direction = OrderSide.SHORT
                tag = "S1_PM_PDH_SWEEP"
                sleeve_name = "SLEEVE_1"
                sl_dist = self.params.sleeve_1_sl_pts
                tp_dist = self.params.sleeve_1_tp_pts
            elif bar.low < self.prev_day_low and bar.close > self.prev_day_low and dn_wick_ratio >= 0.25 and (self.prev_day_low - bar.low) <= 1.2 * atr:
                direction = OrderSide.LONG
                tag = "S1_PM_PDL_SWEEP"
                sleeve_name = "SLEEVE_1"
                sl_dist = self.params.sleeve_1_sl_pts
                tp_dist = self.params.sleeve_1_tp_pts

        # -------------------------------------------------------------
        # SLEEVE 2: NY Open Value Area & Macro SMT Sweep (09:35 - 11:30 EST)
        # -------------------------------------------------------------
        if direction is None and (self.params.s2_start <= t <= self.params.s2_end) and "SLEEVE_2" not in self.daily_traded_sleeves:
            if self.prev_vah is not None and self.prev_val is not None and self.current_vwap is not None and self.today_open is not None:
                # 1. Dalton 70% Value Area Traverse
                if self.today_open > self.prev_vah and bar.close < self.prev_vah and bar.close < self.current_vwap:
                    direction = OrderSide.SHORT
                    tag = "S2_VA_TRAVERSE_SHORT"
                    sleeve_name = "SLEEVE_2"
                    smt_confirmed = is_smt_bearish
                elif self.today_open < self.prev_val and bar.close > self.prev_val and bar.close > self.current_vwap:
                    direction = OrderSide.LONG
                    tag = "S2_VA_TRAVERSE_LONG"
                    sleeve_name = "SLEEVE_2"
                    smt_confirmed = is_smt_bullish
                elif self.prev_val <= self.today_open <= self.prev_vah:
                    if bar.high > self.prev_vah and bar.close < self.prev_vah and bar.close < self.current_vwap:
                        direction = OrderSide.SHORT
                        tag = "S2_VA_BOUNDARY_FADE_SHORT"
                        sleeve_name = "SLEEVE_2"
                        smt_confirmed = is_smt_bearish
                    elif bar.low < self.prev_val and bar.close > self.prev_val and bar.close > self.current_vwap:
                        direction = OrderSide.LONG
                        tag = "S2_VA_BOUNDARY_FADE_LONG"
                        sleeve_name = "SLEEVE_2"
                        smt_confirmed = is_smt_bullish

            # 2. Macro PDH / PDL Liquidity Reversal
            if direction is None:
                if self.today_open is not None and self.today_open < self.prev_day_high and bar.high > self.prev_day_high and bar.close < self.prev_day_high:
                    if (bar.high - self.prev_day_high) <= 1.0 * atr and bar.close <= bar.open + 0.15 * atr:
                        direction = OrderSide.SHORT
                        tag = "S2_PDH_SWEEP_SHORT"
                        sleeve_name = "SLEEVE_2"
                        smt_confirmed = is_smt_bearish
                elif self.today_open is not None and self.today_open > self.prev_day_low and bar.low < self.prev_day_low and bar.close > self.prev_day_low:
                    if (self.prev_day_low - bar.low) <= 1.0 * atr and bar.close >= bar.open - 0.15 * atr:
                        direction = OrderSide.LONG
                        tag = "S2_PDL_SWEEP_LONG"
                        sleeve_name = "SLEEVE_2"
                        smt_confirmed = is_smt_bullish

            if direction is not None:
                if self.params.use_adaptive_atr:
                    sl_dist = min(24.0, max(16.0, 1.0 * atr))
                    tp_dist = min(55.0, max(36.0, 2.4 * atr))
                else:
                    sl_dist = self.params.sleeve_2_sl_pts
                    tp_dist = self.params.sleeve_2_tp_pts

        # -------------------------------------------------------------
        # SLEEVE 3: Cash Close & MOC Imbalance Reversion (14:00 - 15:45 EST)
        # -------------------------------------------------------------
        if (direction is None and self.params.enable_multi_sleeve and
            self.params.s3_start <= t <= self.params.s3_end and
            "SLEEVE_3" not in self.daily_traded_sleeves):
            if len(self.intraday_bars) >= 12 and self.current_vwap is not None:
                recent_12 = self.intraday_bars[-13:-1]
                sw_h = max(b.high for b in recent_12)
                sw_l = min(b.low for b in recent_12)
                if bar.high > sw_h and bar.close < sw_h and bar.close > self.current_vwap and up_wick_ratio >= 0.35:
                    direction = OrderSide.SHORT
                    tag = "S3_MOC_SWING_FADE_SHORT"
                    sleeve_name = "SLEEVE_3"
                    smt_confirmed = is_smt_bearish
                    sl_dist = self.params.sleeve_3_sl_pts
                    tp_dist = self.params.sleeve_3_tp_pts
                elif bar.low < sw_l and bar.close > sw_l and bar.close < self.current_vwap and dn_wick_ratio >= 0.35:
                    direction = OrderSide.LONG
                    tag = "S3_MOC_SWING_FADE_LONG"
                    sleeve_name = "SLEEVE_3"
                    smt_confirmed = is_smt_bullish
                    sl_dist = self.params.sleeve_3_sl_pts
                    tp_dist = self.params.sleeve_3_tp_pts

        if direction is None:
            return None

        # Filter: If strict SMT filter is enabled and SMT is absent on Sleeve 2, discard
        if sleeve_name == "SLEEVE_2" and self.params.enable_smt_divergence and not smt_confirmed:
            return None

        if direction == OrderSide.LONG:
            stop_price = round((bar.close - sl_dist) * 4) / 4
            target_price = round((bar.close + tp_dist) * 4) / 4
        else:
            stop_price = round((bar.close + sl_dist) * 4) / 4
            target_price = round((bar.close - tp_dist) * 4) / 4

        self.trades_taken_today += 1
        if sleeve_name:
            self.daily_traded_sleeves.add(sleeve_name)

        return TradeSetup(
            strategy_name=self.STRATEGY_NAME,
            symbol=self.params.symbol,
            direction=direction,
            order_type=OrderType.MARKET,
            stop_loss=stop_price,
            take_profit=target_price,
            ttl_bars=1,
            time_stop_bars=50,
            tag=f"{tag}_SMT" if smt_confirmed else tag
        )

    def _finalize_prior_session(self) -> None:
        """Computes prior day levels and Dalton Value Area from completed sessions."""
        if not self.daily_rth_bars:
            return

        sorted_days = sorted(self.daily_rth_bars.keys())
        if len(sorted_days) < 1:
            return

        last_day = sorted_days[-1]
        bars = self.daily_rth_bars[last_day]
        if len(bars) < 10:
            return

        h = max(b.high for b in bars)
        l = min(b.low for b in bars)
        c = bars[-1].close

        self.prev_day_high = h
        self.prev_day_low = l
        self.prev_day_close = c

        # Dalton Value Area (70% profile)
        typical = (h + l + c) / 3.0
        rng = h - l
        self.prev_vah = typical + 0.35 * rng
        self.prev_val = typical - 0.35 * rng

        # Intermarket ES prior levels
        if last_day in self.daily_rth_es_bars:
            es_bars = self.daily_rth_es_bars[last_day]
            if len(es_bars) >= 10:
                h_es = max(b.high for b in es_bars)
                l_es = min(b.low for b in es_bars)
                c_es = es_bars[-1].close
                self.prev_day_high_es = h_es
                self.prev_day_low_es = l_es
                typ_es = (h_es + l_es + c_es) / 3.0
                rng_es = h_es - l_es
                self.prev_vah_es = typ_es + 0.35 * rng_es
                self.prev_val_es = typ_es - 0.35 * rng_es
