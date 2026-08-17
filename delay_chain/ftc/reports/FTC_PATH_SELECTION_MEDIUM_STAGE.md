# FTC Path-Selection Medium Stage

## Decision

**Path-Selection Medium Stage = GO**

## Stage Status

| Stage | Status |
|---|---|
| Historical Evidence Freeze | GO |
| Static Path-Selection Contract | GO |
| N8 Code Monotonicity | GO |
| Stage-Count Scaling | GO |
| Medium-Step Characterization | GO |
| Future Fine-Stage Interface | GO |

## Structural Result

- The previous fast/slow unit chain forced every code through all selector stages, so increasing range also increased minimum delay.
- This study selects a shallow A exit or a recursively deeper B path; code 0 does not traverse later mux stages.

## N=8 Step Envelope

| VDD (V) | Min (ps) | Median (ps) | Max (ps) | Span (ps) |
|---:|---:|---:|---:|---:|
| 1.10 | 10.698175000000049 | 21.896225500000025 | 33.094276 | 243.22708499999996 |
| 0.95 | 13.948088000000041 | 43.873114000000044 | 44.055082999999996 | 321.3452959999999 |
| 0.80 | 20.61752399999989 | 43.73184699999991 | 66.84616999999993 | 489.2825499999999 |

## N Scaling

| N | D_min (ps) | D_max (ps) | Span (ps) |
|---:|---:|---:|---:|
| 1 | 36.74088099999995 | 50.67479000000003 | 13.933909000000078 |
| 4 | 36.80341600000008 | 183.10994200000005 | 146.30652599999996 |
| 8 | 36.80341600000008 | 358.148712 | 321.3452959999999 |
| 16 | 36.80341600000008 | 709.355653 | 672.5522369999999 |

## Future Fine-Stage Input

- Worst measured medium step: 66.86260599999991 ps.
- Future fine-stage range must cover at least that one worst-case medium step.

## Scenario Accounting

- New HSPICE scenarios: 41; reused task scenarios: 8.
- Phase 2 / Phase 3 / Phase 4 new counts: 19 / 10 / 12.

## Direct Answers

1. The previous unit chain was NO-GO because every code accumulated all fixed selector overhead; increasing N raised both maximum and minimum delay.
2. Here code 0 exits through X1 and one local mux, while larger codes select recursively deeper serial exits.
3. N=8 at 0.95 V is strictly monotonic across code 0..8; every measured adjacent rise-delay step is positive.
4. The three-anchor step minima, medians, and maxima are listed above from retained HSPICE measurements.
5. N=1/4/8/16 endpoint values and spans are listed above; span grows strictly with N.
6. N=4 to N=16 minimum-path drift is 0.0 ps versus a 43.873114000000044 ps typical 0.95 V medium step, so the shortest path does not scale with range.
7. A future fine stage must cover at least 66.86260599999991 ps, the worst measured medium step.
8. This study created 41 new HSPICE scenarios and logically reused 8 retained task scenarios.
9. The 3-bit refinement, acceptance-window, static-calibration, and fine-grained runners were not rerun.
10. Sensor, XOR, DFF, calibration, and droop work were excluded to isolate the medium-stage topology.
11. This GO advances only the medium stage to the next fine-stage study; it is not a complete FTC macro GO.

## Scope and Meaning

- Historical 3-bit, acceptance-window, static-calibration, and fine-grained runners were read-only evidence and were never run.
- No fine stage, sensor, XOR, DFF, calibration, droop, PVT, RTL, power, area, or layout work was performed.
- GO means only that this medium stage can inform a later fine-stage study; it is not a complete FTC macro GO.
