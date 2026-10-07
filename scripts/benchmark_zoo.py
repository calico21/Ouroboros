#!/usr/bin/env python3
"""
Benchmark Zoo for AlphaForge.
Executes standardized backtests across all auto-discovered strategies in src/strategies/
and produces an institutional comparative leaderboard ranked by Drift Ratio, Expectancy (R), and P(Pass).
"""
import sys
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

        # 10k Monte Carlo
        mc_sim = PropFirmMonteCarloSimulator(
            initial_balance=float(prop_cfg.get("initial_balance", 50000.0)),
            trailing_max_dd=float(prop_cfg.get("trailing_max_drawdown", 2500.0)),
            profit_target=float(prop_cfg.get("profit_target", 3000.0)),
            iterations=10000
        )
        mc_res = mc_sim.run(runner.simulator.closed_trades)

        s = metrics.get("summary", {})
        e = metrics.get("excursion", {})
        ff = metrics.get("friction_frontier", {})

        drift = e.get("drift_ratio", 0.0)
        exp_r = s.get("expectancy_r", 0.0)
        p_pass = mc_res.get("prob_pass_pct", 0.0)
        p_breach = mc_res.get("prob_breach_pct", 0.0)
        pf = s.get("profit_factor", 0.0)
        wr = s.get("win_rate_pct", 0.0)
        trades = s.get("total_trades", 0)
        net_pnl = s.get("total_net_pnl", 0.0)
        s_star = ff.get("critical_slippage_s_star", 0.0)

        disqualified = drift < 1.50

        leaderboard.append({
            "Strategy": name,
            "Trades": trades,
            "Win Rate %": wr,
            "Net PnL ($)": net_pnl,
            "Profit Factor": pf,
            "Expectancy (R)": exp_r,
            "Drift Ratio (x)": drift,
            "P(Pass) %": p_pass,
            "P(Breach) %": p_breach,
            "Crit Slip (S*)": str(s_star),
            "Status": "DISQUALIFIED" if disqualified else "VIABLE"
        })

    # Sort leaderboard by Drift Ratio descending, then Expectancy (R)
    df_leaderboard = pd.DataFrame(leaderboard).sort_values(
        by=["Drift Ratio (x)", "Expectancy (R)", "P(Pass) %"],
        ascending=[False, False, False]
    ).reset_index(drop=True)

    print("\n" + "=" * 110)
    print("                     ALPHAFORGE BENCHMARK ZOO // INSTITUTIONAL LEADERBOARD")
    print("=" * 110)
    print(df_leaderboard.to_string(index=True))
    print("=" * 110)
    print("* Edge Criterion: Alpha Disqualified if Drift Ratio < 1.50x.")
    print("=" * 110 + "\n")

    # Save to reports/tables/
    table_path = Path("reports/tables/benchmark_zoo_leaderboard.csv")
    table_path.parent.mkdir(parents=True, exist_ok=True)
    df_leaderboard.to_csv(table_path, index=False)
    print(f"-> Saved leaderboard table to {table_path}")

    return df_leaderboard


if __name__ == "__main__":
    run_zoo_benchmarks()
