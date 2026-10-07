"""
The Algorithmic "Death Tree": Loss Taxonomy Engine.
Dissects losing trades into mutually exclusive diagnostic failure modes.
"""
from typing import List, Dict, Any
from collections import Counter
from src.core.events import TradeRecord
from src.core.enums import LossCategory


class LossTaxonomyEngine:
    """
    Categorizes all losing trades into distinct forensic buckets:
    1. Immediate Flush: Exits at SL within 6 bars with MFE_R < 0.35 (bad timing / adverse auction).
    2. Trapped Trade: Reached MFE_R >= 0.80 before collapsing to loss/scratch (unrealized round-trip).
    3. Friction Drain: Gross PnL > 0, Net PnL <= 0 due to fees/slippage (stops too narrow).
    4. Structural Invalidation: Standard orderly stop-loss violation.
    """

    @staticmethod
    def classify(trade: TradeRecord) -> LossCategory:
        if trade.net_pnl > 0:
            return None  # Winning trade

        # 1. Immediate Flush
        if trade.bars_held <= 6 and trade.mfe_r < 0.35:
            return LossCategory.IMMEDIATE_FLUSH

        # 2. Trapped Trade
        if trade.mfe_r >= 0.80:
            return LossCategory.TRAPPED_TRADE

        # 3. Friction Drain
        if trade.gross_pnl > 0 and trade.net_pnl <= 0:
            return LossCategory.FRICTION_DRAIN

        # 4. Structural Invalidation
        return LossCategory.STRUCTURAL_INVALIDATION

    @classmethod
    def analyze_losses(cls, trades: List[TradeRecord]) -> Dict[str, Any]:
        losing_trades = [t for t in trades if t.net_pnl <= 0]
        total_losses = len(losing_trades)

        if total_losses == 0:
            return {
                "total_losses": 0,
                "breakdown": {},
                "summary": "Zero losing trades recorded."
            }

        counts = Counter()
        dollar_impact = Counter()

        for t in losing_trades:
            category = t.loss_category or cls.classify(t)
            cat_name = category.value if hasattr(category, "value") else str(category)
            counts[cat_name] += 1
            dollar_impact[cat_name] += abs(t.net_pnl)

        breakdown = {}
        for cat in [c.value for c in LossCategory]:
            cnt = counts.get(cat, 0)
            pct = (cnt / total_losses * 100.0) if total_losses > 0 else 0.0
            dollars = dollar_impact.get(cat, 0.0)
            breakdown[cat] = {
                "count": cnt,
                "percentage": round(pct, 1),
                "total_loss_dollars": round(dollars, 2),
                "avg_loss_dollars": round(dollars / cnt, 2) if cnt > 0 else 0.0
            }

        return {
            "total_losses": total_losses,
            "breakdown": breakdown
        }
