# BFE9 D01 ARCH0 amplitude sensitivity

Gate: `BFE9_D01_ARCH0_AMPLITUDE_SENSITIVITY_FROZEN`

| Metric | D01 30 mV | D02 60 mV frozen baseline |
|---|---:|---:|
| Detection coverage | 22/30 | 30/30 |
| Headroom min / median | -2 / 6.5 | 19 / 38 M-codes |
| First-alarm latency median / worst | 20.534524618566998 / 20.534524618566998 ns | 20.5345 / 20.5345 ns |

Common ARCH0 margins: RISE=22, FALL=24 M-codes.
Common held-out healthy FPR: 1/240 observed events.

This paired result addresses only the observed response to halving the canonical droop amplitude. It does not claim a continuous minimum detectable voltage.
