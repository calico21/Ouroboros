"""
Dynamic MTM Ratchet Floor Stress Envelope Generator.
Constructs precision data series tracking:
- Cumulative Account Equity
- Peak High Water Mark (HWM)
- Dynamic Trailing Drawdown Floor (-$2,500 trailing, locked at $50,100)
- Buffer Clearance ($ to floor)
- Intra-trade adverse excursion spikes
Provides structured JSON time-series for React SVG charting.
"""
from typing import Dict, List, Optional
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field


class RatchetPlotPoint(BaseModel):
    trade_num: int
    timestamp: str
    equity: float
    hwm: float
    trailing_floor: float
    buffer_clearance: float
    is_locked: bool
    trade_pnl: float


class RatchetEnvelopeReport(BaseModel):
    min_clearance: float
    min_clearance_trade: int
    permanent_lock_achieved: bool
    lock_trade_num: Optional[int]
    terminal_equity: float
    terminal_floor: float
    points: List[RatchetPlotPoint]


class UnderwaterRatchetPlotter:
    """
    Computes time-series envelope for Apex 50k trailing floor.
    """

    def __init__(
        self,
        starting_equity: float = 50000.0,
        trailing_buffer: float = 2500.0,
        permanent_lock_level: float = 50100.0,
        hwm_trigger_for_lock: float = 52600.0
    ):
        self.starting_equity = starting_equity
        self.trailing_buffer = trailing_buffer
        self.permanent_lock_level = permanent_lock_level
        self.hwm_trigger_for_lock = hwm_trigger_for_lock

    def generate_envelope(self, trades_df: pd.DataFrame) -> RatchetEnvelopeReport:
        if trades_df.empty:
            return RatchetEnvelopeReport(
                min_clearance=self.trailing_buffer,
                min_clearance_trade=0,
                permanent_lock_achieved=False,
                lock_trade_num=None,
                terminal_equity=self.starting_equity,
                terminal_floor=self.starting_equity - self.trailing_buffer,
                points=[]
            )

        df = trades_df.copy()
        time_col = "exit_time" if "exit_time" in df.columns else ("timestamp" if "timestamp" in df.columns else df.columns[0])
        pnl_col = "net_pnl" if "net_pnl" in df.columns else "pnl"

        equity = self.starting_equity
        hwm = self.starting_equity
        floor = hwm - self.trailing_buffer
        is_locked = False
        lock_trade: Optional[int] = None

        points: List[RatchetPlotPoint] = []
        min_clearance = self.trailing_buffer
        min_clearance_trade = 0

        # Initial point
        points.append(RatchetPlotPoint(
            trade_num=0,
            timestamp=str(df[time_col].iloc[0]) if len(df) > 0 else "0",
            equity=equity,
            hwm=hwm,
            trailing_floor=floor,
            buffer_clearance=self.trailing_buffer,
            is_locked=False,
            trade_pnl=0.0
        ))

        for idx, (_, row) in enumerate(df.iterrows(), 1):
            pnl = float(row[pnl_col])
            equity += pnl

            if equity > hwm:
                hwm = equity
                if hwm >= self.hwm_trigger_for_lock and not is_locked:
                    is_locked = True
                    lock_trade = idx
                    floor = self.permanent_lock_level
                elif not is_locked:
                    floor = hwm - self.trailing_buffer

            clearance = equity - floor
            if clearance < min_clearance:
                min_clearance = clearance
                min_clearance_trade = idx

            points.append(RatchetPlotPoint(
                trade_num=idx,
                timestamp=str(row[time_col]),
                equity=round(equity, 2),
                hwm=round(hwm, 2),
                trailing_floor=round(floor, 2),
                buffer_clearance=round(clearance, 2),
                is_locked=is_locked,
                trade_pnl=round(pnl, 2)
            ))

        return RatchetEnvelopeReport(
            min_clearance=round(min_clearance, 2),
            min_clearance_trade=min_clearance_trade,
            permanent_lock_achieved=is_locked,
            lock_trade_num=lock_trade,
            terminal_equity=round(equity, 2),
            terminal_floor=round(floor, 2),
            points=points
        )
