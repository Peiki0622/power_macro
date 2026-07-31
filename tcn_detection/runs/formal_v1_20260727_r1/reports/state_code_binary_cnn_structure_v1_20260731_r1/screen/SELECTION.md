# Binary CNN Structure Search

All metrics are validation-only three-seed aggregates. No IID feature or metric was loaded.

| Rank | Structure | RF | Params | MAC | Median PR-AUC | Median Accuracy | Median Macro-F1 | Worst Critical recall | Median Safe FAR | Feasible |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | dilated_k5_d124 | 29 | 2722 | 84512 | 0.857864 | 0.982765 | 0.934849 | 0.965588 | 0.016335 | True |
| 2 | dilated_k3_d1248 | 31 | 2450 | 75296 | 0.854474 | 0.981610 | 0.931855 | 0.968341 | 0.018614 | True |
| 3 | baseline_avg_k3 | 7 | 1666 | 50720 | 0.851604 | 0.981432 | 0.929364 | 0.951824 | 0.016525 | True |
| 4 | multistat_k5 | 13 | 2786 | 84576 | 0.883547 | 0.985608 | 0.944211 | 0.943565 | 0.012394 | False |
| 5 | multistat_k3 | 7 | 1730 | 50784 | 0.877729 | 0.982232 | 0.929057 | 0.889883 | 0.014246 | False |
| 6 | dilated_w24_k3_d124 | 15 | 3650 | 112944 | 0.795816 | 0.976501 | 0.914740 | 0.967653 | 0.022888 | False |

TCN validation Critical PR-AUC: `0.861863`; parameters: `4050`; MAC/window: `125952`.

Selected structure: `dilated_k5_d124`.
