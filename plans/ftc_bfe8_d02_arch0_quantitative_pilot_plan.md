# B-FE8-A0-P0: D02 ARCH0 Quantitative Baseline Pilot Plan

Status: `ACTIVE_PLAN`

Branch: `bfe-multitap-latched-frontend`

Plan baseline commit: `9702642d34319dac67f43caa5d1134514c13eb83`

## 0. Objective and hard scope boundary

This round qualifies the **quantitative ARCH0 evaluation methodology on exactly one frozen DROOP12 scenario: D02 `MEDIUM_CANONICAL`**. It does not batch-run D01/D03-D12 and it does not implement ARCH1.

The scientific question is deliberately narrow:

> At the SMIC40LL nominal 1.10 V / 25 C operating point, after per-chip startup calibration and a healthy-only margin freeze, what are ARCH0's observed process-population detection coverage, detection decision headroom, end-to-end first-alarm latency, and independent healthy false-positive rate for the frozen D02 waveform?

This pilot is a **methodology qualification case**. Once its definitions, data flow, and anti-leakage rules are frozen, the later 12-scenario ARCH0 campaign must reuse them rather than redefining metrics after seeing results.

### Hard prohibitions

- Do not modify any BFE7 D01-D12 waveform, background seed 7301, D02 attack geometry, timing, or SHA256.
- Do not run D01 or D03-D12 in this plan.
- Do not implement ARCH1, background tracking, temporal accumulation, extra spatial features, fusion, LUT/ML, DVFS/OPP banks, or any new detector feature.
- Do not modify production ARCH0 RTL, the 30-tap sensor topology, `M_FF`, startup calibration protocol, TIM0 pipeline, or Level-0 abstraction.
- Do not retune latch timing, DFF timing, probe cadence, tap count, RVT/LVT prefixes, or capture aperture in response to a poor D02 result. A failure at the frozen 1.10 V operational condition is evidence, not permission to redesign the frontend.
- Do not reuse BFE6's 0.95 V candidate margins as 1.10 V thresholds.
- Do not use D02 attack data to choose or revise margins. Margin selection must finish and be cryptographically frozen before D02 electrical results are produced.
- Do not rerun historical BFE3/BFE4/BFE5/BFE6 simulations merely to reconstruct already retained process signatures, timing constants, topology, calibration arithmetic, or backend timing.
- Do not rerun a completed BFE8 case whose raw artifacts, process signature, waveform hash, and extraction checks already validate. Resume/reparse instead.
- Do not claim silicon FPR, universal PVT robustness, post-layout signoff, physical Level-0 correctness, or victim timing-fault coverage.

## 1. Frozen authorities

Before any new simulation, read and hash the following current-branch authorities.

### 1.1 BFE7 stimulus authority

- `delay_chain/ftc/analysis/b_fe_frontend/bfe7_droop12_waveforms/BFE7_DROOP12_GATE.json`
  - must contain `BFE7_DROOP12_WAVEFORM_CONTRACT_FROZEN`, `PASS`, `scenario_count=12`, `frozen=true`.
- `delay_chain/ftc/analysis/b_fe_frontend/bfe7_droop12_waveforms/DROOP12_WAVEFORM_CONTRACT.json`
- `delay_chain/ftc/analysis/b_fe_frontend/bfe7_droop12_waveforms/DROOP12_MANIFEST.json`
- `delay_chain/ftc/analysis/b_fe_frontend/bfe7_droop12_waveforms/waveforms/D02_MEDIUM_CANONICAL.inc`
- `delay_chain/ftc/analysis/b_fe_frontend/bfe7_droop12_waveforms/waveforms/D02_MEDIUM_CANONICAL.csv`

At plan creation the frozen manifest records:

```text
D02 CSV SHA256 = db8318eaa8cef551398ff2c347cb74594c3ac56a1712e439702f5b0fa08bbff1
D02 INC SHA256 = f84a883076ea6831dc88272443f6b90df9e58c70de949f51ba26dc19be5e32fa
```

The D02 contract is:

```text
V_NOM       = 1.10 V
TEMP        = 25 C
background  = frozen NBG seed 7301
attack      = 60 mV medium rectangular droop
fall        = 10 ps
plateau     = 3000 ps
rise        = 10 ps
attack PWL  = 19.49 ns / 0 mV -> 19.50 ns / 60 mV
              -> 22.50 ns / 60 mV -> 22.51 ns / 0 mV
reference   = T_E = 21 ns RISE
stop        = 65 ns
```

The BFE8 runner shall consume the exact frozen `.inc`; it shall not regenerate D02 from numeric literals.

### 1.2 ARCH0 / frontend authority

Read and hash:

- `delay_chain/ftc/analysis/b_fe_frontend/bfe0_architecture_contract.json`
  - 30 taps, RVT prefix 4, LVT prefix 0, source-referenced ideal Level-0 threshold `V(xor_i,t) > 0.5 * V(VDD_MONITORED,t)`.
- `delay_chain/ftc/analysis/b_fe_frontend/bfe3_clk2_ftc_latch_dff_capture/BFE3_CLK2_REPORT.md`
  - frozen real LATQ/DFF capture timing convention; do not re-optimize it.
- `delay_chain/ftc/rtl/bfe_backend_ctrl.sv`
  - startup reference arithmetic is RTL-exact integer truncation: `(sum + m_ff_i) >> 2` on the fourth sample;
  - alarm rule is strict `delta_q > alarm_margin_q`.
- current BFE5 TIM0 evidence/reports and RTL only to recover the already-validated event-alignment and E0-to-E7/E8 pipeline timing. No resynthesis is required.
- `delay_chain/ftc/analysis/b_fe_frontend/bfe4_caln0_self_calibration/run_bfe4_caln0_self_calibration.py`
- `delay_chain/ftc/analysis/b_fe_frontend/bfe6_marg0_detection_margin/run_bfe6_marg0_m2.py`
  - reuse only validated helper ideas: MOS_MC process pairing, seed/signature checks, source measurement parsing, Level-0 extraction, real LATQ/DFF replay, resume-from-completed-case behavior.
  - do **not** inherit historical `VDD=0.95`, `DROOP_V`, fixed safe-rail voltage, or old margin arithmetic by accident.

### 1.3 Process population authority

Use the existing paired Monte Carlo population only:

```text
seed = 41001 ... 41030
N = 30
```

Recover each seed's retained `mc_random_signature` from BFE4/BFE6 evidence. Do not rerun old HSPICE to regenerate these signatures. Every new healthy/D02 source case must reproduce the expected signature for its seed or the case is invalid.

Gate: `BFE8_D02_P0_AUTHORITY_AND_REUSE_AUDIT_READY`

Required artifacts:

- `P0_EVIDENCE_MATRIX.md`
- `P0_EVIDENCE_MATRIX.json`
- `P0_EXPECTED_PROCESS_SIGNATURES.csv`
- `P0_SIMULATION_BUDGET.json`

`P0_SIMULATION_BUDGET.json` must explicitly identify which data are unavailable and therefore justify every new simulator call. Expected upper bound if no valid BFE8 artifacts already exist is **30 healthy source/capture cases + 30 D02 source/capture cases**, not a historical-flow rerun.

Stop and commit before P1.

## 2. P1 - Build independent healthy-control stimuli and the task-local runner (zero simulation)

### 2.1 Healthy data partitions

D02's background seed 7301 is attack-test data and remains frozen. Construct three **healthy-only** deterministic background realizations using the exact BFE7 normal-background algorithm and bounds, but different explicit seeds:

```text
CAL_BG     = 7300   # startup calibration only
MARGIN_BG  = 7302   # healthy margin-development only
FPR_BG     = 7303   # independent healthy validation only
```

All three use:

```text
VDD(t) = 1.10 V + n_bg(t)
no attack component
same slow/fast knot spacings and +/-8 mV final bound as BFE7
```

These new healthy files are **controls**, not D13-D15 and not changes to DROOP12.

To minimize physical simulation count, concatenate the three independent healthy realizations into one deterministic `HEALTHY_COMPOSITE` rail per process run, separated by guard intervals. Each local segment must retain its own seed metadata and must contain enough frozen 50 MHz meaningful edges for:

- CAL: exactly 4 valid RISE + 4 valid FALL events used to form references;
- MARGIN: at least 4 RISE + 4 FALL healthy development events;
- FPR: at least 4 RISE + 4 FALL independent healthy validation events.

Boundary/guard events are labeled and excluded. The generator must publish an explicit event map so later analysis never infers segment membership from approximate time windows.

### 2.2 Task-local runner rules

Create a BFE8-specific runner under:

`delay_chain/ftc/analysis/b_fe_frontend/bfe8_d02_arch0_pilot/`

Prefer a small task-local runner over modifying historical BFE4/BFE6 scripts. Shared helpers may be imported for model/cell discovery, process-signature hashing, measurement parsing, and real-capture replay only when their 0.95-V constants cannot leak into the new deck.

The BFE8 electrical contract is:

```text
PD_SENSE / vdd_monitored = generated 1.10-V healthy control OR exact frozen D02 .inc
PD_SAFE                   = stable 1.10 V
VSS                       = 0 V
CLK_SYS_MON               = frozen 50 MHz / 50% periodic convention
RVT prefix / LVT prefix   = 4 / 0
observable taps           = 30
XOR                       = XOR2_X0P5M_A9TL40
Level-0                   = behavioral source-referenced threshold, 0.5 * instantaneous monitored rail
LATQ                      = LATQ_X0P5M_A9TR40
DFF                       = DFFRPQ_X0P5M_A9TR40
LATQ/DFF timing           = frozen existing capture schedule; no retuning
```

The source HSPICE deck must remain transistor-level for the existing RVT/LVT/XOR frontend and use MOS_MC index-2 process variation as in BFE4. The Level-0/real-LATQ/real-DFF path remains the same abstraction boundary already accepted in the project.

For D02 specifically, include the exact BFE7 `.inc` and fail if its SHA256 differs from the frozen manifest. Do not reconstruct `V_VDD_MONITORED` with a new renderer.

### 2.3 Offline tests only

Before any simulator call, unit-test:

- healthy seed reproducibility;
- segment/event map completeness;
- healthy rails always remain within BFE7's bounded 1.092...1.108 V envelope;
- D02 `.inc` and `.csv` hashes match BFE7 manifest;
- source node is exactly `vdd_monitored`/`vss_a`;
- no 0.95-V historical constant appears in the active BFE8 deck template except in comments/provenance paths;
- safe rail is 1.10 V;
- reference arithmetic golden model is `sum(samples) >> 2`, never round-half-up;
- strict alarm rule is `D_M > margin`;
- no ARCH1 logic exists in the analysis path.

Gate: `BFE8_D02_P1_RUNNER_AND_HEALTHY_CONTROLS_READY`

Stop and commit. Simulator accounting remains zero.

## 3. P2 - One-seed healthy-only electrical/capture sanity

Run **only seed 41001** on `HEALTHY_COMPOSITE`. Do not run D02 yet.

Purpose: verify that the inherited physical/capture flow is valid at nominal 1.10 V with bounded normal supply noise before spending the process-population budget or observing attack response.

Required checks:

- HSPICE listing clean, MOS_MC entered, index-2 process signature exactly matches retained seed-41001 signature;
- all required CAL/MARGIN/FPR source samples exist at the frozen latch-close boundaries;
- Level-0 uses `0.5 * V(vdd_monitored)` at each sample, not a fixed 0.55-V literal threshold;
- all real LATQ and DFF outputs used by designated events are rail-resolved under the stable 1.10-V safe rail;
- q_ff width is exactly 30 and `M_FF=sum(i*q_ff[i]), i=0..29` remains in 0..435;
- no event from a guard interval is admitted into CAL/MARGIN/FPR sets;
- RISE/FALL event labels match the frozen system-edge convention.

If the fixed capture timing fails at 1.10 V, stop with a blocking report such as `BFE8_D02_CAPTURE_ASSUMPTION_BLOCKED`. Do **not** sweep latch close, DFF offset, or clock phase in this plan.

Gate: `BFE8_D02_P2_HEALTHY_SINGLE_SEED_CAPTURE_PASS`

Stop and commit. This seed's valid case must be reused in P3.

## 4. P3 - 30-seed healthy calibration + margin freeze

### 4.1 Complete the healthy population without rerunning P2

Reuse seed 41001 from P2. Run only missing seeds 41002...41030 on the identical `HEALTHY_COMPOSITE` methodology. If any case already exists from an interrupted execution, verify artifacts and resume rather than overwrite/rerun.

For every seed retain:

```text
seed
mc_random_signature
4 x M_CAL_RISE
4 x M_CAL_FALL
M_REF_RISE
M_REF_FALL
M_MARGIN_DEV_RISE events
M_MARGIN_DEV_FALL events
FPR segment raw captures (do not analyze yet)
q_ff and rail-resolution flags
source/capture artifact hashes
```

Reference arithmetic is exactly:

```text
M_REF_RISE = sum(4 RISE calibration M values) >> 2
M_REF_FALL = sum(4 FALL calibration M values) >> 2
```

### 4.2 Freeze margins using healthy development data only

For each MARGIN_BG=7302 development event:

```text
D_M = abs(M_FF - M_REF_selected)
```

Choose the pilot margins separately by polarity using only this healthy development partition:

```text
M_MARGIN_RISE_P0 = max(all healthy-development RISE D_M across 30 seeds)
M_MARGIN_FALL_P0 = max(all healthy-development FALL D_M across 30 seeds)
```

This is consistent with the RTL's strict `D_M > margin` rule and gives zero observed false alarms on the development set by construction. It is a **benchmark-conditioned candidate margin**, not a silicon guardband.

Before D02 is ever simulated, write and commit:

`BFE8_D02_MARGIN_LOCK.json`

with at least:

```text
locked = true
attack_data_generated = false
reference_arithmetic = "sum4 >> 2"
comparison = "strict D_M > margin"
M_MARGIN_RISE_P0
M_MARGIN_FALL_P0
healthy_development_event_count_RISE/FALL
input hashes
```

After this file is committed, the margins are immutable for the rest of the plan even if D02 performs poorly.

Gate: `BFE8_D02_P3_HEALTHY_MARGIN_FROZEN`

Stop and commit. No D02 HSPICE is allowed before this gate.

## 5. P4 - Independent healthy FPR (zero new physical simulation)

Only after P3 margin lock, parse the already-captured FPR_BG=7303 segment from the 30 healthy composite cases. Do not reuse MARGIN_BG events for this metric.

For every held-out healthy event, evaluate the same selected RISE/FALL reference and locked margin as ARCH0:

```text
healthy_alarm = (D_M > locked_margin_selected)
```

Primary healthy metric:

```text
FPR_healthy = total held-out healthy alarms / total held-out healthy events
```

Report the raw numerator/denominator and a 95% binomial/Wilson confidence interval as supporting uncertainty, not as a separate detector metric. If zero alarms are observed, phrase the result as `0 / N observed healthy validation alarms`, never as a universal FPR of zero.

Also report RISE/FALL event counts and per-polarity diagnostic FPR, but keep the combined held-out FPR as the paper-facing pilot value.

Gate: `BFE8_D02_P4_INDEPENDENT_HEALTHY_FPR_CHARACTERIZED`

Stop and commit. New HSPICE/PrimeSim runs in P4 must be zero.

## 6. P5 - D02 one-seed attack sanity after margin lock

Now, and only now, run frozen D02 for **seed 41001**.

The D02 source deck must consume the exact manifest-hashed BFE7 `.inc`. Pair the case to seed 41001's retained process signature and its P3 per-chip references. Do not alter the D02 source to make the detector pass or fail.

Check:

- measured/parsed source deck still contains the exact D02 include hash and attack-node contract;
- process signature matches healthy seed 41001;
- the targeted physical event is the 21 ns RISE event from the frozen BFE7 contract;
- designated LATQ/DFF outputs are rail-resolved;
- no pre-attack or unrelated post-attack event is accidentally substituted for the target event;
- target `q_ff`, `M_FF`, `M_REF_RISE`, `D_M`, locked RISE margin, and decision headroom can be derived unambiguously.

Do not modify margins based on this result.

Gate: `BFE8_D02_P5_D02_SINGLE_SEED_CAPTURE_PASS`

Stop and commit. Reuse seed 41001 in P6.

## 7. P6 - 30-seed D02 quantitative ARCH0 population

Reuse P5 seed 41001 and run only missing seeds 41002...41030. Preserve the healthy/D02 process identity by exact `mc_random_signature` matching for every pair.

### 7.1 Event-aligned detector verdict

D02 is defined to challenge the 21 ns RISE event. For each seed `k`:

```text
D_M[k] = abs(M_D02_target[k] - M_REF_RISE[k])
H_D[k] = D_M[k] - M_MARGIN_RISE_P0
A[k]   = 1 iff D_M[k] > M_MARGIN_RISE_P0
```

Because the RTL comparison is strict:

```text
H_D > 0  -> detected
H_D = 0  -> not detected
H_D < 0  -> not detected
```

An alarm caused by a pre-attack or unrelated event must never count as D02 detection.

### 7.2 Primary attack-side metrics

Report exactly these three primary metrics for D02:

#### (1) Process Detection Coverage

```text
C_det = sum(A[k]) / 30
```

Report `x/30`, percentage, and 95% Wilson/binomial confidence interval. Use wording such as `100% observed coverage (30/30)` if applicable; do not claim universal 100% detection.

#### (2) Detection Decision Headroom

```text
H_D[k] = D_M[k] - locked RISE margin
```

Report across **all 30 seeds**, not detected seeds only:

```text
H_D_min
H_D_median
```

Keep full per-seed distribution in CSV. Do not replace headroom with mean absolute M or another metric after seeing the result.

#### (3) End-to-End First-Alarm Latency

Attack onset comes from the frozen D02 contract/CSV, not a hand-entered value. For every detected seed:

```text
L_det[k] = time_of_same_event_E7_droop_alarm - D02_attack_onset
```

The bulk value may be derived from the frozen physical target-event timestamp plus the already-validated TIM0 pipeline contract, but it must later agree with P7 real RTL replay. Report:

```text
L_det_median
L_det_worst
```

MISS seeds have latency `N/A`; do not encode misses as arbitrary large latency values.

### 7.3 Diagnostics retained but not promoted to extra primary metrics

Save per seed:

- q_ff target code;
- M_FF target;
- M_REF_RISE;
- D_M;
- locked margin;
- H_D;
- target verdict;
- pre-attack event verdicts;
- rail-resolution status;
- process signature;
- exact source/capture hashes.

Do not add F1, ROC-AUC, accuracy, mean absolute M, or attack-energy scores to the pilot headline metrics.

Gate: `BFE8_D02_P6_ARCH0_METRICS_CHARACTERIZED`

Stop and commit.

## 8. P7 - Representative real ARCH0 RTL replay, no new HSPICE

The population metrics are computed from real captured q_ff vectors with a golden model. P7 validates that those vectors produce the same event-aligned decision and latency in the implemented ARCH0 backend.

Select representative actual D02 seeds **after P6 without changing any metric**:

- weakest headroom seed (`min H_D`);
- median/near-median headroom seed;
- strongest headroom seed;
- if any MISS exists, include the worst MISS and weakest HIT instead of redundant detected representatives.

Replay the selected real q_ff events through the current `bfe_backend_top`/existing ARCH0 RTL using their actual per-chip four-RISE/four-FALL calibration vectors and the locked P3 margins.

One task-scoped VCS build/run should exercise all selected representatives where practical. No HSPICE, no resynthesis, and no RTL modification.

Verify:

- four RISE + four FALL calibration events are consumed once per epoch;
- RTL references equal the P3 `sum4 >> 2` golden values;
- target D02 event uses RISE reference/margin;
- strict equality remains quiet;
- target alarm verdict equals P6 golden verdict;
- E7 alarm is aligned to the same logical event;
- E8 sticky behavior remains correct;
- replayed `t_alarm - t_attack_onset` agrees with the P6 latency derivation.

If replay disagrees, fix analysis/testbench alignment; do not change production RTL or margins to force agreement.

Gate: `BFE8_D02_P7_ARCH0_RTL_REPLAY_PASS`

Stop and commit.

## 9. P8 - Final pilot package and paper-facing result

Publish under:

`delay_chain/ftc/analysis/b_fe_frontend/bfe8_d02_arch0_pilot/`

at minimum:

```text
P0_EVIDENCE_MATRIX.md/json
P0_EXPECTED_PROCESS_SIGNATURES.csv
P0_SIMULATION_BUDGET.json
healthy_controls/...                  # seeded control contracts/files
BFE8_D02_MARGIN_LOCK.json
BFE8_D02_PER_SEED.csv
BFE8_D02_HEALTHY_FPR.csv
BFE8_D02_METRICS.json
BFE8_D02_RUN_LEDGER.json
BFE8_D02_REPORT.md
BFE8_D02_GATE.json
```

Also create one compact SCI-style pilot figure from the final per-seed table, not from hand-entered values. Preferred content is a process-seed distribution of `H_D` with the zero-headroom decision boundary clearly shown; a small annotation may state observed coverage and the frozen margin. Do not create a large multi-metric dashboard.

The paper-facing table must remain compact:

| Metric | D02 ARCH0 pilot |
|---|---:|
| Healthy FPR | `x / N healthy events` |
| Detection coverage `C_det` | `x / 30 (%)` |
| Decision headroom `H_D` | `min / median` M-codes |
| First-alarm latency `L_det` | `median / worst` ns |

Below the table record the frozen `M_MARGIN_RISE_P0` and `M_MARGIN_FALL_P0`, and state explicitly that they were selected from healthy-only development data before D02 attack simulation.

Final gate:

`BFE8_D02_ARCH0_QUANTITATIVE_PILOT_FROZEN`

This gate means the quantitative method is frozen for expansion to D01/D03-D12. It does **not** mean D02 must pass 30/30.

## 10. Simulation accounting and mandatory reuse discipline

Maintain a run ledger from P0 onward. Every external simulator invocation needs a `reason_new_data_required` field.

Expected maximum new work when starting from no BFE8 raw runs:

```text
Healthy source HSPICE cases : 30 total
  P2 seed41001              : 1
  P3 remaining              : 29
Healthy real capture cases  : 30 total

D02 source HSPICE cases     : 30 total
  P5 seed41001              : 1
  P6 remaining              : 29
D02 real capture cases      : 30 total

P4 new physical runs        : 0
P7 new HSPICE               : 0
P7 VCS backend replay       : 1 task-scoped run preferred
DC/synthesis/STA/P&R        : 0
```

These are upper bounds, not quotas. If task-owned validated artifacts already exist, reuse them and reduce counts. Never rerun merely to make a directory complete.

Before launching a case, check in this order:

1. Is the exact required datum already in retained BFE3/BFE4/BFE6/BFE7 evidence?
2. Is the datum derivable by re-parsing/recomputing an existing BFE8 raw artifact?
3. Is there a completed same-seed case with matching waveform/deck/process hashes that can be resumed?
4. Only if all answers are no may a new simulator call be made.

## 11. Macro-direction guardrails for Codex

The intended research sequence is:

```text
Frozen DROOP12 benchmark
        -> D02 quantitative ARCH0 pilot
        -> freeze methodology/metrics
        -> later expand unchanged method to remaining DROOP12 scenarios
        -> identify real ARCH0 blindspots
        -> only then design ARCH1 against measured limitations
```

If the work starts tuning D02, lowering margins to improve coverage, adding a second feature, adding temporal accumulation, implementing adaptive tracking, changing capture timing, or running all 12 scenarios before this pilot gate closes, it has departed from the authorized direction and must stop.

Execute exactly one stage at a time. Each stage must publish its gate/report/ledger changes and commit before moving to the next stage. A FAIL/INCONCLUSIVE result is acceptable evidence; do not automatically redesign hardware or stimulus to turn it into PASS.
