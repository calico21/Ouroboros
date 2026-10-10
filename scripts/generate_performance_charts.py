from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd

def generate_all_performance_charts(contracts: int = 3, target_r: float = 1.50):
    output_dir = Path("reports/figures")
    output_dir.mkdir(parents=True, exist_ok=True)

    data_path = Path("data/processed/mnq_5m_continuous.parquet")
    df = pd.read_parquet(data_path)
    if df.index.tz is None:
        df.index = df.index.tz_localize("America/New_York")
    else:
        df.index = df.index.tz_convert("America/New_York")
    df = df.sort_index()
    df["date"] = df.index.date
    df["hour_min"] = df.index.strftime("%H:%M")

    daily = df.groupby("date").agg(d_high=("high", "max"))
    daily["pdh"] = daily["d_high"].shift(1)
    df["pdh"] = df["date"].map(daily["pdh"])

    is_rth = (df["hour_min"] >= "09:30") & (df["hour_min"] <= "16:00")
    df["tp"] = (df["high"] + df["low"] + df["close"]) / 3.0
    df["tp_vol"] = df["tp"] * df["volume"]
    rth_df = df[is_rth].copy()
    rth_df["cum_tp_vol"] = rth_df.groupby("date")["tp_vol"].cumsum()
    rth_df["cum_vol"] = rth_df.groupby("date")["volume"].cumsum()
    df["vwap"] = rth_df["cum_tp_vol"] / rth_df["cum_vol"]
    df["vwap"] = df.groupby("date")["vwap"].ffill()

    df["vol_sma20"] = df["volume"].rolling(20, min_periods=5).mean()

    dates = df["date"].values
    hour_mins = df["hour_min"].values
    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    vwaps = df["vwap"].values
    pdhs = df["pdh"].values
    vols = df["volume"].values
    vol_smas = df["vol_sma20"].values
    timestamps = df.index

    balance = 50000.0
    peak = 50000.0
    floor = 47500.0
    active = False
    entry_p = stop_p = target_p = 0.0
    trades = []
    prev_date = None
    traded_today = False

    for i in range(len(df)):
        c_date = dates[i]
        c_time = hour_mins[i]
        o, h, l, c = opens[i], highs[i], lows[i], closes[i]

        if c_date != prev_date:
            traded_today = False
            prev_date = c_date

        if active:
            u_peak = (entry_p - l) * 2.0 * contracts
            f_peak = balance + max(0.0, u_peak)
            if f_peak > peak:
                peak = f_peak
                floor = max(floor, 50100.0) if peak >= 52600.0 else peak - 2500.0

            closed = False
            exit_p = 0.0

            if h >= stop_p:
                closed = True
                exit_p = max(o, stop_p) + 0.25
            elif l <= target_p:
                closed = True
                exit_p = target_p
            elif c_time >= "15:55":
                closed = True
                exit_p = c + 0.25

            if closed:
                pts = entry_p - exit_p
                net = (pts * 2.0 * contracts) - (1.24 * contracts)
                balance += net
                trades.append({
                    "timestamp": timestamps[i],
                    "date": c_date,
                    "net": net,
                    "balance": balance,
                    "cushion": balance - floor,
                    "is_win": net > 0
                })
                active = False

        if not active and not traded_today:
            if "09:45" <= c_time <= "12:30":
                pdh_val = pdhs[i]
                vwap_val = vwaps[i]
                v_val = vols[i]
                v_sma = vol_smas[i]

                if not np.isnan(pdh_val):
                    sweep_dist = h - pdh_val
                    vol_ok = not np.isnan(v_sma) and (v_val >= 1.1 * v_sma)

                    if 0 < sweep_dist <= 15.0 and c < pdh_val and c < vwap_val and vol_ok:
                        active = True
                        entry_p = c - 0.25
                        raw_stop = (h + 0.50) - entry_p
                        stop_dist = min(max(raw_stop, 10.0), 22.0)
                        stop_p = entry_p + stop_dist
                        target_p = entry_p - (target_r * stop_dist)
                        traded_today = True

    t_df = pd.DataFrame(trades)
    t_df["cum_pnl"] = t_df["net"].cumsum()
    t_df["trade_num"] = np.arange(1, len(t_df) + 1)
    t_df["timestamp"] = pd.to_datetime(t_df["timestamp"])
    split_date = pd.Timestamp("2024-01-01", tz="America/New_York")

    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
    plt.rcParams["font.sans-serif"] = "DejaVu Sans"
    plt.rcParams["axes.edgecolor"] = "#CCCCCC"
    plt.rcParams["axes.linewidth"] = 0.8

    fig, axes = plt.subplots(3, 2, figsize=(18, 16))
    fig.suptitle(f"OUROBOROS MNQ MASTER TEARSHEET ({contracts} MNQ, Target {target_r:.2f}R)", fontsize=18, fontweight="bold", y=0.99)

    ax1 = axes[0, 0]
    ax1.plot(t_df["timestamp"], t_df["cum_pnl"], color="#0052CC", linewidth=2.2, label="Curva de PnL Neto ($)")
    ax1.axvline(split_date, color="#D9381E", linestyle="--", linewidth=1.5, label="Corte IS / OOS")
    ax1.axvspan(t_df["timestamp"].min(), split_date, color="#EBF3FB", alpha=0.6, label="In-Sample (2022-2023)")
    ax1.axvspan(split_date, t_df["timestamp"].max(), color="#EDF9E7", alpha=0.6, label="Out-of-Sample (2024-2026)")
    ax1.set_title("1. Curva de Capital Acumulado (Net PnL)", fontsize=13, fontweight="bold")
    ax1.set_ylabel("Dólares ($)")
    ax1.legend(loc="upper left", frameon=True)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

    ax2 = axes[0, 1]
    ax2.plot(t_df["timestamp"], t_df["cushion"], color="#00875A", linewidth=2.0, label="Colchón Disponible")
    ax2.axhline(2500.0, color="#6554C0", linestyle=":", linewidth=1.2, label="Colchón Inicial ($2,500)")
    ax2.axhline(0.0, color="#DE350B", linestyle="-", linewidth=2.0, label="Límite Liquidación ($0)")
    ax2.fill_between(t_df["timestamp"], 0, t_df["cushion"], color="#00875A", alpha=0.15)
    ax2.set_title(f"2. Colchón Apex Trailing (Mínimo: ${t_df['cushion'].min():,.2f})", fontsize=13, fontweight="bold")
    ax2.set_ylabel("Margen Restante ($)")
    ax2.legend(loc="lower left", frameon=True)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

    ax3 = axes[1, 0]
    t_df["month_year"] = t_df["timestamp"].dt.to_period("M")
    monthly_pnl = t_df.groupby("month_year")["net"].sum()
    colors = ["#00875A" if v >= 0 else "#DE350B" for v in monthly_pnl.values]
    monthly_idx = [str(p) for p in monthly_pnl.index]
    ax3.bar(range(len(monthly_pnl)), monthly_pnl.values, color=colors, width=0.7)
    ax3.set_title("3. Rendimiento Mensual Neto ($)", fontsize=13, fontweight="bold")
    ax3.set_ylabel("PnL ($)")
    ax3.set_xticks(range(0, len(monthly_pnl), 3))
    ax3.set_xticklabels(monthly_idx[::3], rotation=45, ha="right", fontsize=9)
    ax3.axhline(0, color="#333333", linewidth=0.8)

    ax4 = axes[1, 1]
    wins = t_df[t_df["net"] > 0]["net"]
    losses = t_df[t_df["net"] <= 0]["net"]
    ax4.hist(wins, bins=15, color="#00875A", alpha=0.75, label=f"Ganadores (N={len(wins)}, Mean=${wins.mean():.1f})")
    ax4.hist(losses, bins=15, color="#DE350B", alpha=0.75, label=f"Perdedores (N={len(losses)}, Mean=${losses.mean():.1f})")
    ax4.axvline(0, color="#172B4D", linestyle="--", linewidth=1.2)
    ax4.set_title(f"4. Asimetría de Retornos (Win Rate: {len(wins)/len(t_df)*100:.1f}%)", fontsize=13, fontweight="bold")
    ax4.set_xlabel("PnL Neto ($)")
    ax4.set_ylabel("Frecuencia")
    ax4.legend(loc="upper right", frameon=True)

    ax5 = axes[2, 0]
    rolling_wr = t_df["is_win"].rolling(15, min_periods=5).mean() * 100.0
    ax5.plot(t_df["trade_num"], rolling_wr, color="#6554C0", linewidth=2.0, label="Win Rate Móvil (15 trades)")
    ax5.axhline(50.0, color="#999999", linestyle="--", label="Breakeven 50%")
    ax5.set_title("5. Estabilidad Temporal: Win Rate Móvil", fontsize=13, fontweight="bold")
    ax5.set_xlabel("Número de Operación")
    ax5.set_ylabel("Win Rate (%)")
    ax5.set_ylim(20, 90)
    ax5.legend(loc="lower left", frameon=True)

    ax6 = axes[2, 1]
    np.random.seed(42)
    sim_paths = []
    trades_pool = t_df["net"].values
    n_sim_runs = 250
    steps = 100
    for _ in range(n_sim_runs):
        p = np.cumsum(np.random.choice(trades_pool, size=steps, replace=True))
        sim_paths.append(p)
        ax6.plot(range(steps), p, color="#0052CC", alpha=0.04, linewidth=1)

    sim_mat = np.array(sim_paths)
    p5 = np.percentile(sim_mat, 5, axis=0)
    p50 = np.percentile(sim_mat, 50, axis=0)
    p95 = np.percentile(sim_mat, 95, axis=0)

    ax6.plot(range(steps), p50, color="#0052CC", linewidth=2.5, label="Mediana (P50)")
    ax6.plot(range(steps), p95, color="#00875A", linewidth=2.0, linestyle="--", label="Favorable (P95)")
    ax6.plot(range(steps), p5, color="#FF8B00", linewidth=2.0, linestyle="--", label="Conservador (P5)")
    ax6.axhline(3000.0, color="#D9381E", linewidth=2.0, linestyle="-", label="Target Apex (+$3,000)")
    ax6.set_title("6. Simulación Monte Carlo hacia Target $3,000", fontsize=13, fontweight="bold")
    ax6.set_xlabel("Trades Ejecutados")
    ax6.set_ylabel("PnL Acumulado ($)")
    ax6.set_ylim(-1000, 5000)
    ax6.legend(loc="upper left", frameon=True)

    plt.tight_layout()
    tearsheet_path = output_dir / "00_master_tearsheet.png"
    plt.savefig(tearsheet_path, dpi=300)
    plt.close()
    print(f"✅ Tearsheet Maestro guardado: {tearsheet_path}")

    # Gráfico individual: Equity & Trailing Floor
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(t_df["timestamp"], t_df["balance"], color="#0052CC", linewidth=2.2, label="Balance de Cuenta ($)")
    ax.plot(t_df["timestamp"], t_df["balance"] - t_df["cushion"], color="#DE350B", linestyle="--", linewidth=1.8, label="Apex Trailing Liquidation Floor ($)")
    ax.fill_between(t_df["timestamp"], t_df["balance"] - t_df["cushion"], t_df["balance"], color="#00875A", alpha=0.15, label="Colchón de Seguridad")
    ax.set_title("Curva de Balance y Suelo de Liquidación Trailing Apex ($50k)", fontsize=14, fontweight="bold")
    ax.set_ylabel("Dólares ($)")
    ax.legend(loc="upper left", frameon=True)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    plt.tight_layout()
    plt.savefig(output_dir / "01_equity_and_trailing_floor.png", dpi=300)
    plt.close()

    # Gráfico individual: Histograma Monte Carlo
    fig, ax = plt.subplots(figsize=(10, 5.5))
    pass_steps = []
    for _ in range(5000):
        acc = 0.0
        for s in range(1, 201):
            acc += np.random.choice(trades_pool)
            if acc >= 3000.0:
                pass_steps.append(s)
                break
    ax.hist(pass_steps, bins=35, color="#0052CC", edgecolor="#FFFFFF", alpha=0.85)
    ax.axvline(np.mean(pass_steps), color="#DE350B", linestyle="--", linewidth=2.0, label=f"Media: {np.mean(pass_steps):.1f} trades")
    ax.axvline(np.median(pass_steps), color="#00875A", linestyle=":", linewidth=2.0, label=f"Mediana: {np.median(pass_steps):.1f} trades")
    ax.set_title("Distribución de Trades Necesarios para Alcanzar +$3,000 en Apex 50k", fontsize=13, fontweight="bold")
    ax.set_xlabel("Número de Trades")
    ax.set_ylabel("Frecuencia (Simulaciones)")
    ax.legend(frameon=True)
    plt.tight_layout()
    plt.savefig(output_dir / "02_monte_carlo_pass_distribution.png", dpi=300)
    plt.close()

    print(f"✅ Gráficos individuales guardados en: {output_dir}/")

if __name__ == "__main__":
    generate_all_performance_charts()
