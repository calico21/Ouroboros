import requests
from pathlib import Path
from live.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

class TelegramNotifier:
    def __init__(self):
        self.token = TELEGRAM_BOT_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.enabled = bool(self.token and self.chat_id)
        if not self.enabled:
            print("⚠️ [NOTIFIER] Credenciales de Telegram no detectadas. Avisos en consola.")

    def send_message(self, text: str):
        print(f"\n{text}\n")
        if not self.enabled:
            return
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
        try:
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            print(f"❌ Error enviando mensaje a Telegram: {e}")

    def send_chart(self, image_path: Path, caption: str = ""):
        if not self.enabled or not image_path.exists():
            return
        url = f"https://api.telegram.org/bot{self.token}/sendPhoto"
        try:
            with open(image_path, "rb") as img:
                files = {"photo": img}
                data = {"chat_id": self.chat_id, "caption": caption, "parse_mode": "HTML"}
                requests.post(url, data=data, files=files, timeout=20)
        except Exception as e:
            print(f"❌ Error subiendo gráfica a Telegram: {e}")

    def notify_startup(self, balance, floor, cushion):
        msg = (
            "🚀 <b>OUROBOROS QUANT: NODO EN LA NUBE INICIADO</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 <b>Balance Inicial:</b> <code>${balance:,.2f}</code>\n"
            f"🛡️ <b>Suelo Liquidación:</b> <code>${floor:,.2f}</code>\n"
            f"🟢 <b>Colchón Apex:</b> <code>${cushion:,.2f}</code>\n"
            "🕒 <b>Cesta Activa:</b> MNQ, MGC, SIL, ZB\n"
            "📡 <b>Modo:</b> Autónomo 24/7 con reportes gráficos diarios"
        )
        self.send_message(msg)

    def notify_trade_opened(self, trade):
        side_icon = "🟢 BUY" if trade["side"] == "BUY" else "🔴 SELL"
        msg = (
            f"⚡ <b>DISPARO DE SUBASSTA: {trade['sym']}</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Operación:</b> {side_icon} | {trade['ctos']} cto(s)\n"
            f"<b>Precio Entrada:</b> <code>{trade['entry']:.4f}</code>\n"
            f"<b>Stop-Loss:</b> <code>{trade['stop']:.4f}</code>\n"
            f"<b>Take-Profit:</b> <code>{trade['target']:.4f}</code>\n"
            f"<b>Riesgo USD:</b> <code>${trade['risk_usd']:.2f}</code>\n"
            f"<b>Patrón:</b> {trade['trigger']} ({trade['time']} ET)"
        )
        self.send_message(msg)

    def notify_trade_closed(self, result):
        icon = "✅ TAKE-PROFIT" if result["is_win"] else "❌ STOP-LOSS"
        frozen_str = " (CONGELADO)" if result["frozen"] else " (Móvil)"
        msg = (
            f"{icon} <b>CIERRE DE POSICIÓN: {result['sym']}</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>PnL Neto:</b> <code>${result['net_pnl']:+,.2f}</code>\n"
            f"<b>Salida:</b> <code>{result['exit']:.4f}</code> ({result['reason']})\n"
            f"<b>Nuevo Balance:</b> <code>${result['balance']:,.2f}</code>\n"
            f"<b>Colchón Vivo:</b> <code>${result['cushion']:,.2f}</code>\n"
            f"<b>Suelo Apex:</b> <code>${result['floor']:,.2f}</code>{frozen_str}"
        )
        self.send_message(msg)

    def notify_daily_summary(self, summary, chart_path: Path):
        pnl_icon = "🟢" if summary["daily_pnl"] >= 0 else "🔴"
        caption = (
            f"📊 <b>REPORTE EJECUTIVO DIARIO ({summary['date']})</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Trades Hoy:</b> {summary['trades_today']} ({summary['wins']}W / {summary['losses']}L)\n"
            f"<b>PnL del Día:</b> {pnl_icon} <code>${summary['daily_pnl']:+,.2f}</code>\n"
            f"💼 <b>Balance Total:</b> <code>${summary['balance']:,.2f}</code>\n"
            f"🛡️ <b>Colchón Vivo:</b> <code>${summary['cushion']:,.2f}</code>\n"
            f"🏆 <b>Win Rate Global:</b> {summary['wr']:.1f}% ({summary['total_trades']} trades)"
        )
        self.send_chart(chart_path, caption=caption)
