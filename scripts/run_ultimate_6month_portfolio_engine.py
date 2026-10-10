import sys
from pathlib import Path
import numpy as np
import pandas as pd

def run_ultimate_portfolio_suite():
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

    # Aislamiento RTH estricto (09:30 - 16:00 ET = 78 barras)
    rth_mask = (df["hour_min"] >= "09:30") & (df["hour_min"] <= "16:00")
    df_rth = df[rth_mask].copy()

    # 1. PDH
    daily = df_rth.groupby("date").agg(d_high=("high", "max"))
    daily["pdh"] = daily["d_high"].shift(1)
    df_rth["pdh"] = df_rth["date"].map(daily["pdh"])

    # 2. VWAP RTH acumulativo
    df_rth["tp"] = (df_rth["high"] + df_rth["low"] + df_rth["close"]) / 3.0
    df_rth["tp_vol"] = df_rth["tp"] * df_rth["volume"]
    df_rth["cum_tp_vol"] = df_rth.groupby("date")["tp_vol"].cumsum()
    df_rth["cum_vol"] = df_rth.groupby("date")["volume"].cumsum()
    df_rth["vwap"] = df_rth["cum_tp_vol"] / df_rth["cum_vol"]

    # 3. SMA20 de volumen
    df_rth["vol_sma20"] = df_rth.groupby("date")["volume"].transform(
        lambda s: s.rolling(20, min_periods=5).mean()
    )

    # 4. ORB 15 min (Barras de 09:30, 09:35, 09:40)
    orb15_df = df_rth[df_rth["hour_min"].isin(["09:30", "09:35", "09:40"])]
    orb15_high = orb15_df.groupby("date")["high"].max()
    orb15_low = orb15_df.groupby("date")["low"].min()
    df_rth["orb15_h"] = df_rth["date"].map(orb15_high)
    df_rth["orb15_l"] = df_rth["date"].map(orb15_low)

    dates = df_rth["date"].values
    hour_mins = df_rth["hour_min"].values
    opens = df_rth["open"].values
    highs = df_rth["high"].values
    lows = df_rth["low"].values
    closes = df_rth["close"].values
    vwaps = df_rth["vwap"].values
    pdhs = df_rth["pdh"].values
    orb_hs = df_rth["orb15_h"].values
    orb_ls = df_rth["orb15_l"].values
    vols = df_rth["volume"].values
    vol_smas = df_rth["vol_sma20"].values
    timestamps = df_rth.index
    all_unique_dates = sorted(list(set(dates)))

    split_date = pd.Timestamp("2024-01-01").date()

    # MOTOR VECTORIAL DE SEÑALES POR MÓDULO
    def generate_signals():
        signals = []
        # Para cada barra, comprobamos si dispara alguna estrategia
        for i in range(len(df_rth)):
            c_date = dates[i]
            c_time = hour_mins[i]
            h, l, c = highs[i], lows[i], closes[i]
            v, v_sma = vols[i], vol_smas[i]
            vwap = vwaps[i]
            pdh = pdhs[i]
            o15_h = orb_hs[i]
            o15_l = orb_ls[i]

            vol_ok = not np.isnan(v_sma) and (v >= 1.0 * v_sma)

            # Módulo 1: PDH SWEEP SHORT (09:45 - 12:30)
            if "09:45" <= c_time <= "12:30" and not np.isnan(pdh) and vol_ok:
                sw = h - pdh
                if 0 < sw <= 15.0 and c < pdh and c < vwap:
                    signals.append({
                        "idx": i, "date": c_date, "time": c_time, "type": "PDH_SHORT",
                        "side": -1, "sig_extreme": h, "sig_c": c
                    })

            # Módulo 2: ORB-15 LONG (09:45 - 11:30)
            if "09:45" <= c_time <= "11:30" and not np.isnan(o15_h) and not np.isnan(o15_l) and vol_ok:
                orb_rng = o15_h - o15_l
                if 12.0 <= orb_rng <= 55.0:
                    if h > o15_h and c > o15_h and c > vwap:
                        orb_mid = (o15_h + o15_l) / 2.0
                        signals.append({
                            "idx": i, "date": c_date, "time": c_time, "type": "ORB_LONG",
                            "side": 1, "sig_extreme": orb_mid, "sig_c": c
                        })

            # Módulo 3: ORB-15 SHORT (09:45 - 11:30)
            if "09:45" <= c_time <= "11:30" and not np.isnan(o15_h) and not np.isnan(o15_l) and vol_ok:
                orb_rng = o15_h - o15_l
                if 12.0 <= orb_rng <= 55.0:
                    if l < o15_l and c < o15_l and c < vwap:
                        orb_mid = (o15_h + o15_l) / 2.0
                        signals.append({
                            "idx": i, "date": c_date, "time": c_time, "type": "ORB_SHORT",
                            "side": -1, "sig_extreme": orb_mid, "sig_c": c
                        })

            # Módulo 4: VWAP PULLBACK LONG (10:15 - 12:30)
            if "10:15" <= c_time <= "12:30" and vol_ok:
                if l <= (vwap + 2.0) and l >= (vwap - 10.0) and c > vwap and c > opens[i]:
                    signals.append({
                        "idx": i, "date": c_date, "time": c_time, "type": "VWAP_PULLBACK_LONG",
                        "side": 1, "sig_extreme": l, "sig_c": c
                    })
        return signals

    all_signals = generate_signals()
    sig_df = pd.DataFrame(all_signals)

    # MOTOR DE EJECUCIÓN EXACTA (OPEN[t+1], SLIPPAGE, STOP-FIRST, TRAILING STOP APEX)
    def simulate_portfolio(allowed_types, contracts=5, target_r=1.75):
        slip_pts = 0.25
        comm = 1.24 * contracts

        active = False
        side = 0
        entry_p = stop_p = target_p = stop_dist = 0.0
        pending = False
        pending_sig = None

        balance = 50000.0
        peak = 50000.0
        floor = 47500.0
        cushions = []
        trades = []
        daily_pnl = {d: 0.0 for d in all_unique_dates}

        prev_date = None
        traded_today = False

        # Convertir señales permitidas a diccionario por barra
        active_sigs_by_idx = {}
        for s in all_signals:
            if s["type"] in allowed_types:
                if s["idx"] not in active_sigs_by_idx:
                    active_sigs_by_idx[s["idx"]] = s

        for i in range(len(df_rth)):
            c_date = dates[i]
            c_time = hour_mins[i]
            o, h, l, c = opens[i], highs[i], lows[i], closes[i]

            if c_date != prev_date:
                traded_today = False
                prev_date = c_date
                active = False
                pending = False

            # Ejecución en barra t+1
            if pending and not active:
                s_info = pending_sig
                side = s_info["side"]

                if side == -1:  # SHORT
                    entry_p = o - slip_pts
                    raw_stop = (s_info["sig_extreme"] + 0.50) - entry_p if s_info["type"] == "PDH_SHORT" else entry_p - s_info["sig_extreme"]
                    stop_dist = min(max(raw_stop, 10.0), 24.0)
                    stop_p = entry_p + stop_dist
                    target_p = entry_p - (target_r * stop_dist)
                else:  # LONG
                    entry_p = o + slip_pts
                    raw_stop = entry_p - (s_info["sig_extreme"] - 0.50)
                    stop_dist = min(max(raw_stop, 10.0), 24.0)
                    stop_p = entry_p - stop_dist
                    target_p = entry_p + (target_r * stop_dist)

                active = True
                pending = False

            if active:
                # Actualizar Trailing Peak intradía
                u_peak = ((entry_p - l) if side == -1 else (h - entry_p)) * 2.0 * contracts
                f_peak = balance + max(0.0, u_peak)
                if f_peak > peak:
                    peak = f_peak
                    floor = max(floor, 50100.0) if peak >= 52600.0 else peak - 2500.0

                closed = False
                exit_p = 0.0

                hit_stop = (h >= stop_p) if side == -1 else (l <= stop_p)
                hit_target = (l <= target_p) if side == -1 else (h >= target_p)

                if hit_stop:
                    closed = True
                    exit_p = (max(o, stop_p) + slip_pts) if side == -1 else (min(o, stop_p) - slip_pts)
                elif hit_target:
                    closed = True
                    exit_p = target_p
                elif c_time >= "15:55":
                    closed = True
                    exit_p = (c + slip_pts) if side == -1 else (c - slip_pts)

                if closed:
                    pts = (entry_p - exit_p) if side == -1 else (exit_p - entry_p)
                    net = (pts * 2.0 * contracts) - comm
                    balance += net
                    daily_pnl[c_date] += net
                    trades.append({
                        "date": c_date, "type": pending_sig["type"], "net": net,
                        "pts": pts, "r_mult": pts / stop_dist if stop_dist > 0 else 0.0,
                        "is_oos": c_date >= split_date, "year": c_date.year
                    })
                    active = False

            if not active and not pending and not traded_today:
                if i in active_sigs_by_idx:
                    pending = True
                    pending_sig = active_sigs_by_idx[i]
                    traded_today = True

            cushions.append(balance - floor)

        min_cush = min(cushions) if cushions else 0.0
        max_dd = 2500.0 - min_cush
        return trades, max_dd, list(daily_pnl.values())

    # =========================================================================
    # PARTE 1: RENDIMIENTO INDIVIDUAL DE CADA MÓDULO (3 MNQ)
    # =========================================================================
    print("=" * 115)
    print("      PARTE 1: AUDITORÍA DE MÓDULOS CANDIDATOS (INDIVIDUAL, 3 MNQ, OPEN[t+1], 1 TICK SLIP)")
    print("=" * 115)
    print(f"{'Módulo Candidato':<30} | {'Trades/Yr':<9} {'IS: PF':<7} {'OOS: WR':<8} {'OOS: PF':<7} {'OOS: PnL':<9} {'Max DD ($)':<11} {'Exp. R':<8}")
    print("-" * 115)

    module_types = [
        ("1. PDH Sweep Short (Baseline)", ["PDH_SHORT"]),
        ("2. ORB-15 Long (Trend Engine)", ["ORB_LONG"]),
        ("3. ORB-15 Short (Breakdown)", ["ORB_SHORT"]),
        ("4. VWAP Pullback Long (Trend)", ["VWAP_PULLBACK_LONG"]),
    ]

    for m_label, m_types in module_types:
        tr_m, dd_m, _ = simulate_portfolio(m_types, contracts=3, target_r=1.75)
        t_is = [t for t in tr_m if not t["is_oos"]]
        t_oos = [t for t in tr_m if t["is_oos"]]
        p_is = np.array([t["net"] for t in t_is]) if t_is else np.array([0.0])
        p_oos = np.array([t["net"] for t in t_oos]) if t_oos else np.array([0.0])

        pf_is = p_is[p_is > 0].sum() / abs(p_is[p_is <= 0].sum()) if abs(p_is[p_is <= 0].sum()) > 0 else 0
        pf_oos = p_oos[p_oos > 0].sum() / abs(p_oos[p_oos <= 0].sum()) if abs(p_oos[p_oos <= 0].sum()) > 0 else 0
        wr_oos = len(p_oos[p_oos > 0]) / len(p_oos) * 100 if len(p_oos) > 0 else 0
        exp_r = np.mean([t["r_mult"] for t in t_oos]) if t_oos else 0.0
        tr_per_yr = len(tr_m) / 4.77

        print(
            f"{m_label:<30} | {tr_per_yr:<9.1f} {pf_is:<7.2f} {wr_oos:<7.1f}% {pf_oos:<7.2f} "
            f"${p_oos.sum():<8.0f} ${dd_m:<10.2f} {exp_r:<+.2f}R"
        )
    print("=" * 115 + "\n")

    # =========================================================================
    # PARTE 2: CARTERAS COMBINADAS Y MONTE CARLO HORIZONTE ESTRICTO 6 MESES
    # =========================================================================
    portfolios = [
        ("Portfolio 0: Solo PDH Short (Actual)", ["PDH_SHORT"]),
        ("Portfolio 1: PDH Short + ORB-15 Long (Dual Core)", ["PDH_SHORT", "ORB_LONG"]),
        ("Portfolio 2: PDH Short + ORB-15 Both (Long + Short)", ["PDH_SHORT", "ORB_LONG", "ORB_SHORT"]),
        ("Portfolio 3: PDH Short + ORB-15 Long + VWAP Pullback", ["PDH_SHORT", "ORB_LONG", "VWAP_PULLBACK_LONG"]),
    ]

    print("=" * 120)
    print("      PARTE 2: CARTERAS DE MOTORES COMBINADOS (5 MNQ, HORIZONTE ESTRICTO <= 6 MESES / 125 SESIONES)")
    print("      50,000 Simulaciones Monte Carlo por Cartera | Trailing Drawdown Intradía Exacto de Apex")
    print("=" * 120)
    print(f"{'Estructura de Cartera':<48} | {'Trades/Yr':<9} {'OOS: PF':<7} {'Max DD ($)':<11} {'DD Buffer%':<10} {'P(Pass<=6M)':<13} {'Tasa Ruina'}")
    print("-" * 120)

    n_sims = 50000
    p_details = []

    for p_label, p_types in portfolios:
        tr_p, dd_p, d_pnl = simulate_portfolio(p_types, contracts=5, target_r=1.75)
        t_oos = [t for t in tr_p if t["is_oos"]]
        p_oos = np.array([t["net"] for t in t_oos]) if t_oos else np.array([0.0])
        pf_oos = p_oos[p_oos > 0].sum() / abs(p_oos[p_oos <= 0].sum()) if abs(p_oos[p_oos <= 0].sum()) > 0 else 0
        tr_per_yr = len(tr_p) / 4.77

        # Monte Carlo en ventana exacta de 125 días (6 meses)
        d_pnl_arr = np.array(d_pnl)
        pass_6m = 0
        fails = 0
        trade_steps = []

        for _ in range(n_sims):
            sim_daily = np.random.choice(d_pnl_arr, size=125, replace=True)
            bal = 50000.0
            peak = 50000.0
            floor = 47500.0
            for s_idx, d_ret in enumerate(sim_daily):
                bal += d_ret
                if bal > peak:
                    peak = bal
                    floor = 50100.0 if peak >= 52600.0 else peak - 2500.0
                if bal <= floor:
                    fails += 1
                    break
                if (bal - 50000.0) >= 3000.0:
                    pass_6m += 1
                    trade_steps.append(s_idx + 1)
                    break

        p_pass = (pass_6m / n_sims) * 100.0
        p_fail = (fails / n_sims) * 100.0
        dd_pct = (dd_p / 2500.0) * 100.0

        print(
            f"{p_label:<48} | {tr_per_yr:<9.1f} {pf_oos:<7.2f} ${dd_p:<10.2f} {dd_pct:<9.1f}% "
            f"{p_pass:<13.1f}% {p_fail:.2f}%"
        )
        p_details.append((p_label, tr_p))
    print("=" * 120 + "\n")

    # =========================================================================
    # PARTE 3: AUDITORÍA AÑO POR AÑO DE LA CARTERA DUAL CORE (2022 A 2026)
    # =========================================================================
    print("=" * 110)
    print("      PARTE 3: CONSISTENCIA AÑO POR AÑO DE LA CARTERA DUAL CORE (PDH SHORT + ORB-15 LONG)")
    print("      Comprobación del Salva-Vidas de 2024: ¿Cómo compensa el ORB Long el mercado alcista?")
    print("=" * 110)
    print(f"{'Año':<8} {'PDH Short PnL':<18} {'ORB Long PnL':<18} {'Cartera Total PnL':<20} {'Trades Totales'}")
    print("-" * 110)

    best_trades = p_details[1][1]  # Portfolio 1
    df_best = pd.DataFrame(best_trades)
    for yr in sorted(df_best["year"].unique()):
        sub_yr = df_best[df_best["year"] == yr]
        p_pdh = sub_yr[sub_yr["type"] == "PDH_SHORT"]["net"].sum()
        p_orb = sub_yr[sub_yr["type"] == "ORB_LONG"]["net"].sum()
        p_tot = sub_yr["net"].sum()
        print(f"{yr:<8} ${p_pdh:<17.2f} ${p_orb:<17.2f} ${p_tot:<19.2f} {len(sub_yr)} trades")
    print("=" * 110 + "\n")

if __name__ == "__main__":
    run_ultimate_portfolio_suite()
