# BFE13-ARCH1-TRACK0: Minimal Dual-Reference Fine-Step Tracker RTL Plan

Status: `ACTIVE_PLAN`

Branch: `bfe-multitap-latched-frontend`

Plan baseline commit: `ce3b650c2dde71f90f13f13f1a5adbe031ffa744`

## 0. Stage objective and macro direction

BFE13 implements only the **minimal TRACK0 research RTL building block** required by the now-synchronized ARCH1 dual-reference architecture. It must not become a full ARCH1/ADAPT0 implementation.

The architectural objective is:

```text
M_REF_STARTUP / SECURITY ANCHOR
    -> immutable under ordinary tracking
    -> signed RISE droop decision

M_REF_TRACK
    -> mutable by bounded fine-step tracker
    -> absolute-error decision and track/hold decision
```

The stage proves only that a timing-friendly RTL tracker can move `M_REF_TRACK` safely and event-atomically while preserving the already-validated signed security path and existing alarm latency.

The central safety invariant is:

> A normal event may create a **candidate** tracking action while it is in flight, but `M_REF_TRACK` may not be modified until that same event has completed the E7 absolute/signed alarm decision. Any event that alarms must contribute zero reference update.

The central timing invariant is:

> Tracker state/update logic must remain outside the E4-to-E7 alarm critical path. Alarm timing remains at the existing E7 boundary; tracker commit occurs at E8 and never adds an alarm pipeline stage.

### Hard prohibitions

- Do not modify the physical/frontend path, capture timing, tap count, `q_ff[29:0]`, or `M_FF` definition.
- Do not modify authoritative ARCH0 RTL.
- Do not modify frozen BFE12 SIGN0 RTL; TRACK0 must be a new candidate fork.
- Do not add external TRACK0 control/status/debug ports.
- Do not implement trusted OPP/DVFS/rebase, security-anchor rebase, recovery protocol, or a new clear mechanism.
- Do not implement a FALL signed comparator.
- Do not implement K-of-N, long voting windows, EWMA, adaptive margins, dynamic `T_POS`, LUT/ML, spatial features, clock-glitch fusion, or broad policy logic.
- Do not tune or freeze a production value for `T_POS_RISE`, `T_TRACK`, or `B_TRACK` from this stage.
- Do not run HSPICE, PrimeSim, LATQ/DFF capture regeneration, waveform regeneration, DC, STA, P&R, or new physical/PVT simulations.
- Do not rerun D01/D02/D04 physical simulations.
- If a failure occurs, debug RTL event/context alignment and tracker state semantics first. Do not retune thresholds or regenerate physical data to force a PASS.

## 1. BFE13-P0 - Freeze authorities and zero-physical-simulation budget

Create the task directory:

`delay_chain/ftc/analysis/b_fe_frontend/bfe13_arch1_track0_rtl/`

Before implementation, fresh-read and hash the current branch authorities.

Required architecture/evidence authorities:

- `delay_chain/ftc/analysis/b_fe_frontend/bfe5_arch1_candidate/BFE5_ARCH1_CANDIDATE.md`
- `delay_chain/ftc/analysis/b_fe_frontend/arch1_signed_tracking_reference_interaction_audit/REFERENCE_INTERACTION_REPORT.md`
- `delay_chain/ftc/analysis/b_fe_frontend/arch1_signed_tracking_reference_interaction_audit/REFERENCE_INTERACTION_SUMMARY.json`
- `delay_chain/ftc/analysis/b_fe_frontend/bfe12_arch1_sign0_signed_droop_rtl/BFE12_SIGN0_GATE.json`

Required RTL authorities to preserve:

- `delay_chain/ftc/rtl/bfe_backend_ctrl.sv`
- `delay_chain/ftc/rtl/bfe_backend_top.sv`
- `delay_chain/ftc/rtl/bfe_capture_bank.sv`
- `delay_chain/ftc/rtl/bfe_m_feature.sv`
- `delay_chain/ftc/rtl/bfe_backend_ctrl_arch1_sign0.sv`
- `delay_chain/ftc/rtl/bfe_backend_arch1_sign0_top.sv`

At plan creation the synchronized ARCH1 document has blob SHA `98ffceffb9041a0ac3b6c97d79bef06cea4f900c`; BFE12 SIGN0 controller/top blobs are `9f8b5768d2a502ebc16e0639ed474cce44e36632` and `f6230067c0a3cf6e9d2b966fdd23c871b7e408b5`. P0 must nevertheless record the fresh current identities before implementation.

Create:

```text
P0_AUTHORITY.json
P0_REUSE_MATRIX.md
P0_SIMULATION_BUDGET.json
```

Required tool budget:

```text
HSPICE / physical source             = 0
LATQ/DFF capture regeneration         = 0
PrimeSim                              = 0
DC / STA / P&R                        = 0
healthy/D01/D02/D04 physical rerun    = 0
new RTL VCS logical regressions       = 2 maximum
```

The two allowed logical regressions are:

```text
1. directed TRACK0 full-top/controller regression
2. retained BFE12 SIGN0-equivalence A/B replay
```

Compile/harness retries may repeat the identical stimulus only after the retry reason is documented; they do not authorize additional scientific experiments.

Gate: `BFE13_TRACK0_P0_AUTHORITIES_FROZEN`

Commit and stop before P1.

## 2. BFE13-P1 - Freeze the TRACK0 RTL microarchitecture before coding

No RTL modification and no simulator call in this stage.

Create:

`delay_chain/ftc/analysis/b_fe_frontend/bfe13_arch1_track0_rtl/TRACK0_RTL_ARCH_CONTRACT.md`

The following microarchitecture is mandatory unless a contradiction with the frozen current RTL is demonstrated and documented before coding.

### 2.1 External interface: zero new ports

`bfe_backend_arch1_track0_top` must inherit the complete BFE12 SIGN0 external interface unchanged:

```text
safe_d[29:0]
latch_gate
clk_probe
reset
event_valid
edge_pol
cal_mode
m_margin_rise[8:0]
m_margin_fall[8:0]
t_pos_rise[8:0]
cal_lock
droop_alarm
droop_alarm_sticky
```

Do not add `track_enable`, `track_state`, `track_ref`, `track_freeze`, `t_track`, `b_track`, rebase, OPP, or debug ports.

TRACK0-specific tuning is compile/elaboration-time only through four module parameters:

```text
T_TRACK_RISE
T_TRACK_FALL
B_TRACK_RISE
B_TRACK_FALL
```

All four parameters must default to zero so the default TRACK0 build is tracker-disabled and can serve as a direct SIGN0-equivalence configuration. Nonzero values used in directed tests are task-local research configurations, not production freezes.

### 2.2 Minimal reference state

Maintain independent RISE/FALL startup and tracking references:

```text
m_ref_startup_rise_q
m_ref_startup_fall_q
m_ref_track_rise_q
m_ref_track_fall_q
```

On the fourth accepted startup calibration sample for a polarity:

```text
startup_ref = (sum_previous_three + current_M_FF) >> 2
m_ref_startup_* <= startup_ref
m_ref_track_*   <= startup_ref
```

TRACK0 does not need a third physical security-anchor register. For this stage:

```text
M_REF_SECURITY_ANCHOR_RISE == m_ref_startup_rise_q
M_REF_SECURITY_ANCHOR_FALL == m_ref_startup_fall_q
```

The startup registers are immutable after calibration until reset. Ordinary tracker logic must have no write path to them.

### 2.3 Two arithmetic lanes, but no duplicated wide signed subtractor

#### Tracking / ABS lane

Use the existing timing-friendly split sign+magnitude subtraction structure, but its reference source becomes the selected `M_REF_TRACK`:

```text
e_track = M_FF - M_REF_TRACK_selected
D_track = abs(e_track)
```

Reuse the existing P4a/P4b-style high/low split; do not replace it with a new monolithic wide subtractor.

#### Signed security lane

For the characterized RISE rule:

```text
e_anchor > T_POS_RISE
```

implement the algebraically equivalent trip-point form:

```text
zero_extend(M_FF) > zero_extend(M_REF_STARTUP_RISE) + zero_extend(T_POS_RISE)
```

Use a **10-bit** trip point so `anchor + T_POS_RISE` cannot overflow the 9-bit code width. This lane should be pipelined as a shallow add then compare, not as a second subtract/abs path. `T_POS_RISE=435` must naturally disable the signed lane because `M_FF<=435` and the comparator is strict `>`.

No FALL signed test is added.

### 2.4 Frozen logical stage contract

Preserve the existing event pipeline and alarm latency. Conceptually:

```text
E4  capture one atomic event parcel
    - M_FF
    - selected M_REF_TRACK snapshot
    - startup/security anchor needed by signed RISE
    - edge polarity
    - absolute margin
    - T_POS_RISE

E5  tracking lane: split subtraction P4a
    security lane: form/register 10-bit anchor + T_POS trip point

E6  tracking lane: split subtraction P4b -> sign + D_track
    security lane: compare event M_FF against registered trip point
    pipeline/alignment registers keep both lanes event-atomic

E7  ABS_ALARM = valid && (D_track > margin)
    SIGNED_RISE_ALARM = valid && RISE && signed-trip-hit
    DROOP_ALARM = ABS_ALARM || SIGNED_RISE_ALARM

E8  sticky update
    TRACK0 FSM/commit logic
```

Exact internal register names may differ, but E7 alarm latency must remain identical to BFE12. No tracker combinational logic may feed the E7 alarm compare/OR cone.

### 2.5 Event-atomic tracker commit

A tracking update is never performed at E4/E5/E6/E7. The final aligned E7 event context is consumed at E8.

Priority at E8 is frozen as:

```text
if current E7 droop_alarm:
    no reference update
    clear both temporal candidate FSMs to IDLE
else if droop_alarm_sticky was already set:
    no reference update
    keep tracker frozen
else if event is stale relative to its captured tracking-reference snapshot:
    no reference update
    clear the selected-polarity FSM to IDLE
else:
    evaluate the selected-polarity TRACK0 FSM
```

Because sticky has no trusted recovery input in TRACK0, once sticky is set the autonomous tracker remains frozen until reset.

### 2.6 Mandatory stale-reference guard; no bypass

An event's tracking error was computed against the `M_REF_TRACK` value captured with that event at E4. A prior event may commit a new tracking reference before this later in-flight event reaches E8. Therefore TRACK0 must carry enough reference-snapshot context to enforce:

```text
captured_track_ref_for_this_event == current_selected_M_REF_TRACK
```

before an E8 update may be committed.

If they differ, the event is stale and cannot count toward persistence or move the reference.

This guard is intentionally outside the alarm path and prevents multiple pipelined events, all computed against an old reference, from causing a cascade of stale `+1/-1` updates.

Do not add an E8-to-E4 combinational bypass mux. A reference update at E8 is visible only to later events that capture it on a subsequent clock. An event that captured the pre-update reference is allowed to become stale and is then discarded by the snapshot guard.

### 2.7 Minimal temporal FSM

Use exactly one independent 2-bit FSM per polarity:

```text
00 IDLE
01 WAIT_POS
10 WAIT_NEG
11 RESERVED / treated as IDLE on recovery
```

Do not introduce a larger state machine in TRACK0.

Opposite-polarity events do not disturb the other polarity's state. For the selected polarity, after all alarm/sticky/stale guards:

```text
D_track == 0:
    selected FSM -> IDLE

0 < D_track <= T_TRACK and e_track positive:
    IDLE     -> WAIT_POS
    WAIT_POS -> commit +1 LSB if upper bound permits, then IDLE
    WAIT_NEG -> WAIT_POS without update

0 < D_track <= T_TRACK and e_track negative:
    IDLE     -> WAIT_NEG
    WAIT_NEG -> commit -1 LSB if lower bound permits, then IDLE
    WAIT_POS -> WAIT_NEG without update

D_track > T_TRACK but no alarm:
    selected FSM -> IDLE
    no update
```

Thus two accepted same-polarity, same-direction small-error observations are required for one reference step. This is the entire TRACK0 temporal filter; do not expand it into K-of-N/EWMA logic.

### 2.8 Bounded update without runtime absolute-difference arithmetic

At startup calibration completion, precompute and register saturated bounds for each polarity using 10-bit intermediate arithmetic:

```text
TRACK_UPPER = min(435, M_REF_STARTUP + B_TRACK)
TRACK_LOWER = max(0,   M_REF_STARTUP - B_TRACK)
```

At E8, a positive commit is permitted only if `M_REF_TRACK < TRACK_UPPER`; a negative commit only if `M_REF_TRACK > TRACK_LOWER`.

The E8 update cone should therefore contain only small FSM decode, equality/bound comparisons, and a 9-bit `+1/-1`; it must not contain a new wide `abs(M_REF_TRACK-M_REF_STARTUP)` datapath.

### 2.9 Timing-friendly structural rules

Freeze all of the following:

```text
external TRACK0 ports added               = 0
alarm output stage added                  = 0
tracker logic in E4->E7 alarm cone        = 0
E8->E4 combinational reference bypass     = 0
second full signed subtractor              = 0
ordinary writes to startup/security ref   = 0
RISE/FALL tracker FSM bits                 = 2 each
reference step per accepted commit         = exactly +/-1 LSB max
```

Gate: `BFE13_TRACK0_P1_RTL_ARCH_FROZEN`

Commit and stop before P2.

## 3. BFE13-P2 - Implement candidate-only TRACK0 RTL, no simulator call

Add only:

```text
delay_chain/ftc/rtl/bfe_backend_ctrl_arch1_track0.sv
delay_chain/ftc/rtl/bfe_backend_arch1_track0_top.sv
```

Reuse unchanged:

```text
bfe_capture_bank.sv
bfe_m_feature.sv
```

Do not edit ARCH0 or BFE12 SIGN0 source files.

### 3.1 Candidate top

`bfe_backend_arch1_track0_top` must have the same ports as `bfe_backend_arch1_sign0_top`. Add only the four compile-time parameters from P1 and propagate them internally.

### 3.2 Controller implementation requirements

Implement exactly the P1 contract:

- separate immutable startup refs and mutable track refs;
- startup/security anchor aliasing for TRACK0;
- ABS/tracking split subtract sourced from `M_REF_TRACK`;
- 10-bit startup-anchor-plus-`T_POS_RISE` signed trip lane;
- event-context alignment through E7;
- independent two-state-direction FSMs for RISE/FALL;
- startup-precomputed saturated track bounds;
- E8 alarm-priority commit;
- sticky freezes tracker until reset;
- event track-reference snapshot equality guard;
- no bypass and no alarm-latency change.

Task-local internal nets/registers should have readable names for hierarchical assertions, especially:

```text
m_ref_startup_rise_q / fall_q
m_ref_track_rise_q / fall_q
track_lower_* / track_upper_*
track_state_rise_q / fall_q
abs_alarm
signed_rise_alarm
captured/aligned track-ref snapshot
```

No debug outputs are added.

### 3.3 Static source audit before simulation

Before P3, generate `P2_STRUCTURAL_AUDIT.json` and assert from source inspection that:

- TRACK0 top port list equals SIGN0 top port list exactly;
- four TRACK0 parameters default to zero;
- ARCH0/SIGN0 authoritative hashes are unchanged;
- startup refs are not assigned in normal tracking logic;
- track refs are assigned only at reset/calibration initialization/E8 commit;
- no FALL signed comparator exists;
- alarm equation is still ABS OR signed-RISE at E7;
- no tracker state is used as an input to the E7 alarm comparator;
- no reference bypass mux exists.

Gate: `BFE13_TRACK0_P2_CANDIDATE_RTL_READY`

Commit and stop. Simulator count remains zero.

## 4. BFE13-P3 - One directed VCS regression for TRACK0 state/timing semantics

Run one self-checking VCS regression using deterministic digital stimuli. No HSPICE-generated waveform is needed.

The regression may instantiate controller-level and full-top candidate instances inside one testbench/run, but it counts as one logical scientific regression.

Use small non-production parameter overrides so updates can be observed quickly; document them as `DIRECTED_TEST_ONLY`. Do not promote them to architecture/signoff values.

Mandatory checks:

1. **Startup dual-reference initialization**
   - four RISE and four FALL samples preserve exact `sum4 >> 2` calibration;
   - `M_REF_TRACK_* == M_REF_STARTUP_*` at lock;
   - startup/security refs never change during ordinary tracking.

2. **Default-disable semantics**
   - with all four TRACK0 parameters at zero, no tracking reference update can occur.

3. **Two-observation positive update**
   - first safe positive small-error event moves selected FSM `IDLE -> WAIT_POS` only;
   - second accepted same-polarity positive small-error event commits exactly `+1` and returns to IDLE.

4. **Two-observation negative update**
   - symmetric `WAIT_NEG` behavior with exactly `-1` step.

5. **Polarity independence**
   - an intervening FALL event does not erase a pending RISE state and vice versa;
   - RISE and FALL references update independently.

6. **Direction reversal**
   - `WAIT_POS + small negative -> WAIT_NEG` without update;
   - `WAIT_NEG + small positive -> WAIT_POS` without update.

7. **Zero/HOLD behavior**
   - `D_track==0` resets the selected FSM to IDLE;
   - `D_track>T_TRACK` with no alarm causes HOLD/no update and resets selected FSM.

8. **Bound behavior**
   - updates stop exactly at precomputed upper/lower bounds;
   - no wraparound and no value outside `0..435`.

9. **ABS alarm priority**
   - an event producing absolute alarm creates zero reference update and clears pending FSM evidence.

10. **Signed-only alarm priority**
    - construct a RISE event with `D_track<=M_MARGIN` but startup-anchor signed trip true;
    - E7 signed alarm must assert;
    - E8 must not update `M_REF_TRACK`;
    - sticky then freezes all subsequent tracker movement until reset.

11. **Dual-reference correctness after real tracker movement**
    - first move `M_REF_TRACK_RISE` away from startup using safe synthetic events;
    - confirm the ABS/tracking path uses the moved track reference;
    - confirm the signed RISE trip still uses the unchanged startup/security anchor.

12. **Stale-reference guard under pipelining**
    - create back-to-back/in-flight safe candidate events against one track-ref snapshot;
    - after one event commits `+1/-1`, later events carrying the old snapshot must not cause another stale update or count as persistence evidence.

13. **No bypass semantics**
    - an event captured on the same edge as an E8 reference commit sees the old reference snapshot;
    - it may later be rejected as stale; no combinational E8-to-E4 behavior is allowed.

14. **Latency**
    - an ABS-only and a signed-only alarm both still emerge at E7;
    - tracker commit occurs at E8 and does not delay `droop_alarm`;
    - sticky remains the existing E8 next-edge behavior.

Required gate:

`BFE13_TRACK0_P3_DIRECTED_RTL_PASS`

On failure, only fix TRACK0 RTL/test alignment. Do not alter upstream authorities or thresholds.

Commit and stop.

## 5. BFE13-P4 - One retained BFE12 SIGN0-equivalence A/B VCS replay

This stage is a regression/equivalence check, not new physical characterization.

Reuse the already-generated BFE12 retained replay stimulus. Do not regenerate HSPICE/capture data.

Run the same retained event stream in parallel through:

```text
A = frozen BFE12 SIGN0
B = TRACK0 with T_TRACK_RISE/FALL=0 and B_TRACK_RISE/FALL=0
```

Exercise the already-used `T_POS_RISE` configurations `435`, `18`, and `19` without any new threshold sweep.

Mandatory event-by-event checks:

- `cal_lock` equivalence;
- `droop_alarm` equivalence;
- `droop_alarm_sticky` equivalence under the same reset epochs;
- no TRACK0 reference movement in default-disable mode;
- identical FALL behavior;
- identical signed/absolute alarm timing;
- no change to the already-frozen BFE12 retained conclusions.

The replay should therefore reproduce, as a regression consequence rather than a new physical claim:

```text
healthy held-out FPR:       unchanged from BFE12
healthy signed additions:   unchanged from BFE12
D01/D02/D04 event outcomes: event-equivalent to SIGN0
```

Any mismatch is classified first as `TRACK0_SIGN0_EQUIVALENCE_FAILURE`; do not retune `T_POS`, margin, calibration, or tracker parameters to hide it.

Gate: `BFE13_TRACK0_P4_SIGN0_EQUIVALENCE_PASS`

Commit and stop.

## 6. BFE13-P5 - Final freeze and stop

Publish at minimum:

```text
TRACK0_RTL_ARCH_CONTRACT.md
P0_AUTHORITY.json
P0_REUSE_MATRIX.md
P0_SIMULATION_BUDGET.json
P2_STRUCTURAL_AUDIT.json
P3_DIRECTED_RESULTS.json
P3_DIRECTED_REPORT.md
P4_EQUIVALENCE_SUMMARY.json
BFE13_TRACK0_RUN_LEDGER.json
BFE13_TRACK0_REPORT.md
BFE13_TRACK0_GATE.json
```

Final success classification:

`DUAL_REFERENCE_EVENT_ATOMIC_TRACK0_RTL_PASS`

Final gate:

`BFE13_ARCH1_TRACK0_RTL_FROZEN`

Require all of the following for PASS:

```text
ARCH0 RTL unchanged
BFE12 SIGN0 RTL unchanged
frontend/capture unchanged
external TRACK0 ports added = 0
physical simulations = 0
alarm stage remains E7
tracker commit occurs only at E8
startup/security refs immutable under ordinary tracking
M_REF_TRACK step <= 1 LSB per accepted commit
RISE/FALL tracker states independent
2-observation same-direction persistence implemented
bounds enforced without wraparound
ABS alarm blocks current update
signed alarm blocks current update
sticky freezes subsequent autonomous updates until reset
stale-reference snapshot guard passes
no E8-to-E4 bypass
TRACK0 default-disable build is event-equivalent to BFE12 SIGN0
production T_POS/T_TRACK/B_TRACK not frozen
trusted OPP/rebase not implemented
FALL signed comparator not implemented
```

The final report must explicitly state what this gate does **not** prove:

- it does not prove real temperature/aging tracking efficacy;
- it does not prove robustness to slow malicious droop/reference poisoning;
- it does not validate trusted OPP/DVFS transitions or security-anchor rebase;
- it does not select production `T_TRACK`, `B_TRACK`, or `T_POS_RISE`;
- it does not constitute PVT/silicon/physical signoff;
- it does not promote complete ARCH1 over authoritative ARCH0.

If BFE13 passes, only then should a successor ADAPT0-class stage design representative benign-drift and slow-attack temporal trajectories and evaluate tracker efficacy/security. Do not start those experiments inside BFE13.

## 7. Codex macro-direction guardrail

The intended project trajectory is:

```text
BFE12 SIGN0
  signed RISE comparator RTL validated
        |
        v
reference-interaction audit
  direct M_REF_TRACK coupling rejected as default
        |
        v
ARCH1 dual-reference policy synchronized
  ABS/TRACK -> M_REF_TRACK
  SIGNED    -> startup/trusted security anchor
        |
        v
====================================================
BFE13 TRACK0                                  <-- NOW
minimal timing-friendly tracker RTL only
- zero new external ports
- two 2-bit polarity FSMs
- +/-1 LSB bounded update
- E7 alarm before E8 commit
- immutable security anchor
- stale-reference guard
- no bypass
====================================================
        |
        v
STOP
        |
        v
later ADAPT0
benign drift / slow unauthorized droop /
poisoning / trusted OPP temporal validation
```

Do not drift from BFE13 into real drift modeling, full ARCH1 policy, OPP/rebase, threshold optimization, PVT, physical simulation, area/power campaigns, new waveform families, or frontend redesign.

Execute P0 -> P5 strictly in order, commit each stage gate, and stop immediately after `BFE13_ARCH1_TRACK0_RTL_FROZEN`.
