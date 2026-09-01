# B-FE12-ARCH1-SIGN0: Minimal Signed-Error Droop Comparator RTL Integration Plan

Status: `ACTIVE_PLAN`

Branch: `bfe-multitap-latched-frontend`

Plan baseline commit: `e517af7e06ec109825c417da10c82f29a6d29b52`

## 0. Stage objective and macro-direction

BFE12 converts the already-frozen **signed-error droop comparator requirement** from retained-data/shadow evidence into a **minimal research-candidate RTL building block**. This stage must isolate one causal change only:

```text
ARCH0 backend decision
    abs(e) > M_MARGIN

        +

ARCH1-SIGN0 RISE droop branch
    e > T_POS_RISE
```

where `e = M_FF - M_REF` and the two alarm requests are OR-combined at the existing alarm-output stage.

This stage is deliberately **not** the full ARCH1 implementation. The gated fine-step tracker, temporal voting, startup-anchor drift budget, trusted OPP/rebase handling, adaptive/reference-tracking state, `N=sum(q)`, spatial classifiers, LUT/ML and FALL signed-error rules remain deferred. The only new detector logic authorized here is the already-required RISE signed-error branch.

The scientific/engineering question is:

> Can a real RTL implementation of the pre-ABS signed RISE droop decision reproduce the frozen D01/D04 shadow benefit, preserve ARCH0 behavior when disabled or outside its scope, and do so without changing the frontend, startup calibration, absolute-error detector, or pipeline latency?

### Hard prohibitions

- Do not modify the physical/frontend path, `safe_d`, LATQ/DFF capture semantics, tap count, `q_ff`, or `M_FF` definition.
- Do not launch HSPICE, PrimeSim, XA/source capture, DC, STA, P&R, or any new physical simulation.
- Do not rerun BFE8/BFE9/BFE10/BFE11 physical simulations.
- Do not regenerate D01/D02/D04 waveforms.
- Do not change ARCH0 `M_MARGIN_RISE=22`, `M_MARGIN_FALL=24`, strict `>` semantics, startup calibration `sum4 >> 2`, or per-chip references.
- Do not implement the fine-step tracker in BFE12.
- Do not invent a FALL signed comparator from RISE-only evidence.
- Do not tune `T_POS_RISE` from BFE12 outcomes. Only the already-frozen diagnostic candidates `18` and `19` may be exercised as evidence-backed configurations.
- Do not freeze either `18` or `19` as the final production/PVT/silicon threshold in this stage.
- Do not replace or silently edit the authoritative ARCH0 RTL files merely to simplify implementation.
- If RTL results disagree with the frozen shadow evidence, first debug event/polarity/sign/threshold pipeline alignment. Do **not** retune thresholds or rerun physics to force agreement.

## 1. BFE12-P0 - Freeze authorities, RTL hashes, retained evidence and simulation budget

Before adding RTL, read the current branch and freeze all authorities into a new task directory:

`delay_chain/ftc/analysis/b_fe_frontend/bfe12_arch1_sign0_signed_droop_rtl/`

### 1.1 Architecture authority

Required:

- `delay_chain/ftc/analysis/b_fe_frontend/bfe5_arch1_candidate/BFE5_ARCH1_CANDIDATE.md`

At plan creation the branch already freezes two ARCH1 backend requirements:

```text
1. bounded/gated fine-step background tracking   [not implemented in BFE12]
2. pre-ABS signed-error droop comparator         [implemented in BFE12]
```

BFE12 must follow the documented RISE form:

```text
SIGNED_DROOP_ALARM_RISE = RISE_event && (e > T_POS_RISE)
ALARM_REQUEST = ABS_ALARM || SIGNED_DROOP_ALARM
```

and must preserve alarm priority over any future tracking update.

### 1.2 Authoritative ARCH0 RTL to preserve

Freeze SHA256/blob identity of at least:

- `delay_chain/ftc/rtl/bfe_backend_ctrl.sv`
- `delay_chain/ftc/rtl/bfe_backend_top.sv`
- `delay_chain/ftc/rtl/bfe_capture_bank.sv`
- `delay_chain/ftc/rtl/bfe_m_feature.sv`
- `delay_chain/ftc/tests/bfe_backend_rtl2_tb.sv`

At plan creation the GitHub blob identities are:

```text
bfe_backend_ctrl.sv      e340980efc7535348721276c7500d881c59ec1d7
bfe_backend_top.sv       2216b8ed5111b4a9f7c4c5b9c34a1e33af685d30
bfe_capture_bank.sv      d9d01f77c234afaad0edabe40df2b7e20e131d76
bfe_m_feature.sv         294c1de5b3dfb91855b1623237ff64bb4dfce2aa
bfe_backend_rtl2_tb.sv   56b63fddf116174ed5f7c6cdc708c8a58b73e787
```

These ARCH0 files are **reference authorities** in BFE12. The preferred implementation is to add candidate-specific ARCH1-SIGN0 RTL files rather than rewriting ARCH0 in place.

### 1.3 Retained data authorities

Reuse without physical rerun:

- BFE8 startup calibration/reference evidence:
  - `BFE8_HEALTHY_PER_SEED.csv`
  - `BFE8_D02_MARGIN_LOCK.json`
- BFE8 held-out healthy FPR:
  - `BFE8_D02_HEALTHY_FPR.csv`
  - `BFE8_D02_HEALTHY_FPR_METRICS.json`
- BFE8 D02 positive-control target rows:
  - `BFE8_D02_PER_SEED.csv`
- BFE9 D01 target rows:
  - `BFE9_D01_PER_SEED.csv`
- frozen signed-error audit:
  - `ARCH1_SIGNED_ERROR_PER_SAMPLE.csv`
  - `ARCH1_SIGNED_ERROR_SEPARABILITY_AUDIT_GATE.json`
- BFE11 D04 target rows and shadow result:
  - `BFE11_D04_PER_SEED.csv`
  - `BFE11_D04_SIGNED_SHADOW.json`

Frozen evidence to reproduce, not retune:

```text
Healthy RISE signed-e retained max = +18
D01 signed-e retained min          = +20
D04 signed-e retained min          = +20
T_POS_RISE diagnostic candidates   = 18, 19

ARCH0 D01 coverage                 = 22/30
shadow D01 coverage @18/@19        = 30/30

ARCH0 D04 coverage                 = 24/30
shadow D04 coverage @18/@19        = 30/30

ARCH0 D02 coverage                 = 30/30
common held-out healthy FPR        = 1/240
```

### 1.4 Reuse matrix and simulation budget

Create:

- `P0_AUTHORITY.json`
- `P0_REUSE_MATRIX.md`
- `P0_SIMULATION_BUDGET.json`

Required accounting:

```text
HSPICE / physical source      = 0
LATQ/DFF capture rerun         = 0
PrimeSim                       = 0
DC / STA / P&R                 = 0
healthy physical rerun         = 0
D01 physical rerun             = 0
D02 physical rerun             = 0
D04 physical rerun             = 0

new RTL VCS scientific regressions:
  directed full-top regression = 1
  retained-data A/B replay      = 1
```

These are two logical scientific regressions, not a license to add unrelated tests. A retry caused by compile/harness defects may repeat the **same** stimulus only after the defect is documented in the run ledger.

Gate: `BFE12_SIGN0_P0_AUTHORITIES_FROZEN`

Commit and stop before P1.

## 2. BFE12-P1 - Add candidate-only SIGN0 RTL, no simulator call

### 2.1 Candidate files

Preferred new files:

```text
delay_chain/ftc/rtl/bfe_backend_ctrl_arch1_sign0.sv
delay_chain/ftc/rtl/bfe_backend_arch1_sign0_top.sv
```

The authoritative ARCH0 files `bfe_backend_ctrl.sv` and `bfe_backend_top.sv` must remain byte-identical during BFE12.

The candidate top may inherit the ARCH0 external status interface and add only the configuration required by this stage:

```text
input [8:0] t_pos_rise
```

Do not add tracker/OPP/background-adaptation ports in SIGN0.

### 2.2 Reuse the existing split subtraction; do not build a second subtractor

The current ARCH0 controller already computes two pieces of signed information internally:

```text
sub_dir_q : direction of M_FF versus M_REF

delta_q   : |M_FF - M_REF|
```

The minimal SIGN0 implementation must reuse this sign+magnitude representation. Do **not** add a duplicate 10-bit signed subtractor on the alarm critical path unless the existing representation is first proven unusable.

For a positive RISE error:

```text
e > T_POS_RISE
```

is equivalent at the aligned output boundary to:

```text
RISE_event
&& positive_direction
&& delta_q > T_POS_RISE
```

### 2.3 Mandatory event-context alignment

The current ARCH0 pipeline captures M/reference/margin, pipes operands, performs P4a direction/low-half subtraction, then P4b completes `delta_q` and aligns `alarm_margin_q`.

SIGN0 must carry the signed-decision context through the same event pipeline. At minimum, preserve event-atomic copies equivalent to:

```text
event_edge_pol_q
    -> event_edge_pol_pipe_q
    -> sub_edge_pol_q
    -> alarm_edge_pol_q

event_t_pos_rise_q
    -> event_t_pos_rise_pipe_q
    -> sub_t_pos_rise_q
    -> alarm_t_pos_rise_q

sub_dir_q
    -> alarm_dir_q
```

Exact names may differ, but at the cycle where `delta_q` and `alarm_margin_q` describe one event, the candidate must also have the **same event's** polarity, sign/direction and `T_POS_RISE` value.

Do not use the live input `edge_pol_i` or a later event's `sub_dir_q` directly at the final comparator.

### 2.4 Required alarm equations

At the existing final compare boundary, conceptually implement:

```text
ABS_ALARM =
    delta_valid_q
    && (delta_q > alarm_margin_q)

SIGNED_RISE_ALARM =
    delta_valid_q
    && !alarm_edge_pol_q
    && alarm_dir_q
    && (delta_q > alarm_t_pos_rise_q)

DROOP_ALARM = ABS_ALARM || SIGNED_RISE_ALARM
```

Important semantics:

- comparator remains strict `>`;
- `e == T_POS_RISE` is quiet;
- negative RISE error must not trigger the signed-positive branch;
- FALL must not trigger the signed-positive branch;
- the inherited absolute branch continues to detect either sign as before;
- no extra pipeline stage may be added after the current alarm boundary;
- sticky behavior remains the existing `droop_alarm`-observed-next-edge behavior.

Internal `ABS_ALARM` and `SIGNED_RISE_ALARM` nets should be named clearly enough for task-local waveform/assertion visibility, but BFE12 does not require new production macro output pins for them.

### 2.5 Disable/equivalence configuration

For regression only, use:

```text
T_POS_RISE = 435
```

as a deterministic disabled-by-threshold configuration because `e` cannot exceed 435 and the comparator is strict `>`.

This is a test mechanism, not a new product enable/disable contract.

Gate: `BFE12_SIGN0_P1_CANDIDATE_RTL_READY`

Commit and stop. Simulator count remains zero.

## 3. BFE12-P2 - One directed full-top VCS regression

Create a task-local self-checking top-level testbench derived from the current RTL2 timing discipline. It must instantiate `bfe_backend_arch1_sign0_top` so that the unchanged capture bank, `M_FF` feature pipeline, startup calibration, detector controller and sticky path are exercised together.

Use simple deterministic one-hot/constructed `safe_d` vectors; do not use HSPICE-generated waveforms.

The directed test must cover at least:

1. no alarm before `CAL_LOCK`;
2. four-sample RISE and four-sample FALL startup calibration still use exact `sum4 >> 2` semantics;
3. strict signed equality:
   - at `T_POS_RISE=18`, `e=+18` is quiet and `e=+19` alarms;
   - at `T_POS_RISE=19`, `e=+19` is quiet and `e=+20` alarms;
4. a negative RISE `e` does not trigger `SIGNED_RISE_ALARM`;
5. a FALL positive excursion does not trigger `SIGNED_RISE_ALARM`;
6. the inherited absolute comparator still alarms for sufficiently large positive or negative excursions and remains quiet at exact absolute-margin equality;
7. calibration-mode and invalid events never create a current alarm;
8. combined alarm reaches the same final detector stage as ARCH0—no added event/cycle latency;
9. sticky is set from the combined alarm with the same next-edge semantics and reset remains the only sticky clear mechanism.

Record an explicit cycle table for one ABS-only alarm and one SIGNED-only recovered alarm. Their detector output stage must match.

Gate: `BFE12_SIGN0_P2_DIRECTED_TOP_RTL_PASS`

If this gate fails, fix candidate RTL/test alignment only. Do not alter upstream ARCH0, frontend, thresholds or physical data.

Commit and stop.

## 4. BFE12-P3 - Build retained controller-level replay pack offline

This stage is offline only: parse retained CSV/JSON and generate deterministic controller-level stimuli. Do not launch VCS yet.

### 4.1 Per-seed calibration reconstruction

For every process seed `41001..41030`, read the four frozen RISE and four frozen FALL startup `M_CAL` samples from BFE8 and independently assert:

```text
(sum(M_CAL_RISE[0:4]) >> 2) == M_REF_RISE
(sum(M_CAL_FALL[0:4]) >> 2) == M_REF_FALL
```

The replay testbench must calibrate the RTL through the normal controller interface using these retained `M_FF` values. Do not force internal reference registers.

### 4.2 Retained event sets

Build one deterministic stimulus manifest containing at least:

```text
A. BFE8 held-out FPR events
   240 events, including both RISE and FALL

B. frozen signed-audit healthy RISE set
   360 retained RISE samples

C. D01 target events
   30 seeds

D. D02 target events
   30 seeds

E. D04 target events
   30 seeds
```

For each event preserve at least:

```text
dataset
seed
polarity
M_FF
M_REF expected
ARCH0 absolute margin
expected signed e
expected ARCH0 alarm
expected SIGN0@18 alarm
expected SIGN0@19 alarm
source artifact/hash
```

Recompute expectations directly from the frozen rules; do not threshold-sweep.

### 4.3 Pre-VCS consistency assertions

The generated replay pack must reproduce the already-frozen offline facts exactly before P4 is allowed:

```text
held-out healthy ARCH0 FPR = 1/240
healthy RISE signed max    = +18
D01 ARCH0                  = 22/30
D01 SIGN0@18/@19           = 30/30
D02 ARCH0                  = 30/30
D04 ARCH0                  = 24/30
D04 SIGN0@18/@19           = 30/30
```

Expected recovered seed sets must be frozen explicitly:

```text
D01 ARCH0 MISS recovered by signed branch:
41005, 41007, 41012, 41015, 41016, 41022, 41025, 41028

D04 ARCH0 MISS recovered by signed branch:
41007, 41012, 41015, 41016, 41022, 41025
```

Gate: `BFE12_SIGN0_P3_RETAINED_REPLAY_PACK_FROZEN`

Commit and stop. No simulator call in P3.

## 5. BFE12-P4 - One exhaustive retained-data A/B VCS regression

Run one self-checking controller-level VCS regression. The testbench must feed the exact same calibration/event stream in parallel to:

```text
DUT_A = authoritative ARCH0 bfe_backend_ctrl
DUT_B = ARCH1-SIGN0 with T_POS_RISE=435   [equivalence/off]
DUT_C = ARCH1-SIGN0 with T_POS_RISE=18
DUT_D = ARCH1-SIGN0 with T_POS_RISE=19
```

All four instances receive identical `m_ff`, `event_valid`, `edge_pol`, calibration mode and ARCH0 margins. The candidate instances differ only in `T_POS_RISE`.

### 5.1 Mandatory equivalence guards

`DUT_B` must match `DUT_A` **event by event** over the complete replay pack. A mismatch means the candidate fork changed ARCH0 behavior outside the intended signed branch and blocks promotion.

For every FALL event, `DUT_C` and `DUT_D` must also match `DUT_A` event by event because the signed RISE branch is disabled by polarity.

### 5.2 Mandatory healthy checks

On BFE8 held-out FPR events:

```text
DUT_A total healthy alarms = 1/240
DUT_C total healthy alarms = 1/240
DUT_D total healthy alarms = 1/240
```

No new RISE healthy alarm is permitted for either frozen signed candidate.

On the 360 retained healthy RISE samples used in the signed audit:

```text
SIGNED_RISE_ALARM@18 = 0/360
SIGNED_RISE_ALARM@19 = 0/360
```

### 5.3 Mandatory attack coverage reproduction

Required event-level results:

```text
                     ARCH0      SIGN0@18      SIGN0@19
D01 30 mV / 3 ns     22/30       30/30         30/30
D02 60 mV / 3 ns     30/30       30/30         30/30
D04 60 mV / 0.6 ns   24/30       30/30         30/30
```

No existing ARCH0 D01/D02/D04 HIT may be lost in either candidate configuration.

The recovered D01 and D04 seed lists must equal the frozen P3 lists exactly. If not, stop and debug pipeline/context alignment; do not select a new threshold.

### 5.4 Latency semantics

For events recovered only by `SIGNED_RISE_ALARM`, the combined `droop_alarm` pulse must emerge at the same detector output stage as an ABS alarm. BFE12 must not add a pipeline stage.

Preserve the frozen TIM0 interpretation:

```text
E0 -> E7 = 7 probe edges
E4 -> E7 = 3 probe edges = 7.5 ns at 400 MHz
```

Do not claim a new physical sensor latency from this replay; it validates backend RTL cycle alignment only.

### 5.5 Outcome classification

Use one of:

```text
RTL_REPRODUCES_FROZEN_SHADOW
    event-level equivalence and all expected retained results reproduced.

PIPELINE_OR_CONTEXT_MISMATCH
    sign/polarity/threshold/event context does not align with delta; debug RTL/harness only.

SIGNED_RULE_LIMITED_IN_RTL
    only after alignment is proven correct, retained RTL behavior genuinely fails to reproduce the offline rule; preserve as negative evidence and do not retune T_POS.
```

Gate: `BFE12_SIGN0_P4_RETAINED_AB_RTL_CHARACTERIZED`

Commit and stop.

## 6. BFE12-P5 - Final freeze, evidence package and architecture cross-link

Publish under:

`delay_chain/ftc/analysis/b_fe_frontend/bfe12_arch1_sign0_signed_droop_rtl/`

at minimum:

```text
P0_AUTHORITY.json
P0_REUSE_MATRIX.md
P0_SIMULATION_BUDGET.json
P2_DIRECTED_TOP_RESULTS.json
P2_DIRECTED_TOP_REPORT.md
P3_REPLAY_MANIFEST.csv/json
P4_EVENT_RESULTS.csv
P4_COVERAGE_SUMMARY.json
P4_EQUIVALENCE_SUMMARY.json
BFE12_SIGN0_RUN_LEDGER.json
BFE12_SIGN0_REPORT.md
BFE12_SIGN0_GATE.json
```

The final report must clearly separate:

```text
ARCH0 authoritative implementation
ARCH1-SIGN0 research-candidate RTL
```

and must not describe full ARCH1 as implemented because the tracker is still absent.

### 6.1 Final success criteria for the signed-comparator building block

For classification `RTL_REPRODUCES_FROZEN_SHADOW`, require all of:

```text
ARCH0 source files unchanged
frontend/capture source files unchanged
no physical simulations
SIGN0@435 bit/event-equivalent to ARCH0 on retained replay
no new FALL behavior
healthy held-out FPR remains 1/240
healthy signed-audit RISE additions remain 0/360
D01 SIGN0@18/@19 = 30/30
D02 SIGN0@18/@19 = 30/30
D04 SIGN0@18/@19 = 30/30
no ARCH0 attack HIT lost
signed-only and absolute alarms share the existing output stage
production T_POS_RISE not frozen
fine-step tracker not implemented
```

Final gate:

`BFE12_ARCH1_SIGNED_DROOP_COMPARATOR_RTL_FROZEN`

If the final gate succeeds, append only a short evidence cross-reference to `BFE5_ARCH1_CANDIDATE.md` stating that the required signed comparator has a validated SIGN0 research RTL implementation and pointing to the BFE12 gate. Do **not** promote the complete ARCH1 architecture or claim tracker validation.

## 7. Macro-direction guardrails for Codex

The project trajectory is intentionally:

```text
BFE8  D02 ARCH0 baseline
  |
BFE9  D01 amplitude blindspot
  |
BFE10 D01 miss mechanism
  |
ARCH1 signed-error retained separability audit
  |
BFE11 D04 duration blindspot + signed shadow generalization
  |
ARCH1 architecture document updated:
  signed comparator is a required block
  |
  v
BFE12 ARCH1-SIGN0
  minimal signed comparator candidate RTL only   <-- THIS PLAN
  |
  +-- preserve ARCH0
  +-- no physical reruns
  +-- no tracker
  +-- reproduce D01/D04 shadow benefit in RTL
  |
  v
STOP
```

Only after BFE12 is frozen should a later stage consider combining the validated signed comparator with the gated fine-step tracker and testing benign drift, slow unauthorized droop, tracker poisoning and trusted OPP transitions (`ADAPT0`-class work).

BFE12 must not drift into a full ARCH1 tracker implementation, a D03-D12 waveform sweep, frontend redesign, PVT signoff, threshold optimization, area/power campaign, or new physical characterization.

Execute P0 -> P5 strictly in order, commit each stage gate, and stop after `BFE12_ARCH1_SIGNED_DROOP_COMPARATOR_RTL_FROZEN`.
