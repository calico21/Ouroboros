"""
Unit tests for RegimeBucketingHarness.
Verifies pre-registration of regime conditioning metrics:
- Initial Balance / ATR
- Opening gap / ATR
- NR7 session classification
- Forward MFE and MAE distribution bucketing in R
"""
import pytest
from datetime import datetime, date, timedelta, time
import numpy as np
import pandas as pd

from src.analytics.regime_bucketing_harness import RegimeBucketingHarness


def test_regime_bucketing_feature_extraction():
    harness = RegimeBucketingHarness(atr_period=5)
    
    # Generate 15 synthetic sessions of 5m bars
    bars = []
    base_date = date(2025, 1, 6) # Monday
    
    for day_i in range(15):
        d = base_date + timedelta(days=day_i)
        if d.weekday() >= 5:
            continue
            
        base_price = 20000.0 + day_i * 50.0
        # 09:30 to 16:00
        for m in range(0, 395, 5):
            t = (datetime.combine(d, time(9, 30)) + timedelta(minutes=m)).time()
            ts = datetime.combine(d, t)
            drift = np.sin(m / 20.0) * 15.0
            o = base_price + drift
            h = o + 4.0
            l = o - 4.0
            c = o + 1.0
            bars.append({
                "timestamp": ts,
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": 1000
            })
            
    df_bars = pd.DataFrame(bars)
    df_bars.set_index("timestamp", inplace=True)
    
    features = harness.compute_daily_regime_features(df_bars)
    assert not features.empty
    assert "ib_range" in features.columns
    assert "atr_14" in features.columns
    assert "ib_to_atr" in features.columns
    assert "gap_to_atr" in features.columns
    assert "is_nr7" in features.columns
    assert "has_ib_extension_1_5x_atr" in features.columns
    assert "ib_bucket" in features.columns


def test_forward_excursion_evaluation():
    harness = RegimeBucketingHarness(atr_period=3)
    
    # Minimal daily features
    dates = [date(2025, 1, 6) + timedelta(days=i) for i in range(10)]
    daily_features = pd.DataFrame({
        "ib_bucket": ["COMPRESSED (<0.35 ATR)", "NORMAL (0.35-0.65 ATR)"] * 5,
        "gap_bucket": ["SMALL (<0.20 ATR)"] * 10,
        "nr7_bucket": ["NON_NR7"] * 9 + ["NR7"],
        "has_ib_extension_1_5x_atr": [True, False] * 5,
    }, index=dates)
    daily_features.index.name = "date"
    
    # Minimal trades
    trades = pd.DataFrame([
        {
            "entry_time": datetime.combine(dates[i], time(13, 35)),
            "r_multiple": 1.2 if i % 2 == 0 else -1.0,
            "mfe_r": 1.5 if i % 2 == 0 else 0.4,
            "mae_r": 0.3 if i % 2 == 0 else 1.0,
            "risk_pts": 15.0
        }
        for i in range(10)
    ])
    
    result = harness.evaluate_forward_excursion_by_bucket(trades, daily_features)
    assert result["total_trades_analyzed"] == 10
    assert "pre_registered_buckets" in result
    assert "ib_bucket" in result["pre_registered_buckets"]
    assert "overall_trend_extension_sessions_fraction_pct" in result
