from pathlib import Path
import numpy as np
import pandas as pd

def run_inversion_sanity_check():
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

    # RTH estricto (78 barras de 5m)
    rth_mask = (df["hour_min"] >= "09:30") & (df["hour_min"] <= "16:00")
    df_rth = df[rth_mask].copy()

    # Pre-cálculo de niveles
    daily = df_rth.groupby("date").agg(
        d_high=("high", "max"), d_low=("low", "min"), d_close=("close", "last")
    )
    daily["pdl"] = daily["d_low"].shift(1)
    df_rth["pdl"] = df_rth["date"].map(daily["pdl"])

    df_rth["tp"] = (df_rth["high"] + df_rth["low"] + df_rth["close"]) / 3.0
    df_rth["tp_vol"] = df_rth["tp"] * df_rth["volume"]
    df_rth["cum_tp_vol"] = df_rth.groupby("date")["tp_vol"].cumsum()
    df_rth["cum_vol"] = df_rth.groupby("date")["volume"].cumsum()
    df_rth["vwap"] = df_rth["cum_tp_vol"] / df_rth["cum_vol"]

    df_rth["vol_sma20"] = df_rth.groupby("date")["volume"].transform(
        lambda s: s.rolling(20, min_periods=5).mean()
    )

    ib_df = df_rth[df_rth["hour_min"].between("09:30", "09:55")]
    ib_stats = ib_df.groupby("date").agg(ibl=("low", "min"))
    df_rth["ibl"] = df_rth["date"].map(ib_stats["ibl"])

    dates = df_rth["date"].values
    hour_mins = df_rth["hour_min"].values
    opens = df_rth["open"].values
    highs = df_rth["high"].values
    lows = df_rth["low"].values
    closes = df_rth["close"].values
    vwaps = df_rth["vwap"].values
    pdls = df_rth["pdl"].values
    ibls = df_rth["ibl"].values
    vols = df_rth["volume"].values
    vol_smas = df_rth["vol_sma20"].values

    def backtest_setup(setup_name, invert=False, contracts=3):
        slip_pts = 0.25
        comm = 1.24 * contracts

        trades = []
        active = False
        pending = False
        side = 0
        entry_p = stop_p = target_p = stop_dist = 0.0
        pending_sig = None
        prev_date = None
        traded_today = False

        for i in range(len(df_rth)):
            c_date = dates[i]
            c_time = hour_mins[i]
            o, h, l, c = opens[i], highs[i], lows[i], closes[i]

            if c_date != prev_date:
                traded_today = False
                prev_date = c_date
                active = False
                pending = False

            if pending and not active:
                side = pending_sig["side"]
                target_r = pending_sig["target_r"]

                if side == 1:  # LONG
                    entry_p = o + slip_pts
                    raw_stop = entry_p - (pending_sig["ref_low"] - 0.50)
                    stop_dist = min(max(raw_stop, 10.0), 24.0)
                    stop_p = entry_p - stop_dist
                    target_p = entry_p + (target_r * stop_dist)
                else:          # SHORT
                    entry_p = o - slip_pts
                    raw_stop = (pending_sig["ref_high"] + 0.50) - entry_p
                    stop_dist = min(max(raw_stop, 10.0), 24.0)
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
                        "net": net,
                        "pts": pts,
                        "is_win": net > 0,
                        "is_oos": c_date >= pd.Timestamp("2024-01-01").date()
                    })
                    active = False

            if not active and not pending and not traded_today:
                v, v_sma = vols[i], vol_smas[i]
                vol_ok = not np.isnan(v_sma) and (v >= 1.0 * v_sma)

                if setup_name == "IB_SPRING" and "10:05" <= c_time <= "12:15" and vol_ok:
                    ibl = ibls[i]
                    if not np.isnan(ibl):
                        sw = ibl - l
                        if 0 < sw <= 20.0 and c > ibl and c > vwaps[i]:
                            # Señal base es LONG (side=1)
                            actual_side = -1 if invert else 1
                            pending = True
                            pending_sig = {
                                "side": actual_side,
                                "ref_low": l,
                                "ref_high": h,
                                "target_r": 1.50
                            }
                            traded_today = True

                elif setup_name == "PDL_SWEEP" and "09:45" <= c_time <= "12:30" and vol_ok:
                    pdl = pdls[i]
                    if not np.isnan(pdl):
                        sw = pdl - l
                        if 0 < sw <= 20.0 and c > pdl and c > vwaps[i]:
                            # Señal base es LONG (side=1)
                            actual_side = -1 if invert else 1
                            pending = True
                            pending_sig = {
                                "side": actual_side,
                                "ref_low": l,
                                "ref_high": h,
                                "target_r": 1.50
                            }
                            traded_today = True

        pnl = np.array([t["net"] for t in trades]) if trades else np.array([0.0])
        wins = pnl[pnl > 0]
        losses = pnl[pnl <= 0]
        wr = len(wins) / len(pnl) * 100 if len(pnl) > 0 else 0.0
        pf = wins.sum() / abs(losses.sum()) if abs(losses.sum()) > 0 else 0.0
        return len(trades), wr, pf, pnl.sum()

    print("=" * 95)
    print("      TEST DIAGNÓSTICO: PRUEBA DE INVERSIÓN DE SEÑAL (SANITY CHECK DEL ARNÉS)")
    print("=" * 95)
    print(f"{'Configuración':<38} | {'N Trades':<10} {'Win Rate':<10} {'Profit Factor':<15} {'PnL Neto ($)'}")
    print("-" * 95)

    cases = [
        ("1. IB Spring (Original: LONG)", "IB_SPRING", False),
        ("2. IB Spring (INVERTIDO: SHORT)", "IB_SPRING", True),
        ("3. PDL Sweep (Original: LONG)", "PDL_SWEEP", False),
        ("4. PDL Sweep (INVERTIDO: SHORT)", "PDL_SWEEP", True),
    ]

    for label, s_name, inv in cases:
        n_t, wr, pf, tot_pnl = backtest_setup(s_name, invert=inv)
        print(f"{label:<38} | {n_t:<10} {wr:<9.1f}% {pf:<15.2f} ${tot_pnl:<12.2f}")
    print("=" * 95 + "\n")

if __name__ == "__main__":
    run_inversion_sanity_check()
