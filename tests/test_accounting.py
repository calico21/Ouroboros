"""
Unit tests for Prop Firm Peak-Unrealized MTM Trailing Floor Accounting.
"""
from datetime import datetime, timezone
from src.core.enums import AccountStatus, DrawdownType
from src.engine.account_tracker import PropFirmAccountTracker


def test_mtm_trailing_ratchet():
    """Verify intra-bar peak unrealized PnL ratchets HWM and floor upward."""
    account = PropFirmAccountTracker(
        initial_balance=50000.0,
        trailing_max_dd=2500.0,
        profit_target=3000.0,
        floor_lock_threshold=2600.0,
        lock_floor_offset=100.0
    )

    assert account.balance == 50000.0
    assert account.high_water_mark == 50000.0
    assert account.floor == 47500.0
    assert account.cushion == 2500.0

    # Bar 1: Unrealized run-up +$1,000 (peak equity $51,000)
    account.update_intra_bar(unrealized_peak_pnl=1000.0, unrealized_trough_pnl=200.0)
    assert account.high_water_mark == 51000.0
    assert account.floor == 48500.0  # 51,000 - 2,500
    assert account.cushion == 1500.0  # 50,000 - 48,500

    # Bar 2: Trade closes with +$800 realized
    account.record_trade_realized(800.0)
    assert account.balance == 50800.0
    assert account.high_water_mark == 51000.0
    assert account.floor == 48500.0


def test_permanent_floor_lock():
    """Verify that when HWM reaches +$2,600 ($52,600), floor locks permanently at $50,100."""
    account = PropFirmAccountTracker(
        initial_balance=50000.0,
        trailing_max_dd=2500.0,
        profit_target=3000.0,
        floor_lock_threshold=2600.0,
        lock_floor_offset=100.0
    )

    # Surge to $52,800 peak MTM
    account.update_intra_bar(unrealized_peak_pnl=2800.0, unrealized_trough_pnl=1000.0)
    assert account.high_water_mark == 52800.0
    assert account.is_floor_locked is True
    # Floating floor would be 52800 - 2500 = 50300, locked floor is >= 50100
    assert account.floor >= 50100.0

    # Drawdown back to $51,000 realized
    account.record_trade_realized(1000.0)
    # Floor should never drop below locked floor
    assert account.floor >= 50100.0


def test_immediate_liquidation_on_floor_breach():
    """Verify that if unrealized trough breaches floor, account status transitions to BREACHED."""
    account = PropFirmAccountTracker(
        initial_balance=50000.0,
        trailing_max_dd=2500.0
    )
    assert account.floor == 47500.0

    # Intra-bar crash down -$2,600 (equity $47,400 <= $47,500)
    account.update_intra_bar(unrealized_peak_pnl=0.0, unrealized_trough_pnl=-2600.0)
    assert account.status == AccountStatus.BREACHED_TRAILING_FLOOR
    assert not account.is_active
