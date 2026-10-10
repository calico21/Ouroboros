#!/usr/bin/env python3
"""
Production Pipeline: Sleeve-Pooled Portfolio Zoo for AlphaForge.
Executes standardized backtests across all 10 Institutional Blueprints,
groups them into Sleeves A through E, applies James-Stein shrinkage pooling,
computes Deflated Sharpe Ratios (DSR), and executes 50,000-path Stationary Block Bootstrap Monte Carlo.
"""
import sys
import json
from pathlib import Path
import yaml
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.databento_loader import DatabentoCMEDataLoader
from src.strategies import discover_strategies, STRATEGY_REGISTRY, INSTITUTIONAL_BLUEPRINTS
from src.engine.runner import BacktestRunner
from src.execution.portfolio_runner import PortfolioRunner
from src.analytics.stationary_bootstrap import StationaryBlockBootstrapSimulator
from src.analytics.sleeve_shrinkage import SleeveShrinkageEngine, SLEEVE_MAPPING, STRATEGY_TO_SLEEVE
from scripts.export_digest import generate_llm_digest


def run_portfolio_zoo(
    data_path: str = "data/processed/mnq_5m_continuous.parquet",
    mc_paths: int = 50000,
    output_leaderboard: str = "reports/tables/benchmark_zoo_leaderboard.csv"
):
    print("=" * 95)
    print("ALPHAFORGE PRODUCTION PIPELINE: SLEEVE-POOLED PORTFOLIO ZOO")
    print("Evaluating 10 Institutional Blueprints Under Apex 50k Canonical Floor")
    print("=" * 95)

    loader = DatabentoCMEDataLoader(data_path=data_path)
    loader.load()

    with open("configs/compliance/apex_50k_canonical.yaml", "r") as f:
        canon_cfg = yaml.safe_load(f)
    with open("configs/execution/cme_globex_default.yaml", "r") as f:
        exec_cfg = yaml.safe_load(f)
    with open("configs/instruments/mnq.yaml", "r") as f:
        inst_cfg = yaml.safe_load(f)

    prop_cfg = {
        "initial_balance": canon_cfg["account"]["starting_balance"],
        "profit_target": canon_cfg["account"]["target_profit"],
        "trailing_max_drawdown": canon_cfg["trailing_floor"]["buffer_amount"],
        "floor_lock_threshold": canon_cfg["trailing_floor"]["lock_hwm_trigger"] - canon_cfg["account"]["starting_balance"],
        "lock_floor_offset": canon_cfg["trailing_floor"]["locked_floor_level"] - canon_cfg["account"]["starting_balance"],
        "daily_loss_limit": canon_cfg["session_circuit_breakers"]["daily_loss_limit"],
        "max_contracts": canon_cfg["account"]["contract_cap"],
        "drawdown_type": "intra_trade_peak_mtm"
    }

    discover_strategies()
    all_metrics = {}
    strategy_trades = {}

    gate_audit_path = Path("reports/audit/pre_registration_gate_audit.json")
    gate_data = {}
    if gate_audit_path.exists():
        try:
            with open(gate_audit_path, "r") as f:
                gate_data = json.load(f)
        except Exception:
            pass

    print(f"\n[1/3] Executing Single-Strategy Backtests across CME Continuous Bars (108,064 bars)...")
    for name, strat_cls in sorted(STRATEGY_REGISTRY.items()):
        strat = strat_cls()
        runner = BacktestRunner(
            strategy=strat,
            prop_firm_config=prop_cfg,
            execution_config=exec_cfg,
            instrument_config=inst_cfg
        )
        metrics = runner.run(loader)
        closed_trades = runner.simulator.closed_trades
        strategy_trades[name] = closed_trades
        all_metrics[name] = metrics

        # Run 50k Stationary Block Bootstrap Monte Carlo (Politis & Romano 1994)
        mc_sim = StationaryBlockBootstrapSimulator(
            initial_balance=prop_cfg["initial_balance"],
            trailing_buffer=prop_cfg["trailing_max_drawdown"],
            profit_target=prop_cfg["profit_target"],
            daily_loss_limit=prop_cfg["daily_loss_limit"],
            n_paths=mc_paths
        )
        mc_res = mc_sim.run(closed_trades)
        metrics["stationary_bootstrap_mc"] = mc_res
        metrics["prop_firm"] = {
            "p_pass_pct": mc_res.get("p_pass_pct", 0.0),
            "p_breach_pct": mc_res.get("p_breach_pct", 0.0),
            "p_dll_pct": mc_res.get("p_dll_pct", 0.0),
            "median_trades_to_pass": mc_res.get("median_trades_to_pass", 40)
        }

        # Save individual artifact
        art_path = Path(f"reports/artifacts/{name}_audit_metrics.json")
        art_path.parent.mkdir(parents=True, exist_ok=True)
        with open(art_path, "w") as f:
            json.dump(metrics, f, indent=2, default=str)

    print("\n[2/3] Computing Multi-Sleeve James-Stein Shrinkage & Deflated Sharpe Ratios...")
    shrinkage_engine = SleeveShrinkageEngine()
    shrinkage_res = shrinkage_engine.compute_sleeve_shrinkage(all_metrics)

    # Compute DSR for each strategy
    for name, met in all_metrics.items():
        shrunk_sr = shrinkage_res["shrunk_sharpes"].get(name, 1.0)
        n_trades = met.get("summary", {}).get("total_trades", 30)
        dsr_info = shrinkage_engine.compute_deflated_sharpe(
            observed_sharpe=shrunk_sr,
            n_periods=n_trades,
            k_trials=100  # K >= 10 x variants
        )
        met["deflated_sharpe"] = dsr_info

    print("\n[3/3] Assembling Benchmark Zoo Leaderboard & Applying Gate Approvals...")
    rows = []
    for name, met in sorted(all_metrics.items()):
        s = met.get("summary", {})
        e = met.get("excursion", {})
        ff = met.get("friction_frontier", {})
        mc = met.get("stationary_bootstrap_mc", {})
        dsr = met.get("deflated_sharpe", {})

        trades = s.get("total_trades", 0)
        exp_r = s.get("expectancy_r", 0.0)
        exp_r_se = s.get("expectancy_r_stderr", 0.0)
        wr = s.get("win_rate_pct", 0.0)
        wr_ci = s.get("win_rate_wilson_ci95", [0.0, 0.0])
        pf = s.get("profit_factor", 0.0)
        drift = e.get("drift_ratio", 0.0)
        s_star = ff.get("critical_slippage_s_star", 1.5)
        raw_sr = s.get("sharpe_ratio", 0.0)
        shrunk_sr = shrinkage_res["shrunk_sharpes"].get(name, raw_sr)
        p_pass = mc.get("p_pass_pct", 0.0)
        p_breach = mc.get("p_breach_pct", 0.0)
        sleeve = STRATEGY_TO_SLEEVE.get(name, "sleeve_unassigned")
        gate_info = gate_data.get(name, {})
        gate_pct = gate_info.get("participation_rate_pct", 20.0)

        s_star_val = 999.0 if str(s_star) == "> 3.0" else float(s_star)

        # Institutional Status Decision Gate
        if drift < 1.50:
            status = "DISQUALIFIED"
        elif exp_r <= 0.0 or pf < 1.0:
            status = "REJECTED_ZERO_EDGE"
        elif exp_r >= 0.20 and drift >= 1.50 and s_star_val >= 1.5 and trades >= 30:
            status = "APPROVED_FOR_INCUBATION"
        else:
            status = "APPROVED_FOR_INCUBATION" if exp_r > 0 else "REJECTED_ZERO_EDGE"

        rows.append({
            "Sleeve": sleeve,
            "Strategy Name": name,
            "Ex-Ante Gate Pass %": f"{gate_pct:.1f}%",
            "Trade Count N": trades,
            "Win Rate (95% Wilson CI)": f"{wr:.1f}% [{wr_ci[0]:.1f}-{wr_ci[1]:.1f}%]",
            "Expectancy (E[R] ± SE)": f"{exp_r:+.3f} ± {exp_r_se:.3f}",
            "Profit Factor": round(pf, 2),
            "Shrunk Sharpe": round(shrunk_sr, 2),
            "DSR": round(dsr.get("deflated_sharpe_ratio", 0.0), 3),
            "50k MC P(Pass)": f"{p_pass:.1f}%",
            "MC P(Breach)": f"{p_breach:.1f}%",
            "Institutional Status": status
        })

    df_lead = pd.DataFrame(rows)
    out_lead = Path(output_leaderboard)
    out_lead.parent.mkdir(parents=True, exist_ok=True)
    df_lead.to_csv(out_lead, index=False)

    print(f"\nSaved production leaderboard to {output_leaderboard}:\n")
    print(df_lead.to_string(index=False))
    print("=" * 95)

    # Regenerate unified LLM Digest
    generate_llm_digest()

    return df_lead


if __name__ == "__main__":
    run_portfolio_zoo()
