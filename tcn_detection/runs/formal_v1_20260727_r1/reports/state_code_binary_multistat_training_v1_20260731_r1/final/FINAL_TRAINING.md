# Final Multistat CNN Training Tuning

All quality metrics are validation-only three-seed aggregates. No IID feature, prediction, or metric was loaded.

## Aggregate Validation Metrics

| Metric | Before retuning | After retuning | TCN |
| --- | ---: | ---: | ---: |
| Median Accuracy | 0.986763 | 0.987873 | 0.978101 |
| Median balanced accuracy | 0.979563 | 0.981712 | 0.984853 |
| Median Macro-F1 | 0.948381 | 0.952356 | 0.920481 |
| Median Critical PR-AUC | 0.894981 | 0.900391 | 0.861863 |
| Worst-seed Critical recall | 0.964212 | 0.964212 | 0.982794 |
| Median Safe FAR | 0.012536 | 0.011112 | 0.022223 |

## Selected Training Parameters

| Parameter | Value |
| --- | ---: |
| learning_rate | 0.004 |
| weight_decay | 1e-05 |
| batch_size | 256 |
| max_epochs | 120 |
| early_stopping_patience | 25 |
| lr_scheduler | none |

## Selected CNN Per Seed

| Seed | Best epoch | Accuracy | Balanced acc. | Macro-F1 | Critical PR-AUC | Critical precision | Critical recall | Safe FAR |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 20260725 | 66 | 0.987962 | 0.981712 | 0.953100 | 0.900489 | 0.858182 | 0.974535 | 0.011112 |
| 20260726 | 53 | 0.987873 | 0.976859 | 0.952356 | 0.897694 | 0.863748 | 0.964212 | 0.010494 |
| 20260727 | 84 | 0.987251 | 0.986778 | 0.951061 | 0.900391 | 0.842941 | 0.986235 | 0.012679 |

## Complexity

| Metric | Selected CNN | TCN |
| --- | ---: | ---: |
| Parameters | 3494 | 4050 |
| Estimated MAC/window | 106668 | 125952 |
| Recorded CPU ms/window | 0.297482 | 0.677508 |

Representative seed: `20260727`; checkpoint SHA256: `b6741281203fc4593b6434df584ace44cffa5daed23ece8745d1b14215a64814`.

This remains a validation-selected next-release candidate. The existing IID evaluation is unchanged and must not be rerun.
