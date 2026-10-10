from pathlib import Path
import pandas as pd
import numpy as np

def run_reality_check():
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

    # 1. Auditoría de barras: aislar estrictamente RTH (09:30 a 16:00 ET = 78 barras de 5m)
    rth_mask = (df["hour_min"] >= "09:30") & (df["hour_min"] <= "16:00")
    df_rth = df[rth_mask].copy()

    # Cálculo estricto de PDH sobre RTH previo
    daily_rth = df_rth.groupby("date").agg(d_high=("high", "max"))
    daily_rth["pdh"] = daily_rth["d_high"].shift(1)
    df_rth["pdh"] = df_rth["date"].map(daily_rth["pdh"])

    # VWAP acumulativo estricto RTH
    df_rth["tp"] = (df_rth["high"] + df_rth["low"] + df_rth["close"]) / 3.0
    df_rth["tp_vol"] = df_rth["tp"] * df_rth["volume"]
    df_rth["cum_tp_vol"] = df_rth.groupby("date")["tp_vol"].cumsum()
    df_rth["cum_vol"] = df_rth.groupby("date")["volume"].cumsum()
    df_rth["vwap"] = df_rth["cum_tp_vol"] / df_rth["cum_vol"]

    # SMA20 de volumen RTH
    df_rth["vol_sma20"] = df_rth.groupby("date")["volume"].transform(
        lambda s: s.rolling(20, min_periods=5).mean()
    )

    def simulate_realistic(data, contracts=3, target_r=1.50, slippage_ticks=1):
        """
        Slippage: en MNQ 1 tick = 0.25 pts ($0.50/contrato).
        Entrada: Open de la siguiente barra + slippage en contra.
        Salida: Si stop, se ejecuta con slippage en contra.
        Intrabarra: Stop Loss tiene prioridad absoluta sobre Target si ambos ocurren en la misma barra.
        """
        slip_pts = slippage_ticks * 0.25
        comm_per_trade = 1.24 * contracts  # $0.62 x 2 por contrato roundtrip

        dates = data["date"].values
        hour_mins = data["hour_min"].values
        opens = data["open"].values
        highs = data["high"].values
        lows = data["low"].values
        closes = data["close"].values
        vwaps = data["vwap"].values
        pdhs = data["pdh"].values
        vols = data["volume"].values
        vol_smas = data["vol_sma20"].values

        trades = []
        active = False
        entry_p = stop_p = target_p = 0.0
        pending_entry = False
        pending_signal = {}

        prev_date = None
        traded_today = False

        for i in range(len(data)):
            c_date = dates[i]
            c_time = hour_mins[i]
            o, h, l, c = opens[i], highs[i], lows[i], closes[i]

            if c_date != prev_date:
                traded_today = False
                prev_date = c_date
                active = False
                pending_entry = False

            # Ejecución de orden pendiente al OPEN de la barra actual (t+1)
            if pending_entry and not active:
                # Entramos corto: slippage nos hace vender más abajo
                entry_p = o - slip_pts
                raw_stop = (pending_signal["signal_high"] + 0.50) - entry_p
                stop_dist = min(max(raw_stop, 10.0), 22.0)
                stop_p = entry_p + stop_dist
                target_p = entry_p - (target_r * stop_dist)
                active = True
                pending_entry = False

            if active:
                closed = False
                exit_p = 0.0

                hit_stop = h >= stop_p
                hit_target = l <= target_p

                # Regla de peor caso intrabarra: Stop primero
                if hit_stop and hit_target:
                    closed = True
                    exit_p = max(o, stop_p) + slip_pts
                elif hit_stop:
                    closed = True
                    exit_p = max(o, stop_p) + slip_pts
                elif hit_target:
                    closed = True
                    exit_p = target_p  # Orden límite pasiva
                elif c_time >= "15:55":
                    closed = True
                    exit_p = c + slip_pts

                if closed:
                    pts = entry_p - exit_p
                    net = (pts * 2.0 * contracts) - comm_per_trade
                    trades.append({
                        "pnl": net,
                        "pts": pts,
                        "r_mult": pts / stop_dist if stop_dist > 0 else 0.0
                    })
                    active = False

            # Evaluación de señal en barra t
            if not active and not pending_entry and not traded_today:
                if "09:45" <= c_time <= "12:30":
                    pdh_val = pdhs[i]
                    vwap_val = vwaps[i]
                    v_val = vols[i]
                    v_sma = vol_smas[i]

                    if not np.isnan(pdh_val):
                        sweep_dist = h - pdh_val
                        vol_ok = not np.isnan(v_sma) and (v_val >= 1.0 * v_sma)

                        if 0 < sweep_dist <= 15.0 and c < pdh_val and c < vwap_val and vol_ok:
                            pending_entry = True
                            pending_signal = {"signal_high": h}
                            traded_today = True

        return trades

    # Separación cronológica
    is_data = df_rth[(df_rth.index >= "2022-01-01") & (df_rth.index < "2024-01-01")]
    oos_data = df_rth[df_rth.index >= "2024-01-01"]

    print("=" * 110)
    print("      TEST DE SENSIBILIDAD A DESLIZAMIENTO (SLIPPAGE) Y RELLENO EN BARRA T+1")
    print("=" * 110)
    print(f"{'Slippage Assumed':<22} | {'IS: N':<5} {'IS: WR':<7} {'IS: PF':<6} {'IS: PnL':<9} | {'OOS: N':<6} {'OOS: WR':<8} {'OOS: PF':<7} {'OOS: PnL':<9} {'OOS Expectancy':<15}")
    print("-" * 110)

    for s_ticks in [0, 1, 2, 3]:
        t_is = simulate_realistic(is_data, slippage_ticks=s_ticks)
        t_oos = simulate_realistic(oos_data, slippage_ticks=s_ticks)

        p_is = np.array([t["pnl"] for t in t_is]) if t_is else np.array([0.0])
        p_oos = np.array([t["pnl"] for t in t_oos]) if t_oos else np.array([0.0])

        wr_is = len(p_is[p_is > 0]) / len(p_is) * 100 if len(p_is) > 0 else 0
        wr_oos = len(p_oos[p_oos > 0]) / len(p_oos) * 100 if len(p_oos) > 0 else 0

        pf_is = p_is[p_is > 0].sum() / abs(p_is[p_is <= 0].sum()) if abs(p_is[p_is <= 0].sum()) > 0 else 0
        pf_oos = p_oos[p_oos > 0].sum() / abs(p_oos[p_oos <= 0].sum()) if abs(p_oos[p_oos <= 0].sum()) > 0 else 0

        exp_d = p_oos.mean() if len(p_oos) > 0 else 0

        label = f"{s_ticks} ticks ({s_ticks*0.25:.2f} pts/lado)"
        print(
            f"{label:<22} | {len(p_is):<5} {wr_is:<6.1f}% {pf_is:<6.2f} ${p_is.sum():<8.0f} | "
            f"{len(p_oos):<6} {wr_oos:<7.1f}% {pf_oos:<7.2f} ${p_oos.sum():<8.0f} ${exp_d:<14.2f}/trade"
        )
    print("=" * 110 + "\n")

    # BOOTSTRAP DE INCERTIDUMBRE (10,000 ITERACIONES SOBRE OOS REALISTA CON 1 TICK DE SLIPPAGE)
    t_realistic_oos = simulate_realistic(oos_data, slippage_ticks=1)
    p_arr = np.array([t["pnl"] for t in t_realistic_oos])
    r_arr = np.array([t["r_mult"] for t in t_realistic_oos])

    np.random.seed(42)
    n_boot = 10000
    boot_wr = []
    boot_pf = []
    boot_exp_r = []

    for _ in range(n_boot):
        sample_idx = np.random.choice(len(p_arr), size=len(p_arr), replace=True)
        s_p = p_arr[sample_idx]
        s_r = r_arr[sample_idx]

        wins = s_p[s_p > 0]
        losses = s_p[s_p <= 0]

        b_wr = len(wins) / len(s_p) * 100
        b_pf = wins.sum() / abs(losses.sum()) if abs(losses.sum()) > 0 else 1.0
        b_expr = s_r.mean()

        boot_wr.append(b_wr)
        boot_pf.append(b_pf)
        boot_exp_r.append(b_expr)

    print("=" * 90)
    print("   INTERVALOS DE CONFIANZA AL 95% (BOOTSTRAP N=10,000 SOBRE OOS 2024-2026)")
    print("   Condiciones: Ejecución Open[t+1] + 1 Tick Slippage + Regla Stop-First")
    print("=" * 90)
    print(f"  Muestra Analizada: N = {len(p_arr)} trades en OOS")
    print(f"  Win Rate Observado      : {len(p_arr[p_arr>0])/len(p_arr)*100:.1f}%  -->  IC 95%: [{np.percentile(boot_wr, 2.5):.1f}%, {np.percentile(boot_wr, 97.5):.1f}%]")
    print(f"  Profit Factor Observado : {p_arr[p_arr>0].sum()/abs(p_arr[p_arr<=0].sum()):.2f}   -->  IC 95%: [{np.percentile(boot_pf, 2.5):.2f}, {np.percentile(boot_pf, 97.5):.2f}]")
    print(f"  Expectativa R Observada : {r_arr.mean():.2f}R   -->  IC 95%: [{np.percentile(boot_exp_r, 2.5):.2f}R, {np.percentile(boot_exp_r, 97.5):.2f}R]")
    print(f"  P(Edge Real > 0) [P(PF > 1.0)]: {(np.array(boot_pf) > 1.0).mean() * 100:.2f}%")
    print("=" * 90 + "\n")

if __name__ == "__main__":
    run_reality_check()
