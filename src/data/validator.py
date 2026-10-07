"""
Data Validation Engine for AlphaForge.
Ensures zero bad ticks, price inversion, or missing values contaminate alpha signals.
"""
from typing import List, Tuple
import pandas as pd
from src.core.exceptions import DataValidationError


class BarDataValidator:
    """Validates bar dataframes against institutional CME data integrity standards."""

    REQUIRED_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]

    @classmethod
    def validate(cls, df: pd.DataFrame) -> Tuple[bool, List[str]]:
        errors = []

        # 1. Column existence
        for col in cls.REQUIRED_COLUMNS:
            if col not in df.columns:
                errors.append(f"Missing required column: {col}")
        
        if errors:
            return False, errors

        # 2. Null values
        null_counts = df[cls.REQUIRED_COLUMNS].isnull().sum()
        if null_counts.any():
            for col, count in null_counts.items():
                if count > 0:
                    errors.append(f"Column {col} contains {count} null values")

        # 3. Price inversions: High >= Low, High >= Open, High >= Close, Low <= Open, Low <= Close
        inversions = (
            (df["high"] < df["low"]) |
            (df["high"] < df["open"]) |
            (df["high"] < df["close"]) |
            (df["low"] > df["open"]) |
            (df["low"] > df["close"])
        )
        if inversions.any():
            bad_idx = df[inversions].index.tolist()[:5]
            errors.append(f"Detected {inversions.sum()} price inversion rows (sample indices: {bad_idx})")

        # 4. Non-positive prices or negative volume
        if (df["open"] <= 0).any() or (df["close"] <= 0).any():
            errors.append("Detected non-positive prices")
        if (df["volume"] < 0).any():
            errors.append("Detected negative volume")

        # 5. Monotonic timestamps
        if not pd.to_datetime(df["timestamp"]).is_monotonic_increasing:
            errors.append("Timestamps are not strictly monotonically increasing")

        return len(errors) == 0, errors

    @classmethod
    def enforce(cls, df: pd.DataFrame) -> pd.DataFrame:
        valid, errors = cls.validate(df)
        if not valid:
            raise DataValidationError(f"Bar data failed validation: {'; '.join(errors)}")
        return df
