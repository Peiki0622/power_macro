# TCN Vernier Pilot Dataset V2

This directory contains the reproducible direct-rail data flow for the TCN
timing-risk dataset.  It drives only the chiplet-A `VDD_A/VSS_A` sense domain;
the reference chain, comparator DFFs, reset network, and wells remain on the
fixed `VDD_REF/VSS_REF` domain.  It does not replace the shared-PDN platform,
an RO, or an attack-current model.

The authoritative electrical pilot is
`data/corpus_v2_20260725_r2.jsonl`, with run directory
`runs/pilot_v2_20260725_r2`.  Do not use the v1 corpus or the historical
run-local corpus copy as a label source.  Trace
`trace_04ef24cc5fec97f4` was rerun to the corrected 99.9 mV specification;
its immutable correction evidence is
`runs/pilot_v2_20260725_r2/state/requeue_trace_04ef24cc5fec97f4.json`.

## Data Layers

- `compact/` is the immutable electrical-fact layer: 96 CSV/JSON trace pairs,
  each with 500 real DFF captures.  It must never be rewritten to add labels.
- `labels/v1/` is the derived slack-truth layer.  It copies every compact row,
  appends mapped slack and future labels, and records source/corpus SHA256s.
- `splits/v1/split_v1.json` records preassigned trace-level membership.  The
  grouping key is `base_waveform_id`; windows are never randomly repartitioned.
- `windows/v1/` holds causal L=8/16/32 CSV indexes.  Window features are only
  the five online Vernier signals, never measured VDD, configured PWL droop,
  or waveform family metadata.
- `reports/v1/` contains the split audit and final dataset acceptance report.

The fixed label contract is `H=8`, `S_warn=5 ps`, `K_recover=3`,
`S_recover=6 ps`, `baseline_code=15`, and `M=32`.  At endpoint `e`, a window
contains captures through `e`, while its target is the slack-derived risk over
`e+1..e+8`.  The final eight rows of every trace are explicitly ineligible.

## Rebuild Derived Data

Run these commands only after the electrical jobs have all reached `SUCCESS`.
The HSPICE worker already compacts each successful trace and deletes its raw
products; do not manually delete files under an active `work/` directory.

```bash
python3 labels/build_slack_map.py \
  --output runs/pilot_v2_20260725_r2/labels/v1/slack_map_v1.csv \
  --report runs/pilot_v2_20260725_r2/labels/v1/slack_map_v1.md

python3 labels/label_traces.py \
  --source-dir runs/pilot_v2_20260725_r2/compact \
  --output-dir runs/pilot_v2_20260725_r2/labels/v1/traces \
  --slack-map runs/pilot_v2_20260725_r2/labels/v1/slack_map_v1.csv \
  --config config/label_v1.json \
  --corpus data/corpus_v2_20260725_r2.jsonl \
  --requeue-ledger runs/pilot_v2_20260725_r2/state/requeue_trace_04ef24cc5fec97f4.json \
  --manifest runs/pilot_v2_20260725_r2/labels/v1/provenance.json

python3 dataset/audit_splits.py \
  --corpus data/corpus_v2_20260725_r2.jsonl \
  --output runs/pilot_v2_20260725_r2/reports/v1/split_audit_v1.json \
  --split-output runs/pilot_v2_20260725_r2/splits/v1/split_v1.json \
  --markdown-output runs/pilot_v2_20260725_r2/reports/v1/split_audit_v1.md

python3 dataset/build_windows.py \
  --label-dir runs/pilot_v2_20260725_r2/labels/v1/traces \
  --output-dir runs/pilot_v2_20260725_r2/windows/v1 \
  --dataset-config config/dataset_v1.json \
  --max-train-windows-per-trace 240

python3 dataset/validate_dataset.py \
  --run-dir runs/pilot_v2_20260725_r2 \
  --label-dir runs/pilot_v2_20260725_r2/labels/v1/traces \
  --windows-dir runs/pilot_v2_20260725_r2/windows/v1 \
  --corpus data/corpus_v2_20260725_r2.jsonl \
  --slack-map runs/pilot_v2_20260725_r2/labels/v1/slack_map_v1.csv \
  --output runs/pilot_v2_20260725_r2/reports/v1/dataset_validation_v1.json \
  --markdown-output runs/pilot_v2_20260725_r2/reports/v1/dataset_validation_v1.md
```

Derived target directories are intentionally immutable: remove no published
artifact to rerun a build.  Publish a new versioned `labels/`, `splits/`,
`windows/`, and `reports/` directory instead.

## Detection Models And Evaluation

The CPU-only model environment is the `DL` conda environment.  Its locked
training dependencies are in `config/requirements_training_v1.txt`; use the
CPU PyTorch index in that file rather than installing a CUDA build.  All model
inputs are the existing five-channel causal window features.  Neither VDD,
configured droop, waveform family, nor split metadata is a model input.

```bash
conda run -n DL python -m pip install -r config/requirements_training_v1.txt

conda run -n DL python -m power_macro.tcn_detection.train.launch_parallel_training \
  --windows-dir runs/pilot_v2_20260725_r2/windows/v1 \
  --label-dir runs/pilot_v2_20260725_r2/labels/v1/traces \
  --training-config config/training_v1.json \
  --model-config config/model_tcn_v1.json \
  --output-dir runs/pilot_v2_20260725_r2/models/v1

conda run -n DL python -m power_macro.tcn_detection.evaluate.evaluate_all \
  --windows-dir runs/pilot_v2_20260725_r2/windows/v1 \
  --label-dir runs/pilot_v2_20260725_r2/labels/v1/traces \
  --corpus data/corpus_v2_20260725_r2.jsonl \
  --training-config config/training_v1.json \
  --models-dir runs/pilot_v2_20260725_r2/models/v1 \
  --output-dir runs/pilot_v2_20260725_r2/evaluation/v1

conda run -n DL python -m power_macro.tcn_detection.evaluate.make_figures \
  --evaluation-dir runs/pilot_v2_20260725_r2/evaluation/v1 \
  --label-dir runs/pilot_v2_20260725_r2/labels/v1/traces \
  --corpus data/corpus_v2_20260725_r2.jsonl \
  --split-audit runs/pilot_v2_20260725_r2/reports/v1/split_audit_v1.json \
  --output-dir runs/pilot_v2_20260725_r2/evaluation/v1/figures
```

The primary comparison is L=16: three sensor threshold rules, normal-only
CAE, ordinary 1D-CNN, and causal TCN.  TCN L=8/L=32 are history-length
ablations.  Threshold calibration and confirmation-window selection use only
validation data; IID/OOD results are frozen.  Current Pilot background modes
all appear in training, so the report evaluates held-out background
realizations and mode-specific performance but makes no unseen-category claim.
