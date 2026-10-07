#!/usr/bin/env python3
"""
Benchmark Zoo for AlphaForge.
Executes standardized backtests across all auto-discovered strategies in src/strategies/
and produces an institutional comparative leaderboard ranked by Drift Ratio, Expectancy (R), and P(Pass).
Incorporates statistical sample significance gating and Wilson score confidence intervals.
"""
import sys
import json
from pathlib import Path
import yaml
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.strategies import discover_strategies, STRATEGY_REGISTRY
from src.data.loader import DataLoader
from src.engine.runner import BacktestRunner
from src.validation.monte_carlo import PropFirmMonteCarloSimulator


def run_zoo_benchmarks(
    data_path: str = "data/processed/mnq_5m.csv",
    prop_firm_cfg_path: str = "configs/prop_firm/apex_50k_trailing_mtm.yaml",
    execution_cfg_path: str = "configs/execution/cme_globex_default.yaml",
    instrument_cfg_path: str = "configs/instruments/mnq.yaml",
    timeframe: str = "5m"
):
    discover_strategies()
    print(f"\nDiscovered {len(STRATEGY_REGISTRY)} strategies: {list(STRATEGY_REGISTRY.keys())}")

    data_p = Path(data_path)
    if not data_p.exists():
        from scripts.ingest_data import generate_cme_intraday_data
        generate_cme_intraday_data(output_processed=data_p)

    loader = DataLoader(data_path=data_p, timeframe=timeframe)
    loader.load()

    with open(prop_firm_cfg_path, "r") as f:
        prop_cfg = yaml.safe_load(f)
    with open(execution_cfg_path, "r") as f:
        exec_cfg = yaml.safe_load(f)
    with open(instrument_cfg_path, "r") as f:
        inst_cfg = yaml.safe_load(f)

    leaderboard = []

    for name, strat_cls in sorted(STRATEGY_REGISTRY.items()):
        print(f"Auditing strategy: {name}...")
        strategy_instance = strat_cls()

        runner = BacktestRunner(
            strategy=strategy_instance,
            prop_firm_config=prop_cfg,
            execution_config=exec_cfg,
            instrument_config=inst_cfg
        )
        metrics = runner.run(loader)

        # 10k Monte Carlo with N<15 gating
        mc_sim = PropFirmMonteCarloSimulator(
            initial_balance=float(prop_cfg.get("initial_balance", 50000.0)),
            trailing_max_dd=float(prop_cfg.get("trailing_max_drawdown", 2500.0)),
            profit_target=float(prop_cfg.get("profit_target", 3000.0)),
            iterations=10000
        )
        mc_res = mc_sim.run(runner.simulator.closed_trades)
        metrics["monte_carlo"] = mc_res

        # Save artifact for digest generator
        artifact_path = Path(f"reports/artifacts/{name}_audit_metrics.json")
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        with open(artifact_path, "w") as f:
            json.dump(metrics, f, indent=2, default=str)

        s = metrics.get("summary", {})
        e = metrics.get("excursion", {})
        ff = metrics.get("friction_frontier", {})

        trades = s.get("total_trades", 0)
        drift = e.get("drift_ratio", 0.0)
        exp_r = s.get("expectancy_r", 0.0)
        exp_r_se = s.get("expectancy_r_stderr", 0.0)
        wr = s.get("win_rate_pct", 0.0)
        wr_ci = s.get("win_rate_wilson_ci95", [0.0, 0.0])
        pf = s.get("profit_factor", 0.0)
        net_pnl = s.get("total_net_pnl", 0.0)
        s_star = ff.get("critical_slippage_s_star", 0.0)

        # Monte Carlo gating
        if mc_res.get("is_suppressed"):
            p_pass_str = "GATED (N<15)"
            p_breach_str = "GATED (N<15)"
        else:
            p_pass_str = f"{mc_res.get('prob_pass_pct', 0.0):.1f}%"
            p_breach_str = f"{mc_res.get('prob_breach_pct', 0.0):.1f}%"

        # Statistical sample gate & status verdict
        if trades < 30:
            status = f"INSUFFICIENT_SAMPLE (N={trades}/30)"
        elif drift < 1.50:
            status = "DISQUALIFIED (DRIFT < 1.5x)"
        elif exp_r <= 0:
            status = "REJECTED_ZERO_EDGE"
        elif str(s_star) != "> 3.0" and float(s_star) < 1.0:
            status = "REJECTED_COST_SENSITIVE"
        else:
            status = "APPROVED_FOR_INCUBATION"

        leaderboard.append({
            "Strategy": name,
            "Trades": trades,
            "Win Rate (95% CI)": f"{wr:.1f}% [{wr_ci[0]:.1f}-{wr_ci[1]:.1f}%]",
            "Net PnL ($)": round(net_pnl, 2),
            "Profit Factor": pf,
            "Expectancy (R ± SE)": f"{exp_r:+.3f} ± {exp_r_se:.3f}",
            "Drift Ratio (x)": drift,
            "P(Pass)": p_pass_str,
            "P(Breach)": p_breach_str,
            "Crit Slip (S*)": str(s_star),
            "Status": status
        })

    # 2. Run Blended Multi-Strategy Portfolio Execution
    if "orb_5m_binary" in STRATEGY_REGISTRY and "afternoon_trend_continuation" in STRATEGY_REGISTRY:
        print("\nAuditing multi-strategy portfolio: portfolio_blended (ORB 5M + PM Trend)...")
        from src.engine.portfolio import PortfolioRunner
        port_runner = PortfolioRunner(
            strategies=[
                STRATEGY_REGISTRY["orb_5m_binary"](),
                STRATEGY_REGISTRY["afternoon_trend_continuation"]()
            ],
            prop_firm_config=prop_cfg,
            execution_config=exec_cfg,
            instrument_config=inst_cfg,
            max_portfolio_contracts=6
        )
        port_metrics = port_runner.run(loader)

        artifact_path = Path("reports/artifacts/portfolio_blended_audit_metrics.json")
        with open(artifact_path, "w") as f:
            json.dump(port_metrics, f, indent=2, default=str)

        ps = port_metrics.get("summary", {})
        pe = port_metrics.get("excursion", {})
        pff = port_metrics.get("friction_frontier", {})
        pmc = port_metrics.get("monte_carlo", {})

        p_trades = ps.get("total_trades", 0)
        p_drift = pe.get("drift_ratio", 0.0)
        p_exp_r = ps.get("expectancy_r", 0.0)
        p_exp_se = ps.get("expectancy_r_stderr", 0.0)
        p_wr = ps.get("win_rate_pct", 0.0)
        p_wr_ci = ps.get("win_rate_wilson_ci95", [0.0, 0.0])
        p_pf = ps.get("profit_factor", 0.0)
        p_net = ps.get("total_net_pnl", 0.0)
        p_s_star = pff.get("critical_slippage_s_star", "> 3.0")

        if pmc.get("is_suppressed"):
            p_pass_str = "GATED (N<15)"
            p_breach_str = "GATED (N<15)"
        else:
            p_pass_str = f"{pmc.get('prob_pass_pct', 0.0):.1f}%"
            p_breach_str = f"{pmc.get('prob_breach_pct', 0.0):.1f}%"

        if p_trades < 30:
            p_status = f"INSUFFICIENT_SAMPLE (N={p_trades}/30)"
        elif p_drift < 1.50:
            p_status = "DISQUALIFIED (DRIFT < 1.5x)"
        elif p_exp_r <= 0:
            p_status = "REJECTED_ZERO_EDGE"
        elif str(p_s_star) != "> 3.0" and float(p_s_star) < 1.0:
            p_status = "REJECTED_COST_SENSITIVE"
        else:
            p_status = "APPROVED_FOR_INCUBATION"

        leaderboard.append({
            "Strategy": "portfolio_blended",
            "Trades": p_trades,
            "Win Rate (95% CI)": f"{p_wr:.1f}% [{p_wr_ci[0]:.1f}-{p_wr_ci[1]:.1f}%]",
            "Net PnL ($)": round(p_net, 2),
            "Profit Factor": p_pf,
            "Expectancy (R ± SE)": f"{p_exp_r:+.3f} ± {p_exp_se:.3f}",
            "Drift Ratio (x)": p_drift,
            "P(Pass)": p_pass_str,
            "P(Breach)": p_breach_str,
            "Crit Slip (S*)": str(p_s_star),
            "Status": p_status
        })

    # Sort leaderboard by Drift Ratio descending, then Net PnL
    df_leaderboard = pd.DataFrame(leaderboard).sort_values(
        by=["Drift Ratio (x)", "Net PnL ($)"],
        ascending=[False, False]
    ).reset_index(drop=True)

    print("\n" + "=" * 120)
    print("                     ALPHAFORGE BENCHMARK ZOO // INSTITUTIONAL LEADERBOARD")
    print("=" * 120)
    print(df_leaderboard.to_string(index=True))
    print("=" * 120)
    print("* Statistical Gate: Strategies with N < 30 trades flagged as INSUFFICIENT_SAMPLE.")
    print("* Edge Criterion: Alpha Disqualified if Drift Ratio < 1.50x.")
    print("=" * 120 + "\n")

    # Save to reports/tables/
    table_path = Path("reports/tables/benchmark_zoo_leaderboard.csv")
    table_path.parent.mkdir(parents=True, exist_ok=True)
    df_leaderboard.to_csv(table_path, index=False)
    print(f"-> Saved leaderboard table to {table_path}")

    return df_leaderboard


if __name__ == "__main__":
    run_zoo_benchmarks()
