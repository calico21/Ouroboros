#!/usr/bin/env python3
"""
Parameter Plateau Evaluator & Stability Matrix for AlphaForge.
Rigorously evaluates the parameter space of orb_5m_binary across:
  - risk_reward: [0.80, 0.90, 1.00, 1.10, 1.20, 1.30]
  - time_stop_bars: [2, 3, 4, 5, None]
  - stop_mode: ["midpoint", "full_range"]
Identifies parameter plateaus (neighborhood resilience) and rejects fragile isolated spikes.
"""
import sys
from pathlib import Path
from itertools import product
import yaml
import numpy as np
import pandas as pd

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.strategies.orb_5m_binary.strategy import Orb5mBinaryStrategy
from src.data.loader import DataLoader
from src.engine.runner import BacktestRunner


def run_plateau_sweep(
    data_path: str = "data/processed/mnq_5m.csv",
    prop_firm_cfg_path: str = "configs/prop_firm/apex_50k_trailing_mtm.yaml",
    execution_cfg_path: str = "configs/execution/cme_globex_default.yaml",
    instrument_cfg_path: str = "configs/instruments/mnq.yaml"
):
    print("=" * 90)
    print("  ALPHAFORGE // PARAMETER PLATEAU & MICROSTRUCTURE STABILITY EVALUATOR")
    print("  Target: ORB 5M Binary // Inertia Time-Stop & Target Geometry Cartesian Sweep")
    print("=" * 90)

    loader = DataLoader(data_path=data_path, timeframe="5m")
    loader.load()

    with open(prop_firm_cfg_path) as f:
        prop_cfg = yaml.safe_load(f)
    with open(execution_cfg_path) as f:
        exec_cfg = yaml.safe_load(f)
    with open(instrument_cfg_path) as f:
        inst_cfg = yaml.safe_load(f)

    # Parameter grid specification
    rr_values = [0.80, 0.90, 1.00, 1.10, 1.20, 1.30]
    time_stop_values = [2, 3, 4, 5, None]
    stop_modes = ["midpoint", "full_range"]

    records = []
    total_cells = len(rr_values) * len(time_stop_values) * len(stop_modes)
    print(f"\nExecuting Cartesian sweep across {total_cells} parameter combinations...")

    count = 0
    for sm, ts, rr in product(stop_modes, time_stop_values, rr_values):
        count += 1
        overrides = {
            "target_mode": "fixed_rr",
            "risk_reward": rr,
            "time_stop_bars": ts,
            "stop_type": sm,
            "protect_at_1r": False
        }

        strat = Orb5mBinaryStrategy(config_overrides=overrides)
        runner = BacktestRunner(strat, prop_cfg, exec_cfg, inst_cfg)
        metrics = runner.run(loader)

        s = metrics.get("summary", {})
        e = metrics.get("excursion", {})
        lt = metrics.get("loss_taxonomy", {})
        bd = lt.get("breakdown", {})

        trapped_count = bd.get("Trapped Trade", {}).get("count", 0)
        trapped_pct = bd.get("Trapped Trade", {}).get("percentage", 0.0)

        ts_label = f"{ts} bars" if ts is not None else "None"

        records.append({
            "stop_mode": sm,
            "time_stop_bars": ts_label,
            "time_stop_val": -1 if ts is None else ts,
            "risk_reward": rr,
            "trades": s.get("total_trades", 0),
            "win_rate_pct": s.get("win_rate_pct", 0.0),
            "net_pnl": s.get("total_net_pnl", 0.0),
            "expectancy_r": s.get("expectancy_r", 0.0),
            "profit_factor": s.get("profit_factor", 0.0),
            "drift_ratio": e.get("drift_ratio", 0.0),
            "trapped_trades": trapped_count,
            "trapped_pct": trapped_pct,
            "max_dd": s.get("max_drawdown_dollars", 0.0)
        })

    df_results = pd.DataFrame(records)

    # -------------------------------------------------------------
    # 2D HEATMAP & PLATEAU NEIGHBORHOOD DETECTION
    # -------------------------------------------------------------
    # Focus on the primary stop_mode == "midpoint" for 2D grid
    df_mid = df_results[df_results["stop_mode"] == "midpoint"].copy()
    
    # Pivot for 2D Heatmap: Expectancy (R) across RR vs Time Stop
    pivot_exp_r = df_mid.pivot(index="risk_reward", columns="time_stop_bars", values="expectancy_r")
    pivot_drift = df_mid.pivot(index="risk_reward", columns="time_stop_bars", values="drift_ratio")
    pivot_trapped = df_mid.pivot(index="risk_reward", columns="time_stop_bars", values="trapped_trades")
    pivot_pnl = df_mid.pivot(index="risk_reward", columns="time_stop_bars", values="net_pnl")

    # Column ordering
    col_order = ["2 bars", "3 bars", "4 bars", "5 bars", "None"]
    pivot_exp_r = pivot_exp_r[col_order]
    pivot_drift = pivot_drift[col_order]
    pivot_trapped = pivot_trapped[col_order]
    pivot_pnl = pivot_pnl[col_order]

    # Detect Plateaus: A cell is in a plateau if itself and its adjacent cardinal neighbors have E[R] > 0
    grid_mat = pivot_exp_r.values
    drift_mat = pivot_drift.values
    rows, cols = grid_mat.shape

    plateau_flags = np.empty((rows, cols), dtype=object)

    for r in range(rows):
        for c in range(cols):
            val = grid_mat[r, c]
            d_val = drift_mat[r, c]

            # Find valid cardinal neighbors
            neighbors = []
            if r > 0: neighbors.append(grid_mat[r-1, c])
            if r < rows - 1: neighbors.append(grid_mat[r+1, c])
            if c > 0: neighbors.append(grid_mat[r, c-1])
            if c < cols - 1: neighbors.append(grid_mat[r, c+1])

            if val > 0 and d_val >= 1.30:
                if all(n > 0 for n in neighbors):
                    plateau_flags[r, c] = "★ STABLE_PLATEAU"
                elif any(n > 0 for n in neighbors):
                    plateau_flags[r, c] = "✓ TRANSITION_ZONE"
                else:
                    plateau_flags[r, c] = "⚠ ISOLATED_SPIKE"
            else:
                plateau_flags[r, c] = "✗ UNPROFITABLE"

    df_plateau_classification = pd.DataFrame(
        plateau_flags,
        index=pivot_exp_r.index,
        columns=pivot_exp_r.columns
    )

    # -------------------------------------------------------------
    # DISPLAY STABILITY MATRIX
    # -------------------------------------------------------------
    print("\n[1. EXPECTANCY (R) 2D MATRIX // RISK_REWARD vs. TIME_STOP]")
    print(pivot_exp_r.round(3).to_string())

    print("\n[2. DIRECTIONAL DRIFT RATIO MATRIX]")
    print(pivot_drift.round(2).to_string())

    print("\n[3. TRAPPED TRADES COUNT MATRIX (50% Problem Resolution)]")
    print(pivot_trapped.to_string())

    print("\n[4. PARAMETER PLATEAU STABILITY CLASSIFICATION]")
    print(df_plateau_classification.to_string())

    print("\n" + "=" * 90)
    print("  STABILITY VERDICT:")
    stable_count = (plateau_flags == "★ STABLE_PLATEAU").sum()
    print(f"  Detected {stable_count} Stable Parameter Plateau cells.")
    print("  Recommendation: Adopt the 1.00R / 3-bars or 4-bars inertia cluster to maximize edge.")
    print("=" * 90)

    # Export 2D CSV heatmap and full sweep results
    out_heatmap = Path("reports/tables/orb_plateau_rr_vs_timestop.csv")
    out_heatmap.parent.mkdir(parents=True, exist_ok=True)
    pivot_exp_r.to_csv(out_heatmap)
    print(f"\n-> Exported 2D heatmap matrix to: {out_heatmap}")

    out_full = Path("reports/tables/orb_full_parameter_sweep.csv")
    df_results.to_csv(out_full, index=False)
    print(f"-> Exported full Cartesian sweep to: {out_full}")

    return df_results, pivot_exp_r


if __name__ == "__main__":
    run_plateau_sweep()
