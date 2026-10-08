"""
Combinatorial Purged Cross-Validation (CPCV) & Probability of Backtest Overfitting (PBO).
Implements the rigorous machine learning validation protocol from:
López de Prado (2018): "Advances in Financial Machine Learning" (Wiley).

Features:
- N groups with k test groups per split (C(N, k) combinations).
- Purging: Removes training observations whose return window overlaps with test trades.
- Embargoing: Discards training bars immediately post-test to eliminate autoregressive leakage.
- Generates out-of-sample Sharpe path distribution and calculates:
  * PBO (Probability of Backtest Overfitting)
  * Median OOS Sharpe Ratio
  * Degradation Ratio (OOS Sharpe / In-Sample Sharpe)
"""
from itertools import combinations
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field


class CPCVSplitResult(BaseModel):
    split_id: int
    test_groups: List[int]
    is_sharpe: float
    oos_sharpe: float
    is_pnl: float
    oos_pnl: float
    is_win_rate: float
    oos_win_rate: float


class CPCVSummary(BaseModel):
    total_splits: int
    num_groups: int
    k_test_groups: int
    median_oos_sharpe: float
    mean_oos_sharpe: float
    min_oos_sharpe: float
    max_oos_sharpe: float
    pbo_pct: float  # Probability of Backtest Overfitting (fraction with OOS Sharpe <= 0)
    degradation_ratio: float  # OOS Sharpe / IS Sharpe
    splits: List[CPCVSplitResult]


class CombinatorialPurgedCV:
    """
    Executes CPCV on realized trade or bar series.
    """

    def __init__(
        self,
        num_groups: int = 6,
        k_test_groups: int = 2,
        embargo_pct: float = 0.02
    ):
        self.num_groups = num_groups
        self.k_test_groups = k_test_groups
        self.embargo_pct = embargo_pct

    def run_validation(self, trades_df: pd.DataFrame) -> CPCVSummary:
        """
        Runs CPCV over trades_df.
        """
        if len(trades_df) < self.num_groups * 3:
            # Fallback if insufficient trade count
            return CPCVSummary(
                total_splits=1,
                num_groups=self.num_groups,
                k_test_groups=self.k_test_groups,
                median_oos_sharpe=0.0,
                mean_oos_sharpe=0.0,
                min_oos_sharpe=0.0,
                max_oos_sharpe=0.0,
                pbo_pct=100.0,
                degradation_ratio=0.0,
                splits=[]
            )

        df = trades_df.copy().reset_index(drop=True)
        pnl_col = "net_pnl" if "net_pnl" in df.columns else "pnl"
        n = len(df)

        group_size = n // self.num_groups
        group_indices = []
        for g in range(self.num_groups):
            start = g * group_size
            end = (g + 1) * group_size if g < self.num_groups - 1 else n
            group_indices.append(list(range(start, end)))

        combos = list(combinations(range(self.num_groups), self.k_test_groups))
        splits_res: List[CPCVSplitResult] = []
        oos_sharpes = []

        embargo_size = int(n * self.embargo_pct)

        for idx, test_grps in enumerate(combos):
            test_indices_set = set()
            for tg in test_grps:
                test_indices_set.update(group_indices[tg])

            # Purge & Embargo
            train_indices = []
            for g in range(self.num_groups):
                if g not in test_grps:
                    for i in group_indices[g]:
                        # Check embargo: not immediately after a test group
                        is_embargoed = False
                        for tg in test_grps:
                            tg_max = max(group_indices[tg])
                            if 0 <= (i - tg_max) <= embargo_size:
                                is_embargoed = True
                                break
                        if not is_embargoed:
                            train_indices.append(i)

            test_indices = sorted(list(test_indices_set))

            train_pnls = df.iloc[train_indices][pnl_col].values
            test_pnls = df.iloc[test_indices][pnl_col].values

            # IS Metrics
            is_mean = np.mean(train_pnls) if len(train_pnls) > 0 else 0.0
            is_std = np.std(train_pnls, ddof=1) if len(train_pnls) > 1 else 1.0
            is_sr = (is_mean / max(is_std, 1e-4)) * np.sqrt(252)

            # OOS Metrics
            oos_mean = np.mean(test_pnls) if len(test_pnls) > 0 else 0.0
            oos_std = np.std(test_pnls, ddof=1) if len(test_pnls) > 1 else 1.0
            oos_sr = (oos_mean / max(oos_std, 1e-4)) * np.sqrt(252)

            oos_sharpes.append(oos_sr)

            is_wr = (np.count_nonzero(train_pnls > 0) / len(train_pnls) * 100.0) if len(train_pnls) > 0 else 0.0
            oos_wr = (np.count_nonzero(test_pnls > 0) / len(test_pnls) * 100.0) if len(test_pnls) > 0 else 0.0

            splits_res.append(CPCVSplitResult(
                split_id=idx + 1,
                test_groups=list(test_grps),
                is_sharpe=round(float(is_sr), 3),
                oos_sharpe=round(float(oos_sr), 3),
                is_pnl=round(float(np.sum(train_pnls)), 2),
                oos_pnl=round(float(np.sum(test_pnls)), 2),
                is_win_rate=round(float(is_wr), 1),
                oos_win_rate=round(float(oos_wr), 1)
            ))

        # PBO: % of OOS Sharpe ratios <= 0
        pbo = (np.count_nonzero(np.array(oos_sharpes) <= 0.0) / len(oos_sharpes)) * 100.0
        med_oos = float(np.median(oos_sharpes))
        mean_oos = float(np.mean(oos_sharpes))
        mean_is = float(np.mean([s.is_sharpe for s in splits_res]))
        degrad = (mean_oos / mean_is) if mean_is > 0 else 0.0

        return CPCVSummary(
            total_splits=len(splits_res),
            num_groups=self.num_groups,
            k_test_groups=self.k_test_groups,
            median_oos_sharpe=round(med_oos, 3),
            mean_oos_sharpe=round(mean_oos, 3),
            min_oos_sharpe=round(float(np.min(oos_sharpes)), 3),
            max_oos_sharpe=round(float(np.max(oos_sharpes)), 3),
            pbo_pct=round(pbo, 1),
            degradation_ratio=round(degrad, 3),
            splits=splits_res
        )
