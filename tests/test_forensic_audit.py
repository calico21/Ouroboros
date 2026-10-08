"""
Unit and integration tests for AlphaForge Deep Forensic Audit Engine.
Validates:
1. MacroCalendar: CME globex holiday, half-day, and event-day lookups.
2. RegimeClassifier: Volatility quintiles Q1-Q5, trend regimes, liquidity tagging.
3. CalendarMetricsCalculator: Continuous 252-day calendar Sharpe, Sortino, and Calmar ratios.
4. DeflatedSharpeCalculator: PSR, DSR (Bailey & López de Prado), and expected maximum Sharpe.
5. MacroAttributionAnalyzer: Event-day vs non-event day slicing.
6. LiquidityExcursionAnalyzer: MFE/MAE drift ratio and capture efficiency.
7. CombinatorialPurgedCV: Purged & embargoed splits and PBO calculation.
8. WalkForwardMatrix: Walk-forward efficiency (WFE) and fold consistency.
9. SyntheticStressEngine: GARCH(1,1) shocks and stationary block-bootstrap.
10. PropFirmMonteCarloSimulator: 50,000-path Apex 50k MTM trailing ratchet and floor lock.
"""
from datetime import date
import pytest
import numpy as np
import pandas as pd

from src.data.macro_calendar import MacroCalendar, CatalystType, MarketSessionType
from src.data.regime_classifier import RegimeClassifier, VolatilityRegime, TrendRegime
from src.analytics.calendar_metrics import CalendarMetricsCalculator
from src.analytics.deflated_sharpe import DeflatedSharpeCalculator
from src.analytics.macro_attribution import MacroAttributionAnalyzer
from src.analytics.liquidity_excursion import LiquidityExcursionAnalyzer
from src.validation.cpcv import CombinatorialPurgedCV
from src.validation.walk_forward_matrix import WalkForwardMatrix
from src.validation.synthetic_stress import SyntheticStressEngine
from src.validation.prop_firm_monte_carlo import PropFirmMonteCarloSimulator


def create_sample_trades() -> pd.DataFrame:
    """Helper to create a realistic sample trade DataFrame."""
    np.random.seed(42)
    dates = pd.date_range("2024-01-08", periods=60, freq="B")
    trades = []
    for i, d in enumerate(dates):
        # 70% win rate
        is_win = np.random.rand() < 0.70
        pnl = float(np.random.uniform(70.0, 160.0) if is_win else np.random.uniform(-90.0, -40.0))
        trades.append({
            "trade_id": f"TRD_{i:03d}",
            "entry_time": f"{d.strftime('%Y-%m-%d')} 13:35:00",
            "exit_time": f"{d.strftime('%Y-%m-%d')} 14:45:00",
            "direction": "LONG",
            "net_pnl": pnl,
            "r_multiple": pnl / 80.0,
            "mfe_ticks": float(np.random.uniform(20.0, 48.0) if is_win else np.random.uniform(4.0, 16.0)),
            "mae_ticks": float(np.random.uniform(4.0, 12.0) if is_win else np.random.uniform(16.0, 24.0)),
            "duration_minutes": int(np.random.uniform(25, 65)),
            "catalyst": CatalystType.FOMC.value if i % 10 == 0 else CatalystType.NONE.value
        })
    return pd.DataFrame(trades)


def test_macro_calendar_schedules():
    cal = MacroCalendar()
    # MLK Day 2024 is holiday
    assert cal.get_session_type(date(2024, 1, 15)) == MarketSessionType.HOLIDAY
    assert not cal.is_trading_day(date(2024, 1, 15))

    # July 3, 2024 is half-day
    assert cal.get_session_type(date(2024, 7, 3)) == MarketSessionType.HALF_DAY
    assert cal.get_half_day_close(date(2024, 7, 3)) == "13:00"

    # Regular trading day
    assert cal.get_session_type(date(2024, 1, 10)) == MarketSessionType.REGULAR

    # FOMC Day check
    assert cal.is_fomc_day(date(2024, 1, 31))
    assert cal.get_primary_catalyst(date(2024, 1, 31)) == CatalystType.FOMC

    # Entry suppression
    suppress, msg = cal.should_suppress_strategy_entry(date(2024, 1, 31), "13:50", buffer_minutes_before=15)
    assert suppress
    assert "FOMC" in msg


def test_regime_classifier():
    classifier = RegimeClassifier()
    # Volatility classification
    assert classifier.classify_volatility(12.0) == VolatilityRegime.Q1_ULTRA_LOW
    assert classifier.classify_volatility(16.0) == VolatilityRegime.Q2_LOW
    assert classifier.classify_volatility(21.0) == VolatilityRegime.Q3_MODERATE
    assert classifier.classify_volatility(28.0) == VolatilityRegime.Q4_ELEVATED
    assert classifier.classify_volatility(35.0) == VolatilityRegime.Q5_CRISIS

    # Trend classification
    assert classifier.classify_trend(0.25, 45.0) == TrendRegime.STRONG_BULL
    assert classifier.classify_trend(-0.25, 45.0) == TrendRegime.STRONG_BEAR
    assert classifier.classify_trend(0.05, 15.0) == TrendRegime.CHOP_RANGE


def test_calendar_metrics_calculator():
    trades = create_sample_trades()
    calc = CalendarMetricsCalculator()
    res = calc.compute(trades, start_date="2024-01-01", end_date="2024-03-31")

    assert res.trading_days_active > 0
    assert res.total_net_pnl > 0
    assert res.calendar_sharpe > 0.0
    assert res.calendar_sortino > 0.0
    assert res.gain_to_pain_ratio > 1.0


def test_deflated_sharpe_calculator():
    calc = DeflatedSharpeCalculator()
    # Gaussian returns with positive mean
    np.random.seed(42)
    daily_returns = np.random.normal(0.001, 0.005, size=100)
    
    dsr_res = calc.compute_dsr(daily_returns, num_trials=25, var_trials=0.25)
    assert 0.0 <= dsr_res.probabilistic_sharpe_ratio <= 1.0
    assert 0.0 <= dsr_res.deflated_sharpe_ratio <= 1.0
    assert dsr_res.expected_max_null_sharpe > 0.0
    assert dsr_res.trials_tested == 25


def test_macro_attribution_analyzer():
    trades = create_sample_trades()
    analyzer = MacroAttributionAnalyzer()
    res = analyzer.analyze(trades)

    assert len(res.cohorts) >= 1
    assert res.event_day_trade_count >= 0
    assert res.recommendation is not None


def test_liquidity_excursion_analyzer():
    trades = create_sample_trades()
    analyzer = LiquidityExcursionAnalyzer()
    res = analyzer.analyze(trades)

    assert res.mean_mfe_ticks > res.mean_mae_ticks
    assert res.drift_ratio > 1.0
    assert res.mfe_capture_efficiency_pct > 0.0


def test_combinatorial_purged_cv():
    trades = create_sample_trades()
    cpcv = CombinatorialPurgedCV(num_groups=5, k_test_groups=2)
    res = cpcv.run_validation(trades)

    assert res.total_splits == 10  # C(5, 2) = 10
    assert 0.0 <= res.pbo_pct <= 100.0
    assert len(res.splits) == 10


def test_walk_forward_matrix():
    trades = create_sample_trades()
    wfo = WalkForwardMatrix(mode="ANCHORED")
    res = wfo.run_matrix(trades, strategy_name="afternoon_trend_continuation")

    assert res.total_folds > 0
    assert 0.0 <= res.consistency_pct <= 100.0


def test_synthetic_stress_engine():
    trades = create_sample_trades()
    engine = SyntheticStressEngine()
    res = engine.run_stress_suite(trades, n_simulations=100)

    assert len(res.scenarios) == 3
    assert 0.0 <= res.resilience_score <= 100.0


def test_prop_firm_monte_carlo():
    trades = create_sample_trades()
    sim = PropFirmMonteCarloSimulator()
    res = sim.simulate(trades, n_paths=200)

    assert res.num_paths == 200
    assert 0.0 <= res.p_pass_pct <= 100.0
    assert 0.0 <= res.p_breach_pct <= 100.0
    assert res.median_max_drawdown <= 2500.0
