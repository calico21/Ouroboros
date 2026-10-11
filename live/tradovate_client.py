import os
import aiohttp
import asyncio
from typing import List, Dict, Any, Optional

class TradovateClient:
    def __init__(self, is_demo: bool = True):
        self.base_url = "https://demo.tradovateapi.com/v1" if is_demo else "https://live.tradovateapi.com/v1"
        self.username = os.getenv("TRADOVATE_USER")
        self.password = os.getenv("TRADOVATE_PASSWORD")
        self.app_id = os.getenv("TRADOVATE_APP_ID", "Ouroboros")
        self.app_version = os.getenv("TRADOVATE_APP_VERSION", "1.0")
        self.cid = os.getenv("TRADOVATE_CID", "")
        self.sec = os.getenv("TRADOVATE_SEC", "")
        self.access_token: Optional[str] = None
        self.account_ids: List[int] = []

    async def authenticate(self) -> str:
        url = f"{self.base_url}/auth/accesstokenrequest"
        payload = {
            "name": self.username,
            "password": self.password,
            "appId": self.app_id,
            "appVersion": self.app_version,
            "cid": int(self.cid) if self.cid.isdigit() else None,
            "sec": self.sec if self.sec else None
        }
        # Limpieza de valores nulos
        payload = {k: v for k, v in payload.items() if v is not None}

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                data = await resp.json()
                if "accessToken" in data:
                    self.access_token = data["accessToken"]
                    print(f"[Tradovate] Autenticación exitosa. Expiración: {data.get('expirationTime')}")
                    return self.access_token
                raise ConnectionError(f"[Tradovate Auth Error] {data}")

    async def fetch_accounts(self) -> List[Dict[str, Any]]:
        headers = {"Authorization": f"Bearer {self.access_token}"}
        url = f"{self.base_url}/account/list"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                accounts = await resp.json()
                self.account_ids = [acc["id"] for acc in accounts]
                print(f"[Tradovate] Cuentas detectadas ({len(self.account_ids)}): {[acc['name'] for acc in accounts]}")
                return accounts

    async def place_bracket_order(
        self,
        account_id: int,
        symbol: str,
        action: str,  # 'Buy' o 'Sell'
        qty: int,
        sl_points: float = 20.0,
        tp_points: float = 48.0
    ) -> Dict[str, Any]:
        """
        Envía una orden Market con Stop Loss y Take Profit nativos en el servidor de Tradovate/CME.
        """
        headers = {"Authorization": f"Bearer {self.access_token}"}
        url = f"{self.base_url}/order/placebracketorder"

        payload = {
            "accountId": account_id,
            "accountSpec": self.username,
            "symbol": symbol,
            "action": action,
            "orderStrategyTypeId": 2,  # Bracket Strategy
            "orderQty": qty,
            "orderType": "Market",
            "params": {
                "stopLoss": {
                    "units": "Points",
                    "value": float(sl_points)
                },
                "takeProfit": {
                    "units": "Points",
                    "value": float(tp_points)
                }
            }
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                res = await resp.json()
                return res

    async def broadcast_order(
        self,
        symbol: str,
        action: str,
        qty: int,
        sl_points: float,
        tp_points: float
    ) -> List[Dict[str, Any]]:
        """
        Trade Copier concurrente: Dispara la orden simultáneamente a todas las cuentas vinculadas.
        """
        tasks = [
            self.place_bracket_order(
                account_id=acc_id,
                symbol=symbol,
                action=action,
                qty=qty,
                sl_points=sl_points,
                tp_points=tp_points
            )
            for acc_id in self.account_ids
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results
