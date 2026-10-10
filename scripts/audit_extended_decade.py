from pathlib import Path
import pandas as pd
import numpy as np
import scipy.stats as stats

def run_extended_decade_audit():
    # Buscar dataset extendido o fallback al continuo disponible
    p_ext = Path("data/processed/nq_5m_extended.parquet")
    p_base = Path("data/processed/mnq_5m_continuous.parquet")

    data_path = p_ext if p_ext.exists() else p_base
    print("=" * 95)
    print(f"   OUROBOROS EXTENDED AUDIT ENGINE: {data_path.name}")
    print("=" * 95)

    df = pd.read_parquet(data_path)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df.set_index("timestamp", inplace=True)
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    if df.index.tz is None:
        df.index = df.index.tz_localize("America/New_York", ambiguous="NaT")
    else:
        df.index = df.index.tz_convert("America/New_York")

    df = df.sort_index()
    df["date"] = df.index.date
    df["hour_min"] = df.index.strftime("%H:%M")

    # Aislamiento estricto de sesión regular (09:30 a 16:00 ET = 78 barras de 5m)
    rth_mask = (df["hour_min"] >= "09:30") & (df["hour_min"] <= "16:00")
    df_rth = df[rth_mask].copy()

    # Cálculo estricto de PDH sobre RTH previo
    daily_rth = df_rth.groupby("date").agg(d_high=("high", "max"))
    daily_rth["pdh"] = daily_rth["d_high"].shift(1)
    df_rth["pdh"] = df_rth["date"].map(daily_rth["pdh"])

    # VWAP intradía acumulativo puro
    df_rth["tp"] = (df_rth["high"] + df_rth["low"] + df_rth["close"]) / 3.0
    df_rth["tp_vol"] = df_rth["tp"] * df_rth["volume"]
    df_rth["cum_tp_vol"] = df_rth.groupby("date")["tp_vol"].cumsum()
    df_rth["cum_vol"] = df_rth.groupby("date")["volume"].cumsum()
    df_rth["vwap"] = df_rth["cum_tp_vol"] / df_rth["cum_vol"]

    # SMA20 de volumen en sesión regular
    df_rth["vol_sma20"] = df_rth.groupby("date")["volume"].transform(
        lambda s: s.rolling(20, min_periods=5).mean()
    )

    def backtest_strict(sub_data, contracts=3, target_r=1.50, slip_ticks=1):
        slip_pts = slip_ticks * 0.25
        comm = 1.24 * contracts

        dates = sub_data["date"].values
        hour_mins = sub_data["hour_min"].values
        opens = sub_data["open"].values
        highs = sub_data["high"].values
        lows = sub_data["low"].values
        closes = sub_data["close"].values
        vwaps = sub_data["vwap"].values
        pdhs = sub_data["pdh"].values
        vols = sub_data["volume"].values
        vol_smas = sub_data["vol_sma20"].values
        timestamps = sub_data.index

        trades = []
        active = False
        entry_p = stop_p = target_p = 0.0
        pending = False
        sig_high = 0.0
        prev_date = None
        traded_today = False

        for i in range(len(sub_data)):
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
                entry_p = o - slip_pts
                raw_stop = (sig_high + 0.50) - entry_p
                stop_dist = min(max(raw_stop, 10.0), 22.0)
                stop_p = entry_p + stop_dist
                target_p = entry_p - (target_r * stop_dist)
                active = True
                pending = False

            if active:
                closed = False
                exit_p = 0.0

                hit_stop = h >= stop_p
                hit_target = l <= target_p

                # Resolución peor caso intrabarra
                if hit_stop and hit_target:
                    closed = True
                    exit_p = max(o, stop_p) + slip_pts
                elif hit_stop:
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
                    r_mult = pts / stop_dist if stop_dist > 0 else 0.0
                    trades.append({
                        "timestamp": timestamps[i],
                        "date": c_date,
                        "pnl": net,
                        "pts": pts,
                        "r_mult": r_mult,
                        "is_win": net > 0
                    })
                    active = False

            if not active and not pending and not traded_today:
                if "09:45" <= c_time <= "12:30":
                    pdh_val = pdhs[i]
                    vwap_val = vwaps[i]
                    v_val = vols[i]
                    v_sma = vol_smas[i]

                    if not np.isnan(pdh_val):
                        sweep_dist = h - pdh_val
                        vol_ok = not np.isnan(v_sma) and (v_val >= 1.0 * v_sma)

                        if 0 < sweep_dist <= 15.0 and c < pdh_val and c < vwap_val and vol_ok:
                            pending = True
                            sig_high = h
                            traded_today = True

        return trades

    # Ejecutar simulación completa
    all_trades = backtest_strict(df_rth)
    t_df = pd.DataFrame(all_trades)

    if t_df.empty:
        print("No se registraron operaciones con los filtros configurados.")
        return

    t_df["year"] = pd.to_datetime(t_df["date"]).dt.year
    total_years = (df_rth.index.max() - df_rth.index.min()).days / 365.25

    print(f"\nPeríodo analizado: {df_rth.index.min().date()} hasta {df_rth.index.max().date()} ({total_years:.1f} años)")
    print(f"Total Operaciones Registradas: {len(t_df)} (~{len(t_df)/total_years:.1f} trades/año)")

    # Rendimiento por Regímenes Históricos
    print("\n" + "-" * 95)
    print(f"{'Época / Ciclo de Mercado':<35} | {'N':<5} {'WinRate':<8} {'Profit Factor':<15} {'PnL Acum ($)':<14} {'Expectancy':<12}")
    print("-" * 95)

    year_splits = [
        ("Histórico Pre-2022 (2010-2021)", t_df["year"] < 2022),
        ("In-Sample (2022-2023: Bear Market)", (t_df["year"] >= 2022) & (t_df["year"] <= 2023)),
        ("Out-of-Sample Reciente (2024-2026)", t_df["year"] >= 2024),
        ("Muestra Total Completa", t_df["year"] >= 2000),
    ]

    for label, mask in year_splits:
        sub = t_df[mask]
        if len(sub) == 0:
            print(f"{label:<35} | {'0':<5} {'N/A':<8} {'N/A':<15} {'$0':<14} {'N/A':<12}")
            continue

        wins = sub[sub["pnl"] > 0]["pnl"]
        losses = sub[sub["pnl"] <= 0]["pnl"]
        wr = len(wins) / len(sub) * 100
        pf = wins.sum() / abs(losses.sum()) if abs(losses.sum()) > 0 else 999.0
        exp_r = sub["r_mult"].mean()
        print(f"{label:<35} | {len(sub):<5} {wr:<7.1f}% {pf:<15.2f} ${sub['pnl'].sum():<13.2f} {exp_r:<+.2f}R")

    print("-" * 95)

    # Bootstrap No Paramétrico
    p_arr = t_df["pnl"].values
    r_arr = t_df["r_mult"].values

    np.random.seed(42)
    n_boot = 10000
    boot_wr = []
    boot_pf = []
    boot_exp_r = []

    for _ in range(n_boot):
        idx = np.random.choice(len(p_arr), size=len(p_arr), replace=True)
        s_p = p_arr[idx]
        s_r = r_arr[idx]

        w = s_p[s_p > 0]
        l = s_p[s_p <= 0]
        boot_wr.append(len(w) / len(s_p) * 100)
        boot_pf.append(w.sum() / abs(l.sum()) if abs(l.sum()) > 0 else 1.0)
        boot_exp_r.append(s_r.mean())

    p_val_edge = (np.array(boot_exp_r) <= 0).mean()

    print("\n" + "=" * 95)
    print("      INFERENCIA ESTADÍSTICA ROBUSTA (BOOTSTRAP N=10,000 SOBRE MUESTRA DISPONIBLE)")
    print("=" * 95)
    print(f"  Tamaño de Muestra Evaluado (N) : {len(t_df)} operaciones")
    print(f"  Win Rate IC 95%                 : [{np.percentile(boot_wr, 2.5):.1f}%  a  {np.percentile(boot_wr, 97.5):.1f}%] (Observado: {len(p_arr[p_arr>0])/len(p_arr)*100:.1f}%)")
    print(f"  Profit Factor IC 95%            : [{np.percentile(boot_pf, 2.5):.2f}   a  {np.percentile(boot_pf, 97.5):.2f}] (Observado: {p_arr[p_arr>0].sum()/abs(p_arr[p_arr<=0].sum()):.2f})")
    print(f"  Expectativa R IC 95%            : [{np.percentile(boot_exp_r, 2.5):.2f}R  a  {np.percentile(boot_exp_r, 97.5):.2f}R] (Observada: {r_arr.mean():.2f}R)")
    print(f"  Probabilidad de Edge Real (PF>1): {(np.array(boot_pf) > 1.0).mean() * 100:.2f}%")
    print(f"  P-Valor Estadístico (H0: E[R]<=0): p = {p_val_edge:.4f}")
    print("=" * 95)

if __name__ == "__main__":
    run_extended_decade_audit()
