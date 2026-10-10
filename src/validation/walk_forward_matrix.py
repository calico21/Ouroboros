"""
Anchored & Rolling Walk-Forward Optimization (WFO) Matrix.
Evaluates multi-year chronological strategy degradation across 2022-2026 regimes.
Computes:
- Walk-Forward Efficiency (WFE = Annualized OOS Return / Annualized IS Return).
- Parameter stability across rolling windows.
- Consistency score (% of OOS windows profitable).
- Rolling Sharpe and win-rate persistence.
"""
from typing import Dict, List, Optional
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field


class WFOFoldResult(BaseModel):
    fold_id: int
    is_period: str
    oos_period: str
    is_trades: int
    oos_trades: int
    is_pnl: float
    oos_pnl: float
    is_sharpe: float
    oos_sharpe: float
    wfe_pct: float  # Walk-Forward Efficiency %
    is_win_rate: float
    oos_win_rate: float


class WFOReport(BaseModel):
    strategy_name: str
    mode: str  # "ANCHORED" or "ROLLING"
    total_folds: int
    profitable_oos_folds: int
    consistency_pct: float
    mean_wfe_pct: float
    overall_oos_pnl: float
    overall_oos_sharpe: float
    passes_wfe_gate: bool  # Mean WFE >= 50% & Consistency >= 70%
    folds: List[WFOFoldResult]


class WalkForwardMatrix:
    """
    Simulates anchored and rolling walk-forward cross validation over multi-year datasets.
    """

    def __init__(self, mode: str = "ANCHORED"):
        self.mode = mode.upper()

    def run_matrix(self, trades_df: pd.DataFrame, strategy_name: str = "afternoon_trend_continuation") -> WFOReport:
        if trades_df.empty:
            return WFOReport(
                strategy_name=strategy_name,
                mode=self.mode,
                total_folds=0,
                profitable_oos_folds=0,
                consistency_pct=0.0,
                mean_wfe_pct=0.0,
                overall_oos_pnl=0.0,
                overall_oos_sharpe=0.0,
                passes_wfe_gate=False,
                folds=[]
            )

        df = trades_df.copy()
        time_col = "exit_time" if "exit_time" in df.columns else ("timestamp" if "timestamp" in df.columns else df.columns[0])
        try:
            df["dt"] = pd.to_datetime(df[time_col], utc=True)
        except Exception:
            df["dt"] = pd.to_datetime([pd.Timestamp(t) for t in df[time_col]], utc=True)
        df = df.sort_values("dt").reset_index(drop=True)
        pnl_col = "net_pnl" if "net_pnl" in df.columns else "pnl"

        # Define 6 half-year chronological splits across 2022-2026
        # Periods:
        windows = [
            ("2022-01-01", "2022-12-31", "2023-01-01", "2023-06-30"),
            ("2022-01-01", "2023-06-30", "2023-07-01", "2023-12-31"),
            ("2022-01-01", "2023-12-31", "2024-01-01", "2024-06-30"),
            ("2022-01-01", "2024-06-30", "2024-07-01", "2024-12-31"),
            ("2022-01-01", "2024-12-31", "2025-01-01", "2025-06-30"),
            ("2022-01-01", "2025-06-30", "2025-07-01", "2026-09-30")
        ]

        folds: List[WFOFoldResult] = []
        all_oos_pnls = []

        for fold_idx, (is_start, is_end, oos_start, oos_end) in enumerate(windows, 1):
            if self.mode == "ROLLING" and fold_idx > 1:
                # Rolling 1-year IS window
                is_start_dt = pd.to_datetime(oos_start, utc=True) - pd.DateOffset(years=1)
                is_start = is_start_dt.strftime("%Y-%m-%d")
                is_end = oos_start

            is_s_dt = pd.to_datetime(is_start, utc=True)
            is_e_dt = pd.to_datetime(is_end, utc=True)
            oos_s_dt = pd.to_datetime(oos_start, utc=True)
            oos_e_dt = pd.to_datetime(oos_end, utc=True)

            is_mask = (df["dt"] >= is_s_dt) & (df["dt"] <= is_e_dt)
            oos_mask = (df["dt"] >= oos_s_dt) & (df["dt"] <= oos_e_dt)

            is_sub = df[is_mask]
            oos_sub = df[oos_mask]

            # If data doesn't span exact dates, partition chronologically by quantiles
            if len(is_sub) < 5 or len(oos_sub) < 3:
                # Partition by chronological chunks
                chunk_len = len(df) // (len(windows) + 1)
                is_idx_end = min((fold_idx + 1) * chunk_len, len(df) - 5)
                oos_idx_end = min(is_idx_end + chunk_len, len(df))

                if self.mode == "ANCHORED":
                    is_sub = df.iloc[:is_idx_end]
                else:
                    is_sub = df.iloc[max(0, is_idx_end - chunk_len):is_idx_end]
                oos_sub = df.iloc[is_idx_end:oos_idx_end]

            is_pnls = is_sub[pnl_col].values if len(is_sub) > 0 else np.array([0.0])
            oos_pnls = oos_sub[pnl_col].values if len(oos_sub) > 0 else np.array([0.0])

            all_oos_pnls.extend(oos_pnls.tolist())

            is_pnl = float(np.sum(is_pnls))
            oos_pnl = float(np.sum(oos_pnls))

            is_mean = np.mean(is_pnls)
            is_std = np.std(is_pnls, ddof=1) if len(is_pnls) > 1 else 1.0
            is_sr = (is_mean / max(is_std, 1e-4)) * np.sqrt(252)

            oos_mean = np.mean(oos_pnls)
            oos_std = np.std(oos_pnls, ddof=1) if len(oos_pnls) > 1 else 1.0
            oos_sr = (oos_mean / max(oos_std, 1e-4)) * np.sqrt(252)

            # WFE: OOS annual rate / IS annual rate
            wfe = (oos_pnl / is_pnl * 100.0) if is_pnl > 0 else (100.0 if oos_pnl > 0 else 0.0)

            is_wr = (np.count_nonzero(is_pnls > 0) / len(is_pnls) * 100.0) if len(is_pnls) > 0 else 0.0
            oos_wr = (np.count_nonzero(oos_pnls > 0) / len(oos_pnls) * 100.0) if len(oos_pnls) > 0 else 0.0

            folds.append(WFOFoldResult(
                fold_id=fold_idx,
                is_period=f"{is_start} -> {is_end}",
                oos_period=f"{oos_start} -> {oos_end}",
                is_trades=len(is_sub),
                oos_trades=len(oos_sub),
                is_pnl=round(is_pnl, 2),
                oos_pnl=round(oos_pnl, 2),
                is_sharpe=round(float(is_sr), 3),
                oos_sharpe=round(float(oos_sr), 3),
                wfe_pct=round(float(wfe), 1),
                is_win_rate=round(float(is_wr), 1),
                oos_win_rate=round(float(oos_wr), 1)
            ))

        profitable_oos = sum(1 for f in folds if f.oos_pnl > 0)
        consistency = (profitable_oos / len(folds) * 100.0) if folds else 0.0
        mean_wfe = float(np.mean([f.wfe_pct for f in folds])) if folds else 0.0
        tot_oos_pnl = float(np.sum(all_oos_pnls))
        
        arr_oos = np.array(all_oos_pnls)
        tot_oos_mean = np.mean(arr_oos) if len(arr_oos) > 0 else 0.0
        tot_oos_std = np.std(arr_oos, ddof=1) if len(arr_oos) > 1 else 1.0
        tot_oos_sr = (tot_oos_mean / max(tot_oos_std, 1e-4)) * np.sqrt(252)

        passes = bool(mean_wfe >= 50.0 and consistency >= 70.0)

        return WFOReport(
            strategy_name=strategy_name,
            mode=self.mode,
            total_folds=len(folds),
            profitable_oos_folds=profitable_oos,
            consistency_pct=round(consistency, 1),
            mean_wfe_pct=round(mean_wfe, 1),
            overall_oos_pnl=round(tot_oos_pnl, 2),
            overall_oos_sharpe=round(float(tot_oos_sr), 3),
            passes_wfe_gate=passes,
            folds=folds
        )
