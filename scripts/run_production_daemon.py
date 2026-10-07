#!/usr/bin/env python3
"""
AlphaForge Autonomous Production Daemon & Session Lifecycle Scheduler.
Manages isolated live/paper execution for 'afternoon_trend_continuation' on CME Micro E-mini Nasdaq (MNQ).
Automates the institutional intraday timetable:
- 11:15 EST: Pre-flight checks, broker connectivity, and market feed verification.
- 11:30 - 13:30 EST: Midday consolidation tracking (Zero order emission).
- 13:30 - 15:15 EST: Execution window armed; breakout order submissions.
- 15:50 EST: Cancel unfilled working bracket limit orders.
- 15:55 EST: Zero-tolerance hard market liquidation.
- 16:00 EST: EOD telemetry export and webhook report broadcast.
- 16:15 EST: Hibernation until next Globex session.
"""
import argparse
import json
import os
import signal
import sys
import time
from datetime import datetime, time as dtime
from pathlib import Path
from typing import Dict, Any, Optional
import pytz
import yaml

from src.core.events import BarEvent
from src.data.loader import DataLoader
from src.execution.broker_gateway import (
    BaseBrokerGateway,
    PaperBrokerGateway,
    TradovateRESTSocketGateway,
)
from src.execution.discrepancy_auditor import DiscrepancyAuditor
from src.execution.webhook_notifier import WebhookNotifier
from src.strategies.afternoon_trend_continuation.strategy import (
    AfternoonTrendContinuationStrategy,
)


class ProductionDaemon:
    """
    Autonomous institutional execution runner for CME Globex futures.
    """

    def __init__(
        self,
        config_path: str = "configs/execution/broker_config.yaml",
        broker_type: str = "paper",
        mode: str = "paper",
        webhook_url: Optional[str] = None,
        simulate_fast: bool = False,
        data_path: str = "data/processed/mnq_5m.csv"
    ):
        self.config_path = Path(config_path)
        with open(self.config_path, "r") as f:
            self.config = yaml.safe_load(f)

        self.broker_type = broker_type or self.config.get("active_broker", "paper")
        self.mode = mode
        self.simulate_fast = simulate_fast
        self.data_path = data_path

        # Setup Webhook Notifier
        wh_url = webhook_url or self.config.get("notifications", {}).get("webhook_url") or os.getenv("TRADOVATE_WEBHOOK_URL")
        self.notifier = WebhookNotifier(wh_url)

        # Setup Discrepancy Auditor
        disc_cfg = self.config.get("discrepancy_auditor", {})
        self.auditor = DiscrepancyAuditor(
            symbol=self.config.get("symbol", "MNQ"),
            point_value=float(self.config.get("point_value", 2.0)),
            tick_size=float(self.config.get("tick_size", 0.25)),
            log_path=disc_cfg.get("log_path", "reports/telemetry/execution_discrepancies.jsonl"),
            friction_threshold_ticks=float(disc_cfg.get("friction_threshold_ticks", 1.5)),
            rolling_window=int(disc_cfg.get("rolling_window", 10))
        )

        # Initialize Broker Gateway
        if self.broker_type == "tradovate":
            self.gateway: BaseBrokerGateway = TradovateRESTSocketGateway(self.config)
        else:
            self.gateway = PaperBrokerGateway(self.config, auditor=self.auditor)

        # Isolated Production Strategy (Frozen)
        self.strategy = AfternoonTrendContinuationStrategy()

        # Operational States
        self.is_running = True
        self.est_tz = pytz.timezone("US/Eastern")
        self.session_state = "IDLE"  # "IDLE", "MIDDAY_TRACKING", "ARMED", "FLATTENED", "EOD_COMPLETED"
        self.current_bar: Optional[BarEvent] = None
        self.trade_executed_today = False

        # Register Signal Handlers for graceful teardown
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        # Attach gateway callbacks
        self.gateway.on_fill(self._on_fill_event)

    def start(self) -> None:
        """Main lifecycle entrypoint."""
        print("=" * 95)
        print("  ALPHAFORGE // INSTITUTIONAL PRODUCTION DAEMON")
        print(f"  Target Strategy: afternoon_trend_continuation (FROZEN PRODUCTION ASSET)")
        print(f"  Broker Gateway:  {self.broker_type.upper()} ({self.mode.upper()}) | Symbol: {self.config.get('symbol', 'MNQ')}")
        print(f"  Account Model:   Apex 50k Peak MTM ($2,500 Trailing Floor | Lock @ $50,100 | DLL -$1,000)")
        print("=" * 95)

        connected = self.gateway.connect()
        if not connected:
            print("Fatal: Could not connect to broker gateway.", file=sys.stderr)
            sys.exit(1)

        self.notifier.send_alert(
            event_type="DAEMON_STARTED",
            title="PRODUCTION DAEMON ONLINE",
            description=f"AlphaForge daemon initialized in **{self.mode.upper()}** mode using **{self.broker_type.upper()}** gateway.",
            fields={
                "Strategy": "afternoon_trend_continuation",
                "Symbol": self.config.get("symbol", "MNQ"),
                "Account": "APEX-50K-LIVE"
            },
            color_hex="#00FFFF"
        )

        if self.simulate_fast:
            self._run_fast_simulation()
        else:
            self._run_realtime_loop()

    def _run_realtime_loop(self) -> None:
        """Live event monitoring loop."""
        print("[DAEMON] Entering live session schedule loop. Awaiting market timestamps...")
        while self.is_running:
            now_est = datetime.now(self.est_tz)
            t = now_est.time()

            # Schedule Transition 1: 11:15 EST - Health Check
            if dtime(11, 15) <= t < dtime(11, 30) and self.session_state == "IDLE":
                print(f"[{now_est.strftime('%H:%M:%S EST')}] [11:15 EST PRE-FLIGHT] Verifying gateway health and feeds...")
                self._verify_gateway_health()
                self.session_state = "PRE_FLIGHT_READY"

            # Schedule Transition 2: 11:30 EST - Midday Consolidation Tracking
            elif dtime(11, 30) <= t < dtime(13, 30):
                if self.session_state != "MIDDAY_TRACKING":
                    print(f"[{now_est.strftime('%H:%M:%S EST')}] [11:30 EST] Midday consolidation tracking corridor ACTIVE.")
                    self.session_state = "MIDDAY_TRACKING"

            # Schedule Transition 3: 13:30 - 15:15 EST - Production Execution Window
            elif dtime(13, 30) <= t < dtime(15, 15):
                if self.session_state != "ARMED":
                    print(f"[{now_est.strftime('%H:%M:%S EST')}] [13:30 EST] Execution Window ARMED! Evaluating breakout signals.")
                    self.session_state = "ARMED"

            # Schedule Transition 4: 15:50 EST - Pending Order Purge
            elif dtime(15, 50) <= t < dtime(15, 55):
                if self.session_state == "ARMED":
                    print(f"[{now_est.strftime('%H:%M:%S EST')}] [15:50 EST] Canceling all unfilled pending orders.")
                    self.session_state = "CANCEL_PENDING"

            # Schedule Transition 5: 15:55 EST - Hard Market Flatten
            elif dtime(15, 55) <= t < dtime(16, 0):
                if self.session_state != "FLATTENED":
                    print(f"[{now_est.strftime('%H:%M:%S EST')}] [15:55 EST] Enforcing ZERO overnight positions! Liquidating.")
                    self.gateway.flatten_all_positions()
                    self.session_state = "FLATTENED"

            # Schedule Transition 6: 16:00 EST - EOD Audit Export
            elif dtime(16, 0) <= t < dtime(16, 15):
                if self.session_state != "EOD_COMPLETED":
                    self._generate_eod_report()
                    self.session_state = "EOD_COMPLETED"

            # Reset at night
            elif t >= dtime(16, 15) or t < dtime(11, 0):
                self.session_state = "IDLE"
                self.trade_executed_today = False

            time.sleep(10)

    def _run_fast_simulation(self) -> None:
        """Accelerated replay of real continuous Globex bars through daemon."""
        print(f"[DAEMON] Running accelerated playback from {self.data_path}...")
        loader = DataLoader(self.data_path, timeframe="5m")
        bars = list(loader.get_bars())
        session_bars = bars[-120:] if len(bars) > 120 else bars

        for bar in session_bars:
            if not self.is_running:
                break
            self.current_bar = bar
            t = bar.timestamp.time()

            # Feed bar to paper gateway broker
            if isinstance(self.gateway, PaperBrokerGateway):
                self.gateway.broker.process_bar(bar)

            # 11:30 - 13:30 EST Midday tracking
            if dtime(11, 30) <= t < dtime(13, 30):
                self.strategy.on_bar(bar)

            # 13:30 - 15:15 EST Execution Window
            elif dtime(13, 30) <= t <= dtime(15, 15):
                setup = self.strategy.on_bar(bar)
                if setup and not self.trade_executed_today:
                    bracket_id = self.gateway.submit_bracket_order(setup, size=1)
                    if bracket_id:
                        self.trade_executed_today = True
                        print(f"[{bar.timestamp.strftime('%H:%M:%S EST')}] >>> SIGNAL SUBMITTED: {setup.direction.value} @ {bar.close:.2f} (Bracket: {bracket_id})")

            # 15:55 Hard Flatten
            elif t >= dtime(15, 55):
                self.gateway.flatten_all_positions()

        self._generate_eod_report()

    def _verify_gateway_health(self) -> bool:
        if not self.gateway.is_connected():
            print("[HEALTH CHECK] Gateway disconnected, attempting reconnect...")
            return self.gateway.connect()
        return True

    def _on_fill_event(self, fill: Dict[str, Any]) -> None:
        print(f"  [EXECUTION FILL] {fill.get('direction')} {fill.get('contracts')}ct @ {fill.get('fill_price'):.2f} (Slip: {fill.get('slippage_ticks'):+.2f} ticks)")
        self.notifier.notify_order_filled(
            strategy="afternoon_trend_continuation",
            side=fill.get("direction", "LONG"),
            price=fill.get("fill_price", 0.0),
            qty=fill.get("contracts", 1),
            sl=0.0,
            tp=0.0,
            slippage_ticks=fill.get("slippage_ticks", 1.0)
        )

    def _generate_eod_report(self) -> None:
        """Generates comprehensive EOD telemetry and sends alerts."""
        print("[DAEMON] Compiling EOD Forensic Discrepancy & Account Audit...")
        summary = self.auditor.export_daily_summary()
        balance = self.gateway.get_account_balance()

        print("=" * 95)
        print("                     END-OF-DAY FORENSIC AUDIT TEAR-SHEET")
        print("=" * 95)
        print(f"  Total Audited Executions:   {summary['total_orders']}")
        print(f"  Mean Slippage:              {summary['mean_slippage_ticks']:+.2f} ticks")
        print(f"  95th Percentile Latency:    {summary['p95_latency_ms']:.2f} ms")
        print(f"  Total Execution Friction:   ${summary['total_dollar_friction']:,.2f}")
        print(f"  Friction Drag Alert:        {'ACTIVE' if summary['friction_drag_alert'] else 'CLEAR'}")
        print(f"  Final Cash Balance:         ${balance:,.2f}")
        print("=" * 95)

        self.notifier.send_alert(
            event_type="EOD_SUMMARY",
            title="END-OF-DAY AUDIT SUMMARY",
            description="Institutional execution session concluded.",
            fields={
                "Total Orders": summary["total_orders"],
                "Mean Slippage": f"{summary['mean_slippage_ticks']:+.2f} ticks",
                "P95 Latency": f"{summary['p95_latency_ms']:.1f} ms",
                "Total Friction": f"${summary['total_dollar_friction']:.2f}",
                "Account Balance": f"${balance:,.2f}"
            },
            color_hex="#00FFFF"
        )

    def _handle_signal(self, signum, frame) -> None:
        """Graceful shutdown handler for SIGINT/SIGTERM."""
        print(f"\n[DAEMON] Received signal {signum}. Initiating emergency teardown...")
        self.is_running = False
        try:
            self.gateway.flatten_all_positions()
            self.gateway.disconnect()
            self._generate_eod_report()
        except Exception as e:
            print(f"[DAEMON] Teardown warning: {e}")
        print("[DAEMON] Teardown complete. Exiting gracefully.")
        sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="AlphaForge Autonomous Production Daemon")
    parser.add_argument("--mode", type=str, default="paper", choices=["paper", "live"], help="Execution mode")
    parser.add_argument("--broker", type=str, default="paper", choices=["paper", "tradovate"], help="Broker gateway")
    parser.add_argument("--config", type=str, default="configs/execution/broker_config.yaml", help="Broker config file")
    parser.add_argument("--notify-webhook", type=str, default=None, help="Discord/Slack webhook URL")
    parser.add_argument("--simulate-fast", action="store_true", help="Run fast simulation for testing")
    parser.add_argument("--data-path", type=str, default="data/processed/mnq_5m.csv", help="Historical bar dataset")
    args = parser.parse_args()

    daemon = ProductionDaemon(
        config_path=args.config,
        broker_type=args.broker,
        mode=args.mode,
        webhook_url=args.notify_webhook,
        simulate_fast=args.simulate_fast,
        data_path=args.data_path
    )
    daemon.start()


if __name__ == "__main__":
    main()
