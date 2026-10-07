"""
Master 6-Panel Executive Quantitative Dashboard for AlphaForge.
Renders high-resolution institutional diagnostic dashboard matching exact forensic specifications.
"""
from pathlib import Path
from typing import List, Dict, Any, Optional
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

from src.core.events import TradeRecord
from src.visualizer.styles import (
    apply_dark_theme, BG_MAIN, BG_PANEL, BG_BORDER, TEXT_PRIMARY, TEXT_SECONDARY,
    TEXT_MUTED, COLOR_PROFIT, COLOR_LOSS, COLOR_CYAN, COLOR_GOLD, COLOR_PURPLE, COLOR_FLOOR
)


class DashboardComposer:
    """Composes the master 6-panel executive forensic diagnostics dashboard."""

    @classmethod
    def render_master_dashboard(
        cls,
        trades: List[TradeRecord],
        metrics: Dict[str, Any],
        strategy_name: str,
        output_path: Path,
        initial_balance: float = 50000.0,
        trailing_max_dd: float = 2500.0,
        profit_target: float = 3000.0
    ) -> Path:
        apply_dark_theme()

        fig = plt.figure(figsize=(18, 14), dpi=180, facecolor=BG_MAIN)
        gs = gridspec.GridSpec(3, 2, figure=fig, hspace=0.32, wspace=0.22,
                               left=0.06, right=0.96, top=0.92, bottom=0.06)

        # Title and Header Banner
        sum_m = metrics.get("summary", {})
        exc_m = metrics.get("excursion", {})
        p_firm = metrics.get("prop_firm", {})
        pf_status = p_firm.get("status", "ACTIVE")
        status_color = COLOR_PROFIT if pf_status == "PASSED" else (COLOR_LOSS if "BREACH" in pf_status else COLOR_CYAN)

        header_title = f"ALPHAFORGE FORENSIC AUDIT // {strategy_name.upper()}"
        subtitle = (
            f"Trades: {sum_m.get('total_trades', 0)}  |  "
            f"Net PnL: ${sum_m.get('total_net_pnl', 0):,.2f}  |  "
            f"Win Rate: {sum_m.get('win_rate_pct', 0)}%  |  "
            f"Profit Factor: {sum_m.get('profit_factor', 0)}  |  "
            f"Expectancy: {sum_m.get('expectancy_r', 0)}R (${sum_m.get('expectancy_dollars', 0):,.2f})  |  "
            f"Drift Ratio: {exc_m.get('drift_ratio', 0)}x  |  "
            f"Prop Firm Status: [{pf_status}]"
        )
        fig.suptitle(header_title, fontsize=16, fontweight="bold", color=TEXT_PRIMARY, y=0.97, ha="left", x=0.06)
        fig.text(0.06, 0.94, subtitle, fontsize=10, color=TEXT_SECONDARY, fontweight="medium")

        # -------------------------------------------------------------
        # PANEL 1 (Top Left): Equity Curve vs. Dynamic Trailing Floor
        # -------------------------------------------------------------
        ax1 = fig.add_subplot(gs[0, 0])
        cls._plot_equity_and_floor(ax1, trades, initial_balance, trailing_max_dd, profit_target)

        # -------------------------------------------------------------
        # PANEL 2 (Top Right): Underwater Drawdown Profile ($)
        # -------------------------------------------------------------
        ax2 = fig.add_subplot(gs[0, 1])
        cls._plot_underwater_drawdown(ax2, trades, trailing_max_dd)

        # -------------------------------------------------------------
        # PANEL 3 (Mid Left): 2D MFE vs. MAE Scatter & Parity Density
        # -------------------------------------------------------------
        ax3 = fig.add_subplot(gs[1, 0])
        cls._plot_mfe_vs_mae(ax3, trades, exc_m)

        # -------------------------------------------------------------
        # PANEL 4 (Mid Right): Empirical R-Multiple Payoff Distribution
        # -------------------------------------------------------------
        ax4 = fig.add_subplot(gs[1, 1])
        cls._plot_r_distribution(ax4, trades, sum_m)

        # -------------------------------------------------------------
        # PANEL 5 (Bottom Left): Temporal PnL Attribution (By Hour)
        # -------------------------------------------------------------
        ax5 = fig.add_subplot(gs[2, 0])
        cls._plot_hourly_attribution(ax5, trades)

        # -------------------------------------------------------------
        # PANEL 6 (Bottom Right): The Death Tree Breakdown (Loss Taxonomy)
        # -------------------------------------------------------------
        ax6 = fig.add_subplot(gs[2, 1])
        cls._plot_death_tree(ax6, metrics.get("loss_taxonomy", {}))

        output_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path, facecolor=BG_MAIN, edgecolor="none")
        plt.close(fig)
        return output_path

    @classmethod
    def _plot_equity_and_floor(cls, ax, trades, initial_balance, trailing_max_dd, profit_target):
        ax.set_title("1. Equity Curve vs. Peak MTM Trailing Floor", fontsize=11, fontweight="bold", pad=8)
        if not trades:
            ax.text(0.5, 0.5, "No trade history", ha="center", va="center", color=TEXT_MUTED)
            return

        pnls = [t.net_pnl for t in trades]
        balances = [initial_balance]
        hwms = [initial_balance]
        floors = [initial_balance - trailing_max_dd]

        cur_bal = initial_balance
        cur_hwm = initial_balance
        cur_floor = initial_balance - trailing_max_dd

        for pnl in pnls:
            cur_bal += pnl
            if cur_bal > cur_hwm:
                cur_hwm = cur_bal
            new_floor = cur_hwm - trailing_max_dd
            # Check lock at +2600
            if cur_hwm >= (initial_balance + 2600.0):
                new_floor = max(new_floor, initial_balance + 100.0)
            if new_floor > cur_floor:
                cur_floor = new_floor
            balances.append(cur_bal)
            hwms.append(cur_hwm)
            floors.append(cur_floor)

        steps = np.arange(len(balances))
        ax.plot(steps, balances, color=COLOR_CYAN, lw=2.2, label="Realized Equity")
        ax.plot(steps, hwms, color=COLOR_GOLD, ls=":", lw=1.5, label="High Water Mark")
        ax.plot(steps, floors, color=COLOR_FLOOR, ls="--", lw=1.8, label="MTM Trailing Floor")
        ax.axhline(initial_balance + profit_target, color=COLOR_PROFIT, ls="-.", lw=1.5,
                   label=f"Target (${initial_balance + profit_target:,.0f})")

        ax.fill_between(steps, floors, balances, color=COLOR_CYAN, alpha=0.1, label="Cushion Buffer")
        ax.set_xlabel("Trade Number", fontsize=9, color=TEXT_SECONDARY)
        ax.set_ylabel("Account Value ($)", fontsize=9, color=TEXT_SECONDARY)
        ax.legend(loc="upper left", fontsize=8, framealpha=0.3, facecolor=BG_PANEL)
        ax.grid(True, alpha=0.25)

    @classmethod
    def _plot_underwater_drawdown(cls, ax, trades, trailing_max_dd):
        ax.set_title("2. Underwater Drawdown Profile ($)", fontsize=11, fontweight="bold", pad=8)
        if not trades:
            ax.text(0.5, 0.5, "No trade history", ha="center", va="center", color=TEXT_MUTED)
            return

        cum_pnls = np.cumsum([t.net_pnl for t in trades])
        running_peaks = np.maximum.accumulate(cum_pnls)
        drawdowns = cum_pnls - running_peaks  # negative numbers

        steps = np.arange(1, len(drawdowns) + 1)
        ax.fill_between(steps, drawdowns, 0, color=COLOR_LOSS, alpha=0.35)
        ax.plot(steps, drawdowns, color=COLOR_LOSS, lw=1.8, label="Dollar Drawdown")
        ax.axhline(-trailing_max_dd, color=COLOR_FLOOR, ls="--", lw=1.6, label=f"Breach Limit (-${trailing_max_dd:,.0f})")

        ax.set_xlabel("Trade Number", fontsize=9, color=TEXT_SECONDARY)
        ax.set_ylabel("Drawdown ($)", fontsize=9, color=TEXT_SECONDARY)
        ax.legend(loc="lower left", fontsize=8, framealpha=0.3, facecolor=BG_PANEL)
        ax.grid(True, alpha=0.25)

    @classmethod
    def _plot_mfe_vs_mae(cls, ax, trades, exc_m):
        ax.set_title("3. 2D MFE vs. MAE Scatter & Parity Density", fontsize=11, fontweight="bold", pad=8)
        if not trades:
            ax.text(0.5, 0.5, "No trade history", ha="center", va="center", color=TEXT_MUTED)
            return

        mae = [t.mae_r for t in trades]
        mfe = [t.mfe_r for t in trades]
        colors = [COLOR_PROFIT if t.net_pnl > 0 else COLOR_LOSS for t in trades]

        ax.scatter(mae, mfe, c=colors, alpha=0.75, edgecolors=BG_BORDER, s=40, zorder=3)

        max_lim = max(max(mae, default=3.0), max(mfe, default=3.0), 3.0) + 0.5
        # Parity Line Y = X
        ax.plot([0, max_lim], [0, max_lim], color=TEXT_MUTED, ls=":", lw=1.5, label="Parity (Y=X)")
        # +1.0R Threshold
        ax.axhline(1.0, color=COLOR_CYAN, ls="--", lw=1.2, label="+1.0R Line")

        drift = exc_m.get("drift_ratio", 0.0)
        disqualified = exc_m.get("is_alpha_disqualified", False)
        status_txt = "DISQUALIFIED (<1.5x)" if disqualified else "VALID EDGE (>=1.5x)"
        ax.text(0.04, 0.90, f"Drift Ratio: {drift}x [{status_txt}]",
                transform=ax.transAxes, fontsize=8.5, fontweight="bold",
                color=COLOR_LOSS if disqualified else COLOR_PROFIT,
                bbox=dict(boxstyle="round,pad=0.3", facecolor=BG_PANEL, edgecolor=BG_BORDER))

        ax.set_xlim(-0.1, max_lim)
        ax.set_ylim(-0.1, max_lim)
        ax.set_xlabel("Maximum Adverse Excursion (MAE in R)", fontsize=9, color=TEXT_SECONDARY)
        ax.set_ylabel("Maximum Favorable Excursion (MFE in R)", fontsize=9, color=TEXT_SECONDARY)
        ax.legend(loc="lower right", fontsize=8, framealpha=0.3, facecolor=BG_PANEL)
        ax.grid(True, alpha=0.25)

    @classmethod
    def _plot_r_distribution(cls, ax, trades, sum_m):
        ax.set_title("4. Empirical R-Multiple Payoff Distribution", fontsize=11, fontweight="bold", pad=8)
        if not trades:
            ax.text(0.5, 0.5, "No trade history", ha="center", va="center", color=TEXT_MUTED)
            return

        r_mults = [t.r_multiple for t in trades]
        mean_r = sum_m.get("expectancy_r", np.mean(r_mults))
        med_r = sum_m.get("median_r", np.median(r_mults))
        skew_r = sum_m.get("skewness_r", 0.0)

        counts, bins, patches = ax.hist(r_mults, bins=18, color=COLOR_CYAN, alpha=0.65, edgecolor=BG_PANEL)
        for count, patch, b in zip(counts, patches, bins):
            if b >= 0:
                patch.set_facecolor(COLOR_PROFIT)
                patch.set_alpha(0.7)
            else:
                patch.set_facecolor(COLOR_LOSS)
                patch.set_alpha(0.7)

        ax.axvline(0, color=TEXT_PRIMARY, ls="-", lw=1.5, alpha=0.8)
        ax.axvline(mean_r, color=COLOR_GOLD, ls="--", lw=1.8, label=f"Mean: {mean_r:+.2f}R")
        ax.axvline(med_r, color=COLOR_CYAN, ls=":", lw=1.8, label=f"Median: {med_r:+.2f}R")

        ax.text(0.04, 0.88, f"Skewness: {skew_r:+.2f}", transform=ax.transAxes,
                fontsize=8.5, color=TEXT_PRIMARY,
                bbox=dict(boxstyle="round,pad=0.3", facecolor=BG_PANEL, edgecolor=BG_BORDER))

        ax.set_xlabel("Realized R-Multiple", fontsize=9, color=TEXT_SECONDARY)
        ax.set_ylabel("Trade Frequency", fontsize=9, color=TEXT_SECONDARY)
        ax.legend(loc="upper right", fontsize=8, framealpha=0.3, facecolor=BG_PANEL)
        ax.grid(True, alpha=0.25)

    @classmethod
    def _plot_hourly_attribution(cls, ax, trades):
        ax.set_title("5. Temporal PnL Attribution (By Hour EST)", fontsize=11, fontweight="bold", pad=8)
        if not trades:
            ax.text(0.5, 0.5, "No trade history", ha="center", va="center", color=TEXT_MUTED)
            return

        hourly_pnl = {}
        for h in range(9, 16):
            hourly_pnl[h] = 0.0

        for t in trades:
            h = t.entry_hour_est
            if h in hourly_pnl:
                hourly_pnl[h] += t.net_pnl

        hours = list(hourly_pnl.keys())
        pnls = [hourly_pnl[h] for h in hours]
        labels = [f"{h:02d}:00" for h in hours]

        colors = [COLOR_PROFIT if p >= 0 else COLOR_LOSS for p in pnls]
        bars = ax.bar(labels, pnls, color=colors, alpha=0.85, edgecolor=BG_PANEL, width=0.6)

        ax.axhline(0, color=TEXT_MUTED, ls="-", lw=1.0)
        ax.set_xlabel("Entry Hour (EST)", fontsize=9, color=TEXT_SECONDARY)
        ax.set_ylabel("Net Realized PnL ($)", fontsize=9, color=TEXT_SECONDARY)
        ax.grid(True, alpha=0.25)

    @classmethod
    def _plot_death_tree(cls, ax, loss_data):
        ax.set_title("6. The Algorithmic Death Tree (Loss Taxonomy)", fontsize=11, fontweight="bold", pad=8)
        breakdown = loss_data.get("breakdown", {})
        if not breakdown:
            ax.text(0.5, 0.5, "Zero losses or no data", ha="center", va="center", color=COLOR_PROFIT)
            return

        cats = list(breakdown.keys())
        counts = [breakdown[c]["count"] for c in cats]
        pcts = [breakdown[c]["percentage"] for c in cats]

        y_pos = np.arange(len(cats))
        bar_colors = [COLOR_LOSS, COLOR_GOLD, COLOR_PURPLE, COLOR_CYAN][:len(cats)]

        bars = ax.barh(y_pos, counts, color=bar_colors, alpha=0.8, edgecolor=BG_PANEL, height=0.55)
        ax.set_yticks(y_pos)
        ax.set_yticklabels(cats, fontsize=8.5, color=TEXT_PRIMARY)
        ax.invert_yaxis()

        for idx, (cnt, pct) in enumerate(zip(counts, pcts)):
            ax.text(cnt + 0.3, idx, f"{cnt} ({pct:.1f}%)", va="center", fontsize=8.5, color=TEXT_SECONDARY)

        ax.set_xlabel("Frequency of Failure Mode", fontsize=9, color=TEXT_SECONDARY)
        ax.grid(True, alpha=0.25)
