import sys
import os
import zipfile
import io
from pathlib import Path
from datetime import datetime, timedelta
import requests
import pandas as pd
import yfinance as yf

RAW_DIR = Path("data/raw_hf")
PROCESSED_DIR = Path("data/processed_hf")
RAW_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# =============================================================================
# 1. DESCARGA CME EN M1 (VENTANAS DE 6 DÍAS CONCATENADAS)
# =============================================================================
FUTURES_TICKERS = {
    "mnq_m1": "NQ=F",
    "mes_m1": "ES=F",
    "mgc_m1": "GC=F",   # Micro Oro
    "mcl_m1": "CL=F",   # Micro Crudo
}

def download_cme_m1():
    print("=" * 95)
    print(" [1/2] DESCARGANDO FUTUROS CME EN VELAS DE 1 MINUTO (VENTANAS DE 6 DÍAS)")
    print("=" * 95)

    now = datetime.now()

    for name, ticker_sym in FUTURES_TICKERS.items():
        out_file = PROCESSED_DIR / f"{name}.parquet"
        print(f"\n▶ Procesando {name.upper()} ({ticker_sym})...")
        chunks = []
        ticker = yf.Ticker(ticker_sym)

        # Yahoo permite hasta 30 días de M1 en peticiones de máximo 7 días
        for offset in range(0, 28, 6):
            end_dt = now - timedelta(days=offset)
            start_dt = now - timedelta(days=offset + 6)
            s_str = start_dt.strftime("%Y-%m-%d")
            e_str = end_dt.strftime("%Y-%m-%d")

            try:
                c = ticker.history(start=s_str, end=e_str, interval="1m")
                if not c.empty:
                    chunks.append(c)
                    print(f"   ✓ Bloque {s_str} -> {e_str}: {len(c):,} barras M1")
            except Exception as e:
                print(f"   ⚠️ Fallo bloque {s_str} -> {e_str}: {e}")

        if chunks:
            df_full = pd.concat(chunks).sort_index()
            # Eliminar duplicados en los cortes de ventana
            df_full = df_full[~df_full.index.duplicated(keep="first")]
            df_full.reset_index(inplace=True)

            col_map = {c: c.lower() for c in df_full.columns}
            df_full.rename(columns=col_map, inplace=True)

            date_col = "datetime" if "datetime" in df_full.columns else "date"
            df_full["timestamp"] = pd.to_datetime(df_full[date_col])
            df_full.set_index("timestamp", inplace=True)

            if df_full.index.tz is None:
                df_full.index = df_full.index.tz_localize("America/New_York")
            else:
                df_full.index = df_full.index.tz_convert("America/New_York")

            df_clean = df_full[["open", "high", "low", "close", "volume"]].copy()
            df_clean = df_clean.astype(float)
            df_clean.to_parquet(out_file)
            print(f"  ✅ Guardado {name.upper()}: {len(df_clean):,} barras M1 en {out_file}")
        else:
            print(f"  ❌ No se pudieron obtener barras para {ticker_sym}.")

# =============================================================================
# 2. DESCARGA ROBUSTA BINANCE VISION ARCHIVES (LIMPIEZA DE CABECERAS)
# =============================================================================
CRYPTO_PAIRS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

def download_binance_vision_m1(months_back=3):
    print("\n" + "=" * 95)
    print(" [2/2] DESCARGANDO CRIPTO PERPETUALS M1 (BINANCE VISION CON FILTRADO DE CABECERAS)")
    print("=" * 95)

    base_url = "https://data.binance.vision/data/futures/um/monthly/klines"
    now = datetime.now()

    for symbol in CRYPTO_PAIRS:
        print(f"\n▶ Procesando {symbol} (Perpetuals M1)...")
        symbol_dfs = []

        for m_offset in range(1, months_back + 1):
            target_date = now - timedelta(days=m_offset * 30)
            year_str = target_date.strftime("%Y")
            month_str = target_date.strftime("%m")

            file_name = f"{symbol}-1m-{year_str}-{month_str}.zip"
            url = f"{base_url}/{symbol}/1m/{file_name}"

            print(f"   Descargando: {year_str}-{month_str}...")
            try:
                res = requests.get(url, timeout=45)
                if res.status_code == 200:
                    with zipfile.ZipFile(io.BytesIO(res.content)) as z:
                        csv_name = z.namelist()[0]
                        with z.open(csv_name) as f:
                            # Leer sin asumir estructura fija de cabeceras
                            raw_csv = pd.read_csv(f, header=None, low_memory=False)

                            # Filtrar la fila de texto si contiene nombres de columnas
                            raw_csv[0] = pd.to_numeric(raw_csv[0], errors="coerce")
                            clean_data = raw_csv.dropna(subset=[0]).copy()

                            # Seleccionar las 6 columnas OHLCV
                            clean_sub = clean_data.iloc[:, :6].copy()
                            clean_sub.columns = ["open_time", "open", "high", "low", "close", "volume"]

                            clean_sub["timestamp"] = pd.to_datetime(clean_sub["open_time"], unit="ms", utc=True)
                            clean_sub.set_index("timestamp", inplace=True)
                            clean_sub.drop(columns=["open_time"], inplace=True)

                            for c in ["open", "high", "low", "close", "volume"]:
                                clean_sub[c] = clean_sub[c].astype(float)

                            symbol_dfs.append(clean_sub)
                            print(f"     ✓ {year_str}-{month_str} procesado con éxito ({len(clean_sub):,} velas M1)")
                else:
                    print(f"     ⏩ Archivo no disponible en el servidor (HTTP {res.status_code})")
            except Exception as e:
                print(f"     ⚠️ Error en {file_name}: {e}")

        if symbol_dfs:
            full_crypto = pd.concat(symbol_dfs).sort_index()
            full_crypto = full_crypto[~full_crypto.index.duplicated(keep="first")]
            out_crypto = PROCESSED_DIR / f"{symbol.lower()}_1m_continuous.parquet"
            full_crypto.to_parquet(out_crypto)
            print(f"  🏁 {symbol} consolidado: {len(full_crypto):,} barras M1 guardadas en {out_crypto}")

if __name__ == "__main__":
    download_cme_m1()
    download_binance_vision_m1(months_back=3)
    print("\n" + "=" * 95)
    print(" PIPELINE DE DESCARGA COMPLETADO CON ÉXITO")
    print("=" * 95)
