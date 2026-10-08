"""
Institutional Regime Classification Engine for CME Equity Index Futures.
Tags historical and live intraday market data into rigorous econometric regimes:
1. Volatility Regimes: VIX/VXN Quintiles (Q1 ultra-low, Q2, Q3, Q4, Q5 panic) & Intraday Relative ATR.
2. Trend Regimes: STRONG_BULL, MODERATE_BULL, CHOP_RANGE, MODERATE_BEAR, STRONG_BEAR (EMA ribbon + ADX).
3. Liquidity Regimes: DEEP_LIQUIDITY, NORMAL, THIN_ILLIQUID, AUCTION_IMBALANCE (RVOL + volume profile).
4. Macro Catalyst Regimes: Cross-referenced with MacroCalendar.
"""
from typing import Dict, List, Optional, Tuple, Union
from enum import Enum
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from src.data.macro_calendar import MacroCalendar, CatalystType


class VolatilityRegime(str, Enum):
    Q1_ULTRA_LOW = "Q1_ULTRA_LOW"    # VIX < 14
    Q2_LOW = "Q2_LOW"                # 14 <= VIX < 18
    Q3_MODERATE = "Q3_MODERATE"      # 18 <= VIX < 24
    Q4_ELEVATED = "Q4_ELEVATED"      # 24 <= VIX < 32
    Q5_CRISIS = "Q5_CRISIS"          # VIX >= 32


class TrendRegime(str, Enum):
    STRONG_BULL = "STRONG_BULL"
    MODERATE_BULL = "MODERATE_BULL"
    CHOP_RANGE = "CHOP_RANGE"
    MODERATE_BEAR = "MODERATE_BEAR"
    STRONG_BEAR = "STRONG_BEAR"


class LiquidityRegime(str, Enum):
    DEEP = "DEEP"
    NORMAL = "NORMAL"
    THIN = "THIN"
    IMBALANCE = "IMBALANCE"


class RegimeTag(BaseModel):
    timestamp: str
    volatility_regime: VolatilityRegime
    vix_proxy: float
    trend_regime: TrendRegime
    adx_proxy: float
    liquidity_regime: LiquidityRegime
    rvol: float
    catalyst_type: CatalystType
    is_event_day: bool


class RegimeClassifier:
    """
    Computes multi-dimensional market regime tags for intraday futures data.
    """

    def __init__(self, macro_calendar: Optional[MacroCalendar] = None):
        self.calendar = macro_calendar or MacroCalendar()

    def classify_volatility(self, annualized_vol: float) -> VolatilityRegime:
        """Classify volatility into standard VIX/VXN quintiles."""
        if annualized_vol < 14.0:
            return VolatilityRegime.Q1_ULTRA_LOW
        elif annualized_vol < 18.0:
            return VolatilityRegime.Q2_LOW
        elif annualized_vol < 24.0:
            return VolatilityRegime.Q3_MODERATE
        elif annualized_vol < 32.0:
            return VolatilityRegime.Q4_ELEVATED
        else:
            return VolatilityRegime.Q5_CRISIS

    def classify_trend(self, slope_fast_slow: float, trend_strength: float) -> TrendRegime:
        """
        Classifies trend based on EMA separation slope and directional strength (ADX proxy).
        """
        if trend_strength < 20.0:
            return TrendRegime.CHOP_RANGE
        
        if slope_fast_slow > 0.15 and trend_strength >= 30.0:
            return TrendRegime.STRONG_BULL
        elif slope_fast_slow > 0.0:
            return TrendRegime.MODERATE_BULL
        elif slope_fast_slow < -0.15 and trend_strength >= 30.0:
            return TrendRegime.STRONG_BEAR
        elif slope_fast_slow < 0.0:
            return TrendRegime.MODERATE_BEAR
        else:
            return TrendRegime.CHOP_RANGE

    def classify_liquidity(self, rvol: float) -> LiquidityRegime:
        """Classifies liquidity based on Relative Volume (RVOL)."""
        if rvol >= 1.8:
            return LiquidityRegime.DEEP
        elif rvol >= 0.8:
            return LiquidityRegime.NORMAL
        elif rvol < 0.5:
            return LiquidityRegime.THIN
        else:
            return LiquidityRegime.IMBALANCE

    def tag_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Enriches an OHLCV DataFrame with regime tags:
        - vol_regime
        - trend_regime
        - liq_regime
        - macro_catalyst
        """
        result = df.copy()

        # Calculate Parkinson / Garman-Klass or Rolling Return Volatility proxy
        log_ret = np.log(result["close"] / result["close"].shift(1)).fillna(0)
        rolling_std = log_ret.rolling(window=20, min_periods=5).std().fillna(0.001)
        # Annualize assuming 5m bars (~75 bars/day, 252 days)
        ann_vol = rolling_std * np.sqrt(75 * 252) * 100.0
        result["vol_proxy"] = ann_vol

        # Trend Indicator: EMA20 vs EMA50
        ema20 = result["close"].ewm(span=20, adjust=False).mean()
        ema50 = result["close"].ewm(span=50, adjust=False).mean()
        slope = ((ema20 - ema50) / ema50) * 100.0

        # ADX Proxy: Directional absolute momentum
        high_low = result["high"] - result["low"]
        hl_smooth = high_low.rolling(14, min_periods=1).mean().replace(0, 0.25)
        mom = (result["close"] - result["close"].shift(14)).abs().fillna(0)
        adx_proxy = np.clip((mom / hl_smooth) * 25.0, 5.0, 75.0)

        # RVOL
        mean_vol = result["volume"].rolling(50, min_periods=5).mean().replace(0, 1)
        rvol = (result["volume"] / mean_vol).fillna(1.0)

        vol_regimes = []
        trend_regimes = []
        liq_regimes = []
        macro_catalysts = []
        is_event_days = []

        for idx, row in result.iterrows():
            # Vol
            v_reg = self.classify_volatility(ann_vol.loc[idx])
            vol_regimes.append(v_reg.value)

            # Trend
            t_reg = self.classify_trend(slope.loc[idx], adx_proxy.loc[idx])
            trend_regimes.append(t_reg.value)

            # Liquidity
            l_reg = self.classify_liquidity(rvol.loc[idx])
            liq_regimes.append(l_reg.value)

            # Macro calendar
            ts = pd.to_datetime(idx) if not isinstance(idx, pd.Timestamp) else idx
            cat = self.calendar.get_primary_catalyst(ts.date())
            macro_catalysts.append(cat.value)
            is_event_days.append(cat != CatalystType.NONE)

        result["vol_regime"] = vol_regimes
        result["trend_regime"] = trend_regimes
        result["liq_regime"] = liq_regimes
        result["macro_catalyst"] = macro_catalysts
        result["is_event_day"] = is_event_days

        return result
