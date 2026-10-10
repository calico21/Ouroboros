import sys
from pathlib import Path
import pandas as pd
import numpy as np

def standardize_and_merge():
    raw_dir = Path("data/raw")
    processed_dir = Path("data/processed")
    processed_dir.mkdir(parents=True, exist_ok=True)

    # 1. Buscar fuentes de datos extendidos (CSV o Parquet)
    possible_files = list(raw_dir.glob("nq*.*")) + list(raw_dir.glob("NQ*.*"))
    target_output = processed_dir / "nq_5m_extended.parquet"

    print("=" * 80)
    print("      OUROBOROS: INGESTA Y ESTANDARIZACIÓN NQ HISTÓRICO EXTENDIDO")
    print("=" * 80)

    if not possible_files:
        print(f"⚠️  No se encontró ningún archivo NQ en {raw_dir}/.")
        print("\nPara cargar datos históricos (2010-2021):")
        print("1. Coloca tu archivo (CSV de FirstRate Data, Databento, o export de NinjaTrader)")
        print("   en la carpeta: data/raw/nq_5m_2010_2026.csv")
        print("\nColumnas esperadas:")
        print("   DateTime (o Date, Time), Open, High, Low, Close, Volume")
        print("=" * 80)
        return

    raw_file = possible_files[0]
    print(f"Procesando archivo fuente: {raw_file}...")

    # Carga según formato
    if raw_file.suffix == ".csv":
        df = pd.read_csv(raw_file)
    else:
        df = pd.read_parquet(raw_file)

    # Normalizar nombres de columnas a minúsculas
    df.columns = [c.strip().lower() for c in df.columns]

    # Detección de columna temporal
    if "datetime" in df.columns:
        df["timestamp"] = pd.to_datetime(df["datetime"])
    elif "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    elif "date" in df.columns and "time" in df.columns:
        df["timestamp"] = pd.to_datetime(df["date"].astype(str) + " " + df["time"].astype(str))
    else:
        raise ValueError("No se reconoció columna de fecha/hora en el archivo.")

    df.set_index("timestamp", inplace=True)

    # Asignar zona horaria America/New_York (CME RTH estándar)
    if df.index.tz is None:
        df.index = df.index.tz_localize("America/New_York", ambiguous="NaT", nonexistent="shift_forward")
    else:
        df.index = df.index.tz_convert("America/New_York")

    # Limpiar columnas OHLCV
    req_cols = ["open", "high", "low", "close", "volume"]
    for col in req_cols:
        if col not in df.columns:
            raise KeyError(f"Columna faltante: {col}")
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df[req_cols].dropna().sort_index()

    # Guardar en parquet optimizado
    df.to_parquet(target_output, compression="snappy")
    print(f"✅ Archivo estandarizado guardado con éxito: {target_output}")
    print(f"   Total barras 5m: {len(df):,}")
    print(f"   Rango temporal : {df.index.min().date()}  -->  {df.index.max().date()}")
    print("=" * 80)

if __name__ == "__main__":
    standardize_and_merge()
