# Frozen IID Binary CNN vs TCN

This is a reporting-only comparison of existing one-shot IID outputs. Neither model was rerun and no IID result changed the frozen CNN replacement decision. The CNN remains the project default, but its quality and event gates do not support a deployment-readiness claim.

## Window Metrics

| Metric | TCN raw | CNN raw | TCN post | CNN post |
| --- | ---: | ---: | ---: | ---: |
| Accuracy | 0.985386 | 0.972193 | 0.984275 | 0.955268 |
| Balanced accuracy | 0.983532 | 0.914283 | 0.989031 | 0.941466 |
| Macro-F1 | 0.944323 | 0.891176 | 0.941168 | 0.851552 |
| Weighted F1 | 0.985970 | 0.972960 | 0.985031 | 0.959628 |
| MCC | 0.892580 | 0.784014 | 0.888047 | 0.724118 |
| Safe FAR | 0.014340 | 0.019231 | 0.016429 | 0.042688 |
| Critical FNR | 0.018595 | 0.152204 | 0.005510 | 0.074380 |
| Specificity | 0.985660 | 0.980769 | 0.983571 | 0.957312 |
| Negative predictive value | 0.998701 | 0.989414 | 0.999614 | 0.994672 |
| Safe precision | 0.998701 | 0.989414 | 0.999614 | 0.994672 |
| Safe recall | 0.985660 | 0.980769 | 0.983571 | 0.957312 |
| Safe F1 | 0.992138 | 0.985072 | 0.991527 | 0.975635 |
| Safe support | 21060 | 21060 | 21060 | 21060 |
| Critical precision | 0.825130 | 0.752445 | 0.806704 | 0.599198 |
| Critical recall | 0.981405 | 0.847796 | 0.994490 | 0.925620 |
| Critical F1 | 0.896508 | 0.797280 | 0.890808 | 0.727470 |
| Critical support | 1452 | 1452 | 1452 | 1452 |

## Probability Metrics

| Metric | TCN | CNN |
| --- | ---: | ---: |
| Critical PR-AUC | 0.901720 | 0.853293 |
| Safe PR-AUC | 0.999581 | 0.999228 |
| Macro PR-AUC | 0.950651 | 0.926261 |
| Critical ROC-AUC | 0.995847 | 0.990558 |
| Safe ROC-AUC | 0.995847 | 0.990558 |
| Macro ROC-AUC | 0.995847 | 0.990558 |
| Log loss | 0.039408 | 0.069786 |
| Binary Brier score | 0.011936 | 0.020461 |
| ECE, 15 bins | 0.008021 | 0.008820 |

## Confusion Matrices

| Variant | TN | FP | FN | TP |
| --- | ---: | ---: | ---: | ---: |
| TCN raw | 20758 | 302 | 27 | 1425 |
| CNN raw | 20655 | 405 | 221 | 1231 |
| TCN post | 20714 | 346 | 8 | 1444 |
| CNN post | 20161 | 899 | 108 | 1344 |

## Event Metrics

| Metric | TCN raw | CNN raw | TCN post | CNN post |
| --- | ---: | ---: | ---: | ---: |
| Trace count | 48 | 48 | 48 | 48 |
| Critical event count | 27 | 27 | 27 | 27 |
| Critical event detection rate | 0.888889 | 0.703704 | 0.962963 | 0.740741 |
| Median Critical delay (ns) | 0.000000 | 60.000000 | 0.000000 | 20.000000 |
| P95 Critical delay (ns) | 15.400000 | 80.400000 | 4.000000 | 40.400000 |
| False-alarm episodes | 15 | 10 | 12 | 14 |
| False alarms / trace | 0.312500 | 0.208333 | 0.250000 | 0.291667 |
| Mean recovery delay (samples) | 9.680000 | 13.800000 | 10.440000 | 22.160000 |

## Hard Pairs

| Metric | TCN | CNN |
| --- | ---: | ---: |
| Pair count | 2 | 2 |
| Scorable pair count | 2 | 2 |
| Pair accuracy | 0.500000 | 0.000000 |

## Paired Decisions

| Count | Raw | Postprocessed |
| --- | ---: | ---: |
| agreement | 22051 | 21755 |
| disagreement | 461 | 757 |
| old_safe_binary_critical | 185 | 605 |
| old_critical_binary_safe | 276 | 152 |
| both_correct | 21804 | 21453 |
| both_wrong | 247 | 302 |
| old_only_correct | 379 | 705 |
| binary_only_correct | 82 | 52 |

Here `old` means TCN and `binary` means CNN in the compatibility field names above.

## Complexity

| Metric | TCN | CNN | CNN reduction |
| --- | ---: | ---: | ---: |
| Parameters | 4050 | 1666 | 58.864198% |
| Estimated MAC/window | 125952 | 50720 | 59.730691% |
| Median CPU ms/window | 0.677507 | 0.194292 | 71.322605% |

## Decision

- Final default model: binary 1D-CNN.
- TCN status: frozen historical quality baseline.
- Deployment ready: no.
- Aligned IID endpoints: 22512.
- `parameters_tuned_on_test=false`.
- `pristine_blind_test=false`.
- `rerun_authorized=false`.
