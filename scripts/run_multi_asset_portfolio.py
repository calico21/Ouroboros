"""
Ouroboros Execution Suite - Multi-Asset Portfolio Engine
Implementa PDH Liquidity Sweep Short con:
1. Filtro estricto de rechazo institucional (mecha superior >= 35%).
2. Regla de exclusión mutua: máximo 1 posición activa simultánea en la cuenta.
3. Selección por convicción: ante señales simultáneas, entra en el activo con mayor ratio de rechazo.
4. Simulación estricta de Peak-Unrealized MTM Trailing Floor de Apex 50k.
"""

from pathlib import Path
import pandas as pd
import numpy as np


class MultiAssetPortfolioEngine:
    def __init__(
        self,
        asset_configs: dict,
        min_wick_ratio: float = 0.35,
        target_r: float = 1.60,
        max_concurrent_trades: int = 1,
        starting_balance: float = 50000.0,
        trailing_buffer: float = 2500.0,
    ):
        self.asset_configs = asset_configs
        self.min_wick_ratio = min_wick_ratio
        self.target_r = target_r
        self.max_concurrent_trades = max_concurrent_trades
        self.starting_balance = starting_balance
        self.trailing_buffer = trailing_buffer

    def _prepare_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
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

        # Previous Day High (PDH)
        daily = df.groupby("date").agg(d_high=("high", "max"))
        daily["pdh"] = daily["d_high"].shift(1)
        df["pdh"] = df["date"].map(daily["pdh"])

        # VWAP de sesión RTH
        is_rth = (df["hour_min"] >= "09:30") & (df["hour_min"] <= "16:00")
        df["tp"] = (df["high"] + df["low"] + df["close"]) / 3.0
        df["tp_vol"] = df["tp"] * df["volume"]
        rth_df = df[is_rth].copy()
        rth_df["cum_tp_vol"] = rth_df.groupby("date")["tp_vol"].cumsum()
        rth_df["cum_vol"] = rth_df.groupby("date")["volume"].cumsum()
        df["vwap"] = rth_df["cum_tp_vol"] / rth_df["cum_vol"]
        df["vwap"] = df.groupby("date")["vwap"].ffill()

        # Ratio de mecha superior
        bar_range = np.maximum(0.25, df["high"] - df["low"])
        upper_wick = df["high"] - np.maximum(df["open"], df["close"])
        df["wick_ratio"] = upper_wick / bar_range

        return df

    def run_backtest(self) -> dict:
        processed_data = {}
        for symbol, cfg in self.asset_configs.items():
            path = Path(cfg["path"])
            if not path.exists():
                print(f"[!] Aviso: No se encontró {path}. Omitiendo {symbol}.")
                continue
            df_raw = pd.read_parquet(path)
            processed_data[symbol] = self._prepare_dataframe(df_raw)

        if not processed_data:
            raise FileNotFoundError("No se encontró ningún dataset válido para operar.")

        # Obtener la unión ordenada de timestamps
        all_timestamps = sorted(
            list(set().union(*[df.index for df in processed_data.values()]))
        )

        balance = self.starting_balance
        peak_equity = self.starting_balance
        floor = self.starting_balance - self.trailing_buffer

        active_trade = None  # Dict con el estado de la posición activa
        trades = []
        cushions = []
        traded_today = {sym: False for sym in processed_data.keys()}
        prev_date = None

        for ts in all_timestamps:
            curr_date = ts.date()
            if curr_date != prev_date:
                traded_today = {sym: False for sym in processed_data.keys()}
                prev_date = curr_date

            hour_min = ts.strftime("%H:%M")

            # 1. GESTIÓN DE LA POSICIÓN ACTIVA (si existe)
            if active_trade is not None:
                sym = active_trade["symbol"]
                df_sym = processed_data[sym]

                if ts in df_sym.index:
                    row = df_sym.loc[ts]
                    o, h, l, c = row["open"], row["high"], row["low"], row["close"]
                    pt_val = self.asset_configs[sym]["point_value"]
                    contracts = active_trade["contracts"]

                    # Actualización de MTM flotante (Peak MTM de Apex)
                    unrealized_gain = (active_trade["entry_price"] - l) * pt_val * contracts
                    floating_peak = balance + max(0.0, unrealized_gain)
                    if floating_peak > peak_equity:
                        peak_equity = floating_peak
                        if peak_equity >= 52600.0:
                            floor = max(floor, 50100.0)
                        else:
                            floor = peak_equity - self.trailing_buffer

                    closed = False
                    exit_price = 0.0
                    reason = ""

                    # Comprobar Stop Loss
                    if h >= active_trade["stop_price"]:
                        closed = True
                        exit_price = max(o, active_trade["stop_price"]) + active_trade["slippage"]
                        reason = "Stop Loss"
                    # Comprobar Target
                    elif l <= active_trade["target_price"]:
                        closed = True
                        exit_price = active_trade["target_price"]
                        reason = "Target"
                    # Salida obligatoria EOD
                    elif hour_min >= "15:55":
                        closed = True
                        exit_price = c + active_trade["slippage"]
                        reason = "Hard EOD"

                    if closed:
                        pts = active_trade["entry_price"] - exit_price
                        gross_pnl = pts * pt_val * contracts
                        comm = self.asset_configs[sym]["commission_rt"] * contracts
                        net_pnl = gross_pnl - comm

                        balance += net_pnl
                        if balance > peak_equity:
                            peak_equity = balance
                            if peak_equity >= 52600.0:
                                floor = max(floor, 50100.0)
                            else:
                                floor = peak_equity - self.trailing_buffer

                        trades.append({
                            "exit_time": ts,
                            "date": curr_date,
                            "symbol": sym,
                            "contracts": contracts,
                            "entry_price": active_trade["entry_price"],
                            "exit_price": exit_price,
                            "risk_pts": active_trade["stop_distance"],
                            "net_pnl": net_pnl,
                            "reason": reason,
                            "balance_after": balance,
                            "cushion_after": balance - floor,
                        })
                        active_trade = None

            # 2. EVALUACIÓN DE NUEVAS ENTRADAS (Solo si no hay posición activa)
            if active_trade is None and "09:45" <= hour_min <= "14:30":
                candidates = []

                for sym, df_sym in processed_data.items():
                    if traded_today[sym] or ts not in df_sym.index:
                        continue

                    row = df_sym.loc[ts]
                    h, c = row["high"], row["close"]
                    pdh_val = row["pdh"]
                    vwap_val = row["vwap"]
                    wick_val = row["wick_ratio"]
                    cfg = self.asset_configs[sym]

                    if not np.isnan(pdh_val):
                        sweep_dist = h - pdh_val
                        if (
                            0 < sweep_dist <= cfg["sweep_tolerance"]
                            and c < pdh_val
                            and c < vwap_val
                            and wick_val >= self.min_wick_ratio
                        ):
                            raw_stop = (h + cfg["stop_pad"]) - c
                            stop_dist = min(max(raw_stop, cfg["min_stop_pts"]), cfg["max_stop_pts"])
                            candidates.append({
                                "symbol": sym,
                                "close": c,
                                "high": h,
                                "wick_ratio": wick_val,
                                "stop_distance": stop_dist,
                                "cfg": cfg,
                            })

                # Si hay señales en varios activos a la vez, se elige el de mayor mecha de rechazo
                if candidates:
                    candidates.sort(key=lambda x: x["wick_ratio"], reverse=True)
                    best = candidates[0]
                    sym = best["symbol"]
                    cfg = best["cfg"]

                    entry_p = best["close"] - cfg["slippage"]
                    stop_p = entry_p + best["stop_distance"]
                    target_p = entry_p - (self.target_r * best["stop_distance"])

                    active_trade = {
                        "symbol": sym,
                        "entry_price": entry_p,
                        "stop_price": stop_p,
                        "target_price": target_p,
                        "stop_distance": best["stop_distance"],
                        "contracts": cfg["contracts"],
                        "slippage": cfg["slippage"],
                    }
                    traded_today[sym] = True

            cushions.append(balance - floor)

        return self._generate_report(trades, cushions, balance)

    def _generate_report(self, trades: list, cushions: list, final_balance: float) -> dict:
        if not trades:
            return {"Error": "No se generaron operaciones con los filtros dados."}

        tl = pd.DataFrame(trades)
        pnl = tl["net_pnl"].values
        wins = pnl[pnl > 0]
        losses = pnl[pnl <= 0]
        wr = len(wins) / len(pnl) * 100
        pf = wins.sum() / abs(losses.sum()) if abs(losses.sum()) > 0 else 0
        min_cush = min(cushions)
        max_dd_buf = ((self.trailing_buffer - min_cush) / self.trailing_buffer) * 100.0

        out_path = Path("reports/artifacts/multi_asset_portfolio_trades.csv")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tl.to_csv(out_path, index=False)

        print("\n" + "=" * 85)
        print("    OUROBOROS: AUDITORÍA DE CARTERA MULTIACTIVO (EXCLUSIÓN MUTUA)")
        print("=" * 85)
        print(f"  Total Operaciones Ejecutadas : {len(pnl)}")
        print(f"  Tasa de Acierto (Win Rate)   : {wr:.2f}%")
        print(f"  Profit Factor Neto           : {pf:.2f}")
        print(f"  PnL Neto Acumulado           : ${pnl.sum():,.2f}")
        print(f"  Esperanza / Trade            : ${pnl.mean():.2f}")
        print(f"  Colchón Mínimo Observado     : ${min_cush:,.2f}")
        print(f"  Consumo Máximo del Colchón   : {max_dd_buf:.2f}% (Límite: 100%)")
        print(f"  Archivo de Auditoría         : {out_path}")
        print("=" * 85)

        print("\n--- DESGLOSE POR ACTIVO ---")
        for sym in tl["symbol"].unique():
            sub = tl[tl["symbol"] == sym]
            sub_pnl = sub["net_pnl"].values
            sub_wins = sub_pnl[sub_pnl > 0]
            sub_losses = sub_pnl[sub_pnl <= 0]
            sub_wr = len(sub_wins) / len(sub_pnl) * 100
            sub_pf = sub_wins.sum() / abs(sub_losses.sum()) if abs(sub_losses.sum()) > 0 else 0
            print(
                f"  {sym:<6} | Trades: {len(sub):<3} | WR: {sub_wr:.1f}% | "
                f"PF: {sub_pf:.2f} | PnL: ${sub_pnl.sum():,.2f}"
            )
        print("=" * 85 + "\n")

        return tl


if __name__ == "__main__":
    # Configuración de activos de futuros CME
    ASSET_UNIVERSE = {
        "MNQ": {
            "path": "data/processed/mnq_5m_continuous.parquet",
            "point_value": 2.0,
            "commission_rt": 1.24,
            "slippage": 0.25,
            "stop_pad": 0.50,
            "sweep_tolerance": 15.0,
            "min_stop_pts": 10.0,
            "max_stop_pts": 22.0,
            "contracts": 2,
        },
        "MES": {
            "path": "data/processed/mes_5m_continuous.parquet",
            "point_value": 5.0,
            "commission_rt": 1.24,
            "slippage": 0.25,
            "stop_pad": 0.50,
            "sweep_tolerance": 5.0,
            "min_stop_pts": 3.0,
            "max_stop_pts": 8.0,
            "contracts": 2,
        },
        "M2K": {
            "path": "data/processed/m2k_5m_continuous.parquet",
            "point_value": 10.0,
            "commission_rt": 1.24,
            "slippage": 0.10,
            "stop_pad": 0.20,
            "sweep_tolerance": 4.0,
            "min_stop_pts": 2.0,
            "max_stop_pts": 6.0,
            "contracts": 1,
        },
    }

    engine = MultiAssetPortfolioEngine(
        asset_configs=ASSET_UNIVERSE,
        min_wick_ratio=0.35,  # Exige al menos 35% de mecha de rechazo
        target_r=1.60,        # Payoff asimétrico optimizado
        max_concurrent_trades=1,
    )
    engine.run_backtest()
