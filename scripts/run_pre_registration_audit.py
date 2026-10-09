#!/usr/bin/env python3
"""
Ex-Ante Pre-Registration Gate Audit Runner for AlphaForge.
Audits all candidate strategies on CME Globex data with ZERO PnL or trade outcome lookahead.
Verifies that ex-ante gate participation rates strictly conform to the 15% to 30% window
(40-75 trade opportunities per year) and profiles 30m/60m forward excursion metrics.
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.databento_loader import DatabentoCMEDataLoader
from src.analytics.gate_registry import PreRegistrationGateAuditor
from src.strategies import discover_strategies, STRATEGY_REGISTRY


def run_pre_registration_audit(
    data_path: str = "data/processed/mnq_5m.csv",
    output_path: str = "reports/audit/pre_registration_gate_audit.json"
):
    print("=" * 85)
    print("ALPHAFORGE EX-ANTE PRE-REGISTRATION GATE AUDIT (STAGE 1 & 2)")
    print("Evaluating Entry Gate Participation Rate & Forward Excursion Without Trade PnL")
    print("=" * 85)

    loader = DatabentoCMEDataLoader(data_path=data_path)
    loader.load()
    bars = list(loader.get_bars())
    print(f"Loaded {len(bars):,} continuous CME bars across real trading sessions.\n")

    auditor = PreRegistrationGateAuditor(
        min_participation_rate=15.0,
        max_participation_rate=30.0,
        over_participation_ceiling=35.0
    )

    discover_strategies()
    all_audit_results = {}

    print(f"{'Strategy Name':<32} | {'Sessions':<8} | {'Qual':<5} | {'Gate %':<7} | {'30m MFE/MAE':<12} | {'60m MFE/MAE':<12} | {'Verdict'}")
    print("-" * 105)

    for name, strat_cls in sorted(STRATEGY_REGISTRY.items()):
        strat = strat_cls()
        audit_res = auditor.audit_strategy(strat, bars)
        all_audit_results[name] = audit_res

        tot_sess = audit_res["total_sessions"]
        qual_sess = audit_res["qualified_sessions"]
        gate_pct = audit_res["participation_rate_pct"]
        fwd_30 = f"{audit_res['forward_30m']['mean_mfe_r']:.2f}/{audit_res['forward_30m']['mean_mae_r']:.2f}R"
        fwd_60 = f"{audit_res['forward_60m']['mean_mfe_r']:.2f}/{audit_res['forward_60m']['mean_mae_r']:.2f}R"
        verdict = audit_res["gate_status"]

        status_symbol = "✓" if audit_res["is_qualified"] else "⚠"
        print(f"{status_symbol} {name:<30} | {tot_sess:>8} | {qual_sess:>5} | {gate_pct:>6.1f}% | {fwd_30:<12} | {fwd_60:<12} | {verdict}")

    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    with open(out_p, "w") as f:
        json.dump(all_audit_results, f, indent=2, default=str)

    print("-" * 105)
    print(f"Audit results successfully written to {output_path}")
    print("=" * 85)
    return all_audit_results


if __name__ == "__main__":
    run_pre_registration_audit()
