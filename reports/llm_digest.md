# ALPHAFORGE // INSTITUTIONAL QUANTITATIVE AUDIT & DIAGNOSTIC DIGEST
**Execution Timestamp:** `2026-10-08 20:44:35 UTC`  
**Target Instrument:** CME Micro E-mini Nasdaq-100 Futures (`MNQ` / `NQ`)  
**Dataset Span:** `2022-01-03 -> 2026-09-30` (140,538 (5-minute continuous) bars across 1,191 trading sessions, 1,732 calendar days)  
**Data Provenance:** `⚠️ SYNTHETIC STOCHASTIC SIMULATION (GBM Regime Generator, Seed 42)`  
> **CRITICAL AUDIT NOTICE:** The multi-year continuous contract was synthesized via stochastic GBM regime modeling. All backtest metrics (Win Rate, Drawdown, Sharpe, WFE) reflect generative model assumptions rather than empirical CME Globex order flow. Production sign-off requires validation on empirical Databento continuous tick data.

**Account Evaluation Model:** Apex 50k Peak-Unrealized MTM Trailing Floor (-$2,500 Floor, +$3,000 Target, $50,100 Permanent Lock, No Daily Loss Limit, 15:55 EST Hard Flatten)  
**Execution Friction Standard:** CME Globex Default (1.0 tick slippage + strict FIFO limit trade-through)  

---

## 1. Multi-Strategy Benchmark Zoo Leaderboard

| Strategy | Trades | Win Rate (95% CI) | Net PnL ($) | Profit Factor | Expectancy (R ± SE) | Drift Ratio (x) | P(Pass) | P(Breach) | Crit Slip (S*) | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :---|
| afternoon_trend_continuation | 1066 | 37.9% [Wilson CI] | 2079.72 | 1.06 | +0.033 ± 0.029 | 1.263 | 1.1% | 1.83% | > 3.0 | APPROVED_FOR_INCUBATION |
| portfolio_blended | 817 | 27.7% [Wilson CI] | -1469.72 | 0.95 | -0.023 ± 0.040 | 1.309 | 0.3% | 6.72% | > 3.0 | CONDITIONAL_AUDIT |
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

**Audit Status:** `CONDITIONAL // SENSITIVITY FLAGGED` | **Institutional Composite Score:** `4.7/100`  
**Key Forensic Findings:**
- Calendar-Day Sharpe: 0.33 (unbiased continuous 252-day accounting)
- Deflated Sharpe Ratio (DSR): 0.0433 (controlling for 25 Zoo trials)
- Apex 50k 50,000-Path P(Pass): 1.1%, P(Breach): 1.8%
- Walk-Forward Efficiency (WFE): 191.8% across 6 regimes
- CPCV Probability of Backtest Overfitting (PBO): 26.7%
- FOMC Catalyst Impact: NEUTRAL: Strategy shows balanced performance across macro event windows.

### A. Unbiased Continuous Calendar-Day Performance (252-Day Annualization)
*(Eliminates trade-concatenation bias by continuous daily business-day return accounting with $0 on flat days)*

| Metric | Value | Institutional Significance |
| :--- | :--- | :--- |
| **Calendar-Day Sharpe Ratio** | `0.333` | True continuous Sharpe (replaces trade-concatenated 11.41) |
| **Calendar-Day Sortino Ratio** | `0.523` | Annualized semi-deviation downside penalty |
| **Calmar Ratio** | `0.129` | Annualized PnL ($440.04) / Max Drawdown |
| **Gain-to-Pain Ratio** | `1.057` | Jack Schwager institutional return-to-pain quotient |
| **Active-Day Exposure Rate** | `89.5%` | 1066 active trading days out of 1191 business days |
| **Net Realized PnL** | `$2,079.72` | Daily mean PnL: `$1.75` (Std: `$83.25`) |
| **Max Realized Drawdown** | `$3,403.88` | `6.81%` of peak equity |
| **Daily Win Rate** | `37.9%` | Best day: `$273.76` / Worst day: `$-211.96` |

### B. Deflated Sharpe Ratio (DSR) & Multiple Testing Surveillance
*(Marcos López de Prado & David Bailey 2014: Adjusting for selection bias, skewness, and Zoo trial variance)*

- **Deflated Sharpe Ratio (DSR):** `0.0433` (⚠️ CAUTION (< 0.95 hurdle))
- **Probabilistic Sharpe Ratio (PSR):** `0.7664` (accounting for higher statistical moments)
- **Expected Maximum Null Sharpe ($E[\max(SR_0)]$):** `1.182`
- **Zoo Trials Penalized ($K$):** `25` historical strategy configurations
- **Return Skewness ($\\gamma_3$):** `0.461` | **Return Kurtosis ($\\gamma_4$):** `-0.354`
- **Family-Wise Error Rate (FWER) $p$-value:** `0.9987`

### C. Combinatorial Purged Cross-Validation (CPCV) & Walk-Forward Matrix (WFO)
*(Evaluating combinatorial backtest overfitting and multi-year chronological regime stability)*

- **CPCV Probability of Backtest Overfitting ($P(\text{PBO}))$:** `26.7%` (15 combinatorial splits across 6 groups)
- **Median Out-of-Sample (OOS) Sharpe:** `0.257` (Mean: `0.349`, Range: `[-1.235, +2.092]`)
- **Variance Degradation Ratio:** `0.793`
- **Walk-Forward Efficiency (WFE %):** `191.8%` (Mode: `ANCHORED`)
- **OOS Regime Consistency:** `50.0%` (3 of 6 out-of-sample regimes profitable)
- **Cumulative OOS Realized PnL:** `$154.44` | **Overall OOS Sharpe:** `0.036`

### D. Macroeconomic Catalyst Attribution & Event-Day Slicing
*(Performance decomposition across FOMC rate decisions, CPI prints, NFP releases, and standard RTH)*

| Catalyst Event | Trades | Win Rate % | Net PnL ($) | Profit Factor | Expectancy (R) | Avg Trade PnL ($) | PnL Share % |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **NON_EVENT** | `985` | `38.5%` | `$2,263.72` | `1.07` | `+0.040R` | `$2.30` | `+108.8%` |
| **FOMC** | `27` | `33.3%` | `$-53.44` | `0.97` | `-0.112R` | `$-1.98` | `-2.6%` |
| **NFP** | `54` | `29.6%` | `$-130.56` | `0.95` | `-0.029R` | `$-2.42` | `-6.3%` |

- **Total Event-Day PnL (FOMC/CPI/NFP):** `$-184.00` (81 trades)
- **Non-Event Normal RTH PnL:** `$2,263.72` (985 trades)
- **FOMC Vulnerability Index:** `-1.98`
- **Catalyst Recommendation:** *NEUTRAL: Strategy shows balanced performance across macro event windows.*

### E. Vectorized 50,000-Path Monte Carlo Simulation (Apex 50k Trailing Floor)
*(High-fidelity path-dependent evaluation with intra-trade MTM dips and $50,100 permanent ratchet)*

| Monte Carlo Metric | Output Value | Apex 50k Operational Target |
| :--- | :--- | :--- |
| **Simulated Paths** | `50,000 paths` | 50,000 randomized bootstrap iterations |
| **P(Pass +$3,000 Target)** | `1.1%` | Target: >= 80.0% qualification rate |
| **P(Breach -$2,500 Floor)** | `1.83%` | Institutional Ceiling: <= 1.00% breach risk |
| **P(Hit -$1,000 DLL)** | `0.00%` | Intraday Hard Flatten Circuit Breaker |
| **Median Trades to Pass** | `127 trades` | 90th Percentile: `147 trades` |
| **95th Percentile Drawdown** | `$2,083.12` | Buffer Dilution: `83.3%` of $2,500 |
| **Permanent Floor Lock Rate** | `1.1%` | Trailing floor frozen at $50,100 upon reaching $52,600 |
- **Monte Carlo Recommendation:** *DISQUALIFIED: Breach probability exceeds institutional risk tolerance (>5%).*

### F. Pre-Registered Session Regime Bucketing & Excursion Distributions
*(Pre-market session variables pre-registered prior to measuring outcomes; checks distribution stability in R)*

- **Sessions with Initial Balance Extension >= 1.5× ATR:** `0.0%`
- **Trend Extension Rate by Year:** 2022: `0.0%`, 2023: `0.0%`, 2024: `0.0%`, 2025: `0.0%`, 2026: `0.0%`

**Forward Excursion Distribution (in R) by Initial Balance Compression:**
| IB Regime | Sample Size | Win Rate | Mean R | Median MFE (R) [p25-p75] | Median MAE (R) [p25-p75] |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **COMPRESSED (<0.35 ATR)** | `972` | `38.3%` | `+0.027R` | `0.81R` [0.32-1.34] | `0.62R` [0.25-1.08] |
| **EXPANDED (>0.65 ATR)** | `3` | `33.3%` | `+0.154R` | `1.06R` [0.65-1.36] | `0.49R` [0.33-0.83] |
| **NORMAL (0.35-0.65 ATR)** | `91` | `40.7%` | `+0.087R` | `0.87R` [0.30-1.47] | `0.56R` [0.21-1.10] |


---

## 3. Algorithmic Death Tree & Slippage Frontier (Loss Taxonomy & Friction)

### The Algorithmic Death Tree
Total Losing Trades Dissected: **662**

| Failure Mode | Count | Pct Share | Total Loss ($) | Econometric Pathology |
| :--- | :--- | :--- | :--- | :--- |
| **Immediate Flush** | `193` | `29.2%` | `-$16,143.80` | Stop-loss hit within 6 bars (MFE < 0.35R) -> Toxic entry timing / adverse selection |
| **Trapped Trade** | `216` | `32.6%` | `-$1,663.16` | MFE >= 0.80R before complete collapse -> Target geometry failure / greed |
| **Friction Drain** | `4` | `0.6%` | `-$8.92` | Gross PnL > 0, Net PnL <= 0 -> Commissions & exchange fees ate stop |
| **Structural Invalidation** | `249` | `37.6%` | `-$18,525.60` | Orderly stop violation -> Market structure invalidation |

### Friction Frontier & Break-Even Critical Slippage ($S^*$)
- **Critical Slippage Threshold ($S^*$):** `2.1 ticks` (level where net expectancy drops to <= 0.00R)
- **Directional Drift Ratio:** `1.263x` | **Excursion Capture Efficiency:** `0.000`

| Slippage (Ticks) | Net PnL ($) | Expectancy ($) | Expectancy (R) | Win Rate % |
| :--- | :--- | :--- | :--- | :--- |
| `0.0 ticks` | `$3,997.72` | `$3.75` | `+0.001R` | `38.1%` |
| `0.5 ticks` | `$3,045.72` | `$2.86` | `-0.010R` | `38.1%` |
| `1.0 ticks` | `$2,093.72` | `$1.96` | `-0.022R` | `38.0%` |
| `1.5 ticks` | `$1,141.72` | `$1.07` | `-0.033R` | `37.7%` |
| `2.0 ticks` | `$189.72` | `$0.18` | `-0.044R` | `37.5%` |
| `3.0 ticks` | `$-1,714.28` | `$-1.61` | `-0.067R` | `37.3%` |

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