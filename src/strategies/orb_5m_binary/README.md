# Opening Range Breakout 5M Binary (`orb_5m_binary`)

## Strategy Overview
The **ORB 5M Binary** strategy capitalizes on the opening auction price discovery in CME equity index futures (MNQ / NQ).

- **Timeframe:** 5-minute bars.
- **Reference Range:** First 5 minutes of Regular Trading Hours (09:30 - 09:35 EST).
- **Execution Logic:**
  - **Long:** Bar close > Opening Range High.
  - **Short:** Bar close < Opening Range Low.
  - **Stop-Loss:** Opening Range Midpoint or opposite boundary.
  - **Take-Profit:** $2.0 \times R$ initial risk multiple.
- **Constraints:** Max 1 trade per session (binary outcome) within the 09:35–11:30 EST execution window.
