#!/usr/bin/env python3
"""
AlphaForge Live / Paper Execution Harness & Real-Time Telemetry Runner.
Simulates live asynchronous broker execution with tick/bar feeds,
real-time Apex Peak-Unrealized MTM ratchets, bracket order state machines,
and WebSocket-ready JSON telemetry streaming.
"""
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
import pytz

from src.data.loader import DataLoader
from src.execution.paper_broker import PaperBroker
from src.execution.models import LiveTelemetryPayload
from src.strategies import discover_strategies
from src.core.events import BarEvent


def main():
    parser = argparse.ArgumentParser(description="AlphaForge Live/Paper Trading Harness")
    parser.add_argument("--strategy", type=str, default="afternoon_trend_continuation", help="Target strategy name")
    parser.add_argument("--speed", type=float, default=0.05, help="Seconds delay between live bar stream ticks")
    parser.add_argument("--max-bars", type=int, default=150, help="Maximum bars to simulate in session")
    parser.add_argument("--data-path", type=str, default="data/processed/mnq_5m.csv", help="Path to continuous data")
    parser.add_argument("--emit-json", action="store_true", help="Emit raw JSON lines for WebSocket bridge")
    args = parser.parse_args()

    strategies = discover_strategies()
    if args.strategy not in strategies:
        print(f"Error: Unknown strategy '{args.strategy}'. Available: {list(strategies.keys())}", file=sys.stderr)
        sys.exit(1)

    strategy_cls = strategies[args.strategy]
    strategy_instance = strategy_cls()

    # Telemetry callback
    def on_telemetry(payload: LiveTelemetryPayload):
        if args.emit_json:
            print(json.dumps(payload.model_dump(), default=str), flush=True)
        else:
            acc = payload.account
            pos = payload.position
            print(
                f"[{payload.timestamp}] Bal: ${acc.current_balance:,.2f} | "
                f"Eq: ${acc.total_equity:,.2f} | Peak: ${acc.peak_hwm:,.2f} | "
                f"Floor: ${acc.trailing_floor:,.2f} (Buf: ${acc.distance_to_floor:,.2f}) | "
                f"Pos: {pos.side} {pos.contracts}ct (Unreal: ${pos.unrealized_pnl:+.2f}) | "
                f"Status: {acc.account_status}",
                flush=True
            )

    broker = PaperBroker(
        symbol="MNQ",
        starting_balance=50000.0,
        on_telemetry=on_telemetry
    )
    broker.start(strategy_name=args.strategy)

    if not args.emit_json:
        print("=" * 90)
        print(f"  ALPHAFORGE // LIVE PAPER EXECUTION HARNESS ACTIVE")
        print(f"  Strategy: {args.strategy} | Symbol: MNQ | Floor Model: Apex 50k Peak MTM")
        print("=" * 90)

    # Load recent dataset bars for live streaming
    loader = DataLoader(args.data_path, symbol="MNQ", timeframe="5m")
    bars = list(loader.get_bars())
    if not bars:
        print("Error: No data bars found.", file=sys.stderr)
        sys.exit(1)

    # Stream recent bars to simulate real-time live trading
    stream_bars = bars[-args.max_bars:]
    bar_count = 0

    try:
        for bar in stream_bars:
            bar_count += 1
            broker.current_price = bar.close
            broker.current_timestamp = bar.timestamp

            # 1. Feed bar to broker for mark-to-market updates & active order fills
            broker.process_bar(bar)

            # 2. Check if strategy produces alpha trade signal
            setup = strategy_instance.on_bar(bar)
            if setup:
                bracket = broker.submit_signal(setup)
                if bracket and not args.emit_json:
                    print(f"  >>> [SIGNAL SUBMITTED] {setup.direction.value} @ {bar.close:.2f} | SL: {setup.stop_loss:.2f} | TP: {setup.take_profit:.2f}")

            # Pace execution if speed is specified
            if args.speed > 0:
                time.sleep(args.speed)

            # If breached or halted, stop simulation
            acc_state = broker.risk_sentinel.get_state()
            if acc_state.is_halted or acc_state.floor_breached:
                break

    except KeyboardInterrupt:
        if not args.emit_json:
            print("\nOperator interrupted execution. Initiating graceful shutdown...")
    finally:
        broker.stop()
        if not args.emit_json:
            print("=" * 90)
            print("  LIVE EXECUTION SESSION TERMINATED")
            final_acc = broker.risk_sentinel.get_state()
            print(f"  Final Equity: ${final_acc.total_equity:,.2f} | High-Water Mark: ${final_acc.peak_hwm:,.2f}")
            print(f"  Trailing Floor: ${final_acc.trailing_floor:,.2f} | Account Status: {final_acc.account_status}")
            print("=" * 90)


if __name__ == "__main__":
    main()
