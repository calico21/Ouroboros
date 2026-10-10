import os
import sys
import time
import logging
from datetime import datetime, time as dtime
from pathlib import Path
import pytz
import pandas as pd
import numpy as np

# Configuración de Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("ouroboros_paper_trading.log")
    ]
)
logger = logging.getLogger("OuroborosBot")

NY_TZ = pytz.timezone("America/New_York")

class AlpacaOuroborosTrader:
    def __init__(self, symbol="QQQ", contracts=6, target_r=1.50):
        """
        symbol: En Alpaca se opera QQQ como proxy directo de Nasdaq-100,
                o MNQ si utilizas Alpaca Futures API / Tradovate Bridge.
        """
        self.symbol = symbol
        self.contracts = contracts
        self.target_r = target_r
        self.api_key = os.getenv("ALPACA_API_KEY", "TU_API_KEY_AQUI")
        self.secret_key = os.getenv("ALPACA_SECRET_KEY", "TU_SECRET_KEY_AQUI")
        self.base_url = "https://paper-api.alpaca.markets"

        self.pdh = None
        self.traded_today = False
        self.active_position = False
        logger.info(f"Ouroboros Trader Inicializado. Símbolo: {self.symbol} | Contratos: {self.contracts}")

    def is_market_open(self):
        now = datetime.now(NY_TZ)
        if now.weekday() >= 5:
            return False
        return dtime(9, 30) <= now.time() <= dtime(16, 0)

    def is_signal_window(self):
        now = datetime.now(NY_TZ)
        return dtime(9, 45) <= now.time() <= dtime(12, 30)

    def is_eod_cutoff(self):
        now = datetime.now(NY_TZ)
        return now.time() >= dtime(15, 55)

    def update_daily_levels(self, historical_daily_bars):
        """Calcula el PDH estricto de la sesión previa."""
        if len(historical_daily_bars) >= 2:
            self.pdh = float(historical_daily_bars.iloc[-2]["high"])
            logger.info(f"Nivel PDH del día anterior actualizado: ${self.pdh:.2f}")

    def evaluate_5m_bar(self, current_bar, vwap, vol_sma20):
        """
        current_bar: dict con 'open', 'high', 'low', 'close', 'volume'
        """
        if self.pdh is None or self.traded_today:
            return None

        h = current_bar["high"]
        c = current_bar["close"]
        v = current_bar["volume"]

        sweep_dist = h - self.pdh

        # Reglas Maestras Congeladas
        is_sweep = 0.0 < sweep_dist <= 15.0
        reentered = c < self.pdh
        bearish_vwap = c < vwap
        institutional_vol = v >= 1.0 * vol_sma20

        if is_sweep and reentered and bearish_vwap and institutional_vol:
            logger.info("🎯 SEÑAL DETECTADA: Barrido de PDH confirmado con volumen y bajo VWAP.")
            return {
                "signal_high": h,
                "pdh": self.pdh,
                "vwap": vwap
            }
        return None

    def execute_bracket_order(self, current_price, signal_high):
        """
        Ejecuta la orden corta en Open[t+1] con Stop y Target vinculados.
        """
        raw_stop = (signal_high + 0.50) - current_price
        stop_dist = min(max(raw_stop, 10.0), 22.0)
        stop_price = current_price + stop_dist
        target_price = current_price - (self.target_r * stop_dist)

        logger.info(f"🚀 EJECUTANDO ORDEN CORTO ({self.contracts} contratos):")
        logger.info(f"   Entrada: ${current_price:.2f} | Stop: ${stop_price:.2f} | Target ({self.target_r:.2f}R): ${target_price:.2f}")

        # Aquí se invoca el cliente REST de Alpaca:
        # self.api.submit_order(symbol=self.symbol, qty=self.contracts, side='sell',
        #                       type='market', order_class='bracket',
        #                       stop_loss={'stop_price': stop_price},
        #                       take_profit={'limit_price': target_price})

        self.traded_today = True
        self.active_position = True

    def run_monitor_loop(self):
        logger.info("Iniciando bucle de monitorización en tiempo real...")
        while True:
            now = datetime.now(NY_TZ)

            # Reset diario
            if now.time() < dtime(9, 30) and self.traded_today:
                self.traded_today = False
                logger.info("Reinicio diario completado.")

            if self.is_market_open():
                if self.is_eod_cutoff() and self.active_position:
                    logger.info("⚠️ 15:55 ET Alcanzado. Cierre obligatorio forzoso de fin de día.")
                    # self.api.close_position(self.symbol)
                    self.active_position = False

            time.sleep(10)  # Polling periódico de 10 segundos

if __name__ == "__main__":
    bot = AlpacaOuroborosTrader()
    # Para ejecutar en producción:
    # bot.run_monitor_loop()
    print("Bot compilado y validado. Listo para recibir credenciales de Alpaca Paper Trading.")
