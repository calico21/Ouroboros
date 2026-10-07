"""
Data Ingestion and Bar Stream Loader for AlphaForge.
Loads, stitches, and normalizes historical CME Globex futures continuous datasets
from single files or directories of Parquet / CSV files (including Databento exports).
"""
from pathlib import Path
from typing import Iterator, Optional, Union, List
import pandas as pd
from src.core.events import BarEvent
from src.data.validator import BarDataValidator
from src.data.resampler import resample_bars
from src.core.time_utils import is_rth, ensure_ny_tz


class DataLoader:
    """
    Ingests and stitches single or partitioned CME Globex continuous datasets.
    Supports Databento parquet files and multi-month CSV archives.
    """

    DATABENTO_COL_MAP = {
        "ts_event": "timestamp",
        "ts_recv": "timestamp",
        "time": "timestamp",
        "size": "volume",
        "vol": "volume",
    }

    def __init__(self, data_path: Union[str, Path], symbol: str = "MNQ", timeframe: str = "5m"):
        self.data_path = Path(data_path)
        self.symbol = symbol
        self.timeframe = timeframe
        self._df: Optional[pd.DataFrame] = None

    def load(self, enforce_validation: bool = True) -> pd.DataFrame:
        if not self.data_path.exists():
            raise FileNotFoundError(f"Data source not found at: {self.data_path}")

        # Ingest single file or stitch partitioned directory
        if self.data_path.is_dir():
            df = self._stitch_directory(self.data_path)
        else:
            df = self._load_file(self.data_path)

        df = self._normalize_columns(df)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

        if enforce_validation:
            BarDataValidator.enforce(df)

        if self.timeframe != "1m" and "timeframe" not in df.columns:
            df = resample_bars(df, timeframe=self.timeframe)

        self._df = df
        return df

    def _load_file(self, file_path: Path) -> pd.DataFrame:
        """Loads a single CSV or Parquet file."""
        if file_path.suffix in [".parquet", ".pq"]:
            return pd.read_parquet(file_path)
        return pd.read_csv(file_path)

    def _stitch_directory(self, dir_path: Path) -> pd.DataFrame:
        """Stitches all CSV or Parquet partition files within a directory chronologically."""
        files = sorted(list(dir_path.glob("*.parquet")) + list(dir_path.glob("*.pq")) + list(dir_path.glob("*.csv")))
        if not files:
            raise FileNotFoundError(f"No parquet or csv files found in directory: {dir_path}")

        dfs = []
        for f in files:
            dfs.append(self._load_file(f))

        stitched = pd.concat(dfs, ignore_index=True)
        return stitched

    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalizes external / Databento column schemas to standard AlphaForge schema."""
        col_rename = {}
        for col in df.columns:
            col_lower = col.lower().strip()
            if col_lower in self.DATABENTO_COL_MAP:
                col_rename[col] = self.DATABENTO_COL_MAP[col_lower]
            elif col_lower in ["open", "high", "low", "close", "volume", "timestamp"]:
                col_rename[col] = col_lower

        df = df.rename(columns=col_rename)
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
