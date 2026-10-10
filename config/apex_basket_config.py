from pathlib import Path

# Reglas Oficiales Apex Trader Funding (Cuenta \$50k)
ACCOUNT = {
    "starting_balance": 50000.0,
    "buffer": 2000.0,
    "initial_floor": 48000.0,
    "lock_hwm": 52600.0,        # Nivel que congela el trailing floor
    "lock_floor": 50100.0,      # Suelo permanente tras tocar \$52,600
    "profit_target": 53000.0,   # Meta: +\$3,000 netos
    "cme_commission_rt": 1.24,  # Comisión Globex por microcontrato round-trip
}

# Cesta Elite de Futuros CME Autorizados
ASSETS = {
    "MNQ": {
        "name": "Micro E-mini Nasdaq-100",
        "ticker": "NQ=F",
        "parquet_path": Path("data/processed/mnq_5m_continuous.parquet"),
        "point_value": 2.0,
        "tick_size": 0.25,
        "max_sweep": 16.0,
        "min_stop": 12.0,
        "max_stop": 22.0,
        "start_time": "09:40",
        "end_time": "11:30",
        "contracts_defense": 2,
        "contracts_normal": 3,
        "contracts_sprint": 4,
    },
    "MGC": {
        "name": "Micro Gold",
        "ticker": "GC=F",
        "parquet_path": Path("data/processed/mgc_5m_continuous.parquet"),
        "point_value": 10.0,
        "tick_size": 0.10,
        "max_sweep": 3.5,
        "min_stop": 1.8,
        "max_stop": 3.5,
        "start_time": "08:25",
        "end_time": "10:30",
        "contracts_defense": 2,
        "contracts_normal": 3,
        "contracts_sprint": 4,
    },
    "SIL": {
        "name": "Micro Silver",
        "ticker": "SI=F",
        "parquet_path": None,
        "point_value": 1000.0,
        "tick_size": 0.005,
        "max_sweep": 0.15,
        "min_stop": 0.04,
        "max_stop": 0.08,
        "start_time": "08:25",
        "end_time": "10:30",
        "contracts_defense": 1,
        "contracts_normal": 1,
        "contracts_sprint": 2,
    },
    "ZB": {
        "name": "30-Year Treasury Bond",
        "ticker": "ZB=F",
        "parquet_path": None,
        "point_value": 1000.0,
        "tick_size": 0.0312,
        "max_sweep": 0.35,
        "min_stop": 0.06,
        "max_stop": 0.12,
        "start_time": "08:20",
        "end_time": "10:00",
        "contracts_defense": 1,
        "contracts_normal": 1,
        "contracts_sprint": 1,
    }
}
