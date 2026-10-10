"""
Rigorous Calendar-Day Performance Metrics Engine.
Eliminates trade-concatenation distortion by evaluating returns over continuous
calendar trading days ($0 PnL accounting on non-trading/flat days, 252-day annualization).
Calculates true econometric ratios:
- Calendar-Day Sharpe Ratio
- Calendar-Day Sortino Ratio (Downside deviation only)
- Calmar Ratio (Annualized Return / Max Realized Drawdown)
- Gain-to-Pain Ratio (Jack Schwager)
- Trading Day Participation & Exposure Rate
"""
from typing import Dict, List, Optional, Union
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from src.data.macro_calendar import MacroCalendar, MarketSessionType


class CalendarMetricsResult(BaseModel):
    total_calendar_days: int
    trading_days_active: int
    trading_days_total: int
    exposure_rate_pct: float
    total_net_pnl: float
    annualized_pnl: float
    daily_pnl_mean: float
    daily_pnl_std: float
    daily_downside_std: float
    calendar_sharpe: float
    calendar_sortino: float
    calmar_ratio: float
    gain_to_pain_ratio: float
    max_drawdown_dollars: float
    max_drawdown_pct: float
    win_rate_daily_pct: float
    best_day_pnl: float
    worst_day_pnl: float


class CalendarMetricsCalculator:
    """
    Computes unbiased continuous calendar metrics from realized trade logs.
    """

    def __init__(self, macro_calendar: Optional[MacroCalendar] = None, starting_equity: float = 50000.0):
        self.calendar = macro_calendar or MacroCalendar()
        self.starting_equity = starting_equity

    def compute(
        self,
        trades_df: pd.DataFrame,
        start_date: Union[str, pd.Timestamp],
        end_date: Union[str, pd.Timestamp]
    ) -> CalendarMetricsResult:
        """
        Calculates calendar metrics from trade records.
        trades_df must have 'exit_time' (or 'timestamp') and 'net_pnl'.
        """
        start_dt = pd.to_datetime(start_date).date()
        end_dt = pd.to_datetime(end_date).date()

        # Build complete series of trading days
        trading_dates = []
        curr = start_dt
        while curr <= end_dt:
            if self.calendar.is_trading_day(curr):
                trading_dates.append(curr.isoformat())
            curr += pd.Timedelta(days=1)

        total_trading_days = max(len(trading_dates), 1)

        # Aggregate trade PnL by date
        daily_pnl_map: Dict[str, float] = {d: 0.0 for d in trading_dates}

        if not trades_df.empty:
            df = trades_df.copy()
            time_col = "exit_time" if "exit_time" in df.columns else ("timestamp" if "timestamp" in df.columns else df.columns[0])
            try:
                df["date_str"] = pd.to_datetime(df[time_col], utc=True).dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d")
            except Exception:
                df["date_str"] = [str(pd.Timestamp(t).date()) for t in df[time_col]]
            
            pnl_col = "net_pnl" if "net_pnl" in df.columns else "pnl"
            grouped = df.groupby("date_str")[pnl_col].sum()

            for d_str, pnl in grouped.items():
                if d_str in daily_pnl_map:
                    daily_pnl_map[d_str] = float(pnl)

        daily_pnls = np.array([daily_pnl_map[d] for d in trading_dates], dtype=float)
        active_days = int(np.count_nonzero(daily_pnls != 0.0))
        exposure_rate = (active_days / total_trading_days) * 100.0

        total_pnl = float(np.sum(daily_pnls))
        years = max(total_trading_days / 252.0, 0.1)
        annualized_pnl = total_pnl / years

        mean_daily = float(np.mean(daily_pnls))
        std_daily = float(np.std(daily_pnls, ddof=1)) if len(daily_pnls) > 1 else 1e-6
        if std_daily < 1e-6:
            std_daily = 1e-6

        # Downside standard deviation (target = 0)
        downside_diffs = np.minimum(daily_pnls, 0.0)
        downside_std = float(np.sqrt(np.mean(downside_diffs ** 2)))
        if downside_std < 1e-6:
            downside_std = 1e-6

        # 252-day annualized Sharpe & Sortino
        calendar_sharpe = float((mean_daily / std_daily) * np.sqrt(252.0))
        calendar_sortino = float((mean_daily / downside_std) * np.sqrt(252.0))

        # Equity curve & Max Drawdown
        cumulative = np.cumsum(daily_pnls)
        peak = np.maximum.accumulate(cumulative)
        drawdowns = peak - cumulative
        max_dd = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0
        max_dd_pct = (max_dd / self.starting_equity) * 100.0

        calmar = annualized_pnl / max_dd if max_dd > 0 else (99.9 if annualized_pnl > 0 else 0.0)

        # Gain-to-Pain Ratio
        pos_sum = float(np.sum(daily_pnls[daily_pnls > 0]))
        neg_sum = float(np.abs(np.sum(daily_pnls[daily_pnls < 0])))
        gain_to_pain = (pos_sum / neg_sum) if neg_sum > 0 else (99.0 if pos_sum > 0 else 0.0)

        # Win rate of active days
        active_pnls = daily_pnls[daily_pnls != 0.0]
        win_rate = (float(np.sum(active_pnls > 0)) / len(active_pnls) * 100.0) if len(active_pnls) > 0 else 0.0

        return CalendarMetricsResult(
            total_calendar_days=int((end_dt - start_dt).days + 1),
            trading_days_active=active_days,
            trading_days_total=total_trading_days,
            exposure_rate_pct=round(exposure_rate, 2),
            total_net_pnl=round(total_pnl, 2),
            annualized_pnl=round(annualized_pnl, 2),
            daily_pnl_mean=round(mean_daily, 2),
            daily_pnl_std=round(std_daily, 2),
            daily_downside_std=round(downside_std, 2),
            calendar_sharpe=round(calendar_sharpe, 3),
            calendar_sortino=round(calendar_sortino, 3),
            calmar_ratio=round(calmar, 3),
            gain_to_pain_ratio=round(gain_to_pain, 3),
            max_drawdown_dollars=round(max_dd, 2),
            max_drawdown_pct=round(max_dd_pct, 2),
            win_rate_daily_pct=round(win_rate, 2),
            best_day_pnl=round(float(np.max(daily_pnls)), 2) if len(daily_pnls) > 0 else 0.0,
            worst_day_pnl=round(float(np.min(daily_pnls)), 2) if len(daily_pnls) > 0 else 0.0,
        )
