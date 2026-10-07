# ALPHAFORGE // INSTITUTIONAL QUANTITATIVE AUDIT & DIAGNOSTIC DIGEST
**Generated:** `2026-10-07 21:24:29 UTC`  
**Target Instrument:** CME Micro E-mini Nasdaq-100 Futures (`MNQ`)  
**Account Evaluation Model:** Apex 50k Peak-Unrealized MTM Trailing Floor ($2,500 Max DD, +$3,000 Target)  
**Execution Friction:** CME Globex Default (1.0 tick slippage + Strict FIFO Limit Trade-Through)  

---

## 1. Multi-Strategy Benchmark Zoo Leaderboard

| Strategy | Trades | Win Rate (95% CI) | Net PnL ($) | Profit Factor | Expectancy (R ± SE) | Drift Ratio (x) | P(Pass) | P(Breach) | Crit Slip (S*) | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :---|
| afternoon_trend_continuation | 61 | 70.5% [58.1-80.4%] | 2949.86 | 3.16 | +0.569 ± 0.112 | 2.178 | 100.0% | 0.0% | > 3.0 | APPROVED_FOR_INCUBATION |
| portfolio_blended | 49 | 61.2% [47.2-73.6%] | 1526.98 | 2.57 | +0.403 ± 0.120 | 1.662 | 96.6% | 0.0% | > 3.0 | APPROVED_FOR_INCUBATION |
| orb_5m_binary | 34 | 38.2% [23.9-55.0%] | -592.18 | 0.46 | -0.109 ± 0.104 | 1.047 | 0.0% | 63.3% | 0.0 | DISQUALIFIED (DRIFT < 1.5x) |
| trapped_liquidity_sweep | 37 | 40.5% [26.4-56.5%] | -1110.84 | 0.45 | -0.242 ± 0.153 | 0.833 | 0.0% | 98.9% | 0.0 | DISQUALIFIED (DRIFT < 1.5x) |
| vwap_mean_reversion_10am | 112 | 25.0% [17.9-33.8%] | -2322.4 | 0.42 | -0.325 ± 0.127 | 0.796 | 0.0% | 85.2% | 0.0 | DISQUALIFIED (DRIFT < 1.5x) |
| open_drive_continuation | 14 | 28.6% [11.7-54.6%] | -192.86 | 0.8 | -0.122 ± 0.386 | 0.755 | GATED (N<15) | GATED (N<15) | 0.0 | INSUFFICIENT_SAMPLE (N=14/30) |

*Status Legend:*  
- `APPROVED_FOR_INCUBATION`: Drift Ratio >= 1.50x, Expectancy > 0.20R, S* >= 1.5 ticks, N >= 30.  
- `REJECTED_ZERO_EDGE`: Drift Ratio < 1.50x or Net Expectancy <= 0.  
- `REJECTED_COST_SENSITIVE`: Fragile alpha collapsing under S* < 1.0 ticks.  
- `INSUFFICIENT_SAMPLE`: N < 30 minimum empirical trades.  

---

## 2. Granular Strategy Forensic Audits

### Strategy: `afternoon_trend_continuation`
**Audit Verdict:** `APPROVED_FOR_INCUBATION` — ✅ APPROVED_FOR_INCUBATION (Statistically robust edge & positive expectancy)

#### Performance & Statistical Guardrails
| Metric | Value | Statistical Assessment |
| :--- | :--- | :--- |
| **Sample Size (N)** | `61 trades` | ✅ Sufficient (N >= 30) |
| **Win Rate** | `70.5% (95% CI: [58.1%, 80.4%])` | 95% Wilson Score Interval |
| **Net Realized PnL** | `$2,949.86` | Gross: `$3,637.46` / Fees: `$687.60` |
| **Expectancy (R)** | `+0.569R ± 0.112 (95% CI: [+0.349R, +0.790R])` | Bootstrap 1,000 resamples (± SE) |
| **Profit Factor** | `3.16` | Win/Loss Payoff: `1.32x` |
| **Sharpe / Sortino** | `11.41 / 21.52` | Annualized intraday |
| **Max Realized DD** | `$355.96` | Peak-to-Trough |

#### Alpha Edge & Excursion Quality
- **Directional Drift Ratio:** `2.178x` (✅ PASS (>= 1.5x))
- **Median MFE / MAE:** `1.042R` favorable / `0.478R` adverse
- **Time-to-Peak MFE:** `7 bars` (median holding time to peak favorable price)
- **Excursion Efficiency:** `-0.067` (fraction of peak favorable run realized at exit)

#### The Algorithmic Death Tree (Loss Taxonomy)
Total Losses Dissected: **18**
| Failure Mode | Count | Pct Share | Total Loss ($) | Diagnostic Meaning |
| :--- | :--- | :--- | :--- | :--- |
| **Immediate Flush** | `3` | `16.7%` | `-$392.88` | SL hit within 6 bars (MFE < 0.35R) -> Toxic entry timing |
| **Trapped Trade** | `2` | `11.1%` | `-$152.84` | MFE >= 0.80R before collapsing -> Greed / poor target geometry |
| **Friction Drain** | `2` | `11.1%` | `-$15.62` | Gross PnL > 0, Net <= 0 -> Commissions & slippage ate stop |
| **Structural Invalidation** | `11` | `61.1%` | `-$801.20` | Orderly stop violation -> Clean invalidation |

#### Friction Frontier & Critical Slippage (S*)
- **Critical Slippage S*:** `> 3.0 ticks` (Break-even slippage where Net Expectancy drops to 0)
| Slippage (Ticks) | Net PnL ($) | Expectancy ($) | Expectancy (R) | Win Rate % |
| :--- | :--- | :--- | :--- | :--- |
| `0.0 ticks` | `$3,215.86` | `$52.72` | `+0.504R` | `72.1%` |
| `0.5 ticks` | `$3,082.86` | `$50.54` | `+0.484R` | `70.5%` |
| `1.0 ticks` | `$2,949.86` | `$48.36` | `+0.463R` | `70.5%` |
| `1.5 ticks` | `$2,816.86` | `$46.18` | `+0.442R` | `70.5%` |
| `2.0 ticks` | `$2,683.86` | `$44.00` | `+0.422R` | `70.5%` |
| `3.0 ticks` | `$2,417.86` | `$39.64` | `+0.381R` | `70.5%` |

#### Prop-Firm Evaluation & Monte Carlo (10,000 Paths)
- **Probability of Passing Target (+$3,000):** `99.99%`
- **Probability of Trailing Floor Breach (-$2,500):** `0.0%`
- **Median Trades to Pass Target:** `61.0`
- **Final Account Balance:** `$52,949.86` (Floor: `$50,461.02`)

---

### Strategy: `open_drive_continuation`
**Audit Verdict:** `INSUFFICIENT_DATA` — ⚠️ INSUFFICIENT_SAMPLE (N = 14 / 30 minimum)

#### Performance & Statistical Guardrails
| Metric | Value | Statistical Assessment |
| :--- | :--- | :--- |
| **Sample Size (N)** | `14 trades` | ⚠️ Insufficient (N < 30) |
| **Win Rate** | `28.6% (95% CI: [11.7%, 54.6%])` | 95% Wilson Score Interval |
| **Net Realized PnL** | `$-192.86` | Gross: `$-81.40` / Fees: `$111.46` |
| **Expectancy (R)** | `-0.122R ± 0.386 (95% CI: [-0.878R, +0.635R])` | Bootstrap 1,000 resamples (± SE) |
| **Profit Factor** | `0.8` | Win/Loss Payoff: `2.01x` |
| **Sharpe / Sortino** | `-2.28 / -24.2` | Annualized intraday |
| **Max Realized DD** | `$729.94` | Peak-to-Trough |

#### Alpha Edge & Excursion Quality
- **Directional Drift Ratio:** `0.755x` (❌ DISQUALIFIED (< 1.5x))
- **Median MFE / MAE:** `0.794R` favorable / `1.051R` adverse
- **Time-to-Peak MFE:** `3 bars` (median holding time to peak favorable price)
- **Excursion Efficiency:** `-2.066` (fraction of peak favorable run realized at exit)

#### The Algorithmic Death Tree (Loss Taxonomy)
Total Losses Dissected: **10**
| Failure Mode | Count | Pct Share | Total Loss ($) | Diagnostic Meaning |
| :--- | :--- | :--- | :--- | :--- |
| **Immediate Flush** | `2` | `20.0%` | `-$220.42` | SL hit within 6 bars (MFE < 0.35R) -> Toxic entry timing |
| **Trapped Trade** | `2` | `20.0%` | `-$172.20` | MFE >= 0.80R before collapsing -> Greed / poor target geometry |
| **Friction Drain** | `0` | `0.0%` | `-$0.00` | Gross PnL > 0, Net <= 0 -> Commissions & slippage ate stop |
| **Structural Invalidation** | `6` | `60.0%` | `-$594.78` | Orderly stop violation -> Clean invalidation |

#### Friction Frontier & Critical Slippage (S*)
- **Critical Slippage S*:** `0.0 ticks` (Break-even slippage where Net Expectancy drops to 0)
| Slippage (Ticks) | Net PnL ($) | Expectancy ($) | Expectancy (R) | Win Rate % |
| :--- | :--- | :--- | :--- | :--- |
| `0.0 ticks` | `$-148.36` | `$-10.60` | `-0.173R` | `28.6%` |
| `0.5 ticks` | `$-170.61` | `$-12.19` | `-0.191R` | `28.6%` |
| `1.0 ticks` | `$-192.86` | `$-13.78` | `-0.208R` | `28.6%` |
| `1.5 ticks` | `$-215.11` | `$-15.36` | `-0.226R` | `28.6%` |
| `2.0 ticks` | `$-237.36` | `$-16.95` | `-0.243R` | `28.6%` |
| `3.0 ticks` | `$-281.86` | `$-20.13` | `-0.278R` | `28.6%` |

#### Prop-Firm Evaluation & Monte Carlo (10,000 Paths)
- **Status:** `SUPPRESSED` — Monte Carlo simulation suppressed: requires at least 15 empirical trades (observed N=14) to prevent deceptive probability estimates.
- **Final Account Balance:** `$49,807.14` (Floor: `$48,058.04`)

---

### Strategy: `orb_5m_binary`
**Audit Verdict:** `REJECTED_ZERO_EDGE` — ❌ REJECTED_ZERO_EDGE (Drift Ratio < 1.50x minimum edge threshold)

#### Performance & Statistical Guardrails
| Metric | Value | Statistical Assessment |
| :--- | :--- | :--- |
| **Sample Size (N)** | `34 trades` | ✅ Sufficient (N >= 30) |
| **Win Rate** | `38.2% (95% CI: [23.9%, 55.0%])` | 95% Wilson Score Interval |
| **Net Realized PnL** | `$-592.18` | Gross: `$-237.08` / Fees: `$355.10` |
| **Expectancy (R)** | `-0.109R ± 0.104 (95% CI: [-0.313R, +0.094R])` | Bootstrap 1,000 resamples (± SE) |
| **Profit Factor** | `0.46` | Win/Loss Payoff: `0.75x` |
| **Sharpe / Sortino** | `-6.6 / -8.75` | Annualized intraday |
| **Max Realized DD** | `$556.68` | Peak-to-Trough |

#### Alpha Edge & Excursion Quality
- **Directional Drift Ratio:** `1.047x` (❌ DISQUALIFIED (< 1.5x))
- **Median MFE / MAE:** `0.386R` favorable / `0.369R` adverse
- **Time-to-Peak MFE:** `1 bars` (median holding time to peak favorable price)
- **Excursion Efficiency:** `-2.117` (fraction of peak favorable run realized at exit)

#### The Algorithmic Death Tree (Loss Taxonomy)
Total Losses Dissected: **21**
| Failure Mode | Count | Pct Share | Total Loss ($) | Diagnostic Meaning |
| :--- | :--- | :--- | :--- | :--- |
| **Immediate Flush** | `14` | `66.7%` | `-$795.06` | SL hit within 6 bars (MFE < 0.35R) -> Toxic entry timing |
| **Trapped Trade** | `2` | `9.5%` | `-$197.20` | MFE >= 0.80R before collapsing -> Greed / poor target geometry |
| **Friction Drain** | `2` | `9.5%` | `-$2.94` | Gross PnL > 0, Net <= 0 -> Commissions & slippage ate stop |
| **Structural Invalidation** | `3` | `14.3%` | `-$111.36` | Orderly stop violation -> Clean invalidation |

#### Friction Frontier & Critical Slippage (S*)
- **Critical Slippage S*:** `0.0 ticks` (Break-even slippage where Net Expectancy drops to 0)
| Slippage (Ticks) | Net PnL ($) | Expectancy ($) | Expectancy (R) | Win Rate % |
| :--- | :--- | :--- | :--- | :--- |
| `0.0 ticks` | `$-441.68` | `$-12.99` | `-0.177R` | `44.1%` |
| `0.5 ticks` | `$-516.93` | `$-15.20` | `-0.202R` | `41.2%` |
| `1.0 ticks` | `$-592.18` | `$-17.42` | `-0.227R` | `38.2%` |
| `1.5 ticks` | `$-667.43` | `$-19.63` | `-0.252R` | `38.2%` |
| `2.0 ticks` | `$-742.68` | `$-21.84` | `-0.277R` | `38.2%` |
| `3.0 ticks` | `$-893.18` | `$-26.27` | `-0.327R` | `35.3%` |

#### Prop-Firm Evaluation & Monte Carlo (10,000 Paths)
- **Probability of Passing Target (+$3,000):** `0.0%`
- **Probability of Trailing Floor Breach (-$2,500):** `63.26%`
- **Median Trades to Pass Target:** `None`
- **Final Account Balance:** `$49,407.82` (Floor: `$47,605.00`)

---

### Strategy: `portfolio_blended`
**Audit Verdict:** `APPROVED_FOR_INCUBATION` — ✅ APPROVED_FOR_INCUBATION (Statistically robust edge & positive expectancy)

#### Performance & Statistical Guardrails
| Metric | Value | Statistical Assessment |
| :--- | :--- | :--- |
| **Sample Size (N)** | `49 trades` | ✅ Sufficient (N >= 30) |
| **Win Rate** | `61.2% (95% CI: [47.2%, 73.6%])` | 95% Wilson Score Interval |
| **Net Realized PnL** | `$1,526.98` | Gross: `$2,000.92` / Fees: `$473.94` |
| **Expectancy (R)** | `+0.403R ± 0.120 (95% CI: [+0.167R, +0.639R])` | Bootstrap 1,000 resamples (± SE) |
| **Profit Factor** | `2.57` | Win/Loss Payoff: `1.62x` |
| **Sharpe / Sortino** | `8.75 / 16.71` | Annualized intraday |
| **Max Realized DD** | `$204.84` | Peak-to-Trough |

#### Alpha Edge & Excursion Quality
- **Directional Drift Ratio:** `1.662x` (✅ PASS (>= 1.5x))
- **Median MFE / MAE:** `0.719R` favorable / `0.433R` adverse
- **Time-to-Peak MFE:** `4 bars` (median holding time to peak favorable price)
- **Excursion Efficiency:** `-0.650` (fraction of peak favorable run realized at exit)

#### The Algorithmic Death Tree (Loss Taxonomy)
Total Losses Dissected: **19**
| Failure Mode | Count | Pct Share | Total Loss ($) | Diagnostic Meaning |
| :--- | :--- | :--- | :--- | :--- |
| **Immediate Flush** | `9` | `47.4%` | `-$470.20` | SL hit within 6 bars (MFE < 0.35R) -> Toxic entry timing |
| **Trapped Trade** | `2` | `10.5%` | `-$151.32` | MFE >= 0.80R before collapsing -> Greed / poor target geometry |
| **Friction Drain** | `2` | `10.5%` | `-$2.94` | Gross PnL > 0, Net <= 0 -> Commissions & slippage ate stop |
| **Structural Invalidation** | `6` | `31.6%` | `-$351.02` | Orderly stop violation -> Clean invalidation |

#### Friction Frontier & Critical Slippage (S*)
- **Critical Slippage S*:** `> 3.0 ticks` (Break-even slippage where Net Expectancy drops to 0)
| Slippage (Ticks) | Net PnL ($) | Expectancy ($) | Expectancy (R) | Win Rate % |
| :--- | :--- | :--- | :--- | :--- |
| `0.0 ticks` | `$1,714.48` | `$34.99` | `+0.338R` | `65.3%` |
| `0.5 ticks` | `$1,620.73` | `$33.08` | `+0.317R` | `63.3%` |
| `1.0 ticks` | `$1,526.98` | `$31.16` | `+0.295R` | `61.2%` |
| `1.5 ticks` | `$1,433.23` | `$29.25` | `+0.274R` | `61.2%` |
| `2.0 ticks` | `$1,339.48` | `$27.34` | `+0.253R` | `61.2%` |
| `3.0 ticks` | `$1,151.98` | `$23.51` | `+0.210R` | `61.2%` |

#### Prop-Firm Evaluation & Monte Carlo (10,000 Paths)
- **Probability of Passing Target (+$3,000):** `96.61%`
- **Probability of Trailing Floor Breach (-$2,500):** `0.0%`
- **Median Trades to Pass Target:** `94.0`
- **Final Account Balance:** `$53,053.96` (Floor: `$50,553.96`)

#### Multi-Strategy Portfolio Allocation & Diversification
- **Diversification Ratio:** `0.59`
- **Strategy Trade Breakdown:** `{'afternoon_trend_continuation': 31, 'orb_5m_binary': 18}`
- **Daily Volatilities:** `{'afternoon_trend_continuation': 87.85, 'orb_5m_binary': 33.54}`
- **Inter-Strategy Correlation Matrix:**
  - `afternoon_trend_continuation`: `{'afternoon_trend_continuation': 1.0, 'orb_5m_binary': 0.295}`
  - `orb_5m_binary`: `{'afternoon_trend_continuation': 0.295, 'orb_5m_binary': 1.0}`

---

### Strategy: `trapped_liquidity_sweep`
**Audit Verdict:** `REJECTED_ZERO_EDGE` — ❌ REJECTED_ZERO_EDGE (Drift Ratio < 1.50x minimum edge threshold)

#### Performance & Statistical Guardrails
| Metric | Value | Statistical Assessment |
| :--- | :--- | :--- |
| **Sample Size (N)** | `37 trades` | ✅ Sufficient (N >= 30) |
| **Win Rate** | `40.5% (95% CI: [26.3%, 56.5%])` | 95% Wilson Score Interval |
| **Net Realized PnL** | `$-1,110.84` | Gross: `$-640.82` / Fees: `$470.02` |
| **Expectancy (R)** | `-0.242R ± 0.153 (95% CI: [-0.542R, +0.058R])` | Bootstrap 1,000 resamples (± SE) |
| **Profit Factor** | `0.45` | Win/Loss Payoff: `0.66x` |
| **Sharpe / Sortino** | `-8.51 / -25.18` | Annualized intraday |
| **Max Realized DD** | `$1,242.30` | Peak-to-Trough |

#### Alpha Edge & Excursion Quality
- **Directional Drift Ratio:** `0.833x` (❌ DISQUALIFIED (< 1.5x))
- **Median MFE / MAE:** `0.833R` favorable / `1.0R` adverse
- **Time-to-Peak MFE:** `1 bars` (median holding time to peak favorable price)
- **Excursion Efficiency:** `-1.462` (fraction of peak favorable run realized at exit)

#### The Algorithmic Death Tree (Loss Taxonomy)
Total Losses Dissected: **22**
| Failure Mode | Count | Pct Share | Total Loss ($) | Diagnostic Meaning |
| :--- | :--- | :--- | :--- | :--- |
| **Immediate Flush** | `4` | `18.2%` | `-$402.20` | SL hit within 6 bars (MFE < 0.35R) -> Toxic entry timing |
| **Trapped Trade** | `7` | `31.8%` | `-$589.52` | MFE >= 0.80R before collapsing -> Greed / poor target geometry |
| **Friction Drain** | `0` | `0.0%` | `-$0.00` | Gross PnL > 0, Net <= 0 -> Commissions & slippage ate stop |
| **Structural Invalidation** | `11` | `50.0%` | `-$1,019.10` | Orderly stop violation -> Clean invalidation |

#### Friction Frontier & Critical Slippage (S*)
- **Critical Slippage S*:** `0.0 ticks` (Break-even slippage where Net Expectancy drops to 0)
| Slippage (Ticks) | Net PnL ($) | Expectancy ($) | Expectancy (R) | Win Rate % |
| :--- | :--- | :--- | :--- | :--- |
| `0.0 ticks` | `$-917.34` | `$-24.79` | `-0.337R` | `40.5%` |
| `0.5 ticks` | `$-1,014.09` | `$-27.41` | `-0.370R` | `40.5%` |
| `1.0 ticks` | `$-1,110.84` | `$-30.02` | `-0.403R` | `40.5%` |
| `1.5 ticks` | `$-1,207.59` | `$-32.64` | `-0.437R` | `40.5%` |
| `2.0 ticks` | `$-1,304.34` | `$-35.25` | `-0.470R` | `40.5%` |
| `3.0 ticks` | `$-1,497.84` | `$-40.48` | `-0.536R` | `40.5%` |

#### Prop-Firm Evaluation & Monte Carlo (10,000 Paths)
- **Probability of Passing Target (+$3,000):** `0.0%`
- **Probability of Trailing Floor Breach (-$2,500):** `98.94%`
- **Median Trades to Pass Target:** `None`
- **Final Account Balance:** `$48,889.16` (Floor: `$47,645.32`)

---

### Strategy: `vwap_mean_reversion_10am`
**Audit Verdict:** `REJECTED_ZERO_EDGE` — ❌ REJECTED_ZERO_EDGE (Drift Ratio < 1.50x minimum edge threshold)

#### Performance & Statistical Guardrails
| Metric | Value | Statistical Assessment |
| :--- | :--- | :--- |
| **Sample Size (N)** | `112 trades` | ✅ Sufficient (N >= 30) |
| **Win Rate** | `25.0% (95% CI: [17.9%, 33.8%])` | 95% Wilson Score Interval |
| **Net Realized PnL** | `$-2,322.40` | Gross: `$-1,336.78` / Fees: `$985.62` |
| **Expectancy (R)** | `-0.325R ± 0.127 (95% CI: [-0.575R, -0.076R])` | Bootstrap 1,000 resamples (± SE) |
| **Profit Factor** | `0.42` | Win/Loss Payoff: `1.25x` |
| **Sharpe / Sortino** | `-7.5 / -13.53` | Annualized intraday |
| **Max Realized DD** | `$2,220.00` | Peak-to-Trough |

#### Alpha Edge & Excursion Quality
- **Directional Drift Ratio:** `0.796x` (❌ DISQUALIFIED (< 1.5x))
- **Median MFE / MAE:** `0.857R` favorable / `1.077R` adverse
- **Time-to-Peak MFE:** `2 bars` (median holding time to peak favorable price)
- **Excursion Efficiency:** `-1.723` (fraction of peak favorable run realized at exit)

#### The Algorithmic Death Tree (Loss Taxonomy)
Total Losses Dissected: **84**
| Failure Mode | Count | Pct Share | Total Loss ($) | Diagnostic Meaning |
| :--- | :--- | :--- | :--- | :--- |
| **Immediate Flush** | `29` | `34.5%` | `-$1,274.84` | SL hit within 6 bars (MFE < 0.35R) -> Toxic entry timing |
| **Trapped Trade** | `31` | `36.9%` | `-$1,771.62` | MFE >= 0.80R before collapsing -> Greed / poor target geometry |
| **Friction Drain** | `0` | `0.0%` | `-$0.00` | Gross PnL > 0, Net <= 0 -> Commissions & slippage ate stop |
| **Structural Invalidation** | `24` | `28.6%` | `-$930.94` | Orderly stop violation -> Clean invalidation |

#### Friction Frontier & Critical Slippage (S*)
- **Critical Slippage S*:** `0.0 ticks` (Break-even slippage where Net Expectancy drops to 0)
| Slippage (Ticks) | Net PnL ($) | Expectancy ($) | Expectancy (R) | Win Rate % |
| :--- | :--- | :--- | :--- | :--- |
| `0.0 ticks` | `$-1,910.90` | `$-17.06` | `-0.469R` | `25.0%` |
| `0.5 ticks` | `$-2,116.65` | `$-18.90` | `-0.520R` | `25.0%` |
| `1.0 ticks` | `$-2,322.40` | `$-20.74` | `-0.572R` | `25.0%` |
| `1.5 ticks` | `$-2,528.15` | `$-22.57` | `-0.623R` | `25.0%` |
| `2.0 ticks` | `$-2,733.90` | `$-24.41` | `-0.674R` | `25.0%` |
| `3.0 ticks` | `$-3,145.40` | `$-28.08` | `-0.777R` | `25.0%` |

#### Prop-Firm Evaluation & Monte Carlo (10,000 Paths)
- **Probability of Passing Target (+$3,000):** `0.0%`
- **Probability of Trailing Floor Breach (-$2,500):** `85.21%`
- **Median Trades to Pass Target:** `None`
- **Final Account Balance:** `$47,677.60` (Floor: `$47,520.00`)

---
