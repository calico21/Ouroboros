"""
Unit tests for Unified Broker Gateway Interface and Live/Paper Adapters.
Validates PaperBrokerGateway and TradovateRESTSocketGateway lifecycle,
bracket submissions, and risk sentinel integration.
"""
from datetime import datetime
import pytz
import pytest

from src.execution.broker_gateway import (
    PaperBrokerGateway,
    TradovateRESTSocketGateway,
)
from src.core.events import TradeSetup
from src.core.enums import OrderSide, OrderType


@pytest.fixture
def base_config():
    return {
        "symbol": "MNQ",
        "point_value": 2.0,
        "tick_size": 0.25,
        "paper": {
            "starting_balance": 50000.0,
            "default_slippage_ticks": 1.0,
            "commission_per_contract": 0.62,
            "simulated_network_latency_ms": 10.0,
            "simulated_execution_latency_ms": 5.0
        },
        "tradovate": {
            "is_demo": True
        }
    }


def test_paper_broker_gateway_lifecycle(base_config):
    fills_recorded = []
    gateway = PaperBrokerGateway(base_config)
    gateway.on_fill(lambda f: fills_recorded.append(f))

    assert gateway.is_connected() is False
    assert gateway.connect() is True
    assert gateway.is_connected() is True

    # Pre-set mock time to 14:00 EST for afternoon trading
    est = pytz.timezone("US/Eastern")
    gateway.broker.current_timestamp = est.localize(datetime(2025, 10, 15, 14, 0, 0))
    gateway.broker.current_price = 20250.0

    # Submit Long Bracket Order
    setup = TradeSetup(
        direction=OrderSide.LONG,
        order_type=OrderType.MARKET,
        stop_loss=20230.0,
        take_profit=20280.0,
        tag="afternoon_test"
    )

    bracket_id = gateway.submit_bracket_order(setup, size=1)
    assert bracket_id is not None
    assert "BRK-" in bracket_id

    # Verify position is active
    pos = gateway.get_positions()
    assert pos["side"] == "LONG"
    assert pos["contracts"] == 1
    assert len(fills_recorded) == 1
    assert fills_recorded[0]["slippage_ticks"] == pytest.approx(1.0)

    # Flatten position
    assert gateway.flatten_all_positions() is True
    pos_after = gateway.get_positions()
    assert pos_after["side"] == "FLAT"
    assert pos_after["contracts"] == 0

    gateway.disconnect()
    assert gateway.is_connected() is False


def test_tradovate_gateway_demo_lifecycle(base_config):
    gateway = TradovateRESTSocketGateway(base_config)
    assert gateway.is_connected() is False

    connected = gateway.connect()
    assert connected is True
    assert gateway.is_connected() is True
    assert gateway.get_account_balance() == 50000.0

    setup = TradeSetup(
        direction=OrderSide.SHORT,
        order_type=OrderType.MARKET,
        stop_loss=20300.0,
        take_profit=20200.0
    )

    bracket_id = gateway.submit_bracket_order(setup, size=1)
    assert bracket_id is not None
    assert "TRADO-BRK-" in bracket_id

    pos = gateway.get_positions()
    assert pos["side"] == "SHORT"
    assert pos["contracts"] == 1

    assert gateway.flatten_all_positions() is True
    assert gateway.get_positions()["side"] == "FLAT"

    gateway.disconnect()
    assert gateway.is_connected() is False
