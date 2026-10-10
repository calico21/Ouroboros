import os
import sys
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import DataFeed

load_dotenv()

api_key = os.getenv("ALPACA_API_KEY")
secret_key = os.getenv("ALPACA_SECRET_KEY")

if not api_key or not secret_key:
    print("❌ ERROR: Faltan las variables ALPACA_API_KEY o ALPACA_SECRET_KEY en .env")
    sys.exit(1)

OUTPUT_DIR = Path("data/processed")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TARGETS = [
    {
        "etf_symbol": "SPY",
        "output_file": OUTPUT_DIR / "mes_5m_continuous.parquet",
        "scale_factor": 10.0,
        "name": "MES (Micro S&P 500)"
    },
    {
        "etf_symbol": "IWM",
        "output_file": OUTPUT_DIR / "m2k_5m_continuous.parquet",
        "scale_factor": 10.0,
        "name": "M2K (Micro Russell 2000)"
    }
]

client = StockHistoricalDataClient(api_key=api_key, secret_key=secret_key)
current_year = datetime.now().year
years = range(2022, current_year + 1)

for target in TARGETS:
    etf = target["etf_symbol"]
    out_path = target["output_file"]
    scale = target["scale_factor"]
    name = target["name"]

    print("=" * 80)
    print(f">>> Descargando e ingiriendo {name} vía {etf} (Factor: {scale}x)...")
    print("=" * 80)

    all_bars = []
    for y in years:
        start_dt = datetime(y, 1, 1, tzinfo=timezone.utc)
        end_dt = datetime.now(timezone.utc) if y == current_year else datetime(y, 12, 31, 23, 59, tzinfo=timezone.utc)

        print(f"  -> Solicitando {etf} para {y} ({start_dt.strftime('%Y-%m-%d')} a {end_dt.strftime('%Y-%m-%d')})...")
        request_params = StockBarsRequest(
            symbol_or_symbols=etf,
            timeframe=TimeFrame.Minute,
            start=start_dt,
            end=end_dt,
            feed=DataFeed.IEX
        )

        try:
            bars = client.get_stock_bars(request_params)
            df_year = bars.df
            if not df_year.empty:
                if isinstance(df_year.index, pd.MultiIndex):
                    df_year = df_year.reset_index(level=0, drop=True)
                all_bars.append(df_year)
                print(f"     Recibidas {len(df_year):,} barras 1m.")
            else:
                print(f"     Sin datos para {y}.")
        except Exception as e:
            print(f"     Error descargando {y}: {e}")

    if not all_bars:
        print(f"❌ Error: No se obtuvieron datos para {etf}. Saltando...")
        continue

    df_raw = pd.concat(all_bars)
    df_raw.reset_index(inplace=True)

    # Procesamiento y resample a 5m
    print(f"  -> Normalizando timestamps y resampleando a 5m...")
    df_raw["timestamp"] = pd.to_datetime(df_raw["timestamp"])
    df_raw["timestamp"] = df_raw["timestamp"].dt.tz_convert("America/New_York")
    df_raw.sort_values("timestamp", inplace=True)
    df_raw.set_index("timestamp", inplace=True)

    resampled = df_raw.resample("5min").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum"
    }).dropna()

    # Escalar precios a puntos de índice
    resampled["open"] = (resampled["open"] * scale).round(2)
    resampled["high"] = (resampled["high"] * scale).round(2)
    resampled["low"] = (resampled["low"] * scale).round(2)
    resampled["close"] = (resampled["close"] * scale).round(2)
    resampled["volume"] = resampled["volume"].astype(int)

    resampled.to_parquet(out_path)
    print(f"✅ Guardado con éxito: {out_path} ({len(resampled):,} barras de 5m)")

print("\n" + "=" * 80)
print(">>> Descarga multiactivo finalizada con éxito.")
print("=" * 80)
