import os
import aiohttp
import asyncio
from dotenv import load_dotenv

load_dotenv()

class TelegramNotifier:
    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.base_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    async def send_message(self, text: str):
        if not self.token or not self.chat_id:
            print("[Telegram] Token o Chat ID no configurados.")
            return

        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.base_url, json=payload, timeout=10) as resp:
                    if resp.status != 200:
                        err = await resp.text()
                        print(f"[Telegram Error {resp.status}] {err}")
        except Exception as e:
            print(f"[Telegram Exception] {e}")

    def notify_sync(self, text: str):
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self.send_message(text))
            else:
                loop.run_until_complete(self.send_message(text))
        except Exception:
            asyncio.run(self.send_message(text))
