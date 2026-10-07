# Open Drive Continuation (`open_drive_continuation`)

## Strategy Overview
The **Open Drive Continuation** strategy is built to catch initial opening momentum when large institutions push the market aggressively right at the 09:30 EST cash open.

- **Timeframe:** 5-minute bars.
- **Drive Identification:**
  - Evaluates bar 1 (09:30 - 09:35 EST).
  - High conviction ratio: $\frac{|\text{Close} - \text{Open}|}{\text{High} - \text{Low}} \ge 0.65$.
  - Minimum drive height $\ge 15.0$ points.
- **Entry & Target:**
  - Enters on immediate subsequent bar continuation break.
  - Initial stop anchored to the drive low (for longs) or drive high (for shorts).
  - Target set at $2.2\times R$ risk multiple.
