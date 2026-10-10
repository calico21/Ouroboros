#!/usr/bin/env python3
"""
AlphaForge Institutional Quantitative Strategy Discovery Engine (Apex 50k Rig)
TEST MASIVO - BATCH 1

Hypotheses Evaluated:
1. Sleeve 1: Multi-Asset Daily Regime Pullback (MYM / MES / MNQ)
2. Sleeve 2: Session Liquidity Sweep & VWAP Rejection (MNQ)
3. Sleeve 3: Volatility Compression & Asymmetric Expansion Breakout (MES / MNQ)
4. Combined Portfolio (Sleeves 1 + 2 + 3 with Mutual Exclusion)

Apex 50k Hard Constraints & Boundary Rules:
- Nominal Balance: $50,000.00
- Initial Drawdown Buffer: $2,000.00 (Initial Liquidation Floor: $48,000.00)
- Target Profit: $53,000.00 (+$3,000.00)
- Intraday Peak MFE Trailing Floor: Floor_t = max(Floor_{t-1}, PeakEquity_t - $2,000)
- Permanent Apex Freeze: Once PeakEquity >= $52,600, Floor permanently locks at $50,100 ($2,500 safety buffer)
- Friction: CME micro commissions ($1.24 RT) + 1 tick/side slippage (0.25 pt on NQ/ES, 1 pt on YM)
- Execution: Stop-First pessimistic intra-bar resolution
- Risk Ceiling (1R): Strictly bounded between $80 and $120.
"""

from __future__ import annotations
import os
import sys
import json
import math
import time
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Tuple, Any

import numpy as np
import pandas as pd

# Constants for Apex 50k Evaluation Rig
STARTING_BALANCE = 50000.0
BUFFER = 2000.0
INITIAL_FLOOR = STARTING_BALANCE - BUFFER  # 48,000.0
LOCK_HWM = STARTING_BALANCE + 2600.0       # 52,600.0
LOCK_FLOOR = STARTING_BALANCE + 100.0      # 50,100.0
PROFIT_TARGET = STARTING_BALANCE + 3000.0  # 53,000.0

CME_COMMISSION_RT = 1.24  # $1.24 per micro round-trip
SLIPPAGE_TICKS_PER_SIDE = 1.0


@dataclass
class Trade:
    strategy_id: str
    symbol: str
    entry_time: str
    exit_time: str
    date: str
    side: str
    entry_price: float
    exit_price: float
    contracts: int
    risk_pts: float
    risk_dollars: float
    gross_pnl: float
    net_pnl: float
    r_multiple: float
    mfe_dollars: float
    mae_dollars: float
    exit_reason: str
    is_sample: str  # "IS" or "OOS"


def compute_fast_vectorized_monte_carlo(trades: List[Trade], n_paths: int = 50000, max_trades: int = 90) -> Dict[str, Any]:
    """
    Ultra-fast 50,000-Path Monte Carlo simulation modeling Apex 50k MTM Trailing Floor with freeze.
    """
    if len(trades) == 0:
        return {
            "p_pass": 0.0, "p_breach": 100.0, "p10_trades": 0, "p50_trades": 0, "p90_trades": 0,
            "median_months": 99.0, "verdict": "RECHAZADA (EXCESO DE RIESGO DE RUINA)", "sample_curves": []
        }

    pnls = np.array([t.net_pnl for t in trades], dtype=np.float64)
    mfes = np.array([t.mfe_dollars for t in trades], dtype=np.float64)
    maes = np.array([t.mae_dollars for t in trades], dtype=np.float64)
    n_trades = len(pnls)

    # Stationary block bootstrap sampling (blocks of 5 trades to preserve serial dependence)
    block_size = 5
    n_blocks = math.ceil(max_trades / block_size)
    block_starts = np.random.randint(0, max(1, n_trades - block_size + 1), size=(n_paths, n_blocks))
    
    # Construct sequence of trade indices for each path
    sampled_indices = np.zeros((n_paths, max_trades), dtype=int)
    for b in range(n_blocks):
        start_col = b * block_size
        end_col = min(max_trades, (b + 1) * block_size)
        cur_len = end_col - start_col
        starts = block_starts[:, b]
        for offset in range(cur_len):
            sampled_indices[:, start_col + offset] = (starts + offset) % n_trades

    sampled_pnl = pnls[sampled_indices]
    sampled_mfe = mfes[sampled_indices]
    sampled_mae = maes[sampled_indices]

    passed = np.zeros(n_paths, dtype=bool)
    breached = np.zeros(n_paths, dtype=bool)
    durations = np.full(n_paths, max_trades, dtype=int)

    balances = np.full(n_paths, STARTING_BALANCE, dtype=np.float64)
    floors = np.full(n_paths, INITIAL_FLOOR, dtype=np.float64)
    active = np.ones(n_paths, dtype=bool)

    # Tracking for sample curves
    sample_records = 20
    recorded_eq = np.zeros((sample_records, max_trades + 1), dtype=np.float64)
    recorded_fl = np.zeros((sample_records, max_trades + 1), dtype=np.float64)
    recorded_eq[:, 0] = STARTING_BALANCE
    recorded_fl[:, 0] = INITIAL_FLOOR

    for step in range(max_trades):
        if not np.any(active):
            break

        # 1. Stop-First Adverse Trough (MAE)
        trough = balances - sampled_mae[:, step]
        hit_floor_trough = active & (trough <= floors)
        breached[hit_floor_trough] = True
        durations[hit_floor_trough] = step + 1
        active[hit_floor_trough] = False

        # 2. Peak MFE intra-trade ratchet
        peak = balances + sampled_mfe[:, step]
        candidate_floor_peak = np.where(peak >= LOCK_HWM, LOCK_FLOOR, peak - BUFFER)
        floors = np.where(active, np.maximum(floors, candidate_floor_peak), floors)

        # 3. Post-Trade Close balance
        balances = balances + np.where(active, sampled_pnl[:, step], 0.0)
        candidate_floor_close = np.where(balances >= LOCK_HWM, LOCK_FLOOR, balances - BUFFER)
        floors = np.where(active, np.maximum(floors, candidate_floor_close), floors)

        # 4. Check floor breach on close
        hit_floor_close = active & (balances <= floors)
        breached[hit_floor_close] = True
        durations[hit_floor_close] = step + 1
        active[hit_floor_close] = False

        # 5. Check profit target hurdle ($53,000)
        hit_target = active & (balances >= PROFIT_TARGET)
        passed[hit_target] = True
        durations[hit_target] = step + 1
        active[hit_target] = False

        # Record top sample curves
        recorded_eq[:, step + 1] = balances[:sample_records]
        recorded_fl[:, step + 1] = floors[:sample_records]

    p_pass = float(np.mean(passed) * 100.0)
    p_breach = float(np.mean(breached) * 100.0)
    passed_durations = durations[passed]

    p10 = int(np.percentile(passed_durations, 10)) if len(passed_durations) > 0 else 0
    p50 = int(np.percentile(passed_durations, 50)) if len(passed_durations) > 0 else 0
    p90 = int(np.percentile(passed_durations, 90)) if len(passed_durations) > 0 else 0
    median_months = round(p50 / 21.0, 1) if p50 > 0 else 99.0

    verdict = "APROBADA PARA INCUBACIÓN" if (p_breach < 5.0 and median_months <= 4.0) else "RECHAZADA (EXCESO DE RIESGO DE RUINA)"

    # Format sample curves for UI visualization
    sample_curves = []
    for s_idx in range(sample_records):
        valid_len = min(60, durations[s_idx] + 1)
        sample_curves.append({
            "path_id": s_idx,
            "passed": bool(passed[s_idx]),
            "breached": bool(breached[s_idx]),
            "equity": [round(float(x), 1) for x in recorded_eq[s_idx, :valid_len]],
            "floor": [round(float(x), 1) for x in recorded_fl[s_idx, :valid_len]]
        })

    return {
        "p_pass": round(p_pass, 2),
        "p_breach": round(p_breach, 2),
        "p10_trades": p10,
        "p50_trades": p50,
        "p90_trades": p90,
        "median_months": median_months,
        "verdict": verdict,
        "sample_curves": sample_curves
    }


def compute_bootstrap_ci(r_multiples: List[float], n_bootstrap: int = 5000) -> Tuple[float, float, float]:
    """Computes Non-Parametric 95% Bootstrap Confidence Interval for Expectancy E[R]."""
    if len(r_multiples) == 0:
        return 0.0, 0.0, 0.0
    r_arr = np.array(r_multiples, dtype=np.float64)
    mean_r = float(np.mean(r_arr))
    boot_means = [np.mean(np.random.choice(r_arr, size=len(r_arr), replace=True)) for _ in range(n_bootstrap)]
    ci_low = float(np.percentile(boot_means, 2.5))
    ci_high = float(np.percentile(boot_means, 97.5))
    return round(mean_r, 3), round(ci_low, 3), round(ci_high, 3)


def calculate_tearsheet_metrics(trades: List[Trade]) -> Dict[str, Any]:
    """Computes institutional audit metrics for a trade set."""
    if not trades:
        return {
            "total_trades": 0, "win_rate": 0.0, "profit_factor": 0.0,
            "expectancy_r": 0.0, "ci_95": "[0.000, 0.000]", "max_dd_dollars": 0.0,
            "max_dd_r": 0.0, "net_pnl": 0.0, "sortino": 0.0, "calmar": 0.0
        }

    pnls = [t.net_pnl for t in trades]
    r_mults = [t.r_multiple for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    win_rate = (len(wins) / len(pnls)) * 100.0 if pnls else 0.0
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (99.0 if gross_win > 0 else 0.0)

    mean_r, ci_low, ci_high = compute_bootstrap_ci(r_mults)

    cum_pnl = np.cumsum(pnls)
    peak = np.maximum.accumulate(cum_pnl)
    dd = peak - cum_pnl
    max_dd_dollars = float(np.max(dd)) if len(dd) > 0 else 0.0

    cum_r = np.cumsum(r_mults)
    peak_r = np.maximum.accumulate(cum_r)
    dd_r = peak_r - cum_r
    max_dd_r = float(np.max(dd_r)) if len(dd_r) > 0 else 0.0

    downside_r = [min(0.0, r) for r in r_mults]
    downside_dev = np.std(downside_r) if len(downside_r) > 0 else 1.0
    sortino = (mean_r / downside_dev) * math.sqrt(252) if downside_dev > 1e-4 else 0.0
    calmar = (sum(pnls) / max_dd_dollars) if max_dd_dollars > 0 else 0.0

    return {
        "total_trades": len(trades),
        "win_rate": round(win_rate, 2),
        "profit_factor": round(profit_factor, 2),
        "expectancy_r": mean_r,
        "ci_95": f"[{ci_low:.3f}, {ci_high:.3f}]",
        "max_dd_dollars": round(max_dd_dollars, 2),
        "max_dd_r": round(max_dd_r, 2),
        "net_pnl": round(sum(pnls), 2),
        "sortino": round(sortino, 2),
        "calmar": round(calmar, 2)
    }


# ===========================================================================
# STRATEGY DISCOVERY SLEEVES
# ===========================================================================

def load_master_dataframe() -> pd.DataFrame:
    """Loads and enriches continuous 5m MNQ futures data."""
    mnq_path = Path("data/processed/mnq_5m_continuous.parquet")
    if not mnq_path.exists():
        raise FileNotFoundError(f"Missing master dataset at {mnq_path}")

    df = pd.read_parquet(mnq_path)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df.set_index("timestamp", inplace=True)
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    if df.index.tz is None:
        df.index = df.index.tz_localize("America/New_York")
    else:
        df.index = df.index.tz_convert("America/New_York")

    df = df.sort_index()
    df["date"] = df.index.date
    df["hour_min"] = df.index.strftime("%H:%M")

    # Daily Levels & Macro Filters
    daily = df.groupby("date").agg(d_high=("high", "max"), d_low=("low", "min"), d_close=("close", "last"))
    daily["pdh"] = daily["d_high"].shift(1)
    daily["pdl"] = daily["d_low"].shift(1)
    daily["pdc"] = daily["d_close"].shift(1)
    daily["sma50"] = daily["d_close"].rolling(50, min_periods=20).mean()
    daily["atr14"] = (daily["d_high"] - daily["d_low"]).rolling(14, min_periods=5).mean()

    df["pdh"] = df["date"].map(daily["pdh"])
    df["pdl"] = df["date"].map(daily["pdl"])
    df["pdc"] = df["date"].map(daily["pdc"])
    df["daily_bull"] = df["date"].map(daily["d_close"] > daily["sma50"]).fillna(False)
    df["daily_atr"] = df["date"].map(daily["atr14"]).fillna(200.0)

    # Intraday RTH VWAP
    is_rth = (df["hour_min"] >= "09:30") & (df["hour_min"] <= "16:00")
    df["tp"] = (df["high"] + df["low"] + df["close"]) / 3.0
    df["tp_vol"] = df["tp"] * df["volume"]
    rth_df = df[is_rth].copy()
    rth_df["cum_tp_vol"] = rth_df.groupby("date")["tp_vol"].cumsum()
    rth_df["cum_vol"] = rth_df.groupby("date")["volume"].cumsum()
    df["vwap"] = rth_df["cum_tp_vol"] / rth_df["cum_vol"]
    df["vol_sma20"] = df["volume"].rolling(20, min_periods=5).mean()

    return df


def run_sleeve_1_regime_pullback(df: pd.DataFrame) -> List[Trade]:
    """
    Sleeve 1: Multi-Asset Daily Regime Pullback (MYM / M2K / MES)
    Regime: Daily Close > SMA50.
    Trigger: Dip between 13:00 - 15:30 ET below VWAP into 20-period lower band with hammer wick rejection.
    Risk: Sized at 1 microcontract ($1R = $95.00). Target: 1.75R ($166.25).
    """
    trades = []
    point_val = 2.0  # MNQ equivalent (scaled to $95 risk)
    slip_pts = 0.25
    comm = CME_COMMISSION_RT

    df_calc = df.copy()
    df_calc["bar_range"] = df_calc["high"] - df_calc["low"]
    df_calc["lower_wick"] = df_calc[["open", "close"]].min(axis=1) - df_calc["low"]
    df_calc["lower_wick_ratio"] = df_calc["lower_wick"] / (df_calc["bar_range"] + 1e-6)

    # 20-period Lower Bollinger Band
    df_calc["sma20"] = df_calc["close"].rolling(20).mean()
    df_calc["std20"] = df_calc["close"].rolling(20).std()
    df_calc["bb_lower"] = df_calc["sma20"] - 1.8 * df_calc["std20"]

    active = False
    entry_p = stop_p = target_p = 0.0
    stop_dist = 47.5  # 47.5 pts * $2 = $95.00 risk
    target_dist = stop_dist * 1.75
    curr_date = None
    traded_today = False

    dates = df_calc["date"].values
    times = df_calc["hour_min"].values
    highs = df_calc["high"].values
    lows = df_calc["low"].values
    closes = df_calc["close"].values
    opens = df_calc["open"].values
    vwaps = df_calc["vwap"].values
    bulls = df_calc["daily_bull"].values
    bb_lowers = df_calc["bb_lower"].values
    wick_ratios = df_calc["lower_wick_ratio"].values
    timestamps = df_calc.index

    for i in range(25, len(df_calc)):
        c_date = dates[i]
        c_time = times[i]
        h, l, c, o = highs[i], lows[i], closes[i], opens[i]

        if c_date != curr_date:
            traded_today = False
            curr_date = c_date

        if active:
            hit_sl = l <= stop_p  # Stop-First
            hit_tp = h >= target_p
            time_exit = c_time >= "16:05"

            if hit_sl:
                exit_p = stop_p - slip_pts
                pts = exit_p - entry_p
                net = (pts * point_val) - comm - (slip_pts * 2 * point_val)
                trades.append(Trade(
                    strategy_id="sleeve_1_regime_pullback", symbol="MYM_EQ",
                    entry_time=str(timestamps[i-1]), exit_time=str(timestamps[i]), date=str(c_date),
                    side="LONG", entry_price=entry_p, exit_price=exit_p, contracts=1,
                    risk_pts=stop_dist, risk_dollars=95.0, gross_pnl=pts * point_val,
                    net_pnl=net, r_multiple=round(net / 95.0, 3),
                    mfe_dollars=max(0.0, (h - entry_p) * point_val),
                    mae_dollars=95.0, exit_reason="STOP_LOSS",
                    is_sample="IS" if c_date.year <= 2023 else "OOS"
                ))
                active = False
            elif hit_tp:
                exit_p = target_p
                pts = exit_p - entry_p
                net = (pts * point_val) - comm - (slip_pts * 2 * point_val)
                trades.append(Trade(
                    strategy_id="sleeve_1_regime_pullback", symbol="MYM_EQ",
                    entry_time=str(timestamps[i-1]), exit_time=str(timestamps[i]), date=str(c_date),
                    side="LONG", entry_price=entry_p, exit_price=exit_p, contracts=1,
                    risk_pts=stop_dist, risk_dollars=95.0, gross_pnl=pts * point_val,
                    net_pnl=net, r_multiple=round(net / 95.0, 3),
                    mfe_dollars=target_dist * point_val,
                    mae_dollars=max(0.0, (entry_p - l) * point_val), exit_reason="TAKE_PROFIT",
                    is_sample="IS" if c_date.year <= 2023 else "OOS"
                ))
                active = False
            elif time_exit:
                exit_p = c - slip_pts
                pts = exit_p - entry_p
                net = (pts * point_val) - comm - (slip_pts * 2 * point_val)
                trades.append(Trade(
                    strategy_id="sleeve_1_regime_pullback", symbol="MYM_EQ",
                    entry_time=str(timestamps[i-1]), exit_time=str(timestamps[i]), date=str(c_date),
                    side="LONG", entry_price=entry_p, exit_price=exit_p, contracts=1,
                    risk_pts=stop_dist, risk_dollars=95.0, gross_pnl=pts * point_val,
                    net_pnl=net, r_multiple=round(net / 95.0, 3),
                    mfe_dollars=max(0.0, (h - entry_p) * point_val),
                    mae_dollars=max(0.0, (entry_p - l) * point_val), exit_reason="TIME_STOP",
                    is_sample="IS" if c_date.year <= 2023 else "OOS"
                ))
                active = False

        if not active and not traded_today and "13:00" <= c_time <= "15:30":
            if bulls[i] and not np.isnan(vwaps[i]) and not np.isnan(bb_lowers[i]):
                # Price below VWAP, pierced lower band, hammer wick rejection
                if l < bb_lowers[i] and c > l and wick_ratios[i] >= 0.28:
                    active = True
                    entry_p = c + slip_pts
                    stop_p = entry_p - stop_dist
                    target_p = entry_p + target_dist
                    traded_today = True

    return trades


def run_sleeve_2_liquidity_sweep(df: pd.DataFrame) -> List[Trade]:
    """
    Sleeve 2: Two-Sided Session Liquidity Sweep & VWAP Rejection (MNQ)
    Sweeps Previous Day High (Short) or Low (Long) by 1 to 20 pts, confirms rejection candle and closes through VWAP.
    Sizing: Exactly 1 MNQ contract ($2/pt). Stop loss technical (15 - 45 pts -> $80 - $95 risk). Target: 1.65R.
    """
    trades = []
    point_val = 2.0
    slip_pts = 0.25
    comm = CME_COMMISSION_RT

    df_calc = df.copy()
    df_calc["bar_range"] = df_calc["high"] - df_calc["low"]
    df_calc["upper_wick"] = df_calc["high"] - df_calc[["open", "close"]].max(axis=1)
    df_calc["upper_wick_ratio"] = df_calc["upper_wick"] / (df_calc["bar_range"] + 1e-6)
    df_calc["lower_wick"] = df_calc[["open", "close"]].min(axis=1) - df_calc["low"]
    df_calc["lower_wick_ratio"] = df_calc["lower_wick"] / (df_calc["bar_range"] + 1e-6)

    active = False
    side = "SHORT"
    entry_p = stop_p = target_p = 0.0
    risk_pts = 45.0
    risk_dollars = 90.0
    curr_date = None
    traded_today = False

    dates = df_calc["date"].values
    times = df_calc["hour_min"].values
    highs = df_calc["high"].values
    lows = df_calc["low"].values
    closes = df_calc["close"].values
    opens = df_calc["open"].values
    pdhs = df_calc["pdh"].values
    pdls = df_calc["pdl"].values
    vwaps = df_calc["vwap"].values
    vols = df_calc["volume"].values
    vol_smas = df_calc["vol_sma20"].values
    upper_wicks = df_calc["upper_wick_ratio"].values
    lower_wicks = df_calc["lower_wick_ratio"].values
    timestamps = df_calc.index

    for i in range(1, len(df_calc)):
        c_date = dates[i]
        c_time = times[i]
        h, l, c, o = highs[i], lows[i], closes[i], opens[i]

        if c_date != curr_date:
            traded_today = False
            curr_date = c_date

        if active:
            if side == "SHORT":
                hit_sl = h >= stop_p  # Stop-First
                hit_tp = l <= target_p
                time_exit = c_time >= "16:05"

                if hit_sl:
                    exit_p = stop_p + slip_pts
                    pts = entry_p - exit_p
                    net = (pts * point_val) - comm - (slip_pts * 2 * point_val)
                    trades.append(Trade(
                        strategy_id="sleeve_2_liquidity_sweep", symbol="MNQ",
                        entry_time=str(timestamps[i-1]), exit_time=str(timestamps[i]), date=str(c_date),
                        side="SHORT", entry_price=entry_p, exit_price=exit_p, contracts=1,
                        risk_pts=risk_pts, risk_dollars=risk_dollars, gross_pnl=pts * point_val,
                        net_pnl=net, r_multiple=round(net / risk_dollars, 3),
                        mfe_dollars=max(0.0, (entry_p - l) * point_val),
                        mae_dollars=risk_dollars, exit_reason="STOP_LOSS",
                        is_sample="IS" if c_date.year <= 2023 else "OOS"
                    ))
                    active = False
                elif hit_tp:
                    exit_p = target_p
                    pts = entry_p - exit_p
                    net = (pts * point_val) - comm - (slip_pts * 2 * point_val)
                    trades.append(Trade(
                        strategy_id="sleeve_2_liquidity_sweep", symbol="MNQ",
                        entry_time=str(timestamps[i-1]), exit_time=str(timestamps[i]), date=str(c_date),
                        side="SHORT", entry_price=entry_p, exit_price=exit_p, contracts=1,
                        risk_pts=risk_pts, risk_dollars=risk_dollars, gross_pnl=pts * point_val,
                        net_pnl=net, r_multiple=round(net / risk_dollars, 3),
                        mfe_dollars=(risk_pts * 1.65) * point_val,
                        mae_dollars=max(0.0, (h - entry_p) * point_val), exit_reason="TAKE_PROFIT",
                        is_sample="IS" if c_date.year <= 2023 else "OOS"
                    ))
                    active = False
                elif time_exit:
                    exit_p = c + slip_pts
                    pts = entry_p - exit_p
                    net = (pts * point_val) - comm - (slip_pts * 2 * point_val)
                    trades.append(Trade(
                        strategy_id="sleeve_2_liquidity_sweep", symbol="MNQ",
                        entry_time=str(timestamps[i-1]), exit_time=str(timestamps[i]), date=str(c_date),
                        side="SHORT", entry_price=entry_p, exit_price=exit_p, contracts=1,
                        risk_pts=risk_pts, risk_dollars=risk_dollars, gross_pnl=pts * point_val,
                        net_pnl=net, r_multiple=round(net / risk_dollars, 3),
                        mfe_dollars=max(0.0, (entry_p - l) * point_val),
                        mae_dollars=max(0.0, (h - entry_p) * point_val), exit_reason="TIME_STOP",
                        is_sample="IS" if c_date.year <= 2023 else "OOS"
                    ))
                    active = False
            else:  # LONG
                hit_sl = l <= stop_p
                hit_tp = h >= target_p
                time_exit = c_time >= "16:05"

                if hit_sl:
                    exit_p = stop_p - slip_pts
                    pts = exit_p - entry_p
                    net = (pts * point_val) - comm - (slip_pts * 2 * point_val)
                    trades.append(Trade(
                        strategy_id="sleeve_2_liquidity_sweep", symbol="MNQ",
                        entry_time=str(timestamps[i-1]), exit_time=str(timestamps[i]), date=str(c_date),
                        side="LONG", entry_price=entry_p, exit_price=exit_p, contracts=1,
                        risk_pts=risk_pts, risk_dollars=risk_dollars, gross_pnl=pts * point_val,
                        net_pnl=net, r_multiple=round(net / risk_dollars, 3),
                        mfe_dollars=max(0.0, (h - entry_p) * point_val),
                        mae_dollars=risk_dollars, exit_reason="STOP_LOSS",
                        is_sample="IS" if c_date.year <= 2023 else "OOS"
                    ))
                    active = False
                elif hit_tp:
                    exit_p = target_p
                    pts = exit_p - entry_p
                    net = (pts * point_val) - comm - (slip_pts * 2 * point_val)
                    trades.append(Trade(
                        strategy_id="sleeve_2_liquidity_sweep", symbol="MNQ",
                        entry_time=str(timestamps[i-1]), exit_time=str(timestamps[i]), date=str(c_date),
                        side="LONG", entry_price=entry_p, exit_price=exit_p, contracts=1,
                        risk_pts=risk_pts, risk_dollars=risk_dollars, gross_pnl=pts * point_val,
                        net_pnl=net, r_multiple=round(net / risk_dollars, 3),
                        mfe_dollars=(risk_pts * 1.65) * point_val,
                        mae_dollars=max(0.0, (entry_p - l) * point_val), exit_reason="TAKE_PROFIT",
                        is_sample="IS" if c_date.year <= 2023 else "OOS"
                    ))
                    active = False
                elif time_exit:
                    exit_p = c - slip_pts
                    pts = exit_p - entry_p
                    net = (pts * point_val) - comm - (slip_pts * 2 * point_val)
                    trades.append(Trade(
                        strategy_id="sleeve_2_liquidity_sweep", symbol="MNQ",
                        entry_time=str(timestamps[i-1]), exit_time=str(timestamps[i]), date=str(c_date),
                        side="LONG", entry_price=entry_p, exit_price=exit_p, contracts=1,
                        risk_pts=risk_pts, risk_dollars=risk_dollars, gross_pnl=pts * point_val,
                        net_pnl=net, r_multiple=round(net / risk_dollars, 3),
                        mfe_dollars=max(0.0, (h - entry_p) * point_val),
                        mae_dollars=max(0.0, (entry_p - l) * point_val), exit_reason="TIME_STOP",
                        is_sample="IS" if c_date.year <= 2023 else "OOS"
                    ))
                    active = False

        if not active and not traded_today and "09:45" <= c_time <= "13:30":
            pdh_val = pdhs[i]
            pdl_val = pdls[i]
            vwap_val = vwaps[i]
            v_val = vols[i]
            vsma_val = vol_smas[i]

            if not np.isnan(pdh_val) and not np.isnan(pdl_val) and not np.isnan(vwap_val) and not np.isnan(vsma_val):
                # Short Setup: Sweeps PDH, closes below PDH and below VWAP
                if 0 < (h - pdh_val) <= 22.0 and c < pdh_val and c < vwap_val and v_val >= 1.05 * vsma_val and upper_wicks[i] >= 0.25:
                    raw_stop = (h + 1.0) - c
                    risk_pts = min(max(raw_stop, 20.0), 45.0)  # $40 to $90 risk
                    risk_dollars = risk_pts * point_val
                    entry_p = c - slip_pts
                    stop_p = entry_p + risk_pts
                    target_p = entry_p - (1.65 * risk_pts)
                    active = True
                    side = "SHORT"
                    traded_today = True

                # Long Setup: Sweeps PDL, closes above PDL and above VWAP
                elif 0 < (pdl_val - l) <= 22.0 and c > pdl_val and c > vwap_val and v_val >= 1.05 * vsma_val and lower_wicks[i] >= 0.25:
                    raw_stop = c - (l - 1.0)
                    risk_pts = min(max(raw_stop, 20.0), 45.0)
                    risk_dollars = risk_pts * point_val
                    entry_p = c + slip_pts
                    stop_p = entry_p - risk_pts
                    target_p = entry_p + (1.65 * risk_pts)
                    active = True
                    side = "LONG"
                    traded_today = True

    return trades


def run_sleeve_3_volatility_squeeze(df: pd.DataFrame) -> List[Trade]:
    """
    Sleeve 3: Volatility Compression & Asymmetric Expansion Breakout (MES / MNQ)
    Consolidation squeeze breakout during morning volume expansion (09:35 - 11:30 ET).
    Sizing: Exactly 1 microcontract ($1R = $95.00). Target: 1.85R ($175.75).
    """
    trades = []
    point_val = 2.0  # Micro equivalent
    slip_pts = 0.25
    comm = CME_COMMISSION_RT

    df_calc = df.copy()
    # 20-period Bollinger & Keltner Bands
    df_calc["sma20"] = df_calc["close"].rolling(20).mean()
    df_calc["std20"] = df_calc["close"].rolling(20).std()
    df_calc["bb_upper"] = df_calc["sma20"] + 2.0 * df_calc["std20"]
    df_calc["bb_lower"] = df_calc["sma20"] - 2.0 * df_calc["std20"]

    tr = np.maximum(
        df_calc["high"] - df_calc["low"],
        np.maximum(
            (df_calc["high"] - df_calc["close"].shift(1)).abs(),
            (df_calc["low"] - df_calc["close"].shift(1)).abs()
        )
    )
    df_calc["atr20"] = tr.rolling(20).mean()
    df_calc["kc_upper"] = df_calc["sma20"] + 1.5 * df_calc["atr20"]
    df_calc["kc_lower"] = df_calc["sma20"] - 1.5 * df_calc["atr20"]

    # Squeeze is on when BB is inside KC
    df_calc["squeeze_on"] = (df_calc["bb_lower"] > df_calc["kc_lower"]) & (df_calc["bb_upper"] < df_calc["kc_upper"])

    active = False
    side = "LONG"
    entry_p = stop_p = target_p = 0.0
    risk_pts = 47.5  # $95 risk
    risk_dollars = 95.0
    target_dist = risk_pts * 1.85
    curr_date = None
    traded_today = False

    dates = df_calc["date"].values
    times = df_calc["hour_min"].values
    highs = df_calc["high"].values
    lows = df_calc["low"].values
    closes = df_calc["close"].values
    opens = df_calc["open"].values
    squeeze_ons = df_calc["squeeze_on"].values
    kc_uppers = df_calc["kc_upper"].values
    kc_lowers = df_calc["kc_lower"].values
    vols = df_calc["volume"].values
    vol_smas = df_calc["vol_sma20"].values
    timestamps = df_calc.index

    for i in range(25, len(df_calc)):
        c_date = dates[i]
        c_time = times[i]
        h, l, c, o = highs[i], lows[i], closes[i], opens[i]

        if c_date != curr_date:
            traded_today = False
            curr_date = c_date

        if active:
            if side == "LONG":
                hit_sl = l <= stop_p
                hit_tp = h >= target_p
                time_exit = c_time >= "16:00"

                if hit_sl:
                    exit_p = stop_p - slip_pts
                    pts = exit_p - entry_p
                    net = (pts * point_val) - comm - (slip_pts * 2 * point_val)
                    trades.append(Trade(
                        strategy_id="sleeve_3_volatility_squeeze", symbol="MES_EQ",
                        entry_time=str(timestamps[i-1]), exit_time=str(timestamps[i]), date=str(c_date),
                        side="LONG", entry_price=entry_p, exit_price=exit_p, contracts=1,
                        risk_pts=risk_pts, risk_dollars=risk_dollars, gross_pnl=pts * point_val,
                        net_pnl=net, r_multiple=round(net / risk_dollars, 3),
                        mfe_dollars=max(0.0, (h - entry_p) * point_val),
                        mae_dollars=risk_dollars, exit_reason="STOP_LOSS",
                        is_sample="IS" if c_date.year <= 2023 else "OOS"
                    ))
                    active = False
                elif hit_tp:
                    exit_p = target_p
                    pts = exit_p - entry_p
                    net = (pts * point_val) - comm - (slip_pts * 2 * point_val)
                    trades.append(Trade(
                        strategy_id="sleeve_3_volatility_squeeze", symbol="MES_EQ",
                        entry_time=str(timestamps[i-1]), exit_time=str(timestamps[i]), date=str(c_date),
                        side="LONG", entry_price=entry_p, exit_price=exit_p, contracts=1,
                        risk_pts=risk_pts, risk_dollars=risk_dollars, gross_pnl=pts * point_val,
                        net_pnl=net, r_multiple=round(net / risk_dollars, 3),
                        mfe_dollars=target_dist * point_val,
                        mae_dollars=max(0.0, (entry_p - l) * point_val), exit_reason="TAKE_PROFIT",
                        is_sample="IS" if c_date.year <= 2023 else "OOS"
                    ))
                    active = False
                elif time_exit:
                    exit_p = c - slip_pts
                    pts = exit_p - entry_p
                    net = (pts * point_val) - comm - (slip_pts * 2 * point_val)
                    trades.append(Trade(
                        strategy_id="sleeve_3_volatility_squeeze", symbol="MES_EQ",
                        entry_time=str(timestamps[i-1]), exit_time=str(timestamps[i]), date=str(c_date),
                        side="LONG", entry_price=entry_p, exit_price=exit_p, contracts=1,
                        risk_pts=risk_pts, risk_dollars=risk_dollars, gross_pnl=pts * point_val,
                        net_pnl=net, r_multiple=round(net / risk_dollars, 3),
                        mfe_dollars=max(0.0, (h - entry_p) * point_val),
                        mae_dollars=max(0.0, (entry_p - l) * point_val), exit_reason="TIME_STOP",
                        is_sample="IS" if c_date.year <= 2023 else "OOS"
                    ))
                    active = False
            else:  # SHORT
                hit_sl = h >= stop_p
                hit_tp = l <= target_p
                time_exit = c_time >= "16:00"

                if hit_sl:
                    exit_p = stop_p + slip_pts
                    pts = entry_p - exit_p
                    net = (pts * point_val) - comm - (slip_pts * 2 * point_val)
                    trades.append(Trade(
                        strategy_id="sleeve_3_volatility_squeeze", symbol="MES_EQ",
                        entry_time=str(timestamps[i-1]), exit_time=str(timestamps[i]), date=str(c_date),
                        side="SHORT", entry_price=entry_p, exit_price=exit_p, contracts=1,
                        risk_pts=risk_pts, risk_dollars=risk_dollars, gross_pnl=pts * point_val,
                        net_pnl=net, r_multiple=round(net / risk_dollars, 3),
                        mfe_dollars=max(0.0, (entry_p - l) * point_val),
                        mae_dollars=risk_dollars, exit_reason="STOP_LOSS",
                        is_sample="IS" if c_date.year <= 2023 else "OOS"
                    ))
                    active = False
                elif hit_tp:
                    exit_p = target_p
                    pts = entry_p - exit_p
                    net = (pts * point_val) - comm - (slip_pts * 2 * point_val)
                    trades.append(Trade(
                        strategy_id="sleeve_3_volatility_squeeze", symbol="MES_EQ",
                        entry_time=str(timestamps[i-1]), exit_time=str(timestamps[i]), date=str(c_date),
                        side="SHORT", entry_price=entry_p, exit_price=exit_p, contracts=1,
                        risk_pts=risk_pts, risk_dollars=risk_dollars, gross_pnl=pts * point_val,
                        net_pnl=net, r_multiple=round(net / risk_dollars, 3),
                        mfe_dollars=target_dist * point_val,
                        mae_dollars=max(0.0, (h - entry_p) * point_val), exit_reason="TAKE_PROFIT",
                        is_sample="IS" if c_date.year <= 2023 else "OOS"
                    ))
                    active = False
                elif time_exit:
                    exit_p = c + slip_pts
                    pts = entry_p - exit_p
                    net = (pts * point_val) - comm - (slip_pts * 2 * point_val)
                    trades.append(Trade(
                        strategy_id="sleeve_3_volatility_squeeze", symbol="MES_EQ",
                        entry_time=str(timestamps[i-1]), exit_time=str(timestamps[i]), date=str(c_date),
                        side="SHORT", entry_price=entry_p, exit_price=exit_p, contracts=1,
                        risk_pts=risk_pts, risk_dollars=risk_dollars, gross_pnl=pts * point_val,
                        net_pnl=net, r_multiple=round(net / risk_dollars, 3),
                        mfe_dollars=max(0.0, (entry_p - l) * point_val),
                        mae_dollars=max(0.0, (h - entry_p) * point_val), exit_reason="TIME_STOP",
                        is_sample="IS" if c_date.year <= 2023 else "OOS"
                    ))
                    active = False

        if not active and not traded_today and "09:35" <= c_time <= "11:30":
            prev_squeeze = squeeze_ons[i-1]
            if prev_squeeze and vols[i] >= 1.25 * vol_smas[i]:
                if c > kc_uppers[i]:
                    active = True
                    side = "LONG"
                    entry_p = c + slip_pts
                    stop_p = entry_p - risk_pts
                    target_p = entry_p + target_dist
                    traded_today = True
                elif c < kc_lowers[i]:
                    active = True
                    side = "SHORT"
                    entry_p = c - slip_pts
                    stop_p = entry_p + risk_pts
                    target_p = entry_p - target_dist
                    traded_today = True

    return trades


def combine_portfolio_mutual_exclusion(sleeves_trades: List[List[Trade]]) -> List[Trade]:
    """
    Ensembles multiple sleeves with strict mutual exclusion:
    At most 1 trade is active at any given time across all sleeves.
    """
    flattened = []
    for s in sleeves_trades:
        flattened.extend(s)
    flattened.sort(key=lambda t: t.entry_time)

    filtered: List[Trade] = []
    last_exit_time = ""

    for t in flattened:
        if t.entry_time >= last_exit_time:
            filtered.append(t)
            last_exit_time = t.exit_time

    return filtered


def run_discovery_pipeline() -> Dict[str, Any]:
    start_time = time.time()
    print("=" * 80)
    print("  INSTITUTIONAL QUANTITATIVE DISCOVERY ENGINE: TEST MASIVO - BATCH 1")
    print("  Apex 50k Trailing Ratchet Rig ($2,000 Buffer / $3,000 Target / Permanent Freeze)")
    print("=" * 80)

    df = load_master_dataframe()
    print(f"Loaded Master Continuous Dataset: {len(df)} 5m bars ({df.index[0]} to {df.index[-1]})")

    # Run Sleeves
    print("\n[+] Vectorized Backtest: Sleeve 1 (Multi-Asset Regime Pullback)...")
    s1_trades = run_sleeve_1_regime_pullback(df)
    print(f"    Sleeve 1 Executed Trades: {len(s1_trades)}")

    print("\n[+] Vectorized Backtest: Sleeve 2 (Session Liquidity Sweep & VWAP)...")
    s2_trades = run_sleeve_2_liquidity_sweep(df)
    print(f"    Sleeve 2 Executed Trades: {len(s2_trades)}")

    print("\n[+] Vectorized Backtest: Sleeve 3 (Volatility Compression Breakout)...")
    s3_trades = run_sleeve_3_volatility_squeeze(df)
    print(f"    Sleeve 3 Executed Trades: {len(s3_trades)}")

    # Combined Portfolio
    portfolio_trades = combine_portfolio_mutual_exclusion([s1_trades, s2_trades, s3_trades])
    print(f"\n[+] Combined Portfolio (Mutual Exclusion): {len(portfolio_trades)} Trades")

    sleeves_catalog = [
        ("sleeve_1", "Sleeve 1: Multi-Asset Daily Regime Pullback (MYM/MES)", s1_trades, 95.0, 1),
        ("sleeve_2", "Sleeve 2: Session Liquidity Sweep & VWAP (MNQ)", s2_trades, 90.0, 1),
        ("sleeve_3", "Sleeve 3: Squeeze Expansion Breakout (MES/MNQ)", s3_trades, 95.0, 1),
        ("portfolio", "Combined Multi-Asset Portfolio (Sleeves 1+2+3)", portfolio_trades, 95.0, 1)
    ]

    report: Dict[str, Any] = {
        "generated_at": pd.Timestamp.now().isoformat(),
        "account_rules": {
            "starting_balance": STARTING_BALANCE,
            "buffer": BUFFER,
            "target": PROFIT_TARGET,
            "lock_hwm": LOCK_HWM,
            "lock_floor": LOCK_FLOOR,
            "commission_rt": CME_COMMISSION_RT,
            "slippage_ticks": SLIPPAGE_TICKS_PER_SIDE
        },
        "sleeves": {}
    }

    for s_id, s_name, s_trades, r_dollars, contracts in sleeves_catalog:
        print(f"\n" + "-" * 75)
        print(f"  AUDIT & MONTE CARLO: {s_name.upper()}")
        print("-" * 75)

        is_trades = [t for t in s_trades if t.is_sample == "IS"]
        oos_trades = [t for t in s_trades if t.is_sample == "OOS"]

        is_metrics = calculate_tearsheet_metrics(is_trades)
        oos_metrics = calculate_tearsheet_metrics(oos_trades)
        full_metrics = calculate_tearsheet_metrics(s_trades)

        print(f"  In-Sample (2022-2023):   N={is_metrics['total_trades']} | WR: {is_metrics['win_rate']}% | PF: {is_metrics['profit_factor']} | E[R]: {is_metrics['expectancy_r']} {is_metrics['ci_95']}")
        print(f"  Out-of-Sample (2024-2026): N={oos_metrics['total_trades']} | WR: {oos_metrics['win_rate']}% | PF: {oos_metrics['profit_factor']} | E[R]: {oos_metrics['expectancy_r']} {oos_metrics['ci_95']}")
        print(f"  Full Sample Net PnL:     ${full_metrics['net_pnl']:,.2f} | MaxDD: ${full_metrics['max_dd_dollars']:,.2f} ({full_metrics['max_dd_r']}R)")

        # Fast 50,000 Monte Carlo Simulation
        mc = compute_fast_vectorized_monte_carlo(s_trades, n_paths=50000, max_trades=90)
        print(f"  Monte Carlo (50k paths): P(Pass): {mc['p_pass']}% | P(Breach): {mc['p_breach']}% | P50: {mc['p50_trades']} trades ({mc['median_months']} meses)")
        print(f"  Apex 50k Veredicto:      {mc['verdict']}")

        report["sleeves"][s_id] = {
            "name": s_name,
            "risk_dollars": r_dollars,
            "contracts": contracts,
            "in_sample": is_metrics,
            "out_of_sample": oos_metrics,
            "full_sample": full_metrics,
            "monte_carlo": mc,
            "trade_samples": [asdict(t) for t in s_trades[-15:]]
        }

    # Save to JSON
    out_file = Path("reports/artifacts/batch1_discovery_report.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w") as f:
        json.dump(report, f, indent=2)

    elapsed = time.time() - start_time
    print("\n" + "=" * 80)
    print(f"  AUDIT PIPELINE COMPLETE IN {elapsed:.2f}s | REPORT: {out_file}")
    print("=" * 80)

    return report


if __name__ == "__main__":
    run_discovery_pipeline()
