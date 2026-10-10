# Opening Range Breakout 5M Binary (`orb_5m_binary`) — Evolved v2.0

## Empirical Audit Post-Mortem & Microstructure
In benchmark audits of raw CME Globex data, `orb_5m_binary` exhibited a severe structural vulnerability:
* **The Trapped Trade Bottleneck:** 50.0% of all losses (12 of 24) were classified under the Algorithmic Death Tree as **Trapped Trades** (trades reaching MFE $\ge +0.80R$ before collapsing into a full $-1.0R$ stop loss).
* **Microstructure Finding:** `Time-to-Peak MFE` was consistently **1 bar (5 minutes)** with `Median MFE` of **+1.148R**.
* **The Solution:** A fixed $+1.30R$ target was choking winners ticks away from fill before momentum rotated. Version 2.0 monetizes the violent opening impulse:
  1. **Configurable Target Geometry:** Supports `fixed_rr` (calibrated around $1.00R$) and `orb_range_multiple` (anchoring TP directly to a fraction of the opening range).
  2. **Inertia Time Stop:** Closes trades via `TIME_STOP` if stagnant after `time_stop_bars` (default: 3 bars = 15 minutes), preventing post-auction rotation into losses.
  3. **Optional Soft Profit Protection:** Tightens stop to breakeven $+0.25$ pt buffer once floating MFE reaches $\ge +0.85R$.

## Parameters (`config.yaml`)
* `timeframe`: 5m
* `or_start_time`: "09:30"
* `or_window_end`: "09:45"
* `trading_window_end`: "11:30"
* `target_mode`: "fixed_rr" (`fixed_rr` or `orb_range_multiple`)
* `risk_reward`: 1.0
* `range_mult`: 0.80
* `time_stop_bars`: 3
* `protect_at_1r`: false
* `stop_type`: "midpoint"
