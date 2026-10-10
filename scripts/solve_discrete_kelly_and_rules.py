from pathlib import Path
import numpy as np
import pandas as pd
import scipy.stats as stats
from scipy.optimize import minimize_scalar

def run_forensic_audit_and_discrete_kelly():
    csv_path = Path("data/processed/ouroboros_trade_log_pdh_h1_granular.csv")
    if not csv_path.exists():
        print(f"❌ Error: {csv_path} no encontrado.")
        return

    df = pd.read_csv(csv_path)
    df["date"] = pd.to_datetime(df["date"]).dt.date

    print("=" * 115)
    print("      AUDITORÍA FORENSE DEFINITIVA DEL TRADE LOG (DATOS REALES DEL ARCHIVO)")
    print(f"      Archivo: {csv_path} | Total Filas: {len(df)}")
    print("=" * 115)

    # 1. Conteo Exacto de Filas y Pares de Días
    df_pdh = df[df["module"] == "PDH_SWEEP"].copy()
    df_h1 = df[df["module"] == "H1_MOMENTUM"].copy()

    dates_pdh = set(df_pdh["date"].unique())
    dates_h1 = set(df_h1["date"].unique())
    dates_overlap = sorted(list(dates_pdh.intersection(dates_h1)))

    print(f"1. CONTEO DE TRADES Y SESIONES:")
    print(f"   • Filas Totales en CSV           : {len(df)}")
    print(f"   • Trades PDH_SWEEP               : {len(df_pdh)} (en {len(dates_pdh)} sesiones distintas)")
    print(f"   • Trades H1_MOMENTUM             : {len(df_h1)} (en {len(dates_h1)} sesiones distintas)")
    print(f"   • Sesiones con AMBOS disparando  : {len(dates_overlap)} días exactos")

    # 2. Análisis de Clamping Real en el Archivo
    print(f"\n2. CLAMPING DE STOPS EN EL ARCHIVO REAL:")
    for mod_name, sub in [("PDH_SWEEP", df_pdh), ("H1_MOMENTUM", df_h1)]:
        c_max = len(sub[sub["stop_pts"] == 22.0])
        c_min = len(sub[sub["stop_pts"] == 10.0])
        c_mid = len(sub[(sub["stop_pts"] > 10.0) & (sub["stop_pts"] < 22.0)])
        raw_over = len(sub[sub["raw_stop_pts"] > 22.0])
        print(f"   ▶ {mod_name} (N={len(sub)}):")
        print(f"      - Clamped al Techo (22.0 pts) : {c_max} ({c_max/len(sub)*100:.1f}%)")
        print(f"      - Clamped al Suelo (10.0 pts) : {c_min} ({c_min/len(sub)*100:.1f}%)")
        print(f"      - Stop Natural (10 a 22 pts)  : {c_mid} ({c_mid/len(sub)*100:.1f}%)")
        print(f"      - Raw Stop > 22 pts           : {raw_over} ({raw_over/len(sub)*100:.1f}%)")
        print(f"      - Stop Medio Ejecutado        : {sub['stop_pts'].mean():.2f} pts | Raw Stop Medio: {sub['raw_stop_pts'].mean():.2f} pts")

    # 3. Distribución Real de Motivos de Salida
    print(f"\n3. MOTIVOS DE SALIDA REALES EN EL ARCHIVO:")
    for mod_name, sub in [("PDH_SWEEP", df_pdh), ("H1_MOMENTUM", df_h1)]:
        vc = sub["exit_reason"].value_counts()
        print(f"   ▶ {mod_name}:")
        for reason, count in vc.items():
            print(f"      - {reason:<10}: {count:>4} trades ({count/len(sub)*100:.1f}%)")

    # 4. Verificación Numérica de Columnas de R y Fricción
    print(f"\n4. VERIFICACIÓN DE FÓRMULAS DE R Y SLIPPAGE:")
    # Tomar la primera fila de H1 para validar
    sample_row = df_h1.iloc[0]
    print(f"   Fila Muestra H1 ({sample_row['entry_time']}):")
    print(f"      - Side: {sample_row['side']} | Stop Pts: {sample_row['stop_pts']} | Risk Dollars: ${sample_row['risk_dollars']:.2f}")
    print(f"      - Exit Reason: {sample_row['exit_reason']} | Gross Pts: {sample_row['gross_pts']:.2f}")
    print(f"      - Net Dollars (0 Ticks) : ${sample_row['net_dollars_0t']:.2f} --> r_net_0t = {sample_row['r_net_0t']:.4f}")
    print(f"      - Net Dollars (1 Tick)  : ${sample_row['net_dollars_1t']:.2f} --> r_net_1t = {sample_row['r_net_1t']:.4f}")
    print(f"      - Net Dollars (2 Ticks) : ${sample_row['net_dollars_2t']:.2f} --> r_net_2t = {sample_row['r_net_2t']:.4f}")
    
    # Validar cálculo:
    # 2 contratos MNQ = $4/pt.
    # Comisión roundtrip = $2.48.
    # Slippage 1 tick por lado = 2 ticks = 0.50 pts = $2.00.
    # Diferencia entre 0t y 1t debe ser exactamente $2.00 si sale por stop o mercado.
    diff_0_1 = sample_row["net_dollars_0t"] - sample_row["net_dollars_1t"]
    print(f"      - Diferencia monetaria (0t vs 1t): ${diff_0_1:.2f} (Esperado: $2.00 si 1 tick/lado)")

    # 5. Bootstrap de E[R] (10.000 resamples) para IC 95%
    print(f"\n" + "=" * 115)
    print("      5. INTERVALOS DE CONFIANZA BOOTSTRAP 95% DE E[R] (CON 1 TICK NET)")
    print("=" * 115)

    def bootstrap_ci(series, n_boot=10000):
        arr = series.values
        means = []
        np.random.seed(42)
        for _ in range(n_boot):
            s = np.random.choice(arr, size=len(arr), replace=True)
            means.append(s.mean())
        return arr.mean(), np.percentile(means, 2.5), np.percentile(means, 97.5), arr.std()

    m_pdh, low_pdh, high_pdh, std_pdh = bootstrap_ci(df_pdh["r_net_1t"])
    m_h1, low_h1, high_h1, std_h1 = bootstrap_ci(df_h1["r_net_1t"])

    # Cartera agrupada por día
    d_daily = df.groupby(["date", "module"])["r_net_1t"].sum().unstack(fill_value=0.0)
    d_daily["port_r"] = d_daily.get("PDH_SWEEP", 0.0) + d_daily.get("H1_MOMENTUM", 0.0)
    m_port, low_port, high_port, std_port = bootstrap_ci(d_daily["port_r"])

    print(f"  • PDH_SWEEP   (N={len(df_pdh):<4}): E[R]={m_pdh:+.3f}R | Std={std_pdh:.3f} | IC 95%: [{low_pdh:+.3f}R, {high_pdh:+.3f}R]")
    print(f"  • H1_MOMENTUM (N={len(df_h1):<4}): E[R]={m_h1:+.3f}R | Std={std_h1:.3f} | IC 95%: [{low_h1:+.3f}R, {high_h1:+.3f}R]")
    print(f"  • CARTERA DÍA (N={len(d_daily):<4}): E[R]={m_port:+.3f}R | Std={std_port:.3f} | IC 95%: [{low_port:+.3f}R, {high_port:+.3f}R]")

    # 6. Cálculo Formal de Kelly Discreto Numérico
    print(f"\n" + "=" * 115)
    print("      6. CÁLCULO DE KELLY DISCRETO EMPÍRICO: max E[ln(1 + f * R)]")
    print("=" * 115)

    def solve_discrete_kelly(r_arr):
        r_arr = np.array(r_arr)
        min_r = r_arr.min()
        max_f_allowed = (1.0 / abs(min_r)) * 0.999 if min_r < 0 else 1.0

        def neg_expected_log_growth(f):
            terms = 1.0 + f * r_arr
            if np.any(terms <= 0):
                return 1e9
            return -np.mean(np.log(terms))

        res = minimize_scalar(neg_expected_log_growth, bounds=(0.0, max_f_allowed), method="bounded")
        f_opt = res.x if res.success else 0.0
        return f_opt

    f_pdh = solve_discrete_kelly(df_pdh["r_net_1t"].values)
    f_h1 = solve_discrete_kelly(df_h1["r_net_1t"].values)
    f_port = solve_discrete_kelly(d_daily["port_r"].values)

    # Kelly conservador sobre el límite inferior del IC
    # Escalar la distribución para que su media sea el límite inferior
    def solve_conservative_kelly(r_arr, target_mean):
        if target_mean <= 0:
            return 0.0
        shift = target_mean - r_arr.mean()
        r_shifted = r_arr + shift
        return solve_discrete_kelly(r_shifted)

    f_pdh_cons = solve_conservative_kelly(df_pdh["r_net_1t"].values, low_pdh)
    f_h1_cons = solve_conservative_kelly(df_h1["r_net_1t"].values, low_h1)

    print(f"{'Módulo / Cartera':<25} | {'Full-Kelly (f*)':<16} {'Half-Kelly':<14} {'Quarter-Kelly':<15} {'Kelly Conservador (IC Low)'}")
    print("-" * 115)
    print(f"{'PDH_SWEEP':<25} | {f_pdh*100:<15.2f}% {f_pdh*50:<13.2f}% {f_pdh*25:<14.2f}% {f_pdh_cons*100:.2f}% (IC Low: {low_pdh:+.2f}R)")
    print(f"{'H1_MOMENTUM':<25} | {f_h1*100:<15.2f}% {f_h1*50:<13.2f}% {f_h1*25:<14.2f}% {f_h1_cons*100:.2f}% (IC Low: {low_h1:+.2f}R)")
    print(f"{'CARTERA DÍA (Conjunto)':<25} | {f_port*100:<15.2f}% {f_port*50:<13.2f}% {f_port*25:<14.2f}% {solve_conservative_kelly(d_daily['port_r'].values, low_port)*100:.2f}%")

    # 7. Simulación Monte Carlo con Ratchet sobre MFE y Regla de Corte Escalonada
    print(f"\n" + "=" * 115)
    print("      7. SIMULACIÓN DE RUPTURA CON RATCHET MFE Y REGLA DE CORTE POR DRAWDOWN")
    print("      Regla de Corte: Drawdown >= 25% del buffer ($500) -> Cortar tamaño al 50%.")
    print("                      Drawdown >= 50% del buffer ($1.000) -> HALT / Parar operativa.")
    print("      Muestra: 10.000 Simulaciones de 250 Sesiones (1 Año) | Buffer: $2.000")
    print("=" * 115)
    print(f"{'Estrategia de Riesgo':<32} | {'1R Inicial ($)':<15} {'Breach Sin Cutoff':<20} {'Breach CON Cutoff Escalonado'}")
    print("-" * 115)

    all_dates = sorted(list(d_daily.index))
    daily_trades = df.groupby("date").apply(lambda g: g.to_dict("records"), include_groups=False).to_dict()

    n_sims = 10000

    for r_pct in [0.005, 0.010, 0.015, 0.020]:
        base_r_dollar = 2000.0 * r_pct
        breaches_raw = 0
        breaches_cutoff = 0

        for _ in range(n_sims):
            sim_dates = np.random.choice(all_dates, size=250, replace=True)

            # 1. Simulación Raw (Sin regla de corte)
            bal = 50000.0
            peak_floor = 48000.0
            is_dead_raw = False

            for d in sim_dates:
                if d in daily_trades:
                    for t in daily_trades[d]:
                        pnl = t["r_net_1t"] * base_r_dollar
                        mfe_d = (t["mfe_pts"] / t["stop_pts"]) * base_r_dollar
                        intra_peak = bal + mfe_d
                        bal += pnl

                        # Ratchet intratrade de Apex
                        peak_floor = max(peak_floor, 50100.0 if intra_peak >= 52600.0 else intra_peak - 2000.0)
                        if bal <= peak_floor:
                            is_dead_raw = True
                            break
                if is_dead_raw:
                    break
            if is_dead_raw:
                breaches_raw += 1

            # 2. Simulación CON Regla de Corte Escalonada
            bal_c = 50000.0
            peak_floor_c = 48000.0
            peak_bal_c = 50000.0
            is_dead_c = False
            halted = False

            for d in sim_dates:
                if halted:
                    break
                if d in daily_trades:
                    for t in daily_trades[d]:
                        # Drawdown actual de buffer
                        buf_dd = peak_bal_c - bal_c

                        # Escalado dinámico por drawdown
                        if buf_dd >= 1000.0:  # 50% buffer consumido -> Parada
                            halted = True
                            break
                        elif buf_dd >= 500.0: # 25% buffer consumido -> Mitad de tamaño
                            current_r_dollar = base_r_dollar * 0.5
                        else:
                            current_r_dollar = base_r_dollar

                        pnl = t["r_net_1t"] * current_r_dollar
                        mfe_d = (t["mfe_pts"] / t["stop_pts"]) * current_r_dollar
                        intra_peak = bal_c + mfe_d
                        bal_c += pnl

                        if bal_c > peak_bal_c:
                            peak_bal_c = bal_c

                        peak_floor_c = max(peak_floor_c, 50100.0 if intra_peak >= 52600.0 else intra_peak - 2000.0)
                        if bal_c <= peak_floor_c:
                            is_dead_c = True
                            break
                if is_dead_c:
                    break
            if is_dead_c:
                breaches_cutoff += 1

        print(f"Riesgo {r_pct*100:.1f}% Buffer (${base_r_dollar:<5.1f})   | ${base_r_dollar:<14.2f} {breaches_raw/n_sims*100:<19.2f}% {breaches_cutoff/n_sims*100:.2f}%")

    print("=" * 115 + "\n")

if __name__ == "__main__":
    run_forensic_audit_and_discrete_kelly()
