"""
Statistical Alpha Drift & Performance Quarantine Sentinel for AlphaForge.
Implements real-time Sequential Probability Ratio Testing (CUSUM change-point detection),
rolling Wilson Score interval monitoring, and cumulative drawdown circuit breakers.
Quarantines alpha execution upon statistically significant deterioration.
"""
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import json
import numpy as np


@dataclass
class TradeOutcome:
    """Record of a closed trade's normalized performance."""
    trade_id: str
    strategy: str
    realized_r: float
    realized_pnl: float
    is_win: bool
    exit_timestamp: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DriftStatus:
    """Current statistical surveillance diagnosis."""
    status: str  # "HEALTHY", "WARNING", "QUARANTINED"
    trade_count: int
    rolling_win_rate_15: float
    wilson_lower_bound: float
    rolling_expectancy_15: float
    expectancy_hurdle: float
    cusum_statistic: float
    cusum_threshold: float
    peak_equity_pnl: float
    current_equity_pnl: float
    current_drawdown_dollars: float
    drawdown_limit_dollars: float
    reason: Optional[str]
    last_update: str


class AlphaDriftSentinel:
    """
    Continuous statistical surveillance engine detecting alpha decay.
    Employs Page-Hinkley / CUSUM change-point detection on standardized R returns,
    enforcing automated quarantine before account trailing floors are breached.
    """

    def __init__(
        self,
        strategy_name: str = "afternoon_trend_continuation",
        expected_r_mean: float = 0.569,  # Institutional baseline from Phase 4 post-mortem
        wilson_lower_bound: float = 0.581,  # 95% Wilson CI lower bound (58.1%)
        expectancy_hurdle: float = 0.150,  # Minimum acceptable rolling expectancy (+0.15R)
        drawdown_quarantine_dollars: float = 800.0,  # 32% of $2,500 Apex buffer
        cusum_allowance_k: float = 0.250,  # Tolerance parameter k in R units
        cusum_threshold_h: float = 4.000,  # Decision boundary h (cumulative R units)
        log_path: str = "reports/telemetry/alpha_drift_status.json",
        notifier: Optional[Any] = None
    ):
        self.strategy_name = strategy_name
        self.mu_0 = expected_r_mean
        self.wilson_lower_bound = wilson_lower_bound
        self.expectancy_hurdle = expectancy_hurdle
        self.drawdown_limit = drawdown_quarantine_dollars
        self.k = cusum_allowance_k
        self.h = cusum_threshold_h
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.notifier = notifier

        self.trades: List[TradeOutcome] = []
        self.cusum_s: float = 0.0
        self.peak_pnl: float = 0.0
        self.cumulative_pnl: float = 0.0
        self.is_quarantined: bool = False
        self.quarantine_reason: Optional[str] = None

    def record_trade(
        self,
        trade_id: str,
        realized_r: float,
        realized_pnl: float,
        timestamp: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> DriftStatus:
        """
        Ingests a realized trade outcome, updates CUSUM sequential test,
        and evaluates quarantine conditions.
        """
        ts_str = (timestamp or datetime.utcnow()).isoformat()
        is_win = realized_pnl > 0.0

        outcome = TradeOutcome(
            trade_id=trade_id,
            strategy=self.strategy_name,
            realized_r=realized_r,
            realized_pnl=realized_pnl,
            is_win=is_win,
            exit_timestamp=ts_str,
            metadata=metadata or {}
        )
        self.trades.append(outcome)

        # Update Cumulative Equity & Drawdown
        self.cumulative_pnl += realized_pnl
        if self.cumulative_pnl > self.peak_pnl:
            self.peak_pnl = self.cumulative_pnl
        current_dd = self.peak_pnl - self.cumulative_pnl

        # Update CUSUM Statistic for Negative Drift:
        # S_n = max(0, S_{n-1} + (mu_0 - R_n - k))
        # Accumulates when realized return is significantly worse than expected
        drift_delta = (self.mu_0 - realized_r) - self.k
        self.cusum_s = max(0.0, self.cusum_s + drift_delta)

        # Compute Rolling Metrics (Last 15 trades)
        rolling_n = 15
        recent = self.trades[-rolling_n:]
        n_recent = len(recent)

        if n_recent > 0:
            rolling_wr = sum(1 for t in recent if t.is_win) / n_recent
            rolling_exp = float(np.mean([t.realized_r for t in recent]))
        else:
            rolling_wr = 1.0
            rolling_exp = self.mu_0

        # Evaluate Quarantine & Warning States
        status = "HEALTHY"
        reason = None

        # Condition 1: Hard Drawdown Breaker ($800 reached)
        if current_dd >= self.drawdown_limit:
            self.is_quarantined = True
            status = "QUARANTINED"
            reason = (
                f"CUMULATIVE DRAWDOWN EXCEEDED: Realized DD ${current_dd:.2f} >= "
                f"${self.drawdown_limit:.2f} threshold (32% of total Apex buffer)."
            )

        # Condition 2: CUSUM Structural Breakpoint (S_n >= h)
        elif self.cusum_s >= self.h:
            self.is_quarantined = True
            status = "QUARANTINED"
            reason = (
                f"CUSUM CHANGE-POINT TRIGGERED: Statistic S_n={self.cusum_s:.2f} >= "
                f"threshold h={self.h:.2f}. Statistically significant negative alpha decay detected."
            )

        # Condition 3: Rolling 15-Trade Degeneration Warning
        elif n_recent >= 15:
            if rolling_wr < self.wilson_lower_bound or rolling_exp < self.expectancy_hurdle:
                status = "WARNING"
                reason = (
                    f"STATISTICAL ROLLING WARNING: 15-trade Win Rate={rolling_wr*100:.1f}% "
                    f"(Wilson lower bound={self.wilson_lower_bound*100:.1f}%) or Expectancy={rolling_exp:.2f}R "
                    f"(< {self.expectancy_hurdle:.2f}R hurdle)."
                )

        if self.is_quarantined and not self.quarantine_reason:
            self.quarantine_reason = reason
            if self.notifier:
                try:
                    self.notifier.send_alert(
                        event_type="STRATEGY_QUARANTINED",
                        title="AUTOMATED STRATEGY QUARANTINE TRIGGERED",
                        description=f"Alpha execution halted for **{self.strategy_name}**: {reason}",
                        fields={
                            "Strategy": self.strategy_name,
                            "CUSUM Statistic": f"{self.cusum_s:.3f} (Limit: {self.h:.2f})",
                            "Current Drawdown": f"${current_dd:.2f} (Limit: ${self.drawdown_limit:.2f})",
                            "Rolling 15-Trade WR": f"{rolling_wr*100:.1f}%",
                            "Rolling Expectancy": f"{rolling_exp:.3f}R"
                        },
                        color_hex="#FF0055"
                    )
                except Exception:
                    pass

        drift_status = DriftStatus(
            status=status if not self.is_quarantined else "QUARANTINED",
            trade_count=len(self.trades),
            rolling_win_rate_15=round(rolling_wr, 3),
            wilson_lower_bound=self.wilson_lower_bound,
            rolling_expectancy_15=round(rolling_exp, 3),
            expectancy_hurdle=self.expectancy_hurdle,
            cusum_statistic=round(self.cusum_s, 3),
            cusum_threshold=self.h,
            peak_equity_pnl=round(self.peak_pnl, 2),
            current_equity_pnl=round(self.cumulative_pnl, 2),
            current_drawdown_dollars=round(current_dd, 2),
            drawdown_limit_dollars=self.drawdown_limit,
            reason=self.quarantine_reason or reason,
            last_update=ts_str
        )

        self._persist_status(drift_status)
        return drift_status

    def get_status(self) -> DriftStatus:
        """Returns current surveillance state snapshot."""
        if not self.trades:
            return DriftStatus(
                status="HEALTHY",
                trade_count=0,
                rolling_win_rate_15=0.705,
                wilson_lower_bound=self.wilson_lower_bound,
                rolling_expectancy_15=self.mu_0,
                expectancy_hurdle=self.expectancy_hurdle,
                cusum_statistic=0.0,
                cusum_threshold=self.h,
                peak_equity_pnl=0.0,
                current_equity_pnl=0.0,
                current_drawdown_dollars=0.0,
                drawdown_limit_dollars=self.drawdown_limit,
                reason=None,
                last_update=datetime.utcnow().isoformat()
            )
        # Compute from current state
        rolling_n = 15
        recent = self.trades[-rolling_n:]
        rolling_wr = sum(1 for t in recent if t.is_win) / len(recent)
        rolling_exp = float(np.mean([t.realized_r for t in recent]))
        current_dd = self.peak_pnl - self.cumulative_pnl

        status = "HEALTHY"
        reason = None
        if self.is_quarantined:
            status = "QUARANTINED"
            reason = self.quarantine_reason
        elif len(recent) >= 15 and (rolling_wr < self.wilson_lower_bound or rolling_exp < self.expectancy_hurdle):
            status = "WARNING"
            reason = (
                f"STATISTICAL ROLLING WARNING: 15-trade Win Rate={rolling_wr*100:.1f}% "
                f"(Wilson lower bound={self.wilson_lower_bound*100:.1f}%) or Expectancy={rolling_exp:.2f}R "
                f"(< {self.expectancy_hurdle:.2f}R hurdle)."
            )

        return DriftStatus(
            status=status,
            trade_count=len(self.trades),
            rolling_win_rate_15=round(rolling_wr, 3),
            wilson_lower_bound=self.wilson_lower_bound,
            rolling_expectancy_15=round(rolling_exp, 3),
            expectancy_hurdle=self.expectancy_hurdle,
            cusum_statistic=round(self.cusum_s, 3),
            cusum_threshold=self.h,
            peak_equity_pnl=round(self.peak_pnl, 2),
            current_equity_pnl=round(self.cumulative_pnl, 2),
            current_drawdown_dollars=round(current_dd, 2),
            drawdown_limit_dollars=self.drawdown_limit,
            reason=reason,
            last_update=datetime.utcnow().isoformat()
        )

    def reset_quarantine(self) -> None:
        """Manual operator override to reset CUSUM statistic and quarantine."""
        self.is_quarantined = False
        self.quarantine_reason = None
        self.cusum_s = 0.0

    def _persist_status(self, status: DriftStatus) -> None:
        """Persists current diagnosis to disk."""
        with open(self.log_path, "w") as f:
            json.dump(asdict(status), f, indent=2)
