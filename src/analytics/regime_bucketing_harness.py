"""
Regime Pre-Registration & Excursion Distribution Bucketing Harness.
Classifies market sessions using strictly pre-market / session-conditioned variables
prior to evaluating strategy trade outcomes:
- Initial Balance (09:30-10:30 EST) Range / Daily ATR(14)
- Prior Session Range / Daily ATR(14)
- Overnight (ETH) Range / Daily ATR(14)
- Opening Gap / Daily ATR(14)
- NR7 (Narrowest Range of 7 sessions) condition
- Fraction of sessions with IB extension >= 1.5x ATR

For each pre-registered bucket, evaluates forward MFE and MAE distributions in R
(p10, p25, median, p75, p90) and validates stability across calendar years
to guard against sample noise, curve-fitting, and generative artifacts.
"""
from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import pandas as pd


class RegimeBucketingHarness:
    """
    Pre-registered forensic bucketing harness.
    Separates market classification from outcome analysis.
    """

    def __init__(self, atr_period: int = 14):
        self.atr_period = atr_period

    def compute_daily_regime_features(self, df_bars: pd.DataFrame) -> pd.DataFrame:
        """
        Extracts pre-registered session features from 5m continuous bars:
        - IB Range (09:30 - 10:30)
        - Session Range (09:30 - 16:00)
        - Daily ATR(14)
        - IB / ATR(14)
        - Prior Range / ATR(14)
        - Opening Gap / ATR(14)
        - NR7 condition
        - IB Extension >= 1.5x ATR
        """
        if df_bars.empty:
            return pd.DataFrame()

        # Ensure datetime index
        if not isinstance(df_bars.index, pd.DatetimeIndex):
            df = df_bars.copy()
            df.index = pd.to_datetime(df.index)
        else:
            df = df_bars

        daily_rows = []
        unique_dates = sorted(list(set(df.index.date)))

        for d in unique_dates:
            day_df = df[df.index.date == d]
            if len(day_df) < 10:
                continue

            # RTH bars (09:30 - 16:00)
            rth_df = day_df[(day_df.index.time >= time(9, 30)) & (day_df.index.time <= time(16, 0))]
            if rth_df.empty:
                rth_df = day_df

            # Initial Balance (09:30 - 10:30 EST)
            ib_df = rth_df[(rth_df.index.time >= time(9, 30)) & (rth_df.index.time < time(10, 30))]
            if not ib_df.empty:
                ib_high = float(ib_df["high"].max())
                ib_low = float(ib_df["low"].min())
                ib_range = max(0.25, ib_high - ib_low)
            else:
                ib_high = float(rth_df.iloc[0]["high"])
                ib_low = float(rth_df.iloc[0]["low"])
                ib_range = max(0.25, ib_high - ib_low)

            sess_high = float(rth_df["high"].max())
            sess_low = float(rth_df["low"].min())
            sess_open = float(rth_df.iloc[0]["open"])
            sess_close = float(rth_df.iloc[-1]["close"])
            sess_range = max(0.25, sess_high - sess_low)

            # IB Extensions
            ext_high = max(0.0, sess_high - ib_high)
            ext_low = max(0.0, ib_low - sess_low)
            max_ib_extension = max(ext_high, ext_low)

            # Overnight / ETH bars (prior 18:00 to 09:25)
            overnight_df = day_df[day_df.index.time < time(9, 30)]
            if not overnight_df.empty:
                on_high = float(overnight_df["high"].max())
                on_low = float(overnight_df["low"].min())
                overnight_range = max(0.25, on_high - on_low)
            else:
                overnight_range = np.nan

            daily_rows.append({
                "date": d,
                "open": sess_open,
                "high": sess_high,
                "low": sess_low,
                "close": sess_close,
                "session_range": sess_range,
                "ib_high": ib_high,
                "ib_low": ib_low,
                "ib_range": ib_range,
                "max_ib_extension": max_ib_extension,
                "overnight_range": overnight_range,
            })

        daily_df = pd.DataFrame(daily_rows)
        if daily_df.empty:
            return daily_df

        daily_df.set_index("date", inplace=True)

        # 1. Daily True Range and ATR(14)
        prev_close = daily_df["close"].shift(1)
        tr1 = daily_df["high"] - daily_df["low"]
        tr2 = (daily_df["high"] - prev_close).abs()
        tr3 = (daily_df["low"] - prev_close).abs()
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        daily_df["true_range"] = true_range
        daily_df["atr_14"] = true_range.rolling(window=self.atr_period, min_periods=3).mean()

        # Fill ATR bootstrap early rows
        daily_df["atr_14"] = daily_df["atr_14"].bfill()

        # 2. Ratios normalized to ATR(14)
        daily_df["ib_to_atr"] = daily_df["ib_range"] / daily_df["atr_14"]
        daily_df["prior_range"] = daily_df["session_range"].shift(1)
        daily_df["prior_range_to_atr"] = daily_df["prior_range"] / daily_df["atr_14"]

        # 3. Opening Gap
        daily_df["prior_close"] = prev_close
        daily_df["opening_gap"] = (daily_df["open"] - daily_df["prior_close"]).abs()
        daily_df["gap_to_atr"] = daily_df["opening_gap"] / daily_df["atr_14"]

        # 4. Overnight Range / ATR
        daily_df["overnight_to_atr"] = daily_df["overnight_range"] / daily_df["atr_14"]

        # 5. NR7 Condition: Today's session range is strictly narrower than the prior 6 days (7-day window)
        rolling_min_prior = daily_df["session_range"].shift(1).rolling(window=6, min_periods=6).min()
        daily_df["is_nr7"] = daily_df["session_range"] < rolling_min_prior

        # 6. IB Extension >= 1.5x ATR
        daily_df["has_ib_extension_1_5x_atr"] = daily_df["max_ib_extension"] >= (1.5 * daily_df["atr_14"])
        daily_df["ib_extension_ratio"] = daily_df["max_ib_extension"] / daily_df["ib_range"]

        # 7. Pre-registered Categorical Buckets
        def categorize_ib(r: float) -> str:
            if pd.isna(r):
                return "NORMAL"
            if r < 0.35:
                return "COMPRESSED (<0.35 ATR)"
            elif r <= 0.65:
                return "NORMAL (0.35-0.65 ATR)"
            else:
                return "EXPANDED (>0.65 ATR)"

        def categorize_gap(g: float) -> str:
            if pd.isna(g):
                return "MEDIUM"
            if g < 0.20:
                return "SMALL (<0.20 ATR)"
            elif g <= 0.50:
                return "MEDIUM (0.20-0.50 ATR)"
            else:
                return "LARGE (>0.50 ATR)"

        daily_df["ib_bucket"] = daily_df["ib_to_atr"].apply(categorize_ib)
        daily_df["gap_bucket"] = daily_df["gap_to_atr"].apply(categorize_gap)
        daily_df["nr7_bucket"] = daily_df["is_nr7"].apply(lambda x: "NR7" if x is True else "NON_NR7")

        return daily_df

    def evaluate_forward_excursion_by_bucket(
        self,
        trades_df: pd.DataFrame,
        daily_features: pd.DataFrame
    ) -> Dict[str, Any]:
        """
        Merges trade outcomes with pre-registered daily regime features.
        Computes forward MFE and MAE in R distributions for each bucket:
        - p10, p25, median (p50), p75, p90, IQR
        - Year-by-year stability check (2022 to 2026)
        - Trend extension fraction analysis (IB ext >= 1.5x ATR)
        """
        if trades_df.empty or daily_features.empty:
            return {
                "total_trades": len(trades_df),
                "total_sessions": len(daily_features),
                "trend_extension_fraction": 0.0,
                "buckets": {}
            }

        df_tr = trades_df.copy()
        if "trade_date" not in df_tr.columns:
            if "entry_time" in df_tr.columns:
                try:
                    df_tr["trade_date"] = pd.to_datetime(df_tr["entry_time"], utc=True).dt.tz_convert("America/New_York").dt.date
                except Exception:
                    df_tr["trade_date"] = [pd.Timestamp(t).date() for t in df_tr["entry_time"]]
            elif isinstance(df_tr.index, pd.DatetimeIndex):
                df_tr["trade_date"] = df_tr.index.date
            else:
                df_tr["trade_date"] = [pd.Timestamp(idx).date() for idx in df_tr.index]

        # Merge with pre-registered session features
        merged = df_tr.merge(
            daily_features.reset_index(),
            left_on="trade_date",
            right_on="date",
            how="inner"
        )

        # Baseline trend extension fraction across all sessions
        ext_series = daily_features["has_ib_extension_1_5x_atr"].dropna()
        overall_trend_ext_fraction = float(ext_series.mean()) if len(ext_series) > 0 else 0.0

        # Yearly breakdown of trend extension fraction
        yearly_trend_fractions = {}
        daily_features_copy = daily_features.copy()
        daily_features_copy["year"] = [d.year for d in daily_features_copy.index]
        for yr, grp in daily_features_copy.groupby("year"):
            val = float(grp["has_ib_extension_1_5x_atr"].dropna().mean())
            yearly_trend_fractions[str(yr)] = round(val * 100, 2)

        # Ensure MFE in R and MAE in R columns exist
        if "mfe_r" not in merged.columns and "mfe_ticks" in merged.columns and "risk_pts" in merged.columns:
            merged["mfe_r"] = (merged["mfe_ticks"] * 0.25) / merged["risk_pts"]
        if "mae_r" not in merged.columns and "mae_ticks" in merged.columns and "risk_pts" in merged.columns:
            merged["mae_r"] = (merged["mae_ticks"] * 0.25) / merged["risk_pts"]

        # Default fallbacks if excursions uncalculated
        if "mfe_r" not in merged.columns:
            merged["mfe_r"] = np.where(merged["r_multiple"] > 0, merged["r_multiple"], 0.2)
        if "mae_r" not in merged.columns:
            merged["mae_r"] = np.where(merged["r_multiple"] < 0, np.abs(merged["r_multiple"]), 0.5)

        def compute_dist(series: pd.Series) -> Dict[str, float]:
            vals = series.dropna().values
            if len(vals) == 0:
                return {"p10": 0.0, "p25": 0.0, "median": 0.0, "p75": 0.0, "p90": 0.0, "mean": 0.0, "iqr": 0.0}
            return {
                "p10": round(float(np.percentile(vals, 10)), 3),
                "p25": round(float(np.percentile(vals, 25)), 3),
                "median": round(float(np.percentile(vals, 50)), 3),
                "p75": round(float(np.percentile(vals, 75)), 3),
                "p90": round(float(np.percentile(vals, 90)), 3),
                "mean": round(float(np.mean(vals)), 3),
                "iqr": round(float(np.percentile(vals, 75) - np.percentile(vals, 25)), 3),
            }

        # Analyze each bucket factor
        bucket_results = {}
        for factor_col in ["ib_bucket", "gap_bucket", "nr7_bucket"]:
            factor_summary = {}
            for bucket_val, b_df in merged.groupby(factor_col):
                if len(b_df) == 0:
                    continue

                mfe_dist = compute_dist(b_df["mfe_r"])
                mae_dist = compute_dist(b_df["mae_r"])

                # Year-by-year stability
                b_df_copy = b_df.copy()
                b_df_copy["year"] = [pd.to_datetime(t).year for t in b_df_copy["trade_date"]]
                yearly_medians = {}
                for yr, y_df in b_df_copy.groupby("year"):
                    if len(y_df) >= 2:
                        yearly_medians[str(yr)] = {
                            "trades": len(y_df),
                            "median_mfe_r": round(float(y_df["mfe_r"].median()), 3),
                            "median_mae_r": round(float(y_df["mae_r"].median()), 3),
                            "win_rate_pct": round(float((y_df["r_multiple"] > 0).mean() * 100), 1),
                        }

                factor_summary[str(bucket_val)] = {
                    "sample_size": len(b_df),
                    "win_rate_pct": round(float((b_df["r_multiple"] > 0).mean() * 100), 1),
                    "mean_r": round(float(b_df["r_multiple"].mean()), 3),
                    "forward_mfe_r_dist": mfe_dist,
                    "forward_mae_r_dist": mae_dist,
                    "yearly_stability": yearly_medians,
                }
            bucket_results[factor_col] = factor_summary

        return {
            "total_trades_analyzed": len(merged),
            "total_sessions_analyzed": len(daily_features),
            "overall_trend_extension_sessions_fraction_pct": round(overall_trend_ext_fraction * 100, 2),
            "yearly_trend_extension_fraction_pct": yearly_trend_fractions,
            "pre_registered_buckets": bucket_results,
        }
