# `[18,8,18]` Fixed-Point Quantization Handoff

## Status

`CURRENT_IMPLEMENTATION_W18_8_18_W8A8_READY`

This report records the quantization of the user-selected floating-point
`[18,8,18]`, k=5 candidate. It does not replace the historical
`CNN_COMPRESSION_V1_NO_FEASIBLE_CANDIDATE` strict compression report: the
floating-point candidate was selected by the user despite not meeting the
original three-seed Teacher gate.

## Provenance and Boundary

| Item | Value |
| --- | --- |
| Architecture | `sensitivity_conv2_w8`, channels `[18,8,18]`, kernels `[5,5,5]` |
| Float checkpoint SHA256 | `2ee30cdac4ee114c1b2a50d34289ecc84a2c885409b9a386032f56a03cca8c4d` |
| Fixed-point contract | `fixed_point_cnn_multistat_w18_8_18_k5_v1.json` |
| Plan SHA256 | `5727557709d413ff458fa4b46916651e5d22b85f5b5ed81473ab1ac88cabc10b` |
| Git HEAD at run start | `7a84f153643e6b5408edeb7c9472876ca51f0958` |
| Window manifest SHA256 | `ccb8787a0766e46e79a56b6b78846aa0e0a4842d420c8a7bbd3000977b50d065` |
| Calibration split | `train` only |
| Selection/evaluation split | `validation` only, 22,512 windows |
| IID/OOD | features not loaded; metrics not computed |

No QAT, label change, post-processing adjustment, RTL, ROM, cycle-model, or
task-three power-codebook change was made.

## Candidate Search

All four required candidates were evaluated with train-only activation-range
calibration and full validation inference. Gates below are relative to the
frozen `[18,8,18]` floating-point candidate.

| Candidate | Accuracy | Balanced Accuracy | Macro-F1 | Critical PR-AUC | Critical Recall | Safe FAR | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Float reference | 0.985430 | 0.970747 | 0.943185 | 0.885063 | 0.953889 | 0.012394 | reference |
| W8/A8 | 0.984986 | 0.970190 | 0.941592 | 0.885696 | 0.953200 | 0.012821 | PASS |
| W16/A8 | 0.985519 | 0.970474 | 0.943464 | 0.883948 | 0.953200 | 0.012251 | PASS |
| W8/A16 | 0.985519 | 0.970474 | 0.943464 | 0.883862 | 0.953200 | 0.012251 | PASS |
| W16/A16 | 0.985430 | 0.970747 | 0.943185 | 0.885062 | 0.953889 | 0.012394 | PASS |

The fixed priority selects W8/A8, the smallest required numeric format. Its
changes from the float candidate are:

| Metric | Change |
| --- | ---: |
| Accuracy | -0.000444 |
| Balanced Accuracy | -0.000558 |
| Macro-F1 | -0.001593 |
| Critical PR-AUC | +0.000633 |
| Critical Recall | -0.000688 |
| Safe FAR | +0.000427 |

## Numeric and Export Verification

The implementation retains signed symmetric zero-point-zero quantization,
per-output-channel weight scales, per-layer activation scales, ties-to-even
rounding, saturation, 32-point average pooling, and Safe-on-tie decisions.

- Validation saturation counts were zero for all ReLU and logit outputs.
- Derived accumulator widths were `conv1=14`, `conv2=20`, `conv3=19`,
  `classifier=19` bits; observed values stayed within analytical bounds.
- Every exported `.mem` file was read back and matched its source integer
  tensor exactly.
- Eight validation-only, trace-distinct golden windows were replayed; every
  integer layer trace and logit matched the saved expected values bit-for-bit.
- The artifact directory contains `quantization_config.json`,
  `quantization_search.json`, `weights/*.mem`, golden traces, a fixed-point
  report, and a SHA256 manifest.

Artifact root:

```text
tcn_detection/runs/formal_v1_20260727_r1/models/
  state_code_binary_cnn_compression_v1_20260805_r1/
    final_w18_8_18_20260805_r1/fixed_point_quantized_20260805_r1/
```

## Stop Gate

The current result is a validation-selected W8/A8 bit-true handoff candidate,
not a deployment-ready RTL implementation. The next stage requires a separate
plan for the reduced-width RTL, new ROM and latency contract, and task-three
power codebook. The legacy W18/K5 hardware and its regression tests remain
unchanged.
