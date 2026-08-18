# FTC Standard-Cell Load Fine Stage

## Decision

**Standard-Cell Load Fine Stage + One-Medium-Step Coverage = NO-GO**

## Stage Status

| Stage | Status |
|---|---|
| Historical Medium Evidence Freeze | GO |
| Static Fine-Load Candidate Discovery | GO |
| Single-Load Electrical Screen | GO |
| 8-Unit Fine Bank | NO-GO |
| Fine-Bank Sizing | NOT_RUN |
| Full-Bank One-Step Coverage | NOT_RUN |
| Full-Bank Monotonicity | NOT_RUN |
| Coupled Medium/Fine Gap Check | NOT_RUN |
| Future Bypass Interface | NOT_RUN |

## Frozen Medium Handoff

The existing N=16 path-selection medium evidence was read only. Its maximum/minimum measured step values were 33.703762/10.232424 ps at 1.10 V, 44.069195/13.209050 ps at 0.95 V, and 66.862606/20.958529 ps at 0.80 V. No historical medium scenario was rerun.

## Candidate Electrical Screen

| Candidate | Result | High-load control | Delta 1.10 / 0.95 / 0.80 V (ps) |
|---|---|---:|---:|
| `NAND2_X8M_A9TL40__signal_A` | GO | 1 | 6.721946 / 6.440552 / 5.971724 |
| `NAND2_X8M_A9TL40__signal_B` | GO | 1 | 2.950481 / 2.147337 / 1.816912 |
| `NOR2_X8A_A9TL40__signal_A` | REJECTED | 0 | 10.780169 / 11.028492 / 10.840325 |
| `NOR2_X8A_A9TL40__signal_B` | GO | 0 | 2.424284 / 2.403228 / 1.319375 |

All 27 Phase-2 scenarios passed HSPICE listing and measurement integrity. `NOR2_X8A__signal_A` was rejected because its 1.10 V increment exceeded the 10.232424 ps medium minimum. The documented selection priority therefore chose `NAND2_X8M__signal_A`.

## 8-Unit Gate Evidence

The required 25 Phase-3 scenarios were completed and retained. The 0.95 V sweep and the 1.10 V samples were strictly increasing. At `0.80 V, medium=8, fine=8`, however, the output-high measurement was `0.709636 V`, below the validity threshold `0.72 V` (`0.9 * VDD`). The row was therefore marked invalid. This is a real loaded-driver waveform failure, not an HSPICE execution failure, so the plan correctly stops before K sizing.

## Direct Answers

1. Selected cell: `NAND2_X8M_A9TL40`; signal pin `A`; control pin `B`.
2. High-load control is 1; low-load control is 0.
3. Single-load rise-delay increments (ps): {'1.10': 6.721946000000003, '0.95': 6.440552000000082, '0.80': 5.971724000000108}.
4. Each selected single-load increment is below the same-anchor frozen medium-step minimum.
5. The selected maximum-size bank fails the required 8-unit waveform-validity Gate at the 0.80 V all-high endpoint; no valid K is derived.
 
## Gate Reasons

- `fine code 8 lacks a valid rising-delay measurement`
14. New physical HSPICE scenarios: 25; reused task scenarios in this finalization: 27.
15. The path-selection medium runner and all earlier FTC runners were not rerun.
16. This result addresses only standard-cell fine-load feasibility and one-medium-step coverage; it is not a complete FTC macro conclusion.

## Scope

- Historical medium scenarios were read-only and were not rerun.
- No bypass, configuration skip, sensor, XOR, DFF, calibration, droop, PVT, RTL, power, area, or layout work was performed.
