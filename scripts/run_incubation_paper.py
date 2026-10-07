#!/usr/bin/env python3
"""
Forward Incubation & Paper Execution Replay Harness for AlphaForge.
Simulates live bar-by-bar CME Globex execution telemetry, logs structured trade records,
enforces Apex Daily Loss Limit (DLL) circuit breakers (-$1,000 intraday cap),
and generates executive compliance tear-sheets and visuals for prop-firm accounts.
"""
import sys
import os
import argparse
import json
from pathlib import Path
from datetime import datetime, time
from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Ensure workspace root is in python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.strategies import discover_strategies, STRATEGY_REGISTRY
from src.data.loader import DataLoader
from src.core.events import BarEvent, TradeRecord
from src.core.enums import OrderSide, AccountStatus, DrawdownType
from src.engine.fee_models import FeeModel
from src.engine.account_tracker import PropFirmAccountTracker
from src.engine.execution_simulator import ExecutionSimulator
from src.engine.position_sizer import PropFirmPositionSizer


def run_incubation_replay(
    strategy_name: str = "afternoon_trend_continuation",
    data_path: str = "data/processed/mnq_5m.csv",
    account_size: float = 50000.0,
    trailing_dd: float = 2500.0,
    daily_loss_limit: float = 1000.0,
    output_dir: str = "reports/incubation/"
) -> Dict[str, Any]:
    print("=" * 100)
    print("  ALPHAFORGE // INSTITUTIONAL FORWARD INCUBATION & PAPER EXECUTION REPLAY")
    print(f"  Target Strategy: {strategy_name} | Instrument: CME Micro E-mini Nasdaq (MNQ)")
    print(f"  Account Model: Apex 50k Peak MTM (${trailing_dd:,.0f} Trailing DD | DLL: -${daily_loss_limit:,.0f})")
    print("=" * 100)

    out_p = Path(output_dir)
    out_p.mkdir(parents=True, exist_ok=True)

    # 1. Discover and instantiate strategy
    discover_strategies()
    if strategy_name not in STRATEGY_REGISTRY:
        raise ValueError(f"Strategy '{strategy_name}' not found. Available: {list(STRATEGY_REGISTRY.keys())}")

    strategy_cls = STRATEGY_REGISTRY[strategy_name]
    strategy = strategy_cls()

    # 2. Ingest continuous data
    loader = DataLoader(data_path=data_path, timeframe="5m")
    loader.load()

    # 3. Setup execution and accounting components
    inst_cfg = {"symbol": "MNQ", "tick_size": 0.25, "tick_value": 0.50, "point_value": 2.00, "commission_per_side": 0.62}
    exec_cfg = {"slippage_ticks": 1.0, "limit_trade_through_ticks": 1.0, "fill_on_touch": False}
    fee_model = FeeModel.from_config(inst_cfg)

    account = PropFirmAccountTracker(
        initial_balance=account_size,
        trailing_max_dd=trailing_dd,
        profit_target=3000.0,
        drawdown_type=DrawdownType.INTRA_TRADE_PEAK_MTM,
        floor_lock_threshold=2600.0,
        lock_floor_offset=100.0,
        daily_loss_limit=daily_loss_limit,
        max_contracts=6
    )

    simulator = ExecutionSimulator.from_config(exec_cfg, inst_cfg)
    sizer = PropFirmPositionSizer.from_config(exec_cfg, {"max_contracts": 4}, inst_cfg)

    # 4. Stream bars sequentially with live DLL circuit breaker
    telemetry_logs = []
    daily_pnl_tracker: Dict[str, float] = {}
    is_dll_locked = False
    current_date_str = None

    equity_curve = []
    dll_breach_events = []

    for bar in loader.get_bars():
        bar_date = bar.timestamp.strftime("%Y-%m-%d")

        # Session Boundary & Daily Lockout Reset
        if bar_date != current_date_str:
            current_date_str = bar_date
            is_dll_locked = False
            account.check_new_day(bar.timestamp)
            if bar_date not in daily_pnl_tracker:
                daily_pnl_tracker[bar_date] = 0.0

        # Process active trades through simulator
        pre_closed = len(simulator.closed_trades)
        simulator.process_bar(bar, account)

        # Detect trade closing
        if len(simulator.closed_trades) > pre_closed:
            new_trade = simulator.closed_trades[-1]
            new_trade.strategy_name = strategy_name
            account.record_trade_realized(new_trade.net_pnl)
            daily_pnl_tracker[bar_date] += new_trade.net_pnl

            # Emit structured telemetry log
            telemetry_logs.append({
                "trade_id": new_trade.trade_id,
                "strategy": strategy_name,
                "timestamp": new_trade.exit_time.isoformat(),
                "side": new_trade.side.value,
                "contracts": new_trade.contracts,
                "entry_price": new_trade.entry_price,
                "exit_price": new_trade.exit_price,
                "exit_reason": new_trade.exit_reason,
                "mfe_r": round(new_trade.mfe_r, 3),
                "mae_r": round(new_trade.mae_r, 3),
                "realized_r": round(new_trade.r_multiple, 3),
                "gross_pnl": round(new_trade.gross_pnl, 2),
                "net_pnl": round(new_trade.net_pnl, 2),
                "account_balance": round(account.balance, 2),
                "remaining_floor_buffer": round(account.cushion, 2),
                "dll_breached": is_dll_locked
            })

        # Evaluate DLL Circuit Breaker (-$1,000 daily loss)
        current_day_loss = daily_pnl_tracker.get(bar_date, 0.0)
        if current_day_loss <= -daily_loss_limit and not is_dll_locked:
            is_dll_locked = True
            dll_breach_events.append({
                "date": bar_date,
                "timestamp": bar.timestamp.isoformat(),
                "loss": current_day_loss
            })
            # Force liquidations if an active position exists
            if simulator.active_trade is not None:
                simulator._liquidate_active_trade(bar, "DLL_CIRCUIT_BREAKER")

        # Snapshot current equity
        unrealized = 0.0
        if simulator.active_trade is not None:
            at = simulator.active_trade
            pts = (bar.close - at["entry_price"]) if at.get("side") == OrderSide.LONG else (at["entry_price"] - bar.close)
            unrealized = pts * 2.00 * at.get("contracts", 1)

        equity_curve.append({
            "timestamp": bar.timestamp,
            "balance": account.balance,
            "floor": account.floor,
            "hwm": account.high_water_mark,
            "equity": account.balance + unrealized,
            "cushion": account.cushion
        })

        if not account.is_active:
            if account.status == AccountStatus.PASSED:
                print(f"\n[TARGET REACHED] Account Evaluation Passed! Balance: ${account.balance:,.2f} >= Target: ${account.target_balance:,.2f}")
            else:
                print(f"\n[ALERT] Account Terminated: {account.breach_reason}")
            break

        # Alpha evaluation (blocked if daily circuit breaker tripped)
        if is_dll_locked:
            continue

        setup = strategy.on_bar(bar)
        if setup and simulator.active_trade is None and not simulator.pending_orders:
            risk_points = abs(bar.close - setup.stop_loss)
            lots = sizer.calculate_lots(account.cushion, risk_points)
            if lots > 0:
                simulator.submit_setup(setup, bar, lots)

    # 5. Export Structured JSON Telemetry
    telemetry_file = out_p / "paper_trades_telemetry.json"
    with open(telemetry_file, "w") as f:
        json.dump(telemetry_logs, f, indent=2)
    print(f"\n-> Exported structured telemetry logs: {telemetry_file} ({len(telemetry_logs)} trades)")

    # 6. Generate Executive High-Resolution Compliance Visual Tear-Sheet
    report_image = out_p / f"{strategy_name}_incubation_report.png"
    _generate_incubation_visual(
        equity_curve=equity_curve,
        trades=simulator.closed_trades,
        daily_pnl=daily_pnl_tracker,
        dll_limit=daily_loss_limit,
        strategy_name=strategy_name,
        output_path=report_image
    )
    print(f"-> Generated executive incubation tear-sheet visual: {report_image}")

    # 7. Print Executive Incubation Summary
    n_trades = len(simulator.closed_trades)
    wins = [t for t in simulator.closed_trades if t.net_pnl > 0]
    total_net = sum(t.net_pnl for t in simulator.closed_trades)
    wr = (len(wins) / n_trades * 100.0) if n_trades > 0 else 0.0

    print("\n" + "=" * 100)
    print("                     FORWARD INCUBATION REPLAY // EXECUTIVE TEAR-SHEET")
    print("=" * 100)
    print(f"  Total Paper Executions:   {n_trades} trades")
    print(f"  Incubation Win Rate:      {wr:.1f}%")
    print(f"  Net Realized PnL:         ${total_net:,.2f}")
    print(f"  Final Account Balance:    ${account.balance:,.2f} (Floor: ${account.floor:,.2f})")
    print(f"  Floor Lock Activated:     {'YES (Locked at $' + str(account.locked_floor_level) + ')' if account.is_floor_locked else 'NO'}")
    print(f"  DLL Circuit Breakers:     {len(dll_breach_events)} session triggers")
    print(f"  Account Status:           {account.status.value}")
    print("=" * 100 + "\n")

    return {
        "strategy": strategy_name,
        "trades": n_trades,
        "win_rate_pct": round(wr, 2),
        "total_net_pnl": round(total_net, 2),
        "account_balance": round(account.balance, 2),
        "floor": round(account.floor, 2),
        "dll_breaches": len(dll_breach_events),
        "status": account.status.value,
        "report_image": str(report_image)
    }


def _generate_incubation_visual(
    equity_curve: List[Dict[str, Any]],
    trades: List[TradeRecord],
    daily_pnl: Dict[str, float],
    dll_limit: float,
    strategy_name: str,
    output_path: Path
) -> None:
    """Generates an institutional 4-panel compliance tear-sheet visual."""
    fig, axes = plt.subplots(2, 2, figsize=(18, 11), facecolor="#0B0F19")

    # Panel 1: Account Equity vs Peak MTM Trailing Floor
    ax1 = axes[0, 0]
    ax1.set_facecolor("#111827")
    if equity_curve:
        df_eq = pd.DataFrame(equity_curve)
        ax1.plot(df_eq["equity"], label="Account Mark-to-Market ($)", color="#06B6D4", linewidth=1.8)
        ax1.plot(df_eq["hwm"], label="High-Water Mark (HWM)", color="#10B981", linestyle="--", alpha=0.7)
        ax1.plot(df_eq["floor"], label="Trailing Liquidation Floor", color="#EF4444", linewidth=1.5)
        ax1.axhline(52600.0, color="#8B5CF6", linestyle=":", label="Floor Lock Trigger ($52,600)", alpha=0.7)
        ax1.axhline(50100.0, color="#EC4899", linestyle=":", label="Permanent Floor ($50,100)", alpha=0.7)

    ax1.set_title("1. MTM Equity Trajectory vs. Peak Trailing Floor", color="#F3F4F6", fontsize=11, fontweight="bold", pad=8)
    ax1.legend(loc="upper left", facecolor="#1F2937", edgecolor="#374151", labelcolor="#D1D5DB", fontsize=8)
    ax1.grid(True, color="#374151", alpha=0.3, linestyle=":")
    ax1.tick_params(colors="#9CA3AF", labelsize=8)

    # Panel 2: Daily PnL vs Apex Daily Loss Limit (-$1,000)
    ax2 = axes[0, 1]
    ax2.set_facecolor("#111827")
    if daily_pnl:
        days = list(daily_pnl.keys())
        pnls = list(daily_pnl.values())
        colors = ["#10B981" if p >= 0 else "#EF4444" for p in pnls]
        ax2.bar(range(len(days)), pnls, color=colors, width=0.7)
        ax2.axhline(-dll_limit, color="#F59E0B", linestyle="--", linewidth=1.8, label=f"Apex DLL Circuit Breaker (-${dll_limit:,.0f})")

    ax2.set_title("2. Daily PnL vs. Apex DLL Circuit Breaker (-$1,000)", color="#F3F4F6", fontsize=11, fontweight="bold", pad=8)
    ax2.legend(loc="upper right", facecolor="#1F2937", edgecolor="#374151", labelcolor="#D1D5DB", fontsize=8)
    ax2.grid(True, color="#374151", alpha=0.3, linestyle=":")
    ax2.tick_params(colors="#9CA3AF", labelsize=8)

    # Panel 3: Trade Excursion Analysis (MFE vs MAE)
    ax3 = axes[1, 0]
    ax3.set_facecolor("#111827")
    if trades:
        mfes = [t.mfe_r for t in trades]
        maes = [t.mae_r for t in trades]
        wins = [t.net_pnl > 0 for t in trades]
        colors = ["#10B981" if w else "#EF4444" for w in wins]
        ax3.scatter(maes, mfes, c=colors, alpha=0.8, edgecolors="#1F2937", s=45)
        # 1:1 Reference Line
        max_r = max(max(mfes, default=2.0), max(maes, default=2.0))
        ax3.plot([0, max_r], [0, max_r], color="#6B7280", linestyle="--", label="Symmetric Boundary")
        ax3.axhline(0.80, color="#F59E0B", linestyle=":", label="Trapped Zone (MFE >= 0.80R)")

    ax3.set_title("3. Excursion Space: MFE vs. MAE (R-Normalized)", color="#F3F4F6", fontsize=11, fontweight="bold", pad=8)
    ax3.set_xlabel("Adverse Excursion (MAE in R)", color="#9CA3AF", fontsize=8)
    ax3.set_ylabel("Favorable Excursion (MFE in R)", color="#9CA3AF", fontsize=8)
    ax3.legend(loc="upper left", facecolor="#1F2937", edgecolor="#374151", labelcolor="#D1D5DB", fontsize=8)
    ax3.grid(True, color="#374151", alpha=0.3, linestyle=":")
    ax3.tick_params(colors="#9CA3AF", labelsize=8)

    # Panel 4: Realized R-Multiple Payoff Distribution
    ax4 = axes[1, 1]
    ax4.set_facecolor("#111827")
    if trades:
        r_mults = [t.r_multiple for t in trades]
        ax4.hist(r_mults, bins=16, color="#06B6D4", edgecolor="#1E293B", alpha=0.85)
        med_r = float(np.median(r_mults))
        ax4.axvline(med_r, color="#10B981", linestyle="--", linewidth=1.8, label=f"Median Realized R: {med_r:+.2f}R")
        ax4.axvline(0.0, color="#9CA3AF", linestyle=":", linewidth=1.0)

    ax4.set_title("4. Realized R-Multiple Distribution", color="#F3F4F6", fontsize=11, fontweight="bold", pad=8)
    ax4.set_xlabel("Realized R-Multiple", color="#9CA3AF", fontsize=8)
    ax4.set_ylabel("Frequency", color="#9CA3AF", fontsize=8)
    ax4.legend(loc="upper right", facecolor="#1F2937", edgecolor="#374151", labelcolor="#D1D5DB", fontsize=8)
    ax4.grid(True, color="#374151", alpha=0.3, linestyle=":")
    ax4.tick_params(colors="#9CA3AF", labelsize=8)

    plt.suptitle(f"ALPHAFORGE // FORWARD INCUBATION TEAR-SHEET: {strategy_name.upper()}", color="#F9FAFB", fontsize=14, fontweight="bold", y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.savefig(output_path, dpi=200, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close()


def main():
    parser = argparse.ArgumentParser(description="AlphaForge Forward Incubation & Paper Execution Replay Harness")
    parser.add_argument("--strategy", type=str, default="afternoon_trend_continuation", help="Strategy to incubate")
    parser.add_argument("--data", type=str, default="data/processed/mnq_5m.csv", help="Continuous bar dataset path")
    parser.add_argument("--account-size", type=float, default=50000.0, help="Initial prop account balance ($)")
    parser.add_argument("--trailing-dd", type=float, default=2500.0, help="Peak-Unrealized Trailing Max DD ($)")
    parser.add_argument("--daily-loss-limit", type=float, default=1000.0, help="Daily Loss Limit circuit breaker ($)")
    parser.add_argument("--output-dir", type=str, default="reports/incubation/", help="Output directory for telemetry & visuals")

    args = parser.parse_args()

    run_incubation_replay(
        strategy_name=args.strategy,
        data_path=args.data,
        account_size=args.account_size,
        trailing_dd=args.trailing_dd,
        daily_loss_limit=args.daily_loss_limit,
        output_dir=args.output_dir
    )


if __name__ == "__main__":
    main()
