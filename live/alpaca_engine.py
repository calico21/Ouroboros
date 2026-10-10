import os
import sys
import time
import datetime as dt
from pathlib import Path
import pandas as pd
import numpy as np

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Cargar variables de entorno
for env_path in [".env", "live/.env", os.path.expanduser("~/.env")]:
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

import live.config as cfg
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest, TakeProfitRequest, StopLossRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.enums import DataFeed

# Inicializar Clientes Alpaca
trading_client = TradingClient(cfg.ALPACA_API_KEY, cfg.ALPACA_SECRET_KEY, paper=cfg.ALPACA_PAPER)
data_client = StockHistoricalDataClient(cfg.ALPACA_API_KEY, cfg.ALPACA_SECRET_KEY)

def get_current_positions_count() -> int:
    try:
        positions = trading_client.get_all_positions()
        return len(positions)
    except Exception as e:
        print(f"⚠️ Error obteniendo posiciones activas: {e}")
        return cfg.MAX_CONCURRENT_POSITIONS  # Por seguridad asumimos cupo lleno

def fetch_asset_context(symbol: str) -> pd.DataFrame | None:
    now_utc = dt.datetime.now(dt.timezone.utc)
    start_utc = now_utc - dt.timedelta(days=5)

    req = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame(5, TimeFrameUnit.Minute),
        start=start_utc,
        end=now_utc,
        feed=DataFeed.IEX
    )
    try:
        bars = data_client.get_stock_bars(req)
        df = bars.df
        if df is None or df.empty:
            return None
        if isinstance(df.index, pd.MultiIndex):
            df = df.xs(symbol, level="symbol")
        df = df.tz_convert(cfg.TIMEZONE)
        df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}, inplace=True)
        return df.sort_index()
    except Exception as e:
        print(f"⚠️ Error descargando barras para {symbol}: {e}")
        return None

def analyze_symbol(symbol: str, df: pd.DataFrame):
    m = df.index.hour * 60 + df.index.minute
    d = df[(m >= 570) & (m < 960)].copy()
    if len(d) < 30:
        return None

    d["day"] = d.index.date
    daily = d.groupby("day").agg(H=("High", "max"), L=("Low", "min"))
    
    # Niveles previos y métricas
    last_day = d["day"].iloc[-1]
    prev_days = daily.index[daily.index < last_day]
    if len(prev_days) == 0:
        return None
    prev_day = prev_days[-1]
    pdh = daily.loc[prev_day, "H"]
    pdl = daily.loc[prev_day, "L"]

    # Día actual
    today_bars = d[d["day"] == last_day].copy()
    if len(today_bars) < 3:
        return None

    vol_sma = today_bars["Volume"].rolling(cfg.VOL_SMA_PERIOD).mean().iloc[-2]
    last_closed_bar = today_bars.iloc[-2]
    prev_closed_bar = today_bars.iloc[-3]
    curr_bar = today_bars.iloc[-1]

    # Verificar ventana operativa
    t_min = last_closed_bar.name.hour * 60 + last_closed_bar.name.minute
    w_start = int(cfg.WINDOW_START.split(":")[0]) * 60 + int(cfg.WINDOW_START.split(":")[1])
    w_end = int(cfg.WINDOW_END.split(":")[0]) * 60 + int(cfg.WINDOW_END.split(":")[1])

    if not (w_start <= t_min <= w_end):
        return None

    if np.isnan(vol_sma) or last_closed_bar["Volume"] < (cfg.MIN_VOL_RATIO * vol_sma):
        return None

    # Lógica de absorción PDH/PDL
    side, ext = 0, 0.0
    if prev_closed_bar["High"] > pdh and last_closed_bar["Close"] < pdh:
        side, ext = -1, max(prev_closed_bar["High"], last_closed_bar["High"])
    elif prev_closed_bar["Low"] < pdl and last_closed_bar["Close"] > pdl:
        side, ext = 1, min(prev_closed_bar["Low"], last_closed_bar["Low"])

    if side == 0:
        return None

    entry_est = curr_bar["Open"]
    stop = ext - (side * cfg.STOP_BUFFER_USD)
    risk_per_share = abs(entry_est - stop)

    if risk_per_share < cfg.MIN_RISK_PER_SHARE:
        return None

    shares = int(cfg.RISK_PER_TRADE_USD / risk_per_share)
    shares = min(shares, cfg.MAX_SHARE_CAP)
    if shares <= 0:
        return None

    tp = entry_est + (side * cfg.TP_R_MULTIPLE * risk_per_share)
    vol_ratio = last_closed_bar["Volume"] / vol_sma if vol_sma > 0 else 1.0

    return {
        "symbol": symbol,
        "side": side,
        "entry": round(entry_est, 2),
        "stop": round(stop, 2),
        "tp": round(tp, 2),
        "shares": shares,
        "score": vol_ratio,
        "timestamp": last_closed_bar.name
    }

def execute_bracket_order(sig: dict):
    side_enum = OrderSide.BUY if sig["side"] == 1 else OrderSide.SELL
    print(f"\n🚀 DISPARANDO ORDEN BRACKET: {sig['symbol']} | Lado: {side_enum.value.upper()} | Acciones: {sig['shares']}")
    print(f"   Entrada: ${sig['entry']:.2f} | Stop: ${sig['stop']:.2f} | Take Profit: ${sig['tp']:.2f}")

    try:
        req = MarketOrderRequest(
            symbol=sig["symbol"],
            qty=sig["shares"],
            side=side_enum,
            time_in_force=TimeInForce.DAY,
            order_class=OrderClass.BRACKET,
            take_profit=TakeProfitRequest(limit_price=sig["tp"]),
            stop_loss=StopLossRequest(stop_price=sig["stop"])
        )
        order = trading_client.submit_order(req)
        print(f"✅ Orden enviada a Alpaca con ID: {order.id}")
        return True
    except Exception as e:
        print(f"❌ Error al enviar orden a Alpaca: {e}")
        return False

def run_cycle():
    active_count = get_current_positions_count()
    available_slots = cfg.MAX_CONCURRENT_POSITIONS - active_count
    
    now_ny = dt.datetime.now(dt.timezone(dt.timedelta(hours=-4)))  # ET aproximado
    print(f"[{now_ny.strftime('%H:%M:%S')} ET] Escaneando {len(cfg.ACTIVE_UNIVERSE)} activos | Slots libres: {available_slots}/{cfg.MAX_CONCURRENT_POSITIONS}")

    if available_slots <= 0:
        print("⏸️ Cupo máximo de posiciones alcanzado (2). Esperando resolución...")
        return

    signals = []
    for sym in cfg.ACTIVE_UNIVERSE:
        df = fetch_asset_context(sym)
        if df is not None:
            sig = analyze_symbol(sym, df)
            if sig:
                signals.append(sig)

    if not signals:
        return

    # Signal Ranker: Ordenar por volumen relativo y despachar las mejores
    ranked = sorted(signals, key=lambda x: x["score"], reverse=True)
    to_fire = ranked[:available_slots]

    for sig in to_fire:
        execute_bracket_order(sig)

def main():
    print("=" * 80)
    print("⚡ OUROBOROS QUANT: DAEMON DE EJECUCIÓN ALPACA (VÍA A)")
    print(f"• Universo: {cfg.ACTIVE_UNIVERSE}")
    print(f"• Riesgo Fijo: ${cfg.RISK_PER_TRADE_USD}/trade | Concurrencia Máx: {cfg.MAX_CONCURRENT_POSITIONS}")
    print(f"• Modo de Cuenta: {'PAPER TRADING' if cfg.ALPACA_PAPER else 'REAL ACCOUNT (LIVE)'}")
    print("=" * 80)

    # Comprobar conexión y cuenta
    try:
        acc = trading_client.get_account()
        print(f"✅ Conectado a Alpaca. Balance: ${float(acc.equity):,.2f} | Buying Power: ${float(acc.buying_power):,.2f}")
    except Exception as e:
        print(f"❌ Error de autenticación con Alpaca: {e}")
        sys.exit(1)

    while True:
        try:
            run_cycle()
        except Exception as e:
            print(f"⚠️ Error en el ciclo de escaneo: {e}")
        time.sleep(60)  # Polling cada 60 segundos

if __name__ == "__main__":
    main()
