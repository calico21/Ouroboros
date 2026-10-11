import os
import sys
import asyncio
from datetime import datetime, time
import pytz
import pandas as pd
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from live.alpaca_client import AlpacaClient
from live.telegram_notifier import TelegramNotifier
from live.auction_engine import AuctionEngine

load_dotenv()

class AlpacaLivePaperTrader:
    def __init__(self):
        self.alpaca = AlpacaClient()
        self.notifier = TelegramNotifier()
        self.engine = AuctionEngine()

        self.primary = os.getenv("PRIMARY_SYMBOL", "QQQ")
        self.ref_sym = os.getenv("REFERENCE_SYMBOL", "SPY")
        self.qty = int(os.getenv("TRADE_QTY", "20"))
        self.max_trades = int(os.getenv("MAX_TRADES_PER_DAY", "3"))

        self.tz_ny = pytz.timezone("America/New_York")
        self.tz_local = pytz.timezone("Europe/Madrid")

        self.current_date = None
        self.daily_trades = 0
        self.daily_pnl = 0.0
        self.has_open_position = False

    async def initialize(self):
        acc = await self.alpaca.get_account()
        equity = float(acc.get("equity", 0.0))
        bp = float(acc.get("buying_power", 0.0))

        now_ny = datetime.now(self.tz_ny)
        now_madrid = datetime.now(self.tz_local)

        start_msg = (
            f"🦅 *Ouroboros Alpaca Paper Trader v3.0*\n"
            f"• *Capital Simulado:* `${equity:,.2f}`\n"
            f"• *Buying Power:* `${bp:,.2f}`\n"
            f"• *Activo:* `{self.primary}` (Ref SMT: `{self.ref_sym}`)\n"
            f"• *Tamaño Fijo:* `{self.qty} títulos`\n"
            f"• *Política:* `MNQ_3TRADE` (Max 3 trades | Hard Halt on Loss)\n"
            f"• *Hora NY:* `{now_ny.strftime('%H:%M:%S EST')}`\n"
            f"• *Hora España:* `{now_madrid.strftime('%H:%M:%S CET')}`"
        )
        print(start_msg)
        await self.notifier.send_message(start_msg)

        # Cargar perfiles de subasta
        await self.refresh_auction_levels()

    async def refresh_auction_levels(self):
        bars_q = await self.alpaca.get_bars(self.primary, timeframe="5Min", limit=200)
        bars_s = await self.alpaca.get_bars(self.ref_sym, timeframe="5Min", limit=200)
        levels = self.engine.compute_prior_day_profiles(bars_q, bars_s)

        if levels.get("prev_date"):
            msg = (
                f"📊 *Niveles de Subasta Cargados (Sesión: {levels['prev_date']})*\n"
                f"• *QQQ VAH / VAL:* `${levels['vah_qqq']:.2f}` / `${levels['val_qqq']:.2f}`\n"
                f"• *QQQ PDH / PDL:* `${levels['pdh_qqq']:.2f}` / `${levels['pdl_qqq']:.2f}`\n"
                f"• *SPY VAH / VAL:* `${levels['vah_spy']:.2f}` / `${levels['val_spy']:.2f}`"
            )
            print(msg)
            await self.notifier.send_message(msg)

    async def check_positions(self):
        positions = await self.alpaca.get_open_positions()
        qqq_pos = [p for p in positions if p.get("symbol") == self.primary]
        self.has_open_position = len(qqq_pos) > 0

    async def evaluate_market(self):
        now_ny = datetime.now(self.tz_ny)
        today = now_ny.date()

        # Reseteo diario
        if self.current_date != today:
            self.current_date = today
            self.daily_trades = 0
            self.daily_pnl = 0.0
            await self.refresh_auction_levels()

        cur_time = now_ny.time()

        # Hard Session Cutoff (15:55 EST): Cerrar todo antes del cierre de mercado
        if cur_time >= time(15, 55):
            if self.has_open_position:
                await self.alpaca.close_all_positions()
                self.has_open_position = False
                await self.notifier.send_message("🛑 *EOD Flatten: Todas las posiciones cerradas a las 15:55 EST.*")
            return

        # Ventana operativa institucional (09:30 a 12:30 EST)
        if not (time(9, 30) <= cur_time <= time(12, 30)):
            return

        # Hard Halt on Loss: Detener operativa del día si hay pérdida
        if self.daily_pnl < 0:
            return

        # Límite máximo de 3 trades diarios
        if self.daily_trades >= self.max_trades:
            return

        await self.check_positions()
        if self.has_open_position:
            return

        # Descarga de datos recientes
        bars_q = await self.alpaca.get_bars(self.primary, timeframe="5Min", limit=40)
        bars_s = await self.alpaca.get_bars(self.ref_sym, timeframe="5Min", limit=40)

        if not bars_q or not bars_s:
            return

        df_q = pd.DataFrame(bars_q)
        df_s = pd.DataFrame(bars_s)

        from live.state_manager import StateManager
        sm = StateManager()

        sig = self.engine.evaluate_signal(df_q, df_s)

        if sig is not None:
            side = "buy" if sig["side"] == "BUY" else "sell"
            units = sm.compute_position_size(is_smt_confirmed=sig["is_smt"])
            shares_per_unit = 80
            qty = units * shares_per_unit

            last_close = sig["entry"]
            sl_price = sig["stop"]
            tp_price = sig["target"]
            sl_dist = sig["sl_dist"]
            tp_dist = sig["tp_dist"]

            smt_label = "🔥 *CONFIRMADO CON DIVERGENCIA SMT (SPY)*" if sig["is_smt"] else "⚪ Estándar"

            alert = (
                f"⚡ *SEÑAL DE ENTRADA - EJECUTANDO EN ALPACA*\n"
                f"• *Activo:* `{self.primary}`\n"
                f"• *Setup:* `{sig['trigger']}` (Régimen: `{sig.get('regime', 'BALANCED')}`)\n"
                f"• *Dirección:* `{'COMPRA (LONG)' if side == 'buy' else 'VENTA EN CORTO (SHORT)'}`\n"
                f"• *SMT Status:* {smt_label}\n"
                f"• *Sizing DP_V1:* `{units} unidades ({qty} títulos)`\n"
                f"• *Precio Ref:* `${last_close:.2f}`\n"
                f"• *Stop Loss:* `${sl_price:.2f}` (-\${sl_dist:.2f})\n"
                f"• *Take Profit:* `${tp_price:.2f}` (+\${tp_dist:.2f})\n"
                f"• *R:R Asimétrico:* `1 : 2.40`"
            )
            print(alert)
            await self.notifier.send_message(alert)

            # Envío de Bracket Order al servidor de Alpaca
            order = await self.alpaca.place_bracket_order(
                symbol=self.primary,
                side=side,
                qty=qty,
                take_profit_price=tp_price,
                stop_loss_price=sl_price
            )

            if "id" in order:
                self.daily_trades += 1
                self.has_open_position = True
                conf_msg = f"✅ *Orden Bracket en Mercado:* ID `{order['id'][:8]}...`"
                print(conf_msg)
                await self.notifier.send_message(conf_msg)

    async def run(self):
        await self.initialize()
        print("\n[Ouroboros] Bot de Paper Trading activo. Escuchando mercado cada 60s...")
        while True:
            try:
                await self.evaluate_market()
            except Exception as e:
                print(f"[Loop Exception] {e}")
            await asyncio.sleep(60)

if __name__ == "__main__":
    trader = AlpacaLivePaperTrader()
    try:
        asyncio.run(trader.run())
    except (KeyboardInterrupt, SystemExit):
        print("\n[Ouroboros] Trader detenido.")
