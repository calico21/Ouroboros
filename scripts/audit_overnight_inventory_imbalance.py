import sys
from pathlib import Path
import numpy as np
import pandas as pd
import scipy.stats as stats

def run_overnight_inventory_audit():
    data_path = Path("data/processed/mnq_5m_continuous.parquet")
    if not data_path.exists():
        print(f"❌ Error: {data_path} no encontrado.")
        return

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

    # 1. Separar RTH y Pre-market
    rth_mask = (df["hour_min"] >= "09:30") & (df["hour_min"] <= "16:00")
    df_rth = df[rth_mask].copy()

    # Cálculo estricto de PDC (Cierre de la sesión regular anterior)
    daily_close = df_rth.groupby("date")["close"].last()
    pdc_series = daily_close.shift(1)
    df_rth["pdc"] = df_rth["date"].map(pdc_series)

    # 2. Análisis del inventario Overnight (pre-market del mismo día: 00:00 a 09:29 ET)
    df_pm = df[df["hour_min"] < "09:30"].copy()
    df_pm["pdc"] = df_pm["date"].map(pdc_series)

    # Métricas nocturnas por día
    def compute_pm_stats(g):
        pdc_val = g["pdc"].iloc[0]
        if np.isnan(pdc_val):
            return pd.Series({
                "on_high": np.nan, "on_low": np.nan, "on_vol": 0,
                "vol_above_pdc": 0, "pct_above_pdc": np.nan,
                "strict_long": False, "strict_short": False
            })
        
        on_h = g["high"].max()
        on_l = g["low"].min()
        tot_vol = g["volume"].sum()
        vol_above = g[g["close"] > pdc_val]["volume"].sum()
        pct_above = (vol_above / tot_vol) if tot_vol > 0 else 0.5
        
        return pd.Series({
            "on_high": on_h,
            "on_low": on_l,
            "on_vol": tot_vol,
            "vol_above_pdc": vol_above,
            "pct_above_pdc": pct_above,
            "strict_long": on_l > pdc_val,   # 100% de la noche por encima de PDC
            "strict_short": on_h < pdc_val   # 100% de la noche por debajo de PDC
        })

    pm_stats = df_pm.groupby("date").apply(compute_pm_stats, include_groups=False)

    df_rth["on_high"] = df_rth["date"].map(pm_stats["on_high"])
    df_rth["on_low"] = df_rth["date"].map(pm_stats["on_low"])
    df_rth["pct_above_pdc"] = df_rth["date"].map(pm_stats["pct_above_pdc"])
    df_rth["strict_long"] = df_rth["date"].map(pm_stats["strict_long"])
    df_rth["strict_short"] = df_rth["date"].map(pm_stats["strict_short"])

    # VWAP RTH Acumulativo
    df_rth["tp"] = (df_rth["high"] + df_rth["low"] + df_rth["close"]) / 3.0
    df_rth["tp_vol"] = df_rth["tp"] * df_rth["volume"]
    df_rth["cum_tp_vol"] = df_rth.groupby("date")["tp_vol"].cumsum()
    df_rth["cum_vol"] = df_rth.groupby("date")["volume"].cumsum()
    df_rth["vwap"] = df_rth["cum_tp_vol"] / df_rth["cum_vol"]

    # SMA20 Volumen
    df_rth["vol_sma20"] = df_rth.groupby("date")["volume"].transform(
        lambda s: s.rolling(20, min_periods=5).mean()
    )

    # Apertura de RTH
    rth_open_series = df_rth[df_rth["hour_min"] == "09:30"].groupby("date")["open"].first()
    df_rth["rth_open"] = df_rth["date"].map(rth_open_series)

    dates = df_rth["date"].values
    hour_mins = df_rth["hour_min"].values
    opens = df_rth["open"].values
    highs = df_rth["high"].values
    lows = df_rth["low"].values
    closes = df_rth["close"].values
    vwaps = df_rth["vwap"].values
    pdcs = df_rth["pdc"].values
    rth_opens = df_rth["rth_open"].values
    vols = df_rth["volume"].values
    vol_smas = df_rth["vol_sma20"].values

    strict_longs = df_rth["strict_long"].values
    strict_shorts = df_rth["strict_short"].values
    pct_aboves = df_rth["pct_above_pdc"].values

    split_date = pd.Timestamp("2024-01-01").date()
    contracts = 2
    point_val = 2.0 * contracts
    comm_dollars = 1.24 * contracts
    slip_pts = 0.25

    # =========================================================================
    # MOTOR GENERAL DE EVALUACIÓN
    # =========================================================================
    def backtest_inventory_model(variant_type="STRICT_PDC_TARGET", target_r_fixed=1.50):
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
            o, h, l, c = opens[i], highs[i], lows[i], closes[i]
            pdc_val = pdcs[i]

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
                    if "PDC_TARGET" in variant_type and not np.isnan(pdc_val) and pdc_val < entry_p:
                        target_p = max(pdc_val, entry_p - (2.5 * stop_dist))
                    else:
                        target_p = entry_p - (target_r_fixed * stop_dist)
                else:          # LONG
                    entry_p = o + slip_pts
                    raw_stop = entry_p - (ref_extreme - 0.50)
                    stop_dist = min(max(raw_stop, 8.0), 22.0)
                    stop_p = entry_p - stop_dist
                    if "PDC_TARGET" in variant_type and not np.isnan(pdc_val) and pdc_val > entry_p:
                        target_p = min(pdc_val, entry_p + (2.5 * stop_dist))
                    else:
                        target_p = entry_p + (target_r_fixed * stop_dist)

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

            # Detección de Señal en la Apertura (09:35 a 10:15 ET)
            if not active and not pending and not traded_today:
                if "09:35" <= c_time <= "10:15":
                    v, v_s = vols[i], vol_smas[i]
                    vwap_val = vwaps[i]
                    vol_ok = not np.isnan(v_s) and (v >= 1.0 * v_s)

                    if not np.isnan(pdc_val) and vol_ok:
                        # 1. Condición de Inventario
                        is_long_imb = False
                        is_short_imb = False

                        if "STRICT" in variant_type:
                            is_long_imb = bool(strict_longs[i])
                            is_short_imb = bool(strict_shorts[i])
                        elif "VOLUME_85" in variant_type:
                            pct_ab = pct_aboves[i]
                            # Gap moderado de al menos 20 pts
                            gap = rth_opens[i] - pdc_val
                            if not np.isnan(pct_ab):
                                is_long_imb = (pct_ab >= 0.85) and (gap >= 20.0)
                                is_short_imb = (pct_ab <= 0.15) and (gap <= -20.0)

                        if "SHORT_ONLY" in variant_type:
                            is_short_imb = False  # Solo faders de inventario largo

                        # 2. Trigger de Rebalanceo:
                        # Si inventario es Long -> Esperamos que el mercado rompa bajo VWAP hacia PDC
                        if is_long_imb and (c < vwap_val) and (c < o):
                            pending = True
                            side = -1
                            ref_extreme = highs[i]
                            traded_today = True

                        # Si inventario es Short -> Esperamos que el mercado rompa sobre VWAP hacia PDC
                        elif is_short_imb and (c > vwap_val) and (c > o):
                            pending = True
                            side = 1
                            ref_extreme = lows[i]
                            traded_today = True

        return trades

    # =========================================================================
    # EJECUCIÓN Y TABLA FORENSE COMPARATIVA
    # =========================================================================
    models = [
        ("1. Strict Dalton (Target PDC)", "STRICT_PDC_TARGET", 1.50),
        ("2. Strict Dalton (Target 1.50R Fijo)", "STRICT_FIXED_R", 1.50),
        ("3. Volume 85% Imbalance (Gap > 20p)", "VOLUME_85_FIXED_R", 1.40),
        ("4. Strict Dalton Short-Only", "STRICT_SHORT_ONLY", 1.50),
    ]

    print("=" * 120)
    print("      AUDITORÍA QUANT: OVERNIGHT INVENTORY IMBALANCE EN MNQ (2022-2026)")
    print("      Condiciones: Entrada Open[t+1], 1 Tick Slip por lado, Comisiones CME $1.24 RT, Stop-First")
    print("=" * 120)
    print(f"{'Modelo de Desequilibrio':<34} | {'Trades/Mes':<10} {'IS: PF':<7} {'OOS: WR':<8} {'OOS: PF':<7} {'OOS Net ($)':<12} {'E[R] OOS':<10} {'IC 95% Bootstrap'}")
    print("-" * 120)

    for label, v_type, tgt_r in models:
        tr = backtest_inventory_model(variant_type=v_type, target_r_fixed=tgt_r)
        if not tr:
            print(f"{label:<34} | {'0':<10} {'N/A':<7} {'N/A':<8} {'N/A':<7} {'$0':<12} {'N/A':<10} {'N/A'}")
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
            f"{label:<34} | {tr_per_month:<10.1f} {pf_is:<7.2f} {wr_oos:<7.1f}% {pf_oos:<7.2f} "
            f"${p_oos.sum():<11.2f} {exp_r_oos:<+9.3f}R [{ci_low:+.2f}R, {ci_high:+.2f}R]"
        )

    print("=" * 120 + "\n")

if __name__ == "__main__":
    run_overnight_inventory_audit()
