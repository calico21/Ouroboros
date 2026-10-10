from pathlib import Path
import pandas as pd
import numpy as np

def run_mnq_deep_audit():
    data_path = Path("data/processed/mnq_5m_continuous.parquet")
    if not data_path.exists():
        print(f"Error: {data_path} no encontrado.")
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
    df["day_name"] = df.index.day_name()
    df["day_of_week"] = df.index.dayofweek  # 0: Mon, 1: Tue, 2: Wed, 3: Thu, 4: Fri

    # Niveles diarios previos
    daily = df.groupby("date").agg(
        d_high=("high", "max"),
        d_close=("close", "last")
    )
    daily["pdh"] = daily["d_high"].shift(1)
    daily["pdc"] = daily["d_close"].shift(1)
    df["pdh"] = df["date"].map(daily["pdh"])
    df["pdc"] = df["date"].map(daily["pdc"])

    # VWAP RTH
    is_rth = (df["hour_min"] >= "09:30") & (df["hour_min"] <= "16:00")
    df["tp"] = (df["high"] + df["low"] + df["close"]) / 3.0
    df["tp_vol"] = df["tp"] * df["volume"]
    rth_df = df[is_rth].copy()
    rth_df["cum_tp_vol"] = rth_df.groupby("date")["tp_vol"].cumsum()
    rth_df["cum_vol"] = rth_df.groupby("date")["volume"].cumsum()
    df["vwap"] = rth_df["cum_tp_vol"] / rth_df["cum_vol"]
    df["vwap"] = df.groupby("date")["vwap"].ffill()

    def simulate_subset(sub_df, contracts=2, target_r=1.40, 
                        max_penetration=15.0, start_t="09:45", end_t="14:30", 
                        allowed_days=None, gap_filter=None):
        dates = sub_df["date"].values
        hour_mins = sub_df["hour_min"].values
        days_of_week = sub_df["day_of_week"].values
        opens = sub_df["open"].values
        highs = sub_df["high"].values
        lows = sub_df["low"].values
        closes = sub_df["close"].values
        vwaps = sub_df["vwap"].values
        pdhs = sub_df["pdh"].values
        pdcs = sub_df["pdc"].values

        balance = 50000.0
        peak = 50000.0
        floor = 47500.0
        active = False
        entry_p = stop_p = target_p = 0.0
        trades = []
        cushions = []
        prev_date = None
        traded_today = False
        rth_open_price = np.nan

        for i in range(len(sub_df)):
            c_date = dates[i]
            c_time = hour_mins[i]
            dow = days_of_week[i]
            o, h, l, c = opens[i], highs[i], lows[i], closes[i]

            if c_date != prev_date:
                traded_today = False
                prev_date = c_date
                rth_open_price = np.nan

            if c_time == "09:30":
                rth_open_price = o

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
                    active = False

            if not active and not traded_today:
                if start_t <= c_time <= end_t:
                    if allowed_days is None or dow in allowed_days:
                        # Filtro de Gap si está activo
                        gap_ok = True
                        if gap_filter == "GAP_UP" and not np.isnan(rth_open_price) and not np.isnan(pdcs[i]):
                            gap_ok = (rth_open_price > pdcs[i])
                        elif gap_filter == "GAP_DOWN" and not np.isnan(rth_open_price) and not np.isnan(pdcs[i]):
                            gap_ok = (rth_open_price <= pdcs[i])

                        if gap_ok:
                            pdh_val = pdhs[i]
                            vwap_val = vwaps[i]
                            if not np.isnan(pdh_val):
                                sweep_dist = h - pdh_val
                                if 0 < sweep_dist <= max_penetration and c < pdh_val and c < vwap_val:
                                    active = True
                                    entry_p = c - 0.25
                                    raw_stop = (h + 0.50) - entry_p
                                    stop_dist = min(max(raw_stop, 10.0), 22.0)
                                    stop_p = entry_p + stop_dist
                                    target_p = entry_p - (target_r * stop_dist)
                                    traded_today = True

            cushions.append(balance - floor)

        pnl_arr = np.array(trades) if len(trades) > 0 else np.array([0.0])
        wins = pnl_arr[pnl_arr > 0]
        losses = pnl_arr[pnl_arr <= 0]
        wr = len(wins) / len(pnl_arr) * 100 if len(pnl_arr) > 0 else 0
        pf = wins.sum() / abs(losses.sum()) if abs(losses.sum()) > 0 else 0
        min_cush = min(cushions) if len(cushions) > 0 else 0
        max_dd_pct = ((2500.0 - min_cush) / 2500.0) * 100.0

        return {
            "n": len(pnl_arr),
            "wr": wr,
            "pf": pf,
            "pnl": pnl_arr.sum(),
            "dd": max_dd_pct
        }

    is_mask = (df.index >= "2022-01-01") & (df.index < "2024-01-01")
    oos_mask = (df.index >= "2024-01-01")

    def print_comparison(title, param_list):
        print("\n" + "=" * 90)
        print(f" AUDITORÍA: {title}")
        print("=" * 90)
        print(f"{'Configuración':<28} | {'IS: N':<5} {'IS: WR':<7} {'IS: PF':<6} {'IS: PnL':<10} | {'OOS: N':<6} {'OOS: WR':<8} {'OOS: PF':<7} {'OOS: PnL':<10} {'OOS: DD':<7}")
        print("-" * 90)
        for label, kwargs in param_list:
            res_is = simulate_subset(df[is_mask], **kwargs)
            res_oos = simulate_subset(df[oos_mask], **kwargs)
            print(
                f"{label:<28} | {res_is['n']:<5} {res_is['wr']:<6.1f}% {res_is['pf']:<6.2f} ${res_is['pnl']:<9.0f} | "
                f"{res_oos['n']:<6} {res_oos['wr']:<7.1f}% {res_oos['pf']:<7.2f} ${res_oos['pnl']:<9.0f} {res_oos['dd']:<6.1f}%"
            )

    # 1. Auditoría por Día de la Semana
    days_params = [
        ("Base (Lunes a Viernes)", {}),
        ("Solo Lunes (Mon)", {"allowed_days": [0]}),
        ("Solo Martes (Tue)", {"allowed_days": [1]}),
        ("Solo Miércoles (Wed)", {"allowed_days": [2]}),
        ("Solo Jueves (Thu)", {"allowed_days": [3]}),
        ("Solo Viernes (Fri)", {"allowed_days": [4]}),
        ("Sin Viernes (Mon-Thu)", {"allowed_days": [0, 1, 2, 3]}),
    ]
    print_comparison("DESGLOSE POR DÍA DE LA SEMANA", days_params)

    # 2. Auditoría por Ventana Horaria de Entrada
    time_params = [
        ("Base: 09:45 a 14:30 ET", {"start_t": "09:45", "end_t": "14:30"}),
        ("Mañana Pura: 09:45 a 11:30 ET", {"start_t": "09:45", "end_t": "11:30"}),
        ("Mañana Ampliada: 09:45 a 12:30 ET", {"start_t": "09:45", "end_t": "12:30"}),
        ("Mediodía en adelante: 11:30 a 14:30 ET", {"start_t": "11:30", "end_t": "14:30"}),
        ("Filtro Anti-Open: 10:00 a 13:00 ET", {"start_t": "10:00", "end_t": "13:00"}),
    ]
    print_comparison("VENTANA HORARIA DE ENTRADA", time_params)

    # 3. Auditoría por Distancia Máxima de Penetración del Barrido
    sweep_params = [
        ("Penetración <= 8 pts", {"max_penetration": 8.0}),
        ("Penetración <= 12 pts", {"max_penetration": 12.0}),
        ("Base: Penetración <= 15 pts", {"max_penetration": 15.0}),
        ("Penetración <= 20 pts", {"max_penetration": 20.0}),
        ("Penetración <= 25 pts", {"max_penetration": 25.0}),
    ]
    print_comparison("TOLERANCIA DE BARRIDO DE PDH", sweep_params)

    # 4. Auditoría por Régimen de Gap de Apertura
    gap_params = [
        ("Base (Todos los días)", {}),
        ("Solo Días con Gap Up", {"gap_filter": "GAP_UP"}),
        ("Solo Días con Gap Down", {"gap_filter": "GAP_DOWN"}),
    ]
    print_comparison("RÉGIMEN DE APERTURA (GAP CONTEXT)", gap_params)
    print("=" * 90 + "\n")

if __name__ == "__main__":
    run_mnq_deep_audit()
