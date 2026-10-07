"""
Dynamic Strategy Discovery and Registry for AlphaForge.
Auto-discovers and registers any strategy residing in its own dedicated folder.
"""
import importlib
import inspect
from pathlib import Path
from typing import Dict, Type
from src.strategies.base import BaseStrategy

STRATEGY_REGISTRY: Dict[str, Type[BaseStrategy]] = {}


def discover_strategies() -> Dict[str, Type[BaseStrategy]]:
    """
    Traverses subdirectories under src/strategies/, dynamically imports strategy modules,
    finds classes inheriting from BaseStrategy, and populates STRATEGY_REGISTRY.
    """
    global STRATEGY_REGISTRY
    STRATEGY_REGISTRY.clear()
    
    strategies_dir = Path(__file__).parent

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
                    print(f"Warning: Failed to load strategy from {child.name}: {e}")

    return STRATEGY_REGISTRY


# Auto-discover upon module import
discover_strategies()
