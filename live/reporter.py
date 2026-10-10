import os
from pathlib import Path
import numpy as np
import pandas as pd

# Modo headless para servidores sin entorno gráfico (X11)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from live.config import APEX_RULES

CHART_OUTPUT_PATH = Path("reports/daily_performance_tearsheet.png")
JOURNAL_FILE = Path("reports/paper_trading_journal.csv")

def generate_daily_chart(state) -> Path:
    """Genera un tear sheet institucional de 4 paneles y lo guarda en disco."""
    CHART_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    plt.style.use("dark_background")
    fig, axs = plt.subplots(2, 2, figsize=(16, 10), dpi=200)
    fig.patch.set_facecolor("#0e1117")
    for ax in axs.flat:
        ax.set_facecolor("#161b22")
        ax.grid(True, linestyle="--", alpha=0.25, color="#8b949e")

    # Si no hay trades todavía, generamos panel base informativo
    if not JOURNAL_FILE.exists() or os.stat(JOURNAL_FILE).st_size == 0:
        fig.suptitle("OUROBOROS QUANT: ESTADO DE INICIALIZACIÓN (SIN OPERACIONES)", fontsize=16, color="#58a6ff", weight="bold")
        axs[0, 0].text(0.5, 0.5, f"Balance: ${state['balance']:,.2f}\nSuelo: ${state['floor']:,.2f}\nColchón: ${state['balance']-state['floor']:,.2f}", 
                       ha="center", va="center", color="#c9d1d9", fontsize=14)
        plt.tight_layout()
        plt.savefig(CHART_OUTPUT_PATH, facecolor=fig.get_facecolor(), edgecolor="none")
        plt.close()
        return CHART_OUTPUT_PATH

    df = pd.read_csv(JOURNAL_FILE)
    df["dt"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("dt").reset_index(drop=True)
    
    # Series acumuladas
    df["cum_pnl"] = df["net_pnl"].cumsum()
    balances = [APEX_RULES["starting_balance"]] + list(df["balance_after"])
    floors = [APEX_RULES["initial_floor"]] + list(df["floor_after"])
    steps = list(range(len(balances)))

    # -------------------------------------------------------------
    # PANEL 1: EQUITY CURVE VS TRAILING FLOOR
    # -------------------------------------------------------------
    ax1 = axs[0, 0]
    ax1.step(steps, balances, where="post", color="#58a6ff", linewidth=2.2, label="Balance Cuenta")
    ax1.step(steps, floors, where="post", color="#f85149", linewidth=2.0, linestyle="--", label="Suelo Apex (Trailing Floor)")
    ax1.axhline(APEX_RULES["profit_target"], color="#3fb950", linestyle=":", linewidth=1.5, label="Target Apex ($53,000)")
    ax1.axhline(APEX_RULES["lock_hwm"], color="#d29922", linestyle=":", linewidth=1.2, label="Freeze Trigger ($52,600)")
    ax1.fill_between(steps, floors, balances, step="post", color="#388bfd", alpha=0.15, label="Colchón Disponible")
    
    ax1.set_title("1. Equity Curve vs Suelo de Liquidación Apex", fontsize=12, color="#58a6ff", weight="bold")
    ax1.set_ylabel("USD ($)")
    ax1.set_xlabel("Número de Operaciones")
    ax1.legend(loc="upper left", fontsize=8, facecolor="#0e1117", edgecolor="#30363d")

    # -------------------------------------------------------------
    # PANEL 2: UNDERWATER DRAWDOWN & BUFFER CONSUMPTION
    # -------------------------------------------------------------
    ax2 = axs[0, 1]
    cum_arr = np.array(balances)
    peak = np.maximum.accumulate(cum_arr)
    dd = cum_arr - peak
    
    ax2.fill_between(steps, dd, 0, step="post", color="#da3633", alpha=0.45)
    ax2.step(steps, dd, where="post", color="#f85149", linewidth=1.8, label="Drawdown desde Máximos")
    ax2.axhline(-APEX_RULES["buffer"], color="#b62324", linestyle="-.", linewidth=1.5, label="Límite Fatal Buffer (-$2,000)")
    ax2.axhline(-600.5, color="#d29922", linestyle=":", linewidth=1.2, label="Max DD Histórico Auditoría (-$600.5)")
    
    ax2.set_title("2. Curva de Drawdown (Tolerancia del Buffer)", fontsize=12, color="#f85149", weight="bold")
    ax2.set_ylabel("USD ($)")
    ax2.set_xlabel("Número de Operaciones")
    ax2.legend(loc="lower left", fontsize=8, facecolor="#0e1117", edgecolor="#30363d")

    # -------------------------------------------------------------
    # PANEL 3: CONTRIBUCIÓN DE PNL POR ACTIVO
    # -------------------------------------------------------------
    ax3 = axs[1, 0]
    palette = {"MNQ": "#58a6ff", "MGC": "#d29922", "SIL": "#e6edf3", "ZB": "#bc8cff"}
    
    for sym in ["MNQ", "MGC", "SIL", "ZB"]:
        sub = df[df["symbol"] == sym].copy()
        if not sub.empty:
            sub["cum_sym"] = sub["net_pnl"].cumsum()
            ax3.plot(sub.index, sub["cum_sym"], marker="o", markersize=4, linewidth=1.8, 
                     color=palette.get(sym, "#8b949e"), label=f"{sym} (${sub['net_pnl'].sum():+,.1f})")
    
    ax3.set_title("3. Contribución de Alpha por Activo (CME Basket)", fontsize=12, color="#bc8cff", weight="bold")
    ax3.set_ylabel("PnL Acumulado ($)")
    ax3.set_xlabel("Índice de Operación Global")
    ax3.legend(loc="upper left", fontsize=8, facecolor="#0e1117", edgecolor="#30363d")

    # -------------------------------------------------------------
    # PANEL 4: DISTRIBUCIÓN DE R-MULTIPLES Y ESTADÍSTICAS
    # -------------------------------------------------------------
    ax4 = axs[1, 1]
    wins = df[df["net_pnl"] > 0]
    losses = df[df["net_pnl"] <= 0]
    
    n_wins = len(wins)
    n_losses = len(losses)
    n_tot = len(df)
    wr = (n_wins / n_tot * 100) if n_tot > 0 else 0.0
    w_sum = wins["net_pnl"].sum()
    l_sum = abs(losses["net_pnl"].sum())
    pf = (w_sum / l_sum) if l_sum > 0 else 99.0
    
    bars = ax4.bar(["Ganadoras", "Perdedoras"], [n_wins, n_losses], color=["#238636", "#da3633"], width=0.55, edgecolor="#30363d")
    for b in bars:
        height = b.get_height()
        ax4.annotate(f"{height}", xy=(b.get_x() + b.get_width() / 2, height),
                     xytext=(0, 3), textcoords="offset points", ha="center", va="bottom", color="#ffffff", weight="bold")
    
    metrics_box = (
        f"MÉTRICAS EN VIVO\n"
        f"────────────────\n"
        f"Trades Totales : {n_tot}\n"
        f"Win Rate       : {wr:.1f}%\n"
        f"Profit Factor  : {pf:.2f}\n"
        f"PnL Neto Total : ${df['net_pnl'].sum():+,.2f}\n"
        f"Colchón Vivo   : ${state['balance'] - state['floor']:,.2f}"
    )
    ax4.text(0.95, 0.95, metrics_box, transform=ax4.transAxes, verticalalignment="top", horizontalalignment="right",
             bbox=dict(boxstyle="round,pad=0.5", facecolor="#0e1117", edgecolor="#30363d", alpha=0.9),
             fontsize=9, family="monospace", color="#c9d1d9")

    ax4.set_title("4. Frecuencia de Ejecución y Ratio W/L", fontsize=12, color="#3fb950", weight="bold")
    ax4.set_ylabel("Cantidad de Trades")

    fig.suptitle(f"OUROBOROS QUANT | TEAR SHEET APEX 50K | BALANCE: ${state['balance']:,.2f}", fontsize=15, color="#ffffff", weight="bold")
    plt.tight_layout()
    plt.savefig(CHART_OUTPUT_PATH, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close()

    return CHART_OUTPUT_PATH
