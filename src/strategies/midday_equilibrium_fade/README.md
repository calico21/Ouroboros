# Strategy 9: midday_equilibrium_fade (Sleeve E: Bounded Mean Reversion)
## Mechanism
Fades lunchtime liquidity vacuum noise between 11:45 and 13:45 ET when Europe has closed and momentum stalls.
## Window & Execution
- 11:45–13:45 ET. Limit orders at VWAP +- 2.0 sigma. Target: Session VWAP.
- SL capped at 25 pts. Max 1 trade per session. Sizing: 1 MNQ.
