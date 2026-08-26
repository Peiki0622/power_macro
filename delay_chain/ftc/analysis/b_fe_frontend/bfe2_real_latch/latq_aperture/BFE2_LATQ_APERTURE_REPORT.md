# B-FE2-LATQ-APERTURE

Gate: `BFE2_LATQ_DG_APERTURE_READY`

Tap29 only; frozen `D_crossing = 1529.871837153000 ps`; `Delta t = G_close - D_crossing`.
The 0.95 V normal source, 30 taps, 4/0 geometry, ideal Level-0 restoration, and real `LATQ_X0P5M_A9TR40` are unchanged.
Classification uses Q's own state sequence and final/tail state. D-to-Q delay is retained only as observed event evidence, never as a capture-safe-window definition.

| Point | Delta t (ps) | D crossing (ps) | G close (ps) | Q crossing(s) (ps) | Final Q | Final Q (V) | Source-free re-flip | Unresolved | Mid-rail | Classification |
|---|---:|---:|---:|---|---:|---:|---|---|---|---|
| CENTER | 4.652781414 | 1529.871837153000 | 1534.524618567000 | [] | 0 | 0.000000157 | False | False | False | `SAFE_REJECT` |
| MID | 15.000000000 | 1529.871837153000 | 1544.871837153000 | [] | 0 | 0.000000157 | False | False | False | `SAFE_REJECT` |
| RIGHT | 23.196735917 | 1529.871837153000 | 1553.068573070000 | [1562.0, 1565.0] | 0 | 0.000000157 | True | True | False | `UNSAFE_APERTURE` |
| LATE_CAPTURE | 45.000000000 | 1529.871837153000 | 1574.871837153000 | [1559.0] | 1 | 0.949999696 | False | False | False | `SAFE_CAPTURE` |

Ordered-boundary check: `True` (at least one SAFE_REJECT, then UNSAFE_APERTURE, then SAFE_CAPTURE in increasing Delta t).

This stage stops immediately; no self-calibration, M/F, FSM, detection, dense sweep, or later phase is authorized.
