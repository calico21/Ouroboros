"""
Unit tests for Strategy Discovery and Dynamic Registry.
"""
from src.strategies import discover_strategies, STRATEGY_REGISTRY
from src.strategies.base import BaseStrategy


def test_strategy_discovery():
    strats = discover_strategies()
    assert "orb_5m_binary" in strats
    assert "vwap_mean_reversion_10am" in strats
    assert "open_drive_continuation" in strats

    for name, cls in strats.items():
        assert issubclass(cls, BaseStrategy)
        instance = cls()
        assert instance.config is not None
        assert "strategy_name" in instance.config
