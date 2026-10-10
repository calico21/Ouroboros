import numpy as np
import pandas as pd
from pathlib import Path

# Cargar dataset
df = pd.read_parquet("data/processed/mnq_5m_continuous.parquet")
if df.index.tz is None:
    df.index = df.index.tz_localize("America/New_York")
else:
    df.index = df.index.tz_convert("America/New_York")
df = df.sort_index()
df["date"] = df.index.date
df["hour_min"] = df.index.strftime("%H:%M")

daily = df.groupby("date").agg(d_high=("high", "max"), d_close=("close", "last"))
daily["pdh"] = daily["d_high"].shift(1)
daily["pdc"] = daily["d_close"].shift(1)
df["pdh"] = df["date"].map(daily["pdh"])
df["pdc"] = df["date"].map(daily["pdc"])

is_rth = (df["hour_min"] >= "09:30") & (df["hour_min"] <= "16:00")
df["tp"] = (df["high"] + df["low"] + df["close"]) / 3.0
df["tp_vol"] = df["tp"] * df["volume"]
rth_df = df[is_rth].copy()
rth_df["cum_tp_vol"] = rth_df.groupby("date")["tp_vol"].cumsum()
rth_df["cum_vol"] = rth_df.groupby("date")["volume"].cumsum()
df["vwap"] = rth_df["cum_tp_vol"] / rth_df["cum_vol"]
df["vwap"] = df.groupby("date")["vwap"].ffill()

def get_trades(contracts=2, no_gap_down=False):
    dates = df["date"].values
    hour_mins = df["hour_min"].values
    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    vwaps = df["vwap"].values
    pdhs = df["pdh"].values
    pdcs = df["pdc"].values

    active = False
    entry_p = stop_p = target_p = 0.0
    trades = []
    prev_date = None
    traded_today = False
    rth_open = np.nan

    for i in range(len(df)):
        c_date = dates[i]
        c_time = hour_mins[i]
        o, h, l, c = opens[i], highs[i], lows[i], closes[i]

        if c_date != prev_date:
            traded_today = False
            prev_date = c_date
            rth_open = np.nan

        if c_time == "09:30":
            rth_open = o

        if active:
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
                trades.append(net)
                active = False

        if not active and not traded_today:
            if "09:45" <= c_time <= "12:30":
                gap_valid = True
                if no_gap_down and not np.isnan(rth_open) and not np.isnan(pdcs[i]):
                    gap_valid = (rth_open >= pdcs[i])

                if gap_valid:
                    pdh_val = pdhs[i]
                    vwap_val = vwaps[i]
                    if not np.isnan(pdh_val):
                        sweep_dist = h - pdh_val
                        if 0 < sweep_dist <= 15.0 and c < pdh_val and c < vwap_val:
                            active = True
                            entry_p = c - 0.25
                            raw_stop = (h + 0.50) - entry_p
                            stop_dist = min(max(raw_stop, 10.0), 22.0)
                            stop_p = entry_p + stop_dist
                            target_p = entry_p - (1.40 * stop_dist)
                            traded_today = True

    return np.array(trades)

def simulate_apex(trade_arr, n_sims=50000, target=3000.0, buffer=2500.0, max_trades=200):
    passes = 0
    fails = 0
    trade_counts = []

    for _ in range(n_sims):
        sim_trades = np.random.choice(trade_arr, size=max_trades, replace=True)
        balance = 50000.0
        peak = 50000.0
        floor = 47500.0

        for idx, t_pnl in enumerate(sim_trades):
            balance += t_pnl
            if balance > peak:
                peak = balance
                floor = 50100.0 if peak >= 52600.0 else peak - buffer

            if balance <= floor:
                fails += 1
                break

            if (balance - 50000.0) >= target:
                passes += 1
                trade_counts.append(idx + 1)
                break

    return (passes / n_sims) * 100.0, (fails / n_sims) * 100.0, np.mean(trade_counts) if trade_counts else 0

print("=" * 80)
print("   SIMULACIÓN MONTE CARLO APEX 50k: ESTRATEGIA OPTIMIZADA (50,000 RUNS)")
print("=" * 80)

tests = [
    ("Config 2 (Solo Mañana, 2 MNQ)", get_trades(contracts=2, no_gap_down=False)),
    ("Config 2 (Solo Mañana, 3 MNQ)", get_trades(contracts=3, no_gap_down=False)),
    ("Config 4 (Mañana + No Gap Down, 2 MNQ)", get_trades(contracts=2, no_gap_down=True)),
    ("Config 4 (Mañana + No Gap Down, 3 MNQ)", get_trades(contracts=3, no_gap_down=True)),
]

for label, trades in tests:
    p_pass, p_fail, avg_t = simulate_apex(trades)
    print(f"\n>> {label}")
    print(f"   Trades en Histórico      : {len(trades)}")
    print(f"   Probabilidad de Aprobación : {p_pass:.2f}%")
    print(f"   Probabilidad de Quiebra    : {p_fail:.2f}%")
    print(f"   Trades Promedio para Pasar : {avg_t:.1f}")

print("\n" + "=" * 80)
