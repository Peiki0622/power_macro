# Stage 1-B: Full Binary Neural Network Supplement Plan

## 1. Purpose and scope

Stage 1 algorithm screening is considered closed. The frozen fast detector candidates remain:

- cusum_V07_H007
- cusum_V07_H008

This stage is a supplementary neural-network experiment only. It does not reopen Stage 1 selection and does not block Stage 2 CUSUM RTL development.

The goal is to answer:

> Can a fully binary neural detector preserve the current CNN detection capability while significantly reducing model storage and hardware complexity?

The BNN must be compared against the frozen W8/A8 CNN under the same detection task, data split, input information and causal rules.

---

# 2. Frozen constraints

## 2.1 Task

Binary current-state detection:

- Safe
- Critical

No future prediction.

## 2.2 Input contract

Allowed input:

- sensor_code
- code_valid
- causal L32 window

Forbidden:

- measured VDD
- configured droop magnitude
- future samples
- hidden labels

The input representation shall be changed only by deterministic encoding.

---

# 3. BNN architecture target

Model name:

```
bnn_therm32_w1a1_nofc_l32
```

The network is fully binary:

- binary input
- binary weights
- binary activations
- binary detection output

No:

- fully connected classifier
- INT8 classifier head
- Softmax
- floating point BatchNorm in inference

Architecture:

```
sensor_code L32
    |
thermometer-32 encoding
    |
Binary Conv1D 32->8 kernel=3
    |
Binary Conv1D 8->8 kernel=3
    |
Binary 1x1 detection head 8->1
    |
K-of-32 temporal voting
    |
alarm bit
```

---

# 4. Step B1: deterministic thermometer encoding

Implement:

```
tcn_detection/bnn/input_encoding.py
```

Mapping:

```
bit[j] = 1 if j < sensor_code else 0
```

Requirements:

- code 0 produces all zero;
- code 32 produces all one;
- sum(bits)==sensor_code;
- no future information;
- invalid sample does not update window.

Add exhaustive tests for all 33 possible codes.

---

# 5. Step B2: floating-point control model

Before binary training, build a same-topology floating-point reference:

```
fp_therm32_nofc_l32
```

Purpose:

Separate:

1. input encoding loss;
2. architecture loss;
3. binary quantization loss.

Do not compare CNN directly against BNN only.

---

# 6. Step B3: train full binary network

Implement:

```
tcn_detection/bnn/
    binary_layers.py
    nofc_model.py
    train_nofc_bnn.py
```

Training requirements:

- use real-valued shadow weights;
- forward uses sign(weight);
- backward uses STE approximation;
- deployment weights are binary.

Training flow:

1. FP pretraining.
2. W1A8 binary-weight training.
3. W1A1 full binary fine tuning.
4. Freeze deployment thresholds.

Run at least three seeds:

```
11, 22, 33
```

---

# 7. Step B4: remove classifier and fold BN

Inference must contain only:

```
XNOR
+
popcount
+
integer threshold compare
```

Fold:

```
Conv + BN + Sign
```

into integer thresholds.

Store only:

- binary weights;
- thresholds;
- output inversion flags.

---

# 8. Step B5: bit-true inference

Implement:

```
tcn_detection/bnn/bittrue_nofc.py
export_nofc_package.py
```

The bit-true engine must explicitly execute:

```
XNOR -> popcount -> compare
```

Do not call normal floating convolution during deployment evaluation.

Required equality:

```
training binary model output
==
bit-true binary inference output
```

---

# 9. Step B6: unified detector interface

Add:

```
tcn_detection/fast_detection/bnn_nofc_baseline.py
```

Required API:

```
reset(metadata)
step(sensor_code, valid)
```

Behavior:

- same warmup policy as CNN;
- invalid capture holds state;
- output only one alarm bit.

---

# 10. Evaluation

Compare:

| Model | Precision |
|---|---|
| Frozen CNN W8/A8 | INT8 |
| FP thermometer model | FP |
| Full binary BNN | W1A1 |
| CUSUM H7/H8 | integer baseline |

Metrics:

- Event Recall
- Safe FAR
- MCC
- F1
- p50/p95 TTD
- model bits
- XNOR operations
- popcount operations
- threshold storage

Use identical train/validation/test splits as CNN.

---

# 11. Candidate configurations

Only evaluate two widths.

## BNN-S

```
Conv1 32->8
Conv2 8->8
Head 8->1
```

## BNN-M

```
Conv1 32->16
Conv2 16->16
Head 16->1
```

No large architecture search.

---

# 12. Pass criteria

BNN is supplementary and does not replace CUSUM RTL.

Recommended targets:

```
Event Recall >= CNN - 3 percentage points
MCC >= CNN - 0.05
hidden convolution multipliers = 0
all inference weights = 1 bit
all inference activations = 1 bit
classifier layer = absent
```

If targets are not achieved, keep BNN as an ablation result only.

---

# 13. Repository outputs

Create:

```
plans/fast_detection_stage1b_full_binary_bnn_supplement_plan.md

tcn_detection/bnn/
tcn_detection/tests/
reports/BNN_STAGE1B_*.md
```

Stage 1-B completion means:

- reproducible binary training;
- bit-true inference;
- unified detector evaluation;
- comparison report against frozen CNN.

Stage 2 CUSUM RTL continues independently.
