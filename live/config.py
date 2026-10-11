import os
from pathlib import Path

# --- Carga Dinámica de Variables de Entorno ---
for env_path in [
    Path(".env"),
    Path("live/.env"),
    Path(__file__).resolve().parent / ".env",
    Path.home() / ".env"
]:
    if env_path.exists():
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        except Exception:
            pass

# --- Credenciales Telegram ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# --- Credenciales Alpaca ---
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY") or os.getenv("ALPACA_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY") or os.getenv("ALPACA_SECRET", "")
ALPACA_PAPER = os.getenv("ALPACA_PAPER", "true").lower() in ("true", "1", "yes")

# --- Reglas Apex Trader Funding 50k ---
APEX_RULES = {
    "starting_balance": 50000.0,
    "initial_floor": 48000.0,
    "profit_target": 53000.0,
    "lock_hwm": 52600.0,
    "lock_floor": 50100.0,
    "buffer": 2500.0,
    "cme_commission_rt": 1.24
}

# --- Configuración Champion Strategy v3.0 (MNQ_3TRADE / DP_V1_ADAPTIVE) ---
STRATEGY_NAME = "apex_sprint_champion"
STRATEGY_MODEL = "DP_V1_ADAPTIVE"

PRIMARY_ASSET = os.getenv("PRIMARY_ASSET", "QQQ")
REFERENCE_ASSET = os.getenv("REFERENCE_ASSET", "SPY")

# Risk & Return Anchor (Equivalente a 20.0 pts MNQ / $40 riesgo y 48.0 pts MNQ / $96 target por unidad)
STOP_LOSS_MNQ_PTS = 20.0
TAKE_PROFIT_MNQ_PTS = 48.0
RISK_PER_BASE_UNIT_USD = 40.0
TARGET_PER_BASE_UNIT_USD = 96.0
REWARD_RISK_RATIO = 2.40

# Secuenciación MNQ_3TRADE
MAX_TRADES_PER_DAY = 3
HARD_HALT_ON_LOSS = True

# Horarios de Subasta y Sesión (America/New_York)
TIMEZONE = "America/New_York"
WINDOW_START = "09:30"             # Apertura regular de mercado (RTH Open)
WINDOW_END = "12:30"               # Cierre de la ventana principal de subasta matinal
FORCE_CLOSE_TIME = "15:55"         # Cierre intradía forzoso (sin riesgo overnight)
DAILY_REPORT_TIME = "16:15"        # Generación y despacho del tearsheet gráfico diario

# Filtro Cuantitativo de Microestructura
VOL_SMA_PERIOD = 20
MIN_VOL_RATIO = 0.95               # Volumen actual >= 95% de la media móvil

# --- Cesta de Activos Soportados ---
ASSETS = {
    "MNQ": {
        "ticker": "MNQ=F",
        "reference_ticker": "MES=F",
        "pt_val": 2.0,
        "tick": 0.25,
        "sl_pts": 20.0,
        "tp_pts": 48.0,
        "start": "09:30",
        "end": "12:30",
        "base_units": 7,
        "max_units": 10,
        "commission_rt": 1.24,
    },
    "QQQ": {
        "ticker": "QQQ",
        "reference_ticker": "SPY",
        "pt_val": 1.0,
        "tick": 0.01,
        "sl_pts": 0.50,            # 0.50 pt QQQ equivale a 20.0 pts MNQ
        "tp_pts": 1.20,            # 1.20 pt QQQ equivale a 48.0 pts MNQ (R:R 1:2.40)
        "shares_per_unit": 80,     # 80 acciones * $0.50 = $40 riesgo base; 80 * $1.20 = $96 target
        "start": "09:30",
        "end": "12:30",
        "base_units": 7,
        "max_units": 10,
        "commission_rt": 0.0,
    }
}
