from pathlib import Path
import numpy as np
import pandas as pd
import scipy.stats as stats

# =============================================================================
# ESPECIFICACIONES DE CONTRATOS Y PARÁMETROS NORMALIZADOS POR ACTIVO
# =============================================================================
ASSET_SPECS = {
    "MNQ": {
        "file": "mnq_5m_continuous.parquet",
        "ticker_alt": "NQ=F",
        "point_val": 2.0,
        "tick_size": 0.25,
        "max_sweep": 15.0,
        "min_stop": 10.0,
        "max_stop": 22.0,
        "buffer_offset": 0.50,
        "comm_rt": 1.24,
    },
    "MES": {
        "file": "mes_5m_continuous.parquet",
        "ticker_alt": "ES=F",
        "point_val": 5.0,
        "tick_size": 0.25,
        "max_sweep": 4.25,
        "min_stop": 3.0,
        "max_stop": 6.5,
        "buffer_offset": 0.25,
        "comm_rt": 1.24,
    },
    "MYM": {
        "file": "mym_5m_continuous.parquet",
        "ticker_alt": "YM=F",
        "point_val": 0.50,
        "tick_size": 1.0,
        "max_sweep": 32.0,
        "min_stop": 22.0,
        "max_stop": 48.0,
        "buffer_offset": 1.0,
        "comm_rt": 1.24,
    },
    "M2K": {
        "file": "m2k_5m_continuous.parquet",
        "ticker_alt": "RTY=F",
        "point_val": 10.0,
        "tick_size": 0.10,
        "max_sweep": 1.80,
        "min_stop": 1.2,
        "max_stop": 2.8,
        "buffer_offset": 0.10,
        "comm_rt": 1.24,
    },
}

def load_or_fetch_asset_data(symbol, spec):
    data_dir = Path("data/processed")
    file_path = data_dir / spec["file"]

    if file_path.exists():
        df = pd.read_parquet(file_path)
    else:
        # Si no existe localmente, descargar histórico equivalente vía yfinance
        print(f"⚠️  {spec['file']} no encontrado en {data_dir}. Descargando {spec['ticker_alt']}...")
        try:
            import yfinance as yf
            ticker = yf.Ticker(spec["ticker_alt"])
            # Descargar máximo periodo disponible en resolución intradía
            df_raw = ticker.history(period="60d", interval="5m")
            if df_raw.empty:
                print(f"❌ No se pudieron descargar datos para {symbol}.")
                return None
            df = df_raw.rename(columns={
                "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"
            })[["open", "high", "low", "close", "volume"]].copy()
            file_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(file_path)
            print(f"✅ Guardado dataset descargado en {file_path}")
        except Exception as e:
            print(f"❌ Error descargando {symbol}: {e}")
            return None

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

    # Aislamiento RTH Estricto
    rth_mask = (df["hour_min"] >= "09:30") & (df["hour_min"] <= "16:00")
    df_rth = df[rth_mask].copy()

    # Niveles e Indicadores RTH
    daily_h = df_rth.groupby("date")["high"].max()
    df_rth["pdh"] = df_rth["date"].map(daily_h.shift(1))

    df_rth["tp"] = (df_rth["high"] + df_rth["low"] + df_rth["close"]) / 3.0
    df_rth["tp_vol"] = df_rth["tp"] * df_rth["volume"]
    df_rth["cum_tp_vol"] = df_rth.groupby("date")["tp_vol"].cumsum()
    df_rth["cum_vol"] = df_rth.groupby("date")["volume"].cumsum()
    df_rth["vwap"] = df_rth["cum_tp_vol"] / df_rth["cum_vol"]

    df_rth["vol_sma20"] = df_rth.groupby("date")["volume"].transform(
        lambda s: s.rolling(20, min_periods=5).mean()
    )
    return df_rth

def backtest_asset(symbol, df_rth, spec, contracts=2, target_r=1.50):
    slip_pts = spec["tick_size"]
    comm_dollars = spec["comm_rt"] * contracts
    point_val = spec["point_val"] * contracts

    dates = df_rth["date"].values
    hour_mins = df_rth["hour_min"].values
    opens = df_rth["open"].values
    highs = df_rth["high"].values
    lows = df_rth["low"].values
    closes = df_rth["close"].values
    vwaps = df_rth["vwap"].values
    pdhs = df_rth["pdh"].values
    vols = df_rth["volume"].values
    vol_smas = df_rth["vol_sma20"].values

    split_date = pd.Timestamp("2024-01-01").date()
    trades = []
    active = False
    pending = False
    sig_high = 0.0
    entry_p = stop_p = target_p = stop_dist = 0.0
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
            entry_p = o - slip_pts
            raw_stop = (sig_high + spec["buffer_offset"]) - entry_p
            stop_dist = min(max(raw_stop, spec["min_stop"]), spec["max_stop"])
            stop_p = entry_p + stop_dist
            target_p = entry_p - (target_r * stop_dist)
            active = True
            pending = False

        if active:
            hit_stop = h >= stop_p
            hit_target = l <= target_p
            closed = False
            exit_p = 0.0

            if hit_stop:
                closed = True
                exit_p = max(o, stop_p) + slip_pts
            elif hit_target:
                closed = True
                exit_p = target_p
            elif c_time >= "15:55":
                closed = True
                exit_p = c + slip_pts

            if closed:
                pts = entry_p - exit_p
                net_dollars = (pts * point_val) - comm_dollars
                risk_dollars = stop_dist * point_val
                r_net = net_dollars / risk_dollars

                trades.append({
                    "date": c_date,
                    "symbol": symbol,
                    "net_dollars": net_dollars,
                    "r_net": r_net,
                    "pts": pts,
                    "stop_pts": stop_dist,
                    "is_win": net_dollars > 0,
                    "is_oos": c_date >= split_date
                })
                active = False

        if not active and not pending and not traded_today:
            if "09:45" <= c_time <= "12:30":
                pdh_val = pdhs[i]
                vwap_val = vwaps[i]
                v_val = vols[i]
                v_sma = vol_smas[i]
                vol_ok = not np.isnan(v_sma) and (v_val >= 1.0 * v_sma)

                if not np.isnan(pdh_val) and vol_ok:
                    sw = h - pdh_val
                    if 0 < sw <= spec["max_sweep"] and c < pdh_val and c < vwap_val:
                        pending = True
                        sig_high = h
                        traded_today = True

    return trades

def run_cross_asset_audit():
    print("=" * 115)
    print("      AUDITORÍA CROSS-ASSET: PDH SWEEP SHORT EN LOS 4 GRANDES ÍNDICES CME (2022-2026)")
    print("      Condiciones: Entrada Open[t+1], 1 Tick Slip por lado, Comisiones Reales, Target 1.50R")
    print("=" * 115)

    asset_results = {}
    valid_symbols = []

    for sym, spec in ASSET_SPECS.items():
        df_asset = load_or_fetch_asset_data(sym, spec)
        if df_asset is not None and len(df_asset) > 1000:
            trades = backtest_asset(sym, df_asset, spec, contracts=2, target_r=1.50)
            asset_results[sym] = trades
            valid_symbols.append(sym)
        else:
            print(f"⏩ Omitiendo {sym} por falta de datos suficientes.")

    print(f"\n{'Activo':<10} | {'Trades/Año':<11} {'IS: PF':<8} {'OOS: WR':<9} {'OOS: PF':<8} {'OOS Net ($)':<12} {'E[R] OOS':<10} {'IC 95% Bootstrap'}")
    print("-" * 115)

    all_trades_flat = []
    for sym in valid_symbols:
        tr = asset_results[sym]
        all_trades_flat.extend(tr)

        t_is = [t for t in tr if not t["is_oos"]]
        t_oos = [t for t in tr if t["is_oos"]]

        p_is = np.array([t["net_dollars"] for t in t_is]) if t_is else np.array([0.0])
        p_oos = np.array([t["net_dollars"] for t in t_oos]) if t_oos else np.array([0.0])
        r_oos = np.array([t["r_net"] for t in t_oos]) if t_oos else np.array([0.0])

        pf_is = p_is[p_is > 0].sum() / abs(p_is[p_is <= 0].sum()) if abs(p_is[p_is <= 0].sum()) > 0 else 0
        pf_oos = p_oos[p_oos > 0].sum() / abs(p_oos[p_oos <= 0].sum()) if abs(p_oos[p_oos <= 0].sum()) > 0 else 0
        wr_oos = len(p_oos[p_oos > 0]) / len(p_oos) * 100 if len(p_oos) > 0 else 0
        exp_r_oos = r_oos.mean() if len(r_oos) > 0 else 0

        boot_means = []
        if len(r_oos) > 5:
            np.random.seed(42)
            for _ in range(5000):
                boot_means.append(np.random.choice(r_oos, size=len(r_oos), replace=True).mean())
            ci_low = np.percentile(boot_means, 2.5)
            ci_high = np.percentile(boot_means, 97.5)
        else:
            ci_low, ci_high = 0.0, 0.0

        years = 4.77
        tr_per_yr = len(tr) / years

        print(
            f"{sym:<10} | {tr_per_yr:<11.1f} {pf_is:<8.2f} {wr_oos:<8.1f}% {pf_oos:<8.2f} "
            f"${p_oos.sum():<11.2f} {exp_r_oos:<+9.3f}R [{ci_low:+.2f}R, {ci_high:+.2f}R]"
        )

    print("=" * 115 + "\n")

    # =========================================================================
    # ANÁLISIS DE CARTERA CROSS-ASSET COMBINADA
    # =========================================================================
    df_all = pd.DataFrame(all_trades_flat)
    if df_all.empty:
        return

    # Agrupar por día: ¿cuántos días coinciden y cuál es la frecuencia neta?
    daily_groups = df_all.groupby("date")
    total_active_days = len(daily_groups)
    overlap_days = sum(len(grp) > 1 for _, grp in daily_groups)

    print("=" * 105)
    print("      CONSOLIDACIÓN DE LA CARTERA CROSS-ASSET")
    print("=" * 105)
    print(f"  • Activos Evaluados Simultáneamente : {', '.join(valid_symbols)}")
    print(f"  • Trades Totales Combinados         : {len(df_all)} (~{len(df_all)/4.77:.1f} trades/año | ~{len(df_all)/57.2:.1f} trades/mes)")
    print(f"  • Días con al menos 1 trade activo  : {total_active_days} días")
    print(f"  • Días con Coincidencia (>1 activo) : {overlap_days} días ({overlap_days/total_active_days*100:.1f}%)")

    # Rendimiento de Cartera (1 trade max por activo; suma de PnL en días de solapamiento)
    p_oos_all = df_all[df_all["is_oos"]]
    pf_port_oos = p_oos_all[p_oos_all["net_dollars"] > 0]["net_dollars"].sum() / \
                  abs(p_oos_all[p_oos_all["net_dollars"] <= 0]["net_dollars"].sum())
    wr_port_oos = len(p_oos_all[p_oos_all["net_dollars"] > 0]) / len(p_oos_all) * 100
    r_port_oos = p_oos_all["r_net"].values

    boot_p = [np.random.choice(r_port_oos, size=len(r_port_oos), replace=True).mean() for _ in range(5000)]
    ci_p_l = np.percentile(boot_p, 2.5)
    ci_p_h = np.percentile(boot_p, 97.5)

    print(f"  • Profit Factor OOS de Cartera      : {pf_port_oos:.2f}")
    print(f"  • Win Rate OOS de Cartera           : {wr_port_oos:.1f}%")
    print(f"  • PnL Neto OOS Total (2 contratos)  : ${p_oos_all['net_dollars'].sum():.2f}")
    print(f"  • Expectativa E[R] OOS              : {r_port_oos.mean():+.3f}R")
    print(f"  • IC 95% Bootstrap de Cartera       : [{ci_p_l:+.3f}R, {ci_p_h:+.3f}R]")
    print("=" * 105 + "\n")

    # =========================================================================
    # SIMULACIÓN MONTE CARLO APEX 50k (OBJETIVO: +$3.000, COLCHÓN: $2.000)
    # =========================================================================
    print("=" * 115)
    print("      SIMULACIÓN MONTE CARLO APEX 50k DE LA CARTERA CROSS-ASSET")
    print("      Límite: 125 Sesiones (6 Meses) | Buffer $2.000 | Target $3.000")
    print("=" * 115)
    print(f"{'Sizing de Cartera':<28} | {'Trades/Mes':<12} {'P(Pass <= 6M)':<16} {'Tasa Breach':<14} {'Veredicto'}")
    print("-" * 115)

    d_daily_r = df_all.groupby("date")["r_net"].sum().values
    n_sims = 20000

    for c_label, r_usd in [("Conservador (1R = $25)", 25.0), ("Moderado (1R = $50)", 50.0), ("Examen 4 MNQ/MES (1R = $80)", 80.0)]:
        passes = 0
        breaches = 0
        for _ in range(n_sims):
            sim_r = np.random.choice(d_daily_r, size=125, replace=True)
            bal = 50000.0
            peak = 50000.0
            floor = 48000.0

            for d_r in sim_r:
                pnl = d_r * r_usd
                bal += pnl
                if bal > peak:
                    peak = bal
                    floor = 50100.0 if peak >= 52600.0 else (peak - 2000.0)

                if bal <= floor:
                    breaches += 1
                    break
                if (bal - 50000.0) >= 3000.0:
                    passes += 1
                    break

        p_pass = (passes / n_sims) * 100.0
        p_breach = (breaches / n_sims) * 100.0
        verdict = "VIABLE" if p_pass > 40.0 and p_breach < 5.0 else ("CONSERVADOR" if p_breach < 1.0 else "EQUILIBRADO")

        print(f"{c_label:<28} | {f'{len(df_all)/57.2:.1f}':<12} {p_pass:<15.1f}% {p_breach:<13.2f}% {verdict}")

    print("=" * 115 + "\n")

if __name__ == "__main__":
    run_cross_asset_audit()
