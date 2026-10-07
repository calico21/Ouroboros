"""
Custom exception hierarchy for AlphaForge.
"""

class AlphaForgeError(Exception):
    """Base exception for all AlphaForge errors."""
    pass


class AccountBreachedError(AlphaForgeError):
    """Raised when peak MTM trailing floor or daily loss limit is breached."""
    def __init__(self, message: str, breach_type: str, floor: float, breached_at: float):
        super().__init__(message)
        self.breach_type = breach_type
        self.floor = floor
        self.breached_at = breached_at


class ExecutionError(AlphaForgeError):
    """Raised when order placement or matching fails."""
    pass


class DataValidationError(AlphaForgeError):
    """Raised when bar data fails integrity or schema checks."""
    pass


class StrategyError(AlphaForgeError):
    """Raised when strategy raises unhandled exception during signal generation."""
    pass
