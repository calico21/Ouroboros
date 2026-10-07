"""
Unit tests for Forensic Metrics Engine, Loss Taxonomy, and Sensitivity.
"""
from datetime import datetime, timezone
from src.core.events import TradeRecord
from src.core.enums import OrderSide, LossCategory
from src.analytics.excursion import ExcursionAnalytics
from src.analytics.loss_taxonomy import LossTaxonomyEngine
from src.analytics.sensitivity import FrictionFrontierEngine


def create_dummy_trade(
    pnl: float,
    gross_pnl: float,
    mfe_r: float,
    mae_r: float,
    bars_held: int,
    exit_reason: str = "STOP_LOSS"
) -> TradeRecord:
    return TradeRecord(
        trade_id="test-1",
        symbol="MNQ",
        strategy_name="orb",
        tag="default",
        side=OrderSide.LONG,
        contracts=1,
        entry_time=datetime(2026, 3, 10, 9, 35, tzinfo=timezone.utc),
        entry_price=20000.0,
        exit_time=datetime(2026, 3, 10, 9, 50, tzinfo=timezone.utc),
        exit_price=19980.0 if pnl < 0 else 20040.0,
        exit_reason=exit_reason,
        initial_sl=19980.0,
        initial_tp=20040.0,
        risk_r_price=20.0,
        mfe_price=20000.0 + (mfe_r * 20.0),
        mae_price=20000.0 - (mae_r * 20.0),
        mfe_r=mfe_r,
        mae_r=mae_r,
        time_to_peak_mfe=2,
        bars_held=bars_held,
        gross_pnl=gross_pnl,
        net_pnl=pnl,
        commissions=1.24,
        slippage_paid=1.0,
        r_multiple=pnl / 40.0,
        excursion_efficiency=0.5
    )


def test_directional_drift_ratio_disqualification():
    """Verify drift ratio disqualifies alpha when below 1.5x threshold."""
    # MFE 0.5R vs MAE 1.0R -> Drift Ratio = 0.5x (< 1.5x)
    trades = [
        create_dummy_trade(pnl=-40.0, gross_pnl=-38.0, mfe_r=0.4, mae_r=1.0, bars_held=3),
        create_dummy_trade(pnl=80.0, gross_pnl=82.0, mfe_r=0.6, mae_r=0.9, bars_held=8)
    ]
    res = ExcursionAnalytics.analyze(trades)
    assert res["drift_ratio"] < 1.50
    assert res["is_alpha_disqualified"] is True


def test_loss_taxonomy_death_tree_classification():
    """Verify exact mutual exclusion of Algorithmic Death Tree buckets."""
    # 1. Immediate flush: exits within 6 bars with MFE_R < 0.35
    t_flush = create_dummy_trade(pnl=-40.0, gross_pnl=-38.0, mfe_r=0.20, mae_r=1.0, bars_held=4)
    assert LossTaxonomyEngine.classify(t_flush) == LossCategory.IMMEDIATE_FLUSH

    # 2. Trapped trade: reached MFE_R >= 0.80 before collapsing
    t_trapped = create_dummy_trade(pnl=-40.0, gross_pnl=-38.0, mfe_r=0.85, mae_r=1.0, bars_held=12)
    assert LossTaxonomyEngine.classify(t_trapped) == LossCategory.TRAPPED_TRADE

    # 3. Friction drain: gross PnL > 0, net PnL <= 0
    t_friction = create_dummy_trade(pnl=-0.50, gross_pnl=1.50, mfe_r=0.40, mae_r=0.5, bars_held=10)
    assert LossTaxonomyEngine.classify(t_friction) == LossCategory.FRICTION_DRAIN

    # 4. Structural invalidation: standard orderly stop
    t_orderly = create_dummy_trade(pnl=-40.0, gross_pnl=-38.0, mfe_r=0.45, mae_r=1.0, bars_held=10)
    assert LossTaxonomyEngine.classify(t_orderly) == LossCategory.STRUCTURAL_INVALIDATION
