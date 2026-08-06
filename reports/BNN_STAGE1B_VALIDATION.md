# BNN Stage 1-B Validation Comparison

Stage 1-B is validation-frozen before IID.  The primary candidate is `8` with K=14 and seed 11.

| model | stage | width | seed | K | event recall | Safe FAR | p95 TTD ns | MCC |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| CNN W8/A8 | validation | 8 | - | - | 0.7917 | 0.0128 | 20.4 | 0.8854 |
| FP thermometer | validation | 8 | 11 | 14 | 0.7500 | 0.0366 | 37.2 | 0.7557 |
| W1A8 BNN | validation | 8 | 11 | 14 | 0.6667 | 0.0353 | 52.0 | 0.7477 |
| W1A1 BNN | validation | 8 | 11 | 14 | 0.7500 | 0.0377 | 41.2 | 0.7453 |
| FP thermometer | validation | 16 | 22 | 12 | 0.8333 | 0.0428 | 28.4 | 0.7388 |
| W1A8 BNN | validation | 16 | 22 | 12 | 0.7500 | 0.0472 | 37.2 | 0.7181 |
| W1A1 BNN | validation | 16 | 22 | 12 | 0.7500 | 0.0397 | 36.6 | 0.7406 |

## Frozen CNN reference

| candidate | event recall | Safe FAR | p95 TTD ns | MCC |
|---|---:|---:|---:|---:|
| CNN frozen | 0.7917 | 0.0128 | 20.4 | 0.8854 |

## Frozen CUSUM reference

| candidate | event recall | Safe FAR | p95 TTD ns | MCC |
|---|---:|---:|---:|---:|
| cusum_V07_H007 | 1.0000 | 0.0497 | 0.0 | 0.7432 |
| cusum_V07_H008 | 1.0000 | 0.0492 | 0.0 | 0.7448 |
