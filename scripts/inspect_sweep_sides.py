from pathlib import Path
import pandas as pd
from scripts.run_liquidity_sweep_backtest import LiquiditySweepEngine

df = pd.read_parquet("data/processed/mnq_5m_continuous.parquet")
engine = LiquiditySweepEngine(df)
tl = engine.run_backtest()

print("=" * 80)
print("       DESGLOSE DIRECCIONAL DE LIQUIDITY SWEEP (PDH vs PDL)")
print("=" * 80)

for side in ["LONG", "SHORT"]:
    sub = tl[tl["direction"] == side]
    pnl = sub["net_pnl"].values
    wins = pnl[pnl > 0]
    losses = pnl[pnl <= 0]
    wr = len(wins) / len(pnl) * 100 if len(pnl) > 0 else 0
    pf = wins.sum() / abs(losses.sum()) if abs(losses.sum()) > 0 else 0
    print(f"{side:<6} | N: {len(pnl):<3} | Win Rate: {wr:.2f}% | Profit Factor: {pf:.2f} | Net PnL: ${pnl.sum():,.2f}")

print("\n--- DISTRIBUCIÓN DE SALIDAS ---")
print(tl["exit_reason"].value_counts(normalize=True).round(3) * 100)
print("=" * 80)
