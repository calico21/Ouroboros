"""
Intra-Trade Excursion Analysis (MFE & MAE in R-Units).
Quantifies directional edge before trade resolution.
"""
from typing import List, Dict, Any
import numpy as np
from src.core.events import TradeRecord


class ExcursionAnalytics:
    """Analyzes Maximum Favorable Excursion (MFE) and Maximum Adverse Excursion (MAE)."""

    @staticmethod
    def analyze(trades: List[TradeRecord]) -> Dict[str, Any]:
        if not trades:
            return {
                "median_mfe_r": 0.0,
                "median_mae_r": 0.0,
                "mean_mfe_r": 0.0,
                "mean_mae_r": 0.0,
                "drift_ratio": 0.0,
                "median_time_to_peak_mfe": 0,
                "excursion_efficiency": 0.0,
                "is_alpha_disqualified": True
            }

        mfe_r_vals = np.array([t.mfe_r for t in trades])
        mae_r_vals = np.array([t.mae_r for t in trades])
        times_to_peak = np.array([t.time_to_peak_mfe for t in trades])
        efficiencies = np.array([t.excursion_efficiency for t in trades])

        median_mfe_r = float(np.median(mfe_r_vals))
        median_mae_r = float(np.median(mae_r_vals))

        # Directional Drift Ratio: Median(MFE_R) / max(0.01, Median(MAE_R))
        drift_ratio = median_mfe_r / max(0.01, median_mae_r)
        
        # Disqualify any alpha with drift ratio < 1.5x
        is_alpha_disqualified = drift_ratio < 1.50

        return {
            "median_mfe_r": round(median_mfe_r, 3),
            "median_mae_r": round(median_mae_r, 3),
            "mean_mfe_r": round(float(np.mean(mfe_r_vals)), 3),
            "mean_mae_r": round(float(np.mean(mae_r_vals)), 3),
            "drift_ratio": round(drift_ratio, 3),
            "median_time_to_peak_mfe": int(np.median(times_to_peak)),
            "mean_time_to_peak_mfe": round(float(np.mean(times_to_peak)), 2),
            "excursion_efficiency": round(float(np.mean(efficiencies)), 3),
            "is_alpha_disqualified": is_alpha_disqualified
        }
