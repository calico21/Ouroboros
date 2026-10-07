"""
Multi-Dimensional Regime Slicing for AlphaForge.
Segments trade performance across session auction windows, weekdays, and volatility quintiles.
"""
from typing import List, Dict, Any
import pandas as pd
import numpy as np
from src.core.events import TradeRecord
from src.core.time_utils import get_session_window


class RegimeSlicingEngine:
    """Slices strategy performance across intraday auction windows, days, and ATR quintiles."""

    @classmethod
    def analyze(cls, trades: List[TradeRecord]) -> Dict[str, Any]:
        if not trades:
            return {"by_session_window": {}, "by_day_of_week": {}, "by_atr_quintile": {}}

        # Convert trade records to DataFrame for clean groupby aggregation
        data = []
        for t in trades:
            data.append({
                "trade_id": t.trade_id,
                "entry_time": t.entry_time,
                "session_window": get_session_window(t.entry_time),
                "day_of_week": t.day_of_week,
                "atr_quintile": f"Q{t.atr_quintile}",
                "net_pnl": t.net_pnl,
                "r_multiple": t.r_multiple,
                "is_win": t.net_pnl > 0
            })

        df = pd.DataFrame(data)

        # 1. By Session Window
        window_stats = cls._aggregate_group(df, "session_window")

        # 2. By Day of Week (in chronological order)
        day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        day_stats = cls._aggregate_group(df, "day_of_week", custom_order=day_order)

        # 3. By ATR Quintile
        quintile_order = ["Q1", "Q2", "Q3", "Q4", "Q5"]
        quintile_stats = cls._aggregate_group(df, "atr_quintile", custom_order=quintile_order)

        return {
            "by_session_window": window_stats,
            "by_day_of_week": day_stats,
            "by_atr_quintile": quintile_stats
        }

    @staticmethod
    def _aggregate_group(df: pd.DataFrame, group_col: str, custom_order: List[str] = None) -> Dict[str, Any]:
        result = {}
        grouped = df.groupby(group_col)

        keys = custom_order if custom_order else sorted(df[group_col].unique())

        for key in keys:
            if key in grouped.groups:
                sub = grouped.get_group(key)
                n = len(sub)
                wins = int(sub["is_win"].sum())
                win_rate = (wins / n * 100.0) if n > 0 else 0.0
                total_pnl = float(sub["net_pnl"].sum())
                avg_pnl = float(sub["net_pnl"].mean())
                avg_r = float(sub["r_multiple"].mean())
                result[key] = {
                    "trade_count": n,
                    "win_rate_pct": round(win_rate, 1),
                    "total_net_pnl": round(total_pnl, 2),
                    "avg_net_pnl": round(avg_pnl, 2),
                    "expectancy_r": round(avg_r, 3)
                }
            else:
                result[key] = {
                    "trade_count": 0,
                    "win_rate_pct": 0.0,
                    "total_net_pnl": 0.0,
                    "avg_net_pnl": 0.0,
                    "expectancy_r": 0.0
                }

        return result
