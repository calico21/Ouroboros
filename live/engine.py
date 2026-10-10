import numpy as np
import pandas as pd
import yfinance as yf

def fetch_5m_data(ticker):
    try:
        t = yf.Ticker(ticker)
        df = t.history(period="2d", interval="5m")
        if df.empty or len(df) < 20:
            return None
        df = df.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
        if df.index.tz is None:
            df.index = df.index.tz_localize("America/New_York", ambiguous="NaT")
        else:
            df.index = df.index.tz_convert("America/New_York")
        df["date"] = df.index.date
        df["hour_min"] = df.index.strftime("%H:%M")
        return df
    except Exception:
        return None

def evaluate_signal(sym, cfg, state_mgr):
    df = fetch_5m_data(cfg["ticker"])
    if df is None:
        return None

    today = df["date"].iloc[-1]
    df_today = df[df["date"] == today].copy()
    df_prev = df[df["date"] < today]
    if df_prev.empty or len(df_today) < 3:
        return None

    pdh = df_prev["high"].max()
    pdl = df_prev["low"].min()

    # Cálculo dinámico de VWAP intradía
    df_today["tp"] = (df_today["high"] + df_today["low"] + df_today["close"]) / 3.0
    cum_vol = df_today["volume"].cumsum()
    vwap = (df_today["tp"] * df_today["volume"]).cumsum() / np.where(cum_vol == 0, 1e-9, cum_vol)
    vol_sma = df_today["volume"].rolling(20, min_periods=5).mean()

    # Penúltima fila = vela cerrada de 5m
    bar = df_today.iloc[-2]
    c_time = bar["hour_min"]

    # Comprobación de ventana operativa estricta
    if not (cfg["start"] <= c_time <= cfg["end"]):
        return None

    o, h, l, c = bar["open"], bar["high"], bar["low"], bar["close"]
    cur_vwap = vwap.iloc[-2]
    v = bar["volume"]
    v_s = vol_sma.iloc[-2]

    # Filtro de volumen institucional
    if np.isnan(v_s) or v < 0.95 * v_s:
        return None

    tick = cfg["tick"]

    # Sizing dinámico
    cushion = state_mgr.get_cushion()
    if state_mgr.state["frozen"]:
        ctos = cfg["sprint_ctos"]
    elif cushion < 1300.0:
        ctos = max(cfg["base_ctos"] - 1, 1)
    else:
        ctos = cfg["base_ctos"]

    # Barrido PDH Short
    sw_h = h - pdh
    if 0 < sw_h <= cfg["max_sw"] and c < pdh and c < cur_vwap and c < o:
        entry = c - tick  # Penalización 1 tick slip
        raw_stop = (h + 2 * tick) - entry
        stop_dist = min(max(raw_stop, cfg["min_stop"]), cfg["max_stop"])
        stop = entry + stop_dist
        target = entry - (1.75 * stop_dist)
        risk_usd = stop_dist * cfg["pt_val"] * ctos
        return {
            "sym": sym, "side": "SELL", "entry": entry, "stop": stop, "target": target,
            "stop_dist": stop_dist, "ctos": ctos, "risk_usd": risk_usd,
            "time": c_time, "trigger": "PDH_SWEEP_SHORT"
        }

    # Barrido PDL Long
    sw_l = pdl - l
    if 0 < sw_l <= cfg["max_sw"] and c > pdl and c > cur_vwap and c > o:
        entry = c + tick  # Penalización 1 tick slip
        raw_stop = entry - (l - 2 * tick)
        stop_dist = min(max(raw_stop, cfg["min_stop"]), cfg["max_stop"])
        stop = entry - stop_dist
        target = entry + (1.75 * stop_dist)
        risk_usd = stop_dist * cfg["pt_val"] * ctos
        return {
            "sym": sym, "side": "BUY", "entry": entry, "stop": stop, "target": target,
            "stop_dist": stop_dist, "ctos": ctos, "risk_usd": risk_usd,
            "time": c_time, "trigger": "PDL_SWEEP_LONG"
        }

    return None
