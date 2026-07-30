# State-code IID v2 final report

Policy: `state_code_iid_v2_20260730_r1`

This release reuses exactly the existing 240 traces and replaces the former
train/validation/IID/OOD assignment with 144 train, 48 validation, and 48 IID
holdout traces. Base-waveform and hard-pair relationships are closed
transitively before assignment. The holdout was evaluated exactly once after
model and postprocessing freeze. Prior trace-level results had been viewed, so
`pristine_blind_test=false`; no parameter was tuned on this holdout.

## Dataset evidence

| Item | Value |
|---|---:|
| Connected components | 212 |
| Train traces | 144 |
| Validation traces | 48 |
| IID holdout traces | 48 |
| State-proportion maximum deviation | 0.000025 |
| Supported-stratum maximum deviation | 0.016667 |
| L32 train windows | 33,840 |
| L32 validation windows | 22,512 |
| L32 IID windows | 22,512 |

## Validation model selection

| History | Mean Macro-F1 | Std | Mean balanced accuracy | Mean Warning recall | Mean Critical recall |
|---|---:|---:|---:|---:|---:|
| L8 | 0.814401 | 0.006122 | 0.814650 | 0.459735 | 0.986006 |
| L16 | 0.840743 | 0.006418 | 0.836870 | 0.546381 | 0.965588 |
| L32 | 0.869576 | 0.002965 | 0.866274 | 0.635406 | 0.965359 |

The frozen model is the L32 direct cross-entropy arm with sqrt-inverse class
weights, seed `20260727`. The seed is closest to the three-seed median Macro-F1,
not the best-seed result. Checkpoint SHA256:
`fcd4a87c2ae01f9ba98b6688ce53735344b86b6c5b109b84aee28503d453f855`.

## Validation OOF postprocessing

The five component-grouped folds contain 10/10/10/9/9 traces. The frozen
state machine uses raw probabilities, Risk on/off 0.25/0.05, Critical on/off
0.30/0.20, `K_on=1`, and `K_off=2`.

| Metric | OOF value | Gate | Pass |
|---|---:|---:|---|
| Accuracy | 0.976013 | - | - |
| Balanced accuracy | 0.854256 | - | - |
| Macro-F1 | 0.848466 | - | - |
| Safe-window FAR | 0.005578 | <= 0.05 | yes |
| Risk event detection | 0.977778 | >= 0.98 | no |
| Critical event detection | 0.958333 | >= 0.98 | no |
| Median Critical delay | 0 ns | <= 4 ns | yes |
| P95 Critical delay | 7.6 ns | <= 12 ns | yes |
| False alarms per trace | 0.0625 | <= 0.10 | yes |
| Mean recovery delay | 3.232558 samples | <= 3 | no |

## Final IID window metrics

| Metric | Raw model | Frozen postprocessing |
|---|---:|---:|
| Accuracy | 0.983120 | 0.979256 |
| Balanced accuracy | 0.892928 | 0.879836 |
| Macro-F1 | 0.893762 | 0.873910 |
| Weighted F1 | 0.982906 | 0.978824 |
| Safe-window FAR | 0.002042 | 0.005578 |
| Critical recall | 0.945592 | 0.986226 |
| Macro PR-AUC OVR | 0.929663 | 0.929663 |
| Macro ROC-AUC OVR | 0.996399 | 0.996399 |
| Weighted ROC-AUC OVR | 0.999432 | 0.999432 |
| Log loss | 0.039948 | 0.039948 |
| Multiclass Brier score | 0.024725 | 0.024725 |

Probability metrics are identical because the state machine changes deployed
class decisions, not the model probabilities.

## Final IID per-class metrics

| Output | Class | Precision | Recall | F1 | Support | PR-AUC | ROC-AUC | OVR Brier |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Raw | Safe | 0.999900 | 0.997958 | 0.998928 | 20,078 | 0.999998 | 0.999984 | 0.001328 |
| Raw | Warning | 0.857482 | 0.735234 | 0.791667 | 982 | 0.882420 | 0.993201 | 0.012363 |
| Raw | Critical | 0.841815 | 0.945592 | 0.890691 | 1,452 | 0.906573 | 0.996012 | 0.011034 |
| Postprocessed | Safe | 1.000000 | 0.994422 | 0.997203 | 20,078 | 0.999998 | 0.999984 | 0.001328 |
| Postprocessed | Warning | 0.830552 | 0.658859 | 0.734810 | 982 | 0.882420 | 0.993201 | 0.012363 |
| Postprocessed | Critical | 0.810413 | 0.986226 | 0.889717 | 1,452 | 0.906573 | 0.996012 | 0.011034 |

## Final IID confusion matrices

Rows are truth and columns are predicted Safe/Warning/Critical.

| Output | True class | Safe | Warning | Critical |
|---|---|---:|---:|---:|
| Raw | Safe | 20,037 | 41 | 0 |
| Raw | Warning | 2 | 722 | 258 |
| Raw | Critical | 0 | 79 | 1,373 |
| Postprocessed | Safe | 19,966 | 112 | 0 |
| Postprocessed | Warning | 0 | 647 | 335 |
| Postprocessed | Critical | 0 | 20 | 1,432 |

## Final IID event metrics

| Metric | Raw model | Frozen postprocessing |
|---|---:|---:|
| Trace count | 48 | 48 |
| Risk event count | 43 | 43 |
| Risk event detection | 1.000000 | 1.000000 |
| Median Risk delay | 0 ns | 0 ns |
| P95 Risk delay | 0 ns | 0 ns |
| Critical event count | 27 | 27 |
| Critical event detection | 0.888889 | 0.925926 |
| Median Critical delay | 0 ns | 0 ns |
| P95 Critical delay | 23.4 ns | 11.2 ns |
| False-alarm episodes | 0 | 0 |
| False alarms per trace | 0 | 0 |
| Mean recovery delay | 0.975610 samples | 3.317073 samples |

## Final gates and hard pairs

| Postprocessed event gate | Pass |
|---|---|
| Risk event detection >= 0.98 | yes |
| Critical event detection >= 0.98 | no |
| Median Critical delay <= 4 ns | yes |
| P95 Critical delay <= 12 ns | yes |
| False alarms/trace <= 0.10 | yes |
| Safe-window FAR <= 0.05 | yes |
| Mean recovery delay <= 3 samples | no |
| Postprocess latency < 0.1 ms/window | yes (0.004611 ms) |

Two IID hard pairs are scorable; one is jointly correct, for pair accuracy
0.5. Overall event acceptance is `false`. Postprocessing materially increases
Critical window recall and improves Critical P95 delay, but reduces Warning
recall and Macro-F1 while increasing recovery delay. It is therefore retained
as frozen evidence, not described as deployment-ready.

Final report SHA256 inputs and machine-readable metrics are stored in
`evaluation/state_code_iid_v2_20260730_r1/frozen_iid_once/frozen_evaluation.json`.
