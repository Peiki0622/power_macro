# FTC Phase 1 Event-Order Timing Quantization Correction Plan

## 0. Scope and authority

This plan is the dedicated correction plan required by the Phase 1B failure recorded at commit:

- `737aa130283301f0e0eeaba62791ab6eef8b566e`

It supersedes **only Phase 1A and Phase 1B** of:

- `plans/ftc_synthesizable_startup_calibration_controller_plan.md`

After this correction reaches GO, the parent controller plan resumes at Phase 2 and MUST consume the corrected Phase 1 timing handoff produced here.

The previous failed Phase 1 candidate is immutable evidence. Do not delete, overwrite, rename away, or reinterpret its results.

## 0.1 What the previous NO-GO actually proved

The first cycle-quantized candidate used this local probe ordering:

```text
reset release
  -> S_CLK rise
  -> S_CLK fall
  -> Q sample 1
  -> Q sample 2
  -> reset assert
```

At 0.95 V this created a return-activity window between S_CLK fall and reset assertion. HSPICE measured a second `dff_ck` rising edge before reset was reasserted, so the candidate correctly failed the active-edge-integrity gate.

The failure does **not** prove that:

- the calibration algorithm is invalid;
- the controller architecture is invalid;
- 1 GHz is intrinsically impossible;
- the medium/fine sensor architecture is invalid.

It proves only that the first integer-cycle schedule violated an event ordering already present in the accepted exact-path timing.

## 0.2 Immutable failed-candidate evidence

Preserve as read-only at minimum:

```text
delay_chain/ftc/controller/analysis/cycle_protocol/
delay_chain/ftc/controller/reports/FTC_CYCLE_QUANTIZATION_NO_GO.md
```

The old 0.80 V GO and 0.95 V NO-GO remain historical evidence for the rejected v1 timing candidate. They are not reusable as v2 acceptance results.

---

# Phase 1R0 — Freeze the accepted exact-path event ordering

## Goal

Derive the synchronous timing problem from the already accepted exact-path schedules instead of independently rounding unrelated physical durations.

## Inputs

Read and cross-check at minimum:

```text
delay_chain/ftc/analysis/reachable_path_acceptance/exact_hspice/exact_path_0p80/operation_schedule.json
delay_chain/ftc/analysis/reachable_path_acceptance/exact_hspice/exact_path_0p95/operation_schedule.json
delay_chain/ftc/analysis/reachable_path_acceptance/exact_hspice/exact_path_1p10/operation_schedule.json
delay_chain/ftc/analysis/reachable_path_acceptance/exact_hspice/final_acceptance.json
delay_chain/ftc/scripts/run_exact_reachable_path_hspice.py
```

Also read the rejected v1 timing evidence only to record the failure mechanism:

```text
delay_chain/ftc/controller/analysis/cycle_protocol/hspice/summary.json
delay_chain/ftc/controller/reports/FTC_CYCLE_QUANTIZATION_NO_GO.md
```

## Required canonical probe event order

For every accepted exact-path probe, extract and verify the same strict event precedence:

```text
RESET_RELEASE_COMPLETE
        <
S_CLK_RISE
        <
Q_SAMPLE_1
        <
Q_SAMPLE_2
        <
RESET_ASSERT_START
        <
RESET_ASSERT_COMPLETE
        <
S_CLK_FALL
        <
RECOVERY_DONE
```

Here `<` means the event on the left must occur strictly before the event on the right.

The corrected Phase 1 MUST treat this ordering as the primary contract. No later integer-cycle mapping may invert or collapse these events unless an explicit accepted exact-path equality proves that they may coincide. The current accepted exact-path does not provide such an equality for Q sample 2, reset assertion, and S_CLK fall.

## Minimum physical separations to extract

Do not hard-code them from memory. Derive them from the accepted exact-path schedules and publish the extracted values. The accepted schedules are expected to show approximately:

- reset-release-complete -> S_CLK rise: 0.49 ns;
- S_CLK rise -> Q sample 1: 2.3 ns;
- Q sample 1 -> Q sample 2: 0.2 ns;
- Q sample 2 -> reset-assert-start: 0.2 ns;
- reset-assert-start -> reset-assert-complete: control-edge duration;
- reset-assert-complete -> S_CLK fall: positive margin, approximately 0.29 ns in the accepted deck;
- S_CLK fall -> recovery done: 2.7 ns.

The generated evidence must contain the actual extracted values and source hashes.

## Output

Create a new task-owned area; do not reuse the rejected v1 directory:

```text
delay_chain/ftc/controller/analysis/cycle_protocol_event_order_v2/
├── exact_path_event_order_audit.json
├── exact_path_event_order_audit.csv
└── source_manifest.json
```

## HSPICE budget

- 0

## Exit gate

`Exact-Path Event Order Extraction = GO`

Only if all three accepted voltage schedules agree on the required event ordering and the source hashes are frozen.

---

# Phase 1R1 — Solve the integer-cycle schedule as an ordered difference-constraint problem

## Goal

Choose integer controller cycles only after the exact-path event ordering and minimum adjacent separations are frozen.

## Clock candidate

Keep the same one-shot candidate used by the parent plan:

- `cal_clk = 1 GHz`
- period = 1 ns

Do not sweep clock frequency in this correction plan.

## Quantization rule

The old method is forbidden:

> independently round reset arm, S_CLK high width, Q-read time, sample spacing, and recovery, then combine those rounded values.

The corrected method is:

1. freeze the exact-path event order;
2. freeze the minimum physical separation for every adjacent ordered event pair;
3. convert each adjacent minimum separation to the minimum number of whole 1 ns controller cycles that is not shorter than the physical separation;
4. solve the event cycles cumulatively in event-order sequence;
5. choose the **earliest feasible integer-cycle schedule** satisfying every ordering and minimum-separation constraint;
6. use the same local probe schedule for all three voltages;
7. freeze all three full voltage trajectories before any new HSPICE run.

## Required v2 local probe candidate at 1 GHz

If the extracted accepted separations match the current accepted evidence, the earliest feasible single-edge synchronous candidate is expected to be:

```text
local cycle 0 : RESET_RELEASE_COMPLETE
local cycle 1 : S_CLK_RISE
local cycle 4 : Q_SAMPLE_1
local cycle 5 : Q_SAMPLE_2
local cycle 6 : RESET_ASSERT
local cycle 7 : S_CLK_FALL
local cycle 10: RECOVERY_DONE
```

This table is a candidate derived from the ordered constraints, not an independently tunable list of durations. The generator must derive it from the constraint set and assert that it is the earliest feasible solution; do not merely hard-code the table and declare success.

### Important consequence

The S_CLK-high interval is now **derived** from the ordered schedule. It is not independently forced to three cycles if doing so would place S_CLK fall before reset assertion.

For the expected v2 candidate:

- S_CLK rises at local cycle 1;
- S_CLK falls at local cycle 7;
- therefore the high interval becomes 6 ns.

This extension is allowed as a timing-quantization candidate, but it is not assumed safe. Phase 1R4 HSPICE must prove whether the frozen sensor still behaves correctly with it.

## CONFIG_UPDATE schedule

Keep configuration-update behavior simple and ordered:

```text
update cycle 0:
  sensor reset asserted
  sensor S_CLK low
  exactly one thermometer bit changes

wait until at least cycle 2 before dependent probe reset release
```

The 2-cycle wait is the integer-cycle representation of the accepted >=1.5 ns configuration-settle requirement.

## Structural constraints that must be machine-checked

For every generated probe:

- reset release occurs before S_CLK rise;
- S_CLK rise occurs before Q sample 1;
- Q sample 1 occurs before Q sample 2;
- Q sample 2 occurs before reset assertion;
- reset assertion occurs before S_CLK fall;
- S_CLK fall occurs before recovery completion;
- M/F remain constant for the entire probe;
- there is exactly one **intended controller-generated** S_CLK rising event;
- there are exactly two Q sample events.

For every config update:

- reset is asserted;
- S_CLK is low;
- exactly one M or F thermometer step occurs;
- no probe event occurs during the required settle interval.

For two-step coarse backoff:

- exactly two adjacent single-step M decrements occur;
- zero probe occurs between them.

## Naming discipline

Do not call a zero-HSPICE structural condition `one_ck` or claim it proves physical CK edge integrity.

Use names such as:

- `one_intended_sclk_rise_event`
- `reset_assert_precedes_sclk_fall`
- `two_q_sample_events`

Physical `dff_ck` edge integrity is proven only in HSPICE.

## Outputs

```text
delay_chain/ftc/controller/analysis/cycle_protocol_event_order_v2/
├── ordered_timing_constraints.json
├── cycle_timing_contract_v2.json
├── cycle_path_v2_0p80_contract.json
├── cycle_path_v2_0p95_contract.json
├── cycle_path_v2_1p10_contract.json
└── pre_run_freeze.json
```

## HSPICE budget

- 0

## Exit gate

`Event-Ordered Cycle Schedule Construction = GO`

---

# Phase 1R2 — Add zero-HSPICE regression tests before rendering decks

## Goal

Prevent the exact v1 ordering bug from recurring silently.

## Mandatory tests

Add tests that fail if any generated probe has:

- S_CLK fall before or at reset assertion;
- reset assertion before or at Q sample 2;
- Q sample 2 before or at Q sample 1;
- Q sample 1 before the required launch-to-read interval;
- more or fewer than two Q sample events;
- more or fewer than one intended S_CLK rising event;
- any M/F change during a probe.

Also assert:

- the v1 rejected schedule is recognized as violating `RESET_ASSERT < S_CLK_FALL`;
- the v2 schedule satisfies every ordered constraint;
- all three v2 voltage contracts use the exact same local probe timing template;
- expected high-level operation counts remain 45 / 36 / 36;
- expected final codes remain M7/F6, M4/F6, M2/F9;
- scenario budget is exactly three;
- no HSPICE result is required for the zero-simulation gate.

## HSPICE budget

- 0

## Exit gate

`Event-Ordered Cycle Contract Tests = GO`

---

# Phase 1R3 — Render and freeze all three corrected decks before simulation

## Goal

Generate all corrected HSPICE decks from the same v2 timing template before observing any new result.

## Scenario names

Use new names so rejected v1 evidence is never overwritten:

- `cycle_path_v2_0p80`
- `cycle_path_v2_0p95`
- `cycle_path_v2_1p10`

## Pre-run requirements

Before launching HSPICE:

- render all three decks;
- freeze all three contract hashes;
- freeze all three deck hashes;
- freeze scenario order;
- confirm historical v1 run directories are untouched;
- confirm the generated probe timeline has reset asserted before S_CLK fall;
- confirm no later voltage deck can be regenerated based on an earlier voltage result.

## Output

```text
delay_chain/ftc/controller/analysis/cycle_protocol_event_order_v2/hspice/
├── pre_run_freeze.json
├── cycle_path_v2_0p80/
├── cycle_path_v2_0p95/
└── cycle_path_v2_1p10/
```

## HSPICE budget

- 0 before the pre-run gate is complete.

## Exit gate

`Event-Ordered HSPICE Deck Freeze = GO`

---

# Phase 1R4 — Run exactly three corrected open-loop HSPICE bridge scenarios

## Execution rule

After Phase 1R3 GO, run all three pre-frozen scenarios exactly once:

1. `cycle_path_v2_0p80`
2. `cycle_path_v2_0p95`
3. `cycle_path_v2_1p10`

Do not adapt the v2 timing template, sensor configuration, or later deck after seeing an earlier result.

Unlike the rejected v1 run, complete all three pre-frozen nominal scenarios before publishing the aggregate v2 decision. A failure in one scenario still makes the final gate NO-GO, but the other pre-frozen nominal scenarios should still be run once so the fixed candidate has complete three-voltage evidence. Do not add a fourth diagnostic scenario.

A simulator infrastructure failure may be retried once only if all contract/deck hashes remain unchanged and the retry reason is recorded separately.

## Probe acceptance

For every reachable probe require:

- Q sample 1 and Q sample 2 classify to the same stable rail;
- observed Q classification matches the frozen expected classification;
- exactly one active `dff_ck` rising edge occurs before reset assertion;
- if a second return-induced `dff_ck` rising edge exists, it must occur only after reset assertion and therefore outside the active capture window;
- reset assertion physically precedes S_CLK fall;
- physical recovery passes the frozen functional guard;
- M/F do not change during the probe.

The active-edge condition must be evaluated using measured CK edge times and measured/generated reset-assert timing, not from the controller event list alone.

## Config-update acceptance

For every reachable configuration update require:

- exactly one thermometer bit changes;
- sensor reset is asserted;
- S_CLK is low;
- no active CK edge/glitch occurs in the configuration quiet window;
- the full 2-cycle settle interval is honored before dependent reset release.

## Expected nominal trajectories

The corrected timing must still reproduce:

- 0.80 V: boundary M9 -> selected M7 -> fine boundary F5 -> lock M7/F6;
- 0.95 V: boundary M6 -> selected M4 -> fine boundary F5 -> lock M4/F6;
- 1.10 V: boundary M4 -> selected M2 -> fine boundary F8 -> lock M2/F9.

## Decision

All three pass:

`Cycle-Quantized Startup Protocol = GO`

Any one fails:

`Cycle-Quantized Startup Protocol = NO-GO`

If NO-GO, report the first real failing mechanism from the complete three-voltage v2 evidence. Do not alter the timing template inside this plan after the first simulation has been launched.

---

# Phase 1R5 — Publish the corrected timing handoff and resume the parent controller plan

Execute only after Phase 1R4 GO.

## Required handoff

Create:

```text
delay_chain/ftc/controller/spec/phase1_timing_handoff.json
```

It must contain at minimum:

- decision = `Cycle-Quantized Startup Protocol = GO`;
- source exact-path acceptance hashes;
- corrected event-order contract hash;
- corrected v2 cycle-timing contract hash;
- `cal_clk_hz = 1000000000`;
- local probe event cycles;
- configuration-settle cycles;
- hashes of all three successful v2 HSPICE decks/results;
- explicit statement that the old `controller/analysis/cycle_protocol/` timing candidate is superseded and must not be consumed by RTL.

## Parent-plan resumption rule

Only after this handoff exists and validates may Codex resume:

- Phase 2 — thermometer configuration registers;
- Phase 3 — operation sequencer and Q sampler;
- later controller phases.

All RTL timing constants MUST be generated from or checked against `phase1_timing_handoff.json`. The rejected v1 `cycle_timing_contract.json` is historical evidence only.

## Final exit gate

`Corrected Phase 1 Timing Handoff = GO`

---

# Explicitly out of scope

This correction plan MUST NOT:

- change medium/fine physical cells;
- change the sensor topology;
- change the real DFF;
- change the paired coarse rule;
- change two-step backoff;
- change fine-boundary semantics;
- change the one-step guard rule;
- change the nominal 1 GHz candidate;
- sweep calibration-clock frequency;
- sweep recovery timing;
- add ConfigSkip;
- start RTL implementation before corrected Phase 1 GO;
- start programmable margin or droop-detection work;
- delete or overwrite the rejected v1 evidence.

# Compact gate sequence

Codex must execute these gates in order:

1. `Exact-Path Event Order Extraction = GO`
2. `Event-Ordered Cycle Schedule Construction = GO`
3. `Event-Ordered Cycle Contract Tests = GO`
4. `Event-Ordered HSPICE Deck Freeze = GO`
5. `Cycle-Quantized Startup Protocol = GO`
6. `Corrected Phase 1 Timing Handoff = GO`

Only then return to Phase 2 of the parent synthesizable-controller plan.
