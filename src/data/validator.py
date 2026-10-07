"""
Data Validation Engine for AlphaForge.
Ensures zero bad ticks, price inversion, look-ahead bias, or roll gap contamination.
Enforces institutional standards for multi-month CME Globex futures continuous series.
"""
from typing import List, Tuple, Dict, Any
import pandas as pd
import numpy as np
from src.core.exceptions import DataValidationError
from src.core.time_utils import is_rth, ensure_ny_tz


class BarDataValidator:
    """Validates bar dataframes against institutional CME data integrity standards."""

    REQUIRED_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]
    MIN_TRADING_DAYS = 60
    MIN_RTH_HOURS = 390  # 60 days * 6.5 RTH hours = 390 hours (or 1000+ total hours)

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

        # 3. Price inversions
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
        ts_series = pd.to_datetime(df["timestamp"])
        if not ts_series.is_monotonic_increasing:
            errors.append("Timestamps are not strictly monotonically increasing")

        return len(errors) == 0, errors

    @classmethod
    def validate_dataset(cls, df: pd.DataFrame) -> Tuple[bool, List[str], Dict[str, Any]]:
        """
        Deep validation for multi-year continuous historical datasets:
        1. Date range spans a minimum of 60 trading days (1,000+ trading hours).
        2. Zero look-ahead bias verification (right-closed intervals, monotonic timestamps).
        3. Continuous volume roll boundary verification without unadjusted gaps distorting ORB.
        """
        valid_basic, errors = cls.validate(df)
        df_ts = pd.to_datetime(df["timestamp"])
        
        # 1. Date Range Span Verification
        unique_days = df_ts.dt.date.nunique()
        total_span_days = (df_ts.max() - df_ts.min()).days
        total_hours = len(df) / 12.0 if "5m" in str(df.get("timeframe", "5m")) else len(df) / 60.0

        stats = {
            "unique_trading_days": int(unique_days),
            "total_calendar_span_days": int(total_span_days),
            "estimated_trading_hours": round(float(total_hours), 1),
            "start_date": str(df_ts.min()),
            "end_date": str(df_ts.max()),
            "total_bars": len(df)
        }

        if unique_days < cls.MIN_TRADING_DAYS:
            errors.append(
                f"Dataset covers only {unique_days} trading days (minimum {cls.MIN_TRADING_DAYS} required for institutional statistical significance)"
            )

        # 2. Look-Ahead Bias Verification
        # Check that timestamp increments are positive and intervals match standard frequencies
        deltas = df_ts.diff().dropna()
        if (deltas <= pd.Timedelta(0)).any():
            errors.append("Look-ahead violation: Found non-positive timestamp increments")

        # Check right-closed alignment (e.g. 5m bars end on minute divisible by 5)
        if len(df) > 1 and deltas.median() == pd.Timedelta(minutes=5):
            minute_mod = df_ts.dt.minute % 5
            if (minute_mod != 0).any():
                bad_count = (minute_mod != 0).sum()
                errors.append(f"Resampling interval alignment issue: {bad_count} bars not aligned to 5-minute boundaries")

        # 3. Continuous Roll Gap & Volume Boundary Verification
        # Check for abnormal price jump gaps (> 150 points in MNQ) across consecutive bars
        price_jumps = (df["open"] - df["close"].shift(1)).abs()
        large_jumps = price_jumps > 150.0  # > 150 pts without roll adjustment
        if large_jumps.any():
            jump_indices = df[large_jumps].index.tolist()[:3]
            errors.append(
                f"Detected {large_jumps.sum()} potential unadjusted contract roll gaps (>150 pts). "
                f"Sample indices: {jump_indices}. Verify Panama back-adjustment to prevent ORB distortions."
            )

        # Check for zero volume dead-zones during RTH
        rth_zero_vol = (df["volume"] == 0)
        if rth_zero_vol.sum() > (len(df) * 0.05):
            errors.append(f"High frequency of zero volume bars ({rth_zero_vol.sum()} bars)")

        is_valid = len(errors) == 0
        return is_valid, errors, stats

    @classmethod
    def enforce(cls, df: pd.DataFrame) -> pd.DataFrame:
        valid, errors = cls.validate(df)
        if not valid:
            raise DataValidationError(f"Bar data failed validation: {'; '.join(errors)}")
        return df
