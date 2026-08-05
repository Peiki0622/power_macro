# Fixed-Point `sensitivity_conv2_w8` Report

Status: **PASS**. This is a validation-selected bit-true reference candidate, not a deployment-ready model and not a new IID result.

## Selected Numeric Contract

- Candidate: `w8_a8` (signed W8, signed A8, signed INT32 logits).
- Weight scales: symmetric per-output-channel powers of two; activation scales: symmetric per-layer powers of two.
- Rounding: round-to-nearest, ties-to-even; saturation occurs after each requantization; validation saturation count is zero.
- Pooling: sum 32 relu3 integers, ties-to-even divide by 32; maximum and endpoint retain the relu3 scale.
- Decision: compare two common-scale INT32 logits; exact ties select Safe, matching two-class argmax.
- Input folding: alpha `0.200019023868605`, beta `-0.438877071469824`, first bias shape `[18, 32]` to preserve standardized zero padding.

## Validation Metrics

| Candidate | Accuracy | Balanced acc. | Macro-F1 | Critical PR-AUC | Critical recall | Safe FAR | Gates |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Float | 0.985430 | 0.970747 | 0.943185 | 0.885063 | 0.953889 | 0.012394 | reference |
| w8_a8 | 0.984986 | 0.970190 | 0.941592 | 0.885696 | 0.953200 | 0.012821 | PASS |
| w16_a8 | 0.985519 | 0.970474 | 0.943464 | 0.883948 | 0.953200 | 0.012251 | PASS |
| w8_a16 | 0.985519 | 0.970474 | 0.943464 | 0.883862 | 0.953200 | 0.012251 | PASS |
| w16_a16 | 0.985430 | 0.970747 | 0.943185 | 0.885062 | 0.953889 | 0.012394 | PASS |

## Overflow and Determinism

- Derived accumulator widths: `{'conv1': 14, 'conv2': 20, 'conv3': 19, 'classifier': 19}`.
- Observed validation accumulator ranges stayed within every per-channel analytical bound.
- Validation upper-saturation counts: `{'relu1': 0, 'relu2': 0, 'relu3': 0, 'logits': 0}`.
- Exhaustive normalization fold error over sensor codes 0..32: `6.93263754e-07` maximum absolute float error.
- Exported `.mem` files were reloaded and golden tensors/logits were bit-exact: `true`.

## Scientific Boundary and Remaining Risks

- Calibration used train only; quantization selection and acceptance used validation only. IID/OOD features and predictions were not read.
- Power-of-two scaling prioritizes a shift-only RTL path; synthesis, cycle accuracy, area, timing, and power remain tasks for the RTL phase.
- Validation evidence does not establish deployment readiness or side-channel masking effectiveness.
