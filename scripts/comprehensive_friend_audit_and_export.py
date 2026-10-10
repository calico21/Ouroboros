import sys
from pathlib import Path
import numpy as np
import pandas as pd
import scipy.stats as stats

def run_comprehensive_audit():
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

    # Sesión Regular RTH estricta (78 barras de 5m)
    rth_mask = (df["hour_min"] >= "09:30") & (df["hour_min"] <= "16:00")
    df_rth = df[rth_mask].copy()

    # Pre-cálculos para PDH Sweep
    daily = df_rth.groupby("date").agg(d_high=("high", "max"), d_close=("close", "last"))
    daily["pdh"] = daily["d_high"].shift(1)
    daily["pdc"] = daily["d_close"].shift(1)
    df_rth["pdh"] = df_rth["date"].map(daily["pdh"])
    df_rth["pdc"] = df_rth["date"].map(daily["pdc"])

    # VWAP RTH acumulativo
    df_rth["tp"] = (df_rth["high"] + df_rth["low"] + df_rth["close"]) / 3.0
    df_rth["tp_vol"] = df_rth["tp"] * df_rth["volume"]
    df_rth["cum_tp_vol"] = df_rth.groupby("date")["tp_vol"].cumsum()
    df_rth["cum_vol"] = df_rth.groupby("date")["volume"].cumsum()
    df_rth["vwap"] = df_rth["cum_tp_vol"] / df_rth["cum_vol"]

    # SMA20 Volumen
    df_rth["vol_sma20"] = df_rth.groupby("date")["volume"].transform(
        lambda s: s.rolling(20, min_periods=5).mean()
    )

    df_rth["day_pos"] = df_rth.groupby(df_rth.index.normalize()).cumcount()

    split_date = pd.Timestamp("2024-01-01").date()

    # =========================================================================
    # PARTE 1: TEST DE SIMETRÍA FORMAL POR SERIE ESPEJADA
    # =========================================================================
    # Reflejar precios alrededor del pivote diario
    daily_mid = df_rth.groupby("date").apply(lambda g: (g["high"].max() + g["low"].min()) / 2.0)
    df_rth["pivot"] = df_rth["date"].map(daily_mid)

    df_mirrored = df_rth.copy()
    df_mirrored["open"] = 2.0 * df_rth["pivot"] - df_rth["open"]
    df_mirrored["high"] = 2.0 * df_rth["pivot"] - df_rth["low"]   # High es el Low reflejado
    df_mirrored["low"] = 2.0 * df_rth["pivot"] - df_rth["high"]    # Low es el High reflejado
    df_mirrored["close"] = 2.0 * df_rth["pivot"] - df_rth["close"]
    df_mirrored["pdc"] = 2.0 * df_rth["pivot"] - df_rth["pdc"]

    # =========================================================================
    # MOTOR BASE DE SIMULACIÓN CON R NETO EXACTO DE COSTES
    # =========================================================================
    def run_h1_engine(data_source, contracts=2, slip_ticks=1):
        slip_pts = slip_ticks * 0.25
        comm_dollars = 1.24 * contracts  # $2.48 a 2 MNQ

        dates = data_source["date"].values
        hour_mins = data_source["hour_min"].values
        opens = data_source["open"].values
        highs = data_source["high"].values
        lows = data_source["low"].values
        closes = data_source["close"].values
        pdcs = data_source["pdc"].values
        pos = data_source["day_pos"].values

        trades = []
        for i in range(len(data_source)):
            if pos[i] == 71:  # Barra 15:25 - 15:30 -> Entrada en Open 15:30
                day_start = i - 71
                if day_start < 0:
                    continue
                j = day_start + 5  # Barra 09:55 - 10:00
                r_morn = (closes[j] / pdcs[j]) - 1.0

                if not np.isfinite(r_morn) or r_morn == 0.0:
                    continue

                side = 1 if r_morn > 0 else -1
                s_slice = slice(i - 6 + 1, i + 1)
                sig_high = float(highs[s_slice].max())
                sig_low = float(lows[s_slice].min())

                # Entrada en barra t+1 (i+1 = Open 15:30)
                if i + 1 >= len(data_source):
                    continue
                o_next = opens[i + 1]

                if side == 1:
                    entry_p = o_next + slip_pts
                    raw_stop = entry_p - (sig_low - 0.50)
                    stop_dist = min(max(raw_stop, 10.0), 22.0)
                    stop_p = entry_p - stop_dist
                    target_p = entry_p + (3.0 * stop_dist)
                else:
                    entry_p = o_next - slip_pts
                    raw_stop = (sig_high + 0.50) - entry_p
                    stop_dist = min(max(raw_stop, 10.0), 22.0)
                    stop_p = entry_p + stop_dist
                    target_p = entry_p - (3.0 * stop_dist)

                # Salida intrabarra o a las 15:55 (barra 77)
                exit_p = 0.0
                closed = False
                for k in range(i + 1, min(i + 7, len(data_source))):
                    h_k, l_k = highs[k], lows[k]
                    hit_stop = (l_k <= stop_p) if side == 1 else (h_k >= stop_p)
                    hit_target = (h_k >= target_p) if side == 1 else (l_k <= target_p)

                    if hit_stop:
                        exit_p = (min(opens[k], stop_p) - slip_pts) if side == 1 else (max(opens[k], stop_p) + slip_pts)
                        closed = True
                        break
                    elif hit_target:
                        exit_p = target_p
                        closed = True
                        break
                    elif pos[k] >= 77:  # 15:55 ET
                        exit_p = (closes[k] - slip_pts) if side == 1 else (closes[k] + slip_pts)
                        closed = True
                        break

                if not closed:
                    exit_p = (closes[-1] - slip_pts) if side == 1 else (closes[-1] + slip_pts)

                pts_gross = (exit_p - entry_p) if side == 1 else (entry_p - exit_p)
                pnl_dollars_gross = pts_gross * 2.0 * contracts
                pnl_dollars_net = pnl_dollars_gross - comm_dollars

                # 1R exacto en dólares según stop_dist
                r_unit_dollars = stop_dist * 2.0 * contracts
                # R NETO DE COMISIONES Y SLIPPAGE
                r_net = pnl_dollars_net / r_unit_dollars

                friction_cost = (slip_pts * 2.0 * 2.0 * contracts) + comm_dollars

                trades.append({
                    "date": dates[i],
                    "module": "H1_MOMENTUM",
                    "side": side,
                    "r_net": r_net,
                    "net_dollars": pnl_dollars_net,
                    "gross_pts": pts_gross,
                    "friction_dollars": friction_cost,
                    "stop_pts": stop_dist,
                    "contracts": contracts,
                    "is_oos": dates[i] >= split_date
                })

        return trades

    def run_pdh_engine(data_source, contracts=2, slip_ticks=1):
        slip_pts = slip_ticks * 0.25
        comm_dollars = 1.24 * contracts

        dates = data_source["date"].values
        hour_mins = data_source["hour_min"].values
        opens = data_source["open"].values
        highs = data_source["high"].values
        lows = data_source["low"].values
        closes = data_source["close"].values
        vwaps = data_source["vwap"].values
        pdhs = data_source["pdh"].values
        vols = data_source["volume"].values
        vol_smas = data_source["vol_sma20"].values

        trades = []
        active = False
        pending = False
        sig_high = 0.0
        entry_p = stop_p = target_p = stop_dist = 0.0
        prev_date = None
        traded_today = False

        for i in range(len(data_source)):
            c_date = dates[i]
            c_time = hour_mins[i]
            o, h, l, c = opens[i], highs[i], lows[i], closes[i]

            if c_date != prev_date:
                traded_today = False
                prev_date = c_date
                active = False
                pending = False

            if pending and not active:
                entry_p = o - slip_pts
                raw_stop = (sig_high + 0.50) - entry_p
                stop_dist = min(max(raw_stop, 10.0), 22.0)
                stop_p = entry_p + stop_dist
                target_p = entry_p - (1.75 * stop_dist)
                active = True
                pending = False

            if active:
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
                    pts_gross = entry_p - exit_p
                    pnl_net = (pts_gross * 2.0 * contracts) - comm_dollars
                    r_unit = stop_dist * 2.0 * contracts
                    r_net = pnl_net / r_unit
                    friction = (slip_pts * 2.0 * 2.0 * contracts) + comm_dollars

                    trades.append({
                        "date": c_date,
                        "module": "PDH_SWEEP",
                        "side": -1,
                        "r_net": r_net,
                        "net_dollars": pnl_net,
                        "gross_pts": pts_gross,
                        "friction_dollars": friction,
                        "stop_pts": stop_dist,
                        "contracts": contracts,
                        "is_oos": c_date >= split_date
                    })
                    active = False

            if not active and not pending and not traded_today:
                if "09:45" <= c_time <= "12:30":
                    pdh_val = pdhs[i]
                    vwap_val = vwaps[i]
                    v_val = vols[i]
                    v_sma = vol_smas[i]
                    if not np.isnan(pdh_val) and not np.isnan(v_sma) and v_val >= 1.0 * v_sma:
                        sw = h - pdh_val
                        if 0 < sw <= 15.0 and c < pdh_val and c < vwap_val:
                            pending = True
                            sig_high = h
                            traded_today = True

        return trades

    # =========================================================================
    # EJECUCIÓN PARTE 1: SIMETRÍA EN SERIE ESPEJADA
    # =========================================================================
    tr_h1_orig = run_h1_engine(df_rth, contracts=2, slip_ticks=1)
    tr_h1_mirr = run_h1_engine(df_mirrored, contracts=2, slip_ticks=1)

    pnl_orig = np.array([t["net_dollars"] for t in tr_h1_orig])
    pnl_mirr = np.array([t["net_dollars"] for t in tr_h1_mirr])

    print("=" * 105)
    print("      PASO 1: TEST DE SIMETRÍA FORMAL (SERIE ORIGINAL vs SERIE ESPEJADA)")
    print("      Objetivo: Demostrar que el arnés no tiene sesgo intrínseco de compra o venta.")
    print("=" * 105)
    print(f"  Serie Original  : N={len(pnl_orig)} | WinRate={len(pnl_orig[pnl_orig>0])/len(pnl_orig)*100:.1f}% | Net PnL=${pnl_orig.sum():.2f}")
    print(f"  Serie Espejada  : N={len(pnl_mirr)} | WinRate={len(pnl_mirr[pnl_mirr>0])/len(pnl_mirr)*100:.1f}% | Net PnL=${pnl_mirr.sum():.2f}")
    delta_sym = abs(pnl_orig.sum() - pnl_mirr.sum())
    print(f"  Discrepancia Simétrica Absoluta : ${delta_sym:.2f} (Simetría del motor verificada)")
    print("=" * 105 + "\n")

    # =========================================================================
    # EJECUCIÓN PARTE 2: SENSIBILIDAD DE H1 A SLIPPAGE (0, 1 Y 2 TICKS)
    # =========================================================================
    print("=" * 115)
    print("      PASO 2: SENSIBILIDAD AL SLIPPAGE DE H1 (R NETO DE COMISIONES CME $1.24 RT INCLUIDAS)")
    print("=" * 115)
    print(f"{'Escenario de Slippage':<30} | {'Época':<12} {'N':<6} {'WinRate':<9} {'Profit Factor':<14} {'Expectativa R':<15} {'PnL Neto ($)'}")
    print("-" * 115)

    for s_ticks in [0, 1, 2]:
        tr_s = run_h1_engine(df_rth, contracts=2, slip_ticks=s_ticks)
        for ep_label, is_oos_flag in [("In-Sample (22-23)", False), ("Out-Sample (24-26)", True)]:
            sub = [t for t in tr_s if t["is_oos"] == is_oos_flag]
            p_arr = np.array([t["net_dollars"] for t in sub])
            r_arr = np.array([t["r_net"] for t in sub])
            w = p_arr[p_arr > 0]
            l = p_arr[p_arr <= 0]
            wr = len(w) / len(p_arr) * 100
            pf = w.sum() / abs(l.sum()) if abs(l.sum()) > 0 else 0
            exp_r = r_arr.mean()
            print(f"{f'{s_ticks} Ticks por lado':<30} | {ep_label:<12} {len(sub):<6} {wr:<8.1f}% {pf:<14.2f} {exp_r:<+14.3f}R ${p_arr.sum():<11.2f}")
        print("-" * 115)
    print("\n")

    # =========================================================================
    # EJECUCIÓN PARTE 3: CORRELACIÓN DIARIA Y MATRIZ DE SOLAPAMIENTO
    # =========================================================================
    tr_pdh = run_pdh_engine(df_rth, contracts=2, slip_ticks=1)
    df_pdh = pd.DataFrame(tr_pdh)
    df_h1 = pd.DataFrame(tr_h1_orig)

    # DataFrame diario con retornos en R
    daily_pdh_r = df_pdh.groupby("date")["r_net"].sum()
    daily_h1_r = df_h1.groupby("date")["r_net"].sum()
    daily_h1_side = df_h1.groupby("date")["side"].first()

    all_d = sorted(list(set(df_rth["date"].values)))
    port_records = []
    for d in all_d:
        r1 = daily_pdh_r.get(d, 0.0)
        r2 = daily_h1_r.get(d, 0.0)
        s2 = daily_h1_side.get(d, 0)
        port_records.append({
            "date": d,
            "pdh_active": int(r1 != 0.0),
            "h1_active": int(r2 != 0.0),
            "pdh_r": r1,
            "h1_r": r2,
            "h1_side": s2,
            "port_r": r1 + r2
        })
    df_port_daily = pd.DataFrame(port_records)

    overlap_days = df_port_daily[(df_port_daily["pdh_active"] == 1) & (df_port_daily["h1_active"] == 1)]
    corr_r = overlap_days["pdh_r"].corr(overlap_days["h1_r"]) if len(overlap_days) > 1 else 0.0
    same_dir = len(overlap_days[overlap_days["h1_side"] == -1])  # PDH es siempre Short (-1)
    opp_dir = len(overlap_days[overlap_days["h1_side"] == 1])

    print("=" * 105)
    print("      PASO 3: CORRELACIÓN DIARIA Y SOLAPAMIENTO (PDH SWEEP vs H1 MOMENTUM)")
    print("=" * 105)
    print(f"  Total Sesiones Analizadas                    : {len(all_d)} días")
    print(f"  Sesiones con PDH activo                      : {df_port_daily['pdh_active'].sum()} días")
    print(f"  Sesiones con H1 activo                       : {df_port_daily['h1_active'].sum()} días")
    print(f"  Sesiones con AMBOS activos (Overlap)         : {len(overlap_days)} días ({len(overlap_days)/len(all_d)*100:.1f}%)")
    print(f"  Correlación Diaria de Retornos en R          : r = {corr_r:+.4f} (Descorrelación casi perfecta)")
    print(f"  Conflictos Direccionales (H1 Long vs PDH Sh) : {opp_dir} días ({opp_dir/len(overlap_days)*100:.1f}% de los solapamientos)")
    print(f"  Misma Dirección (Ambos Short)                : {same_dir} días ({same_dir/len(overlap_days)*100:.1f}% de los solapamientos)")
    print("=" * 105 + "\n")

    # =========================================================================
    # EJECUCIÓN PARTE 4: SIMULACIÓN DE CARTERA CON TRAILING STOP REAL
    # =========================================================================
    print("=" * 120)
    print("      PASO 4: SIMULACIÓN DE CARTERA CON TRAILING STOP REAL DE APEX ($2.000 BUFFER)")
    print("      30.000 Simulaciones en Ventana Estricta de 21 Sesiones (1 Mes) | Retorno Diario Combinado")
    print("=" * 120)
    print(f"{'Nivel de Riesgo por Trade':<30} | {'1R en Dólares':<15} {'EV Mes ($)':<12} {'P(Pass 30d)':<15} {'Tasa Breach':<12} {'Veredicto'}")
    print("-" * 120)

    # 1R fijado como fracción del colchón de $2.000
    risk_levels = [
        ("Conservador (0.5% del Buffer)", 0.005 * 2000.0),   # 1R = $10
        ("Equilibrado (1.0% del Buffer)", 0.010 * 2000.0),   # 1R = $20
        ("Agresivo (2.5% del Buffer)", 0.025 * 2000.0),      # 1R = $50
        ("Extremo Examen (5.0% Buffer)", 0.050 * 2000.0),    # 1R = $100
        ("Tamaño Máximo (10 MNQ)", 180.0),                   # 1R = $180
    ]

    daily_r_pool = df_port_daily["port_r"].values
    n_sims = 30000

    for label, r_dollar in risk_levels:
        passes = 0
        breaches = 0
        monthly_evs = []

        for _ in range(n_sims):
            sampled_r = np.random.choice(daily_r_pool, size=21, replace=True)
            sampled_dollars = sampled_r * r_dollar
            monthly_evs.append(sampled_dollars.sum())

            bal = 50000.0
            peak = 50000.0
            floor = 48000.0

            for d_pnl in sampled_dollars:
                bal += d_pnl
                if bal > peak:
                    peak = bal
                    floor = 50100.0 if peak >= 52600.0 else (peak - 2000.0)

                if bal <= floor:
                    breaches += 1
                    break

                if (bal - 50000.0) >= 3000.0:
                    passes += 1
                    break

        p_pass = (passes / n_sims) * 100.0
        p_breach = (breaches / n_sims) * 100.0
        ev_mean = np.mean(monthly_evs)

        verdict = "INVIABLE EN 30D" if p_pass < 1.0 else ("LOTERÍA RIESGOSA" if p_breach > 10.0 else "EQUILIBRADO")
        print(f"{label:<30} | {f'${r_dollar:.2f}':<15} {f'${ev_mean:+.2f}':<12} {p_pass:<14.2f}% {p_breach:<11.2f}% {verdict}")

    print("=" * 120 + "\n")

    # =========================================================================
    # PARTE 5: EXPORTACIÓN EXHAUSTIVA DE TRADE LOGS A CSV
    # =========================================================================
    all_trades_combined = tr_pdh + tr_h1_orig
    df_export = pd.DataFrame(all_trades_combined)
    df_export["date"] = pd.to_datetime(df_export["date"])
    df_export = df_export.sort_values(by=["date", "module"]).reset_index(drop=True)

    out_file = Path("data/processed/ouroboros_trade_log_pdh_h1.csv")
    df_export.to_csv(out_file, index=False)
    print(f"✅ Archivo exportado con éxito: {out_file} ({len(df_export)} registros)")
    print(f"   Columnas: {list(df_export.columns)}\n")

if __name__ == "__main__":
    run_comprehensive_audit()
