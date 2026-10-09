"""
Multi-Strategy Portfolio Allocation Engine for AlphaForge.
Coordinates concurrent execution of multiple intraday futures strategies
against a single consolidated Apex 50k Peak-Unrealized MTM Trailing Floor,
enforces session-based cushion allocation, concurrency locks, and computes
diversification and correlation metrics.
Guarantees single-ratchet intra-bar accounting.
"""
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import yaml
import numpy as np
import pandas as pd

from src.core.events import BarEvent, TradeRecord, TradeSetup
from src.core.enums import OrderSide, AccountStatus
from src.data.loader import DataLoader
from src.engine.fee_models import FeeModel
from src.engine.position_sizer import PropFirmPositionSizer
from src.execution.simulator import ExecutionSimulator
from src.engine.portfolio_tracker import PortfolioAccountTracker, StrategySubAccount
from src.strategies.base import BaseStrategy
from src.analytics.metrics_engine import MetricsEngine
from src.validation.monte_carlo import PropFirmMonteCarloSimulator


class PortfolioRunner:
    """
    Simulates concurrent multi-strategy institutional futures portfolio execution.
    Enforces shared account equity, non-linear MTM trailing floor ratchets,
    and strictly single-ratchet intra-bar accounting across the aggregated portfolio.
    """

    def __init__(
        self,
        strategies: List[BaseStrategy],
        prop_firm_config: Dict[str, Any],
        execution_config: Dict[str, Any],
        instrument_config: Dict[str, Any],
        max_portfolio_contracts: int = 3
    ):
        self.strategies = strategies
        self.prop_firm_config = prop_firm_config
        self.execution_config = execution_config
        self.instrument_config = instrument_config
        self.max_portfolio_contracts = max_portfolio_contracts

        # Consolidated Master Account
        self.account = PortfolioAccountTracker.from_config(
            prop_firm_config,
            max_contracts=max_portfolio_contracts
        )

        # Per-strategy simulators & sizers
        self.simulators: Dict[str, ExecutionSimulator] = {}
        self.sizers: Dict[str, PropFirmPositionSizer] = {}

        equal_weight = 1.0 / len(strategies) if strategies else 1.0
        for strat in strategies:
            strat_name = getattr(strat, "config", {}).get("strategy_name", strat.__class__.__name__)
            self.account.register_strategy(strat_name, weight=equal_weight)
            self.simulators[strat_name] = ExecutionSimulator.from_config(execution_config, instrument_config)
            self.sizers[strat_name] = PropFirmPositionSizer.from_config(execution_config, prop_firm_config, instrument_config)

    @classmethod
    def from_config_files(
        cls,
        strategies: List[BaseStrategy],
        prop_firm_cfg_path: str = "configs/compliance/apex_50k_canonical.yaml",
        execution_cfg_path: str = "configs/execution/cme_globex_default.yaml",
        instrument_cfg_path: str = "configs/instruments/mnq.yaml",
        max_portfolio_contracts: int = 3
    ) -> "PortfolioRunner":
        with open(prop_firm_cfg_path, "r") as f:
            prop_cfg = yaml.safe_load(f)
        with open(execution_cfg_path, "r") as f:
            exec_cfg = yaml.safe_load(f)
        with open(instrument_cfg_path, "r") as f:
            inst_cfg = yaml.safe_load(f)

        # Standardize nested canonical config format if necessary
        normalized_prop_cfg = prop_cfg.copy()
        if "account" in prop_cfg:
            normalized_prop_cfg["initial_balance"] = prop_cfg["account"].get("starting_balance", 50000.0)
            normalized_prop_cfg["profit_target"] = prop_cfg["account"].get("target_profit", 3000.0)
            max_portfolio_contracts = prop_cfg["account"].get("contract_cap", max_portfolio_contracts)
        if "trailing_floor" in prop_cfg:
            normalized_prop_cfg["trailing_max_drawdown"] = prop_cfg["trailing_floor"].get("buffer_amount", 2500.0)
            normalized_prop_cfg["floor_lock_threshold"] = prop_cfg["trailing_floor"].get("lock_hwm_trigger", 52600.0) - normalized_prop_cfg.get("initial_balance", 50000.0)
            normalized_prop_cfg["lock_floor_offset"] = prop_cfg["trailing_floor"].get("locked_floor_level", 50100.0) - normalized_prop_cfg.get("initial_balance", 50000.0)
        if "session_circuit_breakers" in prop_cfg:
            normalized_prop_cfg["daily_loss_limit"] = prop_cfg["session_circuit_breakers"].get("daily_loss_limit", 1000.0)

        return cls(strategies, normalized_prop_cfg, exec_cfg, inst_cfg, max_portfolio_contracts)

    def run(self, loader: DataLoader) -> Dict[str, Any]:
        """
        Executes unified event-driven simulation loop across all registered strategies.
        Guarantees causal bar streaming and strictly single-ratchet intra-bar accounting.
        """
        bars_processed = 0

        for bar in loader.get_bars():
            bars_processed += 1

            # 1. Daily session rollover check on consolidated account
            self.account.check_new_day(bar.timestamp)

            # 2. Process active trades & pending orders across all strategy simulators
            # Note: skip_intra_bar_accounting=True ensures no sub-simulator double-ratchets
            total_unrealized_peak = 0.0
            total_unrealized_trough = 0.0
            total_unrealized_curr = 0.0

            for strat in self.strategies:
                s_name = getattr(strat, "config", {}).get("strategy_name", strat.__class__.__name__)
                sim = self.simulators[s_name]

                # Record pre-process trade count to detect closed trades
                pre_closed_count = len(sim.closed_trades)
                sim.process_bar(bar, self.account, skip_intra_bar_accounting=True)

                # If trade closed in this bar, record in sub-account and master account
                if len(sim.closed_trades) > pre_closed_count:
                    new_trade = sim.closed_trades[-1]
                    new_trade.strategy_name = s_name
                    self.account.record_sub_account_trade(s_name, new_trade)

                # Track active position state for concurrency
                if sim.active_trade is not None:
                    at = sim.active_trade
                    trade_side = at.get("side")
                    pos_info = {
                        "direction": trade_side,
                        "contracts": at.get("contracts", 0),
                        "entry_price": at.get("entry_price"),
                        "mfe_price": at.get("mfe_price"),
                        "mae_price": at.get("mae_price")
                    }
                    self.account.active_positions[s_name] = pos_info

                    # Aggregate intra-bar unrealized excursions
                    side_sign = 1.0 if trade_side == OrderSide.LONG else -1.0
                    pt_val = sim.point_value
                    qty = at.get("contracts", 1)

                    peak_pts = (bar.high - at["entry_price"]) * side_sign if side_sign > 0 else (at["entry_price"] - bar.low)
                    trough_pts = (bar.low - at["entry_price"]) * side_sign if side_sign > 0 else (at["entry_price"] - bar.high)
                    curr_pts = (bar.close - at["entry_price"]) * side_sign

                    total_unrealized_peak += max(0.0, peak_pts * pt_val * qty)
                    total_unrealized_trough += min(0.0, trough_pts * pt_val * qty)
                    total_unrealized_curr += (curr_pts * pt_val * qty)
                else:
                    self.account.active_positions.pop(s_name, None)

            # 3. Consolidated Peak-Unrealized MTM Trailing Floor Update (Executed STRICTLY ONCE per bar)
            self.account.update_intra_bar(total_unrealized_peak, total_unrealized_trough)
            self.account.record_equity_snapshot(bar.timestamp, total_unrealized_curr)

            # If master account breached, force-liquidate all open positions and halt
            if not self.account.is_active:
                for sim in self.simulators.values():
                    if sim.active_trade is not None:
                        sim._liquidate_active_trade(bar, "PORTFOLIO_FLOOR_BREACH")
                break

            # 4. Alpha Generation & Concurrency-Gated Position Sizing
            for strat in self.strategies:
                s_name = getattr(strat, "config", {}).get("strategy_name", strat.__class__.__name__)
                sim = self.simulators[s_name]
                sizer = self.sizers[s_name]

                # Strategy evaluates bar
                strat.check_session_boundary(bar)
                setup = strat.on_bar(bar)

                if setup is not None and sim.active_trade is None and not sim.pending_orders:
                    risk_points = abs(bar.close - setup.stop_loss)
                    cushion = self.account.cushion
                    target_lots = sizer.calculate_lots(cushion, risk_points)

                    open_contracts = sum(p.get("contracts", 0) for p in self.account.active_positions.values())
                    headroom = max(0, self.max_portfolio_contracts - open_contracts)
                    allocated_lots = min(target_lots, headroom)

                    if allocated_lots > 0:
                        can_open, reason = self.account.can_open_position(s_name, setup.direction, allocated_lots)
                        if can_open:
                            sim.submit_setup(setup, bar, allocated_lots)
                            self.account.active_positions[s_name] = {
                                "direction": setup.direction,
                                "contracts": allocated_lots
                            }

        # 5. Aggregate All Closed Trades Chronologically
        all_closed_trades: List[TradeRecord] = []
        for sim in self.simulators.values():
            all_closed_trades.extend(sim.closed_trades)

        all_closed_trades.sort(key=lambda t: t.exit_time)

        # 6. Compute Consolidated Metrics
        pt_val = float(self.instrument_config.get("point_value", 2.00))
        tick_sz = float(self.instrument_config.get("tick_size", 0.25))

        portfolio_metrics = MetricsEngine.compute_all(
            trades=all_closed_trades,
            account=self.account,
            point_value=pt_val,
            tick_size=tick_sz
        )

        portfolio_metrics["bars_processed"] = bars_processed
        portfolio_metrics["strategy_name"] = "portfolio_blended"
        portfolio_metrics["total_strategies"] = len(self.strategies)

        # 7. Compute Per-Strategy Independent Sub-Account Metrics
        sub_metrics = {}
        for s_name, sim in self.simulators.items():
            if sim.closed_trades:
                sub_metrics[s_name] = MetricsEngine.compute_all(
                    trades=sim.closed_trades,
                    account=self.account,
                    point_value=pt_val,
                    tick_size=tick_sz
                )
            else:
                sub_metrics[s_name] = {"summary": {"total_trades": 0, "total_net_pnl": 0.0}}

        portfolio_metrics["sub_strategies"] = sub_metrics

        # 8. Compute Diversification & Correlated Return Analytics
        portfolio_analytics = self._compute_portfolio_analytics(all_closed_trades)
        portfolio_metrics["portfolio_analytics"] = portfolio_analytics

        # 9. Monte Carlo Simulation on Combined Trade Flow
        mc_sim = PropFirmMonteCarloSimulator(
            initial_balance=float(self.prop_firm_config.get("initial_balance", 50000.0)),
            trailing_max_dd=float(self.prop_firm_config.get("trailing_max_drawdown", 2500.0)),
            profit_target=float(self.prop_firm_config.get("profit_target", 3000.0)),
            iterations=10000
        )
        mc_results = mc_sim.run(all_closed_trades)
        portfolio_metrics["monte_carlo"] = mc_results

        return portfolio_metrics

    def _compute_portfolio_analytics(self, all_trades: List[TradeRecord]) -> Dict[str, Any]:
        """Calculates correlation matrix, diversification ratio, and joint daily returns."""
        if not all_trades:
            return {
                "correlation_matrix": {},
                "diversification_ratio": 1.0,
                "strategy_trade_counts": {},
                "joint_sharpe": 0.0
            }

        trade_rows = []
        for t in all_trades:
            trade_rows.append({
                "date": t.exit_time.strftime("%Y-%m-%d"),
                "strategy": t.strategy_name,
                "net_pnl": t.net_pnl
            })

        df_trades = pd.DataFrame(trade_rows)
        pivot_daily = df_trades.pivot_table(
            index="date",
            columns="strategy",
            values="net_pnl",
            aggfunc="sum"
        ).fillna(0.0)

        corr_dict = {}
        div_ratio = 1.0
        strat_vols = {}

        if len(pivot_daily.columns) > 1 and len(pivot_daily) > 2:
            corr_mat = pivot_daily.corr()
            corr_dict = corr_mat.round(3).to_dict()

            col_weights = np.array([1.0 / len(pivot_daily.columns)] * len(pivot_daily.columns))
            daily_vols = pivot_daily.std().values
            weighted_vol_sum = np.sum(col_weights * daily_vols)

            combined_daily = pivot_daily.sum(axis=1)
            port_vol = combined_daily.std()

            if port_vol > 0:
                div_ratio = float(weighted_vol_sum / port_vol)

            for col in pivot_daily.columns:
                strat_vols[col] = round(float(pivot_daily[col].std()), 2)

        strat_counts = {t.strategy_name: 0 for t in all_trades}
        for t in all_trades:
            strat_counts[t.strategy_name] += 1

        return {
            "correlation_matrix": corr_dict,
            "diversification_ratio": round(div_ratio, 3),
            "strategy_trade_counts": strat_counts,
            "daily_volatility_by_strategy": strat_vols
        }
