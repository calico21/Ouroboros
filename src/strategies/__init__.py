"""
Dynamic Strategy Discovery and Registry for AlphaForge.
Auto-discovers and registers the 10 Institutional Blueprints across 5 Sleeves
as well as any custom strategies residing in dedicated folders.
"""
import importlib
import inspect
from pathlib import Path
from typing import Dict, Type
from src.strategies.base import BaseStrategy

# Import the 10 Institutional Blueprints from their sleeves
from src.strategies.sleeve_a_eth.macro_overshoot_fade import MacroOvershootFadeStrategy
from src.strategies.sleeve_a_eth.thin_eth_gap_failure import ThinEthGapFailureStrategy
from src.strategies.sleeve_b_compression.coil_expansion import CoilExpansionStrategy
from src.strategies.sleeve_b_compression.post_opex_gamma_release import PostOpexGammaReleaseStrategy
from src.strategies.sleeve_c_auction.ib_failed_extension_rotation import IbFailedExtensionRotationStrategy
from src.strategies.sleeve_c_auction.va_traverse_80pct import VaTraverse80PctStrategy
from src.strategies.sleeve_d_cash_close.letf_rebalance_continuation import LetfRebalanceContinuationStrategy
from src.strategies.sleeve_d_cash_close.moc_imbalance_response import MocImbalanceResponseStrategy
from src.strategies.sleeve_e_bounded_mr.midday_equilibrium_fade import MiddayEquilibriumFadeStrategy
from src.strategies.sleeve_e_bounded_mr.positive_gamma_pin_fade import PositiveGammaPinFadeStrategy

INSTITUTIONAL_BLUEPRINTS: Dict[str, Type[BaseStrategy]] = {
    "macro_overshoot_fade": MacroOvershootFadeStrategy,
    "thin_eth_gap_failure": ThinEthGapFailureStrategy,
    "coil_expansion": CoilExpansionStrategy,
    "post_opex_gamma_release": PostOpexGammaReleaseStrategy,
    "ib_failed_extension_rotation": IbFailedExtensionRotationStrategy,
    "va_traverse_80pct": VaTraverse80PctStrategy,
    "letf_rebalance_continuation": LetfRebalanceContinuationStrategy,
    "moc_imbalance_response": MocImbalanceResponseStrategy,
    "midday_equilibrium_fade": MiddayEquilibriumFadeStrategy,
    "positive_gamma_pin_fade": PositiveGammaPinFadeStrategy,
}

STRATEGY_REGISTRY: Dict[str, Type[BaseStrategy]] = {}


def discover_strategies() -> Dict[str, Type[BaseStrategy]]:
    """
    Traverses subdirectories under src/strategies/, dynamically imports strategy modules,
    populates STRATEGY_REGISTRY with institutional blueprints and discovered classes.
    """
    global STRATEGY_REGISTRY
    STRATEGY_REGISTRY.clear()
    
    # Pre-populate canonical 10 blueprints
    STRATEGY_REGISTRY.update(INSTITUTIONAL_BLUEPRINTS)

    strategies_dir = Path(__file__).parent

    # Traverse subdirectories for existing or custom strategies
    for child in strategies_dir.iterdir():
        if child.is_dir() and not child.name.startswith("__") and not child.name.startswith("."):
            strategy_file = child / "strategy.py"
            if strategy_file.exists():
                module_name = f"src.strategies.{child.name}.strategy"
                try:
                    module = importlib.import_module(module_name)
                    for _, cls in inspect.getmembers(module, inspect.isclass):
                        if issubclass(cls, BaseStrategy) and cls is not BaseStrategy:
                            STRATEGY_REGISTRY[child.name] = cls
                            break
                except Exception as e:
                    # Ignore optional dependencies during discovery
                    pass

    return STRATEGY_REGISTRY


# Auto-discover upon module import
discover_strategies()
