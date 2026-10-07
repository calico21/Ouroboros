"""
Dedicated Diagnostic Component Visualizations for AlphaForge.
Renders Monte Carlo Survival Cone, Slippage Decay Curve, and Time-Decay Excursion Profile.
"""
from pathlib import Path
from typing import List, Dict, Any
import numpy as np
import matplotlib.pyplot as plt

from src.core.events import TradeRecord
from src.visualizer.styles import (
    apply_dark_theme, BG_MAIN, BG_PANEL, TEXT_PRIMARY, TEXT_SECONDARY,
    COLOR_PROFIT, COLOR_LOSS, COLOR_CYAN, COLOR_GOLD, COLOR_PURPLE, COLOR_FLOOR
)


class ComponentPlotter:
    """Renders standalone institutional component charts saved to reports/visuals/components/."""

    @classmethod
    def plot_monte_carlo_cone(cls, mc_results: Dict[str, Any], output_path: Path) -> Path:
        """Plots equity percentile cone (5th, 25th, 50th, 75th, 95th) against floor."""
        apply_dark_theme()
        fig, ax = plt.subplots(figsize=(10, 5.5), dpi=200)

        if mc_results.get("is_suppressed"):
            ax.text(
                0.5, 0.5,
                f"MONTE CARLO SUPPRESSED\n\n{mc_results.get('status')}\n\nRequires N >= 15 trades to avoid false confidence",
                ha="center", va="center", color=COLOR_LOSS, fontsize=12, fontweight="bold",
                bbox=dict(boxstyle="round,pad=1.0", facecolor=BG_PANEL, edgecolor=COLOR_LOSS)
            )
            ax.set_title("Prop-Firm Monte Carlo Survival Simulation (Gated)", fontsize=12, fontweight="bold", pad=12)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            plt.tight_layout()
            plt.savefig(output_path, facecolor=BG_MAIN)
            plt.close(fig)
            return output_path

        curves = mc_results.get("percentile_curves", {})
        if not curves:
            plt.close(fig)
            return output_path

        p5 = np.array(curves["p5"])
        p25 = np.array(curves["p25"])
        p50 = np.array(curves["p50"])
        p75 = np.array(curves["p75"])
        p95 = np.array(curves["p95"])
        steps = np.arange(len(p50))

        # Shaded percentile bands
        ax.fill_between(steps, p5, p95, color=COLOR_CYAN, alpha=0.15, label="5th - 95th Percentile")
        ax.fill_between(steps, p25, p75, color=COLOR_CYAN, alpha=0.35, label="25th - 75th Percentile")
        ax.plot(steps, p50, color=COLOR_CYAN, lw=2.2, label="Median Path (50th)")

        # Target and floor
        target = mc_results.get("target_balance", 53000.0)
        floor = mc_results.get("initial_floor", 47500.0)
        ax.axhline(target, color=COLOR_PROFIT, ls="--", lw=1.8, label=f"Profit Target (${target:,.0f})")
        ax.axhline(floor, color=COLOR_FLOOR, ls="--", lw=1.8, label=f"Initial Floor (${floor:,.0f})")

        ax.set_title(
            f"Prop-Firm Monte Carlo Survival Cone (10k Iterations)\n"
            f"P(Pass) = {mc_results.get('prob_pass_pct', 0)}%  |  "
            f"P(Breach) = {mc_results.get('prob_breach_pct', 0)}%  |  "
            f"Median Trades to Pass: {mc_results.get('median_trades_to_pass', 'N/A')}",
            fontsize=12, fontweight="bold", pad=12, color=TEXT_PRIMARY
        )
        ax.set_xlabel("Trade Sequence Step", fontsize=10, color=TEXT_SECONDARY)
        ax.set_ylabel("Account Balance ($)", fontsize=10, color=TEXT_SECONDARY)
        ax.legend(loc="upper left", framealpha=0.3, facecolor=BG_PANEL, edgecolor="#374151")
        ax.grid(True, alpha=0.25)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        plt.tight_layout()
        plt.savefig(output_path, facecolor=BG_MAIN)
        plt.close(fig)
        return output_path

    @classmethod
    def plot_slippage_decay(cls, friction_data: Dict[str, Any], output_path: Path) -> Path:
        """Plots net expectancy and dollar PnL degradation across slippage ticks."""
        apply_dark_theme()
        fig, ax1 = plt.subplots(figsize=(9, 5), dpi=200)

        table = friction_data.get("frontier_table", [])
        if not table:
            plt.close(fig)
            return output_path

        slips = [row["slippage_ticks"] for row in table]
        exp_dollars = [row["expectancy_dollars"] for row in table]
        exp_r = [row["expectancy_r"] for row in table]

        color_exp = COLOR_CYAN
        ax1.set_xlabel("Slippage Per Side (Ticks @ 0.25 pt)", fontsize=10, color=TEXT_SECONDARY)
        ax1.set_ylabel("Net Expectancy ($/Trade)", color=color_exp, fontsize=10)
        line1 = ax1.plot(slips, exp_dollars, color=color_exp, marker="o", lw=2, label="Expectancy ($)")
        ax1.axhline(0, color=COLOR_LOSS, ls=":", lw=1.5, alpha=0.8)
        ax1.tick_params(axis="y", labelcolor=color_exp)

        ax2 = ax1.twinx()
        color_r = COLOR_GOLD
        ax2.set_ylabel("Expectancy (R-Multiple)", color=color_r, fontsize=10)
        line2 = ax2.plot(slips, exp_r, color=color_r, marker="s", lw=2, ls="--", label="Expectancy (R)")
        ax2.tick_params(axis="y", labelcolor=color_r)

        s_star = friction_data.get("critical_slippage_s_star", "N/A")
        plt.title(
            f"Friction Frontier: Slippage Decay & Critical Slippage S*\nBreak-Even S* = {s_star} ticks",
            fontsize=12, fontweight="bold", pad=12, color=TEXT_PRIMARY
        )
        ax1.grid(True, alpha=0.25)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        plt.tight_layout()
        plt.savefig(output_path, facecolor=BG_MAIN)
        plt.close(fig)
        return output_path

    @classmethod
    def plot_time_decay_excursion(cls, trades: List[TradeRecord], output_path: Path) -> Path:
        """Plots holding time (bars) vs MFE progression and time-to-peak."""
        apply_dark_theme()
        fig, ax = plt.subplots(figsize=(9, 5), dpi=200)

        if not trades:
            plt.close(fig)
            return output_path

        bars = [t.bars_held for t in trades]
        mfe_r = [t.mfe_r for t in trades]
        peak_bars = [t.time_to_peak_mfe for t in trades]
        colors = [COLOR_PROFIT if t.net_pnl > 0 else COLOR_LOSS for t in trades]

        ax.scatter(bars, mfe_r, c=colors, alpha=0.75, edgecolors="#1F2937", s=45, label="Trades (MFE_R)")
        ax.scatter(peak_bars, mfe_r, c=COLOR_GOLD, marker="x", alpha=0.6, s=35, label="Peak Bar Attained")

        ax.set_title("Time-Decay Excursion Profile (Bars Held vs MFE_R)", fontsize=12, fontweight="bold", pad=12)
        ax.set_xlabel("Bars Elapsed", fontsize=10, color=TEXT_SECONDARY)
        ax.set_ylabel("Maximum Favorable Excursion (R-Units)", fontsize=10, color=TEXT_SECONDARY)
        ax.axhline(1.0, color=COLOR_CYAN, ls="--", lw=1.2, label="+1.0R Threshold")
        ax.legend(loc="upper right", framealpha=0.3, facecolor=BG_PANEL, edgecolor="#374151")
        ax.grid(True, alpha=0.25)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        plt.tight_layout()
        plt.savefig(output_path, facecolor=BG_MAIN)
        plt.close(fig)
        return output_path
