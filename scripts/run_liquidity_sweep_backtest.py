from pathlib import Path
import pandas as pd
import numpy as np

class LiquiditySweepEngine:
    def __init__(
        self,
        df: pd.DataFrame,
        starting_balance: float = 50000.0,
        trailing_buffer: float = 2500.0,
        max_stop_pts: float = 22.0,
        min_stop_pts: float = 10.0,
        target_r_mult: float = 2.20,
        sweep_tolerance_pts: float = 15.0,
        commission_rt: float = 1.24,
        slippage_pts: float = 0.25,
        point_value: float = 2.0
    ):
        self.df = df.copy()
        self.starting_balance = starting_balance
        self.trailing_buffer = trailing_buffer
        self.max_stop_pts = max_stop_pts
        self.min_stop_pts = min_stop_pts
        self.target_r_mult = target_r_mult
        self.sweep_tolerance_pts = sweep_tolerance_pts
        self.commission_rt = commission_rt
        self.slippage_pts = slippage_pts
        self.point_value = point_value
        
        self.prepared_df = None
        self.trade_log = None
        self.performance_summary = None

    def prepare_data(self) -> pd.DataFrame:
        df = self.df.copy()
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

        # 1. Máximos y Mínimos del Día Anterior (PDH y PDL)
        daily = df.groupby("date").agg(d_high=("high", "max"), d_low=("low", "min"))
        daily["pdh"] = daily["d_high"].shift(1)
        daily["pdl"] = daily["d_low"].shift(1)
        df["pdh"] = df["date"].map(daily["pdh"])
        df["pdl"] = df["date"].map(daily["pdl"])

        # 2. VWAP de sesión RTH
        is_rth = (df["hour_min"] >= "09:30") & (df["hour_min"] <= "16:00")
        df["tp"] = (df["high"] + df["low"] + df["close"]) / 3.0
        df["tp_vol"] = df["tp"] * df["volume"]
        rth_df = df[is_rth].copy()
        rth_df["cum_tp_vol"] = rth_df.groupby("date")["tp_vol"].cumsum()
        rth_df["cum_vol"] = rth_df.groupby("date")["volume"].cumsum()
        df["vwap"] = rth_df["cum_tp_vol"] / rth_df["cum_vol"]
        df["vwap"] = df.groupby("date")["vwap"].ffill()

        self.prepared_df = df
        return df

    def run_backtest(self) -> pd.DataFrame:
        if self.prepared_df is None:
            self.prepare_data()

        df = self.prepared_df
        balance = self.starting_balance
        peak_equity = self.starting_balance
        floor = self.starting_balance - self.trailing_buffer

        active_pos = 0  # 1: Long, -1: Short, 0: Flat
        entry_price = 0.0
        stop_price = 0.0
        target_price = 0.0
        stop_dist = 0.0
        
        current_mae = 0.0
        current_mfe = 0.0
        entry_time = None
        current_date = None

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
        pdhs = df["pdh"].values
        pdls = df["pdl"].values
        timestamps = df.index

        n_bars = len(df)
        traded_today = False
        prev_date = None

        for i in range(n_bars):
            c_date = dates[i]
            c_time = hour_mins[i]
            o, h, l, c = opens[i], highs[i], lows[i], closes[i]

            if c_date != prev_date:
                traded_today = False
                prev_date = c_date

            # GESTIÓN DE POSICIÓN ACTIVA
            if active_pos != 0:
                closed = False
                exit_p = 0.0
                exit_reason = ""

                if active_pos == 1:
                    u_peak = (h - entry_price) * self.point_value
                    u_trough = (l - entry_price) * self.point_value
                else:
                    u_peak = (entry_price - l) * self.point_value
                    u_trough = (entry_price - h) * self.point_value

                current_mfe = max(current_mfe, u_peak)
                current_mae = min(current_mae, u_trough)

                floating_peak = balance + max(0.0, u_peak)
                if floating_peak > peak_equity:
                    peak_equity = floating_peak
                    if peak_equity >= 52600.0:
                        floor = max(floor, 50100.0)
                    else:
                        floor = peak_equity - self.trailing_buffer

                if active_pos == 1:
                    if l <= stop_price:
                        closed = True
                        exit_p = min(o, stop_price) - self.slippage_pts
                        exit_reason = "Stop Loss"
                    elif h >= target_price:
                        closed = True
                        exit_p = target_price
                        exit_reason = "Target"
                    elif c_time >= "15:55":
                        closed = True
                        exit_p = c - self.slippage_pts
                        exit_reason = "Hard EOD"
                else:
                    if h >= stop_price:
                        closed = True
                        exit_p = max(o, stop_price) + self.slippage_pts
                        exit_reason = "Stop Loss"
                    elif l <= target_price:
                        closed = True
                        exit_p = target_price
                        exit_reason = "Target"
                    elif c_time >= "15:55":
                        closed = True
                        exit_p = c + self.slippage_pts
                        exit_reason = "Hard EOD"

                if closed:
                    pts = (exit_p - entry_price) if active_pos == 1 else (entry_price - exit_p)
                    net_dollar = (pts * self.point_value) - self.commission_rt
                    balance += net_dollar

                    if balance > peak_equity:
                        peak_equity = balance
                        if peak_equity >= 52600.0:
                            floor = max(floor, 50100.0)
                        else:
                            floor = peak_equity - self.trailing_buffer

                    trades.append({
                        "entry_time": entry_time,
                        "exit_time": timestamps[i],
                        "date": current_date,
                        "direction": "LONG" if active_pos == 1 else "SHORT",
                        "entry_price": entry_price,
                        "exit_price": exit_p,
                        "stop_price": stop_price,
                        "target_price": target_price,
                        "risk_pts": stop_dist,
                        "net_pnl": net_dollar,
                        "pnl_r": net_dollar / (stop_dist * self.point_value),
                        "mae_dollars": current_mae,
                        "mfe_dollars": current_mfe,
                        "exit_reason": exit_reason,
                        "balance_after": balance,
                        "floor_after": floor,
                        "cushion_after": balance - floor
                    })
                    active_pos = 0
                    current_mae = 0.0
                    current_mfe = 0.0

            # EVALUACIÓN DE ENTRADA (09:45 a 14:30 ET)
            if active_pos == 0 and not traded_today:
                if "09:45" <= c_time <= "14:30":
                    pdh_val = pdhs[i]
                    pdl_val = pdls[i]
                    vwap_val = vwaps[i]

                    if not np.isnan(pdh_val) and not np.isnan(pdl_val):
                        # Barrido Bajista (Bearish Sweep de PDH):
                        # Perfora PDH por unos puntos pero la barra cierra por debajo de PDH
                        if h > pdh_val and (h - pdh_val) <= self.sweep_tolerance_pts and c < pdh_val and c < vwap_val:
                            active_pos = -1
                            entry_price = c - self.slippage_pts
                            raw_stop = (h + 0.50) - entry_price
                            stop_dist = min(max(raw_stop, self.min_stop_pts), self.max_stop_pts)
                            stop_price = entry_price + stop_dist
                            target_price = entry_price - (self.target_r_mult * stop_dist)
                            entry_time = timestamps[i]
                            current_date = c_date
                            traded_today = True

                        # Barrido Alcista (Bullish Sweep de PDL):
                        # Perfora PDL pero la barra cierra por encima de PDL
                        elif l < pdl_val and (pdl_val - l) <= self.sweep_tolerance_pts and c > pdl_val and c > vwap_val:
                            active_pos = 1
                            entry_price = c + self.slippage_pts
                            raw_stop = entry_price - (l - 0.50)
                            stop_dist = min(max(raw_stop, self.min_stop_pts), self.max_stop_pts)
                            stop_price = entry_price - stop_dist
                            target_price = entry_price + (self.target_r_mult * stop_dist)
                            entry_time = timestamps[i]
                            current_date = c_date
                            traded_today = True

            cushion_series.append(balance - floor)
            equity_series.append(balance)
            floor_series.append(floor)

            if (balance - floor) <= 0:
                print(f"[!] Brecha de suelo en {timestamps[i]}")
                break

        self.trade_log = pd.DataFrame(trades)
        self.performance_summary = self._calc_metrics(equity_series, cushion_series)
        return self.trade_log

    def _calc_metrics(self, equity_hist: list, cushion_hist: list) -> dict:
        if self.trade_log is None or len(self.trade_log) == 0:
            return {"Error": "Sin operaciones ejecutadas."}

        tl = self.trade_log
        pnl = tl["net_pnl"].values
        wins = pnl[pnl > 0]
        losses = pnl[pnl <= 0]
        n_trades = len(pnl)

        wr = len(wins) / n_trades if n_trades > 0 else 0.0
        pf = wins.sum() / abs(losses.sum()) if len(losses) > 0 and abs(losses.sum()) > 0 else 0.0
        mean_pnl = np.mean(pnl)
        std_pnl = np.std(pnl, ddof=1) if n_trades > 1 else 1e-6
        downside_std = np.std(pnl[pnl < 0], ddof=1) if len(pnl[pnl < 0]) > 1 else 1e-6

        sharpe = (mean_pnl / std_pnl) * np.sqrt(250)
        sortino = (mean_pnl / downside_std) * np.sqrt(250)
        min_cush = min(cushion_hist)
        max_buffer_consumed = (self.trailing_buffer - min_cush) / self.trailing_buffer * 100.0

        return {
            "Total Trades Executed": n_trades,
            "Win Rate (%)": round(wr * 100, 2),
            "Profit Factor": round(pf, 2),
            "Expectancy Per Trade ($)": round(mean_pnl, 2),
            "Expectancy (R)": round(np.mean(tl["pnl_r"]), 3),
            "Sharpe Ratio": round(sharpe, 2),
            "Sortino Ratio": round(sortino, 2),
            "Net Cumulative PnL ($)": round(equity_hist[-1] - self.starting_balance, 2),
            "Min Cushion Observed ($)": round(min_cush, 2),
            "Max Buffer Consumed (%)": round(max_buffer_consumed, 2),
            "Average MAE ($)": round(np.mean(tl["mae_dollars"]), 2),
            "Average MFE ($)": round(np.mean(tl["mfe_dollars"]), 2),
        }

if __name__ == "__main__":
    df = pd.read_parquet("data/processed/mnq_5m_continuous.parquet")
    engine = LiquiditySweepEngine(df)
    trade_log = engine.run_backtest()
    print("=" * 80)
    print("      AUDITORÍA: LIQUIDITY SWEEP & REVERSAL (PDH/PDL)")
    print("=" * 80)
    for k, v in engine.performance_summary.items():
        print(f"  {k:<35}: {v}")
    print("=" * 80)
