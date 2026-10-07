"""
Data Ingestion and Bar Stream Loader for AlphaForge.
Loads CSV or Parquet data, enforces data hygiene, and yields BarEvents.
"""
from pathlib import Path
from typing import Iterator, Optional, Union
import pandas as pd
from src.core.events import BarEvent
from src.data.validator import BarDataValidator
from src.data.resampler import resample_bars
from src.core.time_utils import is_rth, ensure_ny_tz


class DataLoader:
    """Loads historical futures data and converts into BarEvent generator."""

    def __init__(self, data_path: Union[str, Path], symbol: str = "MNQ", timeframe: str = "5m"):
        self.data_path = Path(data_path)
        self.symbol = symbol
        self.timeframe = timeframe
        self._df: Optional[pd.DataFrame] = None

    def load(self, enforce_validation: bool = True) -> pd.DataFrame:
        if not self.data_path.exists():
            raise FileNotFoundError(f"Data file not found at: {self.data_path}")

        if self.data_path.suffix in [".parquet", ".pq"]:
            df = pd.read_parquet(self.data_path)
        else:
            df = pd.read_csv(self.data_path)

        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values("timestamp").reset_index(drop=True)

        if enforce_validation:
            BarDataValidator.enforce(df)

        if self.timeframe != "1m" and "timeframe" not in df.columns:
            df = resample_bars(df, timeframe=self.timeframe)

        self._df = df
        return df

    def get_bars(self) -> Iterator[BarEvent]:
        """Stream bars sequentially to maintain causality and eliminate lookahead bias."""
        if self._df is None:
            self.load()

        for row in self._df.itertuples(index=False):
            ts = ensure_ny_tz(pd.Timestamp(row.timestamp).to_pydatetime())
            atr = getattr(row, "atr_14", None)
            yield BarEvent(
                timestamp=ts,
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=float(row.volume),
                symbol=self.symbol,
                timeframe=self.timeframe,
                is_rth=is_rth(ts),
                atr_14=float(atr) if (atr is not None and not pd.isna(atr)) else None
            )
