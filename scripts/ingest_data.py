"""
Data Ingestion & High-Fidelity CME Globex Continuous Dataset Generator (AlphaForge).
Ingests and synthesizes full continuous CME Globex futures price action:
- Electronic Trading Hours (ETH): 18:00 ET open through 08:30 ET
- 08:30 ET Macro Catalyst Releases (CPI, NFP, PPI impulses)
- Regular Trading Hours (RTH): 09:30 ET cash open through 16:00 ET close
- Initial Balance (IB 09:30-10:30), Midday Equilibrium (11:45-13:45), LETF Rebalance (15:25), MOC (15:50)
- 17:00 ET CME maintenance cutoff
"""
from pathlib import Path
from datetime import datetime, timedelta, time
import numpy as np
import pandas as pd
import zoneinfo

from src.data.cme_session_clock import (
    NY_TZ,
    get_cme_trade_date,
    get_cme_trade_date_str,
    is_rth,
    is_eth
)
from src.data.resampler import resample_bars


def generate_cme_intraday_data(
    symbol: str = "MNQ",
    start_date: str = "2025-07-01",
    days: int = 75,
    base_price: float = 20250.0,
    output_raw: Path = Path("data/raw/mnq_1m.csv"),
    output_processed: Path = Path("data/processed/mnq_5m.csv")
) -> pd.DataFrame:
    """
    Generates continuous CME Globex 5-minute bars spanning ETH + RTH over 75 trading sessions.
    Simulates real market microstructure across the 10 strategy blueprint windows.
    """
    rng = np.random.default_rng(seed=42)
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=NY_TZ)

    records = []
    current_price = base_price
    dt_5m = timedelta(minutes=5)

    # Economic catalyst calendar dates (approx every 8 sessions)
    macro_days = set(range(3, days, 7))

    for day_idx in range(days):
        cal_date = start_dt + timedelta(days=day_idx)
        if cal_date.weekday() >= 5:  # Skip Saturday & Sunday
            continue

        is_macro_day = day_idx in macro_days
        # Day trend regime: 0 = Bull Trend, 1 = Bear Trend, 2 = Chop / Range
        day_regime = rng.choice([0, 1, 2], p=[0.40, 0.35, 0.25])
        day_drift = 1.5 if day_regime == 0 else (-1.5 if day_regime == 1 else 0.0)

        # Session begins at 18:00 ET on previous calendar date (or Sunday if Monday)
        prev_cal = cal_date - timedelta(days=3 if cal_date.weekday() == 0 else 1)
        session_start = datetime.combine(prev_cal.date(), time(18, 0)).replace(tzinfo=NY_TZ)

        # 23 hours in CME Globex session: 18:00 to 17:00 next day = 276 5-minute bars
        t = session_start
        for bar_idx in range(276):
            et_time = t.time()

            # Skip maintenance window: 17:00 to 18:00 ET
            if time(17, 0) <= et_time < time(18, 0):
                t += dt_5m
                continue

            open_p = current_price

            # Volatility & Volume by session phase
            if time(18, 0) <= et_time or et_time < time(8, 30):
                # Thin ETH Overnight
                vol_sigma = 2.5
                base_vol = rng.integers(300, 1500)
                bar_drift = rng.normal(0.0, 1.0)
            elif time(8, 30) <= et_time < time(8, 35):
                # 08:30 Macro Release Window
                if is_macro_day:
                    vol_sigma = 18.0  # Massive spike
                    base_vol = rng.integers(15000, 35000)
                    bar_drift = rng.choice([25.0, -25.0])  # Macro impulse
                else:
                    vol_sigma = 4.0
                    base_vol = rng.integers(1000, 3000)
                    bar_drift = 0.0
            elif time(8, 35) <= et_time < time(9, 30):
                # Pre-market digestion
                vol_sigma = 4.0
                base_vol = rng.integers(1500, 4500)
                bar_drift = -0.3 * (bar_drift if is_macro_day else 0.0)  # Mean retrace
            elif time(9, 30) <= et_time < time(10, 30):
                # RTH Initial Balance (09:30 - 10:30)
                vol_sigma = 7.5
                base_vol = rng.integers(12000, 32000)
                bar_drift = day_drift * 1.5 + rng.normal(0.0, 3.5)
            elif time(10, 30) <= et_time < time(11, 45):
                # Morning Institutional Discovery
                vol_sigma = 5.0
                base_vol = rng.integers(6000, 18000)
                bar_drift = day_drift * 1.2 + rng.normal(0.0, 2.5)
            elif time(11, 45) <= et_time < time(13, 45):
                # Midday Equilibrium Chop
                vol_sigma = 2.8
                base_vol = rng.integers(2000, 7000)
                bar_drift = rng.normal(0.0, 1.2)  # Low momentum mean-reverting
            elif time(13, 45) <= et_time < time(15, 25):
                # Afternoon Expansion
                vol_sigma = 6.0
                base_vol = rng.integers(7000, 20000)
                bar_drift = day_drift * 2.0 + rng.normal(0.0, 3.0)
            elif time(15, 25) <= et_time < time(15, 45):
                # LETF Rebalancing Window
                vol_sigma = 8.0
                base_vol = rng.integers(15000, 30000)
                bar_drift = (day_drift * 3.5) + rng.normal(0.0, 2.0)
            elif time(15, 50) <= et_time < time(15, 58):
                # MOC Imbalance Burst
                vol_sigma = 7.0
                base_vol = rng.integers(18000, 38000)
                bar_drift = (day_drift * 2.5) + rng.normal(0.0, 2.0)
            else:
                vol_sigma = 3.5
                base_vol = rng.integers(2000, 6000)
                bar_drift = rng.normal(0.0, 1.5)

            # Price action
            price_change = bar_drift + rng.normal(0.0, vol_sigma)
            close_p = round((open_p + price_change) * 4.0) / 4.0
            if close_p <= 0:
                close_p = 0.25

            wick_high = abs(rng.exponential(scale=max(1.0, vol_sigma * 0.4)))
            wick_low = abs(rng.exponential(scale=max(1.0, vol_sigma * 0.4)))

            high_p = max(open_p, close_p) + round(wick_high * 4.0) / 4.0
            low_p = min(open_p, close_p) - round(wick_low * 4.0) / 4.0
            if low_p <= 0:
                low_p = 0.25
            high_p = max(high_p, open_p, close_p)
            low_p = min(low_p, open_p, close_p)

            is_rth_flag = (t.weekday() < 5) and (time(9, 30) <= et_time < time(16, 0))

            records.append({
                "timestamp": t.strftime("%Y-%m-%d %H:%M:%S"),
                "open": float(open_p),
                "high": float(high_p),
                "low": float(low_p),
                "close": float(close_p),
                "volume": int(base_vol)
            })

            current_price = close_p
            t += dt_5m

    df = pd.DataFrame(records)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

    # Compute ATR_14
    df["tr"] = np.maximum(
        df["high"] - df["low"],
        np.maximum(
            (df["high"] - df["close"].shift(1)).abs(),
            (df["low"] - df["close"].shift(1)).abs()
        )
    )
    df["atr_14"] = df["tr"].rolling(14, min_periods=1).mean()
    df = df.drop(columns=["tr"])

    output_processed.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_processed, index=False)
    print(f"Generated {len(df):,} continuous CME Globex 5m bars saved to {output_processed}")
    return df


if __name__ == "__main__":
    generate_cme_intraday_data()
