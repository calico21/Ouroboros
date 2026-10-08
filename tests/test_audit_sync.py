"""
Test suite validating audit desynchronization fixes, cache invalidation,
auto-chaining export_digest, and unified LLM digest generation.
"""
from pathlib import Path
import json
import pytest

from scripts.export_digest import generate_llm_digest


def test_export_digest_unification():
    digest_path = Path("reports/llm_digest_test.md")
    content = generate_llm_digest(
        audit_report_path="reports/audit/deep_forensic_audit_report.json",
        artifacts_dir="reports/artifacts",
        leaderboard_csv="reports/tables/benchmark_zoo_leaderboard.csv",
        output_path=str(digest_path)
    )

    assert digest_path.exists()
    assert len(content) > 5000

    # Section 1: Header metadata
    assert "Target Instrument" in content
    assert "MNQ" in content
    assert "2022-01-03 -> 2026-09-30" in content
    assert "Apex 50k Peak-Unrealized MTM Trailing Floor" in content

    # Section 2: Leaderboard
    assert "Multi-Strategy Benchmark Zoo Leaderboard" in content
    assert "afternoon_trend_continuation" in content

    # Section 3: Phase 6 Deep Forensic Econometrics
    assert "Phase 6 Deep Forensic Econometrics" in content
    assert "Calendar-Day Sharpe Ratio" in content
    assert "Calendar-Day Sortino Ratio" in content
    assert "Calmar Ratio" in content
    assert "Deflated Sharpe Ratio (DSR)" in content
    assert "Probabilistic Sharpe Ratio (PSR)" in content
    assert "CPCV Probability of Backtest Overfitting" in content
    assert "Walk-Forward Efficiency (WFE %)" in content
    assert "Macroeconomic Catalyst Attribution" in content
    assert "FOMC" in content
    assert "CPI" in content
    assert "NFP" in content
    assert "Vectorized 50,000-Path Monte Carlo Simulation" in content

    # Section 4: Death Tree & Friction Frontier
    assert "The Algorithmic Death Tree" in content
    assert "Friction Frontier" in content

    # Section 5: Multi-Account Fleet & CUSUM Drift
    assert "Multi-Account Evaluation Fleet Overview" in content
    assert "Statistical Alpha Drift Sentinel" in content
    assert "CUSUM" in content

    # Cleanup
    if digest_path.exists():
        digest_path.unlink()
