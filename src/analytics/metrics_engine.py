"""
Institutional Metrics & Quantitative Forensics Engine for AlphaForge.
Computes comprehensive institutional KPIs, prop-firm survival diagnostics, R-multiple distributions,
and rigorous statistical sample-size guardrails (Wilson Score CI, bootstrap standard errors, Significance Gate).
"""
import math
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
from src.core.events import TradeRecord
from src.analytics.excursion import ExcursionAnalytics
from src.analytics.loss_taxonomy import LossTaxonomyEngine
from src.analytics.sensitivity import FrictionFrontierEngine
from src.analytics.regime import RegimeSlicingEngine
from src.engine.account_tracker import PropFirmAccountTracker


class MetricsEngine:
    """Computes master quantitative forensic metrics with statistical significance guardrails."""

    MIN_SAMPLE_THRESHOLD = 30
    SUPPRESS_MC_THRESHOLD = 15

    @classmethod
    def compute_all(
        cls,
        trades: List[TradeRecord],
        account: Optional[PropFirmAccountTracker] = None,
        point_value: float = 2.00,
        tick_size: float = 0.25
    ) -> Dict[str, Any]:
        total_trades = len(trades)
        if total_trades == 0:
            return cls._empty_report(account)

        net_pnls = np.array([t.net_pnl for t in trades], dtype=np.float64)
        gross_pnls = np.array([t.gross_pnl for t in trades], dtype=np.float64)
        r_multiples = np.array([t.r_multiple for t in trades], dtype=np.float64)
        commissions = np.array([t.commissions for t in trades], dtype=np.float64)
        slippages = np.array([t.slippage_paid for t in trades], dtype=np.float64)

        winning_trades = [p for p in net_pnls if p > 0]
        losing_trades = [p for p in net_pnls if p <= 0]

        n_wins = len(winning_trades)
        n_losses = len(losing_trades)
        raw_win_rate = (n_wins / total_trades) * 100.0

        # -------------------------------------------------------------
        # STATISTICAL GUARDRAILS & CONFIDENCE INTERVALS
        # -------------------------------------------------------------
        wilson_lower, wilson_upper = cls._calculate_wilson_ci95(n_wins, total_trades)
        expectancy_r_stderr, exp_r_ci_lower, exp_r_ci_upper = cls._bootstrap_expectancy_r_stderr(r_multiples)

        # Sample Significance Gate
        is_sufficient_sample = total_trades >= cls.MIN_SAMPLE_THRESHOLD
        if not is_sufficient_sample:
            sample_status = f"INSUFFICIENT_SAMPLE (N = {total_trades} / {cls.MIN_SAMPLE_THRESHOLD} minimum)"
            sample_warning = (
                f"STATUS: INSUFFICIENT_SAMPLE (N = {total_trades} / {cls.MIN_SAMPLE_THRESHOLD} minimum). "
                f"Statistical estimates, Sharpe/Sortino, and win rate are prone to small-sample bias."
            )
        else:
            sample_status = f"SUFFICIENT_SAMPLE (N = {total_trades})"
            sample_warning = None

        gross_profit = float(np.sum(winning_trades)) if winning_trades else 0.0
        gross_loss = float(np.sum(np.abs(losing_trades))) if losing_trades else 0.0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)

        total_net_pnl = float(np.sum(net_pnls))
        total_gross_pnl = float(np.sum(gross_pnls))
        total_fees = float(np.sum(commissions)) + float(np.sum(slippages))

        avg_trade_pnl = float(np.mean(net_pnls))
        avg_win = float(np.mean(winning_trades)) if winning_trades else 0.0
        avg_loss = float(np.mean(losing_trades)) if losing_trades else 0.0
        win_loss_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0.0

        # R-Multiple statistics
        mean_r = float(np.mean(r_multiples))
        median_r = float(np.median(r_multiples))
        std_r = float(np.std(r_multiples)) if len(r_multiples) > 1 else 0.0
        skew_r = cls._skewness(r_multiples)

        # Sharpe and Sortino
        annualization_factor = np.sqrt(252 * 2)  # ~2 trades/day
        std_pnl = float(np.std(net_pnls)) if len(net_pnls) > 1 else 1.0
        downside_std = float(np.std([p for p in net_pnls if p < 0])) if losing_trades else 1.0
        sharpe = (avg_trade_pnl / std_pnl * annualization_factor) if std_pnl > 0 else 0.0
        sortino = (avg_trade_pnl / downside_std * annualization_factor) if downside_std > 0 else 0.0

        # Equity Curve and Peak-to-Trough Drawdown
        cum_pnl = np.cumsum(net_pnls)
        running_max = np.maximum.accumulate(cum_pnl)
        drawdowns = running_max - cum_pnl
        max_drawdown = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0

        # Excursion & Alpha Drift
        excursion_data = ExcursionAnalytics.analyze(trades)

        # Loss Taxonomy (Algorithmic Death Tree)
        loss_data = LossTaxonomyEngine.analyze_losses(trades)

        # Friction Frontier & S*
        friction_data = FrictionFrontierEngine.evaluate(trades, point_value=point_value, tick_size=tick_size)

        # Regime Slicing
        regime_data = RegimeSlicingEngine.analyze(trades)

        # Prop Firm Summary
        prop_firm_summary = {}
        if account:
            prop_firm_summary = {
                "initial_balance": account.initial_balance,
                "current_balance": round(account.balance, 2),
                "high_water_mark": round(account.high_water_mark, 2),
                "trailing_floor": round(account.floor, 2),
                "remaining_cushion": round(account.cushion, 2),
                "status": account.status.value,
                "breach_reason": account.breach_reason,
                "passed_evaluation": account.status.value == "PASSED",
                "profit_target": account.profit_target,
                "target_balance": account.target_balance,
                "sample_status": sample_status
            }

        return {
            "summary": {
                "total_trades": total_trades,
                "winning_trades": n_wins,
                "losing_trades": n_losses,
                "win_rate_pct": round(raw_win_rate, 2),
                "win_rate_wilson_ci95": [round(wilson_lower, 2), round(wilson_upper, 2)],
                "win_rate_wilson_ci_str": f"{raw_win_rate:.1f}% (95% CI: [{wilson_lower:.1f}%, {wilson_upper:.1f}%])",
                "total_net_pnl": round(total_net_pnl, 2),
                "total_gross_pnl": round(total_gross_pnl, 2),
                "total_fees_paid": round(total_fees, 2),
                "profit_factor": round(profit_factor, 2),
                "expectancy_dollars": round(avg_trade_pnl, 2),
                "expectancy_r": round(mean_r, 3),
                "expectancy_r_stderr": round(expectancy_r_stderr, 3),
                "expectancy_r_ci95": [round(exp_r_ci_lower, 3), round(exp_r_ci_upper, 3)],
                "expectancy_r_ci_str": f"{mean_r:+.3f}R ± {expectancy_r_stderr:.3f} (95% CI: [{exp_r_ci_lower:+.3f}R, {exp_r_ci_upper:+.3f}R])",
                "median_r": round(median_r, 3),
                "skewness_r": round(skew_r, 3),
                "avg_win_dollars": round(avg_win, 2),
                "avg_loss_dollars": round(avg_loss, 2),
                "win_loss_payoff_ratio": round(win_loss_ratio, 2),
                "max_drawdown_dollars": round(max_drawdown, 2),
                "sharpe_ratio": round(sharpe, 2),
                "sortino_ratio": round(sortino, 2),
                "is_sufficient_sample": is_sufficient_sample,
                "sample_significance_status": sample_status,
                "sample_warning": sample_warning
            },
            "excursion": excursion_data,
            "loss_taxonomy": loss_data,
            "friction_frontier": friction_data,
            "regimes": regime_data,
            "prop_firm": prop_firm_summary
        }

    @staticmethod
    def _calculate_wilson_ci95(k: int, n: int) -> Tuple[float, float]:
        """Calculates standard 95% Wilson Score confidence interval for binomial proportions."""
        if n == 0:
            return 0.0, 0.0

        p = k / n
        z = 1.95996398454  # 95% two-tailed standard normal quantile
        z2 = z ** 2

        denominator = 1.0 + (z2 / n)
        center = (p + (z2 / (2.0 * n))) / denominator
        spread = (z * math.sqrt((p * (1.0 - p) / n) + (z2 / (4.0 * (n ** 2))))) / denominator

        lower = max(0.0, center - spread) * 100.0
        upper = min(1.0, center + spread) * 100.0
        return lower, upper

    @staticmethod
    def _bootstrap_expectancy_r_stderr(r_multiples: np.ndarray, iterations: int = 1000) -> Tuple[float, float, float]:
        """Computes bootstrap standard error and 95% confidence bounds for Expectancy in R."""
        n = len(r_multiples)
        mean_r = float(np.mean(r_multiples)) if n > 0 else 0.0

        if n < 3:
            return 0.0, mean_r, mean_r

        rng = np.random.default_rng(seed=42)
        # Vectorized bootstrap resamples
        boot_matrix = rng.choice(r_multiples, size=(iterations, n), replace=True)
        boot_means = np.mean(boot_matrix, axis=1)

        stderr = float(np.std(boot_means))
        ci_lower = float(mean_r - (1.96 * stderr))
        ci_upper = float(mean_r + (1.96 * stderr))
        return stderr, ci_lower, ci_upper

    @staticmethod
    def _skewness(data: np.ndarray) -> float:
        if len(data) < 3:
            return 0.0
        m = np.mean(data)
        s = np.std(data)
        if s == 0:
            return 0.0
        return float(np.mean(((data - m) / s) ** 3))

    @staticmethod
    def _empty_report(account: Optional[PropFirmAccountTracker]) -> Dict[str, Any]:
        return {
            "summary": {
                "total_trades": 0, "win_rate_pct": 0.0, "win_rate_wilson_ci95": [0.0, 0.0],
                "total_net_pnl": 0.0, "profit_factor": 0.0, "expectancy_dollars": 0.0,
                "expectancy_r": 0.0, "expectancy_r_stderr": 0.0, "expectancy_r_ci95": [0.0, 0.0],
                "max_drawdown_dollars": 0.0, "is_sufficient_sample": False,
                "sample_significance_status": "INSUFFICIENT_SAMPLE (N = 0 / 30 minimum)",
                "sample_warning": "STATUS: INSUFFICIENT_SAMPLE (N = 0 / 30 minimum)"
            },
            "excursion": {"drift_ratio": 0.0, "is_alpha_disqualified": True},
            "loss_taxonomy": {"total_losses": 0, "breakdown": {}},
            "friction_frontier": {"frontier_table": [], "critical_slippage_s_star": 0.0},
            "regimes": {},
            "prop_firm": {}
        }
