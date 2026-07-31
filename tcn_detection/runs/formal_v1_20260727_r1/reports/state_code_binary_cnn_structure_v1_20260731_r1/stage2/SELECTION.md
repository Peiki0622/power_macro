# Binary CNN Structure Search

All metrics are validation-only three-seed aggregates. No IID feature or metric was loaded.

| Rank | Structure | RF | Params | MAC | Median PR-AUC | Median Accuracy | Median Macro-F1 | Worst Critical recall | Median Safe FAR | Feasible |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | multistat_w18_k5 | 13 | 3494 | 106668 | 0.894981 | 0.986763 | 0.948381 | 0.964212 | 0.012536 | True |
| 2 | dilated_k5_d124 | 29 | 2722 | 84512 | 0.857864 | 0.982765 | 0.934849 | 0.965588 | 0.016335 | True |
| 3 | multistat_k7 | 19 | 3842 | 118368 | 0.893911 | 0.985785 | 0.944834 | 0.875430 | 0.012109 | False |
| 4 | multistat_w14_d4_k5 | 17 | 3152 | 96404 | 0.890976 | 0.986141 | 0.946277 | 0.927736 | 0.012726 | False |
| 5 | multistat_k5 | 13 | 2786 | 84576 | 0.883547 | 0.985608 | 0.944211 | 0.943565 | 0.012394 | False |
| 6 | multistat_w12_d5_k5 | 21 | 3074 | 94152 | 0.878567 | 0.981699 | 0.930184 | 0.905024 | 0.013011 | False |

TCN validation Critical PR-AUC: `0.861863`; parameters: `4050`; MAC/window: `125952`.

Selected structure: `multistat_w18_k5`.
