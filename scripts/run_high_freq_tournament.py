import sys
from pathlib import Path
import numpy as np
import pandas as pd
import scipy.stats as stats

DATA_DIR = Path("data/processed_hf")

# =============================================================================
# 1. MODELO 1: MNQ MICRO-FVG & LIQUIDITY SWEEP (M1 RTH)
# =============================================================================
def run_mnq_micro_fvg(contracts=2, target_r=1.50):
    df_path = DATA_DIR / "mnq_m1.parquet"
    if not df_path.exists():
        return None
    df = pd.read_parquet(df_path)
    df["date"] = df.index.date
    df["hour_min"] = df.index.strftime("%H:%M")

    # RTH estricto (09:30 a 16:00 ET)
    df = df[(df["hour_min"] >= "09:30") & (df["hour_min"] <= "16:00")].copy()

    # VWAP RTH
    df["tp"] = (df["high"] + df["low"] + df["close"]) / 3.0
    df["tp_vol"] = df["tp"] * df["volume"]
    df["vwap"] = df.groupby("date")["tp_vol"].cumsum() / df.groupby("date")["volume"].cumsum()
    df["vol_sma"] = df.groupby("date")["volume"].transform(lambda s: s.rolling(20, min_periods=5).mean())

    # Rolling 15-min swing high/low (15 barras M1)
    df["swing_h15"] = df.groupby("date")["high"].transform(lambda s: s.shift(1).rolling(15, min_periods=5).max())
    df["swing_l15"] = df.groupby("date")["low"].transform(lambda s: s.shift(1).rolling(15, min_periods=5).min())

    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    vwaps = df["vwap"].values
    vols = df["volume"].values
    vol_smas = df["vol_sma"].values
    sw_hs = df["swing_h15"].values
    sw_ls = df["swing_l15"].values
    dates = df["date"].values
    hour_mins = df["hour_min"].values

    point_val = 2.0 * contracts
    comm = 1.24 * contracts
    slip_pts = 0.25

    trades = []
    active = False
    side = 0
    entry_p = stop_p = target_p = stop_dist = 0.0
    sig_extreme = 0.0
    pending = False
    prev_date = None

    for i in range(2, len(df)):
        c_date = dates[i]
        c_time = hour_mins[i]
        o, h, l, c = opens[i], highs[i], lows[i], closes[i]

        if c_date != prev_date:
            prev_date = c_date
            active = False
            pending = False

        if pending and not active:
            if side == -1:  # SHORT
                entry_p = o - slip_pts
                raw_stop = (sig_extreme + 0.50) - entry_p
                stop_dist = min(max(raw_stop, 5.0), 12.0)
                stop_p = entry_p + stop_dist
                target_p = entry_p - (target_r * stop_dist)
            else:          # LONG
                entry_p = o + slip_pts
                raw_stop = entry_p - (sig_extreme - 0.50)
                stop_dist = min(max(raw_stop, 5.0), 12.0)
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
                net = (pts * point_val) - comm
                r_net = net / (stop_dist * point_val)
                trades.append({
                    "date": c_date, "model": "MNQ_MICRO_FVG", "pts": pts,
                    "net": net, "r_net": r_net, "stop_pts": stop_dist
                })
                active = False

        if not active and not pending:
            # Ventana activa: 09:45 a 12:30 ET
            if "09:45" <= c_time <= "12:30":
                sw_h, sw_l = sw_hs[i], sw_ls[i]
                v, v_s, vwap = vols[i], vol_smas[i], vwaps[i]
                vol_ok = not np.isnan(v_s) and (v >= 1.2 * v_s)

                # Detección de FVG bajista: Low[t-2] > High[t] (desequilibrio vendedor)
                bear_fvg = lows[i - 2] > highs[i]
                # Detección de FVG alcista: High[t-2] < Low[t] (desequilibrio comprador)
                bull_fvg = highs[i - 2] < lows[i]

                # Setup Short: Barrido de swing high previo + FVG bajista + Cierre bajo VWAP
                if not np.isnan(sw_h) and h > sw_h and c < sw_h and c < vwap and bear_fvg and vol_ok:
                    pending = True
                    side = -1
                    sig_extreme = h

                # Setup Long: Barrido de swing low previo + FVG alcista + Cierre sobre VWAP
                elif not np.isnan(sw_l) and l < sw_l and c > sw_l and c > vwap and bull_fvg and vol_ok:
                    pending = True
                    side = 1
                    sig_extreme = l

    return trades

# =============================================================================
# 2. MODELO 2: MICRO ORO (MGC) ORB-M1 MOMENTUM DRIVE
# =============================================================================
def run_gold_momentum_drive(contracts=2, target_r=2.0):
    df_path = DATA_DIR / "mgc_m1.parquet"
    if not df_path.exists():
        return None
    df = pd.read_parquet(df_path)
    df["date"] = df.index.date
    df["hour_min"] = df.index.strftime("%H:%M")

    # Apertura institucional de metales en NY (08:20 a 13:30 ET)
    df = df[(df["hour_min"] >= "08:20") & (df["hour_min"] <= "13:30")].copy()

    # Rango de apertura de 5 minutos (08:20 - 08:25 ET)
    or5_df = df[df["hour_min"].between("08:20", "08:24")]
    or5_h = or5_df.groupby("date")["high"].max()
    or5_l = or5_df.groupby("date")["low"].min()
    df["or5_h"] = df["date"].map(or5_h)
    df["or5_l"] = df["date"].map(or5_l)

    df["tp"] = (df["high"] + df["low"] + df["close"]) / 3.0
    df["tp_vol"] = df["tp"] * df["volume"]
    df["vwap"] = df.groupby("date")["tp_vol"].cumsum() / df.groupby("date")["volume"].cumsum()
    df["vol_sma"] = df.groupby("date")["volume"].transform(lambda s: s.rolling(20, min_periods=5).mean())

    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    vwaps = df["vwap"].values
    vols = df["volume"].values
    vol_smas = df["vol_sma"].values
    or_hs = df["or5_h"].values
    or_ls = df["or5_l"].values
    dates = df["date"].values
    hour_mins = df["hour_min"].values

    point_val = 10.0 * contracts  # $10/pt en Micro Oro ($1/tick de 0.10)
    comm = 1.24 * contracts
    slip_pts = 0.10

    trades = []
    active = False
    side = 0
    entry_p = stop_p = target_p = stop_dist = 0.0
    pending = False
    prev_date = None
    traded_today = False

    for i in range(len(df)):
        c_date = dates[i]
        c_time = hour_mins[i]
        o, h, l, c = opens[i], highs[i], lows[i], closes[i]

        if c_date != prev_date:
            prev_date = c_date
            active = False
            pending = False
            traded_today = False

        if pending and not active:
            if side == 1:
                entry_p = o + slip_pts
                stop_dist = min(max(entry_p - or_ls[i], 1.2), 3.0)
                stop_p = entry_p - stop_dist
                target_p = entry_p + (target_r * stop_dist)
            else:
                entry_p = o - slip_pts
                stop_dist = min(max(or_hs[i] - entry_p, 1.2), 3.0)
                stop_p = entry_p + stop_dist
                target_p = entry_p - (target_r * stop_dist)

            active = True
            pending = False

        if active:
            hit_stop = (l <= stop_p) if side == 1 else (h >= stop_p)
            hit_target = (h >= target_p) if side == 1 else (l <= target_p)
            closed = False
            exit_p = 0.0

            if hit_stop:
                closed = True
                exit_p = (min(o, stop_p) - slip_pts) if side == 1 else (max(o, stop_p) + slip_pts)
            elif hit_target:
                closed = True
                exit_p = target_p
            elif c_time >= "13:25":
                closed = True
                exit_p = (c - slip_pts) if side == 1 else (c + slip_pts)

            if closed:
                pts = (exit_p - entry_p) if side == 1 else (entry_p - exit_p)
                net = (pts * point_val) - comm
                r_net = net / (stop_dist * point_val)
                trades.append({
                    "date": c_date, "model": "MGC_GOLD_ORB", "pts": pts,
                    "net": net, "r_net": r_net, "stop_pts": stop_dist
                })
                active = False

        if not active and not pending and not traded_today:
            # Disparo entre 08:26 y 09:30 ET
            if "08:26" <= c_time <= "09:30":
                o_h, o_l = or_hs[i], or_ls[i]
                v, v_s, vwap = vols[i], vol_smas[i], vwaps[i]
                vol_ok = not np.isnan(v_s) and (v >= 1.3 * v_s)

                if not np.isnan(o_h) and not np.isnan(o_l) and vol_ok:
                    rng = o_h - o_l
                    if 1.5 <= rng <= 6.0:
                        # Ruptura alcista sobre OR5 y VWAP
                        if c > o_h and c > vwap:
                            pending = True
                            side = 1
                            traded_today = True
                        # Ruptura bajista bajo OR5 y VWAP
                        elif c < o_l and c < vwap:
                            pending = True
                            side = -1
                            traded_today = True

    return trades

# =============================================================================
# 3. MODELO 3: CRIPTO VOLATILITY SQUEEZE (BTCUSDT M1)
# =============================================================================
def run_crypto_volatility_squeeze(capital=50000.0, risk_pct=0.01, target_r=1.75):
    df_path = DATA_DIR / "btcusdt_1m_continuous.parquet"
    if not df_path.exists():
        return None
    df = pd.read_parquet(df_path)
    df["date"] = df.index.date

    # Bandas de Bollinger (20, 2.0)
    df["sma20"] = df["close"].rolling(20).mean()
    df["std20"] = df["close"].rolling(20).std()
    df["bb_u"] = df["sma20"] + (2.0 * df["std20"])
    df["bb_l"] = df["sma20"] - (2.0 * df["std20"])
    df["bb_width"] = (df["bb_u"] - df["bb_l"]) / df["sma20"]

    # Keltner Channel (20, 1.5 * ATR)
    df["tr"] = np.maximum(df["high"] - df["low"],
               np.maximum(abs(df["high"] - df["close"].shift(1)),
                          abs(df["low"] - df["close"].shift(1))))
    df["atr20"] = df["tr"].rolling(20).mean()
    df["kc_u"] = df["sma20"] + (1.5 * df["atr20"])
    df["kc_l"] = df["sma20"] - (1.5 * df["atr20"])

    # Condición de Squeeze: Bollinger DENTRO de Keltner
    df["squeeze"] = (df["bb_u"] < df["kc_u"]) & (df["bb_l"] > df["kc_l"])
    df["vol_sma"] = df["volume"].rolling(20).mean()

    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    squeezes = df["squeeze"].values
    bb_widths = df["bb_width"].values
    atrs = df["atr20"].values
    vols = df["volume"].values
    vol_smas = df["vol_sma"].values
    dates = df["date"].values

    fee_rate = 0.0004  # 0.04% roundtrip
    slip_rate = 0.0001 # 1 bp

    trades = []
    active = False
    side = 0
    entry_p = stop_p = target_p = stop_dist = 0.0
    pending = False

    for i in range(25, len(df)):
        o, h, l, c = opens[i], highs[i], lows[i], closes[i]

        if pending and not active:
            if side == 1:
                entry_p = o * (1.0 + slip_rate)
                stop_dist = max(atrs[i] * 1.2, entry_p * 0.0035)
                stop_p = entry_p - stop_dist
                target_p = entry_p + (target_r * stop_dist)
            else:
                entry_p = o * (1.0 - slip_rate)
                stop_dist = max(atrs[i] * 1.2, entry_p * 0.0035)
                stop_p = entry_p + stop_dist
                target_p = entry_p - (target_r * stop_dist)

            active = True
            pending = False

        if active:
            hit_stop = (l <= stop_p) if side == 1 else (h >= stop_p)
            hit_target = (h >= target_p) if side == 1 else (l <= target_p)
            closed = False
            exit_p = 0.0

            if hit_stop:
                closed = True
                exit_p = (min(o, stop_p) * (1.0 - slip_rate)) if side == 1 else (max(o, stop_p) * (1.0 + slip_rate))
            elif hit_target:
                closed = True
                exit_p = target_p

            if closed:
                ret_raw = (exit_p / entry_p - 1.0) if side == 1 else (1.0 - exit_p / entry_p)
                ret_net = ret_raw - fee_rate
                r_risk_pct = stop_dist / entry_p
                r_net = ret_net / r_risk_pct
                # Dólares calculados a $20/R para comparar directamente con cuentas de $2k de buffer
                net_dollars = r_net * 20.0
                trades.append({
                    "date": dates[i], "model": "BTC_SQUEEZE_M1",
                    "net": net_dollars, "r_net": r_net, "stop_pts": stop_dist
                })
                active = False

        if not active and not pending:
            # Salida del Squeeze: si la barra anterior estaba en squeeze y la actual rompe fuera
            if squeezes[i - 1] and not squeezes[i]:
                v, v_s = vols[i], vol_smas[i]
                if v >= 1.5 * v_s:
                    if c > closes[i - 1]:
                        pending = True
                        side = 1
                    elif c < closes[i - 1]:
                        pending = True
                        side = -1

    return trades

# =============================================================================
# EJECUCIÓN DEL TORNEO Y SIMULACIÓN MONTE CARLO APEX (21 SESIONES)
# =============================================================================
def run_tournament():
    print("=" * 115)
    print("      TORNEO DE EDGES DE ALTA FRECUENCIA (EVALUACIÓN M1 TICK-BY-TICK)")
    print("      Condiciones: Entrada Open[t+1], Slippage, Fees y Regla Stop-First")
    print("=" * 115)

    models = [
        ("1. MNQ Micro-FVG Reversal (M1)", run_mnq_micro_fvg),
        ("2. MGC Micro Oro ORB Drive (M1)", run_gold_momentum_drive),
        ("3. BTCUSDT Volatility Squeeze (M1)", run_crypto_volatility_squeeze),
    ]

    print(f"{'Modelo de Alta Frecuencia':<35} | {'Trades/Día':<11} {'N Total':<8} {'WinRate':<9} {'Profit Factor':<15} {'E[R]':<10} {'IC 95% Bootstrap'}")
    print("-" * 115)

    for label, fn in models:
        tr = fn()
        if not tr:
            print(f"{label:<35} | {'N/A':<11} {'0':<8} {'N/A':<9} {'N/A':<15} {'N/A':<10} {'N/A'}")
            continue

        df_tr = pd.DataFrame(tr)
        n_days = len(df_tr["date"].unique())
        tr_per_day = len(df_tr) / max(n_days, 1)

        p_net = df_tr["net"].values
        r_net = df_tr["r_net"].values
        w = p_net[p_net > 0]
        l = p_net[p_net <= 0]

        wr = len(w) / len(p_net) * 100
        pf = w.sum() / abs(l.sum()) if abs(l.sum()) > 0 else 0
        exp_r = r_net.mean()

        # Bootstrap 95% CI
        boot_means = [np.random.choice(r_net, size=len(r_net), replace=True).mean() for _ in range(5000)]
        ci_low = np.percentile(boot_means, 2.5)
        ci_high = np.percentile(boot_means, 97.5)

        print(
            f"{label:<35} | {tr_per_day:<11.2f} {len(df_tr):<8} {wr:<8.1f}% {pf:<15.2f} "
            f"{exp_r:<+9.3f}R [{ci_low:+.2f}R, {ci_high:+.2f}R]"
        )

    print("=" * 115 + "\n")

    # SIMULACIÓN APEX 30 DÍAS (21 SESIONES)
    print("=" * 115)
    print("      SIMULACIÓN MONTE CARLO APEX: 21 SESIONES BURSÁTILES (30 DÍAS NATURALES)")
    print("      Buffer: $2.000 | Target: +$3.000 | 10.000 Caminos por Modelo (1R = $50)")
    print("=" * 115)
    print(f"{'Modelo':<35} | {'Trades en 21d':<14} {'EV 21 Días ($)':<16} {'P(Pass 21d)':<15} {'Tasa Breach':<12} {'Veredicto'}")
    print("-" * 115)

    n_sims = 10000
    for label, fn in models:
        tr = fn()
        if not tr:
            continue
        df_tr = pd.DataFrame(tr)
        daily_pnl = df_tr.groupby("date")["r_net"].sum().values

        passes = 0
        breaches = 0
        ev_totals = []

        for _ in range(n_sims):
            sample_days = np.random.choice(daily_pnl, size=21, replace=True)
            dollars = sample_days * 50.0  # 1R = $50 (2.5% del buffer)
            ev_totals.append(dollars.sum())

            bal = 50000.0
            peak = 50000.0
            floor = 48000.0

            for d_ret in dollars:
                bal += d_ret
                if bal > peak:
                    peak = bal
                    floor = 50100.0 if peak >= 52600.0 else (peak - 2000.0)
                if bal <= floor:
                    breaches += 1
                    break
                if (bal - 50000.0) >= 3000.0:
                    passes += 1
                    break

        p_pass = (passes / n_sims) * 100
        p_breach = (breaches / n_sims) * 100
        avg_ev = np.mean(ev_totals)
        tr_in_21 = (len(df_tr) / len(df_tr['date'].unique())) * 21

        verdict = "CANDIDATO SÓLIDO" if p_pass > 25.0 and p_breach < 8.0 else ("DESTRUCTOR DE CAJA" if p_breach > 20.0 else "INSUFICIENTE")

        print(
            f"{label:<35} | {tr_in_21:<14.1f} {f'${avg_ev:+.2f}':<16} {p_pass:<14.1f}% {p_breach:<11.1f}% {verdict}"
        )

    print("=" * 115 + "\n")

if __name__ == "__main__":
    run_tournament()
