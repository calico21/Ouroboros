"""
Production Webhook Notifier for AlphaForge.
Dispatches high-priority event alerts to Discord, Slack, Telegram, or generic webhooks.
"""
from typing import Optional, Dict, Any
import json
import urllib.request
import urllib.error
from datetime import datetime


class WebhookNotifier:
    """
    Lightweight, dependency-free webhook broadcaster for production trading alerts.
    """

    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url

    def send_alert(
        self,
        event_type: str,
        title: str,
        description: str,
        fields: Optional[Dict[str, Any]] = None,
        color_hex: str = "#00FFFF"
    ) -> bool:
        """
        Sends formatted alert. If no webhook URL is configured, logs locally and returns True.
        """
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        payload = {
            "content": f"**[ALPHAFORGE] {title}**",
            "embeds": [
                {
                    "title": title,
                    "description": description,
                    "color": int(color_hex.replace("#", ""), 16),
                    "timestamp": datetime.utcnow().isoformat(),
                    "footer": {"text": f"AlphaForge Execution Sentinel | {timestamp}"},
                    "fields": [
                        {"name": k, "value": str(v), "inline": True}
                        for k, v in (fields or {}).items()
                    ]
                }
            ]
        }

        if not self.webhook_url:
            # Local silent log
            return True

        try:
            req = urllib.request.Request(
                self.webhook_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json", "User-Agent": "AlphaForge/5.0"}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status in (200, 204)
        except Exception as e:
            # Non-blocking error handling
            print(f"[WebhookNotifier Error] Failed to post alert to webhook: {e}")
            return False

    def notify_order_filled(
        self,
        strategy: str,
        side: str,
        price: float,
        qty: int,
        sl: float,
        tp: float,
        slippage_ticks: float
    ) -> None:
        self.send_alert(
            event_type="ORDER_FILLED",
            title=f"ORDER FILLED: {side} {qty}ct MNQ",
            description=f"Strategy `{strategy}` filled on CME Globex.",
            fields={
                "Entry Price": f"{price:.2f}",
                "Stop Loss": f"{sl:.2f}",
                "Take Profit": f"{tp:.2f}",
                "Slippage": f"{slippage_ticks:+.2f} ticks",
            },
            color_hex="#00E676" if side == "LONG" else "#FF5252"
        )

    def notify_trade_closed(
        self,
        strategy: str,
        realized_pnl: float,
        balance: float,
        floor: float,
        reason: str
    ) -> None:
        color = "#00E676" if realized_pnl > 0 else "#FF5252"
        self.send_alert(
            event_type="TRADE_CLOSED",
            title=f"TRADE CLOSED: {reason}",
            description=f"Realized PnL: **${realized_pnl:+.2f}** | Account Balance: **${balance:,.2f}**",
            fields={
                "Strategy": strategy,
                "Realized PnL": f"${realized_pnl:+.2f}",
                "Account Balance": f"${balance:,.2f}",
                "Trailing Floor": f"${floor:,.2f}",
                "Distance to Breach": f"${balance - floor:,.2f}",
            },
            color_hex=color
        )

    def notify_circuit_breaker(self, reason: str, details: Dict[str, Any]) -> None:
        self.send_alert(
            event_type="CIRCUIT_BREAKER_TRIPPED",
            title="🚨 CRITICAL: CIRCUIT BREAKER ACTIVATED",
            description=f"Trading disarmed immediately. **{reason}**",
            fields=details,
            color_hex="#FF0000"
        )
