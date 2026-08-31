# B-FE11-D04-A0: ARCH0 Voltage-Droop Duration-Sensitivity Execution Plan

Status: `ACTIVE_PLAN`

Branch: `bfe-multitap-latched-frontend`

Plan baseline commit: `51bb6cd9a843c93259111db5b7153f77a8fc6dc5`

## 0. Scientific objective and scope boundary

BFE11 evaluates exactly one new frozen DROOP12 scenario, D04 `SHORT_MEDIUM`, against the already-qualified ARCH0 operating point. The purpose is to characterize **voltage-droop duration / pulse-width sensitivity** while holding droop depth and target-edge centering fixed relative to D02.

Controlled comparison:

```text
D02 MEDIUM_CANONICAL : 60 mV, 19.50 ns -> 22.50 ns full-depth dwell, target 21 ns RISE
D04 SHORT_MEDIUM     : 60 mV, 20.70 ns -> 21.30 ns full-depth dwell, target 21 ns RISE
```

Both use the same 10 ps finite-slope transitions, 1.10 V nominal supply, 25 C, frozen NBG_7301 background, 21 ns RISE target, 30-process population, per-chip startup references, ARCH0 margins and backend. Thus the primary question is:

> With droop depth fixed at 60 mV and the pulse centered on the same meaningful edge, how does shortening the low-voltage exposure from 3.0 ns to 0.6 ns change ARCH0 process detection coverage and decision headroom?

This is an **ARCH0 baseline characterization stage**, not an ARCH1 implementation stage. The previously frozen signed-error separability result is carried only as a predeclared shadow diagnostic to test cross-scenario generalization; it must not modify the formal ARCH0 verdict.

### Hard prohibitions

- Do not alter or regenerate D04/D02 waveform definitions based on detector outcome.
- Do not modify D04 amplitude, width, centering, slew, NBG seed, target edge or any BFE7 artifact.
- Do not rerun BFE8 healthy calibration, healthy population, margin development, held-out FPR, or D02 physical simulations merely for completeness.
- Do not rerun BFE9 D01 or BFE10 analyses.
- Do not modify `M_MARGIN_RISE=22`, `M_MARGIN_FALL=24`, strict `D_M > margin`, per-chip `M_REF_RISE/FALL`, or startup calibration arithmetic.
- Do not modify production ARCH0 RTL, frontend topology, RVT/LVT prefixes, tap count, Level-0 abstraction, LATQ/DFF timing or TIM0 pipeline.
- Do not add a signed-error comparator to production RTL in this plan.
- Do not promote `T_POS=18/19` into a formal threshold or tune it using D04 results.
- Do not implement the fine-step ARCH1 tracker, temporal accumulator, `N=sum(q)`, spatial classifier, LUT/ML, adaptive margin, DVFS logic, or any other ARCH1 feature.
- Do not run D03 or D05-D12.
- Do not reopen latch-aperture or physical Level-0/signoff work.
- A D04 MISS/PARTIAL result is valid evidence. Never change the benchmark, timing or margins to force PASS.

## 1. BFE11-P0 - Freeze authorities, exact hashes and reuse matrix

Before any simulator call, read and hash all required upstream authorities from the current branch.

### 1.1 Frozen D04 waveform authority

Required BFE7 files:

- `delay_chain/ftc/analysis/b_fe_frontend/bfe7_droop12_waveforms/BFE7_DROOP12_GATE.json`
- `delay_chain/ftc/analysis/b_fe_frontend/bfe7_droop12_waveforms/DROOP12_WAVEFORM_CONTRACT.json`
- `delay_chain/ftc/analysis/b_fe_frontend/bfe7_droop12_waveforms/DROOP12_MANIFEST.json`
- `delay_chain/ftc/analysis/b_fe_frontend/bfe7_droop12_waveforms/waveforms/D04_SHORT_MEDIUM.csv`
- `delay_chain/ftc/analysis/b_fe_frontend/bfe7_droop12_waveforms/waveforms/D04_SHORT_MEDIUM.inc`

Frozen manifest hashes at plan creation:

```text
D04 CSV SHA256 = 4c08d1efcb8d37c03627d740abcd7840d4b939e97f3d55f03f2f43e9bf081415
D04 INC SHA256 = a2be7662b35b4a11ed640a9e66bb2acc30ec84054d5b619e4a5a6242b3e6c5ac
```

Frozen D04 contract:

```text
scenario       = D04 SHORT_MEDIUM
V_NOM          = 1.10 V
TEMP           = 25 C
background     = frozen NBG_7301
attack kind    = rect
nominal depth  = 0.06 V
breakpoints    = 20.690 ns / 0 mV
                 20.700 ns / 60 mV
                 21.300 ns / 60 mV
                 21.310 ns / 0 mV
target         = 21 ns RISE
full-depth dwell = 0.600 ns
```

The paired D02 control remains the frozen BFE8 result, not a new simulation:

```text
D02 depth      = 60 mV
D02 dwell      = 3.000 ns
D02 target     = 21 ns RISE
D02 coverage   = 30/30 observed
D02 H_D min/median = +19/+38 M-codes
```

### 1.2 Frozen ARCH0 operating-point authority

Required BFE8/R0 files:

- `delay_chain/ftc/analysis/b_fe_frontend/bfe8_d02_arch0_pilot/BFE8_HEALTHY_PER_SEED.csv`
- `delay_chain/ftc/analysis/b_fe_frontend/bfe8_d02_arch0_pilot/BFE8_D02_MARGIN_LOCK.json`
- `delay_chain/ftc/analysis/b_fe_frontend/bfe8_d02_arch0_pilot/BFE8_D02_HEALTHY_FPR_METRICS.json`
- `delay_chain/ftc/analysis/b_fe_frontend/bfe8_d02_arch0_pilot/BFE8_D02_PER_SEED.csv`
- `delay_chain/ftc/analysis/b_fe_frontend/bfe8_d02_arch0_pilot/BFE8_D02_METRICS.json`
- `delay_chain/ftc/analysis/b_fe_frontend/bfe8_d02_arch0_pilot/R0_GATE.json`

Freeze by evidence/hash:

```text
process seeds            = 41001..41030
M_REF_RISE/FALL          = exact BFE8 per-chip values
reference arithmetic     = sum4 >> 2
M_MARGIN_RISE            = 22
M_MARGIN_FALL            = 24
formal comparison        = strict D_M > selected margin
common held-out FPR      = 1/240 observed events
pre-attack diagnostics   = event-polarity-aware RISE/FALL ref + margin
TIM0/backend             = frozen ARCH0 pipeline
```

### 1.3 Frozen signed-error diagnostic authority

Read only; do not modify:

- `delay_chain/ftc/analysis/b_fe_frontend/arch1_signed_error_separability_audit/ARCH1_SIGNED_ERROR_SEPARABILITY_AUDIT_GATE.json`
- `delay_chain/ftc/analysis/b_fe_frontend/arch1_signed_error_separability_audit/ARCH1_SIGNED_ERROR_SEPARABILITY_AUDIT_REPORT.md`

Carry forward only these diagnostic facts:

```text
healthy RISE signed-e max = +18 on the retained 360 samples
D01 signed-e min          = +20
frozen diagnostic integer T_POS candidates = 18 and 19
formal ARCH0 margins were not modified
production RTL was not modified
```

These values are **shadow-analysis inputs only**. D04 must not be used to optimize a replacement `T_POS`.

### 1.4 Mandatory reuse matrix and simulation budget

Create:

`delay_chain/ftc/analysis/b_fe_frontend/bfe11_d04_arch0_duration_sensitivity/`

with at least:

- `P0_EVIDENCE_MATRIX.md`
- `P0_EVIDENCE_MATRIX.json`
- `P0_REUSE_MANIFEST.json`
- `P0_SIMULATION_BUDGET.json`

Classify evidence explicitly:

```text
REUSE_WITHOUT_RERUN:
  30 healthy process signatures
  30 M_REF_RISE/FALL pairs
  RISE/FALL margins 22/24
  common healthy FPR evidence
  D02 per-seed physical/capture/metrics baseline
  D01/BFE10 mechanism results only as historical context
  signed-error audit healthy distribution and frozen T_POS candidates
  TIM0/backend pipeline evidence

NEW_DATA_REQUIRED:
  D04 transistor-level source response for the same 30 process seeds
  D04 real LATQ/DFF capture vectors for the same 30 process seeds

CONDITIONAL_ONLY:
  production ARCH0 RTL replay if D04 exposes a genuinely new boundary/verdict/alignment class
```

Nominal maximum new physical work:

```text
healthy HSPICE/capture           = 0
D01 HSPICE/capture               = 0
D02 HSPICE/capture               = 0
D04 HSPICE source cases          <= 30 total
D04 real LATQ/DFF capture cases  <= 30 total
margin/FPR development           = 0
PrimeSim                         = 0
DC/STA/P&R                       = 0
production RTL VCS replay        = 0 default, <=1 task-scoped run only if justified
```

These are ceilings, not quotas. Reuse a valid matching D04 case if one already exists with correct D04 hash, process signature and capture evidence.

Gate: `BFE11_D04_P0_AUTHORITY_AND_REUSE_FROZEN`

Commit and stop before P1.

## 2. BFE11-P1 - Build/validate a task-local D04 runner without simulation

Reuse validated BFE8/BFE9 helper structure where appropriate, but do not mutate historical artifacts. Prefer a scenario-parameterized task-local implementation only if historical BFE8/BFE9 outputs remain immutable.

Required D04 signal path remains:

```text
exact frozen D04 .inc
      -> vdd_monitored / PD_SENSE
      -> existing RVT/LVT transistor paths
      -> 30 XOR taps
      -> source-referenced ideal Level-0
      -> real LATQ
      -> real DFF
      -> q_ff[29:0]
      -> M_FF = sum(i*q_ff[i])
```

Keep frozen frontend/capture parameters exactly as ARCH0:

```text
PD_SAFE              = stable 1.10 V
RVT prefix           = 4
LVT prefix           = 0
observable taps      = 30
Level-0 threshold    = V(xor_i,t) > 0.5 * instantaneous V(vdd_monitored,t)
LATQ/DFF schedule    = existing frozen schedule
CLK_PROBE            = 400 MHz / 2.5 ns convention
```

Before any D04 run, perform zero-simulation assertions:

- D04 CSV/INC hashes equal BFE7 manifest;
- D02 and D04 both have 60 mV nominal depth, 10 ps transitions, same NBG_7301, same 21 ns RISE target and same pulse center at 21 ns;
- D02 full-depth dwell is 3.0 ns and D04 full-depth dwell is 0.6 ns;
- BFE8 healthy authority contains exactly 30 unique process seeds and complete refs;
- formal margins remain RISE=22/FALL=24, strict `>`;
- BFE8-R0 polarity-aware pre-attack diagnostic logic is inherited correctly;
- signed diagnostic thresholds 18/19 are not wired into formal ARCH0 verdict code;
- no production RTL, BFE7, BFE8, BFE9, BFE10 or signed-audit artifact can be overwritten by the BFE11 runner;
- no ARCH1 implementation is imported into the physical/capture path.

Gate: `BFE11_D04_P1_RUNNER_CONTRACT_READY`

Commit and stop. Simulator count remains zero.

## 3. BFE11-P2 - One-seed D04 physical/capture sanity

Run only seed `41001` using the exact frozen D04 include.

Purpose: verify that the short-pulse source and existing capture path are bound correctly before launching the population. This stage is not allowed to tune timing around the 0.6 ns pulse.

Required checks:

- HSPICE completes cleanly and is in the intended Monte Carlo process mode;
- process signature exactly matches retained BFE8 healthy/D02 seed41001 signature;
- D04 INC hash is recorded in case metadata;
- target remains exactly 21 ns RISE;
- short pulse is centered around the target exactly as frozen by BFE7;
- Level-0 remains source-referenced to instantaneous monitored VDD;
- target LATQ/DFF outputs are rail-resolved;
- q_ff is exactly 30 bits and `M_FF` is 0..435;
- reference is retained seed41001 `M_REF_RISE`;
- formal margin is 22;
- pre-target events use their own polarity-matched refs/margins;
- HIT or MISS is acceptable;
- no capture-time, latch-aperture, attack-phase or waveform adjustment is allowed if the observed response is weak.

If the fixed capture path is invalid, stop with blocking evidence. Do not move the pulse or capture schedule to make it observable.

Gate: `BFE11_D04_P2_SINGLE_SEED_CAPTURE_PASS`

Commit and stop. Seed41001 must be reused in P3.

## 4. BFE11-P3 - Complete only the missing D04 30-seed population

Reuse P2 seed41001. Run only missing seeds 41002..41030. Before every launch, check whether a complete same-seed D04 case already exists with matching D04 hash, process signature, source/capture contract and retained artifact hashes; if valid, reparse/reuse instead of rerunning.

For each seed retain at least:

```text
seed
mc_random_signature
D04_INC_SHA256
source/capture hashes
target event identity
q_ff_target
M_FF_target
M_REF_RISE/FALL reused from BFE8
locked margins 22/24
rail-resolution flag
full event list for polarity-aware diagnostics
```

No healthy/D01/D02 physical simulation is permitted.

Gate: `BFE11_D04_P3_POPULATION_CAPTURE_COMPLETE`

Commit and stop before metric interpretation.

## 5. BFE11-P4 - Frozen ARCH0 D04 metrics and paired D04-vs-D02 duration analysis

This stage is offline only. Do not launch HSPICE merely to recompute metrics.

### 5.1 Formal ARCH0 D04 verdict

For each seed `k` at the 21 ns RISE target:

```text
D_M_D04[k] = abs(M_FF_D04[k] - M_REF_RISE[k])
H_D_D04[k] = D_M_D04[k] - 22
A_D04[k]   = 1 iff D_M_D04[k] > 22
```

Boundary semantics remain:

```text
H_D > 0 -> HIT
H_D = 0 -> MISS
H_D < 0 -> MISS
```

An alarm at an unrelated event must not count as D04 target detection.

### 5.2 Formal metrics: same three attack metrics, one common healthy metric

Report:

1. **Process Detection Coverage**

```text
C_det_D04 = detected seeds / 30
```

Include numerator/denominator, percentage and 95% Wilson interval.

2. **Decision Headroom** across all 30 seeds, including misses:

```text
H_D_min
H_D_median
```

3. **First-Alarm Latency**, detected target events only:

```text
L_det[k] = same-event E7 alarm time - D04 attack onset
```

With the frozen target/pipeline, the nominal derived value for a detected 21 ns target event is:

```text
(21000 ps + 1534.524618567 ps + 7*2500 ps - 20700 ps) / 1000
= 19.334524618567 ns
```

Do **not** interpret the approximately 1.2 ns smaller attack-onset-referenced latency versus D02 as a faster backend. It is caused by D04 beginning later relative to the same target edge; the TIM0 capture-to-alarm pipeline itself is unchanged.

4. **Healthy FPR** is reused globally:

```text
common ARCH0 held-out healthy FPR = 1/240 observed events
```

Do not create a D04-specific tuned FPR.

### 5.3 Mandatory paired D04-vs-D02 table

Join by exact seed and process signature and create:

`BFE11_D04_D02_PAIRED.csv`

with at least:

```text
seed
mc_random_signature
M_REF_RISE
D_M_D04
H_D_D04
D04_detected
D_M_D02
H_D_D02
D02_detected
HEADROOM_CHANGE_D04_MINUS_D02
```

D02 values must reproduce the frozen BFE8 authority exactly. Do not resimulate or silently recalculate D02 using a changed rule.

The paired analysis is intended to isolate the effect of shortening exposure at fixed 60 mV depth. It is not a new headline metric.

### 5.4 Predeclared interpretation classes

Classify after metrics are frozen:

```text
ROBUST_SHORT_PULSE:
  D04 = 30/30 with comfortably positive H_D_min.

MARGINAL_SHORT_PULSE:
  D04 = 30/30 but H_D_min is near the strict boundary.

PARTIAL_SHORT_PULSE_COVERAGE:
  D04 < 30/30; retain all MISS seeds as genuine ARCH0 short-duration blindspot evidence.
```

No class permits margin, waveform, phase or capture retuning.

Gate: `BFE11_D04_P4_ARCH0_DURATION_METRICS_CHARACTERIZED`

Commit and stop.

## 6. BFE11-P5 - Frozen signed-error shadow generalization audit, no implementation

This is a **secondary offline diagnostic**, not the formal detector.

For each D04 target sample compute:

```text
e_D04[k] = M_FF_D04[k] - M_REF_RISE[k]
```

Evaluate exactly the two already-frozen integer candidates from the prior signed-error audit:

```text
shadow18 = (e_D04 > 18)
shadow19 = (e_D04 > 19)
```

Do not sweep D04 to discover a better threshold and do not change formal ARCH0 results.

Report for each of T_POS=18 and 19:

```text
D04 shadow detection coverage
D04 signed-e min / median / max
D04 weakest detected signed headroom: e_D04 - T_POS
number/list of ARCH0 MISS seeds recovered by the shadow rule
number/list of ARCH0 HIT seeds not detected by the shadow rule, if any
```

Reuse the already-frozen healthy signed-e evidence; do not rerun healthy simulations. State clearly that the prior retained healthy RISE maximum was +18 and that this cross-scenario check does not constitute silicon/PVT signoff.

Interpretation:

```text
GENERALIZES_TO_D04:
  at least one frozen T_POS candidate retains zero observed healthy positive false alarms by authority and provides useful D04 detection without being retuned.

D01_SPECIFIC_OR_LIMITED:
  the frozen signed candidate does not materially help D04 or loses relevant D04 responses.
```

A positive result strengthens the future ARCH1 signed-comparator hypothesis, but **must not add the comparator to production RTL in BFE11**.

Gate: `BFE11_D04_P5_SIGNED_SHADOW_AUDIT_FROZEN`

Commit and stop.

## 7. BFE11-P6 - Conditional production ARCH0 RTL replay only for new evidence

Default: zero new production-RTL replay.

BFE8/BFE9 already validated production ARCH0 reference arithmetic, strict comparison, event alignment and E7 timing. Run at most one task-scoped production RTL VCS replay only if D04 exposes a genuinely new boundary/alignment class, such as:

- an exact `H_D=0` equality case not already adequately represented by prior evidence in the relevant D04 vector context;
- a weakest HIT at `H_D=+1` with a D04-specific vector worth confirming;
- a new sign/direction pattern that could reveal a testbench alignment error;
- a D04 target/event alignment ambiguity caused by retained analysis, not merely a poor detector result.

If no new class exists, publish a zero-run reuse note referencing prior BFE8/BFE9 production-RTL evidence.

If replay is justified:

- use one minimal task-scoped VCS run;
- use already-generated D04 capture vectors;
- launch no HSPICE;
- do not change production RTL or margin if analysis and RTL disagree; debug the harness/alignment first.

Gate is one of:

```text
BFE11_D04_P6_RTL_REPLAY_REUSED_PRIOR_EVIDENCE
BFE11_D04_P6_BOUNDARY_RTL_REPLAY_PASS
```

Commit and stop.

## 8. BFE11-P7 - SCI-style package and final freeze

Generate figures only from frozen BFE8 D02 data and completed BFE11 D04 data.

### 8.1 Primary paired duration-sensitivity figure

Create:

```text
BFE11_D04_D02_PAIRED_HEADROOM.pdf
BFE11_D04_D02_PAIRED_HEADROOM.png
```

Recommended figure:

- x-axis: process seed or paired process index;
- y-axis: `Decision Headroom H_D (M-codes)`;
- show D02 3.0 ns and D04 0.6 ns for identical process instances;
- include `H_D=0` decision boundary;
- preserve pairing visually;
- white background, compact serif/Times-like text if available, grayscale-readable markers/line styles, no decorative palette;
- annotate only coverage and key min/median headroom when useful.

### 8.2 Secondary signed-error shadow figure

If readable and useful, create one compact figure/table showing D04 signed-e against the predeclared `T_POS=18/19` boundaries and clearly label it **diagnostic / not implemented**. Do not let this figure replace the formal ARCH0 duration result.

### 8.3 Final artifact package

Publish under:

`delay_chain/ftc/analysis/b_fe_frontend/bfe11_d04_arch0_duration_sensitivity/`

at minimum:

```text
P0_EVIDENCE_MATRIX.md/json
P0_REUSE_MANIFEST.json
P0_SIMULATION_BUDGET.json
BFE11_D04_PER_SEED.csv
BFE11_D04_METRICS.json
BFE11_D04_D02_PAIRED.csv
BFE11_D04_D02_COMPARISON.json
BFE11_D04_SIGNED_SHADOW.json/csv
BFE11_D04_RUN_LEDGER.json
BFE11_D04_D02_PAIRED_HEADROOM.pdf/png
BFE11_D04_REPORT.md
BFE11_D04_GATE.json
```

Final formal comparison table:

| Metric | D04 60 mV / 0.6 ns | D02 60 mV / 3.0 ns frozen baseline |
|---|---:|---:|
| Detection coverage | `x/30` | `30/30` |
| Headroom min / median | `... / ...` | `19 / 38` M-codes |
| First-alarm latency median / worst | `... / ...` | `20.5345 / 20.5345 ns` |

Below it state once:

```text
Common ARCH0 margins: RISE=22, FALL=24 M-codes
Common held-out healthy FPR: 1/240 observed events
```

Also report the D04 attack-onset-referenced latency interpretation separately so it is not mistaken for an architectural pipeline speedup.

Final gate:

`BFE11_D04_ARCH0_DURATION_SENSITIVITY_FROZEN`

The gate freezes the 60 mV 3.0 ns versus 0.6 ns duration comparison. It does not require D04 30/30 and does not authorize ARCH1 implementation.

## 9. Resume discipline and simulation accounting

Maintain an append-only run ledger. Before every simulator call ask, in order:

1. Is the required datum already retained in BFE7/BFE8/BFE9/BFE10/signed-audit evidence?
2. Can it be obtained by offline reparse?
3. Is there already a valid same-seed D04 source/capture case with matching hashes/signature?
4. Only if all three are no may a new simulator call occur.

P2 seed41001 is part of the 30 and must not be rerun in P3. A failed/corrupt task-local artifact may be regenerated only after documenting why it is not reusable.

Expected maximum new simulation work for this plan:

```text
D04 HSPICE source cases          = 30 total maximum
D04 real capture cases           = 30 total maximum
healthy/D01/D02 physical reruns  = 0
margin/FPR simulations           = 0
PrimeSim                         = 0
DC/STA/P&R                       = 0
production ARCH0 RTL replay      = 0 default, <=1 conditional task-scoped run
```

## 10. Macro-direction guardrails for Codex

The research sequence is intentionally:

```text
BFE8 D02: 60 mV / 3.0 ns ARCH0 positive-control baseline
       |
BFE9 D01: 30 mV / 3.0 ns amplitude sensitivity -> observed blindspot
       |
BFE10: D01 miss mechanism audit
       |
ARCH1 signed-error audit: retained D01/healthy separability exists
       |
       v
BFE11 D04: 60 mV / 0.6 ns ARCH0 duration sensitivity   <-- THIS PLAN ONLY
       |
       +--> formal ARCH0 paired duration result
       |
       +--> zero-extra-physics signed-error shadow generalization check
       |
       v
STOP and choose the next stage from measured evidence
```

BFE11 must not become an ARCH1 implementation exercise and must not become a full D03-D12 sweep. Its job is to establish the second orthogonal ARCH0 sensitivity dimension after amplitude: short-duration voltage-droop exposure at the same 60 mV depth.

Decision discipline after final freeze:

- If D04 is robust, accept that evidence and move later to another already-frozen disturbance dimension rather than inventing a shorter waveform inside BFE11.
- If D04 is marginal/partial, preserve exact miss seeds and first perform a focused retained-data mechanism audit before redesigning hardware.
- If the predeclared signed-error shadow rule generalizes to D04, record this as stronger evidence for a later low-cost ARCH1 signed-comparator microarchitecture stage; do not implement it here.
- If signed-error does not generalize, do not tune `T_POS` on D04. Preserve the negative result and later assess whether another backend feature or frontend observability change is actually justified.

Execute P0 -> P7 strictly in order, publish/commit each stage gate, and stop after `BFE11_D04_ARCH0_DURATION_SENSITIVITY_FROZEN`. Scientific FAIL/PARTIAL outcomes are acceptable and must not trigger hidden retuning.
