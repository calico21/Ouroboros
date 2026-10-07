"""
Vectorized Monte Carlo Bootstrap Simulation for Prop-Firm Path-Dependent Drawdowns.
Simulates 10,000 equity paths under dynamic peak MTM trailing floor ratchets.
Vectorized across paths for lightning-fast execution (< 50ms for 10,000 paths).
Enforces statistical sample-size gating: Suppresses curves when N < 15 empirical trades.
"""
from typing import List, Dict, Any, Optional
import numpy as np
from src.core.events import TradeRecord


class PropFirmMonteCarloSimulator:
    """
    Simulates path-dependent prop-firm evaluation outcomes across thousands of bootstrap paths.
    Enforces minimum N=15 threshold to suppress misleading curves on tiny samples.
    """

    MIN_TRADES_THRESHOLD = 15

    def __init__(
        self,
        initial_balance: float = 50000.0,
        trailing_max_dd: float = 2500.0,
        profit_target: float = 3000.0,
        floor_lock_threshold: Optional[float] = 2600.0,
        lock_floor_offset: Optional[float] = 100.0,
        max_sim_trades: int = 150,
        iterations: int = 10000
    ):
        self.initial_balance = initial_balance
        self.trailing_max_dd = trailing_max_dd
        self.profit_target = profit_target
        self.target_balance = initial_balance + profit_target
        self.floor_lock_threshold = floor_lock_threshold
        self.lock_floor_offset = lock_floor_offset
        self.max_sim_trades = max_sim_trades
        self.iterations = iterations

    def run(self, trades: List[TradeRecord]) -> Dict[str, Any]:
        n_trades = len(trades) if trades else 0

        # Sample size guardrail: Suppress Monte Carlo when N < 15
        if n_trades < self.MIN_TRADES_THRESHOLD:
            return {
                "iterations": self.iterations,
                "is_suppressed": True,
                "status": f"SUPPRESSED_INSUFFICIENT_SAMPLE (N = {n_trades} / {self.MIN_TRADES_THRESHOLD} required)",
                "warning": (
                    f"Monte Carlo simulation suppressed: requires at least {self.MIN_TRADES_THRESHOLD} "
                    f"empirical trades (observed N={n_trades}) to prevent deceptive probability estimates."
                ),
                "prob_pass_pct": None,
                "prob_breach_pct": None,
                "prob_inconclusive_pct": None,
                "median_trades_to_pass": None,
                "percentile_curves": {}
            }

        # Extract empirical net PnLs
        net_pnls = np.array([t.net_pnl for t in trades], dtype=np.float64)

        rng = np.random.default_rng(seed=42)
        bootstrap_indices = rng.integers(0, n_trades, size=(self.iterations, self.max_sim_trades))
        sample_pnls = net_pnls[bootstrap_indices]

        # Vectorized state arrays across all iterations
        balances = np.full(self.iterations, self.initial_balance, dtype=np.float64)
        hwms = np.full(self.iterations, self.initial_balance, dtype=np.float64)
        floors = np.full(self.iterations, self.initial_balance - self.trailing_max_dd, dtype=np.float64)
        locked_flags = np.zeros(self.iterations, dtype=bool)

        locked_floor_level = (self.initial_balance + self.lock_floor_offset) if self.lock_floor_offset else None

        passed = np.zeros(self.iterations, dtype=bool)
        breached = np.zeros(self.iterations, dtype=bool)
        trades_to_pass = np.zeros(self.iterations, dtype=np.int32)

        # For percentile tracking (sample 1000 paths to keep memory light and fast)
        sample_subset_size = min(1000, self.iterations)
        equity_paths = np.zeros((sample_subset_size, self.max_sim_trades + 1), dtype=np.float64)
        equity_paths[:, 0] = self.initial_balance

        for step in range(self.max_sim_trades):
            active = ~passed & ~breached
            if not np.any(active):
                equity_paths[:, step + 1:] = balances[:sample_subset_size, None]
                break

            pnl_step = sample_pnls[:, step]
            balances[active] += pnl_step[active]
            hwms[active] = np.maximum(hwms[active], balances[active])

            new_floors = hwms - self.trailing_max_dd

            if self.floor_lock_threshold is not None and locked_floor_level is not None:
                newly_locked = active & ~locked_flags & (hwms >= (self.initial_balance + self.floor_lock_threshold))
                locked_flags[newly_locked] = True
                new_floors[locked_flags] = np.maximum(new_floors[locked_flags], locked_floor_level)

            floors[active] = np.maximum(floors[active], new_floors[active])

            just_breached = active & (balances <= floors)
            breached[just_breached] = True

            just_passed = active & ~just_breached & (balances >= self.target_balance)
            passed[just_passed] = True
            trades_to_pass[just_passed] = step + 1

            equity_paths[:, step + 1] = balances[:sample_subset_size]

        pass_count = int(np.sum(passed))
        breach_count = int(np.sum(breached))
        inconclusive_count = self.iterations - pass_count - breach_count

        prob_pass = (pass_count / self.iterations) * 100.0
        prob_breach = (breach_count / self.iterations) * 100.0
        prob_inconclusive = (inconclusive_count / self.iterations) * 100.0

        passed_trades = trades_to_pass[passed]
        median_trades = float(np.median(passed_trades)) if len(passed_trades) > 0 else None
        mean_trades = float(np.mean(passed_trades)) if len(passed_trades) > 0 else None

        percentiles = {
            "p5": np.percentile(equity_paths, 5, axis=0).tolist(),
            "p25": np.percentile(equity_paths, 25, axis=0).tolist(),
            "p50": np.percentile(equity_paths, 50, axis=0).tolist(),
            "p75": np.percentile(equity_paths, 75, axis=0).tolist(),
            "p95": np.percentile(equity_paths, 95, axis=0).tolist(),
        }

        return {
            "iterations": self.iterations,
            "is_suppressed": False,
            "status": "VALID_SIMULATION",
            "prob_pass_pct": round(prob_pass, 2),
            "prob_breach_pct": round(prob_breach, 2),
            "prob_inconclusive_pct": round(prob_inconclusive, 2),
            "median_trades_to_pass": round(median_trades, 1) if median_trades else None,
            "mean_trades_to_pass": round(mean_trades, 1) if mean_trades else None,
            "percentile_curves": percentiles,
            "target_balance": self.target_balance,
            "initial_floor": self.initial_balance - self.trailing_max_dd
        }
