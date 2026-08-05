# Iterative CNN Pruning Paths

Each listed operation removes two channels from one layer and immediately recovers the model.

| Step | Channels | Epochs | MAC/window | Critical PR-AUC | Critical Recall | Macro-F1 | Safe FAR | Continue |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | [16, 18, 18] | 16 | 100588 | 0.897570 | 0.973159 | 0.951298 | 0.011539 | yes |
| 2 | [16, 16, 18] | 20 | 89708 | 0.897372 | 0.962147 | 0.949397 | 0.011207 | no |

- Path A status: STOPPED_BY_QUALITY_GATE
- Path B status: SKIPPED_CONV1_SENSITIVITY_NOT_ALLOWED
- Path C status: SKIPPED_CONV3_SENSITIVITY_NOT_ALLOWED
- Path D status: SKIPPED_NO_SUB50_PERCENT_GATE_PASS
