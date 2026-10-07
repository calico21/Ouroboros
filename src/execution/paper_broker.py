"""
Asynchronous Paper Broker Simulation Engine for AlphaForge.
Implements institutional CME Globex order execution, slippage modeling,
OCO bracket order processing, and real-time Apex compliance monitoring.
"""
import asyncio
from datetime import datetime
from typing import Dict, Optional, List, Callable, Any
import uuid

from src.execution.models import (
    LiveOrderRequest,
    ExecutionReport,
    OrderState,
    BrokerAccountState,
    PositionState,
    LiveTelemetryPayload,
)
from src.execution.order_manager import OrderManager, BracketOrder
from src.execution.risk_sentinel import RiskSentinel
from src.core.events import BarEvent, TradeSetup
from src.core.enums import OrderSide, OrderType


class PaperBroker:
    """
    High-fidelity asynchronous paper broker simulating live CME Globex connectivity.
    Enforces Apex evaluation MTM rules, order queues, fills, and real-time telemetry streaming.
    """

    def __init__(
        self,
        symbol: str = "MNQ",
        point_value: float = 2.0,
        tick_size: float = 0.25,
        default_slippage_ticks: float = 1.0,
        commission_per_contract: float = 0.62,
        starting_balance: float = 50000.0,
        on_telemetry: Optional[Callable[[LiveTelemetryPayload], None]] = None
    ):
        self.symbol = symbol
        self.point_value = point_value
        self.tick_size = tick_size
        self.slippage_pts = default_slippage_ticks * tick_size
        self.commission_per_contract = commission_per_contract
        self.on_telemetry = on_telemetry

        self.order_manager = OrderManager(symbol, point_value, tick_size)
        self.risk_sentinel = RiskSentinel(
            starting_balance=starting_balance,
            on_emergency_flatten=self._handle_emergency_flatten
        )

        self.current_price: float = 20000.0
        self.current_timestamp: datetime = datetime.utcnow()
        self.is_running: bool = False
        self.active_strategy_name: str = "afternoon_trend_continuation"
        self.event_logs: List[Dict[str, Any]] = []

    def start(self, strategy_name: str = "afternoon_trend_continuation") -> None:
        """Starts live/paper trading execution."""
        self.is_running = True
        self.active_strategy_name = strategy_name
        self._log(f"Paper broker started for strategy '{strategy_name}'. Apex 50k risk sentinel armed.")
        self.broadcast_telemetry()

    def stop(self) -> None:
        """Stops live execution and flattens any open position."""
        self._log("Stopping paper broker. Triggering graceful flatten...")
        self.flatten_all_positions("BROKER_STOP")
        self.is_running = False
        self.broadcast_telemetry()

    def process_bar(self, bar: BarEvent) -> None:
        """Processes an incoming market bar, checks fills, and updates MTM equity."""
        self.current_price = bar.close
        self.current_timestamp = bar.timestamp

        # 1. Update open position mark-to-market
        unrealized_pnl = self.order_manager.update_market_price(bar.close, bar.timestamp)

        # 2. Risk Sentinel compliance validation
        is_compliant, breach_reason = self.risk_sentinel.update_equity(
            realized_balance=self.risk_sentinel.current_balance,
            unrealized_pnl=unrealized_pnl,
            current_dt=bar.timestamp
        )

        if not is_compliant:
            self._log(f"Compliance violation detected: {breach_reason}")
            self.flatten_all_positions(breach_reason or "RISK_BREACH")
            self.broadcast_telemetry()
            return

        # 3. Process active orders against bar price action [high, low]
        self._evaluate_pending_orders(bar)

        # 4. Broadcast updated telemetry
        self.broadcast_telemetry()

    def submit_signal(self, setup: TradeSetup) -> Optional[BracketOrder]:
        """Submits an alpha strategy signal as an active order bracket."""
        if not self.is_running:
            self._log("Rejecting signal: Broker is not running.")
            return None

        # Check with Risk Sentinel
        can_trade, reason = self.risk_sentinel.can_open_new_trade(self.current_timestamp)
        if not can_trade:
            self._log(f"Risk Sentinel rejected new signal: {reason}")
            return None

        # Position conflict check: do not open if already positioned
        if self.order_manager.position.side != "FLAT":
            self._log(f"Rejecting signal: Existing position active ({self.order_manager.position.side}).")
            return None

        direction = "LONG" if setup.direction == OrderSide.LONG else "SHORT"
        entry_type = "MARKET" if setup.order_type == OrderType.MARKET else "LIMIT"

        # Account buffer for sizing
        distance_to_floor = self.risk_sentinel.total_equity - self.risk_sentinel.trailing_floor

        bracket = self.order_manager.create_bracket(
            direction=direction,
            entry_type=entry_type,
            stop_loss_price=setup.stop_loss,
            take_profit_price=setup.take_profit,
            entry_price=setup.limit_price or self.current_price,
            quantity=1,
            tag=setup.tag,
            buffer_equity=distance_to_floor
        )

        self._log(f"Bracket created: {bracket.bracket_id} [{direction} 1ct @ {entry_type} | SL: {setup.stop_loss:.2f} | TP: {setup.take_profit:.2f}]")

        # If market order, simulate immediate fill
        if entry_type == "MARKET":
            fill_price = (self.current_price + self.slippage_pts) if direction == "LONG" else (self.current_price - self.slippage_pts)
            report = ExecutionReport(
                exec_id=f"EX-{uuid.uuid4().hex[:8]}",
                client_order_id=bracket.parent_order.client_order_id,
                broker_order_id=f"BRK-ORD-{uuid.uuid4().hex[:6]}",
                symbol=self.symbol,
                direction=direction,
                order_type="MARKET",
                status=OrderState.FILLED,
                last_qty=1,
                cum_qty=1,
                leaves_qty=0,
                last_price=fill_price,
                avg_price=fill_price,
                commission=self.commission_per_contract,
                text="Market Order Filled with 1-tick slippage",
                timestamp=self.current_timestamp
            )
            # Deduct commission
            self.risk_sentinel.current_balance -= self.commission_per_contract
            self.order_manager.process_execution_report(report)
            self._log(f"Market Entry Filled: {bracket.direction} 1ct @ {fill_price:.2f}")

        self.broadcast_telemetry()
        return bracket

    def flatten_all_positions(self, reason: str = "MANUAL_FLATTEN") -> None:
        """Emergency action: cancels all pending orders and liquidates active positions at market."""
        pos = self.order_manager.position
        if pos.side != "FLAT" and pos.contracts > 0:
            exit_dir = "SHORT" if pos.side == "LONG" else "LONG"
            fill_price = (self.current_price - self.slippage_pts) if pos.side == "LONG" else (self.current_price + self.slippage_pts)

            pnl_pts = (fill_price - pos.entry_price) if pos.side == "LONG" else (pos.entry_price - fill_price)
            realized_pnl = (pnl_pts * self.point_value * pos.contracts) - (self.commission_per_contract * pos.contracts)

            self.risk_sentinel.current_balance += realized_pnl
            self.risk_sentinel.unrealized_pnl = 0.0
            self.risk_sentinel.total_equity = self.risk_sentinel.current_balance

            report = ExecutionReport(
                exec_id=f"FLATTEN-{uuid.uuid4().hex[:8]}",
                client_order_id=f"FLATTEN-CMD-{uuid.uuid4().hex[:6]}",
                broker_order_id="BROKER-LIQUIDATE",
                symbol=self.symbol,
                direction=exit_dir,
                order_type="MARKET",
                status=OrderState.FILLED,
                last_qty=pos.contracts,
                cum_qty=pos.contracts,
                leaves_qty=0,
                last_price=fill_price,
                avg_price=fill_price,
                commission=self.commission_per_contract * pos.contracts,
                text=f"Flatten Execution: {reason}",
                timestamp=self.current_timestamp
            )
            self.order_manager.execution_history.append(report)

            pos.side = "FLAT"
            pos.contracts = 0
            pos.unrealized_pnl = 0.0

            self._log(f"[FLATTEN_EXECUTED] Closed {pos.contracts}ct position @ {fill_price:.2f}. Realized PnL: ${realized_pnl:.2f} ({reason})")

        # Cancel all active child and pending orders
        for order_id in list(self.order_manager.order_states.keys()):
            if self.order_manager.order_states[order_id] in (OrderState.NEW, OrderState.PENDING_NEW):
                self.order_manager.order_states[order_id] = OrderState.CANCELLED

        self.broadcast_telemetry()

    def _evaluate_pending_orders(self, bar: BarEvent) -> None:
        """Evaluates active take-profit and stop-loss orders against bar [high, low]."""
        pos = self.order_manager.position
        if pos.side == "FLAT" or pos.contracts == 0:
            return

        for bracket_id, bracket in list(self.order_manager.brackets.items()):
            if not bracket.is_active or not bracket.parent_filled:
                continue

            # Check Stop Loss
            sl = bracket.stop_loss_order
            if sl and self.order_manager.order_states.get(sl.client_order_id) == OrderState.NEW:
                sl_hit = False
                sl_fill_price = sl.stop_price or 0.0
                if bracket.direction == "LONG" and bar.low <= sl.stop_price:
                    sl_hit = True
                    sl_fill_price = min(sl.stop_price, bar.open if bar.open < sl.stop_price else sl.stop_price) - self.slippage_pts
                elif bracket.direction == "SHORT" and bar.high >= sl.stop_price:
                    sl_hit = True
                    sl_fill_price = max(sl.stop_price, bar.open if bar.open > sl.stop_price else sl.stop_price) + self.slippage_pts

                if sl_hit:
                    report = ExecutionReport(
                        exec_id=f"EX-{uuid.uuid4().hex[:8]}",
                        client_order_id=sl.client_order_id,
                        broker_order_id=f"SL-FILL-{uuid.uuid4().hex[:6]}",
                        symbol=self.symbol,
                        direction=sl.direction,
                        order_type="STOP",
                        status=OrderState.FILLED,
                        last_qty=bracket.quantity,
                        cum_qty=bracket.quantity,
                        leaves_qty=0,
                        last_price=sl_fill_price,
                        avg_price=sl_fill_price,
                        commission=self.commission_per_contract * bracket.quantity,
                        text="Stop Loss Triggered",
                        timestamp=bar.timestamp
                    )
                    self._process_fill(report)
                    continue

            # Check Take Profit
            tp = bracket.take_profit_order
            if tp and self.order_manager.order_states.get(tp.client_order_id) == OrderState.NEW:
                tp_hit = False
                tp_fill_price = tp.limit_price or 0.0
                if bracket.direction == "LONG" and bar.high >= tp.limit_price:
                    tp_hit = True
                    tp_fill_price = tp.limit_price
                elif bracket.direction == "SHORT" and bar.low <= tp.limit_price:
                    tp_hit = True
                    tp_fill_price = tp.limit_price

                if tp_hit:
                    report = ExecutionReport(
                        exec_id=f"EX-{uuid.uuid4().hex[:8]}",
                        client_order_id=tp.client_order_id,
                        broker_order_id=f"TP-FILL-{uuid.uuid4().hex[:6]}",
                        symbol=self.symbol,
                        direction=tp.direction,
                        order_type="LIMIT",
                        status=OrderState.FILLED,
                        last_qty=bracket.quantity,
                        cum_qty=bracket.quantity,
                        leaves_qty=0,
                        last_price=tp_fill_price,
                        avg_price=tp_fill_price,
                        commission=self.commission_per_contract * bracket.quantity,
                        text="Take Profit Filled",
                        timestamp=bar.timestamp
                    )
                    self._process_fill(report)

    def _process_fill(self, report: ExecutionReport) -> None:
        """Applies execution fill, credits realized PnL to risk sentinel, and executes OCO cancel."""
        pnl_pts = (report.avg_price - self.order_manager.position.entry_price) if self.order_manager.position.side == "LONG" else (self.order_manager.position.entry_price - report.avg_price)
        realized = (pnl_pts * self.point_value * report.cum_qty) - report.commission

        self.risk_sentinel.current_balance += realized
        self.risk_sentinel.unrealized_pnl = 0.0
        self.risk_sentinel.total_equity = self.risk_sentinel.current_balance

        # Process OCO cancellation of counterpart
        cancelled_actions = self.order_manager.process_execution_report(report)
        for act in cancelled_actions:
            self._log(f"OCO Trigger: Cancelled counterpart order {act.client_order_id} ({act.role.value})")

        self._log(f"Order Filled: {report.direction} @ {report.avg_price:.2f} ({report.text}). Realized: ${realized:.2f}")

    def _handle_emergency_flatten(self, reason: str) -> None:
        self._log(f"[SENTINEL_KILL_SWITCH] Emergency flatten requested: {reason}")
        self.flatten_all_positions(reason)

    def broadcast_telemetry(self) -> None:
        """Sends real-time telemetry update."""
        account_state = self.risk_sentinel.get_state()
        pos = self.order_manager.position
        active_orders = self.order_manager.get_active_orders()
        recent_fills = [
            {
                "exec_id": e.exec_id,
                "order_id": e.client_order_id,
                "direction": e.direction,
                "price": e.avg_price,
                "qty": e.cum_qty,
                "text": e.text,
                "timestamp": e.timestamp.strftime("%H:%M:%S")
            }
            for e in self.order_manager.execution_history[-10:]
        ]

        payload = LiveTelemetryPayload(
            timestamp=self.current_timestamp.strftime("%Y-%m-%d %H:%M:%S EST"),
            strategy=self.active_strategy_name,
            is_running=self.is_running,
            account=account_state,
            position=pos,
            active_orders=active_orders,
            recent_fills=recent_fills,
            event_logs=self.event_logs[-20:]
        )

        if self.on_telemetry:
            self.on_telemetry(payload)

    def _log(self, text: str) -> None:
        entry = {
            "time": datetime.utcnow().strftime("%H:%M:%S"),
            "message": text
        }
        self.event_logs.append(entry)
        if len(self.event_logs) > 100:
            self.event_logs = self.event_logs[-100:]
