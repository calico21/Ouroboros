"""
Integration and unit tests for AlphaForge Live/Paper Execution Engine.
Validates RiskSentinel Apex rules, OrderManager OCO brackets,
PaperBroker simulation, and Trapped Liquidity Sweep execution.
"""
from datetime import datetime, time
import pytz
import pytest

from src.execution.risk_sentinel import RiskSentinel
from src.execution.order_manager import OrderManager
from src.execution.paper_broker import PaperBroker
from src.execution.models import OrderState, BracketRole
from src.core.events import BarEvent, TradeSetup
from src.core.enums import OrderSide, OrderType
from src.strategies.trapped_liquidity_sweep.strategy import TrappedLiquiditySweepStrategy


def test_risk_sentinel_peak_mtm_ratchet_and_permanent_lock():
    sentinel = RiskSentinel(starting_balance=50000.0, trailing_drawdown_limit=2500.0, target_profit=3000.0)
    est = pytz.timezone("US/Eastern")
    dt = est.localize(datetime(2025, 10, 15, 10, 0, 0))

    # Initial floor is 50,000 - 2,500 = 47,500
    assert sentinel.trailing_floor == 47500.0

    # Unrealized profit expands equity to 51,500 -> floor ratchets to 49,000
    compliant, reason = sentinel.update_equity(50000.0, 1500.0, dt)
    assert compliant is True
    assert sentinel.peak_hwm == 51500.0
    assert sentinel.trailing_floor == 49000.0
    assert sentinel.floor_locked is False

    # Equity reaches 52,700 (Passes 50k + 2600 threshold) -> Floor locks permanently at 50,100!
    compliant, reason = sentinel.update_equity(52700.0, 0.0, dt)
    assert compliant is True
    assert sentinel.peak_hwm == 52700.0
    assert sentinel.floor_locked is True
    assert sentinel.trailing_floor == 50100.0

    # Equity climbs further to 53,200 -> Floor stays locked at 50,100 (never climbs into profit target)
    compliant, reason = sentinel.update_equity(53200.0, 0.0, dt)
    assert sentinel.trailing_floor == 50100.0
    assert sentinel.is_target_reached is True


def test_risk_sentinel_dll_trigger():
    sentinel = RiskSentinel(starting_balance=50000.0, daily_loss_limit=1000.0)
    est = pytz.timezone("US/Eastern")
    dt = est.localize(datetime(2025, 10, 15, 10, 30, 0))

    # Realized loss -400, open loss -700 -> total daily loss -1100 > 1000 limit!
    compliant, reason = sentinel.update_equity(49600.0, -700.0, dt)
    assert compliant is False
    assert "DAILY_LOSS_LIMIT_TRIGGER" in reason
    assert sentinel.is_dll_halted is True


def test_risk_sentinel_1555_est_hard_close():
    sentinel = RiskSentinel(starting_balance=50000.0, auto_flatten_time=time(15, 55))
    est = pytz.timezone("US/Eastern")

    # 15:54 EST: Allowed
    dt_ok = est.localize(datetime(2025, 10, 15, 15, 54, 0))
    compliant, reason = sentinel.update_equity(50000.0, 100.0, dt_ok)
    assert compliant is True

    # 15:55 EST: Auto flatten triggered
    dt_eod = est.localize(datetime(2025, 10, 15, 15, 55, 0))
    compliant, reason = sentinel.update_equity(50000.0, 100.0, dt_eod)
    assert compliant is False
    assert "END_OF_DAY_HARD_FLATTEN" in reason


def test_order_manager_bracket_and_oco():
    om = OrderManager("MNQ", point_value=2.0, tick_size=0.25)
    bracket = om.create_bracket(
        direction="LONG",
        entry_type="MARKET",
        stop_loss_price=20000.0,
        take_profit_price=20100.0,
        entry_price=20050.0,
        quantity=1,
        buffer_equity=2000.0
    )

    assert bracket.parent_order.quantity == 1
    assert bracket.take_profit_order.limit_price == 20100.0
    assert bracket.stop_loss_order.stop_price == 20000.0

    # Simulate parent fill
    from src.execution.models import ExecutionReport
    parent_fill = ExecutionReport(
        exec_id="E1",
        client_order_id=bracket.parent_order.client_order_id,
        broker_order_id="B1",
        symbol="MNQ",
        direction="LONG",
        order_type="MARKET",
        status=OrderState.FILLED,
        last_qty=1,
        cum_qty=1,
        avg_price=20050.0
    )
    om.process_execution_report(parent_fill)

    assert om.position.side == "LONG"
    assert om.position.contracts == 1
    assert om.order_states[bracket.take_profit_order.client_order_id] == OrderState.NEW
    assert om.order_states[bracket.stop_loss_order.client_order_id] == OrderState.NEW

    # Simulate Take Profit fill -> OCO must cancel Stop Loss
    tp_fill = ExecutionReport(
        exec_id="E2",
        client_order_id=bracket.take_profit_order.client_order_id,
        broker_order_id="B2",
        symbol="MNQ",
        direction="SHORT",
        order_type="LIMIT",
        status=OrderState.FILLED,
        last_qty=1,
        cum_qty=1,
        avg_price=20100.0
    )
    cancel_actions = om.process_execution_report(tp_fill)
    assert len(cancel_actions) == 1
    assert cancel_actions[0].client_order_id == bracket.stop_loss_order.client_order_id
    assert om.position.side == "FLAT"
    assert om.position.realized_pnl == 100.0  # (20100 - 20050) * $2.0 = $100


def test_paper_broker_full_lifecycle():
    telemetry_packets = []
    broker = PaperBroker(
        starting_balance=50000.0,
        on_telemetry=lambda p: telemetry_packets.append(p)
    )
    est = pytz.timezone("US/Eastern")
    broker.current_timestamp = est.localize(datetime(2025, 10, 15, 10, 0, 0))
    broker.start("trapped_liquidity_sweep")

    # Send long signal
    setup = TradeSetup(
        direction=OrderSide.LONG,
        order_type=OrderType.MARKET,
        stop_loss=20010.0,
        take_profit=20060.0
    )
    broker.current_price = 20030.0
    bracket = broker.submit_signal(setup)
    assert bracket is not None
    assert broker.order_manager.position.side == "LONG"

    # Emergency flatten
    broker.flatten_all_positions("TEST_EMERGENCY")
    assert broker.order_manager.position.side == "FLAT"
    assert len(telemetry_packets) > 0
