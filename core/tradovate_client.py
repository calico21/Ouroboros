import asyncio
import json
import time
import requests
import websockets

class TradovateClient:
    """Cliente directo a la API de Tradovate para simulación y cuentas de evaluación Apex."""
    def __init__(self, username, password, app_id="OuroborosQuant", app_version="1.0", is_demo=True):
        self.username = username
        self.password = password
        self.app_id = app_id
        self.app_version = app_version
        self.is_demo = is_demo
        
        # Endpoints oficiales
        if self.is_demo:
            self.base_url = "https://demo.tradovateapi.com/v1"
            self.ws_url = "wss://demo.tradovateapi.com/v1/websocket"
        else:
            self.base_url = "https://live.tradovateapi.com/v1"
            self.ws_url = "wss://live.tradovateapi.com/v1/websocket"
            
        self.token = None
        self.account_id = None
        self.account_name = None

    def authenticate(self):
        """Autenticación REST para obtener token de sesión."""
        url = f"{self.base_url}/auth/accesstokenrequest"
        payload = {
            "name": self.username,
            "password": self.password,
            "appId": self.app_id,
            "appVersion": self.app_version,
            "cid": 8,  # Apex CID
            "sec": ""
        }
        resp = requests.post(url, json=payload, timeout=10)
        data = resp.json()
        if "accessToken" not in data:
            raise ValueError(f"Fallo de autenticación en Tradovate: {data}")
            
        self.token = data["accessToken"]
        
        # Obtener cuenta asociada
        acc_resp = requests.get(
            f"{self.base_url}/account/list",
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=10
        )
        accounts = acc_resp.json()
        self.account_id = accounts[0]["id"]
        self.account_name = accounts[0]["name"]
        print(f"✅ Autenticado en Tradovate | Cuenta: {self.account_name} (ID: {self.account_id})")
        return self.token

    def get_account_cash_balance(self):
        """Consulta el balance neto y el colchón actual de la cuenta."""
        url = f"{self.base_url}/cashBalance/getcashbalancesnapshot?accountId={self.account_id}"
        resp = requests.get(url, headers={"Authorization": f"Bearer {self.token}"}, timeout=10)
        data = resp.json()
        total_cash = data.get("totalCashValue", 50000.0)
        realized_pnl = data.get("realizedPnL", 0.0)
        return total_cash, realized_pnl

    def place_bracket_order(self, symbol, action, quantity, entry_price, stop_loss_price, take_profit_price):
        """
        Envía una orden bracket OCO directamente al motor de Tradovate.
        El Stop y el Target residen en el servidor del bróker.
        """
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        
        # Estructura Bracket OCO
        order_payload = {
            "accountSpec": self.account_name,
            "accountId": self.account_id,
            "action": action,  # "Buy" o "Sell"
            "symbol": symbol,
            "orderType": "Limit",
            "price": entry_price,
            "isAutomated": True,
            "bracket1": {
                "action": "Sell" if action == "Buy" else "Buy",
                "orderType": "Stop",
                "stopPrice": stop_loss_price
            },
            "bracket2": {
                "action": "Sell" if action == "Buy" else "Buy",
                "orderType": "Limit",
                "price": take_profit_price
            }
        }
        
        url = f"{self.base_url}/order/placeorder"
        resp = requests.post(url, json=order_payload, headers=headers, timeout=10)
        return resp.json()
