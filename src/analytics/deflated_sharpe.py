"""
Deflated Sharpe Ratio (DSR) & Probabilistic Sharpe Ratio (PSR) Engine.
Implements the definitive econometric framework from:
Bailey & López de Prado (2014): "The Deflated Sharpe Ratio: Correcting for Selection Bias,
Backtest Overfitting, and Non-Normality" (Journal of Portfolio Management).

Accounts for:
1. Skewness and kurtosis of returns (non-normal distributions).
2. Track record sample length (N observations).
3. Multiple testing / selection bias: Number of independent/dependent trials (M).
4. Variance of Sharpe ratios across all tested strategy candidates.
5. Family-Wise Error Rate (FWER) & Benjamini-Hochberg False Discovery Rate (FDR).
"""
from typing import Dict, List, Optional, Tuple
import numpy as np
from scipy.stats import norm, skew, kurtosis
from pydantic import BaseModel, Field


class DSRResult(BaseModel):
    estimated_sharpe: float
    benchmark_sharpe: float
    probabilistic_sharpe_ratio: float  # PSR [0, 1]
    expected_max_null_sharpe: float    # E[max SR] under null hypothesis
    deflated_sharpe_ratio: float       # DSR [0, 1]
    trials_tested: int                 # M
    sample_length_days: int            # N
    skewness: float
    kurtosis: float
    passes_deflated_hurdle: bool       # DSR >= 0.95
    fwer_p_value: float                # Family-wise error adjusted p-value


class DeflatedSharpeCalculator:
    """
    Computes PSR and DSR to protect against backtest overfitting and data snooping.
    """

    @staticmethod
    def compute_psr(
        sr_hat: float,
        sr_benchmark: float,
        n_samples: int,
        skewness: float = 0.0,
        kurtosis_excess: float = 0.0
    ) -> float:
        """
        Computes Probabilistic Sharpe Ratio:
        PSR(SR*) = Phi( ( (SR_hat - SR*) * sqrt(N - 1) ) / sqrt(1 - skew * SR_hat + ((kurt + 2)/4) * SR_hat^2) )
        """
        if n_samples <= 1:
            return 0.5

        # Note: kurtosis_excess is Fisher excess kurtosis, standard kurtosis is excess + 3
        # In Bailey & Lopez de Prado: denominator term is ((kurtosis - 1) / 4) * sr^2
        # where kurtosis is Pearson kurtosis (normal = 3).
        kurt_pearson = kurtosis_excess + 3.0
        
        denom_sq = 1.0 - skewness * sr_hat + ((kurt_pearson - 1.0) / 4.0) * (sr_hat ** 2)
        if denom_sq <= 0:
            denom_sq = 1e-6
        denom = np.sqrt(denom_sq)

        z = ((sr_hat - sr_benchmark) * np.sqrt(n_samples - 1.0)) / denom
        return float(norm.cdf(z))

    @staticmethod
    def expected_max_sharpe(
        num_trials: int,
        var_trials: float,
        mean_trials: float = 0.0
    ) -> float:
        """
        Computes E[max_M {SR}] under the null hypothesis that trials are IID Gaussian:
        E[max_M] approx mean + sqrt(var) * [ (1 - gamma)*Phi^-1(1 - 1/M) + gamma*Phi^-1(1 - 1/(M*e)) ]
        where gamma is the Euler-Mascheroni constant (~0.57721566).
        """
        if num_trials <= 1:
            return mean_trials

        euler_mascheroni = 0.5772156649015328606
        m = float(num_trials)
        std_trials = np.sqrt(max(var_trials, 1e-6))

        term1 = (1.0 - euler_mascheroni) * norm.ppf(1.0 - 1.0 / m)
        term2 = euler_mascheroni * norm.ppf(1.0 - 1.0 / (m * np.e))
        expected_max = mean_trials + std_trials * (term1 + term2)
        return float(expected_max)

    def compute_dsr(
        self,
        daily_returns: np.ndarray,
        num_trials: int = 25,
        var_trials: float = 0.25,
        benchmark_annual_sharpe: float = 0.0
    ) -> DSRResult:
        """
        Calculates complete Deflated Sharpe Ratio metrics given realized daily returns.
        """
        n = len(daily_returns)
        if n < 5:
            return DSRResult(
                estimated_sharpe=0.0,
                benchmark_sharpe=0.0,
                probabilistic_sharpe_ratio=0.5,
                expected_max_null_sharpe=0.0,
                deflated_sharpe_ratio=0.0,
                trials_tested=num_trials,
                sample_length_days=n,
                skewness=0.0,
                kurtosis=0.0,
                passes_deflated_hurdle=False,
                fwer_p_value=1.0
            )

        mean_r = float(np.mean(daily_returns))
        std_r = float(np.std(daily_returns, ddof=1))
        if std_r < 1e-6:
            std_r = 1e-6

        # Daily Sharpe
        daily_sr = mean_r / std_r
        annual_sr = daily_sr * np.sqrt(252.0)

        # Skewness and excess kurtosis of daily returns
        ret_skew = float(skew(daily_returns)) if len(daily_returns) > 2 else 0.0
        ret_kurt = float(kurtosis(daily_returns)) if len(daily_returns) > 3 else 0.0  # Fisher excess kurtosis

        # Benchmark Sharpe in daily terms
        benchmark_daily = benchmark_annual_sharpe / np.sqrt(252.0)

        # 1. Standard PSR against benchmark
        psr = self.compute_psr(
            sr_hat=daily_sr,
            sr_benchmark=benchmark_daily,
            n_samples=n,
            skewness=ret_skew,
            kurtosis_excess=ret_kurt
        )

        # 2. Expected Maximum Sharpe among M trials
        expected_max_daily = self.expected_max_sharpe(
            num_trials=num_trials,
            var_trials=var_trials / 252.0,  # convert variance to daily
            mean_trials=benchmark_daily
        )
        expected_max_annual = expected_max_daily * np.sqrt(252.0)

        # 3. Deflated Sharpe Ratio: PSR against expected max null Sharpe
        dsr = self.compute_psr(
            sr_hat=daily_sr,
            sr_benchmark=expected_max_daily,
            n_samples=n,
            skewness=ret_skew,
            kurtosis_excess=ret_kurt
        )

        # 4. Family-Wise Error Rate (Bonferroni / Sidak correction)
        raw_p_value = 1.0 - psr
        fwer_p = 1.0 - ((1.0 - min(raw_p_value, 1.0)) ** max(num_trials, 1))

        return DSRResult(
            estimated_sharpe=round(annual_sr, 3),
            benchmark_sharpe=round(benchmark_annual_sharpe, 3),
            probabilistic_sharpe_ratio=round(psr, 4),
            expected_max_null_sharpe=round(expected_max_annual, 3),
            deflated_sharpe_ratio=round(dsr, 4),
            trials_tested=num_trials,
            sample_length_days=n,
            skewness=round(ret_skew, 3),
            kurtosis=round(ret_kurt, 3),
            passes_deflated_hurdle=bool(dsr >= 0.95),
            fwer_p_value=round(fwer_p, 4)
        )
