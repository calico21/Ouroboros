"""
Order Manager and Bracket State Machine for AlphaForge.
Coordinates parent entry orders and OCO (One-Cancels-Other) child stop-loss
and take-profit orders with strict single-contract discipline and de-risking.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, List, Tuple, Any
import uuid

from src.execution.models import (
    LiveOrderRequest,
    ExecutionReport,
    OrderState,
    BracketRole,
    TimeInForce,
    PositionState,
)


@dataclass
class BracketOrder:
    """Represents a composite bracket structure (Parent + TP + SL)."""
    bracket_id: str
    symbol: str
    direction: str  # "LONG" or "SHORT"
    quantity: int
    parent_order: LiveOrderRequest
    take_profit_order: Optional[LiveOrderRequest] = None
    stop_loss_order: Optional[LiveOrderRequest] = None
    is_active: bool = True
    parent_filled: bool = False
    entry_fill_price: float = 0.0
    created_at: datetime = field(default_factory=datetime.utcnow)


class OrderManager:
    """
    Manages client order lifecycles, bracket state transitions,
    and OCO cancellations for live and paper futures execution.
    """

    def __init__(self, symbol: str = "MNQ", point_value: float = 2.0, tick_size: float = 0.25):
        self.symbol = symbol
        self.point_value = point_value
        self.tick_size = tick_size

        # Orders registry: order_id -> LiveOrderRequest
        self.orders: Dict[str, LiveOrderRequest] = {}
        # Order states: order_id -> OrderState
        self.order_states: Dict[str, OrderState] = {}
        # Order fills / executions: order_id -> List[ExecutionReport]
        self.execution_history: List[ExecutionReport] = []
        # Active brackets: bracket_id -> BracketOrder
        self.brackets: Dict[str, BracketOrder] = {}
        # Child to bracket mapping
        self.order_to_bracket: Dict[str, str] = {}

        # Current open position
        self.position = PositionState(symbol=symbol)

    def create_bracket(
        self,
        direction: str,
        entry_type: str,
        stop_loss_price: float,
        take_profit_price: float,
        entry_price: Optional[float] = None,
        quantity: int = 1,
        tag: str = "alpha_bracket",
        buffer_equity: float = 2500.0
    ) -> BracketOrder:
        """
        Builds a verified bracket order structure.
        Applies convex de-risking: enforces 1 contract maximum for apex evaluation safety.
        """
        # Conservative sizing rule: keep strictly 1 contract if buffer < $1,000
        safe_quantity = 1 if buffer_equity < 1500.0 else min(quantity, 2)
        bracket_id = f"BRK-{uuid.uuid4().hex[:8]}"

        parent_id = f"ORD-{uuid.uuid4().hex[:8]}"
        tp_id = f"TP-{uuid.uuid4().hex[:8]}"
        sl_id = f"SL-{uuid.uuid4().hex[:8]}"

        parent = LiveOrderRequest(
            client_order_id=parent_id,
            symbol=self.symbol,
            direction=direction,
            order_type=entry_type,
            quantity=safe_quantity,
            limit_price=entry_price if entry_type == "LIMIT" else None,
            role=BracketRole.PARENT,
            tag=tag
        )

        exit_direction = "SHORT" if direction == "LONG" else "LONG"

        tp = LiveOrderRequest(
            client_order_id=tp_id,
            symbol=self.symbol,
            direction=exit_direction,
            order_type="LIMIT",
            quantity=safe_quantity,
            limit_price=take_profit_price,
            role=BracketRole.TAKE_PROFIT,
            parent_order_id=parent_id,
            tag=f"{tag}_tp"
        )

        sl = LiveOrderRequest(
            client_order_id=sl_id,
            symbol=self.symbol,
            direction=exit_direction,
            order_type="STOP",
            quantity=safe_quantity,
            stop_price=stop_loss_price,
            role=BracketRole.STOP_LOSS,
            parent_order_id=parent_id,
            tag=f"{tag}_sl"
        )

        bracket = BracketOrder(
            bracket_id=bracket_id,
            symbol=self.symbol,
            direction=direction,
            quantity=safe_quantity,
            parent_order=parent,
            take_profit_order=tp,
            stop_loss_order=sl
        )

        self.orders[parent_id] = parent
        self.orders[tp_id] = tp
        self.orders[sl_id] = sl

        self.order_states[parent_id] = OrderState.NEW
        self.order_states[tp_id] = OrderState.PENDING_NEW
        self.order_states[sl_id] = OrderState.PENDING_NEW

        self.order_to_bracket[parent_id] = bracket_id
        self.order_to_bracket[tp_id] = bracket_id
        self.order_to_bracket[sl_id] = bracket_id

        self.brackets[bracket_id] = bracket
        return bracket

    def process_execution_report(self, report: ExecutionReport) -> List[LiveOrderRequest]:
        """
        Updates order and position states upon receiving execution report.
        Returns any new cancellation or activation order requests triggered by OCO logic.
        """
        self.execution_history.append(report)
        self.order_states[report.client_order_id] = report.status
        triggered_actions: List[LiveOrderRequest] = []

        bracket_id = self.order_to_bracket.get(report.client_order_id)
        if not bracket_id or bracket_id not in self.brackets:
            return triggered_actions

        bracket = self.brackets[bracket_id]

        # Scenario A: Parent Entry Filled
        if report.client_order_id == bracket.parent_order.client_order_id and report.status == OrderState.FILLED:
            bracket.parent_filled = True
            bracket.entry_fill_price = report.avg_price

            # Update position state
            self.position.side = bracket.direction
            self.position.contracts = report.cum_qty
            self.position.entry_price = report.avg_price
            self.position.current_price = report.avg_price
            self.position.entry_time = report.timestamp
            self.position.stop_loss_price = bracket.stop_loss_order.stop_price if bracket.stop_loss_order else None
            self.position.take_profit_price = bracket.take_profit_order.limit_price if bracket.take_profit_order else None

            # Arm child orders
            if bracket.take_profit_order:
                self.order_states[bracket.take_profit_order.client_order_id] = OrderState.NEW
            if bracket.stop_loss_order:
                self.order_states[bracket.stop_loss_order.client_order_id] = OrderState.NEW

        # Scenario B: Child Exit Filled (OCO Trigger)
        elif report.status == OrderState.FILLED:
            # Position closed
            pnl_pts = (report.avg_price - self.position.entry_price) if self.position.side == "LONG" else (self.position.entry_price - report.avg_price)
            gross_pnl = pnl_pts * self.point_value * report.cum_qty
            self.position.realized_pnl += gross_pnl
            self.position.unrealized_pnl = 0.0
            self.position.side = "FLAT"
            self.position.contracts = 0
            bracket.is_active = False

            # Cancel counterpart OCO order
            if bracket.take_profit_order and report.client_order_id == bracket.take_profit_order.client_order_id:
                if bracket.stop_loss_order:
                    sl_id = bracket.stop_loss_order.client_order_id
                    self.order_states[sl_id] = OrderState.PENDING_CANCEL
                    cancel_req = LiveOrderRequest(
                        client_order_id=sl_id,
                        direction=bracket.stop_loss_order.direction,
                        order_type="CANCEL",
                        quantity=bracket.stop_loss_order.quantity,
                        role=BracketRole.STOP_LOSS
                    )
                    triggered_actions.append(cancel_req)

            elif bracket.stop_loss_order and report.client_order_id == bracket.stop_loss_order.client_order_id:
                if bracket.take_profit_order:
                    tp_id = bracket.take_profit_order.client_order_id
                    self.order_states[tp_id] = OrderState.PENDING_CANCEL
                    cancel_req = LiveOrderRequest(
                        client_order_id=tp_id,
                        direction=bracket.take_profit_order.direction,
                        order_type="CANCEL",
                        quantity=bracket.take_profit_order.quantity,
                        role=BracketRole.TAKE_PROFIT
                    )
                    triggered_actions.append(cancel_req)

        return triggered_actions

    def update_market_price(self, current_price: float, timestamp: datetime) -> float:
        """Updates open position unrealized MTM PnL and excursions."""
        if self.position.side == "FLAT" or self.position.contracts == 0:
            self.position.unrealized_pnl = 0.0
            self.position.current_price = current_price
            return 0.0

        self.position.current_price = current_price
        pts = (current_price - self.position.entry_price) if self.position.side == "LONG" else (self.position.entry_price - current_price)
        unrealized = pts * self.point_value * self.position.contracts
        self.position.unrealized_pnl = unrealized

        # Excursions
        self.position.peak_unrealized_pnl = max(self.position.peak_unrealized_pnl, unrealized)
        self.position.trough_unrealized_pnl = min(self.position.trough_unrealized_pnl, unrealized)

        # R-multiples if SL is defined
        if self.position.stop_loss_price:
            initial_risk_pts = abs(self.position.entry_price - self.position.stop_loss_price)
            if initial_risk_pts > 0:
                self.position.mfe_r = max(0.0, (self.position.peak_unrealized_pnl / (initial_risk_pts * self.point_value * self.position.contracts)))
                self.position.mae_r = max(0.0, (-self.position.trough_unrealized_pnl / (initial_risk_pts * self.point_value * self.position.contracts)))

        return unrealized

    def get_active_orders(self) -> List[Dict[str, Any]]:
        """Returns list of currently active or open orders."""
        active = []
        for order_id, state in self.order_states.items():
            if state in (OrderState.NEW, OrderState.PENDING_NEW, OrderState.PARTIALLY_FILLED):
                req = self.orders[order_id]
                active.append({
                    "order_id": order_id,
                    "direction": req.direction,
                    "order_type": req.order_type,
                    "quantity": req.quantity,
                    "price": req.limit_price or req.stop_price or "MARKET",
                    "role": req.role.value,
                    "status": state.value
                })
        return active

    def cancel_all_orders(self, reason: str = "CANCEL") -> List[str]:
        """Cancels all active working orders across all brackets."""
        cancelled = []
        for order_id, state in list(self.order_states.items()):
            if state in (OrderState.NEW, OrderState.PENDING_NEW, OrderState.PARTIALLY_FILLED):
                self.order_states[order_id] = OrderState.CANCELLED
                cancelled.append(order_id)
        for b in self.brackets.values():
            b.is_active = False
        return cancelled
