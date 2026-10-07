"""
Bar Resampling Engine for AlphaForge.
Converts 1-minute CME base data into arbitrary timeframes (e.g. 5m, 15m) with ATR calculation.
"""
import pandas as pd
import numpy as np


def resample_bars(df: pd.DataFrame, timeframe: str = "5m") -> pd.DataFrame:
    """
    Resamples 1m data to target timeframe with standard OHLCV aggregation.
    Also computes 14-period Wilder's Average True Range (ATR).
    """
    df = df.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df.set_index("timestamp", inplace=True)

    rule_map = {
        "1m": "1T",
        "5m": "5T",
        "15m": "15T",
        "30m": "30T",
        "1h": "1H",
        "1d": "1D",
    }
    freq = rule_map.get(timeframe, timeframe)

    resampled = df.resample(freq, label="right", closed="right").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum"
    }).dropna()

    resampled.reset_index(inplace=True)

    # Calculate True Range and 14-period ATR
    high = resampled["high"].values
    low = resampled["low"].values
    close = resampled["close"].values
    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]

    tr1 = high - low
    tr2 = np.abs(high - prev_close)
    tr3 = np.abs(low - prev_close)
    tr = np.maximum(tr1, np.maximum(tr2, tr3))

    # Wilder's exponential smoothing for ATR
    atr = pd.Series(tr).ewm(alpha=1/14, adjust=False).mean().values
    resampled["atr_14"] = atr

    return resampled
