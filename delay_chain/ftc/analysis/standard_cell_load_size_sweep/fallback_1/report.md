# Bounded Fallback Acceptance

- Primary candidate: `NAND2_X6M_A9TL40__signal_A`.
- Fallback candidate: `NOR2_X4A_A9TL40__signal_A` (rank 2 by the frozen four-metric order).
- Fallback decision: `NO-GO`.
- New HSPICE scenarios: `59`; scenario manifests: `59 PASS`, `0 FAIL`.
- Raw evidence: `delay_chain/ftc/runs/standard_cell_load_size_sweep_fallback_1/r1/`.
- Analysis evidence: `delay_chain/ftc/analysis/standard_cell_load_size_sweep/fallback_1/`.

## Fallback Measurements

- Initial/final K: `8` / `8`.
- Maximum adjacent fine step (1.10/0.95/0.80 V, ps): `8.308268000000055` / `9.924158999999918` / `11.57256499999994`.
- Minimum coupled medium step (1.10/0.95/0.80 V, ps): `10.20342200000016` / `13.825846999999953` / `20.43259600000033`.

## Measured Reasons

- primary candidate NAND2_X6M_A9TL40__signal_A failed full acceptance; bounded rank-2 fallback was measured
- 0.80 V M15->16 coverage failed
- 1.10 V fine resolution is not below coupled medium step

## Invalid Electrical Measurement

- `scenarios/winner_coupled_medium__m15__k08__f08__v0p80__ba2bb1c61505037ab22e`: VDD=0.8 V, M=15 -> 16, F=8, output high=0.717393004 VDD, output low=0.0118503303 VDD.
