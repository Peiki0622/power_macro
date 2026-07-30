# TCN Vernier Formal Dataset V1

This directory contains the reproducible direct-rail data flow for the TCN
timing-risk dataset. It drives only the chiplet-A `VDD_A/VSS_A` sense domain;
the reference chain, comparator DFFs, reset network, and wells remain on the
fixed `VDD_REF/VSS_REF` domain. It does not replace the shared-PDN platform,
an RO, or an attack-current model.

The current authoritative dataset is Formal V1. Its canonical corpus is
`data/corpus_formal_v1_20260727_r1.jsonl`. Two run roots are intentional:

- `runs/formal_v1_20260727_r1_dataset` is the immutable electrical collection
  run. Its unified `compact/` view contains 240 CSV/JSON trace pairs: 144 new
  HSPICE traces plus read-only links to 96 Pilot V2 traces.
- `runs/formal_v1_20260727_r1` is the immutable derived-data release. It owns
  the V2 timing calibration, labels, fixed split, causal windows, and final
  acceptance reports.

Do not copy the Pilot labels into the Formal release. All 240 compact traces
are relabelled from the same Formal V2 slack map and label configuration so
old and new electrical evidence share one truth definition.

## Published Data Layers

- `runs/formal_v1_20260727_r1_dataset/compact/` is the electrical-fact layer.
  Every trace contains 500 real DFF captures. Compact CSVs must never be
  rewritten to add labels.
- `runs/formal_v1_20260727_r1/labels/v2/` contains the 34-point monotonic
  VDD-to-slack map, 240 labelled trace CSVs, and a SHA256 provenance manifest.
- `runs/formal_v1_20260727_r1/splits/v1/split_v1.json` records immutable
  trace-level membership. The grouping key is `base_waveform_id`; windows are
  never randomly repartitioned.
- `runs/formal_v1_20260727_r1/windows/v1/` contains causal L=8/16/32 CSV
  indexes. Features are limited to five online Vernier signals; measured VDD,
  configured droop, waveform family, and future samples are never inputs.
- `runs/formal_v1_20260727_r1/windows/v2/` copies every v1 window field exactly
  and appends only a label-side time bucket (`none`, `1-2`, `3-4`, or `5-8`
  samples). It is used only by the conditional time-auxiliary experiment; no
  sixth feature channel is introduced.
- `runs/formal_v1_20260727_r1/reports/v1/` contains the split audit and final
  full-corpus acceptance report.

The Formal label contract is `H=8`, `S_warn=5 ps`, `K_recover=3`,
`S_recover=10 ps`, `baseline_code=15`, and `M=32`. At endpoint `e`, a window
contains captures through `e`, while its target is the slack-derived risk over
`e+1..e+8`. The final eight rows of every trace are explicitly ineligible.

The accepted release contains 118,080 eligible labels. Class counts are
Safe/Warning/Critical = 68,655/19,097/30,328. Window counts for L=8/16/32 are
87,000/85,920/83,040. The final report is
`runs/formal_v1_20260727_r1/reports/v1/dataset_validation_v1.md` and its status
must remain `PASS` before any training consumes this release.

## Published Formal TCN Training

The accepted CPU training run is
`runs/formal_v1_20260727_r1/models/tcn_v1`. It trained the three causal TCNs
concurrently from the immutable L=8/16/32 window files with
`config/training_v1.json` and `config/model_tcn_v1.json`. Training processes
loaded only the `train` and `validation` rows; IID/OOD features were not parsed,
and no IID/OOD metric was computed. CAE and CNN were not trained in this run.

| Job | Best epoch | Epochs completed | Validation macro-F1 | Training wall time | Parameters | MACs/window | Checkpoint SHA256 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `tcn_L8` | 13 | 25 | 0.220363650 | 42.911 s | 4,323 | 33,664 | `29c94e288988a5882554bb151baaff6efbace95679b7d283ab612721e2df6485` |
| `tcn_L16` | 14 | 26 | 0.250343779 | 49.041 s | 4,323 | 67,328 | `cc0c685182d97d299a4c41f3124c8774dfd61711b08946d81113f50bfd730e87` |
| `tcn_L32` | 32 | 44 | 0.415408880 | 69.754 s | 4,323 | 134,656 | `84b3bb0cc2bfa1c1976d4c8989e059bf5534df07c76bafda6c12adaccc6469a5` |

`parallel_training_manifest.json` records the exact commands, interpreter,
input hashes, PIDs, timestamps, and zero exit codes. Independent acceptance is
recorded in `training_validation.json`; its status is `PASS` with no failures
and validation prediction counts of 19,400/19,080/18,440 for L=8/16/32. The
validator also strictly reconstructs each checkpoint, probes the public
`[batch,5,L] -> [batch,3]` interface, and checks histories, early stopping,
train-only normalization, probability rows, parameter counts, MAC estimates,
and machine-readable progress logs.

## TCN V2 Target And Compensation Repair

TCN V2 separates the three compensation axes that V1 combined implicitly.
Every V2 configuration explicitly selects natural or weighted sampling,
cross-entropy or focal loss, and no or sqrt-inverse class weights. The trainer
rejects weighted sampling combined with non-unit loss weights. Checkpoints are
selected on validation only with `0.30 * Safe PR-AUC + 0.20 * Warning PR-AUC +
0.50 * Critical PR-AUC`; Macro-F1 remains a reported metric, not the V2
selection target.

The L32 development matrix under `models/tcn_v2_dev` contains three fixed seeds
for each objective. No arm passed every raw gate because Macro PR-AUC remained
below 0.60 and worst-seed Critical recall remained below 0.50.

| Arm | Sampling / loss / weights | Median checkpoint score | Median macro-F1 | Median macro PR-AUC | Worst Critical recall |
| --- | --- | ---: | ---: | ---: | ---: |
| A | natural / CE / none | 0.595335 | 0.557640 | 0.588075 | 0.324474 |
| B | natural / focal / none | 0.592092 | 0.556217 | 0.584785 | 0.329559 |
| C | natural / CE / sqrt-inverse | 0.597155 | 0.559101 | 0.590751 | 0.306217 |
| D | weighted sampler / CE / none | 0.597921 | 0.553666 | 0.590899 | 0.285648 |

D and C entered five-fold trace-level causal postprocessing. All six seed runs
reached 100% OOF Critical-event detection. C was selected because its median
lead was 16 ns versus 12 ns for D; both had 0.025 median false alarms/trace.
The validation-only evidence is in `evaluation/ablation_v2` and
`evaluation/postprocess_ablation_v2`.

Because the raw gates still failed, two planned conditional objectives were
also executed. The ordinal model predicts nested Risk (`y>=1`) and Critical
(`y==2`) heads. The time-auxiliary model adds a four-way label-only horizon
head with loss weight 0.5 and bucket weights 1.0/1.5/2.0. Neither passed the
raw gates, so neither replaced C.

| Conditional arm | Median score | Median macro-F1 | Median macro PR-AUC | Worst Critical recall | Raw gates |
| --- | ---: | ---: | ---: | ---: | --- |
| Ordinal | 0.595222 | 0.561479 | 0.589198 | 0.324012 | FAIL |
| Ordinal + time auxiliary | 0.592855 | 0.546531 | 0.584700 | 0.323550 | FAIL |

## Final TCN V2 Training

The final run `models/tcn_v2` uses arm C and the predeclared seed `20260725`
for all lengths. It was not selected by choosing the best individual seed.
`training_validation.json` is `PASS` and independently checks input hashes,
weighted-PR-AUC best epochs, checkpoints, logs, and complete validation IDs.

| Job | Best epoch | Epochs completed | Checkpoint score | Validation macro-F1 | Wall time | Checkpoint SHA256 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `tcn_L8` | 14 | 26 | 0.515361 | 0.487172 | 42.790 s | `9ad0c162807d73e11fc6e0f7f818c295d79f2b93a7a30df887bced80f56388cf` |
| `tcn_L16` | 17 | 29 | 0.551592 | 0.525257 | 48.223 s | `12cd03c93c16934f8d151ce240801297222e56cfef8a55b5635c00d8891c1e0e` |
| `tcn_L32` | 11 | 23 | 0.588019 | 0.548710 | 45.283 s | `6a25b35b531a26a014123792a15c3fcade8eaa5a0f58e871b02e20ae8c93ef31` |

The final L32 five-fold OOF detector is a trailing mean of width 9, Risk
hysteresis `on/off=0.6/0.4`, Critical hysteresis `on/off=0.6/0.5`, and
`K_on=K_off=1`. Validation reached 100% Critical-event detection, 20 ns median
lead, 0.025 false alarms/trace, and 0.0649% Safe-window false alarms. The frozen
configuration is `evaluation/postprocess_v2/postprocess_config.json`, SHA256
`f66dec3ff3d527e2533531ad040d7926047a70e9949992f23c83b4f0bdc4201d`.

IID/OOD was opened exactly once after this freeze. IID passed all gates. OOD
also reached 100% Critical-event detection, 0.05 false alarms/trace, and 5.21%
Safe-window false alarms, but median lead was `-4 ns`; the strict positive-lead
gate failed. No threshold was changed and no test rerun is permitted. The
immutable report is `evaluation/frozen_tcn_v2/frozen_evaluation.json`, SHA256
`ead9881d2f4e8576c8a63a3309d8bf7ec49f933d4d11dc019f32e55c82318444`.
TCN V2 therefore improves detection and false alarms but is not deployment-ready
for OOD early warning.

## Historical V1 Frozen Postprocessing

The L32 validation probabilities were used to select a causal detector under a
five-fold trace-level protocol. The frozen configuration is an EWMA with
`alpha=0.25`, Risk hysteresis `on/off=0.8/0.6`, Critical hysteresis
`on/off=0.4/0.3`, and `K_on=K_off=1`. Its configuration SHA256 is
`2bd07084cd2a3ebf3f2d445a98a2e0e05d383fd3fb6ecc7dd804b5e03dc73e89`.
The out-of-fold validation result reached 100% Critical-event detection, zero
false alarms, 20 ns median lead, 0% Safe-window false alarms, and macro-F1
0.712370. Full tuning evidence is under
`runs/formal_v1_20260727_r1/evaluation/postprocess_v1`.

After the configuration was frozen, IID/OOD features were opened exactly once.
No test parameter was tuned. IID passed all gates: Critical-event detection was
100%, false alarms were 0.025/trace, median lead was 18 ns, and Safe-window
false alarms were 0.154%. OOD Critical-event detection was 94.12%, false alarms
were 0.25/trace, and Safe-window false alarms were 10.26%, but median lead was
exactly 0 ns. The strict positive-lead gate therefore failed and this detector
must not be described as deployment-ready. The immutable failure evidence is
`runs/formal_v1_20260727_r1/evaluation/frozen_postprocess_v1/frozen_evaluation.json`;
its SHA256 is
`3772f5c1167f8099160c580a7fb8cff65e953d28b344977a63a7a7bd4ffcaecc`.

## Code-Only Current-State Monitoring

The state-code experiment is a separate present-state task. It does not
replace or relabel the H=8 future-risk release above. At sample `e`, truth uses
only that row's already mapped slack: Safe is `slack > 5 ps`, Warning is
`0 < slack <= 5 ps`, and Critical is `slack <= 0 ps`. All 120,000 captures are
eligible because there is no future horizon. The immutable labels are under
`runs/formal_v1_20260727_r1/labels/state_code_v1`; its provenance binds all
240 source `labels/v2` CSV digests and the Formal corpus.

Model input is only the scalar integer `sensor_code`, normalized as
`(sensor_code - 15) / 17`. The L8/L16/L32 indexes under
`runs/formal_v1_20260727_r1/windows/state_code_v1` store `[L,1]` histories and
set `target_start_index=end_index=target_end_index`. The builder fails if a
raw thermometer word differs from its corrected word or either bubble count
is nonzero. That check is required because scalar code is information-
equivalent to the raw word only for the present Formal dataset.

The authoritative L32 objective matrix is `models/state_code_v1/l32_ablation_r2`.
An earlier `l32_ablation` directory is retained as failed implementation
evidence: a loss-branch regression caused all six direct-classification jobs
to fail while six ordinal jobs passed. The branch was fixed, a regression test
was added, and all twelve r2 jobs were trained from scratch. B, natural CE with
sqrt-inverse class weights, ranked first on validation. No arm passed every
raw gate across all seeds.

| History | Mean accuracy | Mean balanced accuracy | Mean macro-F1 | Mean Risk recall | Mean Critical recall |
| --- | ---: | ---: | ---: | ---: | ---: |
| L32 | 0.983475 | 0.889219 | 0.874414 | 0.999564 | 0.917957 |
| L16 | 0.980069 | 0.858910 | 0.837877 | 0.997821 | 0.956656 |
| L8 | 0.978093 | 0.842643 | 0.815133 | 0.997168 | 0.987100 |

The validation-frozen candidate is L32 seed `20260726`, selected as the
median-representative seed rather than the best individual seed. Its manifest
is `models/state_code_v1/frozen_candidate.json`; checkpoint SHA256 is
`b5230383ebcfb5717f9d0eee424c178814c742b863ea82e8189a15cbea199dcd`.
Five-fold trace-level tuning selected raw probabilities, Risk on/off
`0.65/0.55`, Critical on/off `0.20/0.10`, and `K_on=K_off=1`. OOF validation
passed every event gate: Critical and Risk event detection were both 100%,
Critical median/P95 delays were 0/8 ns, false alarms were 0.05/trace, Safe FAR
was 0.1683%, mean recovery delay was 2.314 samples, and postprocess latency was
0.00344 ms/window. The frozen config SHA256 is
`dc4fb6084d78ea6c4e41bce82d08ab2243effc27e5c16aa40d8f1978c9875487`.

IID/OOD was evaluated exactly once after the model and state machine were
frozen. IID postprocessing reached 100% Critical-event detection and 4.8 ns
P95 Critical delay. OOD postprocessing improved macro-F1 to 0.906385 and
window Critical recall to 99.39%, but event detection was only 82.35%, median
Critical delay was 6 ns, and P95 Critical delay was 12.2 ns. These fail the
predeclared 98%, 4 ns, and 12 ns gates.
No parameter was changed and no rerun is permitted. The state monitor is not
deployment-ready; the immutable one-shot report is
`evaluation/state_code_v1/frozen_iid_ood_once/frozen_evaluation.json`, SHA256
`1d868c59f2693f106915273b44f531f6248b35a8ab5d6cedf8ef584625753e1d`.

The development-only baseline, ablation, history, and five-fold reports are
collected under `evaluation/state_code_v1`. Use the `DL` environment for model
commands. Every builder, launcher, tuner, and evaluator refuses to overwrite
its versioned output directory.

### IID-only repartition v2

`state_code_iid_v2_20260730_r1` repartitions the same 240 traces into 144
train, 48 validation, and 48 IID holdout traces; no simulation or dataset
expansion was performed. Base-waveform and hard-pair links use one transitive
component boundary. L32 direct CE with sqrt-inverse weights ranked first and
seed `20260727` was frozen by the median-representative rule. The IID holdout
was evaluated once with `parameters_tuned_on_test=false` and
`pristine_blind_test=false`.

Raw IID accuracy/Macro-F1 are 0.983120/0.893762. Frozen postprocessing raises
Critical window recall from 0.945592 to 0.986226, but lowers Warning recall
from 0.735234 to 0.658859 and Macro-F1 to 0.873910. Critical event detection
is 0.925926 and mean recovery delay is 3.317 samples, so the final event gates
do not pass and the model is not deployment-ready. The complete metric tables
and immutable artifact references are in
`runs/formal_v1_20260727_r1/reports/state_code_iid_v2_20260730_r1/FINAL_REPORT.md`.

### Safe/Critical binary experiment

`state_code_binary_iid_v1_20260730_r1` reuses the exact same 144 train, 48
validation, and 48 IID traces without adding or moving data. The target mapping
is source Safe `0` and Warning `1` to binary Safe `0`, and source Critical `2`
to binary Critical `1`. Input remains only the normalized scalar sensor code.
L32 arm B (natural sampling, sqrt-inverse weighted cross entropy) was selected
by validation Critical PR-AUC and seed `20260725` was frozen by the declared
median-representative rule. Five-fold validation tuning froze a raw-score
detector with Critical on/off thresholds `0.20/0.15` and `K_on=K_off=1`.

This Safe/Critical L32 TCN is the authoritative final model for subsequent
development; the earlier future-risk and three-class state models remain only
as reproducibility baselines and must not be used as the default inference
path. The selected arm uses
`config/model_tcn_state_code_binary_v1.json` and
`config/training_state_code_binary_b_sqrt_ce.json`. Its frozen seed is
`20260725`, and the selected checkpoint SHA256 is
`6135a38c3e6e720ec569d4fa3ce26a2597c8a76489381fe0919e7fe5e087e069`.
Generated checkpoints remain excluded from Git by the repository artifact
policy; the digest is the stable identity used to verify the mounted release.
Choosing this model as authoritative does not override the acceptance gates or
turn the current result into a deployment-readiness claim.

The binary IID holdout was evaluated exactly once. The run records
`parameters_tuned_on_test=false`, `pristine_blind_test=false`, and
`rerun_authorized=false`; it must not be rerun or used for further tuning. Raw
IID accuracy, Macro-F1, Critical PR-AUC, and Critical recall are respectively
0.985386, 0.944323, 0.901720, and 0.981405. Frozen postprocessing changes
accuracy/Macro-F1 to 0.984275/0.941168, raises Critical recall to 0.994490,
detects 96.30% of Critical events, and reduces P95 Critical delay to 4 ns and
false alarms to 0.25/trace. Mean recovery delay remains 10.44 samples, so this
result is an improvement in Critical sensitivity rather than evidence of
deployment readiness.

For a like-for-like binary comparison, the old three-class IID predictions
were read from their existing frozen CSV and projected as non-Critical versus
Critical; the old model was not rerun. The new binary model improves
postprocessed Critical event detection from 92.59% to 96.30% and P95 delay
from 11.2 ns to 4 ns, while its Critical PR-AUC is slightly lower (0.901720
versus 0.906573) and Safe FAR is slightly higher (1.6429% versus 1.5907%). The
machine-readable report and all scalar metric tables are under
`runs/formal_v1_20260727_r1/reports/state_code_binary_iid_v1_20260730_r1/final_iid_comparison`.

## Reproduce Derived Data

Run from `power_macro/tcn_detection`. The paths below are already published
and the builders intentionally refuse to overwrite them. To reproduce the
flow, use a new versioned `labels/`, `splits/`, `windows/`, and `reports/`
target rather than deleting or mixing this accepted release.

```bash
python3 dataset/audit_splits.py \
  --corpus data/corpus_formal_v1_20260727_r1.jsonl \
  --output runs/formal_v1_20260727_r1/reports/v1/split_audit_v1.json \
  --split-output runs/formal_v1_20260727_r1/splits/v1/split_v1.json \
  --markdown-output runs/formal_v1_20260727_r1/reports/v1/split_audit_v1.md

python3 labels/label_traces.py \
  --source-dir runs/formal_v1_20260727_r1_dataset/compact \
  --output-dir runs/formal_v1_20260727_r1/labels/v2/traces \
  --slack-map runs/formal_v1_20260727_r1/labels/v2/slack_map_v2.csv \
  --config config/label_v2_formal.json \
  --corpus data/corpus_formal_v1_20260727_r1.jsonl \
  --requeue-ledger runs/pilot_v2_20260725_r2/state/requeue_trace_04ef24cc5fec97f4.json \
  --manifest runs/formal_v1_20260727_r1/labels/v2/provenance.json

python3 dataset/build_windows.py \
  --label-dir runs/formal_v1_20260727_r1/labels/v2/traces \
  --output-dir runs/formal_v1_20260727_r1/windows/v1 \
  --dataset-config config/dataset_formal_v1_20260727_r1.json \
  --max-train-windows-per-trace 240

python3 dataset/validate_dataset.py \
  --run-dir runs/formal_v1_20260727_r1_dataset \
  --label-dir runs/formal_v1_20260727_r1/labels/v2/traces \
  --windows-dir runs/formal_v1_20260727_r1/windows/v1 \
  --corpus data/corpus_formal_v1_20260727_r1.jsonl \
  --slack-map runs/formal_v1_20260727_r1/labels/v2/slack_map_v2.csv \
  --output runs/formal_v1_20260727_r1/reports/v1/dataset_validation_v1.json \
  --markdown-output runs/formal_v1_20260727_r1/reports/v1/dataset_validation_v1.md
```

The validator follows imported traces back to their Pilot source run. A valid
Formal report therefore requires 144 local and 96 imported cleanup ledgers,
verified import checksums, and zero raw HSPICE residuals in both run roots.

## Historical Pilot V2

Pilot V2 remains immutable under `runs/pilot_v2_20260725_r2`, with canonical
corpus `data/corpus_v2_20260725_r2.jsonl`. It has 96 traces and uses the older
`labels/v1` contract with `S_recover=6 ps`. Trace
`trace_04ef24cc5fec97f4` was rerun to the corrected 99.9 mV specification; its
evidence is retained at
`runs/pilot_v2_20260725_r2/state/requeue_trace_04ef24cc5fec97f4.json`.

Pilot models and evaluations under that run are historical Pilot results. No
model was trained as part of the Formal dataset publication itself; the later,
separately reviewed Formal TCN training is documented above. Use the CPU-only
`DL` conda environment for reproducing model training or artifact validation.
