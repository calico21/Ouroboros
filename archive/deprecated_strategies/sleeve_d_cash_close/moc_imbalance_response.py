"""
Strategy 8: moc_imbalance_response (Sleeve D: Cash Close & Structural Flows).
Exploits NYSE/Nasdaq closing-cross imbalance dissemination at 15:50 ET driving index arbitrage basis trades.
Compliance Exception: Hard liquidation extended to 15:58:00 ET exclusively for this strategy.
"""
from typing import Optional, Dict, Any, List
from datetime import time
from src.core.events import BarEvent, TradeSetup
from src.core.enums import OrderSide, OrderType
from src.strategies.base import BaseStrategy
from src.data.cme_session_clock import ensure_ny_tz


class MocImbalanceResponseStrategy(BaseStrategy):
    STRATEGY_NAME = "moc_imbalance_response"

    def __init__(self, config_overrides: Optional[Dict[str, Any]] = None):
        super().__init__(config_overrides)
        self.reset_session()

    def reset_session(self) -> None:
        self.session_open_price: Optional[float] = None
        self.trade_taken_today = False

    def on_bar(self, bar: BarEvent) -> Optional[TradeSetup]:
        if self.trade_taken_today:
            return None

        et = ensure_ny_tz(bar.timestamp)
        t = et.time()

        if time(9, 30) <= t < time(9, 35):
            self.session_open_price = bar.open
            return None

        # Window: 15:50 to 15:55 ET
        if time(15, 50) <= t <= time(15, 55):
            meta = bar.metadata or {}
            vwap = meta.get("vwap", bar.close)
            vol_pct = meta.get("vol_pct_60", 65.0)

            # Gate: Strong volume and clear directional trend alignment at 15:50
            if vol_pct < 60.0:
                return None

            trend_up = bar.close > vwap and (self.session_open_price and bar.close > self.session_open_price)
            trend_down = bar.close < vwap and (self.session_open_price and bar.close < self.session_open_price)

            if not (trend_up or trend_down):
                return None

            fixed_sl = 14.0  # 12-15 pts fixed SL
            target_pts = 16.0

            if trend_up:
                entry = bar.close
                sl = entry - fixed_sl
                tp = entry + target_pts
                self.trade_taken_today = True

                return TradeSetup(
                    strategy_name=self.STRATEGY_NAME,
                    symbol=bar.symbol,
                    direction=OrderSide.LONG,
                    order_type=OrderType.MARKET,
                    stop_loss=round(sl * 4) / 4,
                    take_profit=round(tp * 4) / 4,
                    time_stop_bars=2,  # Strict exit by 15:58:00 ET
                    protect_at_1r=False,
                    tag="MOC_IMBALANCE_BURST_LONG"
                )
            elif trend_down:
                entry = bar.close
                sl = entry + fixed_sl
                tp = entry - target_pts
                self.trade_taken_today = True

                return TradeSetup(
                    strategy_name=self.STRATEGY_NAME,
                    symbol=bar.symbol,
                    direction=OrderSide.SHORT,
                    order_type=OrderType.MARKET,
                    stop_loss=round(sl * 4) / 4,
                    take_profit=round(tp * 4) / 4,
                    time_stop_bars=2,  # Strict exit by 15:58:00 ET
                    protect_at_1r=False,
                    tag="MOC_IMBALANCE_BURST_SHORT"
                )

        return None
