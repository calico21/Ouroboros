# Apex Shield High-Drift Master Ensemble: Multi-Window Quantitative Stress Rig

Institutional-grade quantitative validation, multi-window walk-forward stress testing, and 50,000-path Monte Carlo trailing-ratchet audit of the **Apex Shield High-Drift Master Ensemble** (CME Micro Futures: MNQ, MYM, M2K) across 4 hermetic historical macro regimes (2018–2026).

---

## User Review & Critical Decisions

> [!IMPORTANT]
> **Confirmed Choices from Phase 1 Clarifications:**
> - **4 Macro Regime Windows**: 
>   1. Window 1 (2018–2020): Volatility Shock, Repo Squeeze & COVID-19 V-Recovery
>   2. Window 2 (2021–2022): Post-Stimulus Peak, Fed Hiking Cycle & Tech Bear Market
>   3. Window 3 (2023–2024): Generative AI Expansion & High-Drift Trend Continuum
>   4. Window 4 (2025–2026): Contemporary Microstructure, Live Regime & Out-of-Sample Validation
> - **Monte Carlo Rigor**: 50,000 stationary bootstrap paths per window with exact Apex 50k Trailing Ratchet (Peak MFE intra-bar update, Apex Permanent Freeze at $50,100 upon touching $52,600, Stop-First order resolution).
> - **Zero-Residual Purge**: Irreversible discarding of sub-0.20R zombie strategies, midday chop setups (11:45–14:00 ET), and ungrounded placebo indicators.
> - **Deliverable Interface**: Full dedicated **Apex Shield Multi-Window Cockpit** in the web dashboard + standalone Python CLI engine (`scripts/run_multi_window_stress_rig.py`).

---

## 1. Overview & Core Concept

### What It Does
An institutional quantitative verification and stress-testing engine dedicated exclusively to the three verified alpha sleeves of the **Apex Shield High-Drift Master Ensemble**:
1. **Sleeve A (Cash Open Value Gap Traverse | MNQ)**: Dalton 80% Rule auction mechanics (09:30–10:15 ET). Target = 1.65R–1.85R with 2 microcontracts.
2. **Sleeve B (Pure PDH Sweep Runner | MNQ)**: Liquidity sweep above PDH (1–15 pts) with VWAP rejection in opening gap-up regime (09:40–11:30 ET). Target = 1.75R–2.00R with 3 microcontracts.
3. **Sleeve C (Low-Notional Daily Swing | MYM & M2K)**: Macro regime pullback (Daily Close > SMA200, IBS < 0.20, RSI2 < 15). Technical stop 1.25x ATR ($95–$115 risk). Target = 1.60R or Close > SMA10 with 1 microcontract.

### Quantitative Guarantees Under Audit
- **Net Expectancy per Window**: Strictly $E[R] \ge +0.25\text{R}$ post-commissions CME ($1.24 RT) and 1 tick slippage per side.
- **Statistical Significance**: Bootstrap 95% Confidence Interval with $N=5,000$ iterations yielding strictly positive lower bounds ($\text{CI}_{\text{low}} > 0.00\text{R}$) across all 4 windows.
- **Apex 50k Evaluation Solvency**: $P(\text{Pass}) \ge 65.0\%$ within 60–90 trades, and Gambler's Ruin probability $P(\text{Breach}) \le 4.0\%$ against the $2,000 buffer.

---

## 2. User Experience & Visual Design

### Aesthetic Direction & Layout
- **Style**: Institutional Quantitative Hedge Fund Cockpit (Dark Slate `#090D16` / Obsidian `#000000`, Metallic borders `#1E293B`, high-contrast Emerald `#10B981` positive alpha, Cyan `#06B6D4` freeze ratchet, and Rose `#F43F5E` breach alerts).
- **Typography**: Clean display typography (`Outfit` / `Plus Jakarta Sans`) combined with strictly monospace tabular figures (`JetBrains Mono` / `tabular-nums`) for all price, tick, Sharpe/Sortino, and PnL metrics.
- **Navigation & Cockpit Paneling**:
  - **Top Level Summary Banner**: 4-Window Macro Performance Matrix, Regime Health Indicators, and Global Ensemble Solvency Badge.
  - **Window Switcher Bar**: 4 hermetic tabs (`Window 1: 2018-2020`, `Window 2: 2021-2022`, `Window 3: 2023-2024`, `Window 4: 2025-2026`) + `Cross-Regime Pooled`.
  - **Interactive 50k Monte Carlo Ratchet Cone**: Dynamic SVG rendering 30 sample equity paths, the peak-ratcheting liquidation floor, the Apex Freeze at $50,100, and profit target at $53,000.
  - **Institutional Tearsheet Grid**: Side-by-side comparative table breakdown showing Win Rate, Profit Factor, Expectancy $E[R]$, Bootstrap 95% CI, Max Drawdown in R and $, Sortino, and Calmar ratios.
  - **Multi-Window Sensitivity Surface**: Stress matrix showing strategy performance under adverse slippage (0.5 tick, 1.0 tick, 2.0 ticks) and execution delays.
  - **Live Audit Execution Console**: Real-time terminal log viewer connected to the backend execution runner.

---

## 3. Key Product Decisions & Trade-Offs

### Decision 1: Data Synthesis for Pre-2022 Macro Regimes (2018–2021)
- **Chosen Approach**: Build a continuous multi-window partition engine that utilizes empirical 2022–2026 continuous 5m CME futures data for Windows 3 & 4, and calibrates Windows 1 & 2 using historical CME settlement ranges, historical ATR, and regime volatility matrices mapped from verified historical daily levels.
- **Why**: Ensures realistic microstructural price action across all 4 distinct market regimes without lookahead bias, reproducing the 2018 VIX spike and 2020 COVID shock adverse excursions.

### Decision 2: Strict Mutual Exclusion & Conviction Routing
- **Chosen Approach**: Account maintains at most 1 active micro future position at any given timestamp. When simultaneous signals occur, priority is routed by structural conviction:
  $$\text{Priority: } \text{Sleeve C (Daily Swing)} \;\longrightarrow\; \text{Sleeve A (Value Gap)} \;\longrightarrow\; \text{Sleeve B (PDH Sweep)}$$
- **Why**: Eliminates margin collision, respects the Apex 50k account purchasing power constraints, and isolates risk to $115/trade.

---

## 4. Technical Architecture & System Layout

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       APEX SHIELD QUANTITATIVE RIG                          │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
            ┌──────────────────────────┴──────────────────────────┐
            ▼                                                     ▼
┌──────────────────────────────┐              ┌───────────────────────────────┐
│     PYTHON CLI STRESS RIG    │              │       EXPRESS / VITE WEB      │
│ run_multi_window_stress_rig  │              │   server.ts & REST API Routes │
├──────────────────────────────┤              ├───────────────────────────────┤
│ • 4 Macro Regime Partitions  │              │ • GET  /api/stress-rig/report │
│ • Sleeves A, B, C Simulators │              │ • POST /api/stress-rig/run    │
│ • 50,000 MC Ratchet Paths    │              │ • SSE / Telemetry Broadcast   │
│ • CME Friction & Slippage    │              └───────────────┬───────────────┘
│ • JSON Audit Report Dump     │                              │
└──────────────┬───────────────┘                              ▼
               │                              ┌───────────────────────────────┐
               ▼                              │     REACT SHIELD COCKPIT      │
┌──────────────────────────────┐              │   ApexShieldStressCockpit.tsx │
│   reports/artifacts/         │              ├───────────────────────────────┤
│   multi_window_stress_report │◄─────────────┤ • 4 Macro Window Switcher     │
└──────────────────────────────┘              │ • 50,000 MC Ratchet Cone      │
                                              │ • Institutional Tearsheets    │
                                              │ • Slippage Sensitivity Grid   │
                                              │ • Terminal Execution Log      │
                                              └───────────────────────────────┘
```

### File & Component Implementation Matrix
1. **`scripts/run_multi_window_stress_rig.py`**:
   - Master Python CLI audit engine.
   - Partitions data into Window 1 (2018–2020), Window 2 (2021–2022), Window 3 (2023–2024), Window 4 (2025–2026).
   - Simulates Sleeve A ($1.65\text{R}$ Dalton Value Gap), Sleeve B ($1.75\text{R}–2.00\text{R}$ Pure PDH Sweep), Sleeve C ($1.60\text{R}$ Multi-Asset Daily Swing).
   - Runs 50,000 Monte Carlo paths per window with exact Apex 50k Peak MFE trailing ratchet and freeze.
   - Dumps `reports/artifacts/multi_window_stress_report.json`.
2. **`server.ts`**:
   - Endpoints `/api/stress-rig/report` and `/api/stress-rig/run`.
3. **`src/components/ApexShieldStressCockpit.tsx`**:
   - Comprehensive multi-window audit cockpit UI meeting institutional standards.
4. **`src/App.tsx`**:
   - Primary navigation tab for `APEX SHIELD (MULTI-WINDOW RIG)` with active status badges.
