import requests
from pathlib import Path
from typing import Dict, Any, Optional
from live.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, PRIMARY_ASSET, REFERENCE_ASSET, STRATEGY_MODEL


class TelegramNotifier:
    """
    Notificador institucional vía Telegram con soporte HTML y envío de tearsheets.
    """

    def __init__(self):
        self.token = TELEGRAM_BOT_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.enabled = bool(self.token and self.chat_id)
        if not self.enabled:
            print("⚠️ [NOTIFIER] Credenciales de Telegram no detectadas en .env. Avisos en consola.")

    def send_message(self, text: str) -> bool:
        print(f"\n{text}\n")
        if not self.enabled:
            return True
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        try:
            resp = requests.post(url, json=payload, timeout=10)
            return resp.status_code == 200
        except Exception as e:
            print(f"❌ Error enviando mensaje a Telegram: {e}")
            return False

    def send_chart(self, image_path: Path, caption: str = "") -> bool:
        if not self.enabled or not image_path.exists() or image_path.stat().st_size == 0:
            return False
        url = f"https://api.telegram.org/bot{self.token}/sendPhoto"
        try:
            with open(image_path, "rb") as img:
                files = {"photo": img}
                data = {"chat_id": self.chat_id, "caption": caption, "parse_mode": "HTML"}
                resp = requests.post(url, data=data, files=files, timeout=25)
                return resp.status_code == 200
        except Exception as e:
            print(f"❌ Error subiendo gráfica a Telegram: {e}")
            return False

    def notify_startup(self, balance: float, floor: float, cushion: float, mode: str = "Paper / Simulation"):
        msg = (
            "🚀 <b>OUROBOROS QUANT: APEX CHAMPION v3.0 INICIADO</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 <b>Balance Inicial:</b> <code>${balance:,.2f}</code>\n"
            f"🛡️ <b>Suelo Liquidación:</b> <code>${floor:,.2f}</code>\n"
            f"🟢 <b>Colchón Vivo (D_t):</b> <code>${cushion:,.2f}</code>\n"
            f"🎯 <b>Activo Principal:</b> <code>{PRIMARY_ASSET}</code> (Ref: <code>{REFERENCE_ASSET}</code>)\n"
            f"⚙️ <b>Modelo Sizing:</b> <code>{STRATEGY_MODEL}</code>\n"
            f"📡 <b>Modo:</b> {mode}\n"
            "🕒 <b>Ventana Subasta:</b> 09:30 – 12:30 EST (Max 3 Trades | Hard Halt on Loss)"
        )
        self.send_message(msg)

    def notify_trade_opened(self, trade: Dict[str, Any]):
        side_icon = "🟢 BUY (LONG)" if trade["side"] == "BUY" else "🔴 SELL (SHORT)"
        smt_tag = " [⚡ SMT CONFIRMADO]" if trade.get("is_smt") else ""
        msg = (
            f"⚡ <b>DISPARO DE SUBASTA: {trade['sym']}</b>{smt_tag}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Operación:</b> {side_icon}\n"
            f"<b>Contratos / Unidades:</b> <code>{trade['ctos']}</code>\n"
            f"<b>Precio Entrada:</b> <code>{trade['entry']:.2f}</code>\n"
            f"<b>Stop-Loss:</b> <code>{trade['stop']:.2f}</code> (-{trade['stop_dist']:.2f} pts)\n"
            f"<b>Take-Profit:</b> <code>{trade['target']:.2f}</code> (+{trade['target_dist']:.2f} pts)\n"
            f"<b>Riesgo Monetario:</b> <code>${trade['risk_usd']:,.2f}</code>\n"
            f"<b>Régimen:</b> <code>{trade.get('regime', 'BALANCED')}</code>\n"
            f"<b>Gatillo:</b> {trade['trigger']} ({trade['time']} EST)"
        )
        self.send_message(msg)

    def notify_trade_closed(self, result: Dict[str, Any]):
        icon = "✅ TAKE-PROFIT" if result["is_win"] else "❌ STOP-LOSS"
        frozen_str = " (CONGELADO)" if result["frozen"] else " (Trailing)"
        halt_warning = "\n🛑 <b>HARD HALT ACTIVADO:</b> Pérdida intradía detectada. Sesión terminada por hoy." if not result["is_win"] else ""
        msg = (
            f"{icon} <b>CIERRE DE POSICIÓN: {result['sym']}</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>PnL Neto:</b> <code>${result['net_pnl']:+,.2f}</code>\n"
            f"<b>Precio Salida:</b> <code>{result['exit']:.2f}</code> ({result['reason']})\n"
            f"<b>Nuevo Balance:</b> <code>${result['balance']:,.2f}</code>\n"
            f"<b>Colchón Vivo (D_t):</b> <code>${result['cushion']:,.2f}</code>\n"
            f"<b>Suelo Apex:</b> <code>${result['floor']:,.2f}</code>{frozen_str}"
            f"{halt_warning}"
        )
        self.send_message(msg)

    def notify_daily_summary(self, summary: Dict[str, Any], chart_path: Optional[Path] = None):
        pnl_icon = "🟢" if summary["daily_pnl"] >= 0 else "🔴"
        caption = (
            f"📊 <b>REPORTE EJECUTIVO DIARIO ({summary['date']})</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Trades Hoy:</b> {summary['trades_today']} ({summary['wins']}W / {summary['losses']}L)\n"
            f"<b>PnL de la Sesión:</b> {pnl_icon} <code>${summary['daily_pnl']:+,.2f}</code>\n"
            f"💼 <b>Balance Total:</b> <code>${summary['balance']:,.2f}</code>\n"
            f"🛡️ <b>Colchón Vivo:</b> <code>${summary['cushion']:,.2f}</code>\n"
            f"🏆 <b>Win Rate Global:</b> {summary['wr']:.1f}% ({summary['total_trades']} ops)"
        )
        if chart_path and chart_path.exists():
            self.send_chart(chart_path, caption=caption)
        else:
            self.send_message(caption)
