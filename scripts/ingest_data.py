"""
Data Ingestion & Multi-Year / Multi-Month CME Futures Market Regime Generator.
Synthesizes realistic intraday MNQ continuous price action reflecting institutional auction regimes.
Enforces validation spanning >= 60 trading days (1,000+ hours) and zero lookahead bias.
"""
from pathlib import Path
from datetime import datetime, timedelta, time
import numpy as np
import pandas as pd

from src.data.validator import BarDataValidator
from src.data.resampler import resample_bars


def generate_cme_intraday_data(
    symbol: str = "MNQ",
    start_date: str = "2025-10-01",
    days: int = 105,  # ~75 trading days (exceeds 60 trading days requirement)
    base_price: float = 20250.0,
    output_raw: Path = Path("data/raw/mnq_1m.csv"),
    output_processed: Path = Path("data/processed/mnq_5m.csv")
) -> pd.DataFrame:
    """
    Generates realistic 1-minute CME equity index futures data across 70+ sessions.
    Simulates:
    - 09:30 open volume & volatility burst
    - Institutional morning trend discovery (10:00 - 11:30)
    - Midday lunch compression & chop (11:30 - 13:30)
    - Afternoon momentum & cash close imbalances (13:30 - 16:00)
    """
    rng = np.random.default_rng(seed=42)
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")

    records = []
    current_price = base_price
    trading_day_count = 0

    for day_idx in range(days):
        session_dt = start_dt + timedelta(days=day_idx)
        if session_dt.weekday() >= 5:  # Skip weekends
            continue

        trading_day_count += 1

        # Daily bias / regime: 0 = Bull Trend, 1 = Bear Trend, 2 = Rotational / Chop
        day_regime = rng.choice([0, 1, 2], p=[0.40, 0.35, 0.25])
        drift = 0.09 if day_regime == 0 else (-0.08 if day_regime == 1 else 0.0)

        # Generate 1m bars from 09:30 to 16:00 (390 bars per day)
        session_time = datetime.combine(session_dt.date(), time(9, 30))

        for minute_idx in range(390):
            bar_ts = session_time + timedelta(minutes=minute_idx)
            t = bar_ts.time()

            # Volatility regime depending on time of day
            if t < time(10, 0):
                vol_mult = 2.4
                base_vol = rng.integers(3000, 9000)
            elif t < time(11, 30):
                vol_mult = 1.4
                base_vol = rng.integers(1500, 4500)
            elif t < time(13, 30):
                vol_mult = 0.7  # lunch chop
                base_vol = rng.integers(600, 1800)
            elif t < time(15, 30):
                vol_mult = 1.3
                base_vol = rng.integers(1400, 4000)
            else:
                vol_mult = 2.0  # market close
                base_vol = rng.integers(3500, 8500)

            # Price delta
            ret = rng.normal(drift, 0.88 * vol_mult)
            bar_open = current_price
            bar_close = bar_open + ret

            high_wick = abs(rng.exponential(0.6 * vol_mult))
            low_wick = abs(rng.exponential(0.6 * vol_mult))

            bar_high = max(bar_open, bar_close) + high_wick
            bar_low = min(bar_open, bar_close) - low_wick

            # Snap to tick size (0.25)
            bar_open = round(round(bar_open / 0.25) * 0.25, 2)
            bar_high = round(round(bar_high / 0.25) * 0.25, 2)
            bar_low = round(round(bar_low / 0.25) * 0.25, 2)
            bar_close = round(round(bar_close / 0.25) * 0.25, 2)

            bar_high = max(bar_high, bar_open, bar_close)
            bar_low = min(bar_low, bar_open, bar_close)

            current_price = bar_close

            records.append({
                "timestamp": bar_ts.strftime("%Y-%m-%d %H:%M:%S"),
                "open": bar_open,
                "high": bar_high,
                "low": bar_low,
                "close": bar_close,
                "volume": int(base_vol)
            })

    df_1m = pd.DataFrame(records)

    # Basic schema enforcement
    BarDataValidator.enforce(df_1m)

    output_raw.parent.mkdir(parents=True, exist_ok=True)
    df_1m.to_csv(output_raw, index=False)
    print(f"Generated {len(df_1m)} 1-minute bars across {trading_day_count} trading days -> saved to {output_raw}")

    # Resample to 5m with right-closed, right-labeled intervals (zero lookahead bias)
    df_5m = resample_bars(df_1m, timeframe="5m")
    
    # Run institutional deep dataset validation
    is_valid, errors, stats = BarDataValidator.validate_dataset(df_5m)
    print(f"\nDataset Validation Stats:")
    for k, v in stats.items():
        print(f"  - {k}: {v}")
    if not is_valid:
        print(f"Validation warnings: {errors}")
    else:
        print("  - Status: PASSED (Institutional compliance >= 60 trading days & zero lookahead)")

    output_processed.parent.mkdir(parents=True, exist_ok=True)
    df_5m.to_csv(output_processed, index=False)
    print(f"\nResampled to {len(df_5m)} 5-minute bars -> saved to {output_processed}")

    return df_5m


if __name__ == "__main__":
    generate_cme_intraday_data()
