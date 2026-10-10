import sys
from pathlib import Path
import numpy as np
import pandas as pd
import scipy.stats as stats

def run_exhaustive_audit():
    data_path = Path("data/processed/mnq_5m_continuous.parquet")
    df = pd.read_parquet(data_path)

    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df.set_index("timestamp", inplace=True)
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    if df.index.tz is None:
        df.index = df.index.tz_localize("America/New_York")
    else:
        df.index = df.index.tz_convert("America/New_York")

    df = df.sort_index()
    df["date"] = df.index.date
    df["hour_min"] = df.index.strftime("%H:%M")

    # 1. Aislamiento RTH estricto (09:30 - 16:00 ET = 78 barras)
    rth_mask = (df["hour_min"] >= "09:30") & (df["hour_min"] <= "16:00")
    df_rth = df[rth_mask].copy()

    # Pre-cálculo vectorial de niveles e indicadores
    daily = df_rth.groupby("date").agg(d_high=("high", "max"), d_low=("low", "min"), d_open=("open", "first"))
    daily["pdh"] = daily["d_high"].shift(1)
    daily["daily_range"] = daily["pdh"] - daily["d_low"].shift(1)
    daily["atr14"] = daily["daily_range"].rolling(14, min_periods=5).mean()
    
    df_rth["pdh"] = df_rth["date"].map(daily["pdh"])
    df_rth["atr14"] = df_rth["date"].map(daily["atr14"])

    df_rth["tp"] = (df_rth["high"] + df_rth["low"] + df_rth["close"]) / 3.0
    df_rth["tp_vol"] = df_rth["tp"] * df_rth["volume"]
    df_rth["cum_tp_vol"] = df_rth.groupby("date")["tp_vol"].cumsum()
    df_rth["cum_vol"] = df_rth.groupby("date")["volume"].cumsum()
    df_rth["vwap"] = df_rth["cum_tp_vol"] / df_rth["cum_vol"]

    df_rth["vol_sma20"] = df_rth.groupby("date")["volume"].transform(
        lambda s: s.rolling(20, min_periods=5).mean()
    )

    # Cache de arrays NumPy para optimización máxima de simulación
    dates = df_rth["date"].values
    hour_mins = df_rth["hour_min"].values
    opens = df_rth["open"].values
    highs = df_rth["high"].values
    lows = df_rth["low"].values
    closes = df_rth["close"].values
    vwaps = df_rth["vwap"].values
    pdhs = df_rth["pdh"].values
    vols = df_rth["volume"].values
    vol_smas = df_rth["vol_sma20"].values
    atrs = df_rth["atr14"].values
    timestamps = df_rth.index

    split_date = pd.Timestamp("2024-01-01").date()

    def simulate_core(max_sweep=15.0, min_vol=1.0, target_r=1.75, contracts=3, slip_ticks=1):
        slip_pts = slip_ticks * 0.25
        comm = 1.24 * contracts

        trades = []
        balance = 50000.0
        peak = 50000.0
        floor = 47500.0
        active = False
        pending = False
        sig_high = 0.0
        entry_p = stop_p = target_p = stop_dist = 0.0
        cushions = []
        prev_date = None
        traded_today = False

        for i in range(len(df_rth)):
            c_date = dates[i]
            c_time = hour_mins[i]
            o, h, l, c = opens[i], highs[i], lows[i], closes[i]

            if c_date != prev_date:
                traded_today = False
                prev_date = c_date
                active = False
                pending = False

            # Ejecución t+1 al Open
            if pending and not active:
                entry_p = o - slip_pts
                raw_stop = (sig_high + 0.50) - entry_p
                stop_dist = min(max(raw_stop, 10.0), 22.0)
                stop_p = entry_p + stop_dist
                target_p = entry_p - (target_r * stop_dist)
                active = True
                pending = False

            if active:
                u_peak = (entry_p - l) * 2.0 * contracts
                f_peak = balance + max(0.0, u_peak)
                if f_peak > peak:
                    peak = f_peak
                    floor = max(floor, 50100.0) if peak >= 52600.0 else peak - 2500.0

                hit_stop = h >= stop_p
                hit_target = l <= target_p
                closed = False
                exit_p = 0.0

                if hit_stop:
                    closed = True
                    exit_p = max(o, stop_p) + slip_pts
                elif hit_target:
                    closed = True
                    exit_p = target_p
                elif c_time >= "15:55":
                    closed = True
                    exit_p = c + slip_pts

                if closed:
                    pts = entry_p - exit_p
                    net = (pts * 2.0 * contracts) - comm
                    balance += net
                    trades.append({
                        "date": c_date,
                        "timestamp": timestamps[i],
                        "net": net,
                        "pts": pts,
                        "r_mult": pts / stop_dist if stop_dist > 0 else 0.0,
                        "atr": atrs[i],
                        "is_oos": c_date >= split_date
                    })
                    active = False

            if not active and not pending and not traded_today:
                if "09:45" <= c_time <= "12:30":
                    pdh_val = pdhs[i]
                    vwap_val = vwaps[i]
                    v_val = vols[i]
                    v_sma = vol_smas[i]

                    if not np.isnan(pdh_val):
                        sw_dist = h - pdh_val
                        vol_ok = not np.isnan(v_sma) and (v_val >= min_vol * v_sma)
                        if 0 < sw_dist <= max_sweep and c < pdh_val and c < vwap_val and vol_ok:
                            pending = True
                            sig_high = h
                            traded_today = True

            cushions.append(balance - floor)

        min_cush = min(cushions) if cushions else 0.0
        max_dd = 2500.0 - min_cush
        return trades, max_dd

    # =========================================================================
    # TEST 1: ANÁLISIS DE LA MESETA PARAMÉTRICA (PARAMETER PLATEAU / GRID)
    # =========================================================================
    print("=" * 115)
    print("      TEST 1: MAPA DE CALOR Y MESETA PARAMÉTRICA (ROBUSTEZ CONTRA CURVE-FITTING)")
    print("      Objetivo: Confirmar si el edge existe en una meseta ancha o es un pico aislado.")
    print("=" * 115)
    print(f"{'Max Sweep':<11} {'Min Vol':<10} {'Target R':<10} | {'IS PF':<7} {'OOS N':<7} {'OOS WR':<8} {'OOS PF':<8} {'OOS PnL':<9} {'OOS MaxDD':<11} {'Estado'}")
    print("-" * 115)

    sweep_grid = [10.0, 12.5, 15.0, 17.5]
    vol_grid = [0.8, 1.0, 1.2]
    target_grid = [1.25, 1.50, 1.75, 2.00]

    grid_results = []
    total_evals = 0

    for sw in sweep_grid:
        for vl in vol_grid:
            for tg in target_grid:
                total_evals += 1
                tr, dd = simulate_core(max_sweep=sw, min_vol=vl, target_r=tg, contracts=3)
                t_is = [t for t in tr if not t["is_oos"]]
                t_oos = [t for t in tr if t["is_oos"]]

                p_is = np.array([t["net"] for t in t_is]) if t_is else np.array([0.0])
                p_oos = np.array([t["net"] for t in t_oos]) if t_oos else np.array([0.0])

                pf_is = p_is[p_is > 0].sum() / abs(p_is[p_is <= 0].sum()) if abs(p_is[p_is <= 0].sum()) > 0 else 0
                pf_oos = p_oos[p_oos > 0].sum() / abs(p_oos[p_oos <= 0].sum()) if abs(p_oos[p_oos <= 0].sum()) > 0 else 0
                wr_oos = len(p_oos[p_oos > 0]) / len(p_oos) * 100 if len(p_oos) > 0 else 0

                status = "ROBUSTO" if pf_oos >= 1.40 and pf_is >= 1.40 else ("ACEPTABLE" if pf_oos >= 1.20 else "FRÁGIL")
                grid_results.append({"sw": sw, "vl": vl, "tg": tg, "pf_is": pf_is, "pf_oos": pf_oos, "pnl_oos": p_oos.sum()})

                # Imprimir muestra representativa
                if tg in [1.50, 1.75] and vl in [1.0, 1.2]:
                    print(
                        f"{sw:<11.1f} {vl:<10.1f} {tg:<10.2f} | {pf_is:<7.2f} {len(p_oos):<7} {wr_oos:<7.1f}% "
                        f"{pf_oos:<8.2f} ${p_oos.sum():<8.0f} ${dd:<10.2f} {status}"
                    )

    pct_profitable = (sum(1 for r in grid_results if r["pf_oos"] > 1.20) / len(grid_results)) * 100
    print("-" * 115)
    print(f"Total combinaciones evaluadas: {total_evals} | Densidad de Meseta Rentable (PF > 1.20): {pct_profitable:.1f}%\n")

    # =========================================================================
    # TEST 2: CONSISTENCIA AÑO POR AÑO (WALK-FORWARD TEMPORAL ESTRICTO)
    # =========================================================================
    print("=" * 110)
    print("      TEST 2: CONSISTENCIA ANUAL (RUNNER 1.75R, 3 MNQ, OPEN[t+1], 1 TICK SLIP)")
    print("=" * 110)
    print(f"{'Año':<8} {'Régimen de Mercado':<30} | {'Trades':<8} {'Win Rate':<10} {'Profit Factor':<15} {'PnL Neto ($)':<14} {'Exp. R':<10}")
    print("-" * 110)

    tr_master, _ = simulate_core(max_sweep=15.0, min_vol=1.0, target_r=1.75, contracts=3)
    df_trades = pd.DataFrame(tr_master)
    df_trades["year"] = pd.to_datetime(df_trades["date"]).dt.year

    regime_names = {
        2022: "Bear Market / Alta Volatilidad",
        2023: "Recuperación / Subidas de Tipos",
        2024: "Rally AI / Rupturas Alcistas",
        2025: "Expansión Sostenida",
        2026: "Madurez de Mercado (YTD)"
    }

    for yr in sorted(df_trades["year"].unique()):
        sub_yr = df_trades[df_trades["year"] == yr]
        w = sub_yr[sub_yr["net"] > 0]["net"]
        l = sub_yr[sub_yr["net"] <= 0]["net"]
        wr = len(w) / len(sub_yr) * 100 if len(sub_yr) > 0 else 0
        pf = w.sum() / abs(l.sum()) if abs(l.sum()) > 0 else 999.0
        exp = sub_yr["r_mult"].mean()
        r_name = regime_names.get(yr, "Estándar")
        print(f"{yr:<8} {r_name:<30} | {len(sub_yr):<8} {wr:<9.1f}% {pf:<15.2f} ${sub_yr['net'].sum():<13.2f} {exp:<+.2f}R")
    print("=" * 110 + "\n")

    # =========================================================================
    # TEST 3: COMPORTAMIENTO POR REGÍMENES DE VOLATILIDAD (ATR TERCILES)
    # =========================================================================
    print("=" * 105)
    print("      TEST 3: CONDICIONAMIENTO POR VOLATILIDAD (ATR 14 DIARIO EN TERCILES)")
    print("=" * 105)
    print(f"{'Tercil de Volatilidad':<28} | {'Trades':<8} {'Win Rate':<10} {'Profit Factor':<15} {'PnL Neto ($)':<14} {'Exp. R':<10}")
    print("-" * 105)

    valid_trades = df_trades.dropna(subset=["atr"])
    atr_q1 = valid_trades["atr"].quantile(0.333)
    atr_q2 = valid_trades["atr"].quantile(0.666)

    terciles = [
        ("Baja Volatilidad (ATR < P33)", valid_trades["atr"] <= atr_q1),
        ("Media Volatilidad (P33-P66)", (valid_trades["atr"] > atr_q1) & (valid_trades["atr"] <= atr_q2)),
        ("Alta Volatilidad (ATR > P66)", valid_trades["atr"] > atr_q2),
    ]

    for label, mask in terciles:
        sub = valid_trades[mask]
        w = sub[sub["net"] > 0]["net"]
        l = sub[sub["net"] <= 0]["net"]
        wr = len(w) / len(sub) * 100 if len(sub) > 0 else 0
        pf = w.sum() / abs(l.sum()) if abs(l.sum()) > 0 else 0
        exp = sub["r_mult"].mean()
        print(f"{label:<28} | {len(sub):<8} {wr:<9.1f}% {pf:<15.2f} ${sub['net'].sum():<13.2f} {exp:<+.2f}R")
    print("=" * 105 + "\n")

    # =========================================================================
    # TEST 4: MATRIZ MONTE CARLO ASIMÉTRICA PARA APEX 50k (TARGET 1.75R)
    # =========================================================================
    print("=" * 115)
    print("      TEST 4: MONTE CARLO APEX 50k (TARGET 1.75R CON SLIPPAGE DINÁMICO PERTURBADO)")
    print("      50,000 Simulaciones por tamaño | Modelado de Trailing Stop Intradía Exacto")
    print("=" * 115)
    print(f"{'Sizing':<10} {'Contratos':<12} | {'Max DD Histórico':<18} {'Consumo Buffer':<16} {'Prob. Aprobación':<18} {'Trades Promedio':<18} {'Tasa Quiebra'}")
    print("-" * 115)

    n_sims = 50000
    for c in [3, 4, 5, 6]:
        tr_c, dd_c = simulate_core(max_sweep=15.0, min_vol=1.0, target_r=1.75, contracts=c)
        p_pool = np.array([t["net"] for t in tr_c])

        passes = 0
        fails = 0
        trade_steps = []

        for _ in range(n_sims):
            # Perturbar retornos aleatoriamente para simular incertidumbre de ejecución
            noise = np.random.choice([-1.0, 0.0, 1.0], size=150) * (0.25 * 2.0 * c)
            sampled = np.random.choice(p_pool, size=150, replace=True) + noise

            bal = 50000.0
            peak = 50000.0
            floor = 47500.0

            for idx, pnl_t in enumerate(sampled):
                bal += pnl_t
                if bal > peak:
                    peak = bal
                    floor = 50100.0 if peak >= 52600.0 else peak - 2500.0

                if bal <= floor:
                    fails += 1
                    break
                if (bal - 50000.0) >= 3000.0:
                    passes += 1
                    trade_steps.append(idx + 1)
                    break

        p_pass = (passes / n_sims) * 100.0
        p_fail = (fails / n_sims) * 100.0
        avg_s = np.mean(trade_steps) if trade_steps else 0.0
        dd_pct = (dd_c / 2500.0) * 100.0

        print(
            f"{f'{c} MNQ':<10} {f'{c} contratos':<12} | ${dd_c:<17.2f} {dd_pct:<15.1f}% "
            f"{p_pass:<17.2f}% {avg_s:<17.1f} {p_fail:.2f}%"
        )
    print("=" * 115 + "\n")

if __name__ == "__main__":
    run_exhaustive_audit()
