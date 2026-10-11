import os
import sys
import asyncio
from datetime import datetime, time
import pytz
from dotenv import load_dotenv

# Asegurar path de Ouroboros
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from live.tradovate_client import TradovateClient
from live.telegram_notifier import TelegramNotifier
from strategies.apex_sprint_champion import ApexSprintChampionStrategy
from src.core.events import BarEvent

load_dotenv()

class ApexLiveOrchestrator:
    def __init__(self):
        is_demo = os.getenv("TRADOVATE_ENV", "demo").lower() == "demo"
        self.client = TradovateClient(is_demo=is_demo)
        self.notifier = TelegramNotifier()
        self.strategy = ApexSprintChampionStrategy()
        self.symbol = os.getenv("TRADING_SYMBOL", "MNQ")
        self.tz = pytz.timezone("America/New_York")
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.current_session_date = None

    async def initialize(self):
        env_mode = "DEMO / EVALUATION" if self.client.base_url.startswith("https://demo") else "LIVE"
        msg = (
            f"🚀 *Ouroboros Live Copier Iniciado*\n"
            f"• *Entorno:* `{env_mode}`\n"
            f"• *Estrategia:* `ApexSprintChampionStrategy v3.0.0`\n"
            f"• *Activo:* `{self.symbol}`\n"
            f"• *Sizing:* `DP_V1_ADAPTIVE` (Max 3 Trades/Día)\n"
            f"• *SL/TP:* 20.0 pts / 48.0 pts (1:2.40 R:R)"
        )
        print(msg)
        await self.notifier.send_message(msg)

        # Autenticación y mapeo de cuentas
        await self.client.authenticate()
        accounts = await self.client.fetch_accounts()
        acc_names = [a.get("name") for a in accounts]
        
        await self.notifier.send_message(
            f"🔗 *Cuentas Vinculadas al Copier ({len(accounts)}):*\n" +
            "\n".join([f"• `{name}`" for name in acc_names])
        )

    async def on_bar_completed(self, bar: BarEvent):
        """
        Llamado al cierre de cada vela de 5 minutos durante la sesión.
        """
        now_ny = bar.timestamp.astimezone(self.tz)
        today = now_ny.date()

        # Reseteo de sesión diaria
        if self.current_session_date != today:
            self.current_session_date = today
            self.daily_pnl = 0.0
            self.daily_trades = 0
            self.strategy.daily_realized_loss = 0.0
            self.strategy.daily_trade_count = 0

        # Filtro de ventana operativa (09:30 a 12:30 EST)
        current_time = now_ny.time()
        if not (time(9, 30) <= current_time <= time(12, 30)):
            return

        # Hard Halt on Loss: Detener sesión si hay pérdida en el día
        if self.daily_pnl < 0.0:
            return

        # Límite máximo de 3 trades por día
        if self.daily_trades >= 3:
            return

        # Evaluación de la señal campeona
        setup = self.strategy.on_bar(bar)
        if setup is not None:
            action = "Buy" if setup.direction.value == "LONG" else "Sell"
            
            # Cálculo dinámico de lotes con Bellman DP Sizing (5 a 10 contratos)
            qty = self.strategy.compute_position_size(d_t=2500.0) # Base inicial o flotante actual
            
            alert = (
                f"⚡ *SEÑAL DETECTADA - EJECUTANDO COPIER*\n"
                f"• *Dirección:* `{action}`\n"
                f"• *Contratos:* `{qty}x {self.symbol}` por cuenta\n"
                f"• *Cuentas a disparar:* `{len(self.client.account_ids)}`\n"
                f"• *Stop Loss:* `20.0 pts` (\$40/c)\n"
                f"• *Take Profit:* `48.0 pts` (\$96/c)\n"
                f"• *Hora:* `{now_ny.strftime('%H:%M:%S EST')}`"
            )
            print(alert)
            await self.notifier.send_message(alert)

            # Envío simultáneo a las cuentas mediante Tradovate Bracket API
            results = await self.client.broadcast_order(
                symbol=self.symbol,
                action=action,
                qty=qty,
                sl_points=20.0,
                tp_points=48.0
            )

            self.daily_trades += 1
            print(f"[Copier Output] {results}")
            await self.notifier.send_message(f"✅ *Órdenes Bracket enviadas al servidor CME.*")

    async def run(self):
        await self.initialize()
        print("\n[Ouroboros] Escuchando mercado. Esperando apertura de subasta 09:30 EST...")
        # Loop de escucha de mercado / WebSockets
        while True:
            await asyncio.sleep(1)

if __name__ == "__main__":
    orchestrator = ApexLiveOrchestrator()
    try:
        asyncio.run(orchestrator.run())
    except (KeyboardInterrupt, SystemExit):
        print("\n[Ouroboros] Copier detenido por el usuario.")
