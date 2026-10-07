#!/usr/bin/env python3
"""
Parameter Plateau & Sensitivity Sweep for AlphaForge.
Evaluates strategy robustness across parameter neighborhood grids to detect overfitting spikes.
"""
import sys
import argparse
from pathlib import Path
import pandas as pd
import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.strategies import discover_strategies, STRATEGY_REGISTRY
from src.data.loader import DataLoader
from src.engine.runner import BacktestRunner


def sweep_target_multipliers(
    strategy_name: str = "orb_5m_binary",
    target_r_steps: list = [1.5, 1.8, 2.0, 2.2, 2.5, 3.0],
    data_path: str = "data/processed/mnq_5m.csv"
):
    discover_strategies()
    strat_cls = STRATEGY_REGISTRY[strategy_name]
    loader = DataLoader(data_path=data_path, timeframe="5m")
    loader.load()

    with open("configs/prop_firm/apex_50k_trailing_mtm.yaml") as f:
        prop_cfg = yaml.safe_load(f)
    with open("configs/execution/cme_globex_default.yaml") as f:
        exec_cfg = yaml.safe_load(f)
    with open("configs/instruments/mnq.yaml") as f:
        inst_cfg = yaml.safe_load(f)

    results = []
    print(f"\nSweeping Target R Multipliers for {strategy_name}:")

    for r in target_r_steps:
        instance = strat_cls(config_overrides={"target_r_multiple": r})
        runner = BacktestRunner(instance, prop_cfg, exec_cfg, inst_cfg)
        metrics = runner.run(loader)
        s = metrics.get("summary", {})
        e = metrics.get("excursion", {})

        results.append({
            "Target R": r,
            "Trades": s.get("total_trades", 0),
            "Win Rate %": s.get("win_rate_pct", 0),
            "Net PnL ($)": s.get("total_net_pnl", 0),
            "Expectancy (R)": s.get("expectancy_r", 0),
            "Drift Ratio": e.get("drift_ratio", 0)
        })

    df_sweep = pd.DataFrame(results)
    print("\n" + "=" * 70)
    print("                PARAMETER PLATEAU SWEEP RESULTS")
    print("=" * 70)
    print(df_sweep.to_string(index=False))
    print("=" * 70 + "\n")

    out_p = Path(f"reports/tables/{strategy_name}_plateau_sweep.csv")
    out_p.parent.mkdir(parents=True, exist_ok=True)
    df_sweep.to_csv(out_p, index=False)
    print(f"-> Saved sweep results to {out_p}")


if __name__ == "__main__":
    sweep_target_multipliers()
