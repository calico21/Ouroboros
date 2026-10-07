"""
Unit tests for Real-Time Execution Discrepancy & Slippage Audit Engine.
Validates latency tracking, signed slippage calculations, attribution,
and rolling friction drag alerts.
"""
from datetime import datetime, timedelta
import tempfile
import pytest

from src.execution.discrepancy_auditor import DiscrepancyAuditor


def test_discrepancy_auditor_latency_and_slippage_calculation():
    with tempfile.NamedTemporaryFile(suffix=".jsonl") as tmp:
        auditor = DiscrepancyAuditor(
            symbol="MNQ",
            point_value=2.0,
            tick_size=0.25,
            log_path=tmp.name,
            friction_threshold_ticks=1.5
        )

        t_emit = datetime(2025, 10, 15, 13, 30, 0, 0)
        t_ack = t_emit + timedelta(milliseconds=12.5)
        t_fill = t_ack + timedelta(milliseconds=7.5)

        # Buyer expecting 20250.00, fills at 20250.50 (+0.50 pts = +2.0 ticks adverse)
        auditor.record_submission(
            order_id="ORD-101",
            symbol="MNQ",
            direction="LONG",
            order_type="MARKET",
            expected_price=20250.00,
            quantity=1,
            strategy="afternoon_trend_continuation",
            t_emit=t_emit,
            t_ack=t_ack
        )

        record = auditor.record_fill(
            order_id="ORD-101",
            actual_fill_price=20250.50,
            filled_qty=1,
            t_fill=t_fill
        )

        assert record is not None
        assert record.network_latency_ms == pytest.approx(12.5, rel=1e-2)
        assert record.execution_latency_ms == pytest.approx(7.5, rel=1e-2)
        assert record.total_latency_ms == pytest.approx(20.0, rel=1e-2)

        # Slippage: 20250.50 - 20250.00 = +0.50 pts
        assert record.slippage_pts == pytest.approx(0.50)
        assert record.slippage_ticks == pytest.approx(2.0)
        # Dollar friction: 0.50 * $2.0 * 1 = $1.00
        assert record.slippage_dollars == pytest.approx(1.00)
        assert record.attribution == "ADVERSE"


def test_discrepancy_auditor_favorable_price_improvement():
    with tempfile.NamedTemporaryFile(suffix=".jsonl") as tmp:
        auditor = DiscrepancyAuditor(
            symbol="MNQ",
            point_value=2.0,
            tick_size=0.25,
            log_path=tmp.name
        )

        t0 = datetime(2025, 10, 15, 14, 0, 0)

        # Short seller expecting 20200.00, fills at 20200.25 (+1 tick favorable price improvement)
        auditor.record_submission(
            order_id="ORD-102",
            symbol="MNQ",
            direction="SHORT",
            order_type="LIMIT",
            expected_price=20200.00,
            quantity=2,
            strategy="afternoon_trend_continuation",
            t_emit=t0,
            t_ack=t0 + timedelta(milliseconds=5.0)
        )

        record = auditor.record_fill(
            order_id="ORD-102",
            actual_fill_price=20200.25,
            filled_qty=2,
            t_fill=t0 + timedelta(milliseconds=10.0)
        )

        assert record.slippage_pts == pytest.approx(-0.25)
        assert record.slippage_ticks == pytest.approx(-1.0)
        assert record.attribution == "FAVORABLE"
        assert record.slippage_dollars == pytest.approx(-1.00)  # Favorable savings


def test_discrepancy_auditor_rolling_friction_alert():
    with tempfile.NamedTemporaryFile(suffix=".jsonl") as tmp:
        auditor = DiscrepancyAuditor(
            symbol="MNQ",
            log_path=tmp.name,
            friction_threshold_ticks=1.5,
            rolling_window=5
        )

        t = datetime(2025, 10, 15, 14, 0, 0)

        # Insert 5 trades with 2.0 ticks adverse slippage each (> 1.5 tick limit)
        for i in range(5):
            oid = f"ORD-HEAVY-{i}"
            auditor.record_submission(
                order_id=oid,
                symbol="MNQ",
                direction="LONG",
                order_type="MARKET",
                expected_price=20000.0,
                quantity=1,
                t_emit=t,
                t_ack=t
            )
            auditor.record_fill(
                order_id=oid,
                actual_fill_price=20000.50,  # +2.0 ticks
                filled_qty=1,
                t_fill=t + timedelta(milliseconds=15.0)
            )

        is_alert, msg = auditor.check_friction_alert()
        assert is_alert is True
        assert "FRICTION DRAG ALERT" in msg

        summary = auditor.export_daily_summary()
        assert summary["total_orders"] == 5
        assert summary["mean_slippage_ticks"] == pytest.approx(2.0)
        assert summary["friction_drag_alert"] is True
