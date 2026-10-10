import os
from pathlib import Path

# Credenciales Alpaca
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY") or os.getenv("ALPACA_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY") or os.getenv("ALPACA_SECRET", "")
ALPACA_PAPER = True  # Cambiar a False únicamente en cuenta real fondeada

# Universo Validado Anti-Overfitting (4 Años Auditados)
ACTIVE_UNIVERSE = ["BK", "TFX", "MRNA", "WAT", "HUM", "CNC"]

# Gestión de Riesgo y Cartera
RISK_PER_TRADE_USD = 100.0        # Riesgo monetario estricto por operación
MAX_CONCURRENT_POSITIONS = 2       # Máximo de posiciones abiertas simultáneas
MAX_SHARE_CAP = 500                # Techo máximo de acciones por ticket (liquidez)
MIN_RISK_PER_SHARE = 0.05          # Stop mínimo para evitar sobreapalancamiento en bajo rango
TP_R_MULTIPLE = 1.75               # Asimetría matemática: Take Profit a +1.75R
STOP_BUFFER_USD = 0.02             # Buffer de stop más allá del extremo barrido

# Horarios de Subasta (America/New_York)
TIMEZONE = "America/New_York"
WINDOW_START = "09:35"             # Esperar 5m tras el Open para asentar el spread
WINDOW_END = "11:30"               # Fin de la ventana de liquidez matinal
FORCE_CLOSE_TIME = "15:55"         # Cierre intradía forzoso (sin riesgo overnight)

# Filtro Cuantitativo de Volumen
VOL_SMA_PERIOD = 20
MIN_VOL_RATIO = 0.95               # Volumen actual >= 95% de la media móvil
