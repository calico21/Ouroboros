"""
Portfolio Account Tracking & Concurrency Engine for AlphaForge.
Maintains independent strategy sub-accounts while enforcing a consolidated
Apex 50k Peak-Unrealized MTM Trailing Floor, floor lock, and multi-contract risk limits.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from src.core.enums import OrderSide, AccountStatus, DrawdownType
from src.core.events import TradeRecord
from src.engine.account_tracker import PropFirmAccountTracker


@dataclass
class StrategySubAccount:
    """Tracks isolated performance and state of an individual strategy within the portfolio."""
    strategy_name: str
    allocated_weight: float = 0.50
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    closed_trades: List[TradeRecord] = field(default_factory=list)
    trades_count: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    gross_pnl: float = 0.0
    fees_paid: float = 0.0

    @property
    def win_rate_pct(self) -> float:
        return (self.winning_trades / self.trades_count * 100.0) if self.trades_count > 0 else 0.0

    def record_closed_trade(self, trade: TradeRecord) -> None:
        self.closed_trades.append(trade)
        self.trades_count += 1
        self.realized_pnl += trade.net_pnl
        self.gross_pnl += trade.gross_pnl
        self.fees_paid += (trade.commissions + trade.slippage_paid)
        if trade.net_pnl > 0:
            self.winning_trades += 1
        elif trade.net_pnl < 0:
            self.losing_trades += 1


class PortfolioAccountTracker(PropFirmAccountTracker):
    """
    Consolidated Multi-Strategy Prop Account Tracker.
    Coordinates multiple strategy sub-accounts against a unified Apex 50k Peak-Unrealized
    trailing drawdown floor, dynamic cushion sharing, and multi-strategy concurrency limits.
    """

    def __init__(
        self,
        initial_balance: float = 50000.0,
        trailing_max_dd: float = 2500.0,
        profit_target: float = 3000.0,
        drawdown_type: DrawdownType = DrawdownType.INTRA_TRADE_PEAK_MTM,
        floor_lock_threshold: Optional[float] = 2600.0,
        lock_floor_offset: Optional[float] = 100.0,
        daily_loss_limit: Optional[float] = 1000.0,
        max_portfolio_contracts: int = 6
    ):
        super().__init__(
            initial_balance=initial_balance,
            trailing_max_dd=trailing_max_dd,
            profit_target=profit_target,
            drawdown_type=drawdown_type,
            floor_lock_threshold=floor_lock_threshold,
            lock_floor_offset=lock_floor_offset,
            daily_loss_limit=daily_loss_limit,
            max_contracts=max_portfolio_contracts
        )
        self.max_portfolio_contracts = max_portfolio_contracts
        self.sub_accounts: Dict[str, StrategySubAccount] = {}
        # Concurrency & active position state: strat_name -> dict
        self.active_positions: Dict[str, Dict[str, Any]] = {}
        self.equity_history: List[Dict[str, Any]] = []

    @classmethod
    def from_config(cls, cfg: Dict[str, Any], max_contracts: int = 6) -> "PortfolioAccountTracker":
        dd_type_str = cfg.get("drawdown_type", "intra_trade_peak_mtm")
        dd_type = DrawdownType(dd_type_str)
        return cls(
            initial_balance=float(cfg.get("initial_balance", 50000.0)),
            trailing_max_dd=float(cfg.get("trailing_max_drawdown", 2500.0)),
            profit_target=float(cfg.get("profit_target", 3000.0)),
            drawdown_type=dd_type,
            floor_lock_threshold=cfg.get("floor_lock_threshold"),
            lock_floor_offset=cfg.get("lock_floor_offset"),
            daily_loss_limit=cfg.get("daily_loss_limit", 1000.0),
            max_portfolio_contracts=max_contracts
        )

    def register_strategy(self, strategy_name: str, weight: float = 0.50) -> None:
        """Register a strategy sub-account for isolated performance tracking."""
        if strategy_name not in self.sub_accounts:
            self.sub_accounts[strategy_name] = StrategySubAccount(
                strategy_name=strategy_name,
                allocated_weight=weight
            )

    def can_open_position(self, strategy_name: str, direction: OrderSide, proposed_contracts: int) -> Tuple[bool, str]:
        """
        Enforces concurrency locks and exposure caps:
        1. Master account must be active.
        2. Total contracts across all active strategy positions + proposed <= max_portfolio_contracts.
        3. Directional lock: Prevent opposing simultaneous allocations (e.g. LONG and SHORT).
        """
        if not self.is_active:
            return False, f"Account not active ({self.status.value})"

        total_open_contracts = sum(pos.get("contracts", 0) for pos in self.active_positions.values())
        if total_open_contracts + proposed_contracts > self.max_portfolio_contracts:
            return False, (
                f"Exceeds max portfolio exposure: {total_open_contracts} open + {proposed_contracts} "
                f"> {self.max_portfolio_contracts} max contracts"
            )

        # Directional conflict verification
        for other_strat, pos in self.active_positions.items():
            if other_strat != strategy_name and pos.get("contracts", 0) > 0:
                other_dir = pos.get("direction")
                if other_dir is not None and other_dir != direction:
                    return False, f"Directional conflict with {other_strat} (Active: {other_dir}, Proposed: {direction})"

        return True, "OK"

    def record_sub_account_trade(self, strategy_name: str, trade: TradeRecord) -> None:
        """Records a completed trade into the strategy's sub-account and master account."""
        if strategy_name in self.sub_accounts:
            self.sub_accounts[strategy_name].record_closed_trade(trade)
        self.record_trade_realized(trade.net_pnl)

    def record_equity_snapshot(self, timestamp: datetime, total_unrealized_pnl: float) -> None:
        """Appends timestamped consolidated equity metrics for path analysis."""
        self.equity_history.append({
            "timestamp": timestamp,
            "balance": self.balance,
            "high_water_mark": self.high_water_mark,
            "floor": self.floor,
            "cushion": self.cushion,
            "unrealized_pnl": total_unrealized_pnl,
            "net_equity": self.balance + total_unrealized_pnl,
            "is_locked": self.is_floor_locked
        })
