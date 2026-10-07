#!/usr/bin/env python3
"""
CLI Audit Runner for AlphaForge.
Executes strategy simulation, calculates forensic diagnostics, runs Monte Carlo,
and renders high-resolution institutional dashboards.
"""
import sys
import argparse
import json
from pathlib import Path
import yaml

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.strategies import discover_strategies, STRATEGY_REGISTRY
from src.data.loader import DataLoader
from src.engine.runner import BacktestRunner
from src.validation.monte_carlo import PropFirmMonteCarloSimulator
from src.visualizer.dashboard_composer import DashboardComposer
from src.visualizer.plot_components import ComponentPlotter


def parse_args():
    parser = argparse.ArgumentParser(description="AlphaForge Quantitative Audit & Forensics Rig")
    parser.add_argument("--strategy", type=str, default="orb_5m_binary",
                        help="Strategy folder name (e.g. orb_5m_binary, vwap_mean_reversion_10am, open_drive_continuation)")
    parser.add_argument("--data", type=str, default="data/processed/mnq_5m.csv",
                        help="Path to historical bar data (CSV or Parquet)")
    parser.add_argument("--timeframe", type=str, default="5m",
                        help="Bar timeframe (e.g. 1m, 5m, 15m)")
    parser.add_argument("--prop-firm", type=str, default="configs/prop_firm/apex_50k_trailing_mtm.yaml",
                        help="Prop firm configuration YAML")
    parser.add_argument("--execution", type=str, default="configs/execution/cme_globex_default.yaml",
                        help="Execution friction YAML")
    parser.add_argument("--instrument", type=str, default="configs/instruments/mnq.yaml",
                        help="Instrument specifications YAML")
    parser.add_argument("--mc-iterations", type=int, default=10000,
                        help="Monte Carlo bootstrap iterations")
    return parser.parse_args()


def print_terminal_summary(strategy_name: str, metrics: dict, mc_res: dict):
    s = metrics.get("summary", {})
    e = metrics.get("excursion", {})
    lt = metrics.get("loss_taxonomy", {})
    ff = metrics.get("friction_frontier", {})
    pf = metrics.get("prop_firm", {})

    print("\n" + "=" * 80)
    print(f"  ALPHAFORGE QUANTITATIVE AUDIT & FORENSIC DIAGNOSTICS REPORT")
    print(f"  Target: CME Globex Intraday Futures // Strategy: {strategy_name.upper()}")
    print("=" * 80)

    print("\n[1. EXECUTIVE PERFORMANCE SUMMARY & STATISTICAL GUARDRAILS]")
    print(f"  Total Trades Executed:   {s.get('total_trades', 0)}")
    print(f"  Sample Significance:     {s.get('sample_significance_status', 'N/A')}")
    if s.get('sample_warning'):
        print(f"  *** WARNING ***          {s.get('sample_warning')}")
    print(f"  Win Rate (Wilson 95% CI):{s.get('win_rate_wilson_ci_str', str(s.get('win_rate_pct', 0)) + '%')}")
    print(f"  Total Realized Net PnL:  ${s.get('total_net_pnl', 0.0):,.2f}")
    print(f"  Gross Profit / Loss:     ${s.get('total_gross_pnl', 0.0):,.2f} / Fees Paid: ${s.get('total_fees_paid', 0.0):,.2f}")
    print(f"  Profit Factor:           {s.get('profit_factor', 0.0)}")
    print(f"  Net Expectancy ($):      ${s.get('expectancy_dollars', 0.0):,.2f} per trade")
    print(f"  Net Expectancy (R Boot): {s.get('expectancy_r_ci_str', str(s.get('expectancy_r', 0)) + 'R')}")
    print(f"  Annualized Sharpe Ratio: {s.get('sharpe_ratio', 0.0)}")
    print(f"  Max Drawdown ($):        ${s.get('max_drawdown_dollars', 0.0):,.2f}")

    print("\n[2. ALPHA QUALITY & EXCURSION FORENSICS]")
    print(f"  Median MFE:              {e.get('median_mfe_r', 0.0)}R")
    print(f"  Median MAE:              {e.get('median_mae_r', 0.0)}R")
    drift = e.get('drift_ratio', 0.0)
    disqualified = e.get('is_alpha_disqualified', False)
    status_str = "DISQUALIFIED (< 1.5x threshold)" if disqualified else "PASSED EDGE (>= 1.5x threshold)"
    print(f"  Directional Drift Ratio: {drift}x  -->  [{status_str}]")
    print(f"  Median Time-to-Peak MFE: {e.get('median_time_to_peak_mfe', 0)} bars")
    print(f"  Excursion Efficiency:    {e.get('excursion_efficiency', 0.0)}")

    print("\n[3. THE ALGORITHMIC DEATH TREE (LOSS TAXONOMY)]")
    breakdown = lt.get("breakdown", {})
    if breakdown:
        for mode, data in breakdown.items():
            print(f"  - {mode:<25}: {data['count']:>3} losses ({data['percentage']:>5.1f}%) | Total Impact: -${data['total_loss_dollars']:>7,.2f}")
    else:
        print("  - Zero losses recorded.")

    print("\n[4. FRICTION FRONTIER & CRITICAL SLIPPAGE]")
    print(f"  Critical Slippage (S*):  {ff.get('critical_slippage_s_star')} ticks")
    print(f"  Viability at 1.5 Ticks:  {'PASS' if ff.get('is_viable') else 'FAIL (Fragile to slippage)'}")

    print("\n[5. PROP-FIRM EVALUATION & MONTE CARLO (10k PATHS)]")
    print(f"  Evaluation Status:       {pf.get('status', 'N/A')}")
    print(f"  Final Account Balance:   ${pf.get('current_balance', 0):,.2f} (Floor: ${pf.get('trailing_floor', 0):,.2f})")
    if mc_res.get("is_suppressed"):
        print(f"  Monte Carlo Status:      {mc_res.get('status')}")
        print(f"  *** MC GATED ***         {mc_res.get('warning')}")
        print(f"  Monte Carlo P(Pass):     SUPPRESSED (N < 15)")
        print(f"  Monte Carlo P(Breach):   SUPPRESSED (N < 15)")
    else:
        print(f"  Monte Carlo P(Pass):     {mc_res.get('prob_pass_pct', 0.0)}% (Target: +$3,000)")
        print(f"  Monte Carlo P(Breach):   {mc_res.get('prob_breach_pct', 0.0)}% (Trailing Floor Breach)")
        print(f"  Median Trades to Pass:   {mc_res.get('median_trades_to_pass', 'N/A')}")
    print("=" * 80 + "\n")


def main():
    args = parse_args()
    discover_strategies()

    if args.strategy not in STRATEGY_REGISTRY:
        print(f"Error: Strategy '{args.strategy}' not found in STRATEGY_REGISTRY.")
        print(f"Available strategies: {list(STRATEGY_REGISTRY.keys())}")
        sys.exit(1)

    strategy_cls = STRATEGY_REGISTRY[args.strategy]
    strategy_instance = strategy_cls()

    # Load data
    data_path = Path(args.data)
    if not data_path.exists():
        print(f"Generating benchmark data at {data_path}...")
        from scripts.ingest_data import generate_cme_intraday_data
        generate_cme_intraday_data(output_processed=data_path)

    loader = DataLoader(data_path=data_path, timeframe=args.timeframe)
    loader.load()

    # Load configs
    with open(args.prop_firm, "r") as f:
        prop_cfg = yaml.safe_load(f)
    with open(args.execution, "r") as f:
        exec_cfg = yaml.safe_load(f)
    with open(args.instrument, "r") as f:
        inst_cfg = yaml.safe_load(f)

    # Initialize BacktestRunner
    runner = BacktestRunner(
        strategy=strategy_instance,
        prop_firm_config=prop_cfg,
        execution_config=exec_cfg,
        instrument_config=inst_cfg
    )

    print(f"Running simulation for {args.strategy} on {args.data}...")
    metrics = runner.run(loader)

    # Run Monte Carlo simulation (10,000 iterations)
    mc_sim = PropFirmMonteCarloSimulator(
        initial_balance=float(prop_cfg.get("initial_balance", 50000.0)),
        trailing_max_dd=float(prop_cfg.get("trailing_max_drawdown", 2500.0)),
        profit_target=float(prop_cfg.get("profit_target", 3000.0)),
        floor_lock_threshold=prop_cfg.get("floor_lock_threshold"),
        lock_floor_offset=prop_cfg.get("lock_floor_offset"),
        iterations=args.mc_iterations
    )
    mc_results = mc_sim.run(runner.simulator.closed_trades)
    metrics["monte_carlo"] = mc_results

    # Print formatted terminal report
    print_terminal_summary(args.strategy, metrics, mc_results)

    # Render Visuals
    print("Rendering institutional dashboards...")
    dashboard_path = Path(f"reports/visuals/dashboards/{args.strategy}_master_dashboard.png")
    DashboardComposer.render_master_dashboard(
        trades=runner.simulator.closed_trades,
        metrics=metrics,
        strategy_name=args.strategy,
        output_path=dashboard_path,
        initial_balance=float(prop_cfg.get("initial_balance", 50000.0)),
        trailing_max_dd=float(prop_cfg.get("trailing_max_drawdown", 2500.0)),
        profit_target=float(prop_cfg.get("profit_target", 3000.0))
    )
    print(f"-> Saved master dashboard: {dashboard_path}")

    # Render dedicated components
    mc_plot = Path(f"reports/visuals/components/{args.strategy}_monte_carlo_cone.png")
    ComponentPlotter.plot_monte_carlo_cone(mc_results, mc_plot)
    print(f"-> Saved Monte Carlo cone: {mc_plot}")

    slip_plot = Path(f"reports/visuals/components/{args.strategy}_slippage_decay.png")
    ComponentPlotter.plot_slippage_decay(metrics["friction_frontier"], slip_plot)
    print(f"-> Saved Slippage decay: {slip_plot}")

    time_plot = Path(f"reports/visuals/components/{args.strategy}_time_decay_excursion.png")
    ComponentPlotter.plot_time_decay_excursion(runner.simulator.closed_trades, time_plot)
    print(f"-> Saved Time-decay excursion: {time_plot}")

    # Save JSON report artifact
    artifact_path = Path(f"reports/artifacts/{args.strategy}_audit_metrics.json")
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    # Filter out non-serializable fields if any
    with open(artifact_path, "w") as f:
        json.dump(metrics, f, indent=2, default=str)
    print(f"-> Saved JSON audit artifact: {artifact_path}")


if __name__ == "__main__":
    main()
