# Trapped Liquidity Sweep Strategy (MNQ)

## 1. Microstructural Edge & Empirical Hypothesis
Following our Phase 3 forensic post-mortem on CME Globex Micro E-mini Nasdaq-100 (`MNQ`) futures:
- The 09:45 EST Opening Range breakout candle is frequently an institutional absorption climax.
- Retail breakout stop-orders aggregate outside the 15-minute Opening Range High and Low (09:30–09:45 EST).
- Institutional liquidity providers trigger these breakout clusters to accumulate inventory, resulting in a false breakout ("liquidity sweep") and an immediate price rotation back inside the range.
- Rather than chasing the breakout, this strategy **fades the failed breakout** upon confirmed re-entry back inside the Opening Range.

## 2. Setup Mechanics
- **Opening Range Window:** 09:30 - 09:45 EST (3 $\times$ 5m bars).
- **Sweep Detection Window:** 09:45 - 10:45 EST.
- **Extension Thresholds:**
  - $\text{Min Extension} \ge 2.0\text{ pts}$ (confirms retail breakout participation).
  - $\text{Max Extension} \le 25.0\text{ pts}$ (invalidates runaway trend days).
- **Timeout Rule:** Must re-enter within $\le 3\text{ bars}$ of the initial breach.
- **Bear Trap (Long Setup):** Price pierces below ORB Low by 2.0–25.0 pts, then closes back ABOVE the ORB Low.
  - $\text{Entry}$: Close of the re-entry candle.
  - $\text{Stop Loss}$: Lowest low of the sweep wick $- 1\text{ tick}$ ($0.25\text{ pt}$).
  - $\text{Take Profit}$: Range Midpoint ($50\%$) or $1.25\text{R}$.
- **Bull Trap (Short Setup):** Price pierces above ORB High by 2.0–25.0 pts, then closes back BELOW the ORB High.
  - $\text{Entry}$: Close of the re-entry candle.
  - $\text{Stop Loss}$: Highest high of the sweep wick $+ 1\text{ tick}$ ($0.25\text{ pt}$).
  - $\text{Take Profit}$: Range Midpoint ($50\%$) or $1.25\text{R}$.
