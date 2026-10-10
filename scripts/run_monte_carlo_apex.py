import numpy as np
import pandas as pd

# Cargar las operaciones reales de la estrategia
df_trades = pd.read_parquet("data/processed/mnq_5m_continuous.parquet")
from scripts.run_walkforward_pdh_sweep import *

# Extraer el array de PnL neto por operación con 1 MNQ
from scripts.run_liquidity_sweep_backtest import LiquiditySweepEngine
engine = LiquiditySweepEngine(df_trades, target_r_mult=1.40)
# Filtramos solo shorts
tl = engine.run_backtest()
tl_short = tl[tl['direction'] == 'SHORT']
pnl_1_contract = tl_short['net_pnl'].values

def simulate_apex(pnl_per_trade, contracts=1, n_sims=50000, target=3000.0, buffer=2500.0, max_trades=250):
    passes = 0
    fails = 0
    trade_counts_to_pass = []
    
    scaled_pnl = pnl_per_trade * contracts
    # Ajuste de comisiones adicionales por contrato
    scaled_pnl = scaled_pnl - (contracts - 1) * 1.24

    for _ in range(n_sims):
        # Muestreo con reemplazo preservando la distribución empírica
        sim_trades = np.random.choice(scaled_pnl, size=max_trades, replace=True)
        
        balance = 50000.0
        peak = 50000.0
        floor = 47500.0
        passed = False
        failed = False
        
        for idx, trade_pnl in enumerate(sim_trades):
            balance += trade_pnl
            if balance > peak:
                peak = balance
                if peak >= 52600.0:
                    floor = 50100.0
                else:
                    floor = peak - buffer
            
            if balance <= floor:
                failed = True
                fails += 1
                break
                
            if (balance - 50000.0) >= target:
                passed = True
                passes += 1
                trade_counts_to_pass.append(idx + 1)
                break

    pass_rate = (passes / n_sims) * 100.0
    fail_rate = (fails / n_sims) * 100.0
    avg_trades = np.mean(trade_counts_to_pass) if trade_counts_to_pass else 0
    
    return pass_rate, fail_rate, avg_trades

print("=" * 80)
print("      SIMULACIÓN MONTE CARLO APEX 50k (50,000 ITERACIONES)")
print("=" * 80)
for c in [1, 2, 3]:
    p_pass, p_fail, avg_t = simulate_apex(pnl_1_contract, contracts=c)
    print(f"[{c} Contrato(s) MNQ]")
    print(f"  Probabilidad de Aprobación : {p_pass:.2f}%")
    print(f"  Probabilidad de Quiebra    : {p_fail:.2f}%")
    print(f"  Trades Promedio para Pasar : {avg_t:.1f}")
    print("-" * 80)
