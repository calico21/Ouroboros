"""
Position Sizing Engine with Indivisible 1-Lot Quantization & Cushion Clamping.
Prevents prop-firm trailing floor violations while guarding against volatility lockouts.
"""
from typing import Dict, Any


class PropFirmPositionSizer:
    """
    Sizes futures positions based on available cushion to the trailing floor.
    Ensures contract count is an integer >= 0, respecting risk budgets and rounding thresholds.
    """

    def __init__(
        self,
        risk_per_trade_pct: float = 0.05,       # Risk 5% of available cushion by default
        max_contracts: int = 10,
        rounding_tolerance_threshold: float = 0.75,
        buffer_risk_limit: float = 0.10,        # Max risk allowed as pct of buffer
        point_value: float = 2.00,
        commission_rt: float = 1.24
    ):
        self.risk_per_trade_pct = risk_per_trade_pct
        self.max_contracts = max_contracts
        self.rounding_tolerance_threshold = rounding_tolerance_threshold
        self.buffer_risk_limit = buffer_risk_limit
        self.point_value = point_value
        self.commission_rt = commission_rt

    @classmethod
    def from_config(cls, exec_cfg: Dict[str, Any], prop_cfg: Dict[str, Any], inst_cfg: Dict[str, Any]) -> "PropFirmPositionSizer":
        return cls(
            risk_per_trade_pct=float(exec_cfg.get("risk_per_trade_pct", 0.05)),
            max_contracts=int(prop_cfg.get("max_contracts", 10)),
            rounding_tolerance_threshold=float(exec_cfg.get("rounding_tolerance_threshold", 0.75)),
            buffer_risk_limit=float(exec_cfg.get("buffer_risk_limit", 0.10)),
            point_value=float(inst_cfg.get("point_value", 2.00)),
            commission_rt=float(inst_cfg.get("total_fee_per_side", 0.62)) * 2
        )

    def calculate_lots(self, cushion: float, stop_distance_points: float) -> int:
        """
        Calculate contract quantity given available cushion to floor and stop distance.
        """
        if cushion <= 0 or stop_distance_points <= 0:
            return 0

        # Risk for 1 contract in dollars: Points * Point_Value + Round-Turn Commission
        one_lot_risk = (stop_distance_points * self.point_value) + self.commission_rt
        if one_lot_risk <= 0:
            return 0

        # Hard guard: 1 contract risk must never exceed maximum allowed cushion percentage (e.g. 15% of cushion)
        if one_lot_risk > (cushion * 0.25):
            # Risk is too large for remaining account buffer
            return 0

        # Target dollar risk budget from cushion
        risk_budget = cushion * self.risk_per_trade_pct

        # Raw lot count
        raw_lots = risk_budget / one_lot_risk

        # Quantize to integer lots
        lots = int(raw_lots)

        if lots == 0:
            # Check Rounding Tolerance Threshold:
            # If the budget covers >= 75% of 1-lot risk and the 1-lot risk is <= 10% of total cushion,
            # allow 1 contract instead of suffering volatility-induced execution lockouts.
            budget_ratio = risk_budget / one_lot_risk
            cushion_risk_ratio = one_lot_risk / cushion
            if (budget_ratio >= self.rounding_tolerance_threshold and 
                cushion_risk_ratio <= self.buffer_risk_limit):
                lots = 1
            else:
                lots = 0

        return min(lots, self.max_contracts)
