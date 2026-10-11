import os
import aiohttp
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

load_dotenv()

class AlpacaClient:
    def __init__(self):
        self.api_key = os.getenv("ALPACA_API_KEY", "")
        self.secret_key = os.getenv("ALPACA_SECRET_KEY", "")
        self.base_url = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
        self.data_url = os.getenv("ALPACA_DATA_URL", "https://data.alpaca.markets")
        self.headers = {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
            "Content-Type": "application/json"
        }

    async def get_account(self) -> Dict[str, Any]:
        url = f"{self.base_url}/v2/account"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers, timeout=10) as resp:
                if resp.status == 200:
                    return await resp.json()
                err = await resp.text()
                raise ConnectionError(f"[Alpaca Auth Error {resp.status}] {err}")

    async def get_bars(self, symbol: str, timeframe: str = "5Min", limit: int = 150) -> List[Dict[str, Any]]:
        """Descarga velas recientes usando el feed gratuito IEX."""
        url = f"{self.data_url}/v2/stocks/bars"
        params = {
            "symbols": symbol,
            "timeframe": timeframe,
            "limit": limit,
            "feed": "iex",
            "sort": "asc"
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers, params=params, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("bars", {}).get(symbol, [])
                err = await resp.text()
                print(f"[Alpaca Bars Error {resp.status}] {err}")
                return []

    async def get_open_positions(self) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/v2/positions"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers, timeout=10) as resp:
                if resp.status == 200:
                    return await resp.json()
                return []

    async def place_bracket_order(
        self,
        symbol: str,
        side: str,  # 'buy' o 'sell'
        qty: int,
        take_profit_price: float,
        stop_loss_price: float
    ) -> Dict[str, Any]:
        """Envía una orden Market Bracket con Stop Loss y Take Profit en el servidor."""
        url = f"{self.base_url}/v2/orders"
        payload = {
            "symbol": symbol,
            "qty": str(qty),
            "side": side.lower(),
            "type": "market",
            "time_in_force": "day",
            "order_class": "bracket",
            "take_profit": {
                "limit_price": str(round(take_profit_price, 2))
            },
            "stop_loss": {
                "stop_price": str(round(stop_loss_price, 2))
            }
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=self.headers, json=payload, timeout=10) as resp:
                res = await resp.json()
                if resp.status in (200, 201):
                    return res
                print(f"[Alpaca Order Error {resp.status}] {res}")
                return res

    async def close_all_positions(self) -> Dict[str, Any]:
        url = f"{self.base_url}/v2/positions"
        async with aiohttp.ClientSession() as session:
            async with session.delete(url, headers=self.headers, timeout=10) as resp:
                return await resp.json()
