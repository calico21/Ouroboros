# VWAP Mean Reversion 10 AM (`vwap_mean_reversion_10am`)

## Strategy Overview
The **VWAP Mean Reversion 10 AM** strategy exploits institutional exhaustion and mean-reverting liquidity pools during the post-open auction.

- **Timeframe:** 5-minute bars.
- **Execution Window:** 10:00 to 14:00 EST.
- **Trigger Logic:**
  - Price expands beyond $\pm 2.0$ standard deviations of the session-anchored VWAP.
  - Generates reversal candle rejection (hammer / shooting star).
  - Enters on market to capture reversion back to session VWAP.
- **Exit Geometry:**
  - Stop placed just beyond candle extreme ($+4$ ticks cushion).
  - Target anchored to dynamic session VWAP. Minimum $1.2\times R$ reward requirement.
