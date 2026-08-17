# FTC Standard-Cell Load Fine Stage

## Decision

**Standard-Cell Load Fine Stage + One-Medium-Step Coverage = NO-GO**

## Stage Status

| Stage | Status |
|---|---|
| Historical Medium Evidence Freeze | GO |
| Static Fine-Load Candidate Discovery | GO |
| Single-Load Electrical Screen | GO |
| 8-Unit Fine Bank | GO |
| Fine-Bank Sizing | NO-GO |
| Full-Bank One-Step Coverage | NOT_RUN |
| Full-Bank Monotonicity | NOT_RUN |
| Coupled Medium/Fine Gap Check | NOT_RUN |
| Future Bypass Interface | NOT_RUN |

## Frozen Medium Handoff

| VDD (V) | Medium max step (ps) | Medium min step (ps) |
|---:|---:|---:|
| 1.10 | 33.7037620000001 | 10.232424000000151 |
| 0.95 | 44.069194999999866 | 13.209050000000047 |
| 0.80 | 66.86260599999991 | 20.958529000000226 |

- N=16 path-selection evidence is frozen; its 41 HSPICE scenarios were not rerun.
- The measured output condition was no external receiver, so coupled medium steps were intentionally left for a bounded full-bank phase.

## Candidate Electrical Screen

| Candidate | Result | High-load control | Delta at 1.10 / 0.95 / 0.80 V (ps) |
|---|---|---:|---:|
| `NAND2_X0P5M_A9TL40__signal_A` | GO | 1 | 0.20438799999988078 / 0.18175600000012082 / 0.1998799999998937 |
| `NAND2_X0P5M_A9TL40__signal_B` | GO | 1 | 0.04176999999998543 / 0.025496000000089225 / 0.018892000000164444 |
| `NOR2_X0P5M_A9TL40__signal_A` | GO | 0 | 0.4210090000001401 / 0.4555729999999585 / 0.5315150000000131 |
| `NOR2_X0P5M_A9TL40__signal_B` | GO | 0 | 0.04888299999998935 / 0.035757000000046446 / 0.04480699999976423 |
- All four physical input-direction candidates passed the single-load integrity and resolution Gates; selection used the documented minimum predicted-bank-size priority.

## Direct Answers

1. Selected cell: `NOR2_X0P5M_A9TL40`; signal pin `A`; control pin `B`.
2. High-load control is 0; low-load control is 1.
3. Single-load rise-delay increments (ps): {'0.80': 0.5315150000000131, '0.95': 0.4555729999999585, '1.10': 0.4210090000001401}.
4. Each selected single-load increment is below the same-anchor frozen medium-step minimum.
5. The 8-unit 0.95 V full-code sweep and bounded high/low-voltage samples are strictly monotonic.

## 8-Unit Range And Bounded-K Gate

| VDD (V) | FineRange_8 (ps) | K prediction |
|---:|---:|---:|
| 1.10 | 4.287128999999879 | 63 |
| 0.95 | 4.30250499999994 | 82 |
| 0.80 | 4.6302789999998595 | 116 |

- Formula: `K_pred(V)=ceil(8*MediumStep_max(V)/FineRange_8(V))`.
- Conservative candidate K=116 exceeds the hard limit of 64; no K=65..116 decks were created.

6. K was derived only from the 8-unit measured range: K predictions {'0.80': 116, '0.95': 82, '1.10': 63} and conservative candidate K=116.
7. K_rescaled: None.
8-12. Full-bank monotonicity, coupled coverage, coupled medium steps, final resolution, and fixed-load offsets were not run because the bounded K Gate stopped the study.
13. No full-bank fixed overhead was measured: any future bypass study must first establish a bounded fine bank, then measure driver and code-0 bank offsets.
14. New physical HSPICE scenarios: 52; reused task scenarios in this finalization: 0.
15. The path-selection medium runner and all earlier FTC runners were not rerun.
16. This result addresses only standard-cell fine-load feasibility and one-medium-step coverage; it is not a complete FTC macro conclusion.

## Scope

- Historical medium scenarios were read-only and were not rerun.
- No bypass, configuration skip, sensor, XOR, DFF, calibration, droop, PVT, RTL, power, area, or layout work was performed.
