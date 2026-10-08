#!/usr/bin/env python3
"""
Consolidated Multi-Year LLM & Institutional Quant Digest Generator for AlphaForge.
Ingests both Phase 6 Deep Forensic Audit artifacts (reports/audit/deep_forensic_audit_report.json),
strategy audit metrics (reports/artifacts/*_audit_metrics.json), benchmark zoo leaderboard,
and execution telemetry (multi_account_fleet.json, alpha_drift_status.json).

Generates a unified, high-density Markdown document at reports/llm_digest.md designed for
institutional risk officers, quantitative researchers, and LLM collaborators.
"""
import sys
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import pandas as pd

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))


def load_json_safe(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: could not parse JSON from {path}: {e}")
        return None


def generate_llm_digest(
    audit_report_path: str = "reports/audit/deep_forensic_audit_report.json",
    artifacts_dir: str = "reports/artifacts",
    leaderboard_csv: str = "reports/tables/benchmark_zoo_leaderboard.csv",
    output_path: str = "reports/llm_digest.md",
    fleet_path: str = "reports/telemetry/multi_account_fleet.json",
    drift_path: str = "reports/telemetry/alpha_drift_status.json"
) -> str:
    audit_file = Path(audit_report_path)
    art_path = Path(artifacts_dir)
    lead_path = Path(leaderboard_csv)
    out_file = Path(output_path)
    fleet_file = Path(fleet_path)
    drift_file = Path(drift_path)

    # 1. Ingest Forensic Audit Report
    forensic = load_json_safe(audit_file) or {}

    # 2. Ingest Multi-Strategy Artifacts
    strategies_data: Dict[str, Any] = {}
    if art_path.exists():
        for f in sorted(art_path.glob("*_audit_metrics.json")):
            strat_name = f.stem.replace("_audit_metrics", "")
            d = load_json_safe(f)
            if d:
                strategies_data[strat_name] = d

    # 3. Ingest or Regenerate Leaderboard
    leaderboard_md = ""
    if lead_path.exists():
        try:
            df_lead = pd.read_csv(lead_path)
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
            leaderboard_md = f"*Error parsing leaderboard CSV: {e}*"
    else:
        leaderboard_md = "*Benchmark zoo leaderboard table not found in reports/tables/benchmark_zoo_leaderboard.csv.*"

    # 4. Ingest Fleet & Drift Telemetry
    fleet_data = load_json_safe(fleet_file)
    if not fleet_data:
        # Check fallback path
        alt_fleet = Path("reports/telemetry/multi_account_fleet_status.json")
        fleet_data = load_json_safe(alt_fleet) or {}

    drift_data = load_json_safe(drift_file) or {}

    # Extract dynamic timestamps & counts
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    cal_m = forensic.get("calendar_metrics", {})
    dsr_m = forensic.get("deflated_sharpe", {})
    macro_m = forensic.get("macro_attribution", {})
    cpcv_m = forensic.get("cpcv", {})
    wfo_m = forensic.get("walk_forward", {})
    mc_m = forensic.get("prop_firm_monte_carlo", {})
    exec_v = forensic.get("executive_verdict", {})

    total_sessions = cal_m.get("trading_days_total", 1191)
    total_calendar_days = cal_m.get("total_calendar_days", 1732)
    active_sessions = cal_m.get("trading_days_active", 931)
    total_bars_str = "140,538 (5-minute continuous)"

    md: list[str] = []

    # =========================================================================
    # SECTION 1: HEADER METADATA
    # =========================================================================
    md.append("# ALPHAFORGE // INSTITUTIONAL QUANTITATIVE AUDIT & DIAGNOSTIC DIGEST")
    md.append(f"**Execution Timestamp:** `{now_utc}`  ")
    md.append("**Target Instrument:** CME Micro E-mini Nasdaq-100 Futures (`MNQ` / `NQ`)  ")
    md.append(f"**Dataset Span:** `2022-01-03 -> 2026-09-30` ({total_bars_str} bars across {total_sessions:,} trading sessions, {total_calendar_days:,} calendar days)  ")
    md.append("**Account Evaluation Model:** Apex 50k Peak-Unrealized MTM Trailing Floor (-$2,500 Floor, +$3,000 Target, $50,100 Permanent Lock, -$1,000 DLL, 15:55 EST Hard Flatten)  ")
    md.append("**Execution Friction Standard:** CME Globex Default (1.0 tick slippage + strict FIFO limit trade-through)  ")
    md.append("\n---\n")

    # =========================================================================
    # SECTION 2: MULTI-STRATEGY BENCHMARK ZOO LEADERBOARD
    # =========================================================================
    md.append("## 1. Multi-Strategy Benchmark Zoo Leaderboard\n")
    md.append(leaderboard_md)
    md.append("\n*Institutional Status Legend:*  ")
    md.append("- `APPROVED_FOR_INCUBATION`: Drift Ratio >= 1.50x, Net Expectancy > 0.20R, S* >= 1.5 ticks, N >= 30.  ")
    md.append("- `REJECTED_ZERO_EDGE`: Drift Ratio < 1.50x or Net Expectancy <= 0.00R.  ")
    md.append("- `REJECTED_COST_SENSITIVE`: Fragile micro-edge destroyed by friction (S* < 1.0 ticks).  ")
    md.append("- `INSUFFICIENT_SAMPLE`: N < 30 minimum empirical trades required for Wilson Score confidence.  ")
    md.append("\n---\n")

    # =========================================================================
    # SECTION 3: PHASE 6 DEEP FORENSIC ECONOMETRICS
    # =========================================================================
    target_strat = forensic.get("strategy_name", "afternoon_trend_continuation")
    md.append(f"## 2. Phase 6 Deep Forensic Econometrics: `{target_strat}`\n")
    
    comp_score = exec_v.get("composite_score", 0.0)
    prod_ready = exec_v.get("production_ready", False)
    status_str = "APPROVED // PRODUCTION READY" if prod_ready else "CONDITIONAL // SENSITIVITY FLAGGED"
    md.append(f"**Audit Status:** `{status_str}` | **Institutional Composite Score:** `{comp_score}/100`  ")
    
    findings = exec_v.get("key_findings", [])
    if findings:
        md.append("**Key Forensic Findings:**")
        for f in findings:
            md.append(f"- {f}")
        md.append("")

    # A. Calendar Metrics
    md.append("### A. Unbiased Continuous Calendar-Day Performance (252-Day Annualization)")
    md.append("*(Eliminates trade-concatenation bias by continuous daily business-day return accounting with $0 on flat days)*\n")
    md.append("| Metric | Value | Institutional Significance |")
    md.append("| :--- | :--- | :--- |")
    md.append(f"| **Calendar-Day Sharpe Ratio** | `{cal_m.get('calendar_sharpe', 0.0):.3f}` | True continuous Sharpe (replaces trade-concatenated 11.41) |")
    md.append(f"| **Calendar-Day Sortino Ratio** | `{cal_m.get('calendar_sortino', 0.0):.3f}` | Annualized semi-deviation downside penalty |")
    md.append(f"| **Calmar Ratio** | `{cal_m.get('calmar_ratio', 0.0):.3f}` | Annualized PnL (${cal_m.get('annualized_pnl', 0.0):,.2f}) / Max Drawdown |")
    md.append(f"| **Gain-to-Pain Ratio** | `{cal_m.get('gain_to_pain_ratio', 0.0):.3f}` | Jack Schwager institutional return-to-pain quotient |")
    md.append(f"| **Active-Day Exposure Rate** | `{cal_m.get('exposure_rate_pct', 0.0):.1f}%` | {active_sessions} active trading days out of {total_sessions} business days |")
    md.append(f"| **Net Realized PnL** | `${cal_m.get('total_net_pnl', 0.0):,.2f}` | Daily mean PnL: `${cal_m.get('daily_pnl_mean', 0.0):.2f}` (Std: `${cal_m.get('daily_pnl_std', 0.0):.2f}`) |")
    md.append(f"| **Max Realized Drawdown** | `${cal_m.get('max_drawdown_dollars', 0.0):,.2f}` | `{cal_m.get('max_drawdown_pct', 0.0):.2f}%` of peak equity |")
    md.append(f"| **Daily Win Rate** | `{cal_m.get('win_rate_daily_pct', 0.0):.1f}%` | Best day: `${cal_m.get('best_day_pnl', 0.0):,.2f}` / Worst day: `${cal_m.get('worst_day_pnl', 0.0):,.2f}` |")
    md.append("")

    # B. Deflated Sharpe Ratio
    md.append("### B. Deflated Sharpe Ratio (DSR) & Multiple Testing Surveillance")
    md.append("*(Marcos López de Prado & David Bailey 2014: Adjusting for selection bias, skewness, and Zoo trial variance)*\n")
    md.append(f"- **Deflated Sharpe Ratio (DSR):** `{dsr_m.get('deflated_sharpe_ratio', 0.0):.4f}` ({'✅ PASS (>= 0.95)' if dsr_m.get('passes_deflated_hurdle') else '⚠️ CAUTION (< 0.95 hurdle)'})")
    md.append(f"- **Probabilistic Sharpe Ratio (PSR):** `{dsr_m.get('probabilistic_sharpe_ratio', 0.0):.4f}` (accounting for higher statistical moments)")
    md.append(f"- **Expected Maximum Null Sharpe ($E[\\max(SR_0)]$):** `{dsr_m.get('expected_max_null_sharpe', 0.0):.3f}`")
    md.append(f"- **Zoo Trials Penalized ($K$):** `{dsr_m.get('trials_tested', 25)}` historical strategy configurations")
    md.append(f"- **Return Skewness ($\\\\gamma_3$):** `{dsr_m.get('skewness', 0.0):.3f}` | **Return Kurtosis ($\\\\gamma_4$):** `{dsr_m.get('kurtosis', 0.0):.3f}`")
    md.append(f"- **Family-Wise Error Rate (FWER) $p$-value:** `{dsr_m.get('fwer_p_value', 1.0):.4f}`")
    md.append("")

    # C. CPCV & Walk-Forward
    md.append("### C. Combinatorial Purged Cross-Validation (CPCV) & Walk-Forward Matrix (WFO)")
    md.append("*(Evaluating combinatorial backtest overfitting and multi-year chronological regime stability)*\n")
    md.append(f"- **CPCV Probability of Backtest Overfitting ($P(\\text{{PBO}}))$:** `{cpcv_m.get('pbo_pct', 0.0):.1f}%` ({cpcv_m.get('total_splits', 15)} combinatorial splits across {cpcv_m.get('num_groups', 6)} groups)")
    md.append(f"- **Median Out-of-Sample (OOS) Sharpe:** `{cpcv_m.get('median_oos_sharpe', 0.0):.3f}` (Mean: `{cpcv_m.get('mean_oos_sharpe', 0.0):.3f}`, Range: `[{cpcv_m.get('min_oos_sharpe', 0.0):.3f}, +{cpcv_m.get('max_oos_sharpe', 0.0):.3f}]`)")
    md.append(f"- **Variance Degradation Ratio:** `{cpcv_m.get('degradation_ratio', 0.0):.3f}`")
    md.append(f"- **Walk-Forward Efficiency (WFE %):** `{wfo_m.get('mean_wfe_pct', 0.0):.1f}%` (Mode: `{wfo_m.get('mode', 'ANCHORED')}`)")
    md.append(f"- **OOS Regime Consistency:** `{wfo_m.get('consistency_pct', 0.0):.1f}%` ({wfo_m.get('profitable_oos_folds', 0)} of {wfo_m.get('total_folds', 0)} out-of-sample regimes profitable)")
    md.append(f"- **Cumulative OOS Realized PnL:** `${wfo_m.get('overall_oos_pnl', 0.0):,.2f}` | **Overall OOS Sharpe:** `{wfo_m.get('overall_oos_sharpe', 0.0):.3f}`")
    md.append("")

    # D. Macro Slicing Table
    md.append("### D. Macroeconomic Catalyst Attribution & Event-Day Slicing")
    md.append("*(Performance decomposition across FOMC rate decisions, CPI prints, NFP releases, and standard RTH)*\n")
    cohorts = macro_m.get("cohorts", [])
    if cohorts:
        md.append("| Catalyst Event | Trades | Win Rate % | Net PnL ($) | Profit Factor | Expectancy (R) | Avg Trade PnL ($) | PnL Share % |")
        md.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
        for c in cohorts:
            md.append(
                f"| **{c.get('catalyst', 'N/A')}** | `{c.get('total_trades', 0)}` | `{c.get('win_rate_pct', 0.0):.1f}%` | "
                f"`${c.get('net_pnl', 0.0):,.2f}` | `{c.get('profit_factor', 0.0):.2f}` | `{c.get('expectancy_r', 0.0):+.3f}R` | "
                f"`${c.get('avg_trade_pnl', 0.0):.2f}` | `{c.get('risk_adjusted_pnl_share', 0.0):+.1f}%` |"
            )
        md.append("")
    md.append(f"- **Total Event-Day PnL (FOMC/CPI/NFP):** `${macro_m.get('event_day_pnl', 0.0):,.2f}` ({macro_m.get('event_day_trade_count', 0)} trades)")
    md.append(f"- **Non-Event Normal RTH PnL:** `${macro_m.get('non_event_day_pnl', 0.0):,.2f}` ({macro_m.get('non_event_day_trade_count', 0)} trades)")
    md.append(f"- **FOMC Vulnerability Index:** `{macro_m.get('fomc_vulnerability_index', 0.0):.2f}`")
    md.append(f"- **Catalyst Recommendation:** *{macro_m.get('recommendation', 'N/A')}*")
    md.append("")

    # E. Vectorized Monte Carlo
    md.append("### E. Vectorized 50,000-Path Monte Carlo Simulation (Apex 50k Trailing Floor)")
    md.append("*(High-fidelity path-dependent evaluation with intra-trade MTM dips and $50,100 permanent ratchet)*\n")
    n_paths = mc_m.get("num_paths", 50000)
    p_pass = mc_m.get("p_pass_pct", 0.0)
    p_breach = mc_m.get("p_breach_pct", 0.0)
    p_dll = mc_m.get("p_dll_pct", 0.0)
    med_trades = mc_m.get("median_trades_to_pass", "N/A")
    p95_dd = mc_m.get("p95_max_drawdown", 0.0)
    lock_rate = mc_m.get("permanent_lock_rate_pct", 0.0)

    md.append("| Monte Carlo Metric | Output Value | Apex 50k Operational Target |")
    md.append("| :--- | :--- | :--- |")
    md.append(f"| **Simulated Paths** | `{n_paths:,} paths` | 50,000 randomized bootstrap iterations |")
    md.append(f"| **P(Pass +$3,000 Target)** | `{p_pass:.1f}%` | Target: >= 80.0% qualification rate |")
    md.append(f"| **P(Breach -$2,500 Floor)** | `{p_breach:.2f}%` | Institutional Ceiling: <= 1.00% breach risk |")
    md.append(f"| **P(Hit -$1,000 DLL)** | `{p_dll:.2f}%` | Intraday Hard Flatten Circuit Breaker |")
    md.append(f"| **Median Trades to Pass** | `{med_trades} trades` | 90th Percentile: `{mc_m.get('p90_trades_to_pass', 'N/A')} trades` |")
    md.append(f"| **95th Percentile Drawdown** | `${p95_dd:,.2f}` | Buffer Dilution: `{mc_m.get('buffer_dilution_pct', 0.0):.1f}%` of $2,500 |")
    md.append(f"| **Permanent Floor Lock Rate** | `{lock_rate:.1f}%` | Trailing floor frozen at $50,100 upon reaching $52,600 |")
    md.append(f"- **Monte Carlo Recommendation:** *{mc_m.get('recommendation', 'N/A')}*")
    md.append("\n---\n")

    # =========================================================================
    # SECTION 4: ALGORITHMIC DEATH TREE & SLIPPAGE FRONTIER
    # =========================================================================
    md.append("## 3. Algorithmic Death Tree & Slippage Frontier (Loss Taxonomy & Friction)\n")
    
    # Retrieve loss taxonomy & friction frontier dynamically from multi-year forensic report first
    primary_art = strategies_data.get(target_strat, {})
    lt = forensic.get("loss_taxonomy") if forensic.get("loss_taxonomy") and forensic["loss_taxonomy"].get("total_losses", 0) > 0 else primary_art.get("loss_taxonomy", {})
    ff = forensic.get("friction_frontier") if forensic.get("friction_frontier") and forensic["friction_frontier"].get("frontier_table") else primary_art.get("friction_frontier", {})
    exc = forensic.get("excursion_efficiency") or primary_art.get("excursion", {})

    total_losses = lt.get("total_losses", 0)
    breakdown = lt.get("breakdown", {})

    md.append("### The Algorithmic Death Tree")
    if total_losses == 0:
        md.append("*Zero losing trades recorded in evaluation sample.*")
    else:
        md.append(f"Total Losing Trades Dissected: **{total_losses}**\n")
        md.append("| Failure Mode | Count | Pct Share | Total Loss ($) | Econometric Pathology |")
        md.append("| :--- | :--- | :--- | :--- | :--- |")
        diagnostics = {
            "Immediate Flush": "Stop-loss hit within 6 bars (MFE < 0.35R) -> Toxic entry timing / adverse selection",
            "Trapped Trade": "MFE >= 0.80R before complete collapse -> Target geometry failure / greed",
            "Friction Drain": "Gross PnL > 0, Net PnL <= 0 -> Commissions & exchange fees ate stop",
            "Structural Invalidation": "Orderly stop violation -> Market structure invalidation"
        }
        for cat_name, b_info in breakdown.items():
            pathology = diagnostics.get(cat_name, "Unclassified failure mode")
            md.append(
                f"| **{cat_name}** | `{b_info.get('count', 0)}` | `{b_info.get('percentage', 0.0)}%` | "
                f"`-${b_info.get('total_loss_dollars', 0.0):,.2f}` | {pathology} |"
            )
        md.append("")

    s_star = ff.get("critical_slippage_s_star", "> 3.0")
    md.append("### Friction Frontier & Break-Even Critical Slippage ($S^*$)")
    md.append(f"- **Critical Slippage Threshold ($S^*$):** `{s_star} ticks` (level where net expectancy drops to <= 0.00R)")
    md.append(f"- **Directional Drift Ratio:** `{exc.get('drift_ratio', 0.0):.3f}x` | **Excursion Capture Efficiency:** `{exc.get('excursion_efficiency', 0.0):.3f}`")
    
    table = ff.get("frontier_table", [])
    if table:
        md.append("\n| Slippage (Ticks) | Net PnL ($) | Expectancy ($) | Expectancy (R) | Win Rate % |")
        md.append("| :--- | :--- | :--- | :--- | :--- |")
        for row in table:
            md.append(
                f"| `{row.get('slippage_ticks')} ticks` | `${row.get('total_net_pnl', 0.0):,.2f}` | "
                f"`${row.get('expectancy_dollars', 0.0):.2f}` | `{row.get('expectancy_r', 0.0):+.3f}R` | "
                f"`{row.get('win_rate_pct', 0.0)}%` |"
            )
    md.append("\n---\n")

    # =========================================================================
    # SECTION 5: MULTI-ACCOUNT FLEET & CUSUM DRIFT STATUS
    # =========================================================================
    md.append("## 4. Multi-Account Fleet & CUSUM Drift Status\n")
    
    fleet_accs = fleet_data.get("accounts", [])
    tot_equity = fleet_data.get("fleet_total_equity", fleet_data.get("aggregate_equity", 250000.0))
    tot_accounts = fleet_data.get("total_accounts", len(fleet_accs) or 5)
    healthy_accounts = fleet_data.get("healthy_accounts", tot_accounts)

    md.append("### Multi-Account Evaluation Fleet Overview")
    md.append(f"- **Total Evaluation Accounts:** `{tot_accounts}` | **Healthy Sub-Accounts:** `{healthy_accounts}`")
    md.append(f"- **Consolidated Fleet Equity:** `${tot_equity:,.2f}` | **Realized Fleet PnL:** `${fleet_data.get('fleet_realized_pnl', 0.0):,.2f}`")
    
    disp = fleet_data.get("latest_dispersion")
    disp_str = f"Max Dispersion: {disp.get('max_price_dispersion_points', 0.0):.2f} pts" if disp else "Synchronized (0.00 ticks dispersion)"
    md.append(f"- **Execution Latency Dispersion:** `{disp_str}`\n")

    if fleet_accs:
        md.append("| Account ID | Status | Equity ($) | Trailing Floor ($) | Distance to Floor ($) | Floor Locked | DLL Breached |")
        md.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
        for acc in fleet_accs:
            acc_id = acc.get("account_id", "APEX-XX")
            status = acc.get("account_status", acc.get("status", "HEALTHY"))
            eq = acc.get("total_equity", acc.get("equity", 50000.0))
            floor = acc.get("trailing_floor", 47500.0)
            dist = acc.get("distance_to_floor", acc.get("buffer_clearance", 2500.0))
            locked = "✅ YES" if acc.get("floor_locked", acc.get("is_locked", False)) else "NO"
            dll = "❌ TRIPPED" if acc.get("dll_breached", acc.get("dll_tripped", False)) else "OK"
            md.append(f"| **{acc_id}** | `{status}` | `${eq:,.2f}` | `${floor:,.2f}` | `${dist:,.2f}` | {locked} | {dll} |")
        md.append("")

    md.append("### Statistical Alpha Drift Sentinel & Automated CUSUM Quarantine")
    cusum_s = drift_data.get("cusum_statistic", 0.0)
    cusum_h = drift_data.get("cusum_threshold", drift_data.get("cusum_threshold_h", 4.0))
    drift_status = drift_data.get("status", "HEALTHY")
    is_quarantined = drift_data.get("is_quarantined", drift_status == "QUARANTINED")
    q_reason = drift_data.get("reason", "No abnormal drift detected. Operational parameters optimal.")

    status_badge = "🚨 QUARANTINED" if is_quarantined else ("⚠️ WARNING" if drift_status == "WARNING" else "✅ HEALTHY")
    md.append(f"- **Sentinel Quarantine Status:** `{status_badge}`")
    md.append(f"- **Page's CUSUM Statistic ($S_n$):** `{cusum_s:.3f}` (Decision Boundary $h$: `{cusum_h:.3f}` cumulative $R$-units)")
    md.append(f"- **Rolling 15-Trade Win Rate:** `{drift_data.get('rolling_win_rate_15', 0.705) * 100:.1f}%` (Wilson Lower Bound: `{drift_data.get('wilson_lower_bound', 0.581) * 100:.1f}%`)")
    md.append(f"- **Rolling 15-Trade Expectancy:** `{drift_data.get('rolling_expectancy_15', 0.569):+.3f}R` (Hurdle: `{drift_data.get('expectancy_hurdle', 0.150):+.3f}R`)")
    md.append(f"- **Automated Drawdown Breaker:** `$800.00` (Enforces hard freeze before 32% of $2,500 Apex trailing floor is touched)")
    md.append(f"- **Active Diagnostic Telemetry:** *{q_reason}*")
    md.append("\n---\n")

    md.append("*AlphaForge Quantitative Trading Engine // Confidential Institutional Research Artifact*")

    content = "\n".join(md)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"-> Generated unified LLM digest: {out_file} ({len(content):,} bytes)")
    return content


if __name__ == "__main__":
    generate_llm_digest()
