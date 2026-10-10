import os
from pathlib import Path

# Carga de variables de entorno desde live/.env si existe
ENV_FILE = Path(__file__).parent / ".env"
if ENV_FILE.exists():
    with open(ENV_FILE) as f:
        for line in f:
            if line.strip() and not line.startswith("#") and "=" in line:
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Reglas Oficiales Apex Trader Funding (50k)
APEX_RULES = {
    "starting_balance": 50000.0,
    "buffer": 2000.0,
    "initial_floor": 48000.0,
    "lock_hwm": 52600.0,
    "lock_floor": 50100.0,
    "profit_target": 53000.0,
    "cme_commission_rt": 1.24
}

# Cesta CME Cuádruple
ASSETS = {
    "MNQ": {
        "name": "Micro E-mini Nasdaq-100",
        "ticker": "NQ=F",
        "pt_val": 2.0,
        "tick": 0.25,
        "max_sw": 16.0,
        "min_stop": 12.0,
        "max_stop": 22.0,
        "start": "09:40",
        "end": "11:30",
        "base_ctos": 2,
        "sprint_ctos": 3
    },
    "MGC": {
        "name": "Micro Gold",
        "ticker": "GC=F",
        "pt_val": 10.0,
        "tick": 0.10,
        "max_sw": 3.5,
        "min_stop": 1.8,
        "max_stop": 3.5,
        "start": "08:25",
        "end": "10:30",
        "base_ctos": 2,
        "sprint_ctos": 3
    },
    "SIL": {
        "name": "Micro Silver",
        "ticker": "SI=F",
        "pt_val": 1000.0,
        "tick": 0.005,
        "max_sw": 0.15,
        "min_stop": 0.04,
        "max_stop": 0.08,
        "start": "08:25",
        "end": "10:30",
        "base_ctos": 1,
        "sprint_ctos": 1
    },
    "ZB": {
        "name": "30Y Treasury Bond",
        "ticker": "ZB=F",
        "pt_val": 1000.0,
        "tick": 0.0312,
        "max_sw": 0.35,
        "min_stop": 0.06,
        "max_stop": 0.12,
        "start": "08:20",
        "end": "10:00",
        "base_ctos": 1,
        "sprint_ctos": 1
    }
}
