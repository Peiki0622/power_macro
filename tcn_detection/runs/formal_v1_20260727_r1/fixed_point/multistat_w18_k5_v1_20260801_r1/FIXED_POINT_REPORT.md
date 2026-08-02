# Fixed-Point `multistat_w18_k5` Report

Status: **PASS**. This is a validation-selected bit-true reference candidate, not a deployment-ready model and not a new IID result.

## Selected Numeric Contract

- Candidate: `w8_a8` (signed W8, signed A8, signed INT32 logits).
- Weight scales: symmetric per-output-channel powers of two; activation scales: symmetric per-layer powers of two.
- Rounding: round-to-nearest, ties-to-even; saturation occurs after each requantization; validation saturation count is zero.
- Pooling: sum 32 relu3 integers, ties-to-even divide by 32; maximum and endpoint retain the relu3 scale.
- Decision: compare two common-scale INT32 logits; exact ties select Safe, matching two-class argmax.
- Input folding: alpha `0.200019023868605`, beta `-0.438877071469824`, first bias shape `[18,32]` to preserve standardized zero padding.

## Validation Metrics

| Candidate | Accuracy | Balanced acc. | Macro-F1 | Critical PR-AUC | Critical recall | Safe FAR | Gates |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Float | 0.987251 | 0.986778 | 0.951061 | 0.900391 | 0.986235 | 0.012679 | reference |
| w8_a8 | 0.987251 | 0.986458 | 0.951032 | 0.899175 | 0.985547 | 0.012631 | PASS |
| w16_a8 | 0.987296 | 0.986802 | 0.951217 | 0.892053 | 0.986235 | 0.012631 | PASS |
| w8_a16 | 0.987207 | 0.987075 | 0.950933 | 0.900463 | 0.986924 | 0.012774 | PASS |
| w16_a16 | 0.987251 | 0.986778 | 0.951061 | 0.900392 | 0.986235 | 0.012679 | PASS |

## Overflow and Determinism

- Derived accumulator widths: `{'conv1': 14, 'conv2': 20, 'conv3': 20, 'classifier': 20}`.
- Observed validation accumulator ranges stayed within every per-channel analytical bound.
- Validation upper-saturation counts: `{'relu1': 0, 'relu2': 0, 'relu3': 0, 'logits': 0}`.
- Exhaustive normalization fold error over sensor codes 0..32: `7.46687174e-07` maximum absolute float error.
- Exported `.mem` files were reloaded and golden tensors/logits were bit-exact: `true`.

## Scientific Boundary and Remaining Risks

- Calibration used train only; quantization selection and acceptance used validation only. IID/OOD features and predictions were not read.
- Power-of-two scaling prioritizes a shift-only RTL path; synthesis, cycle accuracy, area, timing, and power remain tasks for the RTL phase.
- Validation evidence does not establish deployment readiness or side-channel masking effectiveness.
