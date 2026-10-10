from pathlib import Path
import numpy as np
import pandas as pd
import scipy.stats as stats
from scripts.friend_strategies import intraday_momentum_close, placebo_random_side

def run_h1_vs_placebo_audit():
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

    # Cálculo estricto de PDC (Cierre de ayer)
    daily_close = df_rth.groupby("date")["close"].last()
    df_rth["pdc"] = df_rth["date"].map(daily_close.shift(1))

    dates = df_rth["date"].values
    hour_mins = df_rth["hour_min"].values
    opens = df_rth["open"].values
    highs = df_rth["high"].values
    lows = df_rth["low"].values
    closes = df_rth["close"].values
    split_date = pd.Timestamp("2024-01-01").date()

    def simulate_signals(signals_list, contracts=2):
        slip_pts = 0.25
        comm = 1.24 * contracts

        trades = []
        active = False
        side = 0
        entry_p = stop_p = target_p = stop_dist = 0.0
        pending = False
        pending_sig = None
        prev_date = None

        sigs_by_idx = {s["idx"]: s for s in signals_list}

        for i in range(len(df_rth)):
            c_date = dates[i]
            c_time = hour_mins[i]
            o, h, l, c = opens[i], highs[i], lows[i], closes[i]

            if c_date != prev_date:
                prev_date = c_date
                active = False
                pending = False

            if pending and not active:
                sig = pending_sig
                side = sig["side"]
                target_r = sig["target_r"]

                if side == 1:  # LONG
                    entry_p = o + slip_pts
                    raw_stop = entry_p - (sig["sig_low"] - 0.50)
                    stop_dist = min(max(raw_stop, 10.0), 22.0)
                    stop_p = entry_p - stop_dist
                    target_p = entry_p + (target_r * stop_dist)
                else:          # SHORT
                    entry_p = o - slip_pts
                    raw_stop = (sig["sig_high"] + 0.50) - entry_p
                    stop_dist = min(max(raw_stop, 10.0), 22.0)
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
                elif c_time >= "15:55":
                    closed = True
                    exit_p = (c - slip_pts) if side == 1 else (c + slip_pts)

                if closed:
                    pts = (exit_p - entry_p) if side == 1 else (entry_p - exit_p)
                    net = (pts * 2.0 * contracts) - comm
                    trades.append({
                        "date": c_date,
                        "year": c_date.year,
                        "net": net,
                        "pts": pts,
                        "r_mult": pts / stop_dist if stop_dist > 0 else 0.0,
                        "is_win": net > 0,
                        "is_oos": c_date >= split_date
                    })
                    active = False

            if not active and not pending:
                if i in sigs_by_idx:
                    pending = True
                    pending_sig = sigs_by_idx[i]

        return trades

    sigs_h1 = intraday_momentum_close(df_rth)
    sigs_placebo = placebo_random_side(df_rth, seed=7)

    tr_h1 = simulate_signals(sigs_h1)
    tr_plac = simulate_signals(sigs_placebo)

    def bootstrap_metrics(trade_list, n_boot=10000):
        if not trade_list:
            return {}
        pnl = np.array([t["net"] for t in trade_list])
        r_arr = np.array([t["r_mult"] for t in trade_list])

        boot_wr = []
        boot_pf = []
        boot_r = []

        np.random.seed(42)
        for _ in range(n_boot):
            idx = np.random.choice(len(pnl), size=len(pnl), replace=True)
            p_s = pnl[idx]
            r_s = r_arr[idx]
            w = p_s[p_s > 0]
            l = p_s[p_s <= 0]

            boot_wr.append(len(w) / len(p_s) * 100)
            boot_pf.append(w.sum() / abs(l.sum()) if abs(l.sum()) > 0 else 1.0)
            boot_r.append(r_s.mean())

        w_act = pnl[pnl > 0]
        l_act = pnl[pnl <= 0]
        act_pf = w_act.sum() / abs(l_act.sum()) if abs(l_act.sum()) > 0 else 1.0

        return {
            "n": len(pnl),
            "pnl": pnl.sum(),
            "wr_obs": len(w_act) / len(pnl) * 100,
            "wr_ci": (np.percentile(boot_wr, 2.5), np.percentile(boot_wr, 97.5)),
            "pf_obs": act_pf,
            "pf_ci": (np.percentile(boot_pf, 2.5), np.percentile(boot_pf, 97.5)),
            "r_obs": r_arr.mean(),
            "r_ci": (np.percentile(boot_r, 2.5), np.percentile(boot_r, 97.5)),
        }

    print("=" * 105)
    print("      AUDITORÍA CIENTÍFICA: HIPÓTESIS H1 (MOMENTUM DE CIERRE) vs PLACEBO (RANDOM SIDE)")
    print("      Condiciones: Entrada Open 15:30, Salida 15:55, 1 Tick Slip, 2 MNQ")
    print("=" * 105)

    experiments = [
        ("H1: Momentum Gao et al. (IS 2022-2023)", [t for t in tr_h1 if not t["is_oos"]]),
        ("H1: Momentum Gao et al. (OOS 2024-2026)", [t for t in tr_h1 if t["is_oos"]]),
        ("PLACEBO: Random Side (IS 2022-2023)", [t for t in tr_plac if not t["is_oos"]]),
        ("PLACEBO: Random Side (OOS 2024-2026)", [t for t in tr_plac if t["is_oos"]]),
    ]

    for label, t_set in experiments:
        m = bootstrap_metrics(t_set)
        if not m:
            continue
        print(f"\n▶ {label}")
        print(f"   Trades (N)      : {m['n']} trades (~{m['n']/(2 if 'IS' in label else 2.77):.1f} trades/año)")
        print(f"   PnL Neto Total  : ${m['pnl']:<10.2f}")
        print(f"   Win Rate        : {m['wr_obs']:.1f}%  -->  IC 95%: [{m['wr_ci'][0]:.1f}%, {m['wr_ci'][1]:.1f}%]")
        print(f"   Profit Factor   : {m['pf_obs']:.2f}   -->  IC 95%: [{m['pf_ci'][0]:.2f}, {m['pf_ci'][1]:.2f}]")
        print(f"   Expectativa R   : {m['r_obs']:+.2f}R  -->  IC 95%: [{m['r_ci'][0]:+.2f}R, {m['r_ci'][1]:+.2f}R]")

    # Deflated Sharpe Ratio
    def compute_dsr(trade_list, n_trials=25):
        if not trade_list:
            return 1.0, 0.0
        pnl = np.array([t["net"] for t in trade_list])
        mean_pnl = pnl.mean()
        std_pnl = pnl.std() if len(pnl) > 1 else 1e-6
        sr_obs = (mean_pnl / std_pnl) * np.sqrt(252) if std_pnl > 0 else 0.0

        T = len(pnl)
        skew = stats.skew(pnl)
        kurt = stats.kurtosis(pnl) + 3.0
        sr_std = np.sqrt((1 - skew * sr_obs + ((kurt - 1) / 4.0) * (sr_obs ** 2)) / (T - 1))

        gamma = 0.5772156649
        z_val = (1.0 - gamma) * stats.norm.ppf(1.0 - 1.0 / n_trials) + gamma * stats.norm.ppf(1.0 - 1.0 / (n_trials * np.e))
        sr_null = z_val * (1.0 / np.sqrt(252))

        dsr_stat = (sr_obs / np.sqrt(252) - sr_null) / sr_std
        p_val = 1.0 - stats.norm.cdf(dsr_stat)
        return p_val, sr_obs

    p_val_h1, sr_h1 = compute_dsr(tr_h1, n_trials=25)
    print("\n" + "=" * 105)
    print("      DEFLATED SHARPE RATIO (AJUSTADO POR K=25 ENSAYOS PREVIOS)")
    print("=" * 105)
    print(f"  Sharpe Anualizado H1 (Total) : {sr_h1:.2f}")
    print(f"  P-Valor DSR Ajustado         : p = {p_val_h1:.4f}  ({'Significativo' if p_val_h1 < 0.05 else 'No significativo tras penalización por multiplicidad'})")
    print("=" * 105 + "\n")

if __name__ == "__main__":
    run_h1_vs_placebo_audit()
