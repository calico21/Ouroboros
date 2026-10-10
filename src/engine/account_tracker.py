"""
Prop-Firm Accounting and Peak-Unrealized MTM Trailing Drawdown Engine.
Rigorously enforces evaluation mechanics for Apex, Topstep, and MFF accounts.
"""
from typing import Dict, Any, Optional
from datetime import datetime
from src.core.enums import AccountStatus, DrawdownType
from src.core.exceptions import AccountBreachedError


class PropFirmAccountTracker:
    """
    Simulates real-time prop-firm account equity tracking.
    Enforces intra-trade peak mark-to-market trailing floor ratchets.
    """

    def __init__(
        self,
        initial_balance: float = 50000.0,
        trailing_max_dd: float = 2500.0,
        profit_target: float = 3000.0,
        drawdown_type: DrawdownType = DrawdownType.INTRA_TRADE_PEAK_MTM,
        floor_lock_threshold: Optional[float] = 2600.0,
        lock_floor_offset: Optional[float] = 100.0,
        daily_loss_limit: Optional[float] = None,
        max_contracts: int = 10
    ):
        self.initial_balance = initial_balance
        self.trailing_max_dd = trailing_max_dd
        self.profit_target = profit_target
        self.target_balance = initial_balance + profit_target
        self.drawdown_type = drawdown_type
        self.floor_lock_threshold = floor_lock_threshold
        self.lock_floor_offset = lock_floor_offset
        self.daily_loss_limit = daily_loss_limit
        self.max_contracts = max_contracts

        # State Variables
        self.balance: float = initial_balance
        self.high_water_mark: float = initial_balance
        self.floor: float = initial_balance - trailing_max_dd
        self.is_floor_locked: bool = False
        self.locked_floor_level: Optional[float] = (
            initial_balance + lock_floor_offset if lock_floor_offset is not None else None
        )

        # Day tracking
        self.current_date: Optional[str] = None
        self.day_start_balance: float = initial_balance
        self.day_realized_pnl: float = 0.0

        # Status
        self.status: AccountStatus = AccountStatus.ACTIVE
        self.breach_reason: Optional[str] = None

    @classmethod
    def from_config(cls, cfg: Dict[str, Any]) -> "PropFirmAccountTracker":
        dd_type_str = cfg.get("drawdown_type", "intra_trade_peak_mtm")
        dd_type = DrawdownType(dd_type_str)
        return cls(
            initial_balance=float(cfg.get("initial_balance", 50000.0)),
            trailing_max_dd=float(cfg.get("trailing_max_drawdown", 2500.0)),
            profit_target=float(cfg.get("profit_target", 3000.0)),
            drawdown_type=dd_type,
            floor_lock_threshold=cfg.get("floor_lock_threshold"),
            lock_floor_offset=cfg.get("lock_floor_offset"),
            daily_loss_limit=cfg.get("daily_loss_limit"),
            max_contracts=int(cfg.get("max_contracts", 10))
        )

    @property
    def cushion(self) -> float:
        """Current dollar buffer between balance and trailing liquidation floor."""
        return max(0.0, self.balance - self.floor)

    @property
    def is_active(self) -> bool:
        return self.status == AccountStatus.ACTIVE

    def check_new_day(self, timestamp: datetime) -> None:
        """Handles daily session resets and Daily Loss Limit tracking."""
        date_str = timestamp.strftime("%Y-%m-%d")
        if self.current_date != date_str:
            # End of previous day EOD ratchet if configured
            if self.current_date is not None and self.drawdown_type == DrawdownType.END_OF_DAY:
                self._update_floor_ratchet(self.balance)

            self.current_date = date_str
            self.day_start_balance = self.balance
            self.day_realized_pnl = 0.0

    def update_intra_bar(self, unrealized_peak_pnl: float, unrealized_trough_pnl: float) -> None:
        """
        Evaluate account mark-to-market inside a single bar.
        1. Peak MTM updates HWM and immediately pulls trailing floor higher.
        2. Trough MTM checks if unrealized equity violated the updated floor.
        """
        if not self.is_active:
            return

        # Current peak equity within the bar
        bar_peak_equity = self.balance + max(0.0, unrealized_peak_pnl)
        
        # Intra-trade MTM ratchets HWM and floor dynamically
        if self.drawdown_type == DrawdownType.INTRA_TRADE_PEAK_MTM:
            self._update_floor_ratchet(bar_peak_equity)

        # Current trough equity within the bar
        bar_trough_equity = self.balance + unrealized_trough_pnl

        # 1. Check Trailing Drawdown Floor Breach
        if bar_trough_equity <= self.floor:
            self.status = AccountStatus.BREACHED_TRAILING_FLOOR
            self.breach_reason = (
                f"Peak MTM Trailing Floor Breached! Floor: ${self.floor:,.2f}, "
                f"Trough Equity: ${bar_trough_equity:,.2f} (HWM was ${self.high_water_mark:,.2f})"
            )
            return

        # 2. Check Daily Loss Limit (if configured)
        if self.daily_loss_limit is not None:
            day_loss = self.day_start_balance - bar_trough_equity
            if day_loss >= self.daily_loss_limit:
                self.status = AccountStatus.BREACHED_DAILY_LOSS
                self.breach_reason = (
                    f"Daily Loss Limit Breached! Limit: ${self.daily_loss_limit:,.2f}, "
                    f"Current Loss: ${day_loss:,.2f}"
                )

    def _update_floor_ratchet(self, equity_candidate: float) -> None:
        """Applies the non-decreasing trailing floor ratchet and permanent lock logic."""
        if equity_candidate > self.high_water_mark:
            self.high_water_mark = equity_candidate

        if self.drawdown_type == DrawdownType.STATIC:
            # Floor remains at initial_balance - trailing_max_dd
            return

        # Trailing floor and permanent lock logic
        if self.is_floor_locked and self.locked_floor_level is not None:
            new_floor = self.locked_floor_level
        elif (
            self.floor_lock_threshold is not None and
            self.locked_floor_level is not None and
            self.high_water_mark >= (self.initial_balance + self.floor_lock_threshold)
        ):
            self.is_floor_locked = True
            new_floor = self.locked_floor_level
        else:
            new_floor = self.high_water_mark - self.trailing_max_dd

        # Floor can NEVER ratchet downwards
        if new_floor > self.floor:
            self.floor = new_floor

    def record_trade_realized(self, net_pnl: float) -> None:
        """Applies realized trade PnL and verifies target pass / liquidation."""
        if not self.is_active:
            return

        self.balance += net_pnl
        self.day_realized_pnl += net_pnl

        # Post-realization HWM update
        self._update_floor_ratchet(self.balance)

        # Check if profit target reached
        if self.balance >= self.target_balance:
            self.status = AccountStatus.PASSED

        # Check post-trade balance against floor
        if self.balance <= self.floor:
            self.status = AccountStatus.BREACHED_TRAILING_FLOOR
            self.breach_reason = f"Balance ${self.balance:,.2f} fell below floor ${self.floor:,.2f}"
