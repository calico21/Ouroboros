from pathlib import Path
import pandas as pd
import numpy as np

def run_split_validation():
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
    daily = df.groupby("date").agg(d_high=("high", "max"))
    daily["pdh"] = daily["d_high"].shift(1)
    df["pdh"] = df["date"].map(daily["pdh"])

    # VWAP
    is_rth = (df["hour_min"] >= "09:30") & (df["hour_min"] <= "16:00")
    df["tp"] = (df["high"] + df["low"] + df["close"]) / 3.0
    df["tp_vol"] = df["tp"] * df["volume"]
    rth_df = df[is_rth].copy()
    rth_df["cum_tp_vol"] = rth_df.groupby("date")["tp_vol"].cumsum()
    rth_df["cum_vol"] = rth_df.groupby("date")["volume"].cumsum()
    df["vwap"] = rth_df["cum_tp_vol"] / rth_df["cum_vol"]
    df["vwap"] = df.groupby("date")["vwap"].ffill()

    def evaluate_subperiod(sub_df, label):
        dates = sub_df["date"].values
        hour_mins = sub_df["hour_min"].values
        opens = sub_df["open"].values
        highs = sub_df["high"].values
        lows = sub_df["low"].values
        closes = sub_df["close"].values
        vwaps = sub_df["vwap"].values
        pdhs = sub_df["pdh"].values

        balance = 50000.0
        peak_equity = 50000.0
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
                u_peak = (entry_p - l) * 2.0
                floating_peak = balance + max(0.0, u_peak)
                if floating_peak > peak_equity:
                    peak_equity = floating_peak
                    floor = max(floor, 50100.0) if peak_equity >= 52600.0 else peak_equity - 2500.0

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
                    pnl = ((entry_p - exit_p) * 2.0) - 1.24
                    balance += pnl
                    trades.append(pnl)
                    active = False

            if not active and not traded_today:
                if "09:45" <= c_time <= "14:30":
                    pdh_val = pdhs[i]
                    vwap_val = vwaps[i]
                    if not np.isnan(pdh_val):
                        if h > pdh_val and (h - pdh_val) <= 15.0 and c < pdh_val and c < vwap_val:
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
        max_dd_buffer = ((2500.0 - min_cush) / 2500.0) * 100.0

        print(f"\n--- {label} ---")
        print(f"  Periodo               : {sub_df.index[0].date()} a {sub_df.index[-1].date()}")
        print(f"  Trades Ejecutados     : {len(pnl_arr)}")
        print(f"  Win Rate (%)          : {wr:.2f}%")
        print(f"  Profit Factor         : {pf:.2f}")
        print(f"  PnL Neto ($)          : ${pnl_arr.sum():,.2f}")
        print(f"  Expectancy ($)        : ${pnl_arr.mean():.2f}")
        print(f"  Colchón Mínimo ($)    : ${min_cush:,.2f}")
        print(f"  Max Drawdown Buffer   : {max_dd_buffer:.2f}%")

    print("=" * 80)
    print("      VALIDACIÓN IN-SAMPLE vs OUT-OF-SAMPLE (PDH SWEEP SHORT)")
    print("=" * 80)

    is_mask = (df.index >= "2022-01-01") & (df.index < "2024-01-01")
    oos_mask = (df.index >= "2024-01-01")

    evaluate_subperiod(df[is_mask], "IN-SAMPLE (2022 - 2023)")
    evaluate_subperiod(df[oos_mask], "OUT-OF-SAMPLE A CIEGAS (2024 - 2026)")
    print("=" * 80)

if __name__ == "__main__":
    run_split_validation()
