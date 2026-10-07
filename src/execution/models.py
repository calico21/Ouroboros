"""
Data models and Pydantic schemas for AlphaForge Live and Paper Execution.
Defines institutional broker message contracts, order state containers,
and real-time account telemetry structures.
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class OrderState(str, Enum):
    PENDING_NEW = "PENDING_NEW"
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    PENDING_CANCEL = "PENDING_CANCEL"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class TimeInForce(str, Enum):
    DAY = "DAY"
    GTC = "GTC"
    IOC = "IOC"
    FOK = "FOK"


class BracketRole(str, Enum):
    PARENT = "PARENT"
    TAKE_PROFIT = "TAKE_PROFIT"
    STOP_LOSS = "STOP_LOSS"
    TIME_STOP = "TIME_STOP"


class LiveOrderRequest(BaseModel):
    """Client order request sent to the broker."""
    client_order_id: str
    symbol: str = "MNQ"
    direction: str  # "LONG" or "SHORT"
    order_type: str  # "MARKET", "LIMIT", "STOP"
    quantity: int = 1
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: TimeInForce = TimeInForce.DAY
    role: BracketRole = BracketRole.PARENT
    parent_order_id: Optional[str] = None
    tag: str = "alpha_signal"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ExecutionReport(BaseModel):
    """Broker execution report / fill event."""
    exec_id: str
    client_order_id: str
    broker_order_id: str
    symbol: str = "MNQ"
    direction: str
    order_type: str
    status: OrderState
    last_qty: int = 0
    cum_qty: int = 0
    leaves_qty: int = 0
    last_price: float = 0.0
    avg_price: float = 0.0
    commission: float = 0.0
    text: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PositionState(BaseModel):
    """Real-time active position tracking."""
    symbol: str = "MNQ"
    side: str = "FLAT"  # "FLAT", "LONG", "SHORT"
    contracts: int = 0
    entry_price: float = 0.0
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    peak_unrealized_pnl: float = 0.0
    trough_unrealized_pnl: float = 0.0
    mfe_r: float = 0.0
    mae_r: float = 0.0
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    bars_held: int = 0
    entry_time: Optional[datetime] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class BrokerAccountState(BaseModel):
    """Institutional Apex Peak-Unrealized MTM Trailing Floor Account State."""
    account_id: str = "APEX-50K-LIVE"
    starting_balance: float = 50000.0
    current_balance: float = 50000.0
    unrealized_pnl: float = 0.0
    total_equity: float = 50000.0
    peak_hwm: float = 50000.0
    trailing_floor: float = 47500.0
    target_equity: float = 53000.0
    floor_locked: bool = False
    distance_to_floor: float = 2500.0
    distance_to_target: float = 3000.0
    daily_realized_loss: float = 0.0
    daily_unrealized_loss: float = 0.0
    daily_loss_limit: float = 1000.0
    dll_remaining: float = 1000.0
    dll_breached: bool = False
    floor_breached: bool = False
    is_halted: bool = False
    account_status: str = "ACTIVE"  # "ACTIVE", "PASSED", "BREACHED_TRAILING_FLOOR", "BREACHED_DAILY_LOSS", "HALTED"
    open_positions_count: int = 0
    active_orders_count: int = 0
    last_update: datetime = Field(default_factory=datetime.utcnow)


class LiveTelemetryPayload(BaseModel):
    """Full broadcast packet streamed via WebSockets to client UI."""
    type: str = "TELEMETRY_UPDATE"
    timestamp: str
    strategy: str
    is_running: bool = False
    account: BrokerAccountState
    position: PositionState
    active_orders: List[Dict[str, Any]] = Field(default_factory=list)
    recent_fills: List[Dict[str, Any]] = Field(default_factory=list)
    event_logs: List[Dict[str, Any]] = Field(default_factory=list)
