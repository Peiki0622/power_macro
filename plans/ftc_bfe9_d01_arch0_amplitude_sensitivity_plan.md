# B-FE9-D01-A0: ARCH0 Shallow-Droop Amplitude-Sensitivity Plan

Status: `ACTIVE_PLAN`

Branch: `bfe-multitap-latched-frontend`

Plan baseline commit: `1f3fba0ac2dc079ae98b8b20122d24248e281c99`

## 0. Scientific objective and hard stop boundary

This round evaluates **exactly one additional frozen DROOP12 scenario, D01 `SHALLOW_CANONICAL`, on the already-qualified ARCH0 methodology**. The purpose is not to repeat BFE8 from scratch. The purpose is to create a controlled, paired amplitude-sensitivity comparison against D02:

```text
D01: 30 mV, 10 ps fall, 3000 ps plateau, 10 ps rise, target 21 ns RISE
D02: 60 mV, 10 ps fall, 3000 ps plateau, 10 ps rise, target 21 ns RISE
```

Everything except droop depth is intentionally shared: nominal 1.10 V, 25 C, frozen NBG_7301 background, timing, target edge, process population, per-chip startup references, ARCH0 margins, detector RTL, and metric definitions. Therefore the primary research question is:

> When the canonical droop depth is halved from 60 mV to 30 mV while all other benchmark and detector conditions remain frozen, how do ARCH0 process detection coverage and decision headroom change?

This is an **ARCH0 amplitude-sensitivity bracket**, not an ARCH1 development task and not a full DROOP12 campaign.

### Hard prohibitions

- Do not modify D01 or D02 waveform definitions, NBG seed 7301, attack phase, width, slew, target edge, or any BFE7 artifact.
- Do not regenerate D01 numerically in the BFE9 runner. Consume the exact frozen BFE7 `.inc` and verify its manifest hash.
- Do not rerun BFE8 healthy calibration, MARGIN_BG, FPR_BG, or D02 HSPICE/capture/RTL merely for folder completeness.
- Do not recalculate or retune ARCH0 margins using D01 data. The common operating margins remain `M_MARGIN_RISE=22`, `M_MARGIN_FALL=24` M-codes.
- Do not alter per-chip `M_REF_RISE/FALL`; reuse the 30 BFE8 healthy references exactly.
- Do not modify production RTL, frontend topology, tap count, RVT/LVT prefixes, Level-0 abstraction, LATQ/DFF timing, probe period, backend pipeline, or alarm rule.
- Do not implement ARCH1, temporal accumulation, background tracking, adaptive thresholding, extra feature `N`, feature fusion, LUT/ML, DVFS/OPP support, or anti-poisoning logic.
- Do not run D03-D12.
- Do not reduce the D01 depth below 30 mV if D01 passes; do not increase it if D01 fails. The benchmark is evidence, not a target to tune toward a desired verdict.
- Do not change the common healthy FPR after observing D01. The held-out BFE8 result `1/240` belongs to the frozen ARCH0 operating point.
- Do not promote a FAIL/PARTIAL result into a hardware redesign inside this plan.

## 1. BFE9-0 - Freeze authorities, hashes, and reuse matrix before simulation

Read and hash the current-branch authorities before any new simulator call.

### 1.1 Frozen D01/BFE7 authority

Required files:

- `delay_chain/ftc/analysis/b_fe_frontend/bfe7_droop12_waveforms/BFE7_DROOP12_GATE.json`
- `delay_chain/ftc/analysis/b_fe_frontend/bfe7_droop12_waveforms/DROOP12_WAVEFORM_CONTRACT.json`
- `delay_chain/ftc/analysis/b_fe_frontend/bfe7_droop12_waveforms/DROOP12_MANIFEST.json`
- `delay_chain/ftc/analysis/b_fe_frontend/bfe7_droop12_waveforms/waveforms/D01_SHALLOW_CANONICAL.csv`
- `delay_chain/ftc/analysis/b_fe_frontend/bfe7_droop12_waveforms/waveforms/D01_SHALLOW_CANONICAL.inc`

At plan creation, the frozen manifest records:

```text
D01 CSV SHA256 = 49ae91c52ed12f1603a0d25303da855f05df9ca3bf5eaed35b1d9123b9fb42ff
D01 INC SHA256 = cc264410443f03ce1ca1f1ef2b6f7870f08b2a8f1a8fb9befe44c92b9f050fdc
```

D01 contract:

```text
V_NOM       = 1.10 V
TEMP        = 25 C
background  = frozen NBG_7301
attack      = 30 mV rectangular droop
breakpoints = 19.49 ns / 0 mV
              19.50 ns / 30 mV
              22.50 ns / 30 mV
              22.51 ns / 0 mV
target      = 21 ns RISE
```

### 1.2 Frozen BFE8 ARCH0 operating-point authority

Required files:

- `delay_chain/ftc/analysis/b_fe_frontend/bfe8_d02_arch0_pilot/BFE8_HEALTHY_PER_SEED.csv`
- `delay_chain/ftc/analysis/b_fe_frontend/bfe8_d02_arch0_pilot/BFE8_D02_MARGIN_LOCK.json`
- `delay_chain/ftc/analysis/b_fe_frontend/bfe8_d02_arch0_pilot/BFE8_D02_HEALTHY_FPR_METRICS.json`
- `delay_chain/ftc/analysis/b_fe_frontend/bfe8_d02_arch0_pilot/BFE8_D02_PER_SEED.csv`
- `delay_chain/ftc/analysis/b_fe_frontend/bfe8_d02_arch0_pilot/BFE8_D02_METRICS.json`
- `delay_chain/ftc/analysis/b_fe_frontend/bfe8_d02_arch0_pilot/R0_GATE.json`
- `delay_chain/ftc/analysis/b_fe_frontend/bfe8_d02_arch0_pilot/R0_REPORT.md`

Freeze the following common ARCH0 conditions by hash, not by re-estimation:

```text
process seeds                = 41001...41030
process instances            = 30
per-chip M_REF_RISE/FALL     = exact rows from BFE8_HEALTHY_PER_SEED.csv
reference arithmetic         = sum4 >> 2
M_MARGIN_RISE                = 22
M_MARGIN_FALL                = 24
comparison                   = strict D_M > selected margin
common held-out healthy FPR  = 1/240 observed events
D02 observed coverage        = 30/30
D02 H_D min / median         = +19 / +38 M-codes
D02 latency                  = 20.534524618567 ns for detected target events
pre-attack diagnostic        = polarity-aware, as fixed by BFE8-D02-R0
```

BFE8-R0 is mandatory authority: all pre-attack event diagnostics in BFE9 must select the reference and margin from the event's own RISE/FALL polarity from the first implementation; never reintroduce the old all-RISE diagnostic bug.

### 1.3 Reuse audit

Create under:

`delay_chain/ftc/analysis/b_fe_frontend/bfe9_d01_arch0_amplitude_sensitivity/`

at least:

- `P0_EVIDENCE_MATRIX.md`
- `P0_EVIDENCE_MATRIX.json`
- `P0_REUSE_MANIFEST.json`
- `P0_SIMULATION_BUDGET.json`

The reuse matrix must explicitly classify data as:

```text
REUSE_WITHOUT_RERUN:
  30 healthy process signatures
  30 M_REF_RISE/FALL pairs
  RISE/FALL margins 22/24
  held-out healthy FPR evidence
  D02 30-seed per-seed metrics and captures/results for comparison
  TIM0 latency/pipeline contract
  BFE8-R0 polarity-aware diagnostic method

NEW_DATA_REQUIRED:
  D01 transistor-level source response for 30 paired process seeds
  D01 real capture vectors for those 30 cases

CONDITIONAL_ONLY:
  production ARCH0 RTL replay, only if D01 exposes a new decision-boundary/verdict class
```

Expected default new-work upper bound:

```text
healthy HSPICE         = 0
healthy capture        = 0
D02 HSPICE             = 0
D02 capture            = 0
D01 HSPICE             = 30 total maximum
D01 capture            = 30 total maximum
new margin development = 0
new FPR simulation     = 0
DC/STA/P&R             = 0
production RTL replay  = 0 by default; <=1 task-scoped VCS run only if justified by P4
```

These are upper bounds, not quotas. If a valid BFE9 D01 case already exists with matching D01 hash, process signature, deck contract, and capture artifact, reuse it.

Gate: `BFE9_D01_P0_AUTHORITY_AND_REUSE_FROZEN`

Stop and commit before P1.

## 2. BFE9-1 - Implement a D01 task-local runner and offline contract checks

Prefer extending/refactoring validated BFE8 helper logic into a scenario-parameterized task-local path only if doing so does not mutate historical BFE8 results. It is acceptable to reuse BFE8 parsing/capture functions, but BFE9 output must live in its own directory and historical BFE8 artifacts must remain immutable.

### 2.1 Electrical/capture contract

The active D01 source/capture flow remains:

```text
exact frozen D01 .inc
      -> vdd_monitored / PD_SENSE
      -> existing RVT/LVT transistor paths
      -> 30 XOR taps
      -> source-referenced ideal Level-0
      -> real LATQ
      -> real DFF
      -> q_ff[29:0]
      -> M_FF = sum(i*q_ff[i])
```

Keep:

```text
PD_SAFE              = stable 1.10 V
RVT prefix           = 4
LVT prefix           = 0
observable taps      = 30
Level-0 threshold    = V(xor_i,t) > 0.5 * instantaneous V(vdd_monitored,t)
LATQ/DFF schedule    = frozen BFE8/BFE3 schedule
CLK_SYS_MON          = existing 50 MHz convention
CLK_PROBE/TIM0       = existing 400 MHz / 2.5 ns convention
```

Do not replace the frozen D01 include with a generated voltage source inside the source deck. Copy/include the BFE7 artifact and verify its SHA256 before each new source run.

### 2.2 Offline zero-simulation assertions

Before D01 simulation, verify:

- D01 CSV/INC hashes equal the BFE7 manifest;
- D01 and D02 share attack onset, target edge, fall time, plateau duration, rise time, nominal VDD, noise seed, and stop-time semantics;
- their intended primary controlled difference is 30 mV versus 60 mV depth;
- BFE8 healthy CSV contains exactly 30 unique seeds and complete `M_REF_RISE/FALL`;
- margin lock is still exactly RISE=22, FALL=24 and strict `>`;
- R0 gate is PASS and corrected pre-attack diagnostics are polarity-aware;
- no BFE9 code writes any BFE7/BFE8 file;
- no margin-selection function is callable from the D01 attack stage;
- no ARCH1 logic or alternate feature is imported into metric calculation.

Gate: `BFE9_D01_P1_RUNNER_CONTRACT_READY`

Stop and commit. HSPICE/VCS/DC count remains zero in this stage.

## 3. BFE9-2 - One-seed D01 sanity before population launch

Run only process seed `41001` using the exact D01 frozen include.

Purpose: verify stimulus binding and capture plumbing, not characterize coverage yet.

Required checks:

- HSPICE completes cleanly and enters MOS_MC;
- D01 process signature exactly equals the BFE8 retained healthy signature for seed 41001;
- frozen D01 INC hash is recorded in the case metadata;
- target event is exactly the 21 ns RISE event;
- Level-0 threshold remains source-referenced to instantaneous monitored VDD;
- all target LATQ/DFF outputs are rail-resolved;
- q_ff contains exactly 30 bits;
- `M_FF` is within 0..435;
- selected reference is the existing seed-41001 `M_REF_RISE`, not a new calibration result;
- selected margin is 22, not recomputed from D01;
- every pre-target diagnostic event uses its own RISE/FALL reference and margin;
- D01 verdict may be HIT or MISS; either is acceptable.

If the fixed capture path fails, stop with a blocking evidence report. Do not retune latch timing or attack phase.

Gate: `BFE9_D01_P2_SINGLE_SEED_CAPTURE_PASS`

Stop and commit. Seed 41001 must be reused in P3.

## 4. BFE9-3 - Complete the 30-seed D01 process population

Reuse P2 seed 41001. Run only missing D01 seeds 41002...41030. Before every launch, check for a completed same-seed BFE9 case with matching hashes and resume/reparse rather than rerun.

For each seed retain:

```text
seed
mc_random_signature
D01_INC_SHA256
source/capture hashes
target event identity
q_ff_target
M_FF_target
M_REF_RISE reused from BFE8
M_REF_FALL reused from BFE8
locked margins 22/24
rail-resolution flag
full event list needed for polarity-aware pre-attack diagnostics
```

No healthy source/capture simulation is permitted in this stage.

After all 30 physical/capture cases validate, stop before computing paper-facing conclusions.

Gate: `BFE9_D01_P3_POPULATION_CAPTURE_COMPLETE`

Stop and commit.

## 5. BFE9-4 - Frozen ARCH0 metric extraction and paired D01-vs-D02 analysis

This stage should be offline only. It must not launch HSPICE merely to recalculate metrics.

### 5.1 D01 target-event verdict

D01 targets the same 21 ns RISE event as D02. For each seed `k`:

```text
D_M_D01[k] = abs(M_FF_D01_target[k] - M_REF_RISE[k])
H_D_D01[k] = D_M_D01[k] - 22
A_D01[k]   = 1 iff D_M_D01[k] > 22
```

Strict-boundary semantics remain:

```text
H_D > 0 -> HIT
H_D = 0 -> MISS
H_D < 0 -> MISS
```

An unrelated alarm on another event does not count as D01 detection.

### 5.2 Primary D01 metrics: definitions are immutable from BFE8

Report exactly the same attack-side primary metrics used for D02:

1. **Process Detection Coverage**

```text
C_det_D01 = detected seeds / 30
```

Report numerator/denominator, percentage, and 95% Wilson interval. Never convert 30/30 into a universal silicon guarantee.

2. **Detection Decision Headroom**

Across all 30 seeds, including misses:

```text
H_D_min
H_D_median
```

3. **First-Alarm Latency**

For detected target events only:

```text
L_det[k] = same-event E7 alarm time - frozen D01 attack onset
```

Use the already-validated fixed TIM0 timing derivation. Since D01 and D02 share onset and target edge, detected D01 target events are expected to inherit the same fixed latency if the pipeline is unchanged. Report median/worst; MISS seeds are `N/A`, never assigned an artificial large latency.

### 5.3 Common healthy metric is reused, not remeasured

Record in the final BFE9 context:

```text
common ARCH0 held-out healthy FPR = 1/240
```

This is referenced to the BFE8 evidence hash. Do not create a scenario-specific D01 FPR and do not re-run healthy stimuli.

### 5.4 Mandatory paired amplitude-sensitivity diagnostics

Join D01 and frozen D02 by exact process seed/signature and create:

`BFE9_D01_D02_PAIRED.csv`

with at least:

```text
seed
mc_random_signature
M_REF_RISE
D_M_D01
H_D_D01
D01_detected
D_M_D02
H_D_D02
D02_detected
HEADROOM_DROP_D02_TO_D01 = H_D_D02 - H_D_D01
```

This paired diagnostic is not a fourth headline metric. Its purpose is to isolate the response to halving attack amplitude while process/noise/timing/reference/margin remain matched.

Required consistency checks:

- all 30 D01/D02 rows pair by the same `mc_random_signature`;
- D02 values exactly reproduce frozen BFE8 metrics and are never silently recomputed with a different rule;
- selected margin is 22 for both D01/D02 target RISE events;
- polarity-aware pre-attack alarm count is computed correctly for D01;
- no D02 re-simulation occurs.

### 5.5 Predeclare result interpretation before looking for the next scenario

Classify D01 only after metrics are computed:

```text
FULL_OBSERVED_COVERAGE:
  30/30 detected.

MARGINAL_FULL_COVERAGE:
  30/30 detected but H_D_min is close to the strict boundary; report the numerical headroom rather than inventing a new threshold.

PARTIAL_COVERAGE:
  fewer than 30/30 detected; retain all miss seeds as genuine ARCH0 blindspot evidence.
```

Do not alter D01 or the margin in any class.

Gate: `BFE9_D01_P4_ARCH0_AMPLITUDE_METRICS_CHARACTERIZED`

Stop and commit.

## 6. BFE9-5 - Conditional production RTL replay only when it adds new evidence

BFE8 already replayed representative D02 vectors through unchanged production ARCH0 RTL and validated reference arithmetic, strict comparison, E7 alignment, and E8 sticky timing. Therefore **P5 defaults to zero new RTL simulation**.

Run at most one task-scoped production-RTL VCS replay only if P4 exposes a decision class that BFE8 did not already validate well, for example:

- at least one genuine D01 MISS;
- an exact `H_D=0` strict-equality boundary;
- a weakest HIT with `H_D=+1` or similarly boundary-adjacent value;
- a new sign/direction behavior requiring proof that absolute subtraction is replayed correctly.

If none of these occurs, publish a zero-run P5 reuse note pointing to BFE8 P7 and skip VCS.

If replay is justified, select the minimum sufficient set, preferably in one VCS task:

```text
weakest HIT
strongest/closest MISS if present
equality case if present
```

No new HSPICE is allowed in P5. If RTL replay disagrees with the frozen golden analysis, fix alignment/testbench analysis first; do not modify production RTL or margins.

Gate is one of:

- `BFE9_D01_P5_RTL_REPLAY_REUSED_BFE8` for zero-run reuse, or
- `BFE9_D01_P5_BOUNDARY_RTL_REPLAY_PASS` when new replay was scientifically justified.

Stop and commit.

## 7. BFE9-6 - SCI-style paired visualization and final package

Generate figures only from frozen BFE8 D02 tables plus completed BFE9 D01 per-seed data. Do not hand-enter or independently regenerate metric values.

### 7.1 Primary figure

Create a restrained SCI-paper-style paired headroom figure:

`BFE9_D01_D02_PAIRED_HEADROOM.pdf`
`BFE9_D01_D02_PAIRED_HEADROOM.png`

Recommended representation:

- x-axis: process seed or sorted paired-process index;
- y-axis: `Detection Decision Headroom H_D (M-codes)`;
- show D01 30 mV and D02 60 mV for the same process instance;
- include a clear horizontal `H_D=0` decision boundary;
- visually preserve pairing, e.g. paired markers/connecting segments or another uncluttered paired design;
- white background, compact serif/Times-like text if locally available, grayscale-readable markers/line styles, no rainbow palette, no decorative effects;
- annotate only `D01 coverage`, `D02 coverage`, and key min/median headroom if useful;
- do not use a dashboard or introduce extra performance metrics.

If process seed labels make the plot unreadable, use sorted paired index and publish the seed mapping in the companion CSV.

### 7.2 Final artifacts

Publish under:

`delay_chain/ftc/analysis/b_fe_frontend/bfe9_d01_arch0_amplitude_sensitivity/`

at minimum:

```text
P0_EVIDENCE_MATRIX.md/json
P0_REUSE_MANIFEST.json
P0_SIMULATION_BUDGET.json
BFE9_D01_PER_SEED.csv
BFE9_D01_METRICS.json
BFE9_D01_D02_PAIRED.csv
BFE9_D01_D02_COMPARISON.json
BFE9_D01_RUN_LEDGER.json
BFE9_D01_D02_PAIRED_HEADROOM.pdf/png
BFE9_D01_REPORT.md
BFE9_D01_GATE.json
```

The final compact result table should be:

| Metric | D01 30 mV | D02 60 mV frozen baseline |
|---|---:|---:|
| Detection coverage | `x/30` | `30/30` |
| Headroom min / median | `... / ...` | `19 / 38` M-codes |
| First-alarm latency median / worst | `... / ...` | `20.5345 / 20.5345 ns` |

Below the table state once:

```text
Common ARCH0 margins: RISE=22, FALL=24 M-codes
Common held-out healthy FPR: 1/240 observed events
```

Do not duplicate FPR as though D01 and D02 had separately tuned operating points.

### 7.3 Final interpretation rules

The report may conclude only what the paired experiment supports:

- whether halving droop amplitude reduces observed process coverage;
- how the D01 headroom distribution shifts relative to D02;
- whether D01 creates an observed ARCH0 decision-boundary/blindspot population;
- whether detected D01 events retain the unchanged fixed pipeline latency.

Do not claim a continuous minimum detectable voltage from only two amplitudes. Do not claim D01 misses are exploitable timing faults without a victim fault oracle. Call them sensor/detector observability misses where appropriate.

Final gate:

`BFE9_D01_ARCH0_AMPLITUDE_SENSITIVITY_FROZEN`

This gate means the 30 mV versus 60 mV canonical amplitude comparison is frozen. It does not require D01 to pass 30/30.

## 8. Simulation accounting and resume discipline

Maintain an append-only task run ledger. Every simulator call must carry a reason that the required evidence cannot be obtained from retained data.

Before launching any case, check in order:

1. Is the datum already present in BFE7/BFE8 retained evidence?
2. Can it be obtained by re-parsing an existing BFE9 raw case?
3. Is there a completed same-seed D01 case with matching waveform, deck, process signature, and capture hashes?
4. Only if all answers are no may a new simulator call occur.

Nominal maximum new work for this plan:

```text
D01 HSPICE/source cases = 30 total, including P2 seed41001
D01 real capture cases  = 30 total, including P2 seed41001
healthy physical runs   = 0
D02 physical runs       = 0
FPR physical runs       = 0
DC/STA/P&R               = 0
P5 production RTL VCS   = 0 default, <=1 conditional task-scoped replay
```

P2's seed 41001 is part of the 30 and must not be rerun in P3. A failed/corrupt case may be rerun only after documenting why its retained artifact is invalid.

## 9. Macro-direction guardrails for Codex

The research sequence remains:

```text
BFE7 frozen DROOP12
   -> BFE8 D02 quantitative methodology qualification
   -> BFE8-D02-R0 diagnostic correction
   -> BFE9 D01-vs-D02 amplitude-sensitivity bracket
   -> choose the next frozen scenario based on measured evidence
   -> finish ARCH0 baseline characterization
   -> only then design ARCH1 against demonstrated limitations
```

BFE9 must not become an ARCH1 design exercise or a search for an attack that makes ARCH0 fail. If D01 remains 30/30 with large headroom, accept that evidence and move later to a different already-frozen disturbance dimension, most naturally D04 pulse-width sensitivity. If D01 becomes marginal/partial, preserve the exact failing seeds and mechanism for later analysis without changing the benchmark or threshold.

Execute P0 -> P6 exactly in order. Publish and commit each stage gate before proceeding. A FAIL/PARTIAL result is scientifically valid; never tune hardware, margin, waveform, or timing inside this plan merely to obtain PASS.
