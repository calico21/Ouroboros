import numpy as np
import pandas as pd
from typing import Optional, Dict, Any

try:
    import yfinance as yf
    HAS_YFINANCE = True
except (ImportError, ModuleNotFoundError):
    HAS_YFINANCE = False

from live.auction_engine import AuctionEngine
from live.state_manager import StateManager
from live.config import TIMEZONE, WINDOW_START, WINDOW_END


_GLOBAL_AUCTION_ENGINES: Dict[str, AuctionEngine] = {}


def get_auction_engine(sym: str) -> AuctionEngine:
    if sym not in _GLOBAL_AUCTION_ENGINES:
        _GLOBAL_AUCTION_ENGINES[sym] = AuctionEngine(tz_str=TIMEZONE)
    return _GLOBAL_AUCTION_ENGINES[sym]


def fetch_5m_data(ticker: str, period: str = "5d") -> Optional[pd.DataFrame]:
    """
    Descarga velas 5m con yfinance y normaliza nombres de columnas y zona horaria EST.
    """
    if not HAS_YFINANCE:
        print(f"⚠️ [ENGINE] yfinance no está disponible en este intérprete para descargar {ticker}.")
        return None

    try:
        t = yf.Ticker(ticker)
        df = t.history(period=period, interval="5m")
        if df.empty or len(df) < 15:
            return None

        df = df.rename(columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume"
        })

        if df.index.tz is None:
            df.index = df.index.tz_localize(TIMEZONE, ambiguous="NaT")
        else:
            df.index = df.index.tz_convert(TIMEZONE)

        df["date"] = df.index.date
        df["hour_min"] = df.index.strftime("%H:%M")
        return df
    except Exception as e:
        print(f"⚠️ Error descargando velas 5m para {ticker}: {e}")
        return None


def evaluate_signal(
    sym: str,
    cfg: Dict[str, Any],
    state_mgr: StateManager,
    df_primary: Optional[pd.DataFrame] = None,
    df_ref: Optional[pd.DataFrame] = None
) -> Optional[Dict[str, Any]]:
    """
    Evalúa si la vela cerrada inmediatamente anterior genera señal bajo el modelo v3.0:
      - Horario de subasta matinal: 09:30 a 12:30 EST.
      - Microestructura Dalton 70% Value Area + Bandas VWAP +/- 1.5 sigma.
      - Clasificación de régimen TREND vs BALANCED.
      - SMT cross-asset con activo de referencia.
      - Dynamic sizing vía DP_V1_ADAPTIVE (3, 5, 7, 8, 10 contratos).
    """
    ticker_p = cfg.get("ticker", sym)
    ticker_r = cfg.get("reference_ticker", "SPY")

    if df_primary is None:
        df_primary = fetch_5m_data(ticker_p)
    if df_primary is None or len(df_primary) < 15:
        return None

    if df_ref is None and ticker_r:
        df_ref = fetch_5m_data(ticker_r)

    # Filtrar ventana horaria de subasta matinal
    bar = df_primary.iloc[-2]
    c_time = bar["hour_min"]
    w_start = cfg.get("start", WINDOW_START)
    w_end = cfg.get("end", WINDOW_END)

    if not (w_start <= c_time <= w_end):
        return None

    # Motor de subasta
    engine = get_auction_engine(sym)
    sig = engine.evaluate_signal(df_primary, df_ref, asset_config=cfg)
    if sig is None:
        return None

    # Asignación de unidades vía DP_V1_ADAPTIVE
    units = state_mgr.compute_position_size(is_smt_confirmed=sig["is_smt"])

    # Multiplicador para acciones ETF (ej. QQQ) vs Contratos de Futuros (MNQ)
    pt_val = cfg.get("pt_val", 2.0)
    shares_per_unit = cfg.get("shares_per_unit", 1)
    total_qty = units * shares_per_unit

    risk_usd = sig["sl_dist"] * pt_val * total_qty

    return {
        "sym": sym,
        "side": sig["side"],
        "entry": sig["entry"],
        "stop": sig["stop"],
        "target": sig["target"],
        "stop_dist": sig["sl_dist"],
        "target_dist": sig["tp_dist"],
        "ctos": units,
        "qty": total_qty,
        "risk_usd": round(risk_usd, 2),
        "time": sig["time"],
        "trigger": sig["trigger"],
        "regime": sig["regime"],
        "is_smt": sig["is_smt"],
        "atr": sig["atr"]
    }
