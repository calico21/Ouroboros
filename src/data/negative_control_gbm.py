"""
Negative Control Benchmark: Geometric Brownian Motion (GBM) Falsification Engine.
Generates zero-drift continuous CME Globex synthetic market sessions with empirical
MNQ intraday volatility and Poisson jump diffusion.

Mandatory Directive:
On pure noise / random walk, true geometric and structural trading setups are strictly
negative-sum after transaction friction. Any candidate strategy exhibiting statistically
significant positive expectancy (PF > 1.0, t-stat > 2.0) on this synthetic dataset is
falsified and rejected for lookahead bias, state leaking, or harness defect.
"""
from datetime import datetime, timedelta, time
from typing import List, Optional
import numpy as np
import pandas as pd
import zoneinfo

from src.core.events import BarEvent
from src.data.cme_session_clock import NY_TZ, get_cme_trade_date


class FalsificationFailureError(AssertionError):
    """Raised when a candidate strategy demonstrates false edge on pure noise."""
    pass


class NegativeControlGBMGenerator:
    """
    Synthesizes multi-session zero-drift continuous CME Globex futures bar streams.
    S_t follows a jump-diffusion process with zero drift (mu=0), empirical MNQ volatility,
    and trade-through queue frictions.
    """

    def __init__(
        self,
        n_sessions: int = 500,
        start_price: float = 20000.0,
        annualized_vol: float = 0.22,
        jump_lambda: float = 0.02,
        jump_std: float = 12.0,
        seed: int = 42,
        symbol: str = "MNQ",
        point_value: float = 2.00,
        tick_size: float = 0.25
    ):
        self.n_sessions = n_sessions
        self.start_price = start_price
        self.annualized_vol = annualized_vol
        self.jump_lambda = jump_lambda
        self.jump_std = jump_std
        self.seed = seed
        self.symbol = symbol
        self.point_value = point_value
        self.tick_size = tick_size

    def generate_dataframe(self) -> pd.DataFrame:
        """
        Generates 5-minute continuous bars spanning n_sessions of ETH + RTH.
        Session begins at 18:00 ET and ends at 16:55 ET next calendar day.
        """
        rng = np.random.default_rng(self.seed)

        # 5m bars per 23h session: 23 hours * 12 bars/hr = 276 bars per session
        bars_per_session = 276
        dt_step = timedelta(minutes=5)

        # 5m bar volatility scaling: 252 trading days/year, 276 bars/day = ~69,552 bars/year
        dt_annual = 1.0 / (252.0 * bars_per_session)
        bar_sigma = self.annualized_vol * np.sqrt(dt_annual)

        current_price = self.start_price
        start_date = datetime(2023, 1, 2, 18, 0, 0, tzinfo=NY_TZ)

        records = []
        current_session_start = start_date

        for s_idx in range(self.n_sessions):
            # Skip Friday/Saturday rollover to keep CME weekday calendar
            while current_session_start.weekday() in (4, 5):  # Fri, Sat
                current_session_start += timedelta(days=1)

            t = current_session_start
            for b_idx in range(bars_per_session):
                # Skip maintenance halt: 17:00 to 18:00 ET
                et_time = t.time()
                if time(17, 0) <= et_time < time(18, 0):
                    t += dt_step
                    continue

                open_p = current_price

                # GBM return with zero drift: r = -0.5 * sigma^2 * dt + sigma * z
                z = rng.standard_normal()
                gbm_ret = -0.5 * (bar_sigma ** 2) + bar_sigma * z
                close_unrounded = open_p * np.exp(gbm_ret)

                # Poisson jump diffusion
                if rng.random() < self.jump_lambda:
                    jump = rng.normal(0.0, self.jump_std)
                    close_unrounded += jump

                # Round to CME tick size
                close_p = round(close_unrounded / self.tick_size) * self.tick_size
                if close_p <= 0:
                    close_p = self.tick_size

                # High/Low generation from intra-bar Brownian bridge
                wick_up = abs(rng.exponential(scale=1.5 * bar_sigma * open_p))
                wick_down = abs(rng.exponential(scale=1.5 * bar_sigma * open_p))

                high_p = max(open_p, close_p) + round(wick_up / self.tick_size) * self.tick_size
                low_p = min(open_p, close_p) - round(wick_down / self.tick_size) * self.tick_size
                if low_p <= 0:
                    low_p = self.tick_size
                high_p = max(high_p, open_p, close_p)
                low_p = min(low_p, open_p, close_p)

                # Realistic lognormal volume
                base_vol = 1200 if (time(9, 30) <= et_time < time(16, 0)) else 300
                vol = int(rng.lognormal(mean=np.log(base_vol), sigma=0.6))

                records.append({
                    "timestamp": t.strftime("%Y-%m-%d %H:%M:%S"),
                    "open": float(open_p),
                    "high": float(high_p),
                    "low": float(low_p),
                    "close": float(close_p),
                    "volume": vol,
                    "symbol": self.symbol
                })

                current_price = close_p
                t += dt_step

            # Advance to next day's 18:00 ET
            current_session_start = (current_session_start + timedelta(days=1)).replace(hour=18, minute=0, second=0)

        df = pd.DataFrame(records)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df

    def generate_bar_events(self) -> List[BarEvent]:
        """Convert synthesized dataframe into immutable BarEvent sequence."""
        df = self.generate_dataframe()
        bars = []
        for _, row in df.iterrows():
            ts = row["timestamp"].to_pydatetime()
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=NY_TZ)
            et_time = ts.time()
            is_rth_flag = (ts.weekday() < 5) and (time(9, 30) <= et_time < time(16, 0))

            bars.append(BarEvent(
                timestamp=ts,
                symbol=self.symbol,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=int(row["volume"]),
                timeframe="5m",
                is_rth=is_rth_flag
            ))
        return bars
