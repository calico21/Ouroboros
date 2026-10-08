# ALPHAFORGE // INSTITUTIONAL QUANTITATIVE AUDIT & DIAGNOSTIC DIGEST
**Execution Timestamp:** `2026-10-08 20:13:18 UTC`  
**Target Instrument:** CME Micro E-mini Nasdaq-100 Futures (`MNQ` / `NQ`)  
**Dataset Span:** `2022-01-03 -> 2026-09-30` (140,538 (5-minute continuous) bars across 1,191 trading sessions, 1,732 calendar days)  
**Account Evaluation Model:** Apex 50k Peak-Unrealized MTM Trailing Floor (-$2,500 Floor, +$3,000 Target, $50,100 Permanent Lock, -$1,000 DLL, 15:55 EST Hard Flatten)  
**Execution Friction Standard:** CME Globex Default (1.0 tick slippage + strict FIFO limit trade-through)  

---

## 1. Multi-Strategy Benchmark Zoo Leaderboard

| Strategy | Trades | Win Rate (95% CI) | Net PnL ($) | Profit Factor | Expectancy (R ± SE) | Drift Ratio (x) | P(Pass) | P(Breach) | Crit Slip (S*) | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :---|
| afternoon_trend_continuation | 817 | 27.7% [Wilson CI] | -1469.72 | 0.95 | -0.023 ± 0.040 | 1.309 | 0.3% | 6.72% | > 3.0 | CONDITIONAL_AUDIT |
| portfolio_blended | 49 | 61.2% [47.2-73.6%] | 1526.98 | 2.57 | +0.403 ± 0.120 | 1.662 | 96.6% | 0.0% | > 3.0 | APPROVED_FOR_INCUBATION |
| orb_5m_binary | 34 | 38.2% [23.9-55.0%] | -592.18 | 0.46 | -0.109 ± 0.104 | 1.047 | 0.0% | 63.3% | 0.0 | DISQUALIFIED (DRIFT < 1.5x) |
| trapped_liquidity_sweep | 37 | 40.5% [26.4-56.5%] | -1110.84 | 0.45 | -0.242 ± 0.153 | 0.833 | 0.0% | 98.9% | 0.0 | DISQUALIFIED (DRIFT < 1.5x) |
| vwap_mean_reversion_10am | 112 | 25.0% [17.9-33.8%] | -2322.4 | 0.42 | -0.325 ± 0.127 | 0.796 | 0.0% | 85.2% | 0.0 | DISQUALIFIED (DRIFT < 1.5x) |
| open_drive_continuation | 14 | 28.6% [11.7-54.6%] | -192.86 | 0.8 | -0.122 ± 0.386 | 0.755 | GATED (N<15) | GATED (N<15) | 0.0 | INSUFFICIENT_SAMPLE (N=14/30) |

*Institutional Status Legend:*  
- `APPROVED_FOR_INCUBATION`: Drift Ratio >= 1.50x, Net Expectancy > 0.20R, S* >= 1.5 ticks, N >= 30.  
- `REJECTED_ZERO_EDGE`: Drift Ratio < 1.50x or Net Expectancy <= 0.00R.  
- `REJECTED_COST_SENSITIVE`: Fragile micro-edge destroyed by friction (S* < 1.0 ticks).  
- `INSUFFICIENT_SAMPLE`: N < 30 minimum empirical trades required for Wilson Score confidence.  

---

## 2. Phase 6 Deep Forensic Econometrics: `afternoon_trend_continuation`

**Audit Status:** `CONDITIONAL // SENSITIVITY FLAGGED` | **Institutional Composite Score:** `-2.4/100`  
**Key Forensic Findings:**
- Calendar-Day Sharpe: -0.26 (unbiased continuous 252-day accounting)
- Deflated Sharpe Ratio (DSR): 0.0037 (controlling for 25 Zoo trials)
- Apex 50k 50,000-Path P(Pass): 0.3%, P(Breach): 6.7%
- Walk-Forward Efficiency (WFE): 33.3% across 6 regimes
- CPCV Probability of Backtest Overfitting (PBO): 60.0%
- FOMC Catalyst Impact: NEUTRAL: Strategy shows balanced performance across macro event windows.

### A. Unbiased Continuous Calendar-Day Performance (252-Day Annualization)
*(Eliminates trade-concatenation bias by continuous daily business-day return accounting with $0 on flat days)*

| Metric | Value | Institutional Significance |
| :--- | :--- | :--- |
| **Calendar-Day Sharpe Ratio** | `-0.261` | True continuous Sharpe (replaces trade-concatenated 11.41) |
| **Calendar-Day Sortino Ratio** | `-0.418` | Annualized semi-deviation downside penalty |
| **Calmar Ratio** | `-0.108` | Annualized PnL ($-310.97) / Max Drawdown |
| **Gain-to-Pain Ratio** | `0.954` | Jack Schwager institutional return-to-pain quotient |
| **Active-Day Exposure Rate** | `68.6%` | 817 active trading days out of 1191 business days |
| **Net Realized PnL** | `$-1,469.72` | Daily mean PnL: `$-1.23` (Std: `$75.10`) |
| **Max Realized Drawdown** | `$2,875.44` | `5.75%` of peak equity |
| **Daily Win Rate** | `27.7%` | Best day: `$135.84` / Worst day: `$-84.16` |

### B. Deflated Sharpe Ratio (DSR) & Multiple Testing Surveillance
*(Marcos López de Prado & David Bailey 2014: Adjusting for selection bias, skewness, and Zoo trial variance)*

- **Deflated Sharpe Ratio (DSR):** `0.0037` (⚠️ CAUTION (< 0.95 hurdle))
- **Probabilistic Sharpe Ratio (PSR):** `0.2866` (accounting for higher statistical moments)
- **Expected Maximum Null Sharpe ($E[\max(SR_0)]$):** `1.182`
- **Zoo Trials Penalized ($K$):** `25` historical strategy configurations
- **Return Skewness ($\\gamma_3$):** `0.611` | **Return Kurtosis ($\\gamma_4$):** `-1.251`
- **Family-Wise Error Rate (FWER) $p$-value:** `1.0000`

### C. Combinatorial Purged Cross-Validation (CPCV) & Walk-Forward Matrix (WFO)
*(Evaluating combinatorial backtest overfitting and multi-year chronological regime stability)*

- **CPCV Probability of Backtest Overfitting ($P(\text{PBO}))$:** `60.0%` (15 combinatorial splits across 6 groups)
- **Median Out-of-Sample (OOS) Sharpe:** `-0.476` (Mean: `-0.346`, Range: `[-2.345, +1.078]`)
- **Variance Degradation Ratio:** `0.000`
- **Walk-Forward Efficiency (WFE %):** `33.3%` (Mode: `ANCHORED`)
- **OOS Regime Consistency:** `33.3%` (2 of 6 out-of-sample regimes profitable)
- **Cumulative OOS Realized PnL:** `$73.68` | **Overall OOS Sharpe:** `0.020`

### D. Macroeconomic Catalyst Attribution & Event-Day Slicing
*(Performance decomposition across FOMC rate decisions, CPI prints, NFP releases, and standard RTH)*

| Catalyst Event | Trades | Win Rate % | Net PnL ($) | Profit Factor | Expectancy (R) | Avg Trade PnL ($) | PnL Share % |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **NON_EVENT** | `743` | `27.9%` | `$-1,041.88` | `0.96` | `-0.018R` | `$-1.40` | `-70.9%` |
| **FOMC** | `29` | `17.2%` | `$-611.64` | `0.53` | `-0.264R` | `$-21.09` | `-41.6%` |
| **NFP** | `45` | `31.1%` | `$183.80` | `1.11` | `+0.051R` | `$4.08` | `+12.5%` |

- **Total Event-Day PnL (FOMC/CPI/NFP):** `$-427.84` (74 trades)
- **Non-Event Normal RTH PnL:** `$-1,041.88` (743 trades)
- **FOMC Vulnerability Index:** `-21.09`
- **Catalyst Recommendation:** *NEUTRAL: Strategy shows balanced performance across macro event windows.*

### E. Vectorized 50,000-Path Monte Carlo Simulation (Apex 50k Trailing Floor)
*(High-fidelity path-dependent evaluation with intra-trade MTM dips and $50,100 permanent ratchet)*

| Monte Carlo Metric | Output Value | Apex 50k Operational Target |
| :--- | :--- | :--- |
| **Simulated Paths** | `5,000 paths` | 50,000 randomized bootstrap iterations |
| **P(Pass +$3,000 Target)** | `0.3%` | Target: >= 80.0% qualification rate |
| **P(Breach -$2,500 Floor)** | `6.72%` | Institutional Ceiling: <= 1.00% breach risk |
| **P(Hit -$1,000 DLL)** | `0.00%` | Intraday Hard Flatten Circuit Breaker |
| **Median Trades to Pass** | `140 trades` | 90th Percentile: `148 trades` |
| **95th Percentile Drawdown** | `$2,509.43` | Buffer Dilution: `100.4%` of $2,500 |
| **Permanent Floor Lock Rate** | `0.3%` | Trailing floor frozen at $50,100 upon reaching $52,600 |
- **Monte Carlo Recommendation:** *DISQUALIFIED: Breach probability exceeds institutional risk tolerance (>5%).*

---

## 3. Algorithmic Death Tree & Slippage Frontier (Loss Taxonomy & Friction)

### The Algorithmic Death Tree
Total Losing Trades Dissected: **591**

| Failure Mode | Count | Pct Share | Total Loss ($) | Econometric Pathology |
| :--- | :--- | :--- | :--- | :--- |
| **Immediate Flush** | `104` | `17.6%` | `-$8,752.64` | Stop-loss hit within 6 bars (MFE < 0.35R) -> Toxic entry timing / adverse selection |
| **Trapped Trade** | `233` | `39.4%` | `-$1,708.28` | MFE >= 0.80R before complete collapse -> Target geometry failure / greed |
| **Friction Drain** | `0` | `0.0%` | `-$0.00` | Gross PnL > 0, Net PnL <= 0 -> Commissions & exchange fees ate stop |
| **Structural Invalidation** | `254` | `43.0%` | `-$21,305.64` | Orderly stop violation -> Market structure invalidation |

### Friction Frontier & Break-Even Critical Slippage ($S^*$)
- **Critical Slippage Threshold ($S^*$):** `0.0 ticks` (level where net expectancy drops to <= 0.00R)
- **Directional Drift Ratio:** `1.309x` | **Excursion Capture Efficiency:** `0.000`

| Slippage (Ticks) | Net PnL ($) | Expectancy ($) | Expectancy (R) | Win Rate % |
| :--- | :--- | :--- | :--- | :--- |
| `0.0 ticks` | `$-1,469.72` | `$-1.80` | `-0.022R` | `27.7%` |
| `0.5 ticks` | `$-2,173.22` | `$-2.66` | `-0.033R` | `27.7%` |
| `1.0 ticks` | `$-2,876.72` | `$-3.52` | `-0.044R` | `27.7%` |
| `1.5 ticks` | `$-3,580.22` | `$-4.38` | `-0.055R` | `27.7%` |
| `2.0 ticks` | `$-4,283.72` | `$-5.24` | `-0.066R` | `27.7%` |
| `3.0 ticks` | `$-5,690.72` | `$-6.97` | `-0.087R` | `27.7%` |

---

## 4. Multi-Account Fleet & CUSUM Drift Status

### Multi-Account Evaluation Fleet Overview
- **Total Evaluation Accounts:** `2` | **Healthy Sub-Accounts:** `0`
- **Consolidated Fleet Equity:** `$100,200.00` | **Realized Fleet PnL:** `$0.00`
- **Execution Latency Dispersion:** `Synchronized (0.00 ticks dispersion)`

| Account ID | Status | Equity ($) | Trailing Floor ($) | Distance to Floor ($) | Floor Locked | DLL Breached |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **APEX-M1** | `SESSION_CLOSED` | `$50,100.00` | `$47,600.00` | `$2,500.00` | NO | OK |
| **APEX-M2** | `SESSION_CLOSED` | `$50,100.00` | `$47,600.00` | `$2,500.00` | NO | OK |

### Statistical Alpha Drift Sentinel & Automated CUSUM Quarantine
- **Sentinel Quarantine Status:** `⚠️ WARNING`
- **Page's CUSUM Statistic ($S_n$):** `3.885` (Decision Boundary $h$: `50.000` cumulative $R$-units)
- **Rolling 15-Trade Win Rate:** `53.3%` (Wilson Lower Bound: `58.1%`)
- **Rolling 15-Trade Expectancy:** `+0.060R` (Hurdle: `+0.150R`)
- **Automated Drawdown Breaker:** `$800.00` (Enforces hard freeze before 32% of $2,500 Apex trailing floor is touched)
- **Active Diagnostic Telemetry:** *STATISTICAL ROLLING WARNING: 15-trade Win Rate=53.3% (Wilson lower bound=58.1%) or Expectancy=0.06R (< 0.15R hurdle).*

---

*AlphaForge Quantitative Trading Engine // Confidential Institutional Research Artifact*