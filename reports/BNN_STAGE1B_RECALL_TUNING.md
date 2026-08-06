# BNN Stage 1-B Recall Tuning

This is a narrow, validation-only tuning pass on the existing W1A1 BNN-S
checkpoint (`width=8`, `seed=11`).  The network, input encoding, causal
window, binary weights, and folded thresholds are unchanged.  Only the final
K-of-32 temporal vote threshold was selected again.

The selection rule was fixed before the IID replay:

> maximize validation Event Recall subject to Safe FAR <= 0.05.

No IID sample was used to select K or alter the checkpoint.  The complete
validation K=1..32 grid is recorded in the frozen evidence JSON.

## Validation

| detector | K | Event Recall | Safe FAR | MCC | F1 macro | p50 TTD (ns) | p95 TTD (ns) |
|---|---:|---:|---:|---:|---:|---:|---:|
| CNN W8/A8 frozen | - | 0.7917 | 0.0128 | 0.8854 | 0.9416 | 8.0 | 20.4 |
| CUSUM V07/H007 frozen | - | 1.0000 | 0.0497 | 0.7432 | 0.8548 | 0.0 | 0.0 |
| CUSUM V07/H008 frozen | - | 1.0000 | 0.0492 | 0.7448 | 0.8559 | 0.0 | 0.0 |
| BNN-S W1A1 previous freeze | 14 | 0.7500 | 0.0377 | 0.7453 | 0.8641 | 24.0 | 41.2 |
| BNN-S W1A1 recall-tuned | 10 | 0.7917 | 0.0496 | 0.7188 | 0.8446 | 8.0 | 24.8 |

Relative to the previous BNN freeze, K10 gains 4.17 percentage points of
validation Event Recall and reduces p95 TTD by 16.4 ns.  It consumes almost
the full FAR budget (+1.19 percentage points) and lowers MCC by 0.0265.
K9 has higher recall (`0.8333`) but fails the FAR gate (`0.0535`), so it is not
the selected candidate.

## IID replay

The frozen K10 package was replayed once through the online detector on all 48
IID traces (24,000 samples), using the same full-stream metric convention as
the prior BNN IID report.

| detector | K | Event Recall | Safe FAR | MCC | F1 macro | p50 TTD (ns) | p95 TTD (ns) |
|---|---:|---:|---:|---:|---:|---:|---:|
| CNN W8/A8 frozen | - | 0.7037 | 0.0081 | 0.9007 | 0.9502 | 8.0 | 62.8 |
| CUSUM V07/H007 frozen | - | 1.0000 | 0.0493 | 0.7446 | 0.8557 | 0.0 | 0.0 |
| CUSUM V07/H008 frozen | - | 1.0000 | 0.0489 | 0.7461 | 0.8567 | 0.0 | 0.0 |
| BNN-S W1A1 previous freeze | 14 | 0.7407 | 0.0305 | 0.7628 | 0.8751 | 26.0 | 44.4 |
| BNN-S W1A1 recall-tuned | 10 | 0.7407 | 0.0404 | 0.7381 | 0.8575 | 10.0 | 28.4 |

K10 does not increase IID Event Recall, but it preserves the previous
`0.7407` recall and improves p95 TTD by 16.0 ns.  The cost is higher IID FAR
and lower MCC.  CUSUM remains the stronger recall-first baseline.

## Deployment and evidence

The new package is immutable and independent of the earlier `r5` package:

- `bnn_stage1b_recall_tuned_v1_20260806_r1/packages/bnn_s_w8_k10_seed11/`
- `bnn_stage1b_recall_tuned_v1_20260806_r1/artifacts/recall_tuned_freeze.json`
- `bnn_stage1b_recall_tuned_v1_20260806_r1/iid_test_once/IID_TEST_EVALUATION.json`

Export verification passed for all 22,512 validation windows:

```
training temporal bits == bit-true temporal bits
training alarms      == bit-true alarms
```

The package has no multipliers, stores 1-bit weights, and has no classifier or
floating-point inference state.  Its recorded cost proxy is 30,976 XNOR
operations, 544 popcount operations, 106 threshold bits, and 1,008 total
package memory bits.

The original Stage 1 selection and frozen CUSUM RTL direction are unchanged.
Because the BNN MCC target relative to CNN is not met, this tuned BNN remains a
supplementary ablation rather than a replacement detector.
