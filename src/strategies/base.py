"""
BaseStrategy Interface for AlphaForge.
Enforces strict decoupling of alpha generation from execution and account mechanics.
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Dict, Any
import yaml

from src.core.events import BarEvent, TradeSetup
from src.data.cme_session_clock import get_cme_trade_date_str


class BaseStrategy(ABC):
    """
    Abstract Base Strategy Interface.
    Pure alpha generator: consuming immutable BarEvents and emitting abstract TradeSetups.
    Completely isolated and blind to capital, positions, and broker execution details.
    """

    def __init__(self, config_overrides: Optional[Dict[str, Any]] = None):
        self.config = self._load_local_config()
        strat_name = getattr(self, "STRATEGY_NAME", self.__class__.__name__)
        self.config.setdefault("strategy_name", strat_name)
        if config_overrides:
            self.config.update(config_overrides)
        self.current_session_id: Optional[str] = None

    def _load_local_config(self) -> Dict[str, Any]:
        """Auto-loads config.yaml located in the strategy's self-contained directory."""
        import inspect
        cls_file = Path(inspect.getfile(self.__class__))
        config_path = cls_file.parent / "config.yaml"
        if config_path.exists():
            with open(config_path, "r") as f:
                return yaml.safe_load(f) or {}
        return {}

    @abstractmethod
    def on_bar(self, bar: BarEvent) -> Optional[TradeSetup]:
        """
        Evaluate new incoming bar and emit abstract TradeSetup if conditions met.
        Called sequentially bar-by-bar.
        """
        pass

    @abstractmethod
    def reset_session(self) -> None:
        """
        Triggered at session boundaries (e.g. 09:30 EST) to clear daily session states,
        reset opening ranges, intraday indicators, etc.
        """
        pass

    def check_session_boundary(self, bar: BarEvent) -> None:
        """Helper to trigger reset_session() on CME Trade Date (18:00 ET rollover)."""
        trade_date = get_cme_trade_date_str(bar.timestamp)
        if self.current_session_id != trade_date:
            self.current_session_id = trade_date
            self.reset_session()
