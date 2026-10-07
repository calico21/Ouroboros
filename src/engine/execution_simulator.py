"""
Execution Simulation Engine for CME Globex Futures.
Implements strict limit order trade-through verification (no fills on mere touches),
realistic slippage models, intra-bar MFE/MAE excursions, and fee deduction.
"""
from typing import Optional, List, Dict, Any, Tuple
import uuid
from src.core.events import BarEvent, TradeSetup, OrderEvent, FillEvent, TradeRecord
from src.core.enums import OrderSide, OrderType, OrderStatus, LossCategory, AccountStatus
from src.engine.fee_models import FeeModel
from src.engine.account_tracker import PropFirmAccountTracker


class ExecutionSimulator:
    """
    Simulates CME Globex matching engine behavior.
    Enforces passive queue execution rules and realistic market friction.
    """

    def __init__(
        self,
        fee_model: FeeModel,
        slippage_ticks: float = 1.0,
        limit_trade_through_ticks: float = 1.0,
        fill_on_touch: bool = False,
        point_value: float = 2.00,
        tick_size: float = 0.25
    ):
        self.fee_model = fee_model
        self.slippage_ticks = slippage_ticks
        self.limit_trade_through_ticks = limit_trade_through_ticks
        self.fill_on_touch = fill_on_touch
        self.point_value = point_value
        self.tick_size = tick_size

        # Order & Position State
        self.pending_orders: List[OrderEvent] = []
        self.active_trade: Optional[Dict[str, Any]] = None
        self.closed_trades: List[TradeRecord] = []

    @classmethod
    def from_config(cls, exec_cfg: Dict[str, Any], inst_cfg: Dict[str, Any]) -> "ExecutionSimulator":
        fee_model = FeeModel.from_config(inst_cfg)
        return cls(
            fee_model=fee_model,
            slippage_ticks=float(exec_cfg.get("slippage_ticks", 1.0)),
            limit_trade_through_ticks=float(exec_cfg.get("limit_trade_through_ticks", 1.0)),
            fill_on_touch=bool(exec_cfg.get("fill_on_touch", False)),
            point_value=float(inst_cfg.get("point_value", 2.00)),
            tick_size=float(inst_cfg.get("tick_size", 0.25))
        )

    def submit_setup(self, setup: TradeSetup, bar: BarEvent, contracts: int) -> Optional[OrderEvent]:
        """Convert strategy TradeSetup into an active/pending OrderEvent."""
        if contracts <= 0 or self.active_trade is not None:
            return None

        order = OrderEvent(
            order_id=str(uuid.uuid4())[:8],
            timestamp=bar.timestamp,
            symbol=bar.symbol,
            side=setup.direction,
            order_type=setup.order_type,
            quantity=contracts,
            stop_loss=setup.stop_loss,
            take_profit=setup.take_profit,
            limit_price=setup.limit_price,
            ttl_bars=setup.ttl_bars,
            tag=setup.tag,
            status=OrderStatus.PENDING
        )

        if setup.order_type == OrderType.MARKET:
            # Market order fills immediately on current close (or next open) + slippage
            self._fill_market_entry(order, bar)
            return None
        else:
            self.pending_orders.append(order)
            return order

    def _fill_market_entry(self, order: OrderEvent, bar: BarEvent) -> None:
        """Fill market order with slippage penalty and initialize active trade."""
        slippage_pts = self.slippage_ticks * self.tick_size
        if order.side == OrderSide.LONG:
            fill_price = bar.close + slippage_pts
        else:
            fill_price = bar.close - slippage_pts

        entry_commission = self.fee_model.calculate_commission(order.quantity)
        entry_slippage_cost = self.fee_model.calculate_slippage_cost(order.quantity, self.slippage_ticks)

        risk_r = abs(fill_price - order.stop_loss)
        if risk_r <= 0:
            risk_r = self.tick_size

        self.active_trade = {
            "trade_id": order.order_id,
            "symbol": bar.symbol,
            "tag": order.tag,
            "side": order.side,
            "contracts": order.quantity,
            "entry_time": bar.timestamp,
            "entry_price": fill_price,
            "stop_loss": order.stop_loss,
            "take_profit": order.take_profit,
            "risk_r_price": risk_r,
            "entry_commission": entry_commission,
            "entry_slippage_cost": entry_slippage_cost,
            "mfe_price": fill_price,
            "mae_price": fill_price,
            "time_to_peak_mfe": 0,
            "bars_held": 0,
            "entry_hour_est": bar.timestamp.hour,
            "day_of_week": bar.timestamp.strftime("%A"),
            "atr_quintile": 3 if bar.atr_14 is None else 3,  # Will be mapped in analytics
            "is_rth": bar.is_rth
        }

    def process_bar(self, bar: BarEvent, account: PropFirmAccountTracker) -> None:
        """
        Processes pending orders, manages active positions, checks strict trade-through,
        updates MTM excursions, and reports to account tracker.
        """
        # 1. Process Pending Limit Orders
        self._process_pending_limits(bar)

        # 2. If no active position, nothing further to track
        if self.active_trade is None:
            return

        trade = self.active_trade
        trade["bars_held"] += 1
        side = trade["side"]
        entry_price = trade["entry_price"]
        contracts = trade["contracts"]
        sl = trade["stop_loss"]
        tp = trade["take_profit"]

        # Track intra-bar excursion
        if side == OrderSide.LONG:
            bar_peak_price = bar.high
            bar_trough_price = bar.low
            unrealized_peak_pnl = (bar_peak_price - entry_price) * self.point_value * contracts
            unrealized_trough_pnl = (bar_trough_price - entry_price) * self.point_value * contracts

            if bar_peak_price > trade["mfe_price"]:
                trade["mfe_price"] = bar_peak_price
                trade["time_to_peak_mfe"] = trade["bars_held"]
            if bar_trough_price < trade["mae_price"]:
                trade["mae_price"] = bar_trough_price

        else: # SHORT
            bar_peak_price = bar.low    # lowest price is peak favorable for shorts
            bar_trough_price = bar.high # highest price is worst adverse for shorts
            unrealized_peak_pnl = (entry_price - bar_peak_price) * self.point_value * contracts
            unrealized_trough_pnl = (entry_price - bar_trough_price) * self.point_value * contracts

            if bar_peak_price < trade["mfe_price"]:
                trade["mfe_price"] = bar_peak_price
                trade["time_to_peak_mfe"] = trade["bars_held"]
            if bar_trough_price > trade["mae_price"]:
                trade["mae_price"] = bar_trough_price

        # 3. Update account tracker with intra-bar MTM peaks and troughs
        account.update_intra_bar(unrealized_peak_pnl, unrealized_trough_pnl)

        # 4. Check if account liquidation was triggered
        if not account.is_active:
            # Forced market liquidation at worst trough price + slippage
            slippage_pts = self.slippage_ticks * self.tick_size
            exit_price = (bar_trough_price - slippage_pts) if side == OrderSide.LONG else (bar_trough_price + slippage_pts)
            self._close_trade(bar, exit_price, "BREACH_LIQUIDATION", account)
            return

        # 5. Check Stop Loss and Take Profit fills
        self._evaluate_bracket_exits(bar, account)

    def _process_pending_limits(self, bar: BarEvent) -> None:
        """
        Evaluate pending limit orders.
        Requires STRICT TRADE-THROUGH: Price must exceed limit by >= 1 tick.
        A mere touch does NOT constitute execution.
        """
        still_pending = []
        for order in self.pending_orders:
            order.bars_active += 1

            if order.bars_active > order.ttl_bars:
                order.status = OrderStatus.EXPIRED
                continue

            trade_through = self.limit_trade_through_ticks * self.tick_size
            filled = False
            fill_price = order.limit_price

            if order.side == OrderSide.LONG:
                if self.fill_on_touch:
                    filled = bar.low <= order.limit_price
                else:
                    # STRICT TRADE-THROUGH: bar low must be strictly less than limit minus 1 tick
                    filled = bar.low <= (order.limit_price - trade_through)

            else: # SHORT
                if self.fill_on_touch:
                    filled = bar.high >= order.limit_price
                else:
                    # STRICT TRADE-THROUGH: bar high must be strictly greater than limit plus 1 tick
                    filled = bar.high >= (order.limit_price + trade_through)

            if filled and self.active_trade is None:
                order.status = OrderStatus.FILLED
                entry_commission = self.fee_model.calculate_commission(order.quantity)
                # Passive limit orders do not pay adverse slippage
                risk_r = abs(fill_price - order.stop_loss)
                if risk_r <= 0:
                    risk_r = self.tick_size

                self.active_trade = {
                    "trade_id": order.order_id,
                    "symbol": bar.symbol,
                    "tag": order.tag,
                    "side": order.side,
                    "contracts": order.quantity,
                    "entry_time": bar.timestamp,
                    "entry_price": fill_price,
                    "stop_loss": order.stop_loss,
                    "take_profit": order.take_profit,
                    "risk_r_price": risk_r,
                    "entry_commission": entry_commission,
                    "entry_slippage_cost": 0.0,
                    "mfe_price": fill_price,
                    "mae_price": fill_price,
                    "time_to_peak_mfe": 0,
                    "bars_held": 0,
                    "entry_hour_est": bar.timestamp.hour,
                    "day_of_week": bar.timestamp.strftime("%A"),
                    "atr_quintile": 3,
                    "is_rth": bar.is_rth
                }
            else:
                still_pending.append(order)

        self.pending_orders = still_pending

    def _evaluate_bracket_exits(self, bar: BarEvent, account: PropFirmAccountTracker) -> None:
        """
        Evaluates bracket exit conditions (SL / TP) within the current bar.
        Conservative model: In simultaneous trigger ambiguity, Stop Loss takes precedence.
        """
        trade = self.active_trade
        if trade is None:
            return

        side = trade["side"]
        sl = trade["stop_loss"]
        tp = trade["take_profit"]
        slippage_pts = self.slippage_ticks * self.tick_size

        if side == OrderSide.LONG:
            sl_hit = bar.low <= sl
            tp_hit = bar.high >= tp

            if sl_hit and tp_hit:
                # Worst-case assumption: SL hit first
                exit_price = sl - slippage_pts
                self._close_trade(bar, exit_price, "STOP_LOSS", account)
            elif sl_hit:
                exit_price = sl - slippage_pts
                self._close_trade(bar, exit_price, "STOP_LOSS", account)
            elif tp_hit:
                # Passive take profit limit exit
                exit_price = tp
                self._close_trade(bar, exit_price, "TAKE_PROFIT", account)

        else: # SHORT
            sl_hit = bar.high >= sl
            tp_hit = bar.low <= tp

            if sl_hit and tp_hit:
                # Worst-case assumption: SL hit first
                exit_price = sl + slippage_pts
                self._close_trade(bar, exit_price, "STOP_LOSS", account)
            elif sl_hit:
                exit_price = sl + slippage_pts
                self._close_trade(bar, exit_price, "STOP_LOSS", account)
            elif tp_hit:
                exit_price = tp
                self._close_trade(bar, exit_price, "TAKE_PROFIT", account)

    def _close_trade(
        self,
        bar: BarEvent,
        exit_price: float,
        exit_reason: str,
        account: PropFirmAccountTracker
    ) -> None:
        """Closes active trade, applies fees and slippage, and records post-mortem diagnostics."""
        trade = self.active_trade
        if trade is None:
            return

        side = trade["side"]
        contracts = trade["contracts"]
        entry_price = trade["entry_price"]
        risk_r = trade["risk_r_price"]

        exit_commission = self.fee_model.calculate_commission(contracts)
        exit_slippage_cost = (
            self.fee_model.calculate_slippage_cost(contracts, self.slippage_ticks)
            if "STOP" in exit_reason or "LIQUIDATION" in exit_reason else 0.0
        )

        total_commission = trade["entry_commission"] + exit_commission
        total_slippage = trade["entry_slippage_cost"] + exit_slippage_cost

        # Calculate PnL
        if side == OrderSide.LONG:
            gross_pnl = (exit_price - entry_price) * self.point_value * contracts
            pts_mfe = max(0.0, trade["mfe_price"] - entry_price)
            pts_mae = max(0.0, entry_price - trade["mae_price"])
            pnl_points = exit_price - entry_price
        else:
            gross_pnl = (entry_price - exit_price) * self.point_value * contracts
            pts_mfe = max(0.0, entry_price - trade["mfe_price"])
            pts_mae = max(0.0, trade["mae_price"] - entry_price)
            pnl_points = entry_price - exit_price

        net_pnl = gross_pnl - total_commission - total_slippage

        # Normalized R excursions
        mfe_r = pts_mfe / risk_r if risk_r > 0 else 0.0
        mae_r = pts_mae / risk_r if risk_r > 0 else 0.0
        r_multiple = pnl_points / risk_r if risk_r > 0 else 0.0

        # Excursion Realization Efficiency: (Exit - Entry) / (MFE - Entry)
        if pts_mfe > 0:
            excursion_efficiency = pnl_points / pts_mfe
        else:
            excursion_efficiency = 0.0

        # Algorithmic Death Tree (Loss Taxonomy)
        loss_cat = None
        if net_pnl <= 0:
            if trade["bars_held"] <= 6 and mfe_r < 0.35:
                loss_cat = LossCategory.IMMEDIATE_FLUSH
            elif mfe_r >= 0.80:
                loss_cat = LossCategory.TRAPPED_TRADE
            elif gross_pnl > 0 and net_pnl <= 0:
                loss_cat = LossCategory.FRICTION_DRAIN
            else:
                loss_cat = LossCategory.STRUCTURAL_INVALIDATION

        record = TradeRecord(
            trade_id=trade["trade_id"],
            symbol=trade["symbol"],
            strategy_name="",  # Populated by runner
            tag=trade["tag"],
            side=trade["side"],
            contracts=contracts,
            entry_time=trade["entry_time"],
            entry_price=entry_price,
            exit_time=bar.timestamp,
            exit_price=exit_price,
            exit_reason=exit_reason,
            initial_sl=trade["stop_loss"],
            initial_tp=trade["take_profit"],
            risk_r_price=risk_r,
            mfe_price=trade["mfe_price"],
            mae_price=trade["mae_price"],
            mfe_r=mfe_r,
            mae_r=mae_r,
            time_to_peak_mfe=trade["time_to_peak_mfe"],
            bars_held=trade["bars_held"],
            gross_pnl=gross_pnl,
            net_pnl=net_pnl,
            commissions=total_commission,
            slippage_paid=total_slippage,
            r_multiple=r_multiple,
            excursion_efficiency=excursion_efficiency,
            loss_category=loss_cat,
            entry_hour_est=trade["entry_hour_est"],
            day_of_week=trade["day_of_week"],
            atr_quintile=trade["atr_quintile"],
            is_rth=trade["is_rth"]
        )

        self.closed_trades.append(record)
        account.record_trade_realized(net_pnl)
        self.active_trade = None
