import sys
from pathlib import Path
import numpy as np
import pandas as pd
import scipy.stats as stats

def run_smt_divergence_audit():
    data_dir = Path("data/processed")
    mnq_path = data_dir / "mnq_5m_continuous.parquet"
    mes_path = data_dir / "mes_5m_continuous.parquet"

    if not mnq_path.exists() or not mes_path.exists():
        print(f"❌ Error: Archivos no encontrados en {data_dir}.")
        return

    df_mnq = pd.read_parquet(mnq_path)
    df_mes = pd.read_parquet(mes_path)

    # Normalizar DatetimeIndex en America/New_York
    for d in [df_mnq, df_mes]:
        if "timestamp" in d.columns:
            d["timestamp"] = pd.to_datetime(d["timestamp"])
            d.set_index("timestamp", inplace=True)
        if not isinstance(d.index, pd.DatetimeIndex):
            d.index = pd.to_datetime(d.index)
        if d.index.tz is None:
            d.index = d.index.tz_localize("America/New_York")
        else:
            d.index = d.index.tz_convert("America/New_York")

    # Alinear ambos datasets al segundo exacto
    cols_nq = {"open": "open_nq", "high": "high_nq", "low": "low_nq", "close": "close_nq", "volume": "vol_nq"}
    cols_es = {"open": "open_es", "high": "high_es", "low": "low_es", "close": "close_es", "volume": "vol_es"}

    df_mnq = df_mnq.rename(columns=cols_nq)[list(cols_nq.values())]
    df_mes = df_mes.rename(columns=cols_es)[list(cols_es.values())]

    df = df_mnq.join(df_mes, how="inner").sort_index()

    df["date"] = df.index.date
    df["hour_min"] = df.index.strftime("%H:%M")

    # Sesión Regular RTH (09:30 a 16:00 ET = 78 barras)
    rth_mask = (df["hour_min"] >= "09:30") & (df["hour_min"] <= "16:00")
    df_rth = df[rth_mask].copy()

    # VWAP RTH para NQ
    df_rth["tp_nq"] = (df_rth["high_nq"] + df_rth["low_nq"] + df_rth["close_nq"]) / 3.0
    df_rth["tp_vol_nq"] = df_rth["tp_nq"] * df_rth["vol_nq"]
    df_rth["cum_tp_vol_nq"] = df_rth.groupby("date")["tp_vol_nq"].cumsum()
    df_rth["cum_vol_nq"] = df_rth.groupby("date")["vol_nq"].cumsum()
    df_rth["vwap_nq"] = df_rth["cum_tp_vol_nq"] / df_rth["cum_vol_nq"]

    df_rth["vol_sma_nq"] = df_rth.groupby("date")["vol_nq"].transform(
        lambda s: s.rolling(20, min_periods=5).mean()
    )

    # Máximos y Mínimos de sesión acumulados hasta barra t-1 (sin lookahead)
    df_rth["sess_h_nq"] = df_rth.groupby("date")["high_nq"].transform(lambda s: s.shift(1).expanding().max())
    df_rth["sess_l_nq"] = df_rth.groupby("date")["low_nq"].transform(lambda s: s.shift(1).expanding().min())
    df_rth["sess_h_es"] = df_rth.groupby("date")["high_es"].transform(lambda s: s.shift(1).expanding().max())
    df_rth["sess_l_es"] = df_rth.groupby("date")["low_es"].transform(lambda s: s.shift(1).expanding().min())

    # Swings móviles de 30 minutos (6 barras)
    df_rth["roll_h_nq"] = df_rth.groupby("date")["high_nq"].transform(lambda s: s.shift(1).rolling(6, min_periods=3).max())
    df_rth["roll_l_nq"] = df_rth.groupby("date")["low_nq"].transform(lambda s: s.shift(1).rolling(6, min_periods=3).min())
    df_rth["roll_h_es"] = df_rth.groupby("date")["high_es"].transform(lambda s: s.shift(1).rolling(6, min_periods=3).max())
    df_rth["roll_l_es"] = df_rth.groupby("date")["low_es"].transform(lambda s: s.shift(1).rolling(6, min_periods=3).min())

    dates = df_rth["date"].values
    hour_mins = df_rth["hour_min"].values

    opens_nq = df_rth["open_nq"].values
    highs_nq = df_rth["high_nq"].values
    lows_nq = df_rth["low_nq"].values
    closes_nq = df_rth["close_nq"].values
    vwaps_nq = df_rth["vwap_nq"].values
    vols_nq = df_rth["vol_nq"].values
    vol_smas_nq = df_rth["vol_sma_nq"].values

    highs_es = df_rth["high_es"].values
    lows_es = df_rth["low_es"].values

    sess_hs_nq = df_rth["sess_h_nq"].values
    sess_ls_nq = df_rth["sess_l_nq"].values
    sess_hs_es = df_rth["sess_h_es"].values
    sess_ls_es = df_rth["sess_l_es"].values

    roll_hs_nq = df_rth["roll_h_nq"].values
    roll_ls_nq = df_rth["roll_l_nq"].values
    roll_hs_es = df_rth["roll_h_es"].values
    roll_ls_es = df_rth["roll_l_es"].values

    split_date = pd.Timestamp("2024-01-01").date()
    contracts = 2
    point_val = 2.0 * contracts
    comm_dollars = 1.24 * contracts
    slip_pts = 0.25

    # =========================================================================
    # MOTOR DE EVALUACIÓN DE SEÑALES
    # =========================================================================
    def evaluate_smt_model(model_name="SESSION_EXTREME", target_r=1.50):
        trades = []
        active = False
        pending = False
        side = 0
        entry_p = stop_p = target_p = stop_dist = 0.0
        ref_extreme = 0.0
        prev_date = None
        traded_today = False

        for i in range(len(df_rth)):
            c_date = dates[i]
            c_time = hour_mins[i]
            o, h, l, c = opens_nq[i], highs_nq[i], lows_nq[i], closes_nq[i]

            if c_date != prev_date:
                traded_today = False
                prev_date = c_date
                active = False
                pending = False

            # Ejecución en Open[t+1]
            if pending and not active:
                if side == -1:  # SHORT
                    entry_p = o - slip_pts
                    raw_stop = (ref_extreme + 0.50) - entry_p
                    stop_dist = min(max(raw_stop, 8.0), 22.0)
                    stop_p = entry_p + stop_dist
                    target_p = entry_p - (target_r * stop_dist)
                else:          # LONG
                    entry_p = o + slip_pts
                    raw_stop = entry_p - (ref_extreme - 0.50)
                    stop_dist = min(max(raw_stop, 8.0), 22.0)
                    stop_p = entry_p - stop_dist
                    target_p = entry_p + (target_r * stop_dist)

                active = True
                pending = False

            if active:
                hit_stop = (h >= stop_p) if side == -1 else (l <= stop_p)
                hit_target = (l <= target_p) if side == -1 else (h >= target_p)
                closed = False
                exit_p = 0.0

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
                    net = (pts * point_val) - comm_dollars
                    risk = stop_dist * point_val
                    r_net = net / risk
                    trades.append({
                        "date": c_date, "side": side, "pts": pts,
                        "net": net, "r_net": r_net, "stop_pts": stop_dist,
                        "is_win": net > 0, "is_oos": c_date >= split_date
                    })
                    active = False

            # Detección SMT: Ventana matinal 09:45 a 11:30 ET
            if not active and not pending and not traded_today:
                if "09:45" <= c_time <= "11:30":
                    v_nq, v_sma_nq = vols_nq[i], vol_smas_nq[i]
                    vwap_nq = vwaps_nq[i]
                    vol_ok = not np.isnan(v_sma_nq) and (v_nq >= 1.0 * v_sma_nq)

                    if vol_ok:
                        h_es = highs_es[i]
                        l_es = lows_es[i]

                        # MODELO 1: SESSION EXTREME SMT
                        if model_name == "SESSION_EXTREME":
                            sh_nq, sl_nq = sess_hs_nq[i], sess_ls_nq[i]
                            sh_es, sl_es = sess_hs_es[i], sess_ls_es[i]

                            if not np.isnan(sh_nq) and not np.isnan(sh_es):
                                # Bearish SMT: NQ rompe session high, ES no lo rompe -> NQ cierra bajo VWAP
                                if h > sh_nq and h_es <= sh_es and c < vwap_nq and c < o:
                                    pending = True
                                    side = -1
                                    ref_extreme = h
                                    traded_today = True

                                # Bullish SMT: NQ rompe session low, ES no lo rompe -> NQ cierra sobre VWAP
                                elif l < sl_nq and l_es >= sl_es and c > vwap_nq and c > o:
                                    pending = True
                                    side = 1
                                    ref_extreme = l
                                    traded_today = True

                        # MODELO 2: ROLLING 30M SWING SMT
                        elif model_name == "ROLLING_30M_SWING":
                            rh_nq, rl_nq = roll_hs_nq[i], roll_ls_nq[i]
                            rh_es, rl_es = roll_hs_es[i], roll_ls_es[i]

                            if not np.isnan(rh_nq) and not np.isnan(rh_es):
                                if h > rh_nq and h_es <= rh_es and c < vwap_nq:
                                    pending = True
                                    side = -1
                                    ref_extreme = h
                                    traded_today = True
                                elif l < rl_nq and l_es >= rl_es and c > vwap_nq:
                                    pending = True
                                    side = 1
                                    ref_extreme = l
                                    traded_today = True

                        # MODELO 3: SESSION EXTREME SHORT-ONLY
                        elif model_name == "SESSION_SHORT_ONLY":
                            sh_nq, sh_es = sess_hs_nq[i], sess_hs_es[i]
                            if not np.isnan(sh_nq) and not np.isnan(sh_es):
                                if h > sh_nq and h_es <= sh_es and c < vwap_nq and c < o:
                                    pending = True
                                    side = -1
                                    ref_extreme = h
                                    traded_today = True

                        # MODELO 4: WEAKNESS LEAD SHORT (ES Sweeps, NQ Fails to follow)
                        elif model_name == "WEAKNESS_LEAD_SHORT":
                            sh_nq, sh_es = sess_hs_nq[i], sess_hs_es[i]
                            if not np.isnan(sh_nq) and not np.isnan(sh_es):
                                # ES rompe máximo, pero NQ muestra debilidad y no lo supera
                                if h_es > sh_es and h <= sh_nq and c < vwap_nq and c < o:
                                    pending = True
                                    side = -1
                                    ref_extreme = h
                                    traded_today = True

        return trades

    # =========================================================================
    # REPORTE DE RESULTADOS
    # =========================================================================
    configurations = [
        ("1. SMT Session Extreme (Both Sides)", "SESSION_EXTREME", 1.50),
        ("2. SMT Rolling 30m Swing (Both Sides)", "ROLLING_30M_SWING", 1.50),
        ("3. SMT Session Extreme (Short-Only)", "SESSION_SHORT_ONLY", 1.50),
        ("4. SMT Relative Weakness (ES Sweeps)", "WEAKNESS_LEAD_SHORT", 1.50),
    ]

    print("=" * 120)
    print("      AUDITORÍA DE DIVERGENCIA INTERMERCADO SMT (NQ vs ES | 2022-2026)")
    print("      Condiciones: Entrada Open[t+1], 1 Tick Slip por lado, Comisiones CME $1.24 RT, Stop-First")
    print("=" * 120)
    print(f"{'Variante SMT Evaluada':<35} | {'Trades/Mes':<10} {'IS: PF':<7} {'OOS: WR':<8} {'OOS: PF':<7} {'OOS Net ($)':<12} {'E[R] OOS':<10} {'IC 95% Bootstrap'}")
    print("-" * 120)

    for label, m_name, tgt_r in configurations:
        tr = evaluate_smt_model(m_name, target_r=tgt_r)
        if not tr:
            print(f"{label:<35} | {'0':<10} {'N/A':<7} {'N/A':<8} {'N/A':<7} {'$0':<12} {'N/A':<10} {'N/A'}")
            continue

        t_is = [t for t in tr if not t["is_oos"]]
        t_oos = [t for t in tr if t["is_oos"]]

        p_is = np.array([t["net"] for t in t_is]) if t_is else np.array([0.0])
        p_oos = np.array([t["net"] for t in t_oos]) if t_oos else np.array([0.0])
        r_oos = np.array([t["r_net"] for t in t_oos]) if t_oos else np.array([0.0])

        pf_is = p_is[p_is > 0].sum() / abs(p_is[p_is <= 0].sum()) if abs(p_is[p_is <= 0].sum()) > 0 else 0
        pf_oos = p_oos[p_oos > 0].sum() / abs(p_oos[p_oos <= 0].sum()) if abs(p_oos[p_oos <= 0].sum()) > 0 else 0
        wr_oos = len(p_oos[p_oos > 0]) / len(p_oos) * 100 if len(p_oos) > 0 else 0
        exp_r_oos = r_oos.mean() if len(r_oos) > 0 else 0

        boot = [np.random.choice(r_oos, size=len(r_oos), replace=True).mean() for _ in range(5000)] if len(r_oos) > 5 else [0.0]
        ci_low = np.percentile(boot, 2.5)
        ci_high = np.percentile(boot, 97.5)

        tr_per_month = len(tr) / 57.2

        print(
            f"{label:<35} | {tr_per_month:<10.1f} {pf_is:<7.2f} {wr_oos:<7.1f}% {pf_oos:<7.2f} "
            f"${p_oos.sum():<11.2f} {exp_r_oos:<+9.3f}R [{ci_low:+.2f}R, {ci_high:+.2f}R]"
        )

    print("=" * 120 + "\n")

if __name__ == "__main__":
    run_smt_divergence_audit()
