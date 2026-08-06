# Fast Detection Stage 1 Algorithm Screening

## Decision

The validation-only search evaluated 2,048 candidates across eight detector families. The frozen Top-2 are `cusum_V07_H007` and `cusum_V07_H008`; both use only integer residual accumulation and have no multiplier.

IID was evaluated once after freezing. No threshold, feature, model, or candidate ordering was changed from that result.

## Validation metrics

| detector | family | event recall | Safe FAR | median TTD ns | p95 TTD ns | max TTD ns |
|---|---|---:|---:|---:|---:|---:|
| CNN baseline | fixed W8/A8 L32 | 0.7917 | 0.0128 | 8.0 | 20.4 | 24.0 |
| amplitude_slope_A00_S00 | amplitude_slope | 0.0833 | 0.0415 | 0.0 | 0.0 | 0.0 |
| cusum_V07_H007 | cusum | 1.0000 | 0.0497 | 0.0 | 0.0 | 0.0 |
| ewma_q4_T02 | ewma_residual | 1.0000 | 0.0438 | 0.0 | 0.0 | 0.0 |
| int8_scorecard_T-148 | int8_scorecard | 1.0000 | 0.0384 | 0.0 | 3.4 | 4.0 |
| multistat_fsm_scale1 | multistat_fsm | 1.0000 | 0.9768 | 0.0 | 0.0 | 0.0 |
| shallow_tree_D1_L16 | shallow_tree | 1.0000 | 0.0313 | 0.0 | 0.0 | 0.0 |
| single_threshold_T24 | single_threshold | 1.0000 | 0.0486 | 0.0 | 0.0 | 0.0 |
| threshold_confirm_T23_K01 | threshold_confirm | 1.0000 | 0.0486 | 0.0 | 0.0 | 0.0 |

## One-shot IID metrics

| detector | family | event recall | Safe FAR | median TTD ns | p95 TTD ns | max TTD ns |
|---|---|---:|---:|---:|---:|---:|
| CNN baseline | fixed W8/A8 L32 | 0.7037 | 0.0081 | 8.0 | 62.8 | 88.0 |
| cusum_V07_H007 | cusum | 1.0000 | 0.0493 | 0.0 | 0.0 | 0.0 |
| cusum_V07_H008 | cusum | 1.0000 | 0.0489 | 0.0 | 0.0 | 0.0 |

## Hardware cost

The `recall_vs_area.png` x-axis is explicitly a structural resource-count proxy, not physical synthesized area. It is `add/sub + compare + multiplier + state_bits/8 + memory_bits/8`; technology mapping, timing, and power are intentionally deferred to RTL.

| design | add/sub | compare | multiplier | state bits | memory bits | cycles/sample | proxy |
|---|---:|---:|---:|---:|---:|---:|---:|
| CNN baseline | 49068 | 1 | 49068 | 192 | 13472 | None | 99845.00 |
| amplitude_slope | 2 | 2 | 0 | 6 | 0 | 1 | 4.75 |
| cusum | 2 | 3 | 0 | 8 | 0 | 1 | 6.00 |
| ewma_residual | 3 | 1 | 0 | 12 | 0 | 1 | 5.50 |
| int8_scorecard | 6 | 1 | 5 | 38 | 72 | 1 | 25.75 |
| multistat_fsm | 6 | 18 | 0 | 30 | 0 | 1 | 27.75 |
| shallow_tree | 1 | 1 | 0 | 30 | 72 | 1 | 14.75 |
| single_threshold | 0 | 1 | 0 | 1 | 0 | 1 | 1.12 |
| threshold_confirm | 1 | 2 | 0 | 4 | 0 | 1 | 3.50 |

## Pareto evidence

The validation FAR-qualified Pareto points (recall maximized, p95 TTD and structural proxy minimized) are:

- `single_threshold_T24` (single_threshold) recall 1.0000, p95 0.0 ns, proxy 1.12
- `single_threshold_T25` (single_threshold) recall 1.0000, p95 0.0 ns, proxy 1.12
- `single_threshold_T26` (single_threshold) recall 1.0000, p95 0.0 ns, proxy 1.12
- `single_threshold_T27` (single_threshold) recall 1.0000, p95 0.0 ns, proxy 1.12
- `single_threshold_T28` (single_threshold) recall 1.0000, p95 0.0 ns, proxy 1.12
- `single_threshold_T29` (single_threshold) recall 1.0000, p95 0.0 ns, proxy 1.12
- `single_threshold_T30` (single_threshold) recall 1.0000, p95 0.0 ns, proxy 1.12
- `single_threshold_T31` (single_threshold) recall 1.0000, p95 0.0 ns, proxy 1.12
- `single_threshold_T32` (single_threshold) recall 1.0000, p95 0.0 ns, proxy 1.12

## Boundary and next step

All detectors consume only `sensor_code` and `code_valid`; measured VDD and configured droop are not runtime features. Labels remain same-sample Safe/Critical with Warning merged into Safe. The two CUSUM configurations are the Stage 2 RTL microarchitecture candidates.
