# Multistat Feature Distillation

Average, Maximum, and Endpoint were aligned with independent train-only projections.

| lambda stat | Epochs | Critical PR-AUC | Critical Recall | Macro-F1 | Safe FAR | Strict gate |
| ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 0.1 | 57 | 0.897354 | 0.972471 | 0.950637 | 0.011681 | fail |
| 0.2 | 23 | 0.896554 | 0.971094 | 0.949789 | 0.011824 | fail |
| 0.3 | 16 | 0.896455 | 0.969718 | 0.951153 | 0.011302 | fail |

- Selection: fallback_logit_kd
