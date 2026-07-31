# Final Binary CNN Structure Comparison

All quality metrics are validation-only three-seed aggregates. No IID inference or postprocessing was run.

## Aggregate Validation Metrics

| Metric | Original tuned CNN | Selected multistat CNN | TCN |
| --- | ---: | ---: | ---: |
| Median Accuracy | 0.981432 | 0.986763 | 0.978101 |
| Median balanced accuracy | 0.969382 | 0.979563 | 0.984853 |
| Median Macro-F1 | 0.929364 | 0.948381 | 0.920481 |
| Median Critical PR-AUC | 0.851604 | 0.894981 | 0.861863 |
| Worst-seed Critical recall | 0.951824 | 0.964212 | 0.982794 |
| Median Safe FAR | 0.016525 | 0.012536 | 0.022223 |

## Selected CNN Per Seed

| Seed | Best epoch | Accuracy | Balanced acc. | Macro-F1 | Critical PR-AUC | Critical precision | Critical recall | Safe FAR |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 20260725 | 50 | 0.986763 | 0.976265 | 0.948381 | 0.894981 | 0.850638 | 0.964212 | 0.011681 |
| 20260726 | 21 | 0.984542 | 0.979563 | 0.941090 | 0.888401 | 0.820290 | 0.973847 | 0.014721 |
| 20260727 | 77 | 0.987074 | 0.984441 | 0.950233 | 0.895448 | 0.843787 | 0.981418 | 0.012536 |

## Complexity

| Metric | Original tuned CNN | Selected multistat CNN | TCN |
| --- | ---: | ---: | ---: |
| Parameters | 1666.000000 | 3494.000000 | 4050.000000 |
| Estimated MAC/window | 50720.000000 | 106668.000000 | 125952.000000 |
| Recorded CPU ms/window | 0.194292 | 0.293603 | 0.677508 |

Representative seed: `20260725`; checkpoint SHA256: `e7df993fb75a7e4f609cd8f537cbaf9d25d729f05cbefb0ebddb88936351b9ea`.

This checkpoint is a validation-selected next-release candidate. The existing IID evaluation remains unchanged and must not be rerun.
