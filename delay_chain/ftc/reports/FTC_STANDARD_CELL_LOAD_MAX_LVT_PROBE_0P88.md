# FTC Maximum-LVT Fine-Load Follow-On (0.88 VDD Policy)

## Decision

**Standard-Cell Load Fine Stage + One-Medium-Step Coverage = NO-GO under the explicitly authorized 0.88 VDD high-level policy.**

The original 0.90 VDD evidence remains separate and unchanged. The failure below is not an HSPICE execution failure: all retained scenarios completed with valid listings and measurement files.

## Stage Status

| Stage | Status |
|---|---|
| Historical Medium Evidence Freeze | GO |
| Static Fine-Load Candidate Discovery | GO |
| Single-Load Electrical Screen | GO |
| 8-Unit Fine Bank | GO |
| Fine-Bank Sizing | GO |
| Full-Bank One-Step Coverage | GO |
| Full-Bank Monotonicity | GO |
| Coupled Medium/Fine Gap Check | NO-GO |
| Future Bypass Interface | NOT_RUN |

## Waveform Policy

- Output-high acceptance: `>= 0.88 * VDD`.
- Output-low acceptance: `<= 0.10 * VDD`.
- Positive rise/fall propagation, positive 10%-90% edge intervals, and zero extra transitions remain mandatory.
- This policy is a user-authorized exception for this maximum-LVT follow-on only.

## Selected Candidate

| Candidate | Result | High-load control | Delta 1.10 / 0.95 / 0.80 V (ps) |
|---|---|---:|---:|
| `NAND2_X8M_A9TL40__signal_A` | GO and selected | 1 | 6.721946 / 6.440552 / 5.971724 |
| `NAND2_X8M_A9TL40__signal_B` | GO | 1 | 2.950481 / 2.147337 / 1.816912 |
| `NOR2_X8A_A9TL40__signal_A` | REJECTED | 0 | 10.780169 / 11.028492 / 10.840325 |
| `NOR2_X8A_A9TL40__signal_B` | GO | 0 | 2.424284 / 2.403228 / 1.319375 |

The selected structure remains the fixed `BUF_X0P7M_A9TL40` driver followed by parallel `NAND2_X8M_A9TL40` input loads, with signal pin `A` and control pin `B`.

## K Sizing

| VDD (V) | FineRange_8 (ps) | K prediction |
|---:|---:|---:|
| 1.10 | 104.125304 | 3 |
| 0.95 | 124.076224 | 3 |
| 0.80 | 160.400464 | 4 |

The offline candidate was `K=4`, within the hard limit of 64. The first real coupled coverage check had a range gap, so the plan's single permitted rescale produced `K_rescaled=5`. No iterative K sweep was performed.

## Coupled Evidence

For `K=5`, the coverage margins `D(M,K,V)-D(M+1,0,V)` for `M=0,7,15` were:

| VDD (V) | M=0 | M=7 | M=15 |
|---:|---:|---:|---:|
| 1.10 | 28.871419 ps | 28.331908 ps | 51.950205 ps |
| 0.95 | 28.511892 ps | 28.149436 ps | 59.589937 ps |
| 0.80 | 19.769114 ps | 19.799574 ps | invalid waveform |

The `0.80 V, M=15, F=5` endpoint measured `output_logic_high=0.5558779 V` and `output_logic_low=0.0887951 V`. The delay ordering itself had positive margin, but the row is electrically invalid because the high and low logic levels violate the accepted limits.

## Resolution Gate

| VDD (V) | Maximum measured fine step (ps) | Minimum coupled medium step (ps) |
|---:|---:|---:|
| 1.10 | 13.801095 | 10.238465 |
| 0.95 | 16.687787 | 13.205327 |
| 0.80 | 23.001368 | 21.371043 |

All three fail `delta_fine_max(V) < MediumStep_coupled_min(V)`. This is a measured hierarchy failure caused by the large X8 input-load increment, independent of the small 0.90-to-0.88 high-level waiver.

## Evidence Accounting

- New physical HSPICE scenarios retained in this follow-on: 113.
- Final continuation invocation reused 70 exact PASS scenarios and added 43 final scenarios.
- Historical medium scenarios rerun: 0.
- Historical FTC runner invocations: 0.
- Bypass, sensor, XOR, DFF, calibration, droop, PVT, RTL, power, area, and layout scenarios: 0.

The original plan stops here. The measured result does not support proceeding to the bypass stage with the maximum LVT X8 load under the stated resolution and waveform requirements.
