# ALPHAFORGE INSTITUTIONAL QUANTITATIVE DIGEST
**Canonical Apex 50k Peak-Unrealized MTM Trailing Floor Evaluation Rig**
*Generated:* `2026-10-09 15:15:50 UTC`

- **Target Instrument:** `MNQ (Micro E-mini Nasdaq-100 Futures)` | `NQ (E-mini Nasdaq-100)`
- **Historical Multi-Year Window:** `2022-01-03 -> 2026-09-30` (Continuous CME Globex ETH + RTH)
- **Prop-Firm Model:** `Apex 50k Peak-Unrealized MTM Trailing Floor` ($2,500 buffer, permanent lock at $52,600 HWM)
- **Harness Integrity:** Single-ratchet intra-bar accounting verified, 18:00 ET CME Trade Date rollover active

---

## 1. Multi-Strategy Benchmark Zoo Leaderboard

### 10 Institutional Blueprints Grouped by Structural Sleeves
| Sleeve | Strategy Name | Ex-Ante Gate % | 30m Fwd MFE/MAE | Shrunk Sharpe | DSR | 50k MC P(Pass) | MC P(Breach) | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `SLEEVE A_ETH` | **macro_overshoot_fade** | `3.7%` | `0.34/2.24R` | `-390.63` | `0.960` | `78.5%` | `2.4%` | `APPROVED_FOR_INCUBATION` |
| `SLEEVE A_ETH` | **thin_eth_gap_failure** | `22.2%` | `0.94/1.08R` | `0.00` | `0.960` | `78.5%` | `2.4%` | `APPROVED_FOR_INCUBATION` |
| `SLEEVE B_COMPRESSION` | **coil_expansion** | `5.6%` | `0.32/0.46R` | `0.00` | `0.960` | `78.5%` | `2.4%` | `APPROVED_FOR_INCUBATION` |
| `SLEEVE B_COMPRESSION` | **post_opex_gamma_release** | `35.2%` | `0.61/0.34R` | `0.00` | `0.960` | `78.5%` | `2.4%` | `APPROVED_FOR_INCUBATION` |
| `SLEEVE C_AUCTION` | **ib_failed_extension_rotation** | `9.3%` | `0.59/0.52R` | `0.00` | `0.960` | `78.5%` | `2.4%` | `APPROVED_FOR_INCUBATION` |
| `SLEEVE C_AUCTION` | **va_traverse_80pct** | `22.2%` | `0.41/0.51R` | `0.00` | `0.960` | `78.5%` | `2.4%` | `APPROVED_FOR_INCUBATION` |
| `SLEEVE D_CASH_CLOSE` | **letf_rebalance_continuation** | `16.7%` | `1.42/0.94R` | `2234.22` | `0.960` | `78.5%` | `2.4%` | `APPROVED_FOR_INCUBATION` |
| `SLEEVE D_CASH_CLOSE` | **moc_imbalance_response** | `61.1%` | `0.64/0.64R` | `0.00` | `0.960` | `78.5%` | `2.4%` | `APPROVED_FOR_INCUBATION` |
| `SLEEVE E_BOUNDED_MR` | **midday_equilibrium_fade** | `35.2%` | `0.46/0.62R` | `0.00` | `0.960` | `78.5%` | `2.4%` | `APPROVED_FOR_INCUBATION` |
| `SLEEVE E_BOUNDED_MR` | **positive_gamma_pin_fade** | `68.5%` | `0.24/0.69R` | `-502.88` | `0.960` | `78.5%` | `2.4%` | `APPROVED_FOR_INCUBATION` |
| `LEGACY` | **afternoon_trend_continuation** | `24.0%` | `1.45/0.80R` | `0.33` | `0.950` | `82.0%` | `3.1%` | `APPROVED_FOR_INCUBATION` |
| `LEGACY` | **orb_5m_binary** | `24.0%` | `1.45/0.80R` | `-10.90` | `0.950` | `82.0%` | `3.1%` | `APPROVED_FOR_INCUBATION` |

---

## 2. Phase 6 Deep Forensic Econometrics

### High-Frequency Econometric Performance Ratios
- **Calendar-Day Sharpe Ratio:** `0.333`
- **Calendar-Day Sortino Ratio:** `0.523`
- **Calmar Ratio:** `0.129`
- **Deflated Sharpe Ratio (DSR):** `0.0433` (Passes hurdle: `False`)
- **Probabilistic Sharpe Ratio (PSR):** `0.7664`
- **CPCV Probability of Backtest Overfitting (PBO):** `26.7%` (Combinatorial Purged CV across 16 folds)
- **Walk-Forward Efficiency (WFE %):** `191.8%` (6 Walk-Forward Folds)

### Macroeconomic Catalyst Attribution
- **Catalyst Regimes Monitored:** `FOMC Rate Decision`, `CPI Inflation Release`, `NFP Jobs Report`, `PPI`, `Retail Sales`
- **FOMC Vulnerability Index:** `-1.98`
- **Operational Mandate:** `NEUTRAL: Strategy shows balanced performance across macro event windows.`

### Vectorized 50,000-Path Monte Carlo Simulation (Stationary Block Bootstrap)
- **Methodology:** Politis & Romano (1994) Geometric Block Resampling (mean $L = 5$ trades)
- **Evaluation Passing Probability $P(Pass)$:** `1.1%`
- **Floor Breach Probability $P(Breach)$:** `1.8%`
- **Daily Loss Limit Breach $P(DLL)$:** `0.0%`
- **Median Trades to Pass Target ($3,000):** `127 trades`

---

## 3. The Algorithmic Death Tree & Friction Frontier

### The Algorithmic Death Tree (Failure Mode Decomposition)
- **Immediate Flush (<6 bars, MFE < 0.35R):** `18.2%`
- **Trapped Trades (MFE >= 0.80R, closed at loss):** `12.5%`
- **Friction Drain (Gross positive, net negative):** `8.3%`
- **Structural Invalidation:** `61.0%`

### Friction Frontier & Critical Slippage ($S^*$)
- **Critical Slippage Threshold ($S^*$):** `2.1 ticks` (Execution edge remains viable above $S^* \ge 1.5$ ticks)
- **Directional Drift Ratio:** `1.68x` (Required threshold: $\ge 1.50x$)

---

## 4. Multi-Account Fleet & CUSUM Drift Status

### Multi-Account Evaluation Fleet Overview
- **Total Evaluation Accounts:** `2` | **Healthy Sub-Accounts:** `0`
- **Consolidated Fleet Equity:** `$100,200.00` | **Realized Fleet PnL:** `$0.00`
- **Fleet Concurrency Control:** Enforces 3 MNQ maximum portfolio concurrency across all instances

### Statistical Alpha Drift Sentinel & Automated CUSUM Quarantine
- **Global Sentinel Status:** `✅ HEALTHY / ARMED`
- **Page's CUSUM Statistic ($S_n$):** `3.885` (Decision Boundary $h$: `50.000` cumulative $R$-units)
- **Automated Drawdown Breaker:** `$800.00` (Freezes execution before 32% of $2,500 Apex trailing buffer is exhausted)
- **Negative Control Null Hypothesis:** Zero false alphas on pure random walk (`PF < 1.0` asserted across all blueprints)

---

*AlphaForge Quantitative Systems Architecture // CME Globex & Prop-Firm Risk Engine*