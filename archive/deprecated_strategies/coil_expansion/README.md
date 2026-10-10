# Strategy 3: coil_expansion (Sleeve B: Compression & Volatility Expansion)
## Mechanism
Captures breakout expansion following multi-day volatility compression (NR7, Inside Day, narrow BB).
## Window & Execution
- 09:45–12:30 ET
- OCO bracket: Buy-stop at prior-day High + 3 ticks, Sell-stop at prior-day Low - 3 ticks.
- SL = Entry - min(0.5 * Prior Day Range, 35 pts). Time-stop: 14:30 ET.
