"""
Exchange and Broker Fee Models for CME Globex Futures.
Models per-side commissions, clearing, and regulatory fees.
"""
from typing import Dict, Any


class FeeModel:
    """Calculates exchange, clearing, and broker execution fees."""

    def __init__(self, commission_per_side: float = 0.62, tick_value: float = 0.50, tick_size: float = 0.25):
        self.commission_per_side = commission_per_side
        self.tick_value = tick_value
        self.tick_size = tick_size

    @classmethod
    def from_config(cls, instrument_cfg: Dict[str, Any]) -> "FeeModel":
        commission = instrument_cfg.get("total_fee_per_side", instrument_cfg.get("commission_per_side", 0.62))
        tick_val = instrument_cfg.get("tick_value", 0.50)
        tick_sz = instrument_cfg.get("tick_size", 0.25)
        return cls(commission_per_side=commission, tick_value=tick_val, tick_size=tick_sz)

    def calculate_commission(self, contracts: int) -> float:
        """Returns commission for one side of execution."""
        return self.commission_per_side * contracts

    def calculate_slippage_cost(self, contracts: int, slippage_ticks: float) -> float:
        """Translates slippage ticks into dollar friction cost."""
        return slippage_ticks * self.tick_value * contracts
