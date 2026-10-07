"""
Continuous Contract and Roll Handling for CME Futures.
Supports panama-canal back-adjustment and unadjusted front-month tracking.
"""
from typing import List
import pandas as pd


class ContinuousContractManager:
    """Manages continuous contract concatenation and roll adjustments."""

    @staticmethod
    def back_adjust(contracts: List[pd.DataFrame], roll_gaps: List[float]) -> pd.DataFrame:
        """
        Panama-canal cumulative difference back-adjustment.
        Preserves true price action geometry and bar spreads without artificial zero-bounds.
        """
        adjusted_dfs = []
        cumulative_gap = 0.0

        for df, gap in zip(reversed(contracts), reversed([0.0] + roll_gaps)):
            cumulative_gap += gap
            adj_df = df.copy()
            for col in ["open", "high", "low", "close"]:
                if col in adj_df.columns:
                    adj_df[col] = adj_df[col] + cumulative_gap
            adjusted_dfs.append(adj_df)

        return pd.concat(reversed(adjusted_dfs), ignore_index=True)
