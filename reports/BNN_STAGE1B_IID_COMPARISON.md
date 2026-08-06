# BNN Stage 1-B IID Comparison

The IID evaluation was run exactly once after freezing the BNN packages.

| model | width | seed | K | event recall | Safe FAR | p95 TTD ns | MCC |
|---|---:|---:|---:|---:|---:|---:|---:|
| BNN | 8 | 11 | 14 | 0.7407 | 0.0305 | 44.4 | 0.7628 |
| BNN | 16 | 22 | 12 | 0.7037 | 0.0335 | 36.4 | 0.7552 |

## Frozen CNN IID reference

| candidate | event recall | Safe FAR | p95 TTD ns | MCC |
|---|---:|---:|---:|---:|
| CNN frozen | 0.7037 | 0.0081 | 62.8 | 0.9007 |

## Frozen CUSUM IID reference

| candidate | event recall | Safe FAR | p95 TTD ns | MCC |
|---|---:|---:|---:|---:|
| cusum_V07_H007 | 1.0000 | 0.0493 | 0.0 | 0.7446 |
| cusum_V07_H008 | 1.0000 | 0.0489 | 0.0 | 0.7461 |
