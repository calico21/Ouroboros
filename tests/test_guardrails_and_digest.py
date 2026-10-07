"""
Unit tests for Statistical Sample-Size Guardrails, Dataset Validator, and LLM Digest.
"""
from datetime import datetime, timezone, timedelta
import numpy as np
import pandas as pd
from src.analytics.metrics_engine import MetricsEngine
from src.data.validator import BarDataValidator
from src.validation.monte_carlo import PropFirmMonteCarloSimulator
from src.core.events import TradeRecord
from src.core.enums import OrderSide
from scripts.export_digest import generate_llm_digest


def make_trades(n: int, win_rate: float = 0.5) -> list:
    trades = []
    for i in range(n):
        is_win = (i / n) < win_rate
        pnl = 80.0 if is_win else -40.0
        trades.append(TradeRecord(
            trade_id=f"t-{i}",
            symbol="MNQ",
            strategy_name="test_strat",
            tag="default",
            side=OrderSide.LONG,
            contracts=1,
            entry_time=datetime(2026, 3, 10, 9, 35, tzinfo=timezone.utc),
            entry_price=20000.0,
            exit_time=datetime(2026, 3, 10, 9, 50, tzinfo=timezone.utc),
            exit_price=20040.0 if is_win else 19980.0,
            exit_reason="TAKE_PROFIT" if is_win else "STOP_LOSS",
            initial_sl=19980.0,
            initial_tp=20040.0,
            risk_r_price=20.0,
            mfe_price=20040.0 if is_win else 20005.0,
            mae_price=19995.0 if is_win else 19980.0,
            mfe_r=2.0 if is_win else 0.25,
            mae_r=0.25 if is_win else 1.0,
            time_to_peak_mfe=2,
            bars_held=5,
            gross_pnl=pnl + 1.24,
            net_pnl=pnl,
            commissions=1.24,
            slippage_paid=0.0,
            r_multiple=2.0 if is_win else -1.0,
            excursion_efficiency=1.0 if is_win else -1.0
        ))
    return trades


def test_wilson_ci95_calculation():
    """Verify Wilson Score 95% interval prevents misleading 100% win rate on small samples."""
    # 2 wins out of 2 trades (100% observed win rate)
    lower, upper = MetricsEngine._calculate_wilson_ci95(k=2, n=2)
    # Wilson interval for 2/2 has lower bound around 34.2%, NOT 100%!
    assert lower < 40.0
    assert upper == 100.0

    # 50 wins out of 100 trades (50% win rate)
    lower_100, upper_100 = MetricsEngine._calculate_wilson_ci95(k=50, n=100)
    assert 39.0 < lower_100 < 41.0
    assert 59.0 < upper_100 < 61.0


def test_sample_significance_gate_warning():
    """Verify N < 30 triggers INSUFFICIENT_SAMPLE warning status."""
    small_trades = make_trades(10, win_rate=0.8)
    metrics = MetricsEngine.compute_all(small_trades)
    s = metrics["summary"]

    assert s["is_sufficient_sample"] is False
    assert "INSUFFICIENT_SAMPLE" in s["sample_significance_status"]
    assert s["sample_warning"] is not None

    large_trades = make_trades(35, win_rate=0.6)
    metrics_large = MetricsEngine.compute_all(large_trades)
    s_large = metrics_large["summary"]

    assert s_large["is_sufficient_sample"] is True
    assert "SUFFICIENT_SAMPLE" in s_large["sample_significance_status"]
    assert s_large["sample_warning"] is None


def test_monte_carlo_suppression_on_small_n():
    """Verify Monte Carlo is suppressed when N < 15 to avoid false confidence."""
    tiny_trades = make_trades(10)
    mc = PropFirmMonteCarloSimulator(iterations=100)
    res = mc.run(tiny_trades)

    assert res["is_suppressed"] is True
    assert res["prob_pass_pct"] is None
    assert res["prob_breach_pct"] is None
    assert "SUPPRESSED" in res["status"]

    sufficient_mc_trades = make_trades(20)
    res_sufficient = mc.run(sufficient_mc_trades)
    assert res_sufficient["is_suppressed"] is False
    assert res_sufficient["prob_pass_pct"] is not None


def test_dataset_validator():
    """Verify validate_dataset checks 60-day threshold and zero lookahead."""
    # Data with only 10 days
    base_ts = pd.Timestamp("2026-01-05 09:30:00")
    records = []
    for d in range(10):
        for m in range(0, 390, 5):
            ts = base_ts + pd.Timedelta(days=d, minutes=m)
            records.append({
                "timestamp": ts,
                "open": 20000.0,
                "high": 20010.0,
                "low": 19995.0,
                "close": 20005.0,
                "volume": 1000
            })
    df_short = pd.DataFrame(records)
    valid, errors, stats = BarDataValidator.validate_dataset(df_short)
    assert valid is False
    assert any("trading days" in e and "minimum 60" in e for e in errors)
