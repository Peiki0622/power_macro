# Frozen IID Safe/Critical Comparison

This report projects the already-frozen three-class output as Safe/Warning -> non-Critical and Critical -> Critical. No model was rerun and no parameter was tuned on IID.

## Window Metrics

| Metric | Old raw | Binary raw | Old post | Binary post |
| --- | ---: | ---: | ---: | ---: |
| Accuracy | 0.985030 | 0.985386 | 0.984231 | 0.984275 |
| Balanced accuracy | 0.966671 | 0.983532 | 0.985159 | 0.989031 |
| Macro-F1 | 0.941328 | 0.944323 | 0.940613 | 0.941168 |
| Weighted F1 | 0.985433 | 0.985970 | 0.984943 | 0.985031 |
| MCC | 0.884404 | 0.892580 | 0.886241 | 0.888047 |
| Safe FAR | 0.012251 | 0.014340 | 0.015907 | 0.016429 |
| Critical false-negative rate | 0.054408 | 0.018595 | 0.013774 | 0.005510 |
| Specificity | 0.987749 | 0.985660 | 0.984093 | 0.983571 |
| Negative predictive value | 0.996217 | 0.998701 | 0.999036 | 0.999614 |
| Critical precision | 0.841815 | 0.825130 | 0.810413 | 0.806704 |
| Critical recall | 0.945592 | 0.981405 | 0.986226 | 0.994490 |
| Safe precision | 0.996217 | 0.998701 | 0.999036 | 0.999614 |
| Safe recall | 0.987749 | 0.985660 | 0.984093 | 0.983571 |
| Safe F1 | 0.991965 | 0.992138 | 0.991508 | 0.991527 |
| Critical F1 | 0.890691 | 0.896508 | 0.889717 | 0.890808 |

## Probability Metrics

Probability metrics are operating-point independent, so raw and postprocessed values are identical within each model.

| Metric | Old projected | Binary |
| --- | ---: | ---: |
| Critical PR-AUC | 0.906573 | 0.901720 |
| Safe PR-AUC | 0.999591 | 0.999581 |
| Macro PR-AUC | 0.953082 | 0.950651 |
| Critical ROC-AUC | 0.996012 | 0.995847 |
| Safe ROC-AUC | 0.996012 | 0.995847 |
| Macro ROC-AUC | 0.996012 | 0.995847 |
| Log loss | 0.035553 | 0.039408 |
| Binary Brier score | 0.011034 | 0.011936 |
| ECE (15 bins) | 0.005707 | 0.008021 |

## Confusion Matrices

| Variant | TN | FP | FN | TP |
| --- | ---: | ---: | ---: | ---: |
| Old 3-class projected, raw | 20802 | 258 | 79 | 1373 |
| Binary, raw | 20758 | 302 | 27 | 1425 |
| Old 3-class projected, post | 20725 | 335 | 20 | 1432 |
| Binary, post | 20714 | 346 | 8 | 1444 |

## Event Metrics

| Metric | Old raw | Binary raw | Old post | Binary post |
| --- | ---: | ---: | ---: | ---: |
| Critical events | 27 | 27 | 27 | 27 |
| Critical event detection | 0.888889 | 0.888889 | 0.925926 | 0.962963 |
| Median Critical delay (ns) | 0.000000 | 0.000000 | 0.000000 | 0.000000 |
| P95 Critical delay (ns) | 23.400000 | 15.400000 | 11.200000 | 4.000000 |
| False-alarm episodes | 19 | 15 | 15 | 12 |
| False alarms / trace | 0.395833 | 0.312500 | 0.312500 | 0.250000 |
| Mean recovery delay (samples) | 9.520000 | 9.680000 | 10.200000 | 10.440000 |

## Paired Disagreements

| Count | Raw | Postprocessed |
| --- | ---: | ---: |
| agreement | 22416 | 22459 |
| disagreement | 96 | 53 |
| old_safe_binary_critical | 96 | 38 |
| old_critical_binary_safe | 0 | 15 |
| both_correct | 22131 | 22131 |
| both_wrong | 285 | 328 |
| old_only_correct | 44 | 26 |
| binary_only_correct | 52 | 27 |

## Integrity

- Aligned IID endpoints: 22512
- `parameters_tuned_on_test=false`
- `pristine_blind_test=false`
- `rerun_authorized=false`
