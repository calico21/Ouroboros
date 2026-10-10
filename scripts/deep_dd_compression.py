from pathlib import Path
import pandas as pd
import numpy as np

def run_dd_compression():
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

    # PDH
    daily = df.groupby("date").agg(
        d_open=("open", "first"),
        d_high=("high", "max"),
        d_close=("close", "last")
    )
    daily["pdh"] = daily["d_high"].shift(1)
    daily["sma_20_daily"] = daily["d_close"].rolling(20).mean().shift(1)
    df["pdh"] = df["date"].map(daily["pdh"])
    df["sma_20_daily"] = df["date"].map(daily["sma_20_daily"])

    # VWAP RTH
    is_rth = (df["hour_min"] >= "09:30") & (df["hour_min"] <= "16:00")
    df["tp"] = (df["high"] + df["low"] + df["close"]) / 3.0
    df["tp_vol"] = df["tp"] * df["volume"]
    rth_df = df[is_rth].copy()
    rth_df["cum_tp_vol"] = rth_df.groupby("date")["tp_vol"].cumsum()
    rth_df["cum_vol"] = rth_df.groupby("date")["volume"].cumsum()
    df["vwap"] = rth_df["cum_tp_vol"] / rth_df["cum_vol"]
    df["vwap"] = df.groupby("date")["vwap"].ffill()

    def simulate(sub_df, contracts=2, max_bars_in_trade=None, max_daily_stretch=None):
        dates = sub_df["date"].values
        hour_mins = sub_df["hour_min"].values
        opens = sub_df["open"].values
        highs = sub_df["high"].values
        lows = sub_df["low"].values
        closes = sub_df["close"].values
        vwaps = sub_df["vwap"].values
        pdhs = sub_df["pdh"].values
        sma_20s = sub_df["sma_20_daily"].values
        timestamps = sub_df.index

        balance = 50000.0
        peak = 50000.0
        floor = 47500.0
        active = False
        entry_p = stop_p = target_p = 0.0
        bars_held = 0
        trades = []
        cushions = []
        daily_pnl = {}
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
                bars_held += 1
                u_peak = (entry_p - l) * 2.0 * contracts
                f_peak = balance + max(0.0, u_peak)
                if f_peak > peak:
                    peak = f_peak
                    floor = max(floor, 50100.0) if peak >= 52600.0 else peak - 2500.0

                closed = False
                exit_p = 0.0

                # 1. Stop Loss
                if h >= stop_p:
                    closed = True
                    exit_p = max(o, stop_p) + 0.25
                # 2. Target
                elif l <= target_p:
                    closed = True
                    exit_p = target_p
                # 3. Time Stop (Salida si no desarrolla en N barras de 5m)
                elif max_bars_in_trade is not None and bars_held >= max_bars_in_trade:
                    closed = True
                    exit_p = c + 0.25
                # 4. EOD Hard Cutoff
                elif c_time >= "15:55":
                    closed = True
                    exit_p = c + 0.25

                if closed:
                    pts = entry_p - exit_p
                    net = (pts * 2.0 * contracts) - (1.24 * contracts)
                    balance += net
                    trades.append({
                        "time": timestamps[i],
                        "date": c_date,
                        "pnl": net,
                        "bars_held": bars_held,
                        "balance": balance,
                        "cushion": balance - floor
                    })
                    daily_pnl[c_date] = daily_pnl.get(c_date, 0.0) + net
                    active = False

            if not active and not traded_today:
                if "09:45" <= c_time <= "12:30":
                    pdh_val = pdhs[i]
                    vwap_val = vwaps[i]
                    sma_val = sma_20s[i]

                    # Filtro de sobreextensión diaria opcional
                    stretch_ok = True
                    if max_daily_stretch is not None and not np.isnan(sma_val) and sma_val > 0:
                        stretch_pct = (c - sma_val) / sma_val * 100.0
                        if stretch_pct > max_daily_stretch:
                            stretch_ok = False

                    if stretch_ok and not np.isnan(pdh_val):
                        sweep_dist = h - pdh_val
                        if 0 < sweep_dist <= 15.0 and c < pdh_val and c < vwap_val:
                            active = True
                            entry_p = c - 0.25
                            raw_stop = (h + 0.50) - entry_p
                            stop_dist = min(max(raw_stop, 10.0), 22.0)
                            stop_p = entry_p + stop_dist
                            target_p = entry_p - (1.40 * stop_dist)
                            bars_held = 0
                            traded_today = True

            cushions.append(balance - floor)

        pnl_arr = np.array([t["pnl"] for t in trades]) if len(trades) > 0 else np.array([0.0])
        wins = pnl_arr[pnl_arr > 0]
        losses = pnl_arr[pnl_arr <= 0]
        wr = len(wins) / len(pnl_arr) * 100 if len(pnl_arr) > 0 else 0
        pf = wins.sum() / abs(losses.sum()) if abs(losses.sum()) > 0 else 0
        min_cush = min(cushions) if len(cushions) > 0 else 0
        max_dd_dollars = 2500.0 - min_cush
        max_dd_pct = (max_dd_dollars / 2500.0) * 100.0

        days_series = pd.Series(daily_pnl)
        if len(days_series) > 1:
            mean_d = days_series.mean()
            downside = days_series[days_series < 0]
            downside_dev = np.sqrt((downside ** 2).mean()) if len(downside) > 0 else 1e-6
            sortino = (mean_d / downside_dev) * np.sqrt(252) if downside_dev > 0 else 0.0
        else:
            sortino = 0.0

        return {
            "n": len(pnl_arr),
            "wr": wr,
            "pf": pf,
            "pnl": pnl_arr.sum(),
            "dd_dollars": max_dd_dollars,
            "dd_pct": max_dd_pct,
            "sortino": sortino,
            "trades": trades
        }

    is_mask = (df.index >= "2022-01-01") & (df.index < "2024-01-01")
    oos_mask = (df.index >= "2024-01-01")

    tests = [
        ("1. Referencia (Sin Time-Stop)", {}),
        ("2. Time-Stop a 9 Barras (45 min)", {"max_bars_in_trade": 9}),
        ("3. Time-Stop a 12 Barras (60 min)", {"max_bars_in_trade": 12}),
        ("4. Time-Stop a 18 Barras (90 min)", {"max_bars_in_trade": 18}),
        ("5. Filtro Anti-Euforia (Price <= SMA20 + 3%)", {"max_daily_stretch": 3.0}),
        ("6. Time-Stop 60m + Anti-Euforia 3%", {"max_bars_in_trade": 12, "max_daily_stretch": 3.0}),
    ]

    print("=" * 105)
    print("      AUDITORÍA DE REDUCCIÓN DE DRAWDOWN Y MAXIMIZACIÓN DE SORTINO")
    print("=" * 105)
    print(f"{'Configuración':<38} | {'IS: PF':<6} {'IS: Sort':<8} {'IS: PnL':<9} | {'OOS: PF':<7} {'OOS: Sort':<9} {'OOS: MaxDD ($)':<14} {'OOS: DD (%)':<10}")
    print("-" * 105)

    for label, kwargs in tests:
        r_is = simulate(df[is_mask], **kwargs)
        r_oos = simulate(df[oos_mask], **kwargs)
        print(
            f"{label:<38} | {r_is['pf']:<6.2f} {r_is['sortino']:<8.2f} ${r_is['pnl']:<8.0f} | "
            f"{r_oos['pf']:<7.2f} {r_oos['sortino']:<9.2f} ${r_oos['dd_dollars']:<13.2f} {r_oos['dd_pct']:<9.1f}%"
        )
    print("=" * 105 + "\n")

if __name__ == "__main__":
    run_dd_compression()
