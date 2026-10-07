#!/usr/bin/env python3
"""
Consolidated LLM Digest Generator for AlphaForge.
Aggregates quantitative audit artifacts and leaderboard tables into an institutional,
high-density Markdown report (reports/llm_digest.md) designed for quantitative collaborators and LLMs.
"""
import sys
import json
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))


def generate_llm_digest(
    artifacts_dir: str = "reports/artifacts",
    leaderboard_csv: str = "reports/tables/benchmark_zoo_leaderboard.csv",
    output_path: str = "reports/llm_digest.md"
) -> str:
    art_path = Path(artifacts_dir)
    lead_path = Path(leaderboard_csv)
    out_file = Path(output_path)

    # 1. Load Leaderboard if available
    leaderboard_md = ""
    if lead_path.exists():
        try:
            df_lead = pd.read_csv(lead_path)
            # Format manual markdown table
            headers = [str(c) for c in df_lead.columns]
            lines = [
                "| " + " | ".join(headers) + " |",
                "| " + " | ".join([":---"] * len(headers)) + "|"
            ]
            for _, r in df_lead.iterrows():
                row_vals = [str(r[c]) for c in df_lead.columns]
                lines.append("| " + " | ".join(row_vals) + " |")
            leaderboard_md = "\n".join(lines)
        except Exception as e:
            leaderboard_md = f"Error reading leaderboard: {e}"
    else:
        leaderboard_md = "*Benchmark zoo leaderboard table not yet generated. Run `scripts/benchmark_zoo.py`.*"

    # 2. Collect all strategy artifacts
    artifact_files = sorted(list(art_path.glob("*_audit_metrics.json")))
    strategies_data = {}

    for f in artifact_files:
        try:
            with open(f, "r") as fp:
                data = json.load(fp)
                strat_name = f.stem.replace("_audit_metrics", "")
                strategies_data[strat_name] = data
        except Exception as e:
            print(f"Warning: could not read {f}: {e}")

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Build High-Density Markdown
    md_lines = []
    md_lines.append("# ALPHAFORGE // INSTITUTIONAL QUANTITATIVE AUDIT & DIAGNOSTIC DIGEST")
    md_lines.append(f"**Generated:** `{now_utc}`  ")
    md_lines.append("**Target Instrument:** CME Micro E-mini Nasdaq-100 Futures (`MNQ`)  ")
    md_lines.append("**Account Evaluation Model:** Apex 50k Peak-Unrealized MTM Trailing Floor ($2,500 Max DD, +$3,000 Target)  ")
    md_lines.append("**Execution Friction:** CME Globex Default (1.0 tick slippage + Strict FIFO Limit Trade-Through)  ")
    md_lines.append("\n---\n")

    # Section 1: Comparative Zoo Leaderboard
    md_lines.append("## 1. Multi-Strategy Benchmark Zoo Leaderboard\n")
    md_lines.append(leaderboard_md)
    md_lines.append("\n*Status Legend:*  ")
    md_lines.append("- `APPROVED_FOR_INCUBATION`: Drift Ratio >= 1.50x, Expectancy > 0.20R, S* >= 1.5 ticks, N >= 30.  ")
    md_lines.append("- `REJECTED_ZERO_EDGE`: Drift Ratio < 1.50x or Net Expectancy <= 0.  ")
    md_lines.append("- `REJECTED_COST_SENSITIVE`: Fragile alpha collapsing under S* < 1.0 ticks.  ")
    md_lines.append("- `INSUFFICIENT_SAMPLE`: N < 30 minimum empirical trades.  ")
    md_lines.append("\n---\n")

    # Section 2: Deep-Dive Forensic Diagnostics Per Strategy
    md_lines.append("## 2. Granular Strategy Forensic Audits\n")

    if not strategies_data:
        md_lines.append("*No strategy audit artifacts found in reports/artifacts/.*")
    else:
        for strat_name, data in strategies_data.items():
            s = data.get("summary", {})
            e = data.get("excursion", {})
            lt = data.get("loss_taxonomy", {})
            ff = data.get("friction_frontier", {})
            pf = data.get("prop_firm", {})
            mc = data.get("monte_carlo", {})

            trades = s.get("total_trades", 0)
            drift = e.get("drift_ratio", 0.0)
            exp_r = s.get("expectancy_r", 0.0)
            s_star = ff.get("critical_slippage_s_star", 0.0)

            # Determine Verdict
            if trades < 30:
                verdict = f"⚠️ INSUFFICIENT_SAMPLE (N = {trades} / 30 minimum)"
                verdict_badge = "INSUFFICIENT_DATA"
            elif drift < 1.50:
                verdict = "❌ REJECTED_ZERO_EDGE (Drift Ratio < 1.50x minimum edge threshold)"
                verdict_badge = "REJECTED_ZERO_EDGE"
            elif exp_r <= 0:
                verdict = "❌ REJECTED_ZERO_EDGE (Negative Net Expectancy)"
                verdict_badge = "REJECTED_ZERO_EDGE"
            elif str(s_star) != "> 3.0" and float(s_star) < 1.0:
                verdict = f"❌ REJECTED_COST_SENSITIVE (Critical Slippage S* = {s_star} < 1.0 ticks)"
                verdict_badge = "REJECTED_COST_SENSITIVE"
            else:
                verdict = "✅ APPROVED_FOR_INCUBATION (Statistically robust edge & positive expectancy)"
                verdict_badge = "APPROVED_FOR_INCUBATION"

            md_lines.append(f"### Strategy: `{strat_name}`")
            md_lines.append(f"**Audit Verdict:** `{verdict_badge}` — {verdict}\n")

            # KPI Grid
            md_lines.append("#### Performance & Statistical Guardrails")
            md_lines.append("| Metric | Value | Statistical Assessment |")
            md_lines.append("| :--- | :--- | :--- |")
            md_lines.append(f"| **Sample Size (N)** | `{trades} trades` | {'⚠️ Insufficient (N < 30)' if trades < 30 else '✅ Sufficient (N >= 30)'} |")
            md_lines.append(f"| **Win Rate** | `{s.get('win_rate_wilson_ci_str', str(s.get('win_rate_pct')) + '%')}` | 95% Wilson Score Interval |")
            md_lines.append(f"| **Net Realized PnL** | `${s.get('total_net_pnl', 0):,.2f}` | Gross: `${s.get('total_gross_pnl', 0):,.2f}` / Fees: `${s.get('total_fees_paid', 0):,.2f}` |")
            md_lines.append(f"| **Expectancy (R)** | `{s.get('expectancy_r_ci_str', str(exp_r) + 'R')}` | Bootstrap 1,000 resamples (± SE) |")
            md_lines.append(f"| **Profit Factor** | `{s.get('profit_factor', 0)}` | Win/Loss Payoff: `{s.get('win_loss_payoff_ratio', 0)}x` |")
            md_lines.append(f"| **Sharpe / Sortino** | `{s.get('sharpe_ratio', 0)} / {s.get('sortino_ratio', 0)}` | Annualized intraday |")
            md_lines.append(f"| **Max Realized DD** | `${s.get('max_drawdown_dollars', 0):,.2f}` | Peak-to-Trough |")
            md_lines.append("")

            # Alpha Quality & Excursion
            md_lines.append("#### Alpha Edge & Excursion Quality")
            md_lines.append(f"- **Directional Drift Ratio:** `{drift}x` ({'✅ PASS (>= 1.5x)' if drift >= 1.5 else '❌ DISQUALIFIED (< 1.5x)'})")
            md_lines.append(f"- **Median MFE / MAE:** `{e.get('median_mfe_r', 0)}R` favorable / `{e.get('median_mae_r', 0)}R` adverse")
            md_lines.append(f"- **Time-to-Peak MFE:** `{e.get('median_time_to_peak_mfe', 0)} bars` (median holding time to peak favorable price)")
            md_lines.append(f"- **Excursion Efficiency:** `{e.get('excursion_efficiency', 0):.3f}` (fraction of peak favorable run realized at exit)")
            md_lines.append("")

            # The Death Tree Breakdown
            md_lines.append("#### The Algorithmic Death Tree (Loss Taxonomy)")
            total_losses = lt.get("total_losses", 0)
            breakdown = lt.get("breakdown", {})
            if total_losses == 0:
                md_lines.append("*Zero losing trades recorded in this sample.*")
            else:
                md_lines.append(f"Total Losses Dissected: **{total_losses}**")
                md_lines.append("| Failure Mode | Count | Pct Share | Total Loss ($) | Diagnostic Meaning |")
                md_lines.append("| :--- | :--- | :--- | :--- | :--- |")
                for cat_name, b_info in breakdown.items():
                    meaning = {
                        "Immediate Flush": "SL hit within 6 bars (MFE < 0.35R) -> Toxic entry timing",
                        "Trapped Trade": "MFE >= 0.80R before collapsing -> Greed / poor target geometry",
                        "Friction Drain": "Gross PnL > 0, Net <= 0 -> Commissions & slippage ate stop",
                        "Structural Invalidation": "Orderly stop violation -> Clean invalidation"
                    }.get(cat_name, "Unclassified")
                    md_lines.append(
                        f"| **{cat_name}** | `{b_info['count']}` | `{b_info['percentage']}%` | `-${b_info['total_loss_dollars']:,.2f}` | {meaning} |"
                    )
            md_lines.append("")

            # Friction Frontier & S*
            md_lines.append("#### Friction Frontier & Critical Slippage (S*)")
            md_lines.append(f"- **Critical Slippage S*:** `{s_star} ticks` (Break-even slippage where Net Expectancy drops to 0)")
            table = ff.get("frontier_table", [])
            if table:
                md_lines.append("| Slippage (Ticks) | Net PnL ($) | Expectancy ($) | Expectancy (R) | Win Rate % |")
                md_lines.append("| :--- | :--- | :--- | :--- | :--- |")
                for row in table:
                    md_lines.append(
                        f"| `{row['slippage_ticks']} ticks` | `${row['total_net_pnl']:,.2f}` | `${row['expectancy_dollars']:.2f}` | `{row['expectancy_r']:+.3f}R` | `{row['win_rate_pct']}%` |"
                    )
            md_lines.append("")

            # Prop Firm Monte Carlo
            md_lines.append("#### Prop-Firm Evaluation & Monte Carlo (10,000 Paths)")
            if mc.get("is_suppressed"):
                md_lines.append(f"- **Status:** `SUPPRESSED` — {mc.get('warning')}")
            else:
                md_lines.append(f"- **Probability of Passing Target (+$3,000):** `{mc.get('prob_pass_pct', 0)}%`")
                md_lines.append(f"- **Probability of Trailing Floor Breach (-$2,500):** `{mc.get('prob_breach_pct', 0)}%`")
                md_lines.append(f"- **Median Trades to Pass Target:** `{mc.get('median_trades_to_pass', 'N/A')}`")
            md_lines.append(f"- **Final Account Balance:** `${pf.get('current_balance', 0):,.2f}` (Floor: `${pf.get('trailing_floor', 0):,.2f}`)")

            # Multi-Strategy Portfolio Analytics (if available)
            pa = data.get("portfolio_analytics")
            if pa:
                md_lines.append("")
                md_lines.append("#### Multi-Strategy Portfolio Allocation & Diversification")
                md_lines.append(f"- **Diversification Ratio:** `{pa.get('diversification_ratio', 1.0)}`")
                md_lines.append(f"- **Strategy Trade Breakdown:** `{pa.get('strategy_trade_counts', {})}`")
                md_lines.append(f"- **Daily Volatilities:** `{pa.get('daily_volatility_by_strategy', {})}`")
                md_lines.append("- **Inter-Strategy Correlation Matrix:**")
                corr = pa.get("correlation_matrix", {})
                for k1, v1 in corr.items():
                    md_lines.append(f"  - `{k1}`: `{v1}`")

            md_lines.append("\n---\n")

    content = "\n".join(md_lines)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w") as fp:
        fp.write(content)

    print(f"-> Generated consolidated LLM digest: {out_file} ({len(content)} bytes)")
    return content


if __name__ == "__main__":
    generate_llm_digest()
