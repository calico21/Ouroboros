"""
VWAP Mean Reversion Strategy for Intraday CME Futures.
Fades statistical over-extensions past +/- 2 standard deviations back toward session VWAP.
"""
from datetime import time
from typing import Optional
from src.core.events import BarEvent, TradeSetup
from src.core.enums import OrderSide, OrderType
from src.strategies.base import BaseStrategy
from src.strategies.vwap_mean_reversion_10am.indicators import SessionVWAPTracker


class VwapMeanReversion10amStrategy(BaseStrategy):
    """
    VWAP Mean Reversion Strategy (active after 10:00 AM EST).
    Identifies exhaustion beyond 2 standard deviations of VWAP with target at mean.
    """

    def __init__(self, config_overrides: Optional[dict] = None):
        super().__init__(config_overrides)
        self.vwap_tracker = SessionVWAPTracker()
        self.trades_this_session = 0

    def reset_session(self) -> None:
        self.vwap_tracker.reset()
        self.trades_this_session = 0

    def on_bar(self, bar: BarEvent) -> Optional[TradeSetup]:
        self.check_session_boundary(bar)

        vwap, std_dev = self.vwap_tracker.update(bar.high, bar.low, bar.close, bar.volume)
        if vwap is None or std_dev <= 0:
            return None

        t = bar.timestamp.time()
        # Execution window: 10:00 - 14:00 EST
        if t < time(10, 0) or t >= time(14, 0):
            return None

        if self.trades_this_session >= self.config.get("max_trades_per_session", 2):
            return None

        multiplier = self.config.get("band_std_threshold", 2.0)
        upper_band = vwap + (multiplier * std_dev)
        lower_band = vwap - (multiplier * std_dev)

        buffer_pts = self.config.get("stop_buffer_ticks", 4) * 0.25

        # Long Setup: Low pierced lower band, close printed bullish rejection hammer
        if bar.low < lower_band and bar.close > bar.open:
            stop_loss = bar.low - buffer_pts
            risk = bar.close - stop_loss
            if risk < self.config.get("min_risk_points", 8.0) or risk > self.config.get("max_risk_points", 35.0):
                return None

            take_profit = vwap
            # Must offer at least 1.2R reward to risk
            if (take_profit - bar.close) < (1.2 * risk):
                return None

            self.trades_this_session += 1
            return TradeSetup(
                direction=OrderSide.LONG,
                order_type=OrderType.MARKET,
                stop_loss=round(stop_loss, 2),
                take_profit=round(take_profit, 2),
                ttl_bars=self.config.get("ttl_bars", 8),
                tag="VWAP_FADE_LONG",
                metadata={"vwap": round(vwap, 2), "std_dev": round(std_dev, 2)}
            )

        # Short Setup: High pierced upper band, close printed bearish rejection
        elif bar.high > upper_band and bar.close < bar.open:
            stop_loss = bar.high + buffer_pts
            risk = stop_loss - bar.close
            if risk < self.config.get("min_risk_points", 8.0) or risk > self.config.get("max_risk_points", 35.0):
                return None

            take_profit = vwap
            if (bar.close - take_profit) < (1.2 * risk):
                return None

            self.trades_this_session += 1
            return TradeSetup(
                direction=OrderSide.SHORT,
                order_type=OrderType.MARKET,
                stop_loss=round(stop_loss, 2),
                take_profit=round(take_profit, 2),
                ttl_bars=self.config.get("ttl_bars", 8),
                tag="VWAP_FADE_SHORT",
                metadata={"vwap": round(vwap, 2), "std_dev": round(std_dev, 2)}
            )

        return None
