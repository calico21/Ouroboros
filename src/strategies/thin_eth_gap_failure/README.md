# Strategy 2: thin_eth_gap_failure (Sleeve A: ETH Imbalances)
## Mechanism
Fades uninformed overnight gaps built on thin, news-free ETH volume.
## Window & Execution
- Armed at 09:45 ET, executes until 11:00 ET.
- Limit order at OR midpoint. SL capped at 35 pts.
- Target: 50% gap fill (scale 50%), runner to prior RTH close.
