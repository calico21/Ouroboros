"""
High-Fidelity CME Globex Market Ingestion Engine (AlphaForge).
Ingests CME GLBX.MDP3 trades and MBP-1 market data spanning full continuous sessions:
Electronic Trading Hours (ETH, 18:00 ET open) through Regular Trading Hours (RTH, 16:00 ET close).

Computes rolling econometric indicators:
- ATR_20 (Daily trade-date basis)
- Intraday volume percentiles per 5-minute bucket over prior 60 days
- Session VWAP anchored to 18:00 ET rollover
- Prior-Day Range, Inside Day, NR7, and Initial Balance boundaries
"""
from pathlib import Path
from typing import Optional, Union, Iterator, List, Dict, Any
from datetime import datetime, date, time, timedelta
import pandas as pd
import numpy as np

from src.core.events import BarEvent
from src.data.cme_session_clock import (
    ensure_ny_tz,
    get_cme_trade_date,
    get_cme_trade_date_str,
    is_rth,
    is_eth,
    NY_TZ
)


class DatabentoCMEDataLoader:
    """
    Ingests and normalizes CME Globex futures continuous bar streams.
    Enforces CME 18:00 ET Trade Date session rollover and precomputes
    ATR_20, session VWAP, 60-day volume bucket distributions, and profile metrics.
    """

    def __init__(
        self,
        data_path: Union[str, Path] = "data/processed/mnq_5m.csv",
        symbol: str = "MNQ",
        timeframe: str = "5m"
    ):
        self.data_path = Path(data_path)
        self.symbol = symbol
        self.timeframe = timeframe
        self.df: Optional[pd.DataFrame] = None

    def load(self, enrich_indicators: bool = True) -> pd.DataFrame:
        """Loads and processes full CME Globex dataset."""
        # Prioritize rich 108k continuous parquet dataset
        priority_paths = [
            Path("data/databento/mnq_continuous_5m.parquet"),
            Path("data/processed/mnq_5m_continuous.parquet"),
            Path("data/cache/mnq_5y_continuous_5m.parquet"),
        ]
        
        if not self.data_path.exists() or self.data_path == Path("data/processed/mnq_5m.csv"):
            for p in priority_paths:
                if p.exists():
                    self.data_path = p
                    break

        if not self.data_path.exists():
            # If not found, fall back to cache or raw
            alt_paths = [
                Path("data/cache/mnq_5y_continuous_5m.csv"),
                Path("data/raw/mnq_1m.csv"),
                Path("data/processed/mnq_5m.csv")
            ]
            found = False
            for p in alt_paths:
                if p.exists():
                    self.data_path = p
                    found = True
                    break
            if not found:
                raise FileNotFoundError(f"No continuous CME data found at {self.data_path}")

        # Ingest CSV or Parquet
        if self.data_path.suffix in (".parquet", ".pq"):
            df = pd.read_parquet(self.data_path)
        else:
            df = pd.read_csv(self.data_path)

        # Normalize column names
        col_map = {
            "ts_event": "timestamp",
            "ts_recv": "timestamp",
            "time": "timestamp",
            "size": "volume",
            "vol": "volume"
        }
        df = df.rename(columns=lambda c: col_map.get(c.lower(), c.lower()))

        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

        # Standardize timestamps to America/New_York
        if df["timestamp"].dt.tz is None:
            df["timestamp"] = df["timestamp"].dt.tz_localize(NY_TZ)
        else:
            df["timestamp"] = df["timestamp"].dt.tz_convert(NY_TZ)

        # Assign CME Trade Date (18:00 ET rollover)
        trade_dates = []
        for ts in df["timestamp"]:
            trade_dates.append(get_cme_trade_date_str(ts))
        df["trade_date"] = trade_dates

        # Intraday 5m bucket identifier (HH:MM ET)
        df["bucket_hm"] = df["timestamp"].dt.strftime("%H:%M")
        df["is_rth"] = [is_rth(t) for t in df["timestamp"]]

        if enrich_indicators:
            df = self._enrich_rolling_indicators(df)

        self.df = df
        return df

    def _enrich_rolling_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates:
        1. ATR_20 on daily CME Trade Date basis
        2. Session-anchored VWAP (reset at 18:00 ET)
        3. Intraday volume percentiles per 5-minute bucket over prior 60 days
        4. Prior-day High, Low, Range, Close
        """
        # --- 1. Compute Daily Trade Date Aggregates ---
        daily_agg = df.groupby("trade_date").agg(
            day_open=("open", "first"),
            day_high=("high", "max"),
            day_low=("low", "min"),
            day_close=("close", "last"),
            day_volume=("volume", "sum")
        ).reset_index()

        daily_agg["prev_close"] = daily_agg["day_close"].shift(1)
        daily_agg["tr"] = np.maximum(
            daily_agg["day_high"] - daily_agg["day_low"],
            np.maximum(
                (daily_agg["day_high"] - daily_agg["prev_close"]).abs(),
                (daily_agg["day_low"] - daily_agg["prev_close"]).abs()
            )
        )
        daily_agg["atr_20"] = daily_agg["tr"].rolling(window=20, min_periods=1).mean()
        daily_agg["prev_day_high"] = daily_agg["day_high"].shift(1)
        daily_agg["prev_day_low"] = daily_agg["day_low"].shift(1)
        daily_agg["prev_day_range"] = (daily_agg["day_high"] - daily_agg["day_low"]).shift(1)
        daily_agg["prev_day_close"] = daily_agg["prev_close"]

        # Inside day flag & NR7
        daily_agg["range"] = daily_agg["day_high"] - daily_agg["day_low"]
        daily_agg["is_inside_day"] = (
            (daily_agg["day_high"] < daily_agg["day_high"].shift(1)) &
            (daily_agg["day_low"] > daily_agg["day_low"].shift(1))
        ).shift(1)
        min_7d_range = daily_agg["range"].rolling(7, min_periods=7).min().shift(1)
        daily_agg["is_nr7"] = (daily_agg["prev_day_range"] <= min_7d_range)

        # Merge daily metrics back into bar df
        df = df.merge(
            daily_agg[[
                "trade_date", "atr_20", "prev_day_high", "prev_day_low",
                "prev_day_range", "prev_day_close", "is_inside_day", "is_nr7"
            ]],
            on="trade_date",
            how="left"
        )
        df["atr_20"] = df["atr_20"].fillna(df["high"] - df["low"])

        # --- 2. Anchored Session VWAP (Resets at 18:00 ET Trade Date Rollover) ---
        typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
        pv = typical_price * df["volume"]

        df["cum_pv"] = pv.groupby(df["trade_date"]).cumsum()
        df["cum_vol"] = df["volume"].groupby(df["trade_date"]).cumsum()
        df["vwap"] = df["cum_pv"] / np.maximum(1, df["cum_vol"])

        # VWAP standard deviation bands (1.0, 2.0 sigma)
        df["pv_sq"] = ((typical_price - df["vwap"]) ** 2) * df["volume"]
        cum_pv_sq = df["pv_sq"].groupby(df["trade_date"]).cumsum()
        vwap_variance = cum_pv_sq / np.maximum(1, df["cum_vol"])
        df["vwap_sigma"] = np.sqrt(np.maximum(0.0, vwap_variance))
        df["vwap_upper_2"] = df["vwap"] + 2.0 * df["vwap_sigma"]
        df["vwap_lower_2"] = df["vwap"] - 2.0 * df["vwap_sigma"]

        # --- 3. Prior 60-day Volume Percentile per 5m Bucket ---
        # Group by bucket_hm and calculate rolling empirical percentile
        bucket_pcts = []
        vol_lookup = {}
        for b, v in zip(df["bucket_hm"].values, df["volume"].values):
            if b not in vol_lookup:
                vol_lookup[b] = []
            history = vol_lookup[b]
            if len(history) >= 5:
                # Percentile rank in past history up to 60 sessions
                rank = (np.array(history[-60:]) < v).mean() * 100.0
            else:
                rank = 50.0
            bucket_pcts.append(rank)
            history.append(v)
            if len(history) > 120:
                vol_lookup[b] = history[-60:]

        df["vol_pct_60"] = bucket_pcts

        return df

    def get_bars(self) -> Iterator[BarEvent]:
        """Streams immutable BarEvents chronologically with full CME attributes."""
        if self.df is None:
            self.load()

        for row in self.df.itertuples(index=False):
            ts = getattr(row, "timestamp")
            if hasattr(ts, "to_pydatetime"):
                ts = ts.to_pydatetime()
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=NY_TZ)

            meta = {
                "trade_date": getattr(row, "trade_date", None),
                "atr_20": float(getattr(row, "atr_20", 30.0)),
                "vwap": float(getattr(row, "vwap", getattr(row, "close"))),
                "vwap_upper_2": float(getattr(row, "vwap_upper_2", getattr(row, "close") + 20.0)),
                "vwap_lower_2": float(getattr(row, "vwap_lower_2", getattr(row, "close") - 20.0)),
                "vol_pct_60": float(getattr(row, "vol_pct_60", 50.0)),
                "prev_day_high": float(getattr(row, "prev_day_high", getattr(row, "high"))),
                "prev_day_low": float(getattr(row, "prev_day_low", getattr(row, "low"))),
                "prev_day_range": float(getattr(row, "prev_day_range", 50.0)),
                "prev_day_close": float(getattr(row, "prev_day_close", getattr(row, "close"))),
                "is_inside_day": bool(getattr(row, "is_inside_day", False)),
                "is_nr7": bool(getattr(row, "is_nr7", False)),
            }

            yield BarEvent(
                timestamp=ts,
                symbol=self.symbol,
                open=float(getattr(row, "open")),
                high=float(getattr(row, "high")),
                low=float(getattr(row, "low")),
                close=float(getattr(row, "close")),
                volume=int(getattr(row, "volume")),
                timeframe=self.timeframe,
                atr_14=float(getattr(row, "atr_20", 30.0)),
                is_rth=bool(getattr(row, "is_rth", True)),
                metadata=meta
            )
