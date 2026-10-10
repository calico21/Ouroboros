from pathlib import Path
import pandas as pd
import numpy as np

def run_true_metrics():
    df = pd.read_parquet("data/processed/mnq_5m_continuous.parquet")
    if df.index.tz is None:
        df.index = df.index.tz_localize("America/New_York")
    else:
        df.index = df.index.tz_convert("America/New_York")
    df = df.sort_index()
    df["date"] = df.index.date
    df["hour_min"] = df.index.strftime("%H:%M")

    # PDH
    daily = df.groupby("date").agg(d_high=("high", "max"))
    daily["pdh"] = daily["d_high"].shift(1)
    df["pdh"] = df["date"].map(daily["pdh"])

    # VWAP RTH
    is_rth = (df["hour_min"] >= "09:30") & (df["hour_min"] <= "16:00")
    df["tp"] = (df["high"] + df["low"] + df["close"]) / 3.0
    df["tp_vol"] = df["tp"] * df["volume"]
    rth_df = df[is_rth].copy()
    rth_df["cum_tp_vol"] = rth_df.groupby("date")["tp_vol"].cumsum()
    rth_df["cum_vol"] = rth_df.groupby("date")["volume"].cumsum()
    df["vwap"] = rth_df["cum_tp_vol"] / rth_df["cum_vol"]
    df["vwap"] = df.groupby("date")["vwap"].ffill()

    # SMA 20 de Volumen
    df["vol_sma20"] = df["volume"].rolling(20, min_periods=5).mean()

    def eval_model(sub_df, contracts=2, min_vol=None):
        dates = sub_df["date"].values
        hour_mins = sub_df["hour_min"].values
        opens = sub_df["open"].values
        highs = sub_df["high"].values
        lows = sub_df["low"].values
        closes = sub_df["close"].values
        vwaps = sub_df["vwap"].values
        pdhs = sub_df["pdh"].values
        vols = sub_df["volume"].values
        vol_smas = sub_df["vol_sma20"].values

        all_unique_dates = sorted(list(set(dates)))
        daily_pnl = {d: 0.0 for d in all_unique_dates}

        balance = 50000.0
        peak = 50000.0
        floor = 47500.0
        active = False
        entry_p = stop_p = target_p = 0.0
        trades = []
        cushions = []
        prev_date = None
        traded_today = False

        for i in range(len(sub_df)):
            c_date = dates[i]
            c_time = hour_mins[i]
            o, h, l, c = opens[i], highs[i], lows[i], closes[i]

            if c_date != prev_date:
                traded_today = False
                prev_date = c_date

            if active:
                u_peak = (entry_p - l) * 2.0 * contracts
                f_peak = balance + max(0.0, u_peak)
                if f_peak > peak:
                    peak = f_peak
                    floor = max(floor, 50100.0) if peak >= 52600.0 else peak - 2500.0

                closed = False
                exit_p = 0.0

                if h >= stop_p:
                    closed = True
                    exit_p = max(o, stop_p) + 0.25
                elif l <= target_p:
                    closed = True
                    exit_p = target_p
                elif c_time >= "15:55":
                    closed = True
                    exit_p = c + 0.25

                if closed:
                    pts = entry_p - exit_p
                    net = (pts * 2.0 * contracts) - (1.24 * contracts)
                    balance += net
                    trades.append(net)
                    daily_pnl[c_date] += net
                    active = False

            if not active and not traded_today:
                if "09:45" <= c_time <= "12:30":
                    pdh_val = pdhs[i]
                    vwap_val = vwaps[i]
                    v_val = vols[i]
                    v_sma = vol_smas[i]

                    if not np.isnan(pdh_val):
                        sweep_dist = h - pdh_val
                        vol_ok = (min_vol is None) or (not np.isnan(v_sma) and v_val >= min_vol * v_sma)

                        if 0 < sweep_dist <= 15.0 and c < pdh_val and c < vwap_val and vol_ok:
                            active = True
                            entry_p = c - 0.25
                            raw_stop = (h + 0.50) - entry_p
                            stop_dist = min(max(raw_stop, 10.0), 22.0)
                            stop_p = entry_p + stop_dist
                            target_p = entry_p - (1.40 * stop_dist)
                            traded_today = True

            cushions.append(balance - floor)

        pnl_arr = np.array(trades) if len(trades) > 0 else np.array([0.0])
        wins = pnl_arr[pnl_arr > 0]
        losses = pnl_arr[pnl_arr <= 0]
        wr = len(wins) / len(pnl_arr) * 100 if len(pnl_arr) > 0 else 0
        pf = wins.sum() / abs(losses.sum()) if abs(losses.sum()) > 0 else 0
        min_cush = min(cushions) if len(cushions) > 0 else 0
        max_dd = 2500.0 - min_cush
        max_dd_pct = (max_dd / 2500.0) * 100.0

        # Sortino sobre la serie completa de sesiones bursátiles (incluyendo ceros)
        pnl_series = pd.Series(list(daily_pnl.values()))
        mean_ret = pnl_series.mean()
        downside = pnl_series[pnl_series < 0]
        downside_dev = np.sqrt((downside ** 2).sum() / len(pnl_series))
        true_sortino = (mean_ret / downside_dev) * np.sqrt(252) if downside_dev > 0 else 0.0

        return {
            "n": len(pnl_arr),
            "wr": wr,
            "pf": pf,
            "pnl": pnl_arr.sum(),
            "dd": max_dd,
            "dd_pct": max_dd_pct,
            "sortino": true_sortino
        }

    is_mask = (df.index >= "2022-01-01") & (df.index < "2024-01-01")
    oos_mask = (df.index >= "2024-01-01")

    print("=" * 100)
    print("      MÉTRICAS CALENDARIO ESTANDARIZADAS (INCLUYENDO DÍAS VACÍOS)")
    print("=" * 100)
    print(f"{'Estrategia':<36} | {'IS: N':<5} {'IS: PF':<6} {'IS: Sort':<8} | {'OOS: N':<6} {'OOS: PF':<7} {'OOS: Sort':<9} {'OOS: MaxDD':<11} {'OOS: DD%':<8}")
    print("-" * 100)

    for label, v in [
        ("Base Mañana (Sin Filtro Vol)", None),
        ("Volumen >= 1.2x SMA20 (Config 3)", 1.2),
        ("Volumen >= 1.1x SMA20", 1.1),
    ]:
        r_is = eval_model(df[is_mask], min_vol=v)
        r_oos = eval_model(df[oos_mask], min_vol=v)
        print(
            f"{label:<36} | {r_is['n']:<5} {r_is['pf']:<6.2f} {r_is['sortino']:<8.2f} | "
            f"{r_oos['n']:<6} {r_oos['pf']:<7.2f} {r_oos['sortino']:<9.2f} ${r_oos['dd']:<10.2f} {r_oos['dd_pct']:<7.1f}%"
        )
    print("=" * 100 + "\n")

if __name__ == "__main__":
    run_true_metrics()
