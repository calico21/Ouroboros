# scripts/run_vcr_orb_backtest.py
"""
AlphaForge Institutional Engine: 15-Minute Volatility-Compressed ORB (VCR-ORB)
Evaluación empírica determinista sobre datos continuos de MNQ (2022-2026).
"""

from pathlib import Path
import numpy as np
import pandas as pd


class MNQEconometricORBEngine:
    def __init__(
        self,
        df: pd.DataFrame,
        starting_balance: float = 50000.0,
        trailing_buffer: float = 2500.0,
        profit_hurdle: float = 3000.0,
        min_risk_pts: float = 20.0,
        max_risk_pts: float = 37.5,
        target_r_mult: float = 1.75,
        commission_rt: float = 1.24,
        slippage_ticks: float = 1.0,
        tick_size: float = 0.25,
        point_value: float = 2.0,
        vcr_threshold: float = 0.70,
        rvol_threshold: float = 1.30,
        min_or_width: float = 15.0,
        max_or_width: float = 50.0,
    ):
        self.df = df.copy()
        self.starting_balance = starting_balance
        self.trailing_buffer = trailing_buffer
        self.profit_hurdle = profit_hurdle
        self.min_risk_pts = min_risk_pts
        self.max_risk_pts = max_risk_pts
        self.target_r_mult = target_r_mult
        self.commission_rt = commission_rt
        self.slippage_pts = slippage_ticks * tick_size
        self.point_value = point_value
        self.vcr_threshold = vcr_threshold
        self.rvol_threshold = rvol_threshold
        self.min_or_width = min_or_width
        self.max_or_width = max_or_width

        self.prepared_df = None
        self.trade_log = None
        self.performance_summary = None

    def prepare_indicators(self) -> pd.DataFrame:
        df = self.df.copy()

        # Normalizar DatetimeIndex en America/New_York
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df.set_index("timestamp", inplace=True)
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)

        if df.index.tz is None:
            df.index = df.index.tz_localize("America/New_York")
        else:
            df.index = df.index.tz_convert("America/New_York")

        df = df.sort_index()
        df["date"] = df.index.date
        df["hour_min"] = df.index.strftime("%H:%M")

        # 1. Daily ATR (14 periodos) desfasado estrictamente 1 sesión
        daily = df.groupby("date").agg(
            d_high=("high", "max"),
            d_low=("low", "min"),
            d_close=("close", "last"),
        )
        daily["prev_close"] = daily["d_close"].shift(1)
        daily["tr"] = np.maximum(
            daily["d_high"] - daily["d_low"],
            np.maximum(
                (daily["d_high"] - daily["prev_close"]).abs(),
                (daily["d_low"] - daily["prev_close"]).abs(),
            ),
        )
        daily["atr14"] = daily["tr"].rolling(14, min_periods=1).mean().shift(1)
        daily["atr14"] = daily["atr14"].bfill()
        df["daily_atr14"] = df["date"].map(daily["atr14"])

        # 2. Rango ETH (18:00 T-1 a 09:25 T) con mapeo robusto a la sesión RTH
        dates_unique = sorted(df["date"].unique())
        date_to_idx = {d: idx for idx, d in enumerate(dates_unique)}

        def get_session_date(row_date, hm):
            idx = date_to_idx[row_date]
            if hm >= "18:00":
                return (
                    dates_unique[idx + 1]
                    if idx + 1 < len(dates_unique)
                    else row_date
                )
            return row_date

        df["session_date"] = [
            get_session_date(d, hm)
            for d, hm in zip(df["date"], df["hour_min"])
        ]

        is_eth = (df["hour_min"] >= "18:00") | (df["hour_min"] < "09:30")
        eth_agg = (
            df[is_eth]
            .groupby("session_date")
            .agg(eth_high=("high", "max"), eth_low=("low", "min"))
        )
        eth_agg["eth_range"] = eth_agg["eth_high"] - eth_agg["eth_low"]

        df["eth_range"] = df["session_date"].map(eth_agg["eth_range"])
        df["eth_range"] = df["eth_range"].fillna(df["daily_atr14"] * 0.5)
        df["vcr"] = df["eth_range"] / df["daily_atr14"]

        # 3. Opening Range de 15 minutos (barras 09:30, 09:35, 09:40)
        is_or_bar = df["hour_min"].isin(["09:30", "09:35", "09:40"])
        or_agg = (
            df[is_or_bar]
            .groupby("date")
            .agg(or_high=("high", "max"), or_low=("low", "min"))
        )
        or_agg["or_width"] = or_agg["or_high"] - or_agg["or_low"]
        or_agg["or_mid"] = (or_agg["or_high"] + or_agg["or_low"]) / 2.0

        df["or_high"] = df["date"].map(or_agg["or_high"])
        df["or_low"] = df["date"].map(or_agg["or_low"])
        df["or_width"] = df["date"].map(or_agg["or_width"])
        df["or_mid"] = df["date"].map(or_agg["or_mid"])

        # 4. VWAP intradiario acumulado desde 09:30 ET
        is_rth = (df["hour_min"] >= "09:30") & (df["hour_min"] <= "16:00")
        df["tp"] = (df["high"] + df["low"] + df["close"]) / 3.0
        df["tp_vol"] = df["tp"] * df["volume"]

        rth_df = df[is_rth].copy()
        rth_df["cum_tp_vol"] = rth_df.groupby("date")["tp_vol"].cumsum()
        rth_df["cum_vol"] = rth_df.groupby("date")["volume"].cumsum()
        df["vwap"] = rth_df["cum_tp_vol"] / rth_df["cum_vol"]
        df["vwap"] = df.groupby("date")["vwap"].ffill()

        # 5. RVOL sobre media móvil de 20 barras de 5m con lag de 1 barra
        df["vol_sma20"] = (
            df["volume"].rolling(window=20, min_periods=5).mean().shift(1)
        )
        df["rvol"] = df["volume"] / df["vol_sma20"]

        self.prepared_df = df
        return df

    def run_backtest(self) -> pd.DataFrame:
        if self.prepared_df is None:
            self.prepare_indicators()

        df = self.prepared_df

        balance = self.starting_balance
        peak_equity = self.starting_balance
        floor = self.starting_balance - self.trailing_buffer

        active_position = 0  # 1: Long, -1: Short, 0: Flat
        entry_price = 0.0
        stop_price = 0.0
        target_price = 0.0
        stop_distance = 0.0
        be_triggered = False

        current_trade_mae = 0.0
        current_trade_mfe = 0.0
        entry_time = None
        current_trade_date = None

        trades = []
        equity_series = []
        floor_series = []
        cushion_series = []

        dates = df["date"].values
        hour_mins = df["hour_min"].values
        opens = df["open"].values
        highs = df["high"].values
        lows = df["low"].values
        closes = df["close"].values
        vwaps = df["vwap"].values
        rvols = df["rvol"].values
        vcrs = df["vcr"].values
        or_highs = df["or_high"].values
        or_lows = df["or_low"].values
        or_mids = df["or_mid"].values
        or_widths = df["or_width"].values
        timestamps = df.index

        n_bars = len(df)
        traded_today = False
        prev_date = None

        for i in range(n_bars):
            curr_date = dates[i]
            curr_time = hour_mins[i]
            o, h, l, c = opens[i], highs[i], lows[i], closes[i]

            if curr_date != prev_date:
                traded_today = False
                prev_date = curr_date

            # GESTIÓN DE POSICIÓN ACTIVA
            if active_position != 0:
                trade_closed = False
                exit_price = 0.0
                exit_reason = ""

                if active_position == 1:
                    unrealized_peak = (h - entry_price) * self.point_value
                    unrealized_trough = (l - entry_price) * self.point_value
                else:
                    unrealized_peak = (entry_price - l) * self.point_value
                    unrealized_trough = (entry_price - h) * self.point_value

                current_trade_mfe = max(current_trade_mfe, unrealized_peak)
                current_trade_mae = min(current_trade_mae, unrealized_trough)

                # Ratchet intra-trade de Apex (Peak-Unrealized MTM)
                floating_peak_equity = balance + max(0.0, unrealized_peak)
                if floating_peak_equity > peak_equity:
                    peak_equity = floating_peak_equity
                    # Suelo se congela permanentemente si el pico alcanza $52,600
                    if peak_equity >= 52600.0:
                        floor = max(floor, 50100.0)
                    else:
                        floor = peak_equity - self.trailing_buffer

                # Breakeven a +1.0R (protección contra inversión total)
                if not be_triggered:
                    if (
                        active_position == 1
                        and (h - entry_price) >= stop_distance
                    ):
                        stop_price = entry_price + 0.50  # +2 ticks
                        be_triggered = True
                    elif (
                        active_position == -1
                        and (entry_price - l) >= stop_distance
                    ):
                        stop_price = entry_price - 0.50  # +2 ticks
                        be_triggered = True

                # Salidas prioritarias
                if active_position == 1:
                    if l <= stop_price:
                        trade_closed = True
                        exit_price = min(o, stop_price) - self.slippage_pts
                        exit_reason = "Stop Loss"
                    elif h >= target_price:
                        trade_closed = True
                        exit_price = target_price
                        exit_reason = "Target Limit (1.75R)"
                    elif curr_time >= "15:55":
                        trade_closed = True
                        exit_price = c - self.slippage_pts
                        exit_reason = "Hard EOD (15:55)"

                elif active_position == -1:
                    if h >= stop_price:
                        trade_closed = True
                        exit_price = max(o, stop_price) + self.slippage_pts
                        exit_reason = "Stop Loss"
                    elif l <= target_price:
                        trade_closed = True
                        exit_price = target_price
                        exit_reason = "Target Limit (1.75R)"
                    elif curr_time >= "15:55":
                        trade_closed = True
                        exit_price = c + self.slippage_pts
                        exit_reason = "Hard EOD (15:55)"

                if trade_closed:
                    gross_pnl_pts = (
                        (exit_price - entry_price)
                        if active_position == 1
                        else (entry_price - exit_price)
                    )
                    gross_pnl_dollars = gross_pnl_pts * self.point_value
                    net_pnl_dollars = gross_pnl_dollars - self.commission_rt

                    balance += net_pnl_dollars
                    if balance > peak_equity:
                        peak_equity = balance
                        if peak_equity >= 52600.0:
                            floor = max(floor, 50100.0)
                        else:
                            floor = peak_equity - self.trailing_buffer

                    trades.append(
                        {
                            "entry_time": entry_time,
                            "exit_time": timestamps[i],
                            "date": current_trade_date,
                            "direction": "LONG"
                            if active_position == 1
                            else "SHORT",
                            "entry_price": entry_price,
                            "exit_price": exit_price,
                            "stop_price": stop_price,
                            "target_price": target_price,
                            "risk_pts": stop_distance,
                            "net_pnl": net_pnl_dollars,
                            "pnl_r": net_pnl_dollars
                            / (stop_distance * self.point_value),
                            "mae_dollars": current_trade_mae,
                            "mfe_dollars": current_trade_mfe,
                            "exit_reason": exit_reason,
                            "balance_after": balance,
                            "floor_after": floor,
                            "cushion_after": balance - floor,
                        }
                    )

                    active_position = 0
                    current_trade_mae = 0.0
                    current_trade_mfe = 0.0
                    be_triggered = False

            # DISPARO DE ENTRADA (09:45 a 11:30 ET)
            if active_position == 0 and not traded_today:
                if "09:45" <= curr_time <= "11:30":
                    vcr_val = vcrs[i]
                    or_w = or_widths[i]
                    or_h = or_highs[i]
                    or_l = or_lows[i]
                    or_m = or_mids[i]
                    rvol_val = rvols[i]
                    vwap_val = vwaps[i]

                    # Filtros de régimen ex-ante
                    if (
                        not np.isnan(vcr_val)
                        and vcr_val <= self.vcr_threshold
                        and self.min_or_width <= or_w <= self.max_or_width
                        and rvol_val >= self.rvol_threshold
                    ):

                        long_signal = (c > or_h) and (c > vwap_val)
                        short_signal = (c < or_l) and (c < vwap_val)

                        if long_signal:
                            active_position = 1
                            entry_price = c + self.slippage_pts
                            raw_stop_dist = abs(entry_price - or_m)
                            stop_distance = min(
                                max(raw_stop_dist, self.min_risk_pts),
                                self.max_risk_pts,
                            )
                            stop_price = entry_price - stop_distance
                            target_price = entry_price + (
                                self.target_r_mult * stop_distance
                            )

                            entry_time = timestamps[i]
                            current_trade_date = curr_date
                            traded_today = True

                        elif short_signal:
                            active_position = -1
                            entry_price = c - self.slippage_pts
                            raw_stop_dist = abs(entry_price - or_m)
                            stop_distance = min(
                                max(raw_stop_dist, self.min_risk_pts),
                                self.max_risk_pts,
                            )
                            stop_price = entry_price + stop_distance
                            target_price = entry_price - (
                                self.target_r_mult * stop_distance
                            )

                            entry_time = timestamps[i]
                            current_trade_date = curr_date
                            traded_today = True

            current_cushion = balance - floor
            equity_series.append(balance)
            floor_series.append(floor)
            cushion_series.append(current_cushion)

            if current_cushion <= 0:
                print(
                    f"\n[!] BREACH DE LIQUIDACIÓN: Colchón agotado en {timestamps[i]}"
                )
                break

        self.trade_log = pd.DataFrame(trades)
        self.performance_summary = self._calculate_metrics(
            equity_series, floor_series, cushion_series
        )
        return self.trade_log

    def _calculate_metrics(
        self, equity_hist: list, floor_hist: list, cushion_hist: list
    ) -> dict:
        if self.trade_log is None or len(self.trade_log) == 0:
            return {"Error": "No se generaron operaciones."}

        tl = self.trade_log
        pnl = tl["net_pnl"].values
        wins = pnl[pnl > 0]
        losses = pnl[pnl <= 0]

        n_trades = len(pnl)
        win_rate = len(wins) / n_trades if n_trades > 0 else 0.0
        gross_profit = np.sum(wins) if len(wins) > 0 else 0.0
        gross_loss = np.abs(np.sum(losses)) if len(losses) > 0 else 1e-6
        profit_factor = gross_profit / gross_loss

        mean_pnl = np.mean(pnl)
        std_pnl = np.std(pnl, ddof=1) if n_trades > 1 else 1e-6
        downside_returns = pnl[pnl < 0]
        downside_std = (
            np.std(downside_returns, ddof=1)
            if len(downside_returns) > 1
            else 1e-6
        )

        sharpe_ratio = (mean_pnl / std_pnl) * np.sqrt(250)
        sortino_ratio = (mean_pnl / downside_std) * np.sqrt(250)

        min_cushion = min(cushion_hist)
        max_buffer_consumed = self.trailing_buffer - min_cushion
        max_buffer_consumed_pct = (
            max_buffer_consumed / self.trailing_buffer
        ) * 100.0

        final_balance = equity_hist[-1]
        hurdle_achieved = (
            final_balance - self.starting_balance
        ) >= self.profit_hurdle
        account_liquidated = min_cushion <= 0.0

        return {
            "Total Trades Executed": n_trades,
            "Win Rate (%)": round(win_rate * 100, 2),
            "Profit Factor": round(profit_factor, 2),
            "Expectancy Per Trade ($)": round(mean_pnl, 2),
            "Expectancy (R)": round(np.mean(tl["pnl_r"]), 3),
            "Sharpe Ratio": round(sharpe_ratio, 2),
            "Sortino Ratio": round(sortino_ratio, 2),
            "Starting Balance ($)": self.starting_balance,
            "Final Closed Balance ($)": round(final_balance, 2),
            "Net Cumulative PnL ($)": round(
                final_balance - self.starting_balance, 2
            ),
            "Profit Hurdle Achieved": hurdle_achieved,
            "Account Liquidated": account_liquidated,
            "Minimum Cushion Observed ($)": round(min_cushion, 2),
            "Max Buffer Consumed (%)": round(max_buffer_consumed_pct, 2),
            "Average MAE ($)": round(np.mean(tl["mae_dollars"]), 2),
            "Average MFE ($)": round(np.mean(tl["mfe_dollars"]), 2),
        }


def main():
    data_path = Path("data/processed/mnq_5m_continuous.parquet")
    if not data_path.exists():
        print(f"❌ Error: No se encontró el dataset continuo en {data_path}")
        return

    print("=" * 80)
    print("   ALPHAFORGE: AUDITORÍA FORENSE 15-MINUTE VCR-ORB (CME GLOBEX MNQ)")
    print("=" * 80)
    print(f"-> Ingestando dataset real desde: {data_path}")
    df = pd.read_parquet(data_path)
    print(f"-> Barras cargadas: {len(df):,}")

    engine = MNQEconometricORBEngine(df)
    trade_log = engine.run_backtest()

    print("\n" + "=" * 80)
    print("                      RESUMEN DE DESEMPEÑO APEX 50k")
    print("=" * 80)
    for k, v in engine.performance_summary.items():
        print(f"  {k:<35}: {v}")
    print("=" * 80)

    # Exportar el log de operaciones para auditoría
    out_dir = Path("reports/artifacts")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / "vcr_orb_forensic_trades.csv"
    trade_log.to_csv(out_csv, index=False)
    print(f"\n✅ Log forense guardado en: {out_csv}")


if __name__ == "__main__":
    main()