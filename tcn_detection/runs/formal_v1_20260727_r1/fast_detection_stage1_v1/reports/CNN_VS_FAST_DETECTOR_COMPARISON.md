# CNN vs Fast Detector Comparison

This comparison keeps the frozen W8/A8 L32 CNN as reference and evaluates only the two validation-frozen fast candidates on IID once.

| detector | split | event recall | p95 TTD ns | Safe FAR | multiplier count | state bits |
|---|---|---:|---:|---:|---:|---:|
| CNN baseline | validation | 0.7917 | 20.4 | 0.0128 | 49068 | 192 |
| CNN baseline | iid_test_once | 0.7037 | 62.8 | 0.0081 | 49068 | 192 |
| cusum_V07_H007 | iid_test_once | 1.0000 | 0.0 | 0.0493 | 0 | 8 |
| cusum_V07_H008 | iid_test_once | 1.0000 | 0.0 | 0.0489 | 0 | 8 |

The IID result is descriptive only. It was not used to tune thresholds or select between H=7 and H=8. Both CUSUM candidates provide one-cycle/sample operation, zero multipliers, and a large structural reduction relative to the CNN; their implementation decision is intentionally deferred to RTL verification.
