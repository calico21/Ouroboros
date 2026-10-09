"""
Ex-Ante Pre-Registration Gate Audit & Forward Excursion Profiler (AlphaForge).
Enforces strict two-stage quantitative evaluation:
Stage 1: Gate Participation Audit (Percentage of trading sessions qualifying).
         Requires strictly 15% to 30% participation rate (40-75 trades/year).
         Rejects candidates triggering on >35% of days for over-participation.
Stage 2: Forward Excursion Profiling (30m and 60m forward MFE/MAE in R-units before execution).
"""
from typing import Dict, Any, List, Optional, Tuple, Type
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

from src.core.events import BarEvent, TradeSetup
from src.core.enums import OrderSide
from src.strategies.base import BaseStrategy
from src.data.cme_session_clock import get_cme_trade_date_str


class PreRegistrationGateAuditor:
    """
    Audits ex-ante pre-trade gate participation and measures forward excursions
    with ZERO PnL or trade outcome lookahead.
    """

    def __init__(
        self,
        min_participation_rate: float = 15.0,
        max_participation_rate: float = 30.0,
        over_participation_ceiling: float = 35.0
    ):
        self.min_participation_rate = min_participation_rate
        self.max_participation_rate = max_participation_rate
        self.over_participation_ceiling = over_participation_ceiling

    def audit_strategy(
        self,
        strategy: BaseStrategy,
        bars: List[BarEvent]
    ) -> Dict[str, Any]:
        """
        Executes two-stage ex-ante audit:
        1. Tracks qualified sessions vs total sessions.
        2. Measures 30m and 60m forward MFE/MAE on qualified entries.
        """
        strategy.reset_session()
        total_sessions_set = set()
        qualified_sessions_set = set()
        qualified_events: List[Dict[str, Any]] = []

        # Map bars by index for fast forward lookups
        n_bars = len(bars)

        for i, bar in enumerate(bars):
            strategy.check_session_boundary(bar)
            trade_date = get_cme_trade_date_str(bar.timestamp)
            total_sessions_set.add(trade_date)

            # Strategy evaluates bar
            setup = strategy.on_bar(bar)
            if setup is not None:
                # Gate triggered
                qualified_sessions_set.add(trade_date)

                # Measure forward excursions: 30m (6 bars) and 60m (12 bars)
                stop_dist = abs(bar.close - setup.stop_loss)
                if stop_dist <= 0:
                    stop_dist = 5.0

                fwd_30m_bars = bars[i + 1: min(n_bars, i + 7)]
                fwd_60m_bars = bars[i + 1: min(n_bars, i + 13)]

                mfe_30, mae_30 = self._calc_excursion(bar.close, setup.direction, fwd_30m_bars)
                mfe_60, mae_60 = self._calc_excursion(bar.close, setup.direction, fwd_60m_bars)

                qualified_events.append({
                    "timestamp": bar.timestamp,
                    "trade_date": trade_date,
                    "direction": setup.direction.value if hasattr(setup.direction, "value") else str(setup.direction),
                    "entry_price": bar.close,
                    "stop_loss": setup.stop_loss,
                    "risk_r_pts": stop_dist,
                    "fwd_30m_mfe_r": mfe_30 / stop_dist,
                    "fwd_30m_mae_r": mae_30 / stop_dist,
                    "fwd_60m_mfe_r": mfe_60 / stop_dist,
                    "fwd_60m_mae_r": mae_60 / stop_dist,
                })

        total_sessions = max(1, len(total_sessions_set))
        qualified_sessions = len(qualified_sessions_set)
        participation_rate = (qualified_sessions / total_sessions) * 100.0

        # Stage 1 Verdict
        if participation_rate > self.over_participation_ceiling:
            gate_status = "REJECTED_OVER_PARTICIPATION"
            is_qualified = False
        elif participation_rate < self.min_participation_rate:
            gate_status = "UNDER_PARTICIPATION"
            is_qualified = False
        elif participation_rate <= self.max_participation_rate:
            gate_status = "QUALIFIED_CANONICAL"
            is_qualified = True
        else:
            gate_status = "BORDERLINE_ACCEPTABLE"
            is_qualified = True

        # Stage 2 Forward Excursion Metrics
        if qualified_events:
            df_ev = pd.DataFrame(qualified_events)
            mfe_30_mean = float(df_ev["fwd_30m_mfe_r"].mean())
            mae_30_mean = float(df_ev["fwd_30m_mae_r"].mean())
            mfe_60_mean = float(df_ev["fwd_60m_mfe_r"].mean())
            mae_60_mean = float(df_ev["fwd_60m_mae_r"].mean())
            edge_ratio_30m = mfe_30_mean / max(0.01, mae_30_mean)
            edge_ratio_60m = mfe_60_mean / max(0.01, mae_60_mean)
        else:
            mfe_30_mean, mae_30_mean, mfe_60_mean, mae_60_mean = 0.0, 0.0, 0.0, 0.0
            edge_ratio_30m, edge_ratio_60m = 0.0, 0.0

        strat_name = getattr(strategy, "config", {}).get("strategy_name", strategy.__class__.__name__)

        return {
            "strategy_name": strat_name,
            "total_sessions": total_sessions,
            "qualified_sessions": qualified_sessions,
            "participation_rate_pct": round(participation_rate, 2),
            "gate_status": gate_status,
            "is_qualified": is_qualified,
            "total_setups_triggered": len(qualified_events),
            "forward_30m": {
                "mean_mfe_r": round(mfe_30_mean, 3),
                "mean_mae_r": round(mae_30_mean, 3),
                "edge_ratio": round(edge_ratio_30m, 2)
            },
            "forward_60m": {
                "mean_mfe_r": round(mfe_60_mean, 3),
                "mean_mae_r": round(mae_60_mean, 3),
                "edge_ratio": round(edge_ratio_60m, 2)
            }
        }

    def _calc_excursion(
        self,
        entry_price: float,
        side: Any,
        fwd_bars: List[BarEvent]
    ) -> Tuple[float, float]:
        """Calculates forward MFE and MAE in price points."""
        if not fwd_bars:
            return 0.0, 0.0

        is_long = (side == OrderSide.LONG or str(side).upper() in ("LONG", "BUY"))
        if is_long:
            highs = [b.high for b in fwd_bars]
            lows = [b.low for b in fwd_bars]
            mfe = max(0.0, max(highs) - entry_price)
            mae = max(0.0, entry_price - min(lows))
        else:
            highs = [b.high for b in fwd_bars]
            lows = [b.low for b in fwd_bars]
            mfe = max(0.0, entry_price - min(lows))
            mae = max(0.0, max(highs) - entry_price)

        return float(mfe), float(mae)
