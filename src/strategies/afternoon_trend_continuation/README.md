# Afternoon Trend Continuation (`afternoon_trend_continuation`)

## Quantitative Hypothesis & Market Microstructure
The **Afternoon Trend Continuation** strategy targets institutional liquidity rebalancing in CME equity index futures (MNQ / NQ) between **13:30 and 15:30 EST**.

### Microstructural Rationale
1. **European Cash Close Cleanout:** European markets close at 11:30 AM EST (16:30 London), creating a lull in institutional algorithmic volume. Between 11:30 and 13:30 EST, price typically trades inside a contracted, low-volume "lunch chop" bracket.
2. **Reduced Retail Noise:** Opening retail noise and morning stop-hunts subside by the early afternoon.
3. **NYSE MOC (Market-On-Close) Imbalance Flows:** Starting around 13:30–14:00 EST, institutional asset managers and ETF market makers begin executing programmatic hedging and basket balancing ahead of the 15:50 EST MOC deadline.
4. **Directional Persistence:** Breakouts from the 11:30–13:30 EST consolidation exhibit substantially lower false breakout rates than the 09:30 open, leading to higher trending persistence and cleaner directional expansion.

## Strategy Architecture
* **Consolidation Window (11:30 - 13:30 EST):** Establishes the midday consolidation reference bracket (Highest High and Lowest Low).
* **Execution Window (13:30 - 15:15 EST):** 
  * **Long:** Bar close > Midday High.
  * **Short:** Bar close < Midday Low.
  * **Stop:** Midpoint of the midday consolidation (or consolidation extreme).
  * **Target:** $1.50 \times \text{Risk}$ initial risk-reward.
* **Cutoff & Discipline:** Maximum 1 trade per day, with strict EOD liquidation cutoff at 15:55 EST.
