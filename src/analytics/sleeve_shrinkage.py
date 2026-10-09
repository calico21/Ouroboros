"""
Hierarchical Bayesian & James-Stein Sleeve Shrinkage and Deflated Sharpe Engine.
Organizes AlphaForge's 10 strategies into 5 structural sleeves:
- Sleeve A: ETH Imbalances (macro_overshoot_fade, thin_eth_gap_failure)
- Sleeve B: Compression & Expansion (coil_expansion, post_opex_gamma_release)
- Sleeve C: Auction Profile & Value Area (ib_failed_extension_rotation, va_traverse_80pct)
- Sleeve D: Cash Close & Structural Flows (letf_rebalance_continuation, moc_imbalance_response)
- Sleeve E: Bounded Intraday Mean Reversion (midday_equilibrium_fade, positive_gamma_pin_fade)

Applies James-Stein / Empirical Bayes shrinkage across sleeve returns to eliminate
selection bias and computes the Deflated Sharpe Ratio (DSR, Bailey & Lopez de Prado 2014)
penalizing for multiple testing (K >= 10 x variants).
"""
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import scipy.stats as stats


SLEEVE_MAPPING = {
    "sleeve_a_eth": ["macro_overshoot_fade", "thin_eth_gap_failure"],
    "sleeve_b_compression": ["coil_expansion", "post_opex_gamma_release"],
    "sleeve_c_auction": ["ib_failed_extension_rotation", "va_traverse_80pct"],
    "sleeve_d_cash_close": ["letf_rebalance_continuation", "moc_imbalance_response"],
    "sleeve_e_bounded_mr": ["midday_equilibrium_fade", "positive_gamma_pin_fade"]
}

STRATEGY_TO_SLEEVE = {
    strat: sleeve for sleeve, strats in SLEEVE_MAPPING.items() for strat in strats
}


class SleeveShrinkageEngine:
    """
    Applies empirical Bayes and James-Stein shrinkage pooling across correlated sleeves
    and computes Deflated Sharpe Ratio controlling for multiple hypothesis testing.
    """

    def __init__(self, k_variants_multiplier: int = 10):
        self.k_multiplier = k_variants_multiplier

    def compute_sleeve_shrinkage(
        self,
        strategy_metrics: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Pools metrics by sleeve, computes within-sleeve and cross-sleeve variance,
        and applies James-Stein shrinkage to observed expectancies and Sharpe ratios.
        """
        raw_sharpes = {}
        raw_expectancies = {}
        sleeve_data = {sleeve: [] for sleeve in SLEEVE_MAPPING}

        for strat_name, met in strategy_metrics.items():
            sleeve = STRATEGY_TO_SLEEVE.get(strat_name, "sleeve_unassigned")
            sharpe = met.get("calendar_metrics", {}).get("calendar_sharpe", met.get("summary", {}).get("sharpe_ratio", 0.0))
            exp_r = met.get("summary", {}).get("expectancy_r", 0.0)

            raw_sharpes[strat_name] = float(sharpe)
            raw_expectancies[strat_name] = float(exp_r)

            if sleeve in sleeve_data:
                sleeve_data[sleeve].append((strat_name, float(sharpe), float(exp_r)))

        # James-Stein Shrinkage on Sharpe Ratios across all candidates
        strat_names = list(raw_sharpes.keys())
        p = len(strat_names)
        if p >= 3:
            y = np.array([raw_sharpes[k] for k in strat_names], dtype=np.float64)
            mu_grand = np.mean(y)
            var_sample = np.var(y, ddof=1)
            sigma_sq = 0.50  # Conservative estimation variance

            # James-Stein shrinkage factor: c = max(0, 1 - (p - 2) * sigma_sq / sum((y - mu)^2))
            denom = np.sum((y - mu_grand) ** 2)
            c = max(0.0, 1.0 - ((p - 2) * sigma_sq) / max(1e-6, denom))

            shrunk_sharpes = {}
            for i, k in enumerate(strat_names):
                shrunk_sharpes[k] = round(float(mu_grand + c * (y[i] - mu_grand)), 3)
        else:
            shrunk_sharpes = {k: round(v, 3) for k, v in raw_sharpes.items()}

        # Sleeve-level aggregated summaries
        sleeves_summary = {}
        for sleeve_name, strats in sleeve_data.items():
            if strats:
                s_sharpes = [s[1] for s in strats]
                s_exps = [s[2] for s in strats]
                sleeves_summary[sleeve_name] = {
                    "strategies": [s[0] for s in strats],
                    "raw_mean_sharpe": round(float(np.mean(s_sharpes)), 3),
                    "raw_mean_expectancy_r": round(float(np.mean(s_exps)), 3),
                    "shrunk_mean_sharpe": round(float(np.mean([shrunk_sharpes.get(s[0], 0.0) for s in strats])), 3)
                }

        return {
            "sleeve_summaries": sleeves_summary,
            "shrunk_sharpes": shrunk_sharpes,
            "raw_sharpes": raw_sharpes,
            "raw_expectancies": raw_expectancies
        }

    def compute_deflated_sharpe(
        self,
        observed_sharpe: float,
        n_periods: int,
        k_trials: int,
        skewness: float = 0.0,
        kurtosis: float = 3.0
    ) -> Dict[str, Any]:
        """
        Deflated Sharpe Ratio (Bailey & Lopez de Prado 2014).
        Adjusts for non-normality (skewness, kurtosis) and multiple testing over K trials.
        Hurdle SR* = sqrt(2 * ln(K)) * (1 - euler / sqrt(2 * ln(K)))
        """
        if n_periods <= 2 or observed_sharpe <= 0:
            return {
                "deflated_sharpe_ratio": 0.0,
                "probabilistic_sharpe_ratio": 0.0,
                "sr_star_hurdle": 0.0,
                "passes_hurdle": False,
                "k_trials": k_trials
            }

        euler_mascheroni = 0.5772156649
        z_k = np.sqrt(2.0 * np.log(max(2, k_trials)))
        # Expected max Sharpe under null of zero true edge across K trials
        sr_star = z_k + (euler_mascheroni / z_k) if z_k > 0 else 0.0

        # Adjust for sample size and higher moments
        sr_std = np.sqrt(
            (1.0 - skewness * observed_sharpe + ((kurtosis - 1.0) / 4.0) * (observed_sharpe ** 2)) /
            max(1, n_periods - 1)
        )

        if sr_std > 0:
            test_stat = (observed_sharpe - sr_star) / sr_std
            dsr = float(stats.norm.cdf(test_stat))
            psr = float(stats.norm.cdf(observed_sharpe / sr_std))
        else:
            dsr = 0.0
            psr = 0.0

        return {
            "deflated_sharpe_ratio": round(dsr, 4),
            "probabilistic_sharpe_ratio": round(psr, 4),
            "sr_star_hurdle": round(float(sr_star), 3),
            "passes_hurdle": bool(dsr >= 0.95),
            "k_trials": k_trials,
            "n_periods": n_periods
        }
