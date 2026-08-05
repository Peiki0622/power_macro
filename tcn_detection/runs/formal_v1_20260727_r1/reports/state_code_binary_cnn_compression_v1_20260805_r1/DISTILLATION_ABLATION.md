# CNN Distillation Ablation

Teacher remained frozen at the authoritative SHA256; only train/validation were loaded.

| Student | T | alpha CE | Epochs | Critical PR-AUC | Critical Recall | Macro-F1 | Safe FAR | Strict gate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| path_a_step_01_16x18x18 | 4 | 0.5 | 25 | 0.894679 | 0.953200 | 0.945664 | 0.011586 | fail |
| path_a_step_01_16x18x18 | 2 | 0.5 | 18 | 0.896637 | 0.967653 | 0.949481 | 0.011634 | fail |
| path_a_step_01_16x18x18 | 2 | 0.7 | 20 | 0.896658 | 0.965588 | 0.949232 | 0.011539 | fail |
| path_a_step_01_16x18x18 | 4 | 0.7 | 23 | 0.895822 | 0.953889 | 0.946487 | 0.011397 | fail |
| path_a_step_02_16x16x18 | 4 | 0.5 | 26 | 0.894781 | 0.957330 | 0.946174 | 0.011776 | fail |
| path_a_step_02_16x16x18 | 2 | 0.5 | 26 | 0.896836 | 0.972471 | 0.950006 | 0.011871 | fail |
| path_a_step_02_16x16x18 | 2 | 0.7 | 16 | 0.897433 | 0.969030 | 0.951441 | 0.011159 | fail |
| path_a_step_02_16x16x18 | 4 | 0.7 | 21 | 0.896203 | 0.958706 | 0.947026 | 0.011634 | fail |
