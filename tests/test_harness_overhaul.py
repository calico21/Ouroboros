"""
Unit Tests for AlphaForge Architectural Overhaul:
1. ExecutionSimulator._liquidate_active_trade immediate market liquidation & adverse slippage
2. PortfolioRunner strictly single-ratchet intra-bar MTM accounting
3. CME Session Clock & 18:00 ET Trade Date rollover
4. Negative Control Falsification on Synthetic GBM noise
"""
from datetime import datetime, date, time
import pytest
import zoneinfo

from src.core.events import BarEvent, TradeSetup
from src.core.enums import OrderSide, OrderType, AccountStatus
from src.data.cme_session_clock import (
    get_cme_trade_date,
    get_cme_trade_date_str,
    is_cme_session_boundary,
    NY_TZ
)
from src.execution.simulator import ExecutionSimulator
from src.engine.fee_models import FeeModel
from src.engine.account_tracker import PropFirmAccountTracker
from src.execution.portfolio_runner import PortfolioRunner
from src.strategies.sleeve_e_bounded_mr.midday_equilibrium_fade import MiddayEquilibriumFadeStrategy


def test_cme_session_clock_rollover():
    """Verify CME Trade Date rolls at 18:00 ET, not midnight."""
    # Sunday 18:05 ET belongs to Monday trade date
    sun_1805 = datetime(2025, 10, 5, 18, 5, 0, tzinfo=NY_TZ)
    assert get_cme_trade_date(sun_1805) == date(2025, 10, 6)
    assert get_cme_trade_date_str(sun_1805) == "2025-10-06"

    # Monday 02:00 ET belongs to Monday trade date
    mon_0200 = datetime(2025, 10, 6, 2, 0, 0, tzinfo=NY_TZ)
    assert get_cme_trade_date(mon_0200) == date(2025, 10, 6)

    # Monday 15:30 ET belongs to Monday trade date
    mon_1530 = datetime(2025, 10, 6, 15, 30, 0, tzinfo=NY_TZ)
    assert get_cme_trade_date(mon_1530) == date(2025, 10, 6)

    # Monday 18:01 ET rolls to Tuesday trade date
    mon_1801 = datetime(2025, 10, 6, 18, 1, 0, tzinfo=NY_TZ)
    assert get_cme_trade_date(mon_1801) == date(2025, 10, 7)

    # Rollover check
    assert is_cme_session_boundary(mon_1530, mon_1801) is True
    assert is_cme_session_boundary(sun_1805, mon_0200) is False


def test_liquidate_active_trade_enforcement():
    """Verify ExecutionSimulator._liquidate_active_trade closes position with adverse slippage."""
    fee_model = FeeModel(commission_per_side=0.62, tick_value=0.50, tick_size=0.25)
    sim = ExecutionSimulator(fee_model=fee_model, slippage_ticks=1.0, tick_size=0.25)
    account = PropFirmAccountTracker(initial_balance=50000.0, trailing_max_dd=2500.0)

    entry_bar = BarEvent(
        timestamp=datetime(2025, 10, 6, 10, 0, 0, tzinfo=NY_TZ),
        symbol="MNQ",
        open=20000.0,
        high=20010.0,
        low=19995.0,
        close=20000.0,
        volume=1000,
        timeframe="5m"
    )

    setup = TradeSetup(
        direction=OrderSide.LONG,
        order_type=OrderType.MARKET,
        stop_loss=19980.0,
        take_profit=20050.0,
        tag="test_strat"
    )

    # Submit market entry
    sim.submit_setup(setup, entry_bar, contracts=2)
    assert sim.active_trade is not None
    assert sim.active_trade["contracts"] == 2

    # Liquidation trigger bar (breach event)
    breach_bar = BarEvent(
        timestamp=datetime(2025, 10, 6, 10, 5, 0, tzinfo=NY_TZ),
        symbol="MNQ",
        open=19990.0,
        high=19992.0,
        low=19950.0,
        close=19955.0,
        volume=1200,
        timeframe="5m"
    )

    # Call _liquidate_active_trade
    rec = sim._liquidate_active_trade(breach_bar, "BREACH_LIQUIDATION", account=account, adverse_slippage_ticks=2.0)
    assert rec is not None
    assert sim.active_trade is None
    assert rec.exit_reason == "BREACH_LIQUIDATION"
    assert len(sim.closed_trades) == 1
    # Adverse slippage penalty: exit price is breach_bar.low - (2 * 0.25) = 19949.50
    assert rec.exit_price == 19949.50


def test_single_ratchet_intra_bar_accounting():
    """Verify PortfolioRunner does not double-ratchet trailing floor."""
    strat = MiddayEquilibriumFadeStrategy()
    prop_cfg = {
        "initial_balance": 50000.0,
        "trailing_max_drawdown": 2500.0,
        "profit_target": 3000.0,
        "floor_lock_threshold": 2600.0,
        "lock_floor_offset": 100.0,
        "drawdown_type": "intra_trade_peak_mtm",
        "max_contracts": 3
    }
    exec_cfg = {"slippage_ticks": 1.0, "limit_trade_through_ticks": 1.0}
    inst_cfg = {"point_value": 2.00, "tick_size": 0.25, "commission_per_contract_rt": 1.24}

    runner = PortfolioRunner(
        strategies=[strat],
        prop_firm_config=prop_cfg,
        execution_config=exec_cfg,
        instrument_config=inst_cfg,
        max_portfolio_contracts=3
    )

    # Initial floor is 47,500
    assert runner.account.floor == 47500.0
    assert runner.account.high_water_mark == 50000.0
