"""
Unit test suite for ApexSprintChampionStrategy.
"""
from datetime import datetime, time
import pytest
import pytz

from src.core.events import BarEvent, TradeSetup
from src.core.enums import OrderSide, OrderType
from strategies.apex_sprint_champion import ApexSprintChampionStrategy, ChampionExecutionParameters


def test_instantiation_and_config():
    strat = ApexSprintChampionStrategy()
    assert strat.params.symbol == "MNQ"
    assert strat.params.stop_loss_pts == 20.0
    assert strat.params.take_profit_pts == 48.0
    assert strat.params.base_contracts == 5
    assert strat.params.ratchet_contracts == 8


def test_on_bar_execution():
    strat = ApexSprintChampionStrategy()
    ny_tz = pytz.timezone("America/New_York")

    # Feed bars for Day 1 to establish prior levels
    for m in range(0, 390, 5):
        h = 9 + m // 60
        mins = m % 60
        ts = ny_tz.localize(datetime(2025, 1, 6, h, mins))
        bar = BarEvent(
            timestamp=ts,
            open=20000.0,
            high=20100.0,
            low=19950.0,
            close=20050.0,
            volume=500.0,
            symbol="MNQ",
            atr_14=18.0
        )
        strat.on_bar(bar)

    assert strat.prev_day_high is not None
    assert strat.prev_day_low is not None
    assert strat.prev_vah is not None
    assert strat.prev_val is not None

    # Day 2: Test open outside VAH and reject back inside below VWAP
    ts_open = ny_tz.localize(datetime(2025, 1, 7, 9, 30))
    bar_open = BarEvent(
        timestamp=ts_open,
        open=20200.0,  # Opened above VAH
        high=20210.0,
        low=20150.0,
        close=20180.0,
        volume=600.0,
        symbol="MNQ",
        atr_14=18.0
    )
    res_open = strat.on_bar(bar_open)

    # Next bar: Re-enters below VAH and below VWAP
    ts_reenter = ny_tz.localize(datetime(2025, 1, 7, 9, 35))
    bar_reenter = BarEvent(
        timestamp=ts_reenter,
        open=20180.0,
        high=20185.0,
        low=20000.0,
        close=20010.0,  # Below VAH and below VWAP
        volume=800.0,
        symbol="MNQ",
        atr_14=18.0
    )
    res_signal = strat.on_bar(bar_reenter)
    assert res_signal is not None
    assert isinstance(res_signal, TradeSetup)
    assert res_signal.direction == OrderSide.SHORT
    assert res_signal.stop_loss == 20010.0 + 20.0
    assert res_signal.take_profit == 20010.0 - 48.0


def test_dynamic_kelly_position_sizing():
    strat = ApexSprintChampionStrategy()

    # 1. Base phase ($50,000 equity, floor $47,500 -> D_t = 2,500)
    strat.account_equity = 50000.0
    strat.high_water_mark = 50000.0
    strat.trailing_floor = 47500.0
    assert strat.compute_position_size(is_smt_confirmed=False) == 5
    assert strat.compute_position_size(is_smt_confirmed=True) == 6

    # 2. Traction phase (equity $50,800 -> profit $800, D_t = 2,500)
    strat.account_equity = 50800.0
    strat.high_water_mark = 50800.0
    strat.trailing_floor = 48300.0
    assert strat.compute_position_size(is_smt_confirmed=False) == 7
    assert strat.compute_position_size(is_smt_confirmed=True) == 8

    # 3. Expansion phase (equity $51,600 -> profit $1,600, D_t = 2,500)
    strat.account_equity = 51600.0
    strat.high_water_mark = 51600.0
    strat.trailing_floor = 49100.0
    assert strat.compute_position_size(is_smt_confirmed=False) == 8
    assert strat.compute_position_size(is_smt_confirmed=True) == 9

    # 4. Frozen floor phase (HWM >= $52,600 -> trailing floor locked at $50,100)
    strat.account_equity = 52700.0
    strat.high_water_mark = 52700.0
    strat.trailing_floor = 50100.0
    assert strat.compute_position_size() == 10

    # 5. Defensive clamp in drawdown (D_t < $1,750)
    strat.account_equity = 48800.0
    strat.high_water_mark = 50000.0
    strat.trailing_floor = 47500.0  # D_t = 1,300
    assert strat.compute_position_size() == 4


def test_adaptive_atr_targets():
    strat = ApexSprintChampionStrategy(config_overrides={"use_adaptive_atr": True})
    ny_tz = pytz.timezone("America/New_York")

    # Day 1: Establish prior levels
    for m in range(0, 390, 5):
        h = 9 + m // 60
        mins = m % 60
        ts = ny_tz.localize(datetime(2025, 1, 6, h, mins))
        bar = BarEvent(
            timestamp=ts, open=20000.0, high=20100.0, low=19950.0,
            close=20050.0, volume=500.0, symbol="MNQ", atr_14=20.0
        )
        strat.on_bar(bar)

    # Day 2: Signal bar with ATR = 20.0 (SL should be 20.0, TP should be min(55, 2.4 * 20) = 48.0)
    ts_open = ny_tz.localize(datetime(2025, 1, 7, 9, 30))
    strat.on_bar(BarEvent(
        timestamp=ts_open, open=20200.0, high=20210.0, low=20150.0,
        close=20180.0, volume=600.0, symbol="MNQ", atr_14=20.0
    ))
    ts_sig = ny_tz.localize(datetime(2025, 1, 7, 9, 35))
    res = strat.on_bar(BarEvent(
        timestamp=ts_sig, open=20180.0, high=20185.0, low=20000.0,
        close=20010.0, volume=800.0, symbol="MNQ", atr_14=20.0
    ))
    assert res is not None
    # SL = min(24.0, max(16.0, 1.0 * 20.0)) = 20.0
    # TP = min(55.0, max(36.0, 2.4 * 20.0)) = 48.0
    assert res.stop_loss == 20010.0 + 20.0
    assert res.take_profit == 20010.0 - 48.0


def test_bang_bang_maximizer_position_sizing():
    config = {
        "sizing_model": "BANG_BANG_MAXIMIZER",
        "base_contracts": 7,
        "max_contracts": 10,
        "floor_clamp_buffer": 1400.0,
        "floor_clamp_contracts": 4,
        "endgame_sprint_sessions": 7,
        "endgame_sprint_contracts": 10,
        "smt_conviction_boost": True
    }
    strat = ApexSprintChampionStrategy(config_overrides=config)

    # 1. Base initial stride (D_t = 2500, k = 15, profit = 0)
    strat.account_equity = 50000.0
    strat.high_water_mark = 50000.0
    strat.trailing_floor = 47500.0
    strat.sessions_remaining = 15
    assert strat.compute_position_size(is_smt_confirmed=False) == 7

    # 2. SMT Conviction Boost -> 10 contracts
    assert strat.compute_position_size(is_smt_confirmed=True) == 10

    # 3. Defensive floor clamp in drawdown (D_t = 1200 < 1400) -> 4 contracts
    strat.account_equity = 48700.0
    strat.trailing_floor = 47500.0
    strat.high_water_mark = 50000.0
    assert strat.compute_position_size(is_smt_confirmed=False) == 4
    # Defensive guard strictly overrides SMT boost
    assert strat.compute_position_size(is_smt_confirmed=True) == 4

    # 4. Locked Floor Sprint (HWM >= 52600 or profit >= 1800) -> 10 contracts
    strat.account_equity = 51900.0  # profit = 1900
    strat.high_water_mark = 51900.0
    strat.trailing_floor = 49400.0  # D_t = 2500
    assert strat.compute_position_size(is_smt_confirmed=False) == 10

    # 5. Endgame Escalation (k <= 7 sessions remaining and profit < 2000) -> 10 contracts
    strat.account_equity = 50500.0  # profit = 500
    strat.high_water_mark = 50500.0
    strat.trailing_floor = 48000.0  # D_t = 2500
    strat.sessions_remaining = 6
    assert strat.compute_position_size(is_smt_confirmed=False) == 10


def test_pure_pass_frontier_position_sizing():
    config = {
        "sizing_model": "PURE_PASS_FRONTIER",
        "base_contracts": 7,
        "max_contracts": 10,
        "floor_clamp_buffer": 1400.0,
        "floor_clamp_contracts": 4,
        "endgame_sprint_sessions": 7,
        "endgame_sprint_contracts": 10,
        "smt_conviction_boost": True
    }
    strat = ApexSprintChampionStrategy(config_overrides=config)

    # Initial Stride: 7 MNQ
    strat.account_equity = 50000.0
    strat.trailing_floor = 47500.0
    strat.sessions_remaining = 15
    assert strat.compute_position_size(is_smt_confirmed=False) == 7

    # SMT Conviction: 10 MNQ
    assert strat.compute_position_size(is_smt_confirmed=True) == 10

    # Traction Acceleration (profit >= 900): 8 MNQ
    strat.account_equity = 51000.0
    assert strat.compute_position_size(is_smt_confirmed=False) == 8

    # Floor Freeze Sprint: 10 MNQ
    strat.high_water_mark = 52700.0
    assert strat.compute_position_size(is_smt_confirmed=False) == 10


def test_dp_v1_adaptive_position_sizing():
    config = {
        "sizing_model": "DP_V1_ADAPTIVE",
        "base_contracts": 7,
        "max_contracts": 10,
        "smt_conviction_boost": True
    }
    strat = ApexSprintChampionStrategy(config_overrides=config)

    # 1. Base Initial Stride: 7 MNQ
    strat.account_equity = 50000.0
    strat.high_water_mark = 50000.0
    strat.trailing_floor = 47500.0
    strat.sessions_remaining = 15
    assert strat.compute_position_size(is_smt_confirmed=False) == 7

    # 2. SMT Conviction: 10 MNQ
    assert strat.compute_position_size(is_smt_confirmed=True) == 10

    # 3. Traction Acceleration (profit >= 600): 8 MNQ
    strat.account_equity = 50700.0
    strat.trailing_floor = 48200.0
    assert strat.compute_position_size(is_smt_confirmed=False) == 8

    # 4. Multi-tier Defensive Clamp Tier 1 (1200 <= D_t < 1500): 5 MNQ
    strat.account_equity = 49000.0
    strat.trailing_floor = 47600.0  # D_t = 1,400
    assert strat.compute_position_size(is_smt_confirmed=False) == 5

    # 5. Multi-tier Defensive Clamp Tier 2 (D_t < 1200): 3 MNQ
    strat.account_equity = 48600.0
    strat.trailing_floor = 47600.0  # D_t = 1,000
    assert strat.compute_position_size(is_smt_confirmed=False) == 3

    # 6. Locked Floor Sprint: 10 MNQ
    strat.account_equity = 52700.0
    strat.high_water_mark = 52700.0
    strat.trailing_floor = 50100.0
    assert strat.compute_position_size(is_smt_confirmed=False) == 10

    # 7. Endgame Escalation (k <= 5, gap > 800): 10 MNQ
    strat.account_equity = 50500.0
    strat.high_water_mark = 50500.0
    strat.trailing_floor = 48000.0
    strat.sessions_remaining = 4
    assert strat.compute_position_size(is_smt_confirmed=False) == 10


def test_live_config_and_apex_rules():
    from live.config import (
        APEX_RULES,
        PRIMARY_ASSET,
        REFERENCE_ASSET,
        STRATEGY_MODEL,
        MAX_TRADES_PER_DAY,
        HARD_HALT_ON_LOSS,
        STOP_LOSS_MNQ_PTS,
        TAKE_PROFIT_MNQ_PTS
    )
    assert APEX_RULES["starting_balance"] == 50000.0
    assert APEX_RULES["initial_floor"] == 48000.0
    assert APEX_RULES["lock_hwm"] == 52600.0
    assert APEX_RULES["lock_floor"] == 50100.0
    assert APEX_RULES["buffer"] == 2500.0
    assert STRATEGY_MODEL == "DP_V1_ADAPTIVE"
    assert MAX_TRADES_PER_DAY == 3
    assert HARD_HALT_ON_LOSS is True
    assert STOP_LOSS_MNQ_PTS == 20.0
    assert TAKE_PROFIT_MNQ_PTS == 48.0


def test_live_state_manager_ratchet_and_freeze(tmp_path):
    from live.state_manager import StateManager
    state_file = tmp_path / "account_state.json"
    journal_file = tmp_path / "journal.csv"

    sm = StateManager(state_file=state_file, journal_file=journal_file)
    assert sm.state["balance"] == 50000.0
    assert sm.state["floor"] == 48000.0
    assert sm.get_cushion() == 2000.0
    assert sm.state["frozen"] is False

    # DP_V1_ADAPTIVE Initial stride
    assert sm.compute_position_size(is_smt_confirmed=False) == 7
    assert sm.compute_position_size(is_smt_confirmed=True) == 10

    # Winning trade taking account to $52,700 -> HWM >= $52,600 freezes floor at $50,100
    res = sm.update_on_trade_close(
        sym="MNQ",
        net_pnl=2700.0,
        mfe_usd=2800.0,
        exit_price=20048.0,
        reason="TAKE_PROFIT",
        trade_data={"side": "BUY", "entry": 20000.0, "time": "10:00", "ctos": 10}
    )
    assert res["balance"] == 52700.0
    assert res["floor"] == 50100.0
    assert res["frozen"] is True
    assert sm.compute_position_size() == 10

    # Defensive clamps in drawdown
    sm.state["balance"] = 49000.0
    sm.state["floor"] = 47600.0  # D_t = 1,400 -> Clamp 5
    sm.state["frozen"] = False
    sm.state["hwm"] = 50000.0
    assert sm.compute_position_size(is_smt_confirmed=False) == 5

    sm.state["balance"] = 48600.0
    sm.state["floor"] = 47600.0  # D_t = 1,000 -> Clamp 3
    assert sm.compute_position_size(is_smt_confirmed=False) == 3


def test_live_auction_engine_dalton_profiles_and_regimes():
    from live.auction_engine import AuctionEngine
    import pandas as pd
    import numpy as np

    engine = AuctionEngine()
    ny_tz = pytz.timezone("America/New_York")

    # Generate synthetic 2-day 5m bars for primary (QQQ) and ref (SPY)
    dates = [datetime(2025, 1, 6), datetime(2025, 1, 7)]
    rows_p = []
    rows_r = []

    for d in dates:
        for m in range(0, 390, 5):
            h = 9 + m // 60
            mins = m % 60
            if (h == 9 and mins < 30) or h >= 16:
                continue
            ts = ny_tz.localize(datetime(d.year, d.month, d.day, h, mins))
            # Primary: Base 500
            rows_p.append({
                "timestamp": ts, "open": 500.0, "high": 505.0, "low": 495.0, "close": 502.0, "volume": 1000.0
            })
            # Ref: Base 600
            rows_r.append({
                "timestamp": ts, "open": 600.0, "high": 604.0, "low": 596.0, "close": 601.0, "volume": 1500.0
            })

    df_p = pd.DataFrame(rows_p)
    df_r = pd.DataFrame(rows_r)

    profiles = engine.compute_prior_day_profiles(df_p, df_r)
    assert profiles["pdh_primary"] == 505.0
    assert profiles["pdl_primary"] == 495.0
    assert not np.isnan(profiles["vah_primary"])
    assert not np.isnan(profiles["val_primary"])
    assert profiles["pdh_ref"] == 604.0
    assert profiles["pdl_ref"] == 596.0

    # Test balanced regime evaluation with Dalton VA traverse
    vwap, up_b, dn_b = engine.compute_vwap_bands(df_p.iloc[-30:])
    regime = engine.detect_regime(df_p.iloc[-30:], vwap, up_b, dn_b, atr14=2.0)
    assert regime in ("BALANCED", "TREND")





