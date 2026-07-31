# Binary CNN Hyperparameter Search

All values are validation-only aggregates over three seeds. IID features and metrics were not loaded.

| Rank | Arm | LR | Weight decay | Median Critical PR-AUC | Median Macro-F1 | Worst Critical recall | Median balanced acc. | Median Safe FAR | PR-AUC std |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | lr4em3_none | 0.004 | 1e-05 | 0.900391 | 0.952356 | 0.964212 | 0.981712 | 0.011112 | 0.001295 |
| 2 | lr4em3_plateau10 | 0.004 | 1e-05 | 0.899753 | 0.950067 | 0.958706 | 0.979006 | 0.012394 | 0.001197 |
| 3 | lr3em3_none | 0.003 | 1e-05 | 0.898682 | 0.952386 | 0.964212 | 0.982448 | 0.011681 | 0.001766 |
| 4 | lr2em3_none | 0.002 | 1e-05 | 0.898175 | 0.950812 | 0.969718 | 0.982317 | 0.012299 | 0.002137 |
| 5 | lr3em3_plateau10 | 0.003 | 1e-05 | 0.897417 | 0.950608 | 0.969030 | 0.980074 | 0.011634 | 0.000621 |
| 6 | lr3em3_plateau6 | 0.003 | 1e-05 | 0.896739 | 0.949377 | 0.958706 | 0.973916 | 0.010969 | 0.002441 |
| 7 | lr2em3_plateau10 | 0.002 | 1e-05 | 0.895457 | 0.948758 | 0.958706 | 0.975043 | 0.011681 | 0.002098 |
| 8 | lr4em3_plateau6 | 0.004 | 1e-05 | 0.894210 | 0.947561 | 0.947006 | 0.973417 | 0.011871 | 0.001574 |
| 9 | lr2em3_plateau6 | 0.002 | 1e-05 | 0.892613 | 0.945322 | 0.955953 | 0.973180 | 0.011919 | 0.007621 |

Selected arm: `lr4em3_none`.
