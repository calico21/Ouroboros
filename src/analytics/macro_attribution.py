"""
Macroeconomic Catalyst Performance Attribution & Event-Day Slicing.
Decomposes trading strategy performance across high-impact economic catalysts:
- FOMC Rate Decisions & Press Conferences (14:00 EST)
- CPI Inflation Announcements (08:30 EST)
- NFP Employment Situation Reports (08:30 EST)
- Baseline Non-Event Regular Sessions
Reveals whether the alpha is catalyst-fragile or catalyst-resilient.
"""
from typing import Dict, List, Optional
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from src.data.macro_calendar import MacroCalendar, CatalystType


class CatalystCohortMetrics(BaseModel):
    catalyst: str
    total_trades: int
    net_pnl: float
    win_rate_pct: float
    profit_factor: float
    expectancy_r: float
    avg_trade_pnl: float
    max_loss: float
    max_win: float
    risk_adjusted_pnl_share: float


class MacroAttributionReport(BaseModel):
    cohorts: List[CatalystCohortMetrics]
    event_day_pnl: float
    non_event_day_pnl: float
    event_day_trade_count: int
    non_event_day_trade_count: int
    fomc_vulnerability_index: float  # < 0 indicates negative expectancy on FOMC days
    recommendation: str


class MacroAttributionAnalyzer:
    """
    Slices realized trade records by macroeconomic catalyst.
    """

    def __init__(self, macro_calendar: Optional[MacroCalendar] = None):
        self.calendar = macro_calendar or MacroCalendar()

    def analyze(self, trades_df: pd.DataFrame) -> MacroAttributionReport:
        if trades_df.empty:
            return MacroAttributionReport(
                cohorts=[],
                event_day_pnl=0.0,
                non_event_day_pnl=0.0,
                event_day_trade_count=0,
                non_event_day_trade_count=0,
                fomc_vulnerability_index=0.0,
                recommendation="NO_TRADES"
            )

        df = trades_df.copy()
        time_col = "entry_time" if "entry_time" in df.columns else ("timestamp" if "timestamp" in df.columns else df.columns[0])
        pnl_col = "net_pnl" if "net_pnl" in df.columns else "pnl"
        r_col = "r_multiple" if "r_multiple" in df.columns else None

        # Assign catalyst if not present
        if "catalyst" not in df.columns:
            catalysts = []
            for _, row in df.iterrows():
                dt = pd.to_datetime(row[time_col]).date()
                cat = self.calendar.get_primary_catalyst(dt)
                catalysts.append(cat.value)
            df["catalyst"] = catalysts

        total_pnl = float(df[pnl_col].sum())
        cohorts: List[CatalystCohortMetrics] = []

        for cat_name in [CatalystType.NONE.value, CatalystType.FOMC.value, CatalystType.CPI.value, CatalystType.NFP.value]:
            sub = df[df["catalyst"] == cat_name]
            n = len(sub)
            if n == 0:
                continue

            sub_pnl = float(sub[pnl_col].sum())
            wins = sub[sub[pnl_col] > 0]
            losses = sub[sub[pnl_col] < 0]
            wr = (len(wins) / n) * 100.0

            gross_win = float(wins[pnl_col].sum()) if len(wins) > 0 else 0.0
            gross_loss = abs(float(losses[pnl_col].sum())) if len(losses) > 0 else 0.0
            pf = (gross_win / gross_loss) if gross_loss > 0 else (99.0 if gross_win > 0 else 0.0)

            if r_col and r_col in sub.columns:
                exp_r = float(sub[r_col].mean())
            else:
                avg_loss = abs(float(losses[pnl_col].mean())) if len(losses) > 0 else 100.0
                exp_r = float(sub[pnl_col].mean()) / avg_loss if avg_loss > 0 else 0.0

            pnl_share = (sub_pnl / abs(total_pnl) * 100.0) if abs(total_pnl) > 0 else 0.0

            cohorts.append(CatalystCohortMetrics(
                catalyst=cat_name,
                total_trades=n,
                net_pnl=round(sub_pnl, 2),
                win_rate_pct=round(wr, 1),
                profit_factor=round(pf, 2),
                expectancy_r=round(exp_r, 3),
                avg_trade_pnl=round(sub_pnl / n, 2),
                max_loss=round(float(sub[pnl_col].min()), 2),
                max_win=round(float(sub[pnl_col].max()), 2),
                risk_adjusted_pnl_share=round(pnl_share, 1)
            ))

        # Event day vs Non-event day split
        event_sub = df[df["catalyst"] != CatalystType.NONE.value]
        non_event_sub = df[df["catalyst"] == CatalystType.NONE.value]

        event_pnl = float(event_sub[pnl_col].sum()) if not event_sub.empty else 0.0
        non_event_pnl = float(non_event_sub[pnl_col].sum()) if not non_event_sub.empty else 0.0

        # FOMC vulnerability
        fomc_sub = df[df["catalyst"] == CatalystType.FOMC.value]
        fomc_vuln = float(fomc_sub[pnl_col].mean()) if not fomc_sub.empty else 0.0

        if fomc_vuln < -100.0:
            rec = "CRITICAL: FOMC sessions destroy capital. Enforce strict execution suppression around 14:00-15:00 EST."
        elif fomc_vuln > 50.0:
            rec = "EXCELLENT: Strategy successfully rides post-FOMC momentum after 14:30 EST press conference."
        else:
            rec = "NEUTRAL: Strategy shows balanced performance across macro event windows."

        return MacroAttributionReport(
            cohorts=cohorts,
            event_day_pnl=round(event_pnl, 2),
            non_event_day_pnl=round(non_event_pnl, 2),
            event_day_trade_count=len(event_sub),
            non_event_day_trade_count=len(non_event_sub),
            fomc_vulnerability_index=round(fomc_vuln, 2),
            recommendation=rec
        )
