# BFE12 P0 Authority and Reuse Matrix

Gate: `BFE12_SIGN0_P0_AUTHORITIES_FROZEN`

## Reused without rerun

- BFE8 startup references and margins: `BFE8_HEALTHY_PER_SEED.csv`, `BFE8_D02_MARGIN_LOCK.json`.
- BFE8 healthy FPR and D02 targets: `BFE8_D02_HEALTHY_FPR.csv`, `BFE8_D02_HEALTHY_FPR_METRICS.json`, `BFE8_D02_PER_SEED.csv`.
- BFE9 D01 targets: `BFE9_D01_PER_SEED.csv`.
- ARCH1 signed audit: `ARCH1_SIGNED_ERROR_PER_SAMPLE.csv` and its gate JSON.
- BFE11 D04 targets and signed shadow: `BFE11_D04_PER_SEED.csv`, `BFE11_D04_SIGNED_SHADOW.json`.
- ARCH0 RTL and RTL2 timing discipline remain reference authorities and are not edited.

## Explicitly excluded

- No HSPICE, PrimeSim, physical source/capture rerun, DC, STA, P&R, or waveform regeneration.
- No fine-step tracker, FALL signed comparator, threshold sweep, frontend/capture change, or ARCH0 rewrite.

## New scientific regressions

Exactly two logical VCS regressions are reserved: one directed full-top test in P2 and one retained-data controller A/B replay in P4. A compile or harness retry may repeat only the same stimulus and must be recorded in the run ledger.
