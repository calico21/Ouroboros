"""
Unit tests for AlphaForge AlphaDriftSentinel.
Validates CUSUM change-point detection, Wilson score interval surveillance,
cumulative drawdown circuit breakers, and operator quarantine overrides.
"""
import pytest
from src.execution.drift_sentinel import AlphaDriftSentinel


def test_drift_sentinel_healthy_regime():
    sentinel = AlphaDriftSentinel(
        strategy_name="afternoon_trend_continuation",
        expected_r_mean=0.569,
        wilson_lower_bound=0.581,
        expectancy_hurdle=0.150,
        drawdown_quarantine_dollars=800.0,
        cusum_threshold_h=4.0
    )
    # Simulate a stream of 15 trades consistent with 70% win rate
    # Wins: +1.2R (+$120), Losses: -1.0R (-$100)
    for i in range(15):
        is_win = (i % 3 != 0)  # 10 wins, 5 losses -> ~66.7% win rate
        r_val = 1.2 if is_win else -1.0
        pnl_val = 120.0 if is_win else -100.0
        status = sentinel.record_trade(
            trade_id=f"T-{i}",
            realized_r=r_val,
            realized_pnl=pnl_val
        )

    assert not sentinel.is_quarantined
    assert status.status == "HEALTHY"
    assert status.rolling_win_rate_15 >= 0.581
    assert status.rolling_expectancy_15 >= 0.150
    assert status.cusum_statistic < 4.0


def test_drift_sentinel_cusum_change_point_quarantine():
    sentinel = AlphaDriftSentinel(
        strategy_name="afternoon_trend_continuation",
        expected_r_mean=0.569,
        cusum_allowance_k=0.250,
        cusum_threshold_h=3.0,
        drawdown_quarantine_dollars=2000.0  # Large enough so drawdown doesn't trigger first
    )
    # Simulate severe alpha decay: sequence of negative returns
    # drift_delta = (0.569 - (-1.0)) - 0.25 = 1.319 per trade
    # In 3 trades: 3 * 1.319 = 3.957 >= 3.0 -> triggers quarantine
    for i in range(3):
        status = sentinel.record_trade(
            trade_id=f"BAD-{i}",
            realized_r=-1.0,
            realized_pnl=-50.0  # small dollar loss so DD doesn't trigger first
        )

    assert sentinel.is_quarantined
    assert status.status == "QUARANTINED"
    assert "CUSUM CHANGE-POINT TRIGGERED" in status.reason
    assert status.cusum_statistic >= 3.0


def test_drift_sentinel_drawdown_limit_breaker():
    sentinel = AlphaDriftSentinel(
        strategy_name="afternoon_trend_continuation",
        drawdown_quarantine_dollars=800.0,
        cusum_threshold_h=100.0  # High so CUSUM doesn't trigger first
    )
    # 5 trades of -$170 each = -$850 drawdown
    for i in range(5):
        status = sentinel.record_trade(
            trade_id=f"DD-{i}",
            realized_r=-0.85,
            realized_pnl=-170.0
        )

    assert sentinel.is_quarantined
    assert status.status == "QUARANTINED"
    assert "CUMULATIVE DRAWDOWN EXCEEDED" in status.reason
    assert status.current_drawdown_dollars >= 800.0


def test_drift_sentinel_rolling_warning_and_override():
    sentinel = AlphaDriftSentinel(
        strategy_name="afternoon_trend_continuation",
        wilson_lower_bound=0.581,
        expectancy_hurdle=0.150,
        drawdown_quarantine_dollars=5000.0,
        cusum_threshold_h=50.0
    )
    # 15 trades with 50% win rate (< 58.1% Wilson hurdle)
    for i in range(15):
        is_win = (i % 2 == 0)
        sentinel.record_trade(
            trade_id=f"W-{i}",
            realized_r=0.2 if is_win else -0.1,
            realized_pnl=20.0 if is_win else -10.0
        )

    status = sentinel.get_status()
    assert status.status == "WARNING"
    assert "STATISTICAL ROLLING WARNING" in status.reason

    # Test quarantine trigger and manual operator reset
    sentinel.is_quarantined = True
    sentinel.quarantine_reason = "Manual test quarantine"
    assert sentinel.get_status().status == "QUARANTINED"

    sentinel.reset_quarantine()
    assert not sentinel.is_quarantined
    assert sentinel.cusum_s == 0.0
