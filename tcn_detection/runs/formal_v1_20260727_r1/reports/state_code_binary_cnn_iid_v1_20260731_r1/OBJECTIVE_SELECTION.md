# Binary CNN Objective Selection

Architecture/history: `large_L32`. This report is validation-only.

| Arm | Critical PR-AUC | Accuracy | Balanced accuracy | Macro-F1 | Worst recall | Safe FAR | Feasible |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| a_natural_ce | 0.833067 | 0.971215 | 0.920540 | 0.889535 | 0.861666 | 0.021274 | no |
| b_sqrt_ce | 0.828330 | 0.966818 | 0.929403 | 0.878645 | 0.878871 | 0.027637 | no |
| c_sqrt_focal | 0.825393 | 0.965796 | 0.927575 | 0.875426 | 0.883689 | 0.028539 | no |
| d_balanced_sampler_ce | 0.820959 | 0.952958 | 0.941263 | 0.845784 | 0.924295 | 0.045301 | no |

Selected `a_natural_ce` using `mandatory_cnn_quality_fallback`.
