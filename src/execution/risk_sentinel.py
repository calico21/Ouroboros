"""
Real-Time Risk Sentinel and Apex Compliance Guard for AlphaForge.
Enforces tick-by-tick Peak-Unrealized MTM Trailing Floor ratchets,
permanent floor locking, Daily Loss Limit (DLL: -$1,000) circuit breakers,
and strict 15:55 EST session close hard-liquidations.
"""
from datetime import datetime, time
from typing import Tuple, Optional, Callable, List
import pytz

from src.execution.models import BrokerAccountState


class RiskSentinel:
    """
    Institutional risk watchdog operating alongside execution engines.
    Zero-tolerance compliance enforcement for CME futures prop firm accounts.
    """

    def __init__(
        self,
        starting_balance: float = 50000.0,
        trailing_drawdown_limit: float = 2500.0,
        target_profit: float = 3000.0,
        daily_loss_limit: float = 1000.0,
        lock_at_plus_100: bool = True,
        auto_flatten_time: time = time(15, 55),
        market_open_time: time = time(9, 30),
        on_emergency_flatten: Optional[Callable[[str], None]] = None
    ):
        self.starting_balance = starting_balance
        self.trailing_drawdown_limit = trailing_drawdown_limit
        self.target_profit = target_profit
        self.target_equity = starting_balance + target_profit
        self.daily_loss_limit = daily_loss_limit
        self.lock_at_plus_100 = lock_at_plus_100
        self.auto_flatten_time = auto_flatten_time
        self.market_open_time = market_open_time
        self.on_emergency_flatten = on_emergency_flatten

        # Account Equity States
        self.current_balance = starting_balance
        self.unrealized_pnl = 0.0
        self.total_equity = starting_balance
        self.peak_hwm = starting_balance
        self.trailing_floor = starting_balance - trailing_drawdown_limit
        self.floor_locked = False

        # Daily Session Tracking
        self.session_open_equity = starting_balance
        self.daily_realized_loss = 0.0
        self.current_session_date: Optional[str] = None
        self.is_dll_halted = False
        self.is_floor_breached = False
        self.is_target_reached = False
        self.is_hard_closed = False

        self.est_tz = pytz.timezone("US/Eastern")
        self.audit_log: List[str] = []

    def check_new_session(self, current_dt: datetime) -> None:
        """Handles daily 17:00 or 09:30 session rollover."""
        if current_dt.tzinfo is None:
            current_dt = self.est_tz.localize(current_dt)
        else:
            current_dt = current_dt.astimezone(self.est_tz)

        date_str = current_dt.strftime("%Y-%m-%d")
        if self.current_session_date != date_str:
            self.current_session_date = date_str
            self.session_open_equity = self.current_balance
            self.daily_realized_loss = 0.0
            self.is_dll_halted = False
            self.is_hard_closed = False
            self._log(f"[SESSION_RESET] New trading session {date_str}. Open Equity: ${self.session_open_equity:.2f}")

    def update_equity(
        self,
        realized_balance: float,
        unrealized_pnl: float,
        current_dt: datetime
    ) -> Tuple[bool, Optional[str]]:
        """
        Processes tick/bar MTM equity update and validates compliance rules.
        Returns: (is_compliant, breach_reason_if_any)
        """
        self.check_new_session(current_dt)

        self.current_balance = realized_balance
        self.unrealized_pnl = unrealized_pnl
        self.total_equity = realized_balance + unrealized_pnl

        # 1. Update Peak High-Water Mark on intra-trade unrealized equity
        if self.total_equity > self.peak_hwm:
            self.peak_hwm = self.total_equity
            self._recalculate_floor()

        # 2. Check Target Profit Pass
        if self.total_equity >= self.target_equity and not self.is_target_reached:
            self.is_target_reached = True
            self._log(f"[EVALUATION_PASSED] Target ${self.target_equity:.2f} reached! Current: ${self.total_equity:.2f}")

        # 3. Check Trailing Floor Breach (Highest priority)
        if self.total_equity <= self.trailing_floor:
            self.is_floor_breached = True
            reason = (
                f"TRAILING_FLOOR_BREACH: Equity ${self.total_equity:.2f} breached floor "
                f"${self.trailing_floor:.2f} (Peak HWM: ${self.peak_hwm:.2f})"
            )
            self._log(f"[CRITICAL_ALERT] {reason}")
            self._trigger_flatten(reason)
            return False, reason

        # 4. Check Daily Loss Limit (Realized + Open loss from session open)
        daily_drawdown = self.session_open_equity - self.total_equity
        if daily_drawdown >= self.daily_loss_limit and not self.is_dll_halted:
            self.is_dll_halted = True
            reason = (
                f"DAILY_LOSS_LIMIT_TRIGGER: Daily loss -${daily_drawdown:.2f} exceeded "
                f"limit -${self.daily_loss_limit:.2f}"
            )
            self._log(f"[DLL_BREACH] {reason}")
            self._trigger_flatten(reason)
            return False, reason

        # 5. Check 15:55 EST Hard Flatten (Apex rule: flat before 16:59, institutional safety 15:55)
        if current_dt.tzinfo is None:
            t = current_dt.time()
        else:
            t = current_dt.astimezone(self.est_tz).time()

        if t >= self.auto_flatten_time and not self.is_hard_closed:
            self.is_hard_closed = True
            reason = f"END_OF_DAY_HARD_FLATTEN: Current time {t.strftime('%H:%M:%S')} >= {self.auto_flatten_time.strftime('%H:%M:%S')}"
            self._log(f"[EOD_FLATTEN] {reason}")
            self._trigger_flatten(reason)
            return False, reason

        return True, None

    def can_open_new_trade(self, current_dt: datetime) -> Tuple[bool, str]:
        """Validates whether new risk exposure is permissible."""
        if self.is_floor_breached:
            return False, "Account permanently breached trailing floor."
        if self.is_dll_halted:
            return False, "Account halted due to Daily Loss Limit (-$1,000)."
        if self.is_hard_closed:
            return False, "Session closed (post-15:55 EST)."

        if current_dt.tzinfo is None:
            t = current_dt.time()
        else:
            t = current_dt.astimezone(self.est_tz).time()

        if t >= self.auto_flatten_time:
            return False, f"Trading disarmed after {self.auto_flatten_time.strftime('%H:%M')} EST."

        # Buffer check
        distance_to_floor = self.total_equity - self.trailing_floor
        if distance_to_floor < 250.0:  # Minimum safety buffer
            return False, f"Insufficient floor cushion (${distance_to_floor:.2f} < $250.00 min cushion)."

        return True, "Trading allowed."

    def get_state(self) -> BrokerAccountState:
        """Returns snapshot for telemetry serialization."""
        distance_to_floor = max(0.0, self.total_equity - self.trailing_floor)
        distance_to_target = max(0.0, self.target_equity - self.total_equity)
        daily_dd = max(0.0, self.session_open_equity - self.total_equity)
        dll_rem = max(0.0, self.daily_loss_limit - daily_dd)

        status = "ACTIVE"
        if self.is_floor_breached:
            status = "BREACHED_TRAILING_FLOOR"
        elif self.is_dll_halted:
            status = "BREACHED_DAILY_LOSS"
        elif self.is_target_reached:
            status = "PASSED"
        elif self.is_hard_closed:
            status = "SESSION_CLOSED"

        return BrokerAccountState(
            account_id="APEX-50K-LIVE",
            starting_balance=self.starting_balance,
            current_balance=self.current_balance,
            unrealized_pnl=self.unrealized_pnl,
            total_equity=self.total_equity,
            peak_hwm=self.peak_hwm,
            trailing_floor=self.trailing_floor,
            target_equity=self.target_equity,
            floor_locked=self.floor_locked,
            distance_to_floor=distance_to_floor,
            distance_to_target=distance_to_target,
            daily_realized_loss=self.daily_realized_loss,
            daily_unrealized_loss=min(0.0, self.unrealized_pnl),
            daily_loss_limit=self.daily_loss_limit,
            dll_remaining=dll_rem,
            dll_breached=self.is_dll_halted,
            floor_breached=self.is_floor_breached,
            is_halted=self.is_dll_halted or self.is_floor_breached,
            account_status=status,
            open_positions_count=1 if abs(self.unrealized_pnl) > 0.001 else 0,
            active_orders_count=0
        )

    def _recalculate_floor(self) -> None:
        """Recalculates trailing floor with permanent lock at +$100.00."""
        new_floor = self.peak_hwm - self.trailing_drawdown_limit
        if self.lock_at_plus_100:
            permanent_lock_level = self.starting_balance + 100.0
            if new_floor >= permanent_lock_level:
                self.trailing_floor = permanent_lock_level
                if not self.floor_locked:
                    self.floor_locked = True
                    self._log(f"[FLOOR_LOCKED] Trailing floor locked permanently at ${self.trailing_floor:.2f}!")
                return

        self.trailing_floor = max(self.trailing_floor, new_floor)

    def _trigger_flatten(self, reason: str) -> None:
        if self.on_emergency_flatten:
            self.on_emergency_flatten(reason)

    def _log(self, msg: str) -> None:
        self.audit_log.append(f"[{datetime.utcnow().strftime('%H:%M:%S.%f')[:-3]}] {msg}")
