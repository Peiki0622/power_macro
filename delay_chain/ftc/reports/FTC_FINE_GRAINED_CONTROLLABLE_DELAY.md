# FTC Fine-Grained Controllable Delay

## Decision

**Fine-Grained Controllable Delay = NO-GO**

## Stage Status

| Stage | Status |
|---|---|
| Unit Cell | NO-GO |
| 8-Stage Short Chain | NOT_RUN |
| N Sizing | NOT_RUN |
| Full Chain | NOT_RUN |
| Real-DFF Calibration | NOT_RUN |
| C_lock + M Feasibility | NOT_RUN |

## Reasons

- 1.10 V: unit SLOW/FAST ratio is below the required full-range lower bound
- 0.95 V: unit SLOW/FAST ratio is below the required full-range lower bound
- 0.80 V: unit SLOW/FAST ratio is below the required full-range lower bound
- MXIT2 is output-inverting; no documented same-polarity low-overhead bypass primitive is available

## Scope

- TT/25°C only; no PVT, RTL, power, area, or layout claim is made.
- Historical 3-bit tap-tree runners and raw data were read-only inputs.
