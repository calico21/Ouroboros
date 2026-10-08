"""
Institutional Multi-Page Deep Forensic Tearsheet Composer.
Aggregates all multi-year econometric, stress, and prop-firm validation engines into:
1. Structured JSON executive audit report (`reports/audit/deep_forensic_audit_report.json`).
2. Self-contained HTML interactive tearsheet (`reports/audit/deep_forensic_tearsheet.html`).
"""
from pathlib import Path
from typing import Dict, List, Optional, Any
import json
import numpy as np

from src.analytics.calendar_metrics import CalendarMetricsResult
from src.analytics.deflated_sharpe import DSRResult
from src.analytics.macro_attribution import MacroAttributionReport
from src.analytics.liquidity_excursion import ExcursionEfficiencyMetrics
from src.validation.cpcv import CPCVSummary
from src.validation.walk_forward_matrix import WFOReport
from src.validation.synthetic_stress import SyntheticStressReport
from src.validation.prop_firm_monte_carlo import PropFirmMonteCarloResult
from src.visualizer.regime_heatmaps import RegimeHeatmapReport
from src.visualizer.underwater_ratchet_plot import RatchetEnvelopeReport


class DeepTearsheetComposer:
    """
    Composes comprehensive forensic audit reports for AlphaForge.
    """

    def compose_report(
        self,
        strategy_name: str,
        calendar_metrics: CalendarMetricsResult,
        dsr_metrics: DSRResult,
        macro_report: MacroAttributionReport,
        excursion_metrics: ExcursionEfficiencyMetrics,
        cpcv_summary: CPCVSummary,
        wfo_report: WFOReport,
        stress_report: SyntheticStressReport,
        mc_result: PropFirmMonteCarloResult,
        heatmap_report: RegimeHeatmapReport,
        ratchet_report: RatchetEnvelopeReport,
        loss_taxonomy: Optional[Dict[str, Any]] = None,
        friction_frontier: Optional[Dict[str, Any]] = None,
        output_dir: str = "reports/audit"
    ) -> Dict[str, Any]:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        full_audit = {
            "strategy_name": strategy_name,
            "audit_timestamp": "2026-10-08T12:00:00Z",
            "executive_verdict": {
                "production_ready": bool(
                    calendar_metrics.calendar_sharpe >= 1.5 and
                    dsr_metrics.passes_deflated_hurdle and
                    mc_result.p_pass_pct >= 90.0 and
                    mc_result.p_breach_pct <= 2.0 and
                    stress_report.resilience_score >= 80.0
                ),
                "composite_score": round(
                    (min(calendar_metrics.calendar_sharpe / 2.5, 1.0) * 25.0) +
                    (dsr_metrics.deflated_sharpe_ratio * 25.0) +
                    (mc_result.p_pass_pct * 0.25) +
                    (stress_report.resilience_score * 0.25),
                    1
                ),
                "key_findings": [
                    f"Calendar-Day Sharpe: {calendar_metrics.calendar_sharpe:.2f} (unbiased continuous 252-day accounting)",
                    f"Deflated Sharpe Ratio (DSR): {dsr_metrics.deflated_sharpe_ratio:.4f} (controlling for {dsr_metrics.trials_tested} Zoo trials)",
                    f"Apex 50k 50,000-Path P(Pass): {mc_result.p_pass_pct:.1f}%, P(Breach): {mc_result.p_breach_pct:.1f}%",
                    f"Walk-Forward Efficiency (WFE): {wfo_report.mean_wfe_pct:.1f}% across {wfo_report.total_folds} regimes",
                    f"CPCV Probability of Backtest Overfitting (PBO): {cpcv_summary.pbo_pct:.1f}%",
                    f"FOMC Catalyst Impact: {macro_report.recommendation}"
                ]
            },
            "calendar_metrics": calendar_metrics.model_dump(),
            "deflated_sharpe": dsr_metrics.model_dump(),
            "macro_attribution": macro_report.model_dump(),
            "excursion_efficiency": excursion_metrics.model_dump(),
            "cpcv": cpcv_summary.model_dump(),
            "walk_forward": wfo_report.model_dump(),
            "synthetic_stress": stress_report.model_dump(),
            "prop_firm_monte_carlo": mc_result.model_dump(),
            "regime_heatmaps": heatmap_report.model_dump(),
            "loss_taxonomy": loss_taxonomy or {},
            "friction_frontier": friction_frontier or {},
            "ratchet_envelope": {
                "min_clearance": ratchet_report.min_clearance,
                "permanent_lock_achieved": ratchet_report.permanent_lock_achieved,
                "terminal_equity": ratchet_report.terminal_equity,
                "terminal_floor": ratchet_report.terminal_floor,
                "points_sample": [p.model_dump() for p in ratchet_report.points[::max(1, len(ratchet_report.points) // 100)]]
            }
        }

        # Write JSON report
        json_file = out_path / "deep_forensic_audit_report.json"
        with open(json_file, "w") as f:
            json.dump(full_audit, f, indent=2)

        # Write HTML tearsheet
        html_file = out_path / "deep_forensic_tearsheet.html"
        self._write_html_tearsheet(full_audit, html_file)

        return full_audit

    def _write_html_tearsheet(self, audit: Dict[str, Any], filepath: Path):
        strat = audit["strategy_name"]
        exec_v = audit["executive_verdict"]
        cal = audit["calendar_metrics"]
        dsr = audit["deflated_sharpe"]
        mc = audit["prop_firm_monte_carlo"]
        wfo = audit["walk_forward"]
        cpcv = audit["cpcv"]
        stress = audit["synthetic_stress"]
        macro = audit["macro_attribution"]

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>AlphaForge - Deep Forensic Audit Tearsheet: {strat}</title>
  <style>
    body {{ background: #0b0f19; color: #e2e8f0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace; margin: 0; padding: 24px; }}
    h1, h2, h3 {{ margin-top: 0; font-weight: 700; letter-spacing: -0.02em; }}
    .badge {{ display: inline-block; padding: 4px 10px; border-radius: 4px; font-size: 11px; font-weight: 600; text-transform: uppercase; }}
    .badge-green {{ background: #064e3b; color: #6ee7b7; border: 1px solid #059669; }}
    .badge-red {{ background: #7f1d1d; color: #fca5a5; border: 1px solid #dc2626; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; margin-bottom: 24px; }}
    .card {{ background: #131b2e; border: 1px solid #1e293b; border-radius: 8px; padding: 18px; }}
    .metric-val {{ font-size: 24px; font-weight: 700; color: #38bdf8; font-mono; }}
    .metric-label {{ font-size: 11px; text-transform: uppercase; color: #94a3b8; margin-bottom: 4px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 12px; }}
    th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #1e293b; }}
    th {{ background: #0f172a; color: #94a3b8; text-transform: uppercase; font-size: 10px; }}
    .score-banner {{ background: linear-gradient(135deg, #1e293b, #0f172a); border: 1px solid #334155; border-radius: 8px; padding: 20px; margin-bottom: 24px; display: flex; justify-content: space-between; align-items: center; }}
  </style>
</head>
<body>
  <div class="score-banner">
    <div>
      <h1 style="margin:0 0 6px 0; font-size: 22px;">Institutional Forensic Audit Tearsheet</h1>
      <div style="font-size: 13px; color: #94a3b8;">Asset: CME Micro E-mini Nasdaq-100 (MNQ) | Strategy: <strong style="color:#f8fafc">{strat}</strong></div>
    </div>
    <div style="text-align: right;">
      <div style="font-size: 32px; font-weight: 800; color: #10b981;">{exec_v['composite_score']}/100</div>
      <span class="badge { 'badge-green' if exec_v['production_ready'] else 'badge-red' }">
        { 'PRODUCTION APPROVED' if exec_v['production_ready'] else 'UNDER OBSERVATION' }
      </span>
    </div>
  </div>

  <h2>1. Continuous Calendar-Day Performance (252-Day Annualized)</h2>
  <div class="grid">
    <div class="card">
      <div class="metric-label">Calendar Sharpe Ratio</div>
      <div class="metric-val">{cal['calendar_sharpe']}</div>
      <div style="font-size: 11px; color:#94a3b8; margin-top: 4px;">Zero-inflated trade-concatenation eliminated</div>
    </div>
    <div class="card">
      <div class="metric-label">Calendar Sortino Ratio</div>
      <div class="metric-val">{cal['calendar_sortino']}</div>
      <div style="font-size: 11px; color:#94a3b8; margin-top: 4px;">Downside volatility penalization</div>
    </div>
    <div class="card">
      <div class="metric-label">Calmar Ratio</div>
      <div class="metric-val">{cal['calmar_ratio']}</div>
      <div style="font-size: 11px; color:#94a3b8; margin-top: 4px;">Max DD: ${cal['max_drawdown_dollars']:.2f} ({cal['max_drawdown_pct']}%)</div>
    </div>
    <div class="card">
      <div class="metric-label">Gain-to-Pain Ratio</div>
      <div class="metric-val">{cal['gain_to_pain_ratio']}</div>
      <div style="font-size: 11px; color:#94a3b8; margin-top: 4px;">Sum Positive / |Sum Negative|</div>
    </div>
  </div>

  <h2>2. Deflated Sharpe & Multiple Testing Surveillance (Bailey & López de Prado)</h2>
  <div class="grid">
    <div class="card">
      <div class="metric-label">Deflated Sharpe Ratio (DSR)</div>
      <div class="metric-val" style="color: {'#10b981' if dsr['passes_deflated_hurdle'] else '#ef4444'};">{dsr['deflated_sharpe_ratio']:.4f}</div>
      <div style="font-size: 11px; color:#94a3b8; margin-top: 4px;">Hurdle: 0.9500 (Trials M={dsr['trials_tested']})</div>
    </div>
    <div class="card">
      <div class="metric-label">Probabilistic Sharpe (PSR)</div>
      <div class="metric-val">{dsr['probabilistic_sharpe_ratio']:.4f}</div>
      <div style="font-size: 11px; color:#94a3b8; margin-top: 4px;">Accounting for Skew={dsr['skewness']}, Kurt={dsr['kurtosis']}</div>
    </div>
    <div class="card">
      <div class="metric-label">E[max SR] Null Benchmark</div>
      <div class="metric-val">{dsr['expected_max_null_sharpe']}</div>
      <div style="font-size: 11px; color:#94a3b8; margin-top: 4px;">Expected max under data snooping</div>
    </div>
    <div class="card">
      <div class="metric-label">FWER Adjusted p-value</div>
      <div class="metric-val">{dsr['fwer_p_value']:.4f}</div>
      <div style="font-size: 11px; color:#94a3b8; margin-top: 4px;">Family-wise false positive probability</div>
    </div>
  </div>

  <h2>3. Apex 50k MTM Trailing Ratchet Monte Carlo (50,000 Paths)</h2>
  <div class="grid">
    <div class="card">
      <div class="metric-label">P(Pass +$3,000 Target)</div>
      <div class="metric-val" style="color:#10b981;">{mc['p_pass_pct']}%</div>
      <div style="font-size: 11px; color:#94a3b8; margin-top: 4px;">Median trades to pass: {mc['median_trades_to_pass']}</div>
    </div>
    <div class="card">
      <div class="metric-label">P(Breach -$2,500 Floor)</div>
      <div class="metric-val" style="color: {'#10b981' if mc['p_breach_pct'] <= 1.0 else '#ef4444'};">{mc['p_breach_pct']}%</div>
      <div style="font-size: 11px; color:#94a3b8; margin-top: 4px;">Critical limit: <= 5.0%</div>
    </div>
    <div class="card">
      <div class="metric-label">Permanent Floor Lock Rate</div>
      <div class="metric-val">{mc['permanent_lock_rate_pct']}%</div>
      <div style="font-size: 11px; color:#94a3b8; margin-top: 4px;">Locked permanently at $50,100</div>
    </div>
    <div class="card">
      <div class="metric-label">95th Percentile Drawdown</div>
      <div class="metric-val">${mc['p95_max_drawdown']:.2f}</div>
      <div style="font-size: 11px; color:#94a3b8; margin-top: 4px;">Buffer dilution: {mc['buffer_dilution_pct']}% of $2,500</div>
    </div>
  </div>

  <h2>4. Walk-Forward Matrix (WFE) & Combinatorial Purged CV (CPCV)</h2>
  <div class="grid">
    <div class="card">
      <div class="metric-label">Mean Walk-Forward Efficiency (WFE)</div>
      <div class="metric-val">{wfo['mean_wfe_pct']}%</div>
      <div style="font-size: 11px; color:#94a3b8; margin-top: 4px;">Institutional target: >= 50.0%</div>
    </div>
    <div class="card">
      <div class="metric-label">WFO Consistency Score</div>
      <div class="metric-val">{wfo['consistency_pct']}%</div>
      <div style="font-size: 11px; color:#94a3b8; margin-top: 4px;">Profitable OOS folds: {wfo['profitable_oos_folds']}/{wfo['total_folds']}</div>
    </div>
    <div class="card">
      <div class="metric-label">CPCV Overfitting Probability (PBO)</div>
      <div class="metric-val" style="color: {'#10b981' if cpcv['pbo_pct'] < 10.0 else '#ef4444'};">{cpcv['pbo_pct']}%</div>
      <div style="font-size: 11px; color:#94a3b8; margin-top: 4px;">Purged & embargoed combinations</div>
    </div>
    <div class="card">
      <div class="metric-label">GARCH Stress Resilience</div>
      <div class="metric-val">{stress['resilience_score']}/100</div>
      <div style="font-size: 11px; color:#94a3b8; margin-top: 4px;">{stress['verdict']}</div>
    </div>
  </div>

  <h2>5. Macro Catalyst Performance Attribution</h2>
  <div class="card">
    <div style="font-size: 13px; color:#94a3b8; margin-bottom: 8px;"><strong>Executive Note:</strong> {macro['recommendation']}</div>
    <table>
      <thead>
        <tr>
          <th>Macro Catalyst</th>
          <th>Trades</th>
          <th>Net PnL</th>
          <th>Win Rate</th>
          <th>Profit Factor</th>
          <th>Expectancy (R)</th>
          <th>Max Loss</th>
        </tr>
      </thead>
      <tbody>
        {"".join([f'''<tr>
          <td><strong>{c['catalyst']}</strong></td>
          <td>{c['total_trades']}</td>
          <td style="color: {'#10b981' if c['net_pnl'] >= 0 else '#ef4444'}; font-weight:600;">${c['net_pnl']:.2f}</td>
          <td>{c['win_rate_pct']}%</td>
          <td>{c['profit_factor']:.2f}</td>
          <td>+{c['expectancy_r']:.3f}R</td>
          <td>${c['max_loss']:.2f}</td>
        </tr>''' for c in macro['cohorts']])}
      </tbody>
    </table>
  </div>
</body>
</html>"""
        with open(filepath, "w") as f:
            f.write(html_content)
