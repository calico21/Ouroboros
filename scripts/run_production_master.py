import numpy as np
import pandas as pd
from pathlib import Path

def run_master_production():
    df = pd.read_parquet("data/processed/mnq_5m_continuous.parquet")
    if df.index.tz is None:
        df.index = df.index.tz_localize("America/New_York")
    else:
        df.index = df.index.tz_convert("America/New_York")
    df = df.sort_index()
    df["date"] = df.index.date
    df["hour_min"] = df.index.strftime("%H:%M")

    # Niveles e Indicadores Oficiales
    daily = df.groupby("date").agg(d_high=("high", "max"))
    daily["pdh"] = daily["d_high"].shift(1)
    df["pdh"] = df["date"].map(daily["pdh"])

    is_rth = (df["hour_min"] >= "09:30") & (df["hour_min"] <= "16:00")
    df["tp"] = (df["high"] + df["low"] + df["close"]) / 3.0
    df["tp_vol"] = df["tp"] * df["volume"]
    rth_df = df[is_rth].copy()
    rth_df["cum_tp_vol"] = rth_df.groupby("date")["tp_vol"].cumsum()
    rth_df["cum_vol"] = rth_df.groupby("date")["volume"].cumsum()
    df["vwap"] = rth_df["cum_tp_vol"] / rth_df["cum_vol"]
    df["vwap"] = df.groupby("date")["vwap"].ffill()

    df["vol_sma20"] = df["volume"].rolling(20, min_periods=5).mean()

    def execute_backtest(sub_df, contracts=3, target_r=1.50):
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
        timestamps = sub_df.index

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
                    trades.append({
                        "timestamp": timestamps[i],
                        "date": c_date,
                        "time": c_time,
                        "entry": entry_p,
                        "exit": exit_p,
                        "pts": pts,
                        "net": net,
                        "balance": balance,
                        "cushion": balance - floor
                    })
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
                        vol_ok = not np.isnan(v_sma) and (v_val >= 1.1 * v_sma)

                        if 0 < sweep_dist <= 15.0 and c < pdh_val and c < vwap_val and vol_ok:
                            active = True
                            entry_p = c - 0.25
                            raw_stop = (h + 0.50) - entry_p
                            stop_dist = min(max(raw_stop, 10.0), 22.0)
                            stop_p = entry_p + stop_dist
                            target_p = entry_p - (target_r * stop_dist)
                            traded_today = True

            cushions.append(balance - floor)

        pnl_arr = np.array([t["net"] for t in trades]) if len(trades) > 0 else np.array([0.0])
        wins = pnl_arr[pnl_arr > 0]
        losses = pnl_arr[pnl_arr <= 0]
        wr = len(wins) / len(pnl_arr) * 100 if len(pnl_arr) > 0 else 0
        pf = wins.sum() / abs(losses.sum()) if abs(losses.sum()) > 0 else 0
        min_cush = min(cushions) if len(cushions) > 0 else 0
        max_dd = 2500.0 - min_cush
        max_dd_pct = (max_dd / 2500.0) * 100.0

        pnl_series = pd.Series(list(daily_pnl.values()))
        mean_ret = pnl_series.mean()
        downside = pnl_series[pnl_series < 0]
        downside_dev = np.sqrt((downside ** 2).sum() / len(pnl_series))
        sortino = (mean_ret / downside_dev) * np.sqrt(252) if downside_dev > 0 else 0.0

        return {
            "n": len(pnl_arr),
            "wr": wr,
            "pf": pf,
            "pnl": pnl_arr.sum(),
            "dd": max_dd,
            "dd_pct": max_dd_pct,
            "sortino": sortino,
            "trades": trades,
            "pnl_arr": pnl_arr
        }

    is_mask = (df.index >= "2022-01-01") & (df.index < "2024-01-01")
    oos_mask = (df.index >= "2024-01-01")

    # Auditoría por tamaño de contrato
    for contracts in [2, 3]:
        r_is = execute_backtest(df[is_mask], contracts=contracts, target_r=1.50)
        r_oos = execute_backtest(df[oos_mask], contracts=contracts, target_r=1.50)
        tot_pnl = r_is["pnl"] + r_oos["pnl"]
        tot_trades = r_is["n"] + r_oos["n"]

        print("=" * 85)
        print(f"   OUROBOROS MNQ MASTER: CONFIGURACIÓN OFICIAL ({contracts} CONTRATOS, TARGET 1.50R)")
        print("=" * 85)
        print(f"  Trades Totales (2022-2026) : {tot_trades} trades (~18.6 trades/año)")
        print(f"  PnL Total Acumulado        : ${tot_pnl:,.2f}")
        print(f"  -------------------------------------------------------------")
        print(f"  [IN-SAMPLE 2022-2023]      : WR: {r_is['wr']:.1f}% | PF: {r_is['pf']:.2f} | PnL: ${r_is['pnl']:,.2f}")
        print(f"  [OUT-OF-SAMPLE 2024-2026]  : WR: {r_oos['wr']:.1f}% | PF: {r_oos['pf']:.2f} | PnL: ${r_oos['pnl']:,.2f}")
        print(f"  Sortino Calendario OOS     : {r_oos['sortino']:.2f}")
        print(f"  Max Drawdown Colchón Apex  : ${r_oos['dd']:,.2f} ({r_oos['dd_pct']:.1f}% del límite de $2,500)")
        print("=" * 85)

        # Simulación Monte Carlo
        n_sims = 50000
        passes = 0
        fails = 0
        trade_counts = []
        trades_pool = np.concatenate([r_is["pnl_arr"], r_oos["pnl_arr"]])

        for _ in range(n_sims):
            sim_trades = np.random.choice(trades_pool, size=200, replace=True)
            bal = 50000.0
            peak = 50000.0
            floor = 47500.0

            for idx, t in enumerate(sim_trades):
                bal += t
                if bal > peak:
                    peak = bal
                    floor = 50100.0 if peak >= 52600.0 else peak - 2500.0

                if bal <= floor:
                    fails += 1
                    break

                if (bal - 50000.0) >= 3000.0:
                    passes += 1
                    trade_counts.append(idx + 1)
                    break

        p_pass = (passes / n_sims) * 100.0
        p_fail = (fails / n_sims) * 100.0
        avg_t = np.mean(trade_counts) if trade_counts else 0

        print(f"  MONTE CARLO APEX 50k ({n_sims:,} iteraciones):")
        print(f"    Probabilidad de Pasar Evaluación : {p_pass:.2f}%")
        print(f"    Probabilidad de Quebrar Cuenta   : {p_fail:.2f}%")
        print(f"    Trades Promedio para Pasar ($3k) : {avg_t:.1f} trades")
        print("=" * 85 + "\n")

    # Guardar CSV de trades para inspección
    trades_df = pd.DataFrame(r_oos["trades"])
    Path("reports/artifacts").mkdir(parents=True, exist_ok=True)
    trades_df.to_csv("reports/artifacts/production_master_trades_oos.csv", index=False)
    print(">>> Registro detallado guardado en: reports/artifacts/production_master_trades_oos.csv")

if __name__ == "__main__":
    run_master_production()
