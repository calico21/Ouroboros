"""
Friction Frontier & Critical Slippage Analysis.
Quantifies strategy fragility and determines break-even slippage S*.
"""
from typing import List, Dict, Any, Optional
import numpy as np
from src.core.events import TradeRecord


class FrictionFrontierEngine:
    """
    Evaluates strategy resilience across varying execution frictions.
    Identifies Critical Slippage S* where expectancy drops to zero.
    """

    DEFAULT_STEPS = [0.0, 0.5, 1.0, 1.5, 2.0, 3.0]

    @classmethod
    def evaluate(
        cls,
        trades: List[TradeRecord],
        point_value: float = 2.00,
        tick_size: float = 0.25,
        slippage_steps: Optional[List[float]] = None
    ) -> Dict[str, Any]:
        if not trades:
            return {
                "frontier_table": [],
                "critical_slippage_s_star": 0.0,
                "is_viable": False
            }

        steps = slippage_steps or cls.DEFAULT_STEPS
        tick_value = point_value * tick_size  # e.g. $0.50 for MNQ

        frontier_records = []
        slippage_points = []
        expectancy_vals = []

        n_trades = len(trades)

        for s in steps:
            net_pnls = []
            r_multiples = []

            for t in trades:
                # Baseline gross pnl without slippage
                # In TradeRecord: net_pnl = gross_pnl - commissions - slippage_paid
                # Slippage paid was based on original simulation slippage
                # We calculate net PnL under test slippage `s`:
                # Each side paying s ticks: entry side + (if market exit) exit side
                sides_paying_slip = 2 if "STOP" in t.exit_reason or "LIQUIDATION" in t.exit_reason else 1
                test_slippage_cost = s * tick_value * t.contracts * sides_paying_slip
                sim_net_pnl = t.gross_pnl - t.commissions - test_slippage_cost
                net_pnls.append(sim_net_pnl)

                r_mult = sim_net_pnl / (t.risk_r_price * point_value * t.contracts) if (t.risk_r_price > 0 and t.contracts > 0) else 0.0
                r_multiples.append(r_mult)

            total_net = float(np.sum(net_pnls))
            expectancy_dollar = float(np.mean(net_pnls))
            expectancy_r = float(np.mean(r_multiples))
            win_rate = float(np.mean([p > 0 for p in net_pnls]) * 100.0)

            frontier_records.append({
                "slippage_ticks": s,
                "slippage_pts": s * tick_size,
                "total_net_pnl": round(total_net, 2),
                "expectancy_dollars": round(expectancy_dollar, 2),
                "expectancy_r": round(expectancy_r, 3),
                "win_rate_pct": round(win_rate, 1)
            })

            slippage_points.append(s)
            expectancy_vals.append(expectancy_dollar)

        # Calculate Critical Slippage S* via linear interpolation / zero-crossing
        s_star = cls._find_zero_crossing(slippage_points, expectancy_vals)

        return {
            "frontier_table": frontier_records,
            "critical_slippage_s_star": round(s_star, 2) if s_star is not None else "> 3.0",
            "is_viable": (s_star is None or s_star >= 1.5)
        }

    @staticmethod
    def _find_zero_crossing(x: List[float], y: List[float]) -> Optional[float]:
        """Finds root where y(x) = 0."""
        for i in range(len(y) - 1):
            if (y[i] >= 0 and y[i+1] < 0) or (y[i] <= 0 and y[i+1] > 0):
                # Linear interpolation
                if y[i+1] - y[i] != 0:
                    root = x[i] - y[i] * (x[i+1] - x[i]) / (y[i+1] - y[i])
                    return float(root)
        if y[0] < 0:
            return 0.0
        return None
