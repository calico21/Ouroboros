"""
Unit & Integration Tests for Phase 3 Deliverables:
- Portfolio Allocation Engine & Concurrency Locks (src/engine/portfolio.py, portfolio_tracker.py)
- Forward Incubation Replay & Apex DLL Circuit Breakers (scripts/run_incubation_paper.py)
- ORB Breakout Quality & RVOL Filtering Gates (src/strategies/orb_5m_binary/)
"""
from datetime import datetime, time
import zoneinfo
import pytest

from src.core.events import BarEvent, TradeRecord
from src.core.enums import OrderSide, AccountStatus, DrawdownType
from src.strategies.orb_5m_binary.strategy import Orb5mBinaryStrategy
from src.strategies.orb_5m_binary.indicators import TimeBucketVolumeTracker, check_breakout_candle_quality
from src.strategies.afternoon_trend_continuation.strategy import AfternoonTrendContinuationStrategy
from src.engine.portfolio_tracker import PortfolioAccountTracker, StrategySubAccount
from src.engine.portfolio import PortfolioRunner
from src.data.loader import DataLoader

NY_TZ = zoneinfo.ZoneInfo("America/New_York")


def test_orb_rvol_and_clutch_candle_quality():
    """Verify ORB structural quality (Clutch Factor) and RVOL filtering."""
    # 1. Wicky candle rejection (Body < 55%)
    passed_wick, body_pct, ext = check_breakout_candle_quality(
        open_price=20000.0, high_price=20060.0, low_price=19995.0, close_price=20025.0,
        is_long=True, min_bar_body_pct=0.55, min_close_extremity_pct=0.75
    )
    assert not passed_wick
    assert body_pct < 0.55

    # 2. Strong clutch bar pass (Body >= 55% and closes in top 25%)
    passed_clutch, body_pct2, ext2 = check_breakout_candle_quality(
        open_price=20010.0, high_price=20050.0, low_price=20008.0, close_price=20048.0,
        is_long=True, min_bar_body_pct=0.55, min_close_extremity_pct=0.75
    )
    assert passed_clutch
    assert body_pct2 >= 0.55
    assert ext2 >= 0.75

    # 3. Time bucket RVOL tracker
    tracker = TimeBucketVolumeTracker(lookback_days=15)
    t_bucket = time(9, 45)
    tracker.set_baseline(t_bucket, median_volume=20000.0)

    # Volume 22,000 -> RVOL = 1.10 (< 1.25 gate)
    assert tracker.get_rvol(t_bucket, 22000.0) == 1.10
    # Volume 28,000 -> RVOL = 1.40 (>= 1.25 gate)
    assert tracker.get_rvol(t_bucket, 28000.0) == 1.40


def test_portfolio_account_tracker_concurrency_and_locks():
    """Verify PortfolioAccountTracker enforces max contracts and opposing directional locks."""
    account = PortfolioAccountTracker(
        initial_balance=50000.0,
        trailing_max_dd=2500.0,
        max_portfolio_contracts=6
    )
    account.register_strategy("orb_5m_binary", weight=0.50)
    account.register_strategy("afternoon_trend_continuation", weight=0.50)

    # Strategy 1 opens 4 contracts LONG
    can_open, msg = account.can_open_position("orb_5m_binary", OrderSide.LONG, proposed_contracts=4)
    assert can_open
    account.active_positions["orb_5m_binary"] = {"direction": OrderSide.LONG, "contracts": 4}

    # Strategy 2 attempts to open 3 contracts LONG (4 + 3 = 7 > max 6 contracts)
    can_open_exceed, msg = account.can_open_position("afternoon_trend_continuation", OrderSide.LONG, proposed_contracts=3)
    assert not can_open_exceed
    assert "Exceeds max portfolio exposure" in msg

    # Strategy 2 attempts to open 2 contracts SHORT (opposing direction while ORB is LONG)
    can_open_opposing, msg = account.can_open_position("afternoon_trend_continuation", OrderSide.SHORT, proposed_contracts=2)
    assert not can_open_opposing
    assert "Directional conflict" in msg

    # Strategy 2 opens 2 contracts LONG (4 + 2 = 6 <= max 6 contracts)
    can_open_ok, _ = account.can_open_position("afternoon_trend_continuation", OrderSide.LONG, proposed_contracts=2)
    assert can_open_ok


def test_portfolio_runner_session_capital_and_analytics():
    """Verify PortfolioRunner updates consolidated cushion across intraday windows."""
    loader = DataLoader("data/processed/mnq_5m.csv", timeframe="5m")
    loader.load()

    prop_cfg = {
        "initial_balance": 50000.0,
        "trailing_max_drawdown": 2500.0,
        "profit_target": 3000.0,
        "drawdown_type": "intra_trade_peak_mtm",
        "floor_lock_threshold": 2600.0,
        "lock_floor_offset": 100.0
    }
    exec_cfg = {
        "slippage_ticks": 1.0,
        "limit_trade_through_ticks": 1.0,
        "fill_on_touch": False
    }
    inst_cfg = {
        "symbol": "MNQ",
        "tick_size": 0.25,
        "point_value": 2.00,
        "commission_per_side": 0.62
    }

    strategies = [
        Orb5mBinaryStrategy(),
        AfternoonTrendContinuationStrategy()
    ]
    runner = PortfolioRunner(strategies, prop_cfg, exec_cfg, inst_cfg, max_portfolio_contracts=6)
    metrics = runner.run(loader)

    summary = metrics["summary"]
    analytics = metrics["portfolio_analytics"]

    assert summary["total_trades"] >= 30, "Blended portfolio should satisfy N >= 30 sample size gate"
    assert summary["total_net_pnl"] > 0, "Blended portfolio should be profitable"
    assert "diversification_ratio" in analytics
    assert "correlation_matrix" in analytics
    assert metrics["monte_carlo"]["prob_pass_pct"] > 80.0
