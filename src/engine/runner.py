"""
Master Backtest & Execution Simulation Runner for AlphaForge.
Coordinates bar ingestion, alpha evaluation, order execution, and account tracking.
"""
from typing import Dict, Any, Optional
import yaml
from pathlib import Path

from src.core.events import BarEvent
from src.core.exceptions import AccountBreachedError
from src.data.loader import DataLoader
from src.engine.fee_models import FeeModel
from src.engine.account_tracker import PropFirmAccountTracker
from src.engine.position_sizer import PropFirmPositionSizer
from src.engine.execution_simulator import ExecutionSimulator
from src.strategies.base import BaseStrategy
from src.analytics.metrics_engine import MetricsEngine
from src.validation.monte_carlo import PropFirmMonteCarloSimulator


class BacktestRunner:
    """Executes institutional-grade futures simulation and forensic diagnostic audits."""

    def __init__(
        self,
        strategy: BaseStrategy,
        prop_firm_config: Dict[str, Any],
        execution_config: Dict[str, Any],
        instrument_config: Dict[str, Any]
    ):
        self.strategy = strategy
        self.prop_firm_config = prop_firm_config
        self.execution_config = execution_config
        self.instrument_config = instrument_config

        # Instantiate Engine Components
        self.account = PropFirmAccountTracker.from_config(prop_firm_config)
        self.simulator = ExecutionSimulator.from_config(execution_config, instrument_config)
        self.sizer = PropFirmPositionSizer.from_config(execution_config, prop_firm_config, instrument_config)

    @classmethod
    def from_config_files(
        cls,
        strategy: BaseStrategy,
        prop_firm_cfg_path: str = "configs/prop_firm/apex_50k_trailing_mtm.yaml",
        execution_cfg_path: str = "configs/execution/cme_globex_default.yaml",
        instrument_cfg_path: str = "configs/instruments/mnq.yaml"
    ) -> "BacktestRunner":
        with open(prop_firm_cfg_path, "r") as f:
            prop_cfg = yaml.safe_load(f)
        with open(execution_cfg_path, "r") as f:
            exec_cfg = yaml.safe_load(f)
        with open(instrument_cfg_path, "r") as f:
            inst_cfg = yaml.safe_load(f)

        return cls(strategy, prop_cfg, exec_cfg, inst_cfg)

    def run(self, loader: DataLoader) -> Dict[str, Any]:
        """Runs full event-driven simulation loop over loader bar generator."""
        bars_processed = 0

        for bar in loader.get_bars():
            bars_processed += 1

            # 1. New day session checks
            self.account.check_new_day(bar.timestamp)
            self.strategy.check_session_boundary(bar)

            # 2. Process active trades & pending orders with current bar
            self.simulator.process_bar(bar, self.account)

            # 3. If account breached or liquidated, break simulation early
            if not self.account.is_active:
                break

            # 4. Strategy generates setup (blind to capital or account details)
            setup = self.strategy.on_bar(bar)

            # 5. Position sizing based on cushion to trailing floor
            if setup and self.simulator.active_trade is None:
                risk_points = abs(bar.close - setup.stop_loss)
                contracts = self.sizer.calculate_lots(self.account.cushion, risk_points)

                if contracts > 0:
                    self.simulator.submit_setup(setup, bar, contracts)

        # Label strategy name on all closed trades
        strat_name = getattr(self.strategy, "config", {}).get("strategy_name", self.strategy.__class__.__name__)
        for t in self.simulator.closed_trades:
            t.strategy_name = strat_name

        # Compute forensic metrics
        pt_val = float(self.instrument_config.get("point_value", 2.00))
        tick_sz = float(self.instrument_config.get("tick_size", 0.25))

        metrics = MetricsEngine.compute_all(
            trades=self.simulator.closed_trades,
            account=self.account,
            point_value=pt_val,
            tick_size=tick_sz
        )

        metrics["bars_processed"] = bars_processed
        metrics["strategy_name"] = strat_name

        return metrics
