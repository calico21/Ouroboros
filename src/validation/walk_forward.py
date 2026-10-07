"""
Walk-Forward Optimization and Stability Validation for AlphaForge.
Evaluates out-of-sample persistence of alpha signals.
"""
from typing import List, Dict, Any
import numpy as np
from src.core.events import TradeRecord


class WalkForwardValidator:
    """Splits trade history into sequential in-sample (IS) and out-of-sample (OOS) windows."""

    @staticmethod
    def evaluate(trades: List[TradeRecord], n_splits: int = 4) -> Dict[str, Any]:
        if len(trades) < (n_splits * 5):
            return {"splits": [], "stability_score": 0.0}

        chunk_size = len(trades) // n_splits
        splits = []

        oos_pnls = []

        for i in range(n_splits - 1):
            is_trades = trades[i * chunk_size : (i + 1) * chunk_size]
            oos_trades = trades[(i + 1) * chunk_size : (i + 2) * chunk_size]

            is_pnl = sum(t.net_pnl for t in is_trades)
            oos_pnl = sum(t.net_pnl for t in oos_trades)
            oos_pnls.append(oos_pnl)

            is_exp = np.mean([t.r_multiple for t in is_trades]) if is_trades else 0.0
            oos_exp = np.mean([t.r_multiple for t in oos_trades]) if oos_trades else 0.0

            splits.append({
                "split_idx": i + 1,
                "is_trade_count": len(is_trades),
                "oos_trade_count": len(oos_trades),
                "is_net_pnl": round(float(is_pnl), 2),
                "oos_net_pnl": round(float(oos_pnl), 2),
                "is_expectancy_r": round(float(is_exp), 3),
                "oos_expectancy_r": round(float(oos_exp), 3),
                "oos_profitable": oos_pnl > 0
            })

        # Stability score: percentage of OOS splits that remained profitable
        profitable_oos = sum(1 for s in splits if s["oos_profitable"])
        stability_score = round(profitable_oos / len(splits) * 100.0, 1) if splits else 0.0

        return {
            "splits": splits,
            "stability_score": stability_score,
            "is_robust": stability_score >= 66.0
        }
