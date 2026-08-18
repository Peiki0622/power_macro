# FTC Fine-Stage Validation Contract Audit

## Decision

**Fine-Stage Delay-Line Waveform Contract = GO**

## Provisional Result

- Provisional fine driver/load/K: `BUF_X0P8M_A9TL40` / `NOR2_X4A_A9TL40__signal_A` / `10`. This is not a complete FTC macro GO.

## Direct Answers

1. The old Gate comes from `run_standard_cell_load_fine_stage.py:measurement_lines()` and `classify()`.
2. It checked voltages at fixed 2.5/5.5 ns times, not a receiver capture contract.
3. Every r2 record was reparsed from raw measures; the per-driver complete-pulse count is listed below.
4. The Phase-2 X0P8/K10 M15/F10 0.80 V path crossed 90% on its first rise at 2.533718 ns.
5. It returned through 10% on its first fall at 5.444582 ns.
6. Phase-2 result is `GO`; W_high90/W_low10 = 2676.240393 / 2664.162856 ps, both positive.
7. Three-voltage representative-boundary coverage is `GO`.
8. At 0.80 V, max fine step 10.138468 ps is below min coupled-medium step 20.395800 ps.
9. The four old NO-GO endpoints are validation false negatives: all 378 raw records have complete crossings and zero electrical waveform failures.
10. Stronger drivers reduce load sensitivity, reducing FineRange_8 and increasing required K.
11. Driver/load rescans are forbidden because this audit first isolates the validation contract.
12. The historical 378-scenario co-design matrix and all upstream medium/load/probe runs were not rerun.
13. New HSPICE scenarios: 19 (limit: 19).
14. A GO is only a delay-line waveform-contract GO; no consumer capture edge or setup/hold contract exists yet.
15. Bypass, configuration skip, and the real capture contract remain later architecture work, not this audit.

## Frozen Contract

- Driver/load/K: `BUF_X0P8M_A9TL40` / `NOR2_X4A_A9TL40__signal_A` / `10`.
- Legacy ratios remain `0.9` / `0.1`; they were not relaxed.
- Phase 3 completed 18/18 endpoint scenarios.

## r2 Crossing Reclassification

| Driver | Complete 10/50/90 pulse records | Fixed-sample misses | Electrical waveform failures |
|---|---:|---:|---:|
| `BUF_X0P8M_A9TL40` | 86 | 1 | 0 |
| `BUF_X1M_A9TL40` | 89 | 1 | 0 |
| `BUF_X1P4M_A9TL40` | 97 | 1 | 0 |
| `BUF_X2M_A9TL40` | 106 | 1 | 0 |

## X0P8/K10 Coverage Margins

| VDD (V) | M0→1 / M7→8 / M15→16 margin (ps) |
|---:|---:|
| 1.10 | 32.969189/31.646754/55.269577 |
| 0.95 | 29.097720/28.289514/58.453985 |
| 0.80 | 12.804907/12.257002/57.179659 |
