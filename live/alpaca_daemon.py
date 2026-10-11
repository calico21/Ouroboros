"""
Ouroboros Quant - Alpaca Live/Paper Execution Daemon
===================================================
Ejecuta la estrategia campeona Apex Sprint Champion v3.0 (QQQ / SPY)
mediante la API de Alpaca con gestión de riesgo institucional DP_V1_ADAPTIVE.
"""
import os
import sys
import time
from datetime import datetime, date
from pathlib import Path
from typing import Optional, Dict, Any
import pytz
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import live.config as cfg
from live.auction_engine import AuctionEngine
from live.state_manager import StateManager
from live.notifier import TelegramNotifier
from live.reporter import generate_daily_chart

try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import MarketOrderRequest, TakeProfitRequest, StopLossRequest
    from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    from alpaca.data.enums import DataFeed
    HAS_ALPACA_SDK = True
except (ImportError, ModuleNotFoundError):
    HAS_ALPACA_SDK = False


class AlpacaChampionDaemon:
    def __init__(self):
        self.tz = pytz.timezone(cfg.TIMEZONE)
        self.primary_sym = cfg.PRIMARY_ASSET
        self.ref_sym = cfg.REFERENCE_ASSET
        self.asset_cfg = cfg.ASSETS.get(self.primary_sym, cfg.ASSETS["QQQ"])

        self.state_mgr = StateManager()
        self.notifier = TelegramNotifier()
        self.engine = AuctionEngine(tz_str=cfg.TIMEZONE)

        self.trading_client = None
        self.data_client = None
        if HAS_ALPACA_SDK and cfg.ALPACA_API_KEY and cfg.ALPACA_SECRET_KEY:
            self.trading_client = TradingClient(cfg.ALPACA_API_KEY, cfg.ALPACA_SECRET_KEY, paper=cfg.ALPACA_PAPER)
            self.data_client = StockHistoricalDataClient(cfg.ALPACA_API_KEY, cfg.ALPACA_SECRET_KEY)

        self.trades_today = 0
        self.daily_loss_occurred = False
        self.current_session_date = None

    def fetch_bars(self, symbol: str) -> Optional[pd.DataFrame]:
        if self.data_client:
            try:
                now_utc = datetime.now(pytz.utc)
                start_utc = now_utc - pd.Timedelta(days=5)
                req = StockBarsRequest(
                    symbol_or_symbols=symbol,
                    timeframe=TimeFrame(5, TimeFrameUnit.Minute),
                    start=start_utc,
                    end=now_utc,
                    feed=DataFeed.IEX
                )
                bars = self.data_client.get_stock_bars(req)
                df = bars.df
                if df is not None and not df.empty:
                    if isinstance(df.index, pd.MultiIndex):
                        df = df.xs(symbol, level="symbol")
                    df = df.tz_convert(cfg.TIMEZONE)
                    df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"}, inplace=True)
                    return df.sort_index()
            except Exception as e:
                print(f"⚠️ Error Alpaca data client para {symbol}: {e}")

        # Fallback a yfinance
        try:
            import yfinance as yf
            t = yf.Ticker(symbol)
            df = t.history(period="5d", interval="5m")
            if not df.empty:
                if df.index.tz is None:
                    df.index = df.index.tz_localize(cfg.TIMEZONE, ambiguous="NaT")
                else:
                    df.index = df.index.tz_convert(cfg.TIMEZONE)
                return df
        except Exception:
            pass
        return None

    def get_open_positions_count(self) -> int:
        if self.trading_client:
            try:
                positions = self.trading_client.get_all_positions()
                return len(positions)
            except Exception:
                return 0
        return 0

    def execute_bracket_order(self, sig: Dict[str, Any]) -> bool:
        units = self.state_mgr.compute_position_size(is_smt_confirmed=sig["is_smt"])
        shares_per_unit = self.asset_cfg.get("shares_per_unit", 80)
        total_shares = units * shares_per_unit
        side_enum = OrderSide.BUY if sig["side"] == "BUY" else OrderSide.SELL

        print(f"\n🚀 EJECUTANDO ORDEN BRACKET: {self.primary_sym} | {sig['side']} | {total_shares} acciones ({units} unidades DP)")
        print(f"   Entrada: ${sig['entry']:.2f} | Stop: ${sig['stop']:.2f} | Target: ${sig['target']:.2f}")

        sig["ctos"] = units
        sig["units"] = units
        sig["qty"] = total_shares
        sig["risk_usd"] = round(sig["sl_dist"] * total_shares, 2)
        sig["sym"] = self.primary_sym
        self.notifier.notify_trade_opened(sig)

        if self.trading_client:
            try:
                req = MarketOrderRequest(
                    symbol=self.primary_sym,
                    qty=total_shares,
                    side=side_enum,
                    time_in_force=TimeInForce.DAY,
                    order_class=OrderClass.BRACKET,
                    take_profit=TakeProfitRequest(limit_price=sig["target"]),
                    stop_loss=StopLossRequest(stop_price=sig["stop"])
                )
                order = self.trading_client.submit_order(req)
                print(f"✅ Orden enviada a Alpaca ID: {order.id}")
                return True
            except Exception as e:
                print(f"❌ Error al enviar orden a Alpaca: {e}")
                return False
        return True

    def run_cycle(self):
        now_ny = datetime.now(self.tz)
        today_date = now_ny.date()
        time_str = now_ny.strftime("%H:%M")

        if self.current_session_date != today_date:
            self.current_session_date = today_date
            self.trades_today = 0
            self.daily_loss_occurred = False

        if not (cfg.WINDOW_START <= time_str <= cfg.WINDOW_END):
            return

        if cfg.HARD_HALT_ON_LOSS and self.daily_loss_occurred:
            return
        if self.trades_today >= cfg.MAX_TRADES_PER_DAY:
            return

        if self.get_open_positions_count() > 0:
            return

        df_p = self.fetch_bars(self.primary_sym)
        df_r = self.fetch_bars(self.ref_sym)
        if df_p is None or len(df_p) < 15:
            return

        sig = self.engine.evaluate_signal(df_p, df_r, asset_config=self.asset_cfg)
        if sig:
            success = self.execute_bracket_order(sig)
            if success:
                self.trades_today += 1

        if time_str >= cfg.DAILY_REPORT_TIME and self.state_mgr.state.get("last_summary_date") != str(today_date):
            chart_path = generate_daily_chart(self.state_mgr.state)
            summary = self.state_mgr.get_daily_metrics(str(today_date))
            self.notifier.notify_daily_summary(summary, chart_path)
            self.state_mgr.state["last_summary_date"] = str(today_date)
            self.state_mgr.save()

    def start(self):
        print("=" * 80)
        print(f"⚡ OUROBOROS QUANT: DAEMON ALPACA APEX SPRINT CHAMPION v3.0")
        print(f"• Activo Principal: {self.primary_sym} (Referencia SMT: {self.ref_sym})")
        print(f"• Modelo de Sizing: {cfg.STRATEGY_MODEL} (DP_V1_ADAPTIVE)")
        print(f"• Modo de Cuenta: {'PAPER TRADING' if cfg.ALPACA_PAPER else 'REAL ACCOUNT (LIVE)'}")
        print("=" * 80)
        self.notifier.notify_startup(
            self.state_mgr.state["balance"],
            self.state_mgr.state["floor"],
            self.state_mgr.get_cushion(),
            mode="Alpaca Daemon"
        )
        while True:
            try:
                self.run_cycle()
            except Exception as e:
                print(f"⚠️ Error en ciclo Alpaca: {e}")
            time.sleep(30)


def main():
    daemon = AlpacaChampionDaemon()
    daemon.start()


if __name__ == "__main__":
    main()
