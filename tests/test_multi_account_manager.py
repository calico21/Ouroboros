"""
Unit and integration tests for MultiAccountRouter and prop-firm fleet execution.
Validates concurrent async fan-out, independent RiskSentinel trailing floors,
sub-account DLL isolation, and cross-account dispersion metrics.
"""
import pytest
import asyncio
from datetime import datetime
import pytz

from src.core.events import TradeSetup
from src.core.enums import OrderSide, OrderType
from src.execution.multi_account_manager import (
    MultiAccountRouter,
    SubAccountConfig,
)


def test_multi_account_concurrent_fanout():
    async def _run():
        configs = [
            SubAccountConfig(account_id=f"APEX-TEST-{i:02d}", is_master=(i == 1))
            for i in range(1, 4)
        ]
        router = MultiAccountRouter(
            sub_accounts=configs,
            symbol="MNQ",
            point_value=2.0,
            tick_size=0.25,
            dispersion_threshold_ticks=2.0
        )

        setup = TradeSetup(
            direction=OrderSide.LONG,
            order_type=OrderType.MARKET,
            stop_loss=20180.0,
            take_profit=20240.0,
            limit_price=20200.0,
            tag="afternoon_trend_continuation"
        )

        dispersion = await router.broadcast_setup(setup)

        assert dispersion.successful_submissions == 3
        assert len(dispersion.latencies_ms) == 3
        assert len(dispersion.fill_prices) == 3
        assert dispersion.latency_dispersion_ms >= 0.0

        # Verify positions on each sub-account
        summary = router.get_fleet_summary()
        assert summary.total_accounts == 3
        for acct in summary.accounts:
            assert acct["position"]["side"] == "LONG"
            assert acct["position"]["contracts"] == 1
            assert acct["position"]["entry_price"] > 0

    asyncio.run(_run())


def test_multi_account_dll_isolation_and_bypass():
    async def _run():
        configs = [
            SubAccountConfig(account_id="APEX-HEALTHY-01", starting_balance=50000.0),
            SubAccountConfig(account_id="APEX-HALTED-02", starting_balance=50000.0),
        ]
        router = MultiAccountRouter(sub_accounts=configs)

        # Artificially trigger DLL on account 2
        node_halted = router.nodes["APEX-HALTED-02"]
        now = pytz.timezone("US/Eastern").localize(datetime(2026, 10, 7, 14, 0))
        # -$1050 loss exceeds -$1000 DLL
        node_halted.record_realized(-1050.0, now)

        assert node_halted.risk_sentinel.is_dll_halted

        # Broadcast new setup
        setup = TradeSetup(
            direction=OrderSide.SHORT,
            order_type=OrderType.MARKET,
            stop_loss=20170.0,
            take_profit=20110.0,
            limit_price=20150.0,
            tag="afternoon_trend_continuation"
        )

        dispersion = await router.broadcast_setup(setup)

        # Only the healthy account should have executed!
        assert dispersion.successful_submissions == 1
        assert "APEX-HEALTHY-01" in dispersion.fill_prices
        assert "APEX-HALTED-02" not in dispersion.fill_prices

        assert router.nodes["APEX-HEALTHY-01"].position.side == "SHORT"
        assert router.nodes["APEX-HALTED-02"].position.side == "FLAT"

    asyncio.run(_run())


def test_multi_account_mtm_ratchet_and_emergency_flatten():
    configs = [
        SubAccountConfig(account_id="APEX-M1", starting_balance=50000.0),
        SubAccountConfig(account_id="APEX-M2", starting_balance=50000.0),
    ]
    router = MultiAccountRouter(sub_accounts=configs)

    # Open positions directly
    for node in router.nodes.values():
        node.position.side = "LONG"
        node.position.contracts = 1
        node.position.entry_price = 20000.0

    now = pytz.timezone("US/Eastern").localize(datetime(2026, 10, 7, 14, 30))

    # Price moves +50 pts ($100 per MNQ contract)
    summary = router.update_mark_price(20050.0, now)
    assert summary.fleet_unrealized_pnl == 200.0  # $100 * 2 accounts

    for acct in summary.accounts:
        assert acct["unrealized_pnl"] == 100.0
        # Peak equity increases to 50,100 -> trailing floor ratchets up
        assert acct["peak_hwm"] == 50100.0
        assert acct["trailing_floor"] == 47600.0

    # Emergency flatten
    router.emergency_flatten_fleet()
    flat_summary = router.get_fleet_summary()
    for acct in flat_summary.accounts:
        assert acct["position"]["side"] == "FLAT"
        assert acct["position"]["contracts"] == 0
        assert acct["account_status"] == "SESSION_CLOSED"
