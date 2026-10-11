import os
from pathlib import Path
import numpy as np
import pandas as pd

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except (ImportError, ModuleNotFoundError):
    HAS_MATPLOTLIB = False

from live.config import APEX_RULES

CHART_OUTPUT_PATH = Path("reports/daily_performance_tearsheet.png")
JOURNAL_FILE = Path("reports/paper_trading_journal.csv")


def generate_daily_chart(state: dict) -> Path:
    """
    Genera el Tearsheet Ejecutivo de 4 Paneles para la estrategia campeona Apex 50k v3.0:
      - Panel 1: Curva de Balance vs Suelo de Liquidación Apex (Trailing Floor y Floor Congelado).
      - Panel 2: Underwater Drawdown vs Límite Fatal de Buffer ($2,500).
      - Panel 3: Contribución de Alpha Acumulada por Activo (QQQ / MNQ).
      - Panel 4: Distribución Win/Loss, Tasa de Acierto (Win Rate) y Profit Factor.
    """
    CHART_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    if not HAS_MATPLOTLIB:
        print("⚠️ [REPORTER] Matplotlib no está disponible en este intérprete. Guardando estado placeholder.")
        if not CHART_OUTPUT_PATH.exists():
            CHART_OUTPUT_PATH.write_bytes(b"")
        return CHART_OUTPUT_PATH

    plt.style.use("dark_background")
    fig, axs = plt.subplots(2, 2, figsize=(16, 10), dpi=200)
    fig.patch.set_facecolor("#0e1117")
    for ax in axs.flat:
        ax.set_facecolor("#161b22")
        ax.grid(True, linestyle="--", alpha=0.25, color="#8b949e")

    buffer_limit = float(APEX_RULES.get("buffer", 2500.0))

    if not JOURNAL_FILE.exists() or os.stat(JOURNAL_FILE).st_size == 0:
        fig.suptitle("OUROBOROS QUANT: ESTADO DE INICIALIZACIÓN (APEX SPRINT CHAMPION v3.0)", fontsize=16, color="#58a6ff", weight="bold")
        cushion = state['balance'] - state['floor']
        axs[0, 0].text(
            0.5, 0.5,
            f"Balance Inicial : ${state['balance']:,.2f}\n"
            f"Suelo Apex      : ${state['floor']:,.2f}\n"
            f"Colchón Vivo    : ${cushion:,.2f}\n"
            f"Estado Suelo    : {'CONGELADO ($50,100)' if state.get('frozen') else 'TRAILING DINÁMICO'}",
            ha="center", va="center", color="#c9d1d9", fontsize=14, family="monospace"
        )
        plt.tight_layout()
        plt.savefig(CHART_OUTPUT_PATH, facecolor=fig.get_facecolor(), edgecolor="none")
        plt.close()
        return CHART_OUTPUT_PATH

    try:
        df = pd.read_csv(JOURNAL_FILE)
    except Exception:
        df = pd.DataFrame()

    if df.empty or "balance_after" not in df.columns:
        fig.suptitle("OUROBOROS QUANT: ESPERANDO PRIMERA OPERACIÓN", fontsize=16, color="#58a6ff", weight="bold")
        plt.tight_layout()
        plt.savefig(CHART_OUTPUT_PATH, facecolor=fig.get_facecolor(), edgecolor="none")
        plt.close()
        return CHART_OUTPUT_PATH

    df["dt"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("dt").reset_index(drop=True)

    balances = [APEX_RULES["starting_balance"]] + list(df["balance_after"])
    floors = [APEX_RULES["initial_floor"]] + list(df["floor_after"])
    steps = list(range(len(balances)))

    # PANEL 1: EQUITY VS SUELO DE LIQUIDACIÓN
    ax1 = axs[0, 0]
    ax1.step(steps, balances, where="post", color="#58a6ff", linewidth=2.2, label="Balance Cuenta")
    ax1.step(steps, floors, where="post", color="#f85149", linewidth=2.0, linestyle="--", label="Suelo Apex (Trailing Floor)")
    ax1.axhline(APEX_RULES["profit_target"], color="#3fb950", linestyle=":", linewidth=1.5, label=f"Target Apex (${APEX_RULES['profit_target']:,.0f})")
    ax1.axhline(APEX_RULES["lock_hwm"], color="#d29922", linestyle=":", linewidth=1.2, label=f"Freeze Trigger (${APEX_RULES['lock_hwm']:,.0f})")
    ax1.fill_between(steps, floors, balances, step="post", color="#388bfd", alpha=0.15, label="Colchón Disponible (D_t)")
    ax1.set_title("1. Equity Curve vs Suelo de Liquidación Apex", fontsize=12, color="#58a6ff", weight="bold")
    ax1.set_ylabel("USD ($)")
    ax1.set_xlabel("Número de Operaciones")
    ax1.legend(loc="upper left", fontsize=8, facecolor="#0e1117", edgecolor="#30363d")

    # PANEL 2: UNDERWATER DRAWDOWN
    ax2 = axs[0, 1]
    cum_arr = np.array(balances)
    peak = np.maximum.accumulate(cum_arr)
    dd = cum_arr - peak
    ax2.fill_between(steps, dd, 0, step="post", color="#da3633", alpha=0.45)
    ax2.step(steps, dd, where="post", color="#f85149", linewidth=1.8, label="Drawdown desde Máximos")
    ax2.axhline(-buffer_limit, color="#b62324", linestyle="-.", linewidth=1.5, label=f"Límite Fatal Buffer (-${buffer_limit:,.0f})")
    ax2.set_title("2. Curva de Drawdown (Tolerancia de Buffer)", fontsize=12, color="#f85149", weight="bold")
    ax2.set_ylabel("USD ($)")
    ax2.set_xlabel("Número de Operaciones")
    ax2.legend(loc="lower left", fontsize=8, facecolor="#0e1117", edgecolor="#30363d")

    # PANEL 3: CONTRIBUCIÓN DE ALPHA POR ACTIVO
    ax3 = axs[1, 0]
    symbols = df["symbol"].unique()
    palette = ["#58a6ff", "#3fb950", "#bc8cff", "#d29922", "#f0883e"]
    for i, sym in enumerate(symbols):
        sub = df[df["symbol"] == sym].copy()
        if not sub.empty:
            sub["cum_sym"] = sub["net_pnl"].cumsum()
            color = palette[i % len(palette)]
            ax3.plot(sub.index + 1, sub["cum_sym"], marker="o", markersize=4, linewidth=1.8,
                     color=color, label=f"{sym} (${sub['net_pnl'].sum():+,.2f})")
    ax3.set_title("3. Contribución de PnL por Activo", fontsize=12, color="#bc8cff", weight="bold")
    ax3.set_ylabel("PnL Acumulado ($)")
    ax3.set_xlabel("Índice de Operación")
    ax3.legend(loc="upper left", fontsize=8, facecolor="#0e1117", edgecolor="#30363d")

    # PANEL 4: WIN/LOSS & MÉTRICAS
    ax4 = axs[1, 1]
    wins = df[df["net_pnl"] > 0]
    losses = df[df["net_pnl"] <= 0]
    n_wins = len(wins)
    n_losses = len(losses)
    n_tot = len(df)
    wr = (n_wins / n_tot * 100.0) if n_tot > 0 else 0.0
    w_sum = wins["net_pnl"].sum()
    l_sum = abs(losses["net_pnl"].sum())
    pf = (w_sum / l_sum) if l_sum > 0 else 99.0

    bars = ax4.bar(["Ganadoras", "Perdedoras"], [n_wins, n_losses], color=["#238636", "#da3633"], width=0.55, edgecolor="#30363d")
    for b in bars:
        height = b.get_height()
        ax4.annotate(f"{height}", xy=(b.get_x() + b.get_width() / 2, height),
                     xytext=(0, 3), textcoords="offset points", ha="center", va="bottom", color="#ffffff", weight="bold")

    metrics_box = (
        f"MÉTRICAS EN VIVO v3.0\n"
        f"─────────────────────\n"
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

    fig.suptitle(f"OUROBOROS QUANT | TEARSHEET APEX 50K v3.0 | BALANCE: ${state['balance']:,.2f}", fontsize=15, color="#ffffff", weight="bold")
    plt.tight_layout()
    plt.savefig(CHART_OUTPUT_PATH, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close()

    return CHART_OUTPUT_PATH
