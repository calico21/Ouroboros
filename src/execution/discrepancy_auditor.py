"""
Real-Time Execution Discrepancy & Slippage Audit Engine for AlphaForge.
Tracks microsecond signaling-to-fill latencies, tick-level price execution drift,
slippage attribution (favorable vs adverse), and cumulative friction drag.
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import json
import numpy as np


@dataclass
class DiscrepancyRecord:
    """Detailed forensic audit record for an executed order."""
    order_id: str
    strategy: str
    symbol: str
    direction: str  # "LONG" or "SHORT"
    order_type: str  # "MARKET", "LIMIT", "STOP"
    quantity: int
    expected_price: float
    actual_fill_price: float
    slippage_pts: float
    slippage_ticks: float
    slippage_dollars: float
    attribution: str  # "ADVERSE", "NEUTRAL", "FAVORABLE"
    t_emit: str
    t_ack: str
    t_fill: str
    network_latency_ms: float
    execution_latency_ms: float
    total_latency_ms: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class DiscrepancyAuditor:
    """
    Forensic watchdog for live and paper futures order execution.
    Audits execution latency, validates fill price against theoretical targets,
    and raises alarms if rolling friction drag exceeds institutional tolerances.
    """

    def __init__(
        self,
        symbol: str = "MNQ",
        point_value: float = 2.0,
        tick_size: float = 0.25,
        log_path: str = "reports/telemetry/execution_discrepancies.jsonl",
        friction_threshold_ticks: float = 1.5,
        rolling_window: int = 10
    ):
        self.symbol = symbol
        self.point_value = point_value
        self.tick_size = tick_size
        self.log_path = Path(log_path)
        self.friction_threshold_ticks = friction_threshold_ticks
        self.rolling_window = rolling_window

        # Temporary in-flight submissions: order_id -> dict
        self._pending_orders: Dict[str, Dict[str, Any]] = {}
        # Completed audited records
        self.records: List[DiscrepancyRecord] = []

        # Ensure parent directory exists
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def record_submission(
        self,
        order_id: str,
        symbol: str,
        direction: str,
        order_type: str,
        expected_price: float,
        quantity: int = 1,
        strategy: str = "afternoon_trend_continuation",
        t_emit: Optional[datetime] = None,
        t_ack: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Records initial signal generation and broker transmission acknowledgment."""
        now = datetime.utcnow()
        emit_dt = t_emit or now
        ack_dt = t_ack or now

        self._pending_orders[order_id] = {
            "order_id": order_id,
            "symbol": symbol,
            "direction": direction,
            "order_type": order_type,
            "expected_price": expected_price,
            "quantity": quantity,
            "strategy": strategy,
            "t_emit": emit_dt,
            "t_ack": ack_dt,
            "metadata": metadata or {}
        }

    def record_fill(
        self,
        order_id: str,
        actual_fill_price: float,
        filled_qty: int,
        t_fill: Optional[datetime] = None
    ) -> Optional[DiscrepancyRecord]:
        """
        Processes execution fill, computes latency delta and price discrepancy,
        persists to disk, and checks cumulative friction threshold.
        """
        fill_dt = t_fill or datetime.utcnow()
        submission = self._pending_orders.pop(order_id, None)

        if not submission:
            # Order without submission tracked - synthesize baseline
            submission = {
                "order_id": order_id,
                "symbol": self.symbol,
                "direction": "LONG",
                "order_type": "MARKET",
                "expected_price": actual_fill_price,
                "quantity": filled_qty,
                "strategy": "unknown",
                "t_emit": fill_dt,
                "t_ack": fill_dt,
                "metadata": {}
            }

        t_emit = submission["t_emit"]
        t_ack = submission["t_ack"]

        net_latency_ms = max(0.0, (t_ack - t_emit).total_seconds() * 1000.0)
        exec_latency_ms = max(0.0, (fill_dt - t_ack).total_seconds() * 1000.0)
        tot_latency_ms = max(0.0, (fill_dt - t_emit).total_seconds() * 1000.0)

        expected_price = submission["expected_price"]
        direction = submission["direction"].upper()

        # Slippage calculation convention:
        # For BUY/LONG: actual > expected => adverse (+), actual < expected => favorable (-)
        # For SELL/SHORT: actual < expected => adverse (+), actual > expected => favorable (-)
        if direction in ("LONG", "BUY"):
            slippage_pts = actual_fill_price - expected_price
        else:
            slippage_pts = expected_price - actual_fill_price

        slippage_ticks = round(slippage_pts / self.tick_size, 3)
        slippage_dollars = round(slippage_pts * self.point_value * filled_qty, 2)

        # Attribution
        if abs(slippage_ticks) < 0.05:
            attribution = "NEUTRAL"
        elif slippage_ticks > 0:
            attribution = "ADVERSE"
        else:
            attribution = "FAVORABLE"

        record = DiscrepancyRecord(
            order_id=order_id,
            strategy=submission["strategy"],
            symbol=submission["symbol"],
            direction=direction,
            order_type=submission["order_type"],
            quantity=filled_qty,
            expected_price=expected_price,
            actual_fill_price=actual_fill_price,
            slippage_pts=round(slippage_pts, 3),
            slippage_ticks=slippage_ticks,
            slippage_dollars=slippage_dollars,
            attribution=attribution,
            t_emit=t_emit.isoformat(),
            t_ack=t_ack.isoformat(),
            t_fill=fill_dt.isoformat(),
            network_latency_ms=round(net_latency_ms, 2),
            execution_latency_ms=round(exec_latency_ms, 2),
            total_latency_ms=round(tot_latency_ms, 2),
            metadata=submission["metadata"]
        )

        self.records.append(record)
        self._persist(record)
        return record

    def get_rolling_friction(self, window: Optional[int] = None) -> float:
        """Returns average slippage in ticks over the rolling window."""
        w = window or self.rolling_window
        if not self.records:
            return 0.0
        recent = self.records[-w:]
        return float(np.mean([r.slippage_ticks for r in recent]))

    def check_friction_alert(self) -> Tuple[bool, str]:
        """
        Checks if rolling average slippage exceeds institutional limit.
        Returns: (alert_triggered, message)
        """
        if len(self.records) < min(3, self.rolling_window):
            return False, "Sample size too small for rolling friction check."

        rolling_mean = self.get_rolling_friction()
        if rolling_mean > self.friction_threshold_ticks:
            msg = (
                f"🚨 FRICTION DRAG ALERT: Rolling {len(self.records[-self.rolling_window:])}-trade "
                f"mean slippage is {rolling_mean:.2f} ticks (> {self.friction_threshold_ticks} tick limit). "
                f"Adverse market impact exceeds critical alpha boundary!"
            )
            return True, msg

        return False, f"Friction acceptable ({rolling_mean:.2f} ticks average)."

    def export_daily_summary(self) -> Dict[str, Any]:
        """Generates comprehensive summary diagnostics across all audited executions."""
        if not self.records:
            return {
                "total_orders": 0,
                "mean_slippage_ticks": 0.0,
                "median_slippage_ticks": 0.0,
                "max_slippage_ticks": 0.0,
                "total_dollar_friction": 0.0,
                "p95_latency_ms": 0.0,
                "mean_latency_ms": 0.0,
                "adverse_count": 0,
                "favorable_count": 0,
                "neutral_count": 0,
                "friction_drag_alert": False
            }

        slips = [r.slippage_ticks for r in self.records]
        dollars = [r.slippage_dollars for r in self.records]
        latencies = [r.total_latency_ms for r in self.records]

        adverse = sum(1 for r in self.records if r.attribution == "ADVERSE")
        favorable = sum(1 for r in self.records if r.attribution == "FAVORABLE")
        neutral = sum(1 for r in self.records if r.attribution == "NEUTRAL")

        is_alert, alert_msg = self.check_friction_alert()

        summary = {
            "total_orders": len(self.records),
            "mean_slippage_ticks": round(float(np.mean(slips)), 2),
            "median_slippage_ticks": round(float(np.median(slips)), 2),
            "max_slippage_ticks": round(float(np.max(slips)), 2),
            "total_dollar_friction": round(float(np.sum(dollars)), 2),
            "mean_latency_ms": round(float(np.mean(latencies)), 2),
            "p95_latency_ms": round(float(np.percentile(latencies, 95)), 2),
            "adverse_count": adverse,
            "favorable_count": favorable,
            "neutral_count": neutral,
            "friction_drag_alert": is_alert,
            "alert_message": alert_msg
        }

        # Persist summary
        summary_path = self.log_path.parent / "daily_discrepancy_summary.json"
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2)

        return summary

    def _persist(self, record: DiscrepancyRecord) -> None:
        """Appends JSON line to file."""
        with open(self.log_path, "a") as f:
            f.write(json.dumps(asdict(record)) + "\n")
