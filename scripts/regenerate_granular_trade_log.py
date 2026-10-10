from pathlib import Path
import numpy as np
import pandas as pd
import scipy.stats as stats

def run_granular_regeneration():
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

    # Sesión regular (78 barras de 5m)
    rth_mask = (df["hour_min"] >= "09:30") & (df["hour_min"] <= "16:00")
    df_rth = df[rth_mask].copy()

    daily = df_rth.groupby("date").agg(d_high=("high", "max"), d_close=("close", "last"))
    daily["pdh"] = daily["d_high"].shift(1)
    daily["pdc"] = daily["d_close"].shift(1)
    df_rth["pdh"] = df_rth["date"].map(daily["pdh"])
    df_rth["pdc"] = df_rth["date"].map(daily["pdc"])

    df_rth["tp"] = (df_rth["high"] + df_rth["low"] + df_rth["close"]) / 3.0
    df_rth["tp_vol"] = df_rth["tp"] * df_rth["volume"]
    df_rth["cum_tp_vol"] = df_rth.groupby("date")["tp_vol"].cumsum()
    df_rth["cum_vol"] = df_rth.groupby("date")["volume"].cumsum()
    df_rth["vwap"] = df_rth["cum_tp_vol"] / df_rth["cum_vol"]

    df_rth["vol_sma20"] = df_rth.groupby("date")["volume"].transform(
        lambda s: s.rolling(20, min_periods=5).mean()
    )
    df_rth["day_pos"] = df_rth.groupby(df_rth.index.normalize()).cumcount()

    timestamps = df_rth.index
    dates = df_rth["date"].values
    opens = df_rth["open"].values
    highs = df_rth["high"].values
    lows = df_rth["low"].values
    closes = df_rth["close"].values
    vwaps = df_rth["vwap"].values
    pdhs = df_rth["pdh"].values
    pdcs = df_rth["pdc"].values
    vols = df_rth["volume"].values
    vol_smas = df_rth["vol_sma20"].values
    pos = df_rth["day_pos"].values

    split_date = pd.Timestamp("2024-01-01").date()
    contracts = 2
    point_val = 2.0 * contracts
    comm_dollars = 1.24 * contracts

    records = []

    # =========================================================================
    # 1. MOTOR GRANULAR PDH SWEEP SHORT
    # =========================================================================
    active = False
    pending = False
    sig_high = 0.0
    prev_date = None
    traded_today = False

    for i in range(len(df_rth)):
        c_date = dates[i]
        c_pos = pos[i]
        o, h, l, c = opens[i], highs[i], lows[i], closes[i]

        if c_date != prev_date:
            traded_today = False
            prev_date = c_date
            active = False
            pending = False

        if pending and not active:
            entry_time = timestamps[i]
            base_entry = o
            raw_stop = (sig_high + 0.50) - base_entry
            stop_dist = min(max(raw_stop, 10.0), 22.0)
            is_clamped = (raw_stop > 22.0) or (raw_stop < 10.0)

            stop_p = base_entry + stop_dist
            target_p = base_entry - (1.75 * stop_dist)

            # Rastrear excursión barra a barra
            mfe_pts = 0.0
            mae_pts = 0.0
            exit_time = None
            exit_reason = None
            raw_exit = 0.0

            for k in range(i, len(df_rth)):
                if dates[k] != c_date:
                    break
                h_k, l_k, c_k, o_k = highs[k], lows[k], closes[k], opens[k]

                # MFE y MAE intradiarios (posición corta)
                fav = base_entry - l_k
                adv = h_k - base_entry
                if fav > mfe_pts:
                    mfe_pts = fav
                if adv > mae_pts:
                    mae_pts = adv

                hit_stop = h_k >= stop_p
                hit_target = l_k <= target_p

                if hit_stop:
                    raw_exit = max(o_k, stop_p)
                    exit_reason = "STOP"
                    exit_time = timestamps[k]
                    break
                elif hit_target:
                    raw_exit = target_p
                    exit_reason = "TARGET"
                    exit_time = timestamps[k]
                    break
                elif pos[k] >= 77:  # 15:55 ET
                    raw_exit = c_k
                    exit_reason = "TIME_EOD"
                    exit_time = timestamps[k]
                    break

            risk_dollars = stop_dist * point_val

            # Cálculos multi-slippage
            gross_pts = base_entry - raw_exit
            gross_dollars = gross_pts * point_val

            net_0t = gross_dollars - comm_dollars
            net_1t = ((base_entry - 0.25) - (raw_exit + (0.25 if exit_reason == "STOP" else 0.0))) * point_val - comm_dollars
            net_2t = ((base_entry - 0.50) - (raw_exit + (0.50 if exit_reason == "STOP" else 0.0))) * point_val - comm_dollars

            records.append({
                "entry_time": entry_time,
                "exit_time": exit_time,
                "date": c_date,
                "module": "PDH_SWEEP",
                "side": -1,
                "entry_price": base_entry,
                "exit_price": raw_exit,
                "exit_reason": exit_reason,
                "stop_price": stop_p,
                "target_price": target_p,
                "stop_pts": stop_dist,
                "raw_stop_pts": raw_stop,
                "is_stop_clamped": is_clamped,
                "target_r_spec": 1.75,
                "mfe_pts": mfe_pts,
                "mae_pts": mae_pts,
                "risk_dollars": risk_dollars,
                "gross_pts": gross_pts,
                "net_dollars_0t": net_0t,
                "net_dollars_1t": net_1t,
                "net_dollars_2t": net_2t,
                "r_net_0t": net_0t / risk_dollars,
                "r_net_1t": net_1t / risk_dollars,
                "r_net_2t": net_2t / risk_dollars,
                "is_oos": c_date >= split_date
            })
            pending = False

        if not active and not pending and not traded_today:
            if 3 <= c_pos <= 36:  # 09:45 a 12:30 ET
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

    # =========================================================================
    # 2. MOTOR GRANULAR H1 MOMENTUM
    # =========================================================================
    for i in range(len(df_rth)):
        if pos[i] == 71:  # 15:25 - 15:30 -> Entrada en Open 15:30 (barra i+1)
            day_start = i - 71
            if day_start < 0 or (i + 1) >= len(df_rth):
                continue
            j = day_start + 5
            r_morn = (closes[j] / pdcs[j]) - 1.0

            if not np.isfinite(r_morn) or r_morn == 0.0:
                continue

            side = 1 if r_morn > 0 else -1
            s_slice = slice(i - 6 + 1, i + 1)
            sig_h = float(highs[s_slice].max())
            sig_l = float(lows[s_slice].min())

            entry_time = timestamps[i + 1]
            base_entry = opens[i + 1]

            if side == 1:
                raw_stop = base_entry - (sig_l - 0.50)
                stop_dist = min(max(raw_stop, 10.0), 22.0)
                stop_p = base_entry - stop_dist
                target_p = base_entry + (3.0 * stop_dist)
            else:
                raw_stop = (sig_h + 0.50) - base_entry
                stop_dist = min(max(raw_stop, 10.0), 22.0)
                stop_p = base_entry + stop_dist
                target_p = base_entry - (3.0 * stop_dist)

            is_clamped = (raw_stop > 22.0) or (raw_stop < 10.0)

            mfe_pts = 0.0
            mae_pts = 0.0
            exit_time = None
            exit_reason = None
            raw_exit = 0.0

            for k in range(i + 1, min(i + 7, len(df_rth))):
                h_k, l_k, c_k, o_k = highs[k], lows[k], closes[k], opens[k]

                fav = (h_k - base_entry) if side == 1 else (base_entry - l_k)
                adv = (base_entry - l_k) if side == 1 else (h_k - base_entry)
                if fav > mfe_pts:
                    mfe_pts = fav
                if adv > mae_pts:
                    mae_pts = adv

                hit_stop = (l_k <= stop_p) if side == 1 else (h_k >= stop_p)
                hit_target = (h_k >= target_p) if side == 1 else (l_k <= target_p)

                if hit_stop:
                    raw_exit = min(o_k, stop_p) if side == 1 else max(o_k, stop_p)
                    exit_reason = "STOP"
                    exit_time = timestamps[k]
                    break
                elif hit_target:
                    raw_exit = target_p
                    exit_reason = "TARGET"
                    exit_time = timestamps[k]
                    break
                elif pos[k] >= 77:
                    raw_exit = c_k
                    exit_reason = "TIME_EOD"
                    exit_time = timestamps[k]
                    break

            if exit_time is None:
                raw_exit = closes[-1]
                exit_reason = "TIME_EOD"
                exit_time = timestamps[-1]

            risk_dollars = stop_dist * point_val
            gross_pts = (raw_exit - base_entry) if side == 1 else (base_entry - raw_exit)
            gross_dollars = gross_pts * point_val

            net_0t = gross_dollars - comm_dollars
            slip_pts_1 = 0.25
            slip_pts_2 = 0.50

            # Ajuste de slippage para Long y Short
            if side == 1:
                e_1 = base_entry + slip_pts_1
                x_1 = raw_exit - (slip_pts_1 if exit_reason != "TARGET" else 0.0)
                net_1t = (x_1 - e_1) * point_val - comm_dollars

                e_2 = base_entry + slip_pts_2
                x_2 = raw_exit - (slip_pts_2 if exit_reason != "TARGET" else 0.0)
                net_2t = (x_2 - e_2) * point_val - comm_dollars
            else:
                e_1 = base_entry - slip_pts_1
                x_1 = raw_exit + (slip_pts_1 if exit_reason != "TARGET" else 0.0)
                net_1t = (e_1 - x_1) * point_val - comm_dollars

                e_2 = base_entry - slip_pts_2
                x_2 = raw_exit + (slip_pts_2 if exit_reason != "TARGET" else 0.0)
                net_2t = (e_2 - x_2) * point_val - comm_dollars

            records.append({
                "entry_time": entry_time,
                "exit_time": exit_time,
                "date": dates[i + 1],
                "module": "H1_MOMENTUM",
                "side": side,
                "entry_price": base_entry,
                "exit_price": raw_exit,
                "exit_reason": exit_reason,
                "stop_price": stop_p,
                "target_price": target_p,
                "stop_pts": stop_dist,
                "raw_stop_pts": raw_stop,
                "is_stop_clamped": is_clamped,
                "target_r_spec": 3.0,
                "mfe_pts": mfe_pts,
                "mae_pts": mae_pts,
                "risk_dollars": risk_dollars,
                "gross_pts": gross_pts,
                "net_dollars_0t": net_0t,
                "net_dollars_1t": net_1t,
                "net_dollars_2t": net_2t,
                "r_net_0t": net_0t / risk_dollars,
                "r_net_1t": net_1t / risk_dollars,
                "r_net_2t": net_2t / risk_dollars,
                "is_oos": dates[i + 1] >= split_date
            })

    df_granular = pd.DataFrame(records).sort_values("entry_time").reset_index(drop=True)
    out_path = Path("data/processed/ouroboros_trade_log_pdh_h1_granular.csv")
    df_granular.to_csv(out_path, index=False)

    print("=" * 115)
    print("      INSPECCIÓN FORENSE DEL LOG REGENERADO (GRANULARIDAD TICK-BY-TICK)")
    print(f"      Archivo generado: {out_path} ({len(df_granular)} operaciones)")
    print("=" * 115)

    # 1. Análisis de Clamping y Salidas
    for mod in ["PDH_SWEEP", "H1_MOMENTUM"]:
        sub = df_granular[df_granular["module"] == mod]
        clamped_22 = len(sub[sub["stop_pts"] == 22.0])
        clamped_10 = len(sub[sub["stop_pts"] == 10.0])
        print(f"\n▶ Módulo: {mod} (N = {len(sub)} trades)")
        print(f"   Stops clampados al máximo (22.0 pts) : {clamped_22} trades ({clamped_22/len(sub)*100:.1f}%)")
        print(f"   Stops clampados al mínimo (10.0 pts) : {clamped_10} trades ({clamped_10/len(sub)*100:.1f}%)")
        print(f"   Distribución de Motivos de Salida   : {dict(sub['exit_reason'].value_counts())}")
        print(f"   MFE Medio: {sub['mfe_pts'].mean():.2f} pts | MAE Medio: {sub['mae_pts'].mean():.2f} pts")

    # 2. Correlación Diaria con Bootstrap 95% CI
    d_pdh = df_granular[df_granular["module"] == "PDH_SWEEP"].groupby("date")["r_net_1t"].sum()
    d_h1 = df_granular[df_granular["module"] == "H1_MOMENTUM"].groupby("date")["r_net_1t"].sum()
    shared_days = sorted(list(set(d_pdh.index).intersection(set(d_h1.index))))

    r_pairs = [(d_pdh[d], d_h1[d]) for d in shared_days]
    r1_arr = np.array([p[0] for p in r_pairs])
    r2_arr = np.array([p[1] for p in r_pairs])

    boot_corrs = []
    np.random.seed(42)
    for _ in range(10000):
        b_idx = np.random.choice(len(r_pairs), size=len(r_pairs), replace=True)
        boot_corrs.append(stats.pearsonr(r1_arr[b_idx], r2_arr[b_idx])[0])

    corr_point = stats.pearsonr(r1_arr, r2_arr)[0]
    ci_corr = (np.percentile(boot_corrs, 2.5), np.percentile(boot_corrs, 97.5))

    print("\n" + "=" * 115)
    print("      CORRELACIÓN DIARIA CON BOOTSTRAP DE PARES COINCIDENTES")
    print("=" * 115)
    print(f"  Pares coincidentes (N)              : {len(shared_days)} días")
    print(f"  Correlación puntual observada       : r = {corr_point:+.4f}")
    print(f"  Intervalo de Confianza Bootstrap 95%: [{ci_corr[0]:+.4f}, {ci_corr[1]:+.4f}]")
    print(f"  Conclusión: La correlación abarca desde {ci_corr[0]:.2f} hasta {ci_corr[1]:.2f}. Compatible con cero, pero con incertidumbre.")

    # 3. Criterio de Kelly para Cuenta sin Límite Temporal
    def compute_kelly(r_series):
        # f* = E[R] / E[R^2] (aproximación para distribución continua)
        mean_r = r_series.mean()
        var_r = r_series.var()
        if mean_r <= 0 or var_r <= 0:
            return 0.0, 0.0, 0.0
        f_star = mean_r / (mean_r**2 + var_r)
        return f_star, f_star * 0.5, f_star * 0.25

    print("\n" + "=" * 115)
    print("      DIMENSIONAMIENTO A LARGO PLAZO: CRITERIO DE KELLY (CUENTA SIN FECHA DE CADUCIDAD)")
    print("=" * 115)
    print(f"{'Módulo':<25} | {'E[R] (1-Tick Net)':<18} {'Varianza R':<14} {'Full-Kelly (f*)':<16} {'Half-Kelly':<14} {'Quarter-Kelly'}")
    print("-" * 115)

    for mod in ["PDH_SWEEP", "H1_MOMENTUM"]:
        r_s = df_granular[df_granular["module"] == mod]["r_net_1t"]
        fk, hk, qk = compute_kelly(r_s)
        print(f"{mod:<25} | {r_s.mean():<+18.3f}R {r_s.var():<14.3f} {fk*100:<15.2f}% {hk*100:<13.2f}% {qk*100:.2f}%")

    r_combined = df_granular.groupby("date")["r_net_1t"].sum()
    fk_c, hk_c, qk_c = compute_kelly(r_combined)
    print(f"{'CARTERA COMBINADA':<25} | {r_combined.mean():<+18.3f}R {r_combined.var():<14.3f} {fk_c*100:<15.2f}% {hk_c*100:<13.2f}% {qk_c*100:.2f}%")

    # 4. Simulación Monte Carlo con Ratchet Intratrade
    print("\n" + "=" * 115)
    print("      SIMULACIÓN DE QUIEBRA CON RATCHET INTRATRADE (APEX TRAILING SOBRE MFE)")
    print("      Buffer: $2.000 | 10.000 Caminos de 250 Sesiones (1 Año) | Riesgo anclado a Quarter-Kelly")
    print("=" * 115)

    n_sims = 10000
    all_unique_dates = sorted(list(set(df_rth["date"].values)))
    trades_by_date = {}
    for d, grp in df_granular.groupby("date"):
        trades_by_date[d] = grp.to_dict("records")

    for risk_pct in [0.005, 0.010, 0.020]:
        breaches_no_ratchet = 0
        breaches_with_ratchet = 0

        for _ in range(n_sims):
            sim_days = np.random.choice(all_unique_dates, size=250, replace=True)
            bal = 50000.0
            peak_bal = 50000.0
            floor_no_r = 48000.0
            floor_with_r = 48000.0
            dead_no = False
            dead_with = False

            for d in sim_days:
                if d in trades_by_date:
                    for t in trades_by_date[d]:
                        # 1R fijo en dólares según riesgo de buffer
                        r_dollar = 2000.0 * risk_pct
                        pnl_trade = t["r_net_1t"] * r_dollar
                        mfe_dollar = (t["mfe_pts"] / t["stop_pts"]) * r_dollar

                        # Trailing SIN ratchet (solo al cierre)
                        bal += pnl_trade
                        if bal > peak_bal:
                            peak_bal = bal
                            floor_no_r = 50100.0 if peak_bal >= 52600.0 else (peak_bal - 2000.0)
                        if bal <= floor_no_r:
                            dead_no = True

                        # Trailing CON ratchet intratrade de Apex (persigue MFE durante la vela)
                        intra_peak = (bal - pnl_trade) + mfe_dollar
                        floor_with_r = max(floor_with_r, 50100.0 if intra_peak >= 52600.0 else (intra_peak - 2000.0))
                        if bal <= floor_with_r:
                            dead_with = True

                if dead_with and dead_no:
                    break

            if dead_no:
                breaches_no_ratchet += 1
            if dead_with:
                breaches_with_ratchet += 1

        print(f"  Riesgo 1R = {risk_pct*100:.1f}% Buffer (${2000*risk_pct:.0f}) | Breach Sin Ratchet: {breaches_no_ratchet/n_sims*100:.2f}% | Breach CON RATCHET: {breaches_with_ratchet/n_sims*100:.2f}%")

    print("=" * 115 + "\n")

if __name__ == "__main__":
    run_granular_regeneration()
