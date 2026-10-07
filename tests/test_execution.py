"""
Unit tests for Execution Simulator and Strict Limit Order Trade-Through.
"""
from datetime import datetime, timezone
from src.core.events import BarEvent, TradeSetup
from src.core.enums import OrderSide, OrderType, OrderStatus
from src.engine.fee_models import FeeModel
from src.engine.account_tracker import PropFirmAccountTracker
from src.engine.execution_simulator import ExecutionSimulator
from src.engine.position_sizer import PropFirmPositionSizer


def test_strict_limit_trade_through_validation():
    """
    CME Globex FIFO queue rule:
    Limit Buy at 20000.0 must NOT fill on touch (Low == 20000.0).
    It MUST trade through by >= 1 tick (Low <= 19999.75).
    """
    fee_model = FeeModel(commission_per_side=0.62, tick_value=0.50, tick_size=0.25)
    simulator = ExecutionSimulator(
        fee_model=fee_model,
        slippage_ticks=1.0,
        limit_trade_through_ticks=1.0,
        fill_on_touch=False,
        tick_size=0.25
    )
    account = PropFirmAccountTracker()

    setup = TradeSetup(
        direction=OrderSide.LONG,
        order_type=OrderType.LIMIT,
        limit_price=20000.0,
        stop_loss=19950.0,
        take_profit=20100.0,
        ttl_bars=5
    )

    bar0 = BarEvent(
        timestamp=datetime(2026, 3, 10, 9, 30, tzinfo=timezone.utc),
        open=20010.0, high=20015.0, low=20005.0, close=20008.0, volume=1000, symbol="MNQ"
    )
    simulator.submit_setup(setup, bar0, contracts=1)
    assert len(simulator.pending_orders) == 1

    # Bar 1: Mere touch! Low == 20000.00
    bar_touch = BarEvent(
        timestamp=datetime(2026, 3, 10, 9, 35, tzinfo=timezone.utc),
        open=20008.0, high=20012.0, low=20000.0, close=20005.0, volume=1500, symbol="MNQ"
    )
    simulator.process_bar(bar_touch, account)
    assert simulator.active_trade is None
    assert len(simulator.pending_orders) == 1
    assert simulator.pending_orders[0].status == OrderStatus.PENDING

    # Bar 2: Trade-through by 1 tick! Low == 19999.75
    bar_trade_through = BarEvent(
        timestamp=datetime(2026, 3, 10, 9, 40, tzinfo=timezone.utc),
        open=20005.0, high=20008.0, low=19999.75, close=20002.0, volume=2000, symbol="MNQ"
    )
    simulator.process_bar(bar_trade_through, account)
    assert simulator.active_trade is not None
    assert simulator.active_trade["entry_price"] == 20000.0
    assert len(simulator.pending_orders) == 0


def test_position_sizer_rounding_clamp():
    """Verify single-contract quantization and rounding tolerance threshold."""
    sizer = PropFirmPositionSizer(
        risk_per_trade_pct=0.05,
        rounding_tolerance_threshold=0.75,
        buffer_risk_limit=0.10,
        point_value=2.00,
        commission_rt=1.24
    )

    # Cushion $1,000. Stop distance 15 points.
    # 1-lot risk = 15 * 2 + 1.24 = $31.24.
    # Risk budget (5% of 1,000) = $50.
    # Lots = 50 / 31.24 = 1.6 -> int(1) = 1 lot.
    assert sizer.calculate_lots(cushion=1000.0, stop_distance_points=15.0) == 1

    # Small cushion: $500. Stop distance 15 points ($31.24 risk).
    # Risk budget = 5% of 500 = $25.
    # raw_lots = 25 / 31.24 = 0.80.
    # int(raw_lots) = 0.
    # But budget covers 80% (>= 75% threshold), and 1-lot risk ($31.24 / 500 = 6.2% <= 10% limit).
    # Rounding clamp triggers -> allocates 1 contract!
    assert sizer.calculate_lots(cushion=500.0, stop_distance_points=15.0) == 1

    # Buffer depleted: Cushion $150. Stop distance 15 points.
    # 1-lot risk is 31.24 / 150 = 20.8% of buffer (> 10% limit).
    # Safety lock refuses allocation -> 0 contracts.
    assert sizer.calculate_lots(cushion=150.0, stop_distance_points=15.0) == 0
