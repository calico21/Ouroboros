# scripts/download_alpaca_data.py
import os
import sys
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed

from dotenv import load_dotenv

# Carga automáticamente las variables definidas en el .env de la raíz
load_dotenv()

# Ahora os.getenv() ya tiene acceso a las claves
api_key = os.getenv("ALPACA_API_KEY")
secret_key = os.getenv("ALPACA_SECRET_KEY")

OUTPUT_DIR = Path("data/processed")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
PARQUET_FILE = OUTPUT_DIR / "mnq_5m_continuous.parquet"

# Factor de conversión: 1 acción de QQQ ≈ 1/40 de 1 contrato NQ
SCALE_TO_NQ_POINTS = True
NQ_SCALE_FACTOR = 40.0

def fetch_alpaca_qqq():
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")
    
    if not api_key or not secret_key:
        print("❌ ERROR: Faltan las variables ALPACA_API_KEY o ALPACA_SECRET_KEY.")
        print("Configúralas con:")
        print("  export ALPACA_API_KEY='tu_key'")
        print("  export ALPACA_SECRET_KEY='tu_secret'")
        sys.exit(1)

    print(">>> [1/4] Inicializando cliente de Alpaca (Feed: IEX Gratuito)...")
    client = StockHistoricalDataClient(api_key=api_key, secret_key=secret_key)
    
    # Descargar por ventanas anuales para asegurar estabilidad
    current_year = datetime.now().year
    years = range(2022, current_year + 1)
    all_bars = []
    
    for y in years:
        start_dt = datetime(y, 1, 1, tzinfo=timezone.utc)
        # Si es el año actual, descargar hasta hoy; si no, hasta fin de año
        end_dt = datetime.now(timezone.utc) if y == current_year else datetime(y, 12, 31, 23, 59, tzinfo=timezone.utc)
        
        print(f">>> [2/4] Solicitando barras 1m de QQQ para {y} ({start_dt.strftime('%Y-%m-%d')} a {end_dt.strftime('%Y-%m-%d')})...")
        request_params = StockBarsRequest(
            symbol_or_symbols="QQQ",
            timeframe=TimeFrame.Minute,
            start=start_dt,
            end=end_dt,
            feed=DataFeed.IEX
        )
        
        bars = client.get_stock_bars(request_params)
        df_year = bars.df
        
        if not df_year.empty:
            # alpaca-py devuelve MultiIndex (symbol, timestamp)
            if isinstance(df_year.index, pd.MultiIndex):
                df_year = df_year.reset_index(level=0, drop=True)
            all_bars.append(df_year)
            print(f"    -> {len(df_year):,} barras recibidas para {y}.")
        else:
            print(f"    -> Sin datos para {y}.")

    if not all_bars:
        raise ValueError("No se recibieron datos de Alpaca.")

    df_raw = pd.concat(all_bars)
    df_raw.reset_index(inplace=True)
    df_raw.rename(columns={"timestamp": "timestamp"}, inplace=True)
    return df_raw

def process_and_save(df: pd.DataFrame):
    print(">>> [3/4] Ajustando zonas horarias y resampleando a 5 minutos...")
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Estandarizar a hora de Nueva York (America/New_York)
    df['timestamp'] = df['timestamp'].dt.tz_convert("America/New_York")
    df.sort_values("timestamp", inplace=True)
    df.set_index("timestamp", inplace=True)
    
    # Resample a 5m
    df_5m = df.resample("5min").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum"
    }).dropna()

    if SCALE_TO_NQ_POINTS:
        print(f">>> Escalando precios de QQQ x {NQ_SCALE_FACTOR:.1f} para alinear con puntos de NQ/MNQ...")
        for col in ["open", "high", "low", "close"]:
            df_5m[col] = (df_5m[col] * NQ_SCALE_FACTOR).round(2)

    df_5m.reset_index(inplace=True)
    
    print(f">>> [4/4] Guardando {len(df_5m):,} barras reales en {PARQUET_FILE}...")
    df_5m.to_parquet(PARQUET_FILE, index=False)
    print("✅ ¡Completado! El dataset histórico de mercado real está listo.")

if __name__ == "__main__":
    df = fetch_alpaca_qqq()
    process_and_save(df)