import time
import os
from datetime import datetime, date
from typing import Optional, Dict, Any
import pytz
import pandas as pd

from live.config import (
    ASSETS,
    APEX_RULES,
    PRIMARY_ASSET,
    REFERENCE_ASSET,
    STRATEGY_NAME,
    STRATEGY_MODEL,
    MAX_TRADES_PER_DAY,
    HARD_HALT_ON_LOSS,
    TIMEZONE,
    WINDOW_START,
    WINDOW_END,
    FORCE_CLOSE_TIME,
    DAILY_REPORT_TIME
)
from live.notifier import TelegramNotifier
from live.state_manager import StateManager
from live.engine import evaluate_signal, fetch_5m_data
from live.reporter import generate_daily_chart


class ApexChampionRunner:
    """
    Ejecutor Unificado en Tiempo Real para la Estrategia Campeona Apex Sprint v3.0:
      - Activo Principal: QQQ (o MNQ si CME está activo).
      - Activo Referencia: SPY (o MES para SMT).
      - Ventana de subasta matinal: 09:30 a 12:30 EST.
      - Secuenciación MNQ_3TRADE:
          * Máximo 3 trades por día.
          * Hard Halt inmediato al registrar la primera pérdida del día.
          * Permite operaciones 2 y 3 única y exclusivamente tras operaciones ganadoras.
      - Salida forzosa intradía a las 15:55 EST (cero riesgo overnight).
      - Generación y despacho de tearsheet de 4 paneles a las 16:15 EST.
    """

    def __init__(self, mode: str = "Paper / Simulation"):
        self.mode = mode
        self.tz = pytz.timezone(TIMEZONE)
        self.state_mgr = StateManager()
        self.notifier = TelegramNotifier()

        self.primary_sym = PRIMARY_ASSET
        self.ref_sym = REFERENCE_ASSET
        self.cfg = ASSETS.get(self.primary_sym, ASSETS["QQQ"])

        self.active_trade: Optional[Dict[str, Any]] = None
        self.trades_today: int = 0
        self.daily_loss_occurred: bool = False
        self.current_session_date: Optional[date] = None

    def get_eastern_time(self) -> datetime:
        return datetime.now(self.tz)

    def _sync_session_date(self, now_ny: datetime) -> None:
        today_date = now_ny.date()
        if self.current_session_date != today_date:
            if self.current_session_date is not None:
                # Decrementar horizonte de sesiones restantes
                rem = max(1, self.state_mgr.state.get("sessions_remaining", 21) - 1)
                self.state_mgr.state["sessions_remaining"] = rem
                self.state_mgr.save()

            self.current_session_date = today_date
            self.trades_today = 0
            self.daily_loss_occurred = False
            print(f"\n[SESIÓN NUEVA] Fecha EST: {today_date} | Sesiones restantes: {self.state_mgr.state.get('sessions_remaining', 21)}")

    def run_iteration(self) -> None:
        now_ny = self.get_eastern_time()
        time_str = now_ny.strftime("%H:%M")
        today_date = now_ny.date()
        today_str = str(today_date)

        self._sync_session_date(now_ny)

        # -------------------------------------------------------------
        # 1. GESTIÓN Y SEGUIMIENTO DE POSICIÓN ACTIVA
        # -------------------------------------------------------------
        if self.active_trade is not None:
            ticker = self.cfg.get("ticker", self.primary_sym)
            df = fetch_5m_data(ticker, period="2d")
            if df is not None and not df.empty:
                last_bar = df.iloc[-1]
                h_last = float(last_bar["high"])
                l_last = float(last_bar["low"])
                c_last = float(last_bar["close"])

                side = self.active_trade["side"]
                stop_lvl = self.active_trade["stop"]
                target_lvl = self.active_trade["target"]

                hit_stop = (h_last >= stop_lvl) if side == "SELL" else (l_last <= stop_lvl)
                hit_target = (l_last <= target_lvl) if side == "SELL" else (h_last >= target_lvl)
                is_timeout = time_str >= FORCE_CLOSE_TIME

                if hit_stop or hit_target or is_timeout:
                    if hit_target:
                        reason = "TAKE_PROFIT"
                        exit_price = target_lvl
                    elif hit_stop:
                        reason = "STOP_LOSS"
                        exit_price = stop_lvl
                    else:
                        reason = "EOD_TIMEOUT_FLATTEN"
                        exit_price = c_last

                    # Cálculo de PnL en puntos y neto en USD
                    if side == "SELL":
                        pts = self.active_trade["entry"] - exit_price
                    else:
                        pts = exit_price - self.active_trade["entry"]

                    pt_val = self.cfg.get("pt_val", 2.0)
                    units = self.active_trade.get("ctos", 1)
                    shares_per_unit = self.cfg.get("shares_per_unit", 1)
                    total_units = units * shares_per_unit

                    comm_rt = float(self.cfg.get("commission_rt", 1.24))
                    comm_total = comm_rt * units * 2.0  # ida y vuelta

                    gross_pnl = pts * pt_val * total_units
                    net_pnl = round(gross_pnl - comm_total, 2)

                    # MFE (Maximum Favorable Excursion) para ratcheting de HWM
                    if side == "SELL":
                        best_pts = max(0.0, self.active_trade["entry"] - l_last)
                    else:
                        best_pts = max(0.0, h_last - self.active_trade["entry"])
                    mfe_usd = best_pts * pt_val * total_units

                    result = self.state_mgr.update_on_trade_close(
                        self.primary_sym, net_pnl, mfe_usd, exit_price, reason, self.active_trade
                    )
                    self.notifier.notify_trade_closed(result)

                    # Secuenciación MNQ_3TRADE:
                    if net_pnl <= 0.0:
                        self.daily_loss_occurred = True
                        print(f"🛑 [HARD HALT] Pérdida intradía registrada (${net_pnl}). Se cancela operativa por hoy.")
                    else:
                        self.trades_today += 1
                        print(f"✅ [WIN] Operación ganadora ({self.trades_today}/{MAX_TRADES_PER_DAY}). Buscando siguiente setup si ventana sigue abierta.")

                    self.active_trade = None

        # -------------------------------------------------------------
        # 2. EVALUACIÓN DE SEÑALES EN VENTANA DE SUBASTA (09:30 - 12:30 EST)
        # -------------------------------------------------------------
        elif WINDOW_START <= time_str <= WINDOW_END:
            # Control estricto de pérdidas y conteo diario
            if HARD_HALT_ON_LOSS and self.daily_loss_occurred:
                pass  # Hard halt: No se admiten más operaciones tras una pérdida
            elif self.trades_today >= MAX_TRADES_PER_DAY:
                pass  # Límite de 3 operaciones diarias alcanzado
            else:
                sig = evaluate_signal(self.primary_sym, self.cfg, self.state_mgr)
                if sig is not None:
                    self.active_trade = sig
                    self.notifier.notify_trade_opened(sig)

        # -------------------------------------------------------------
        # 3. REPORTE EJECUTIVO Y TEARSHEET NOCTURNO (16:15 EST)
        # -------------------------------------------------------------
        if time_str >= DAILY_REPORT_TIME and self.state_mgr.state.get("last_summary_date") != today_str:
            chart_path = generate_daily_chart(self.state_mgr.state)
            summary = self.state_mgr.get_daily_metrics(today_str)
            self.notifier.notify_daily_summary(summary, chart_path)
            self.state_mgr.state["last_summary_date"] = today_str
            self.state_mgr.save()
            print(f"📊 [REPORTE ENVIADO] Tearsheet diario despachado para {today_str}.")

    def start(self, poll_interval_sec: int = 15) -> None:
        self.notifier.notify_startup(
            self.state_mgr.state["balance"],
            self.state_mgr.state["floor"],
            self.state_mgr.get_cushion(),
            mode=self.mode
        )
        print("🚀 [RUNNER] Daemon iniciado en modo continuo. Presione Ctrl+C para detener.")

        try:
            while True:
                self.run_iteration()
                time.sleep(poll_interval_sec)
        except KeyboardInterrupt:
            print("\n🛑 [RUNNER] Daemon detenido por el usuario.")


def main():
    runner = ApexChampionRunner()
    runner.start()


if __name__ == "__main__":
    main()
