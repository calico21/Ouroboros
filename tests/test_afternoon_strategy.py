"""
PyTest discovery test for Afternoon Trend Continuation Strategy.
"""
from src.strategies.afternoon_trend_continuation.tests import test_afternoon_consolidation_and_breakout


def test_afternoon_strategy_integration():
    test_afternoon_consolidation_and_breakout()
