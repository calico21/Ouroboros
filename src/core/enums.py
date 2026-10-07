"""
Core Enums for AlphaForge Quantitative Backtesting & Diagnostics Engine.
"""
from enum import Enum, auto


class OrderSide(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class PositionSide(str, Enum):
    FLAT = "FLAT"
    LONG = "LONG"
    SHORT = "SHORT"


class DrawdownType(str, Enum):
    INTRA_TRADE_PEAK_MTM = "intra_trade_peak_mtm"
    END_OF_DAY = "end_of_day"
    STATIC = "static"


class LossCategory(str, Enum):
    IMMEDIATE_FLUSH = "Immediate Flush"            # Exits at SL <= 6 bars with MFE_R < 0.35
    TRAPPED_TRADE = "Trapped Trade"                # Reached MFE_R >= 0.80 before collapsing to loss or scratch
    FRICTION_DRAIN = "Friction Drain"              # Gross PnL > 0, Net PnL <= 0 due to fees/slippage
    STRUCTURAL_INVALIDATION = "Structural Invalidation"  # Orderly stop-loss violation


class AccountStatus(str, Enum):
    ACTIVE = "ACTIVE"
    PASSED = "PASSED"
    BREACHED_TRAILING_FLOOR = "BREACHED_TRAILING_FLOOR"
    BREACHED_DAILY_LOSS = "BREACHED_DAILY_LOSS"
    MAX_TRADES_REACHED = "MAX_TRADES_REACHED"
