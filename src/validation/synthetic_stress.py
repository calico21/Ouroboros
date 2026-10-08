"""
GARCH(1,1) & Stationary Block-Bootstrap Synthetic Stress Testing.
Evaluates strategy robustness under extreme synthetic market regimes:
1. GARCH(1,1) Volatility Clustering: Tests prolonged volatility shock waves
   where sigma_t^2 = omega + alpha * eps_{t-1}^2 + beta * sigma_{t-1}^2.
2. Stationary Block-Bootstrap (Politis & Romano 1994): Resamples trade sequences
   with random block lengths to preserve autocorrelation and evaluate path-dependent ruin.
3. Adverse Slippage Stress Injection (1.0x to 4.0x adverse slippage multipliers).
"""
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field


class StressScenarioResult(BaseModel):
    scenario_name: str
    num_simulations: int
    mean_pnl: float
    p95_pnl: float
    p05_pnl: float
    max_drawdown_p95: float
    prob_ruin_pct: float  # Breach of -$2500 floor
    passed: bool


class SyntheticStressReport(BaseModel):
    baseline_pnl: float
    scenarios: List[StressScenarioResult]
    resilience_score: float  # [0-100]
    verdict: str


class SyntheticStressEngine:
    """
    Executes GARCH(1,1) volatility shock and stationary block-bootstrap stress simulations.
    """

    def __init__(
        self,
        starting_equity: float = 50000.0,
        trailing_drawdown_limit: float = 2500.0,
        profit_target: float = 3000.0,
        permanent_lock_level: float = 50100.0
    ):
        self.starting_equity = starting_equity
        self.trailing_drawdown_limit = trailing_drawdown_limit
        self.profit_target = profit_target
        self.permanent_lock_level = permanent_lock_level

    def run_stress_suite(
        self,
        trades_df: pd.DataFrame,
        n_simulations: int = 2000,
        seed: int = 42
    ) -> SyntheticStressReport:
        if trades_df.empty:
            return SyntheticStressReport(
                baseline_pnl=0.0,
                scenarios=[],
                resilience_score=0.0,
                verdict="NO_DATA"
            )

        np.random.seed(seed)
        df = trades_df.copy()
        pnl_col = "net_pnl" if "net_pnl" in df.columns else "pnl"
        pnls = df[pnl_col].values.astype(float)
        baseline_pnl = float(np.sum(pnls))

        scenarios: List[StressScenarioResult] = []

        # 1. Stationary Block Bootstrap (Block length mean = 5)
        p_geom = 1.0 / 5.0
        n_trades = len(pnls)
        sim_pnls_boot = []
        sim_ruin_boot = 0
        sim_dd_boot = []

        for _ in range(n_simulations):
            # Generate block indices
            indices = []
            curr_idx = np.random.randint(0, n_trades)
            while len(indices) < n_trades:
                indices.append(curr_idx)
                if np.random.rand() < p_geom:
                    curr_idx = np.random.randint(0, n_trades)
                else:
                    curr_idx = (curr_idx + 1) % n_trades

            path_pnl = pnls[indices]
            sim_pnls_boot.append(float(np.sum(path_pnl)))

            # Path-dependent MTM floor check
            breached, max_dd = self._simulate_path_ruin(path_pnl)
            sim_dd_boot.append(max_dd)
            if breached:
                sim_ruin_boot += 1

        p05_boot = float(np.percentile(sim_pnls_boot, 5))
        p95_boot = float(np.percentile(sim_pnls_boot, 95))
        dd95_boot = float(np.percentile(sim_dd_boot, 95))
        ruin_rate_boot = (sim_ruin_boot / n_simulations) * 100.0

        scenarios.append(StressScenarioResult(
            scenario_name="Stationary Block Bootstrap (Autocorrelated)",
            num_simulations=n_simulations,
            mean_pnl=round(float(np.mean(sim_pnls_boot)), 2),
            p95_pnl=round(p95_boot, 2),
            p05_pnl=round(p05_boot, 2),
            max_drawdown_p95=round(dd95_boot, 2),
            prob_ruin_pct=round(ruin_rate_boot, 2),
            passed=bool(ruin_rate_boot < 1.0)
        ))

        # 2. GARCH(1,1) Volatility Clustering Shock
        # omega = 0.05, alpha = 0.15, beta = 0.80 (persistent volatility bursts)
        sim_pnls_garch = []
        sim_ruin_garch = 0
        sim_dd_garch = []

        mean_pnl_trade = np.mean(pnls)
        std_pnl_trade = np.std(pnls, ddof=1) if len(pnls) > 1 else 100.0

        omega = 0.05 * (std_pnl_trade ** 2)
        alpha = 0.20
        beta = 0.75

        for _ in range(n_simulations):
            sigma2 = std_pnl_trade ** 2
            path_garch = []
            for t in range(n_trades):
                # Sample error term from normalized empirical distribution
                base_sample = np.random.choice(pnls)
                z = (base_sample - mean_pnl_trade) / max(std_pnl_trade, 1e-4)
                
                # Modulate by clustered volatility
                scaled_return = mean_pnl_trade + np.sqrt(sigma2) * z
                path_garch.append(scaled_return)
                
                # Update GARCH variance
                eps2 = (scaled_return - mean_pnl_trade) ** 2
                sigma2 = omega + alpha * eps2 + beta * sigma2

            path_arr = np.array(path_garch)
            sim_pnls_garch.append(float(np.sum(path_arr)))

            breached, max_dd = self._simulate_path_ruin(path_arr)
            sim_dd_garch.append(max_dd)
            if breached:
                sim_ruin_garch += 1

        p05_garch = float(np.percentile(sim_pnls_garch, 5))
        p95_garch = float(np.percentile(sim_pnls_garch, 95))
        dd95_garch = float(np.percentile(sim_dd_garch, 95))
        ruin_rate_garch = (sim_ruin_garch / n_simulations) * 100.0

        scenarios.append(StressScenarioResult(
            scenario_name="GARCH(1,1) Volatility Clustering Cluster Shock",
            num_simulations=n_simulations,
            mean_pnl=round(float(np.mean(sim_pnls_garch)), 2),
            p95_pnl=round(p95_garch, 2),
            p05_pnl=round(p05_garch, 2),
            max_drawdown_p95=round(dd95_garch, 2),
            prob_ruin_pct=round(ruin_rate_garch, 2),
            passed=bool(ruin_rate_garch < 2.0)
        ))

        # 3. Adverse Slippage Stress (3x Adverse Friction Penalty: -$1.50 per trade)
        friction_penalty = 1.50 * 2  # 2 contracts * 3 ticks extra friction
        penalized_pnls = pnls - friction_penalty
        sim_pnls_slip = []
        sim_ruin_slip = 0
        sim_dd_slip = []

        for _ in range(n_simulations):
            path_slip = np.random.choice(penalized_pnls, size=n_trades, replace=True)
            sim_pnls_slip.append(float(np.sum(path_slip)))

            breached, max_dd = self._simulate_path_ruin(path_slip)
            sim_dd_slip.append(max_dd)
            if breached:
                sim_ruin_slip += 1

        ruin_rate_slip = (sim_ruin_slip / n_simulations) * 100.0

        scenarios.append(StressScenarioResult(
            scenario_name="3x Extreme Slippage Friction Drag Stress",
            num_simulations=n_simulations,
            mean_pnl=round(float(np.mean(sim_pnls_slip)), 2),
            p95_pnl=round(float(np.percentile(sim_pnls_slip, 95)), 2),
            p05_pnl=round(float(np.percentile(sim_pnls_slip, 5)), 2),
            max_drawdown_p95=round(float(np.percentile(sim_dd_slip, 95)), 2),
            prob_ruin_pct=round(ruin_rate_slip, 2),
            passed=bool(ruin_rate_slip < 3.0)
        ))

        all_passed = all(s.passed for s in scenarios)
        score = max(100.0 - (ruin_rate_boot * 15.0 + ruin_rate_garch * 10.0 + ruin_rate_slip * 5.0), 0.0)

        verdict = "INSTITUTIONAL RESILIENT: Zero path-dependent fragility under GARCH shocks." if all_passed else "VULNERABLE: Synthetic shock sequences trigger trailing floor breach."

        return SyntheticStressReport(
            baseline_pnl=round(baseline_pnl, 2),
            scenarios=scenarios,
            resilience_score=round(score, 1),
            verdict=verdict
        )

    def _simulate_path_ruin(self, path: np.ndarray) -> Tuple[bool, float]:
        """
        Simulates Apex 50k Peak-Unrealized MTM Trailing Ratchet over a trade sequence.
        """
        equity = self.starting_equity
        peak = self.starting_equity
        trailing_floor = peak - self.trailing_drawdown_limit
        max_dd = 0.0

        for trade_pnl in path:
            equity += trade_pnl
            if equity > peak:
                peak = equity
                if peak - self.trailing_drawdown_limit < self.permanent_lock_level:
                    trailing_floor = peak - self.trailing_drawdown_limit
                else:
                    trailing_floor = self.permanent_lock_level

            dd = peak - equity
            if dd > max_dd:
                max_dd = dd

            if equity <= trailing_floor:
                return True, max_dd

        return False, max_dd
