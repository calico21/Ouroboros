"""
Ouroboros Engine - Strategy Module
PDH Liquidity Sweep & Reversal Short Strategy (MNQ Futures)
Diseñado para CME Globex MNQ bajo restricciones de Apex 50k Trailing Floor.
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any
import pandas as pd
import numpy as np


@dataclass
class TradeSignal:
    timestamp: pd.Timestamp
    symbol: str
    direction: int  # -1: Short
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_points: float
    target_r: float
    metadata: Dict[str, Any]


class PDHLiquiditySweepShortStrategy:
    """
    Estrategia de Rechazo y Absorción en el Máximo Diario Previo (PDH Sweep Short).
    
    Reglas Institucionales:
    1. Identifica el Previous Day High (PDH) de la sesión regular/completa previa.
    2. Ventana de escaneo: 09:45 a 14:30 ET (evita los barridos ciegos de 09:30).
    3. Trigger: La barra de 5m supera el PDH por un margen tolerable (<= 15 pts),
       pero cierra por debajo del PDH Y por debajo del VWAP acumulado de la sesión.
    4. Stop Loss: Estructural sobre la mecha de la barra (High + 2 ticks),
       acotado estrictamente entre 10 y 22 puntos (preserva el colchón de Apex).
    5. Take Profit: Orden límite fija a 1.40R (sin breakeven prematuro).
    6. Salida forzada por tiempo: 15:55 ET (flat intradía obligatorio).
    """

    def __init__(
        self,
        symbol: str = "MNQ",
        target_r: float = 1.40,
        max_stop_pts: float = 22.0,
        min_stop_pts: float = 10.0,
        sweep_tolerance_pts: float = 15.0,
        scan_start_time: str = "09:45",
        scan_end_time: str = "14:30",
        hard_exit_time: str = "15:55",
        point_value: float = 2.0
    ):
        self.symbol = symbol
        self.target_r = target_r
        self.max_stop_pts = max_stop_pts
        self.min_stop_pts = min_stop_pts
        self.sweep_tolerance_pts = sweep_tolerance_pts
        self.point_value = point_value

        self.scan_start = pd.to_datetime(scan_start_time).time()
        self.scan_end = pd.to_datetime(scan_end_time).time()
        self.hard_exit = pd.to_datetime(hard_exit_time).time()

        # Variables de estado intradiario
        self.current_date = None
        self.pdh = np.nan
        self.session_cum_tp_vol = 0.0
        self.session_cum_vol = 0.0
        self.session_traded = False

        # Registro de sesiones previas para calcular PDH
        self.daily_highs = {}
        self.today_high = -np.inf

    def on_bar(self, bar: pd.Series) -> Optional[TradeSignal]:
        bar_time = bar.name if isinstance(bar.name, pd.Timestamp) else pd.to_datetime(bar["timestamp"])
        bar_date = bar_time.date()
        time_of_day = bar_time.time()

        # Cambio de sesión diaria
        if self.current_date != bar_date:
            if self.current_date is not None and self.today_high > -np.inf:
                self.daily_highs[self.current_date] = self.today_high

            self.current_date = bar_date
            self.session_cum_tp_vol = 0.0
            self.session_cum_vol = 0.0
            self.session_traded = False
            self.today_high = -np.inf

            # Obtener el PDH del día inmediatamente anterior registrado
            sorted_dates = sorted(self.daily_highs.keys())
            self.pdh = self.daily_highs[sorted_dates[-1]] if len(sorted_dates) > 0 else np.nan

        # Rastrear máximo de la sesión actual
        high = bar["high"]
        low = bar["low"]
        close = bar["close"]
        vol = bar.get("volume", 1.0)
        self.today_high = max(self.today_high, high)

        # Actualizar VWAP continuo de la sesión RTH
        tp = (high + low + close) / 3.0
        self.session_cum_tp_vol += tp * vol
        self.session_cum_vol += vol
        current_vwap = self.session_cum_tp_vol / max(1.0, self.session_cum_vol)

        # Condiciones de entrada
        if self.session_traded or np.isnan(self.pdh):
            return None

        if self.scan_start <= time_of_day <= self.scan_end:
            # Detección del barrido de PDH y rechazo bajista
            sweep_distance = high - self.pdh
            if 0 < sweep_distance <= self.sweep_tolerance_pts and close < self.pdh and close < current_vwap:
                entry_price = close - 0.25  # Asumiendo 1 tick de slippage adverso
                raw_stop_dist = (high + 0.50) - entry_price
                stop_dist = min(max(raw_stop_dist, self.min_stop_pts), self.max_stop_pts)

                stop_loss = entry_price + stop_dist
                take_profit = entry_price - (self.target_r * stop_dist)
                self.session_traded = True

                return TradeSignal(
                    timestamp=bar_time,
                    symbol=self.symbol,
                    direction=-1,
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    risk_points=stop_dist,
                    target_r=self.target_r,
                    metadata={
                        "pdh": self.pdh,
                        "sweep_pts": sweep_distance,
                        "vwap": current_vwap,
                        "raw_stop": raw_stop_dist
                    }
                )

        return None
