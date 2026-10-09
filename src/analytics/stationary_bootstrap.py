"""
Politis & Romano (1994) Stationary Block Bootstrap Monte Carlo Simulator.
Evaluates path-dependent survival against the canonical Apex 50k Peak-Unrealized MTM Trailing Floor.
Replaces IID bootstrap with geometric block-length resampling (mean length L = 5)
to faithfully preserve loss clustering, regime persistence, and auto-correlated streaks.
"""
from typing import List, Dict, Any, Optional
import numpy as np

from src.core.events import TradeRecord


class StationaryBlockBootstrapSimulator:
    """
    Simulates path-dependent prop-firm evaluation outcomes using Politis & Romano (1994)
    Stationary Block Bootstrap over 50,000 resampled trajectories.
    """

    def __init__(
        self,
        initial_balance: float = 50000.0,
        trailing_buffer: float = 2500.0,
        profit_target: float = 3000.0,
        lock_hwm_trigger: float = 52600.0,
        locked_floor_level: float = 50100.0,
        daily_loss_limit: float = 1000.0,
        mean_block_length: float = 5.0,
        n_paths: int = 50000,
        max_trades_per_path: int = 250,
        seed: int = 42
    ):
        self.initial_balance = initial_balance
        self.trailing_buffer = trailing_buffer
        self.target_balance = initial_balance + profit_target
        self.lock_hwm_trigger = lock_hwm_trigger
        self.locked_floor_level = locked_floor_level
        self.daily_loss_limit = daily_loss_limit
        self.mean_block_length = mean_block_length
        self.n_paths = n_paths
        self.max_trades_per_path = max_trades_per_path
        self.seed = seed

    def run(self, trades: List[TradeRecord]) -> Dict[str, Any]:
        """
        Executes 50,000 paths of Stationary Block Bootstrap.
        Returns exact P(Pass), P(Breach), P(DLL), and drawdown percentiles.
        """
        n_trades = len(trades)
        if n_trades < 10:
            return {
                "n_paths": self.n_paths,
                "n_trades_source": n_trades,
                "is_suppressed": True,
                "reason": f"Sample size N={n_trades} < 10 insufficient for stationary bootstrap",
                "prob_pass_pct": 0.0,
                "prob_breach_pct": 0.0,
                "p_pass_pct": 0.0,
                "p_breach_pct": 0.0,
                "p_dll_pct": 0.0,
                "median_trades_to_pass": None,
            }

        # Extract empirical trade return vectors
        pnls = np.array([t.net_pnl for t in trades], dtype=np.float64)
        mfes = np.array([max(0.0, (t.mfe_r * t.risk_r_price * 2.0 * t.contracts)) if hasattr(t, "mfe_r") else max(0.0, t.net_pnl) for t in trades], dtype=np.float64)
        maes = np.array([max(0.0, (t.mae_r * t.risk_r_price * 2.0 * t.contracts)) if hasattr(t, "mae_r") else max(0.0, -t.net_pnl) for t in trades], dtype=np.float64)

        rng = np.random.default_rng(self.seed)
        p_geom = 1.0 / self.mean_block_length  # e.g., 0.20 for L=5

        passes = 0
        breaches = 0
        dll_breaches = 0
        trades_to_pass = []
        terminal_equities = np.zeros(self.n_paths)
        max_drawdowns = np.zeros(self.n_paths)

        # Batch simulation for 50,000 paths
        for path_idx in range(self.n_paths):
            balance = self.initial_balance
            hwm = self.initial_balance
            floor = self.initial_balance - self.trailing_buffer
            floor_locked = False
            path_max_dd = 0.0

            # Politis & Romano index generation
            current_idx = rng.integers(0, n_trades)
            day_loss = 0.0

            for t_step in range(self.max_trades_per_path):
                # Next trade step
                trade_pnl = pnls[current_idx]
                trade_mfe = mfes[current_idx]
                trade_mae = maes[current_idx]

                # 1. Floating peak excursion ratchets trailing floor intra-trade
                peak_floating = balance + trade_mfe
                if peak_floating > hwm:
                    hwm = peak_floating
                    # Check floor lock
                    if hwm >= self.lock_hwm_trigger:
                        floor_locked = True
                        floor = max(floor, self.locked_floor_level)
                    elif not floor_locked:
                        floor = max(floor, hwm - self.trailing_buffer)

                # 2. Check intra-trade trough breach
                trough_floating = balance - trade_mae
                if trough_floating <= floor:
                    breaches += 1
                    path_max_dd = max(path_max_dd, hwm - trough_floating)
                    break

                # 3. Apply realized PnL
                balance += trade_pnl
                day_loss += -trade_pnl

                if balance > hwm:
                    hwm = balance
                    if hwm >= self.lock_hwm_trigger:
                        floor_locked = True
                        floor = max(floor, self.locked_floor_level)
                    elif not floor_locked:
                        floor = max(floor, hwm - self.trailing_buffer)

                dd = hwm - balance
                if dd > path_max_dd:
                    path_max_dd = dd

                # Check DLL
                if self.daily_loss_limit and day_loss >= self.daily_loss_limit:
                    dll_breaches += 1

                # Check terminal floor breach
                if balance <= floor:
                    breaches += 1
                    break

                # Check profit target pass
                if balance >= self.target_balance:
                    passes += 1
                    trades_to_pass.append(t_step + 1)
                    break

                # Stationary block transition:
                # With prob p_geom, jump to new random index; else increment sequentially
                if rng.random() < p_geom:
                    current_idx = rng.integers(0, n_trades)
                else:
                    current_idx = (current_idx + 1) % n_trades

            terminal_equities[path_idx] = balance
            max_drawdowns[path_idx] = path_max_dd

        prob_pass = (passes / self.n_paths) * 100.0
        prob_breach = (breaches / self.n_paths) * 100.0
        prob_dll = (dll_breaches / self.n_paths) * 100.0
        med_trades = int(np.median(trades_to_pass)) if trades_to_pass else None

        dd_50 = float(np.percentile(max_drawdowns, 50))
        dd_95 = float(np.percentile(max_drawdowns, 95))
        dd_99 = float(np.percentile(max_drawdowns, 99))

        return {
            "n_paths": self.n_paths,
            "n_trades_source": n_trades,
            "mean_block_length": self.mean_block_length,
            "method": "Politis_Romano_1994_Stationary_Bootstrap",
            "is_suppressed": False,
            "prob_pass_pct": round(prob_pass, 2),
            "prob_breach_pct": round(prob_breach, 2),
            "p_pass_pct": round(prob_pass, 2),
            "p_breach_pct": round(prob_breach, 2),
            "p_dll_pct": round(prob_dll, 2),
            "median_trades_to_pass": med_trades,
            "max_drawdown_distribution": {
                "p50": round(dd_50, 2),
                "p95": round(dd_95, 2),
                "p99": round(dd_99, 2),
            },
            "mean_terminal_equity": round(float(np.mean(terminal_equities)), 2)
        }
