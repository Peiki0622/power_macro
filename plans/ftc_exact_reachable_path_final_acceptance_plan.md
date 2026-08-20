# FTC Exact Reachable-Path Final Acceptance Plan

## 0. Purpose and execution contract

This plan closes the remaining validation gap in the FTC dynamic startup calibration flow. The physical delay architecture is already frozen and must not be reopened in this plan. The only objective here is to turn the currently incomplete reachability reclassification into a true operation-level executable contract, then run exactly three final transistor-level HSPICE scenarios corresponding to the three nominal supply voltages.

Baseline commit for this plan:

- `0e8dcd6fe296ec3828a27ec99230d1b55f4a46d2`
- commit message: `完成FTC可达路径验收语义重分类`

The current baseline already established the following directionally correct facts:

- reachable-path semantic replay is structurally viable;
- the historical 0.80 V recovery failures belong to counterfactual pre-rendered branches rather than the actually selected control trajectory;
- the recovered functional guard is 2.7 ns;
- the formal exact-path HSPICE decision is still `PENDING_HSPICE`;
- zero new exact-path HSPICE scenarios have been executed so far.

This plan MUST NOT alter the following frozen design choices:

- medium path-selection stage architecture;
- medium delay cell / mux selection;
- fine standard-cell load architecture;
- fine driver/load cell selection;
- real-DFF choice;
- sensor tap / XOR / DFF topology;
- two-probe coarse decision rule;
- two-step coarse backoff;
- one-step fine guard;
- 1.5 ns configuration-settle interval;
- 10 ps configuration-control edge;
- 0.49 ns reset-to-S_CLK launch separation unless an existing helper requires the already frozen value;
- 2.7 ns reachable functional recovery guard;
- the three target voltages: 0.80 V, 0.95 V, 1.10 V.

If any formal exact reachable-path HSPICE scenario fails, this plan ends in `NO-GO`. Do not tune the recovery guard, DFF, backoff depth, fine-stage range, medium-stage structure, or cell choices inside this plan. A new targeted root-cause plan must be created from the first real reachable failure.

---

## 1. Current blocker that this plan must eliminate

The repository is not blocked on delay-cell design. It is blocked on final validation infrastructure.

The current `run_reachable_path_acceptance.py` and generated artifacts are not yet a formal executable acceptance engine because:

1. transition reachability is inferred from legacy `transition_type` labels instead of from the replayed control-state machine;
2. reachable configuration-update failures are not included in the formal failure aggregation;
3. several published GO/count fields are hard-coded rather than derived from structured evidence;
4. the recovery audit publishes an incorrect 0.80 V reachable-probe count (`71` instead of the per-voltage count `28`);
5. current `exact_path_*_contract.json` files are compare-code sequences, not complete operation timelines;
6. coarse increments and fine increments are not explicitly represented as independent configuration-update operations;
7. the current test suite encodes the incomplete model by expecting only the two coarse-backoff updates;
8. no exact reachable-path HSPICE runner or exact-path result set exists yet.

The plan therefore has two strict halves:

- **Half A: zero-HSPICE repair of semantics, operation contracts, audits, and tests.**
- **Half B: exactly three new HSPICE executions after Half A is completely frozen.**

No HSPICE run is allowed before Half A is complete.

---

## 2. Frozen protocol semantics

Codex must implement and validate exactly this controller behavior.

### 2.1 Coarse search

For medium code `M` starting from `M0`:

1. perform probe A at the current `M`;
2. perform probe B independently at the same `M`;
3. if both probe results are stable-low, declare this `M` the coarse boundary and stop the upward scan;
4. otherwise increment `M` by exactly one thermometer bit and wait the full configuration-settle interval before the next pair of probes.

### 2.2 Coarse backoff

After detecting the coarse boundary:

1. decrement `M` by one thermometer bit;
2. wait the full configuration-settle interval;
3. decrement `M` by one thermometer bit again;
4. wait the full configuration-settle interval;
5. perform no comparison probe between the two backoff updates.

### 2.3 Fine search

At the selected medium base:

1. start from `F0`;
2. perform one comparison probe at each fine code;
3. if the result remains stable-high, increment `F` by exactly one thermometer bit and wait the full configuration-settle interval;
4. the first fine code that is not stable-high is the fine boundary;
5. guard code = fine boundary + 1;
6. update to the guard code by one thermometer bit and wait the full settle interval;
7. perform one guard probe;
8. perform one independent lock-hold repeat at the same guard code;
9. both guard and lock-hold must be stable-low to enter LOCK.

### 2.4 Frozen expected trajectories

The expected logical outcomes are:

- **0.80 V**: coarse boundary `M9` -> selected base `M7` -> fine boundary `F5` -> guard/lock `F6`.
- **0.95 V**: coarse boundary `M6` -> selected base `M4` -> fine boundary `F5` -> guard/lock `F6`.
- **1.10 V**: coarse boundary `M4` -> selected base `M2` -> fine boundary `F8` -> guard/lock `F9`.

These values are acceptance expectations, not tuning knobs.

---

## 3. Phase 0 - Freeze baseline and inputs

### Goal

Make the existing evidence immutable for this task and ensure every later artifact can be traced to the baseline.

### Required actions

1. Record baseline HEAD `0e8dcd6fe296ec3828a27ec99230d1b55f4a46d2` in the new analysis summary.
2. Hash or otherwise fingerprint every baseline CSV/JSON/report that will be consumed.
3. Treat all existing pre-rendered dynamic acceptance data as read-only golden evidence.
4. Do not regenerate historical HSPICE scenarios.
5. Explicitly list the source files reused from:
   - reachable-path acceptance analysis;
   - DFF reset/capture repair analysis;
   - dynamic startup calibration protocol scripts;
   - selected-cell / topology configuration.

### Exit criteria

- all inputs are enumerated and frozen;
- no HSPICE execution has occurred;
- generated artifacts identify the exact baseline commit and evidence fingerprints.

---

## 4. Phase 1 - Replace legacy transition reachability with replay-derived operation reachability

### Goal

Make the control-state replay, not historical labels, the sole source of truth for reachability.

### Required implementation

Refactor `delay_chain/ftc/scripts/run_reachable_path_acceptance.py` so that it first builds an explicit ordered operation list from the frozen protocol state machine.

Each operation must have, at minimum:

- `scenario`;
- `operation_index`;
- `operation_type`;
- `M_before`;
- `M_after`;
- `F_before`;
- `F_after`;
- `probe_kind` if applicable;
- `reachable`;
- `formal_gate`;
- `legacy_evidence_key` if mapped to old evidence;
- `reason`.

Allowed operation classes should be explicit and stable, for example:

- `initial_state`;
- `coarse_probe_a`;
- `coarse_probe_b`;
- `coarse_increment`;
- `coarse_backoff_step_1`;
- `coarse_backoff_step_2`;
- `fine_probe`;
- `fine_increment`;
- `guard_probe`;
- `lock_hold_probe`.

Do not inherit legacy `transition_type` as the reachability decision. Historical rows may only be used as evidence mapped onto an already replayed operation.

### Mandatory 0.80 V reachability assertions

The replay must mark as reachable:

- `M0->M1` through `M8->M9`;
- `M9->M8`;
- `M8->M7`;
- selected-branch fine increments `F0->F1` through `F5->F6` at `M7`.

The replay must mark as unreachable/counterfactual:

- `M9->M10`;
- any transition starting from an unreachable `M10` state, including legacy `M10->M9` evidence;
- fine-branch activity associated with medium bases that the controller never selects;
- all other pre-rendered branches not present in the state-machine replay.

### Mapping rule

Map old electrical evidence to replayed operations by concrete state transition identity, not by legacy label. The key should include enough context to prevent aliasing, at minimum:

`(scenario, M_before, M_after, F_before, F_after, operation class/context)`.

If an old row cannot be uniquely mapped, fail the zero-HSPICE audit rather than guessing.

### Exit criteria

- transition reachability is fully replay-derived;
- every reachable update has a unique mapped electrical evidence row or is explicitly marked as requiring new exact-path HSPICE evidence;
- no unreachable historical branch can contribute to the formal GO/NO-GO decision.

---

## 5. Phase 2 - Build a complete operation-level exact-path contract

### Goal

Replace the current compare-only exact path files with true executable time-ordered contracts.

### Required contract semantics

Every code change must appear as its own `config_update` operation. Probe and configuration updates must be independent operation classes.

For every `config_update`:

- exactly one thermometer bit changes;
- DFF reset is asserted during the configuration update;
- `S_CLK` is held low during the update;
- configuration-control edge is 10 ps;
- the full 1.5 ns settle interval completes before any subsequent probe;
- there is no active capture-clock edge inside the configuration quiet window.

For every comparison probe:

- code remains constant throughout the probe;
- reset is released according to the frozen reset-arm timing contract;
- exactly one intended active CK rising edge is produced;
- Q is sampled twice according to the existing stable-rail acceptance semantics;
- both samples must indicate the same rail;
- the recovery interval is evaluated using the frozen 2.7 ns reachable functional guard.

### Required operation ordering

For each voltage contract:

1. initial state;
2. two coarse probes at each visited medium code;
3. an explicit coarse increment between successive medium codes;
4. after boundary detection, two explicit single-bit backoff updates;
5. zero comparison probes between the two backoff updates;
6. one fine probe at each visited fine code;
7. an explicit fine increment between successive fine codes;
8. one guard probe at the guard code;
9. one lock-hold probe at the same guard code.

### Expected operation counts

The contract generator should assert these totals after explicit update insertion:

- 0.80 V: 28 compare operations + 9 coarse increments + 2 backoff updates + 6 fine increments = **45 total operations**.
- 0.95 V: 22 compare operations + 6 coarse increments + 2 backoff updates + 6 fine increments = **36 total operations**.
- 1.10 V: 21 compare operations + 4 coarse increments + 2 backoff updates + 9 fine increments = **36 total operations**.

These counts are acceptance invariants. If the replay logic changes them, stop and investigate rather than adjusting the expected totals.

### Required output files

Generate refreshed exact-path contracts under a dedicated analysis directory, for example:

- `exact_path_0p80_contract.json`
- `exact_path_0p95_contract.json`
- `exact_path_1p10_contract.json`
- `exact_path_operations.csv`
- `exact_path_contract_summary.json`

The old `probe_index` may be retained only as a reference to golden evidence. It must not define the scheduling identity of the new deck.

### Exit criteria

- every visited M/F code change is explicit;
- no compare operation implicitly changes configuration;
- operation totals match 45/36/36;
- all thermometer transitions are one-bit changes;
- contracts are deterministic and generated before any new HSPICE run.

---

## 6. Phase 3 - Unify formal acceptance gating

### Goal

Make the published decision depend on all real reachable electrical obligations, not only comparison-probe rows.

### Required aggregation

The formal per-voltage failure set must include all reachable failures from:

1. comparison probes;
2. configuration updates / transitions;
3. reset/clock quiet-window checks;
4. CK pulse integrity;
5. Q ambiguity / dual-sample disagreement;
6. recovery-tail checks;
7. coarse-boundary correctness;
8. two-step backoff correctness;
9. fine-boundary correctness;
10. guard stability;
11. lock-hold stability;
12. final LOCK-code correctness.

Counterfactual failures must remain visible in a diagnostic section but must never gate the formal reachable-path decision.

### Remove hard-coded publication logic

Eliminate hard-coded values for:

- `reachability_semantics_decision`;
- reachable failure counts;
- counterfactual failure counts;
- per-voltage probe counts;
- recovery-audit counts;
- final GO/NO-GO.

All published values must be derived from structured replay/audit records.

### Fix recovery count bug

The 0.80 V recovery audit must publish its own reachable probe count, expected to be 28, not the aggregate 71 across all three voltages.

### Decision model

Before new HSPICE:

- `reachability_semantics_decision` may be `GO` only if replay/audit consistency tests pass;
- `formal_exact_path_decision` must remain `PENDING_HSPICE`;
- `final_dynamic_protocol_decision` must remain `PENDING_HSPICE`.

After new HSPICE:

- all three exact scenarios must pass for `formal_exact_path_decision = GO`;
- only then may `final_dynamic_protocol_decision = GO`.

### Exit criteria

- every formal decision is computed, not hard-coded;
- probe and configuration-update failures are gated together;
- report, CSV, and JSON counts are internally consistent.

---

## 7. Phase 4 - Strengthen zero-HSPICE tests

### Goal

Make it impossible for the previous incomplete model to regress silently.

### Required tests

Update or replace `delay_chain/ftc/tests/test_reachable_path_acceptance.py` with assertions covering at least:

1. no medium-code jump between adjacent probe states without an explicit configuration update;
2. no fine-code jump without an explicit configuration update;
3. exactly two coarse-backoff updates after boundary detection;
4. both backoff updates are one-bit thermometer transitions;
5. zero comparison probes occur between backoff step 1 and step 2;
6. selected fine increments are reachable and formal-gating operations;
7. `M9->M10` is unreachable at 0.80 V;
8. legacy `M10->M9` evidence is not formal reachable evidence;
9. counterfactual branches cannot gate formal acceptance;
10. every real reachable transition does gate formal acceptance;
11. all reachable config updates satisfy one-bit coding;
12. per-voltage compare counts remain 28/22/21;
13. total operation counts are 45/36/36;
14. recovery per-voltage counts are correct;
15. report values equal the JSON source-of-truth values;
16. no GO field is assigned by literal hard-coded publication code when it should be derived;
17. exact-path HSPICE scenario budget is at most 3;
18. no historical scenario is scheduled for rerun;
19. all three exact contracts are generated before any simulator invocation;
20. contracts for later voltages are not mutated based on earlier HSPICE outcomes.

### Zero-HSPICE gate

At the end of this phase, run only Python/unit/contract tests. Do not launch HSPICE.

If any zero-HSPICE test fails, stop here. Do not proceed to simulator execution.

### Exit criteria

- all zero-HSPICE tests pass;
- generated operation contracts are frozen;
- scenario count remains zero.

---

## 8. Phase 5 - Implement the exact-path HSPICE runner by reusing frozen physical helpers

### Goal

Create the minimum new runner needed to execute the exact operation contracts without rebuilding the physical sensor or delay line.

### Reuse requirements

Reuse the proven physical/deck/measurement helpers from:

- `delay_chain/ftc/scripts/run_dynamic_startup_calibration_protocol.py`

and, where appropriate, the repaired timing constants/logic from:

- `delay_chain/ftc/scripts/run_dff_reset_capture_repair.py`.

Do not duplicate or redesign the transistor-level topology.

### Required architectural change

The old scheduler binds code changes too closely to probes. The new runner must schedule an explicit sequence of operation objects.

Implement separate scheduling paths for:

- `config_update`;
- `compare_probe`;
- `guard_probe`;
- `lock_hold_probe`.

Each operation must have its own start/end timestamps and must be checkable independently.

### Frozen timing requirements

At minimum preserve:

- configuration edge: 10 ps;
- configuration settle: 1.5 ns;
- reset-to-S_CLK launch separation: frozen existing value, nominally 0.49 ns;
- S_CLK edge: existing 1 ps contract;
- Q-read offsets: inherited from the proven dynamic protocol helper;
- reachable functional recovery guard: 2.7 ns.

Do not sweep the recovery guard. Do not substitute the older 2.8 ns full-diagnostic-space value into the functional exact-path runner.

### Required runner outputs

Create machine-readable outputs for each scenario, for example:

- exact operation schedule;
- deck path and hash;
- simulator invocation metadata;
- per-operation transition audit;
- per-probe Q measurements;
- CK-edge audit;
- recovery audit;
- final scenario acceptance JSON.

### Exit criteria

- runner can render all three decks without invoking HSPICE;
- rendered decks correspond exactly to the frozen contracts;
- contract hashes are recorded;
- no scenario has yet been simulated.

---

## 9. Phase 6 - Pre-run freeze and three-scenario budget lock

### Goal

Prevent adaptive tuning or cross-scenario contamination.

### Required actions

Before the first HSPICE launch:

1. generate all three exact contracts;
2. render all three exact decks;
3. hash all three contracts and all three decks;
4. record all frozen acceptance expectations;
5. record simulator command lines;
6. assert that exactly three new scenarios are queued:
   - `exact_path_0p80`;
   - `exact_path_0p95`;
   - `exact_path_1p10`;
7. assert that no fourth scenario can be scheduled by the runner;
8. assert that no historical scenario is included;
9. assert that later contracts/decks cannot be regenerated automatically based on earlier result status.

### Exit criteria

- all three decks are frozen before run 1;
- scenario budget = exactly 3;
- acceptance criteria are immutable for the execution phase.

---

## 10. Phase 7 - Run exactly three new HSPICE scenarios

### Execution order

Run exactly once each:

1. `exact_path_0p80`
2. `exact_path_0p95`
3. `exact_path_1p10`

Do not add diagnostic reruns inside this plan.

If a simulator execution itself crashes due to infrastructure rather than circuit behavior, preserve logs and classify it separately. Do not silently rerun until it passes. Any rerun requires an explicit documented infrastructure reason and must not alter the electrical deck or acceptance contract.

### Per-scenario formal checks

Each scenario must prove all of the following:

1. operation sequence matches the frozen contract exactly;
2. every real configuration update changes exactly one thermometer bit;
3. DFF reset is asserted during configuration updates;
4. S_CLK remains low through configuration updates;
5. 1.5 ns settle completes before the next comparison probe;
6. no unintended CK active edge occurs during configuration quiet windows;
7. each comparison probe produces exactly one intended active CK rising edge;
8. expected Q decision matches the replay contract;
9. the two Q samples agree on the same rail;
10. no Q ambiguity is observed;
11. all reachable recovery tails satisfy the 2.7 ns functional guard;
12. coarse boundary equals the frozen expected boundary;
13. exactly two coarse backoff steps occur;
14. no comparison probe exists between those two backoff steps;
15. selected medium base equals the frozen expected base;
16. fine boundary equals the frozen expected boundary;
17. guard code equals boundary + 1;
18. guard probe is stable-low;
19. lock-hold repeat is stable-low;
20. final locked `(M,F)` matches the frozen expected code.

Expected final codes:

- 0.80 V -> `(M7,F6)`;
- 0.95 V -> `(M4,F6)`;
- 1.10 V -> `(M2,F9)`.

### Stop rule

If any one of the three scenarios has a genuine reachable electrical failure:

- final result = `NO-GO`;
- preserve all artifacts;
- identify the first failing real reachable operation;
- do not tune anything in this plan;
- do not open a fourth scenario;
- create a follow-up plan focused only on that first real failure.

---

## 11. Phase 8 - Publish final acceptance artifacts

### If all three scenarios pass

Publish:

- `Exact Reachable-Path Dynamic Startup Calibration = GO`
- `Dynamic Startup Calibration Protocol = GO`

The final report must explicitly distinguish:

- historical counterfactual failures;
- zero-HSPICE reachability reclassification;
- new exact-path HSPICE evidence;
- per-voltage operation counts;
- per-voltage probe counts;
- per-voltage configuration-update counts;
- per-voltage recovery results;
- final locked codes.

### If any scenario fails

Publish:

- `Exact Reachable-Path Dynamic Startup Calibration = NO-GO`
- `Dynamic Startup Calibration Protocol = NO-GO`

The report must identify the first failing reachable operation and must explicitly state that no tuning was performed after observing the failure.

### Required artifact consistency checks

Before commit:

- JSON is the source of truth;
- CSV counts equal JSON counts;
- Markdown report values equal JSON values;
- exact contract hashes match simulated deck metadata;
- scenario count equals 3 if all executions completed;
- no historical rerun is present;
- no hard-coded GO can override a failed audit.

---

## 12. Codex implementation discipline

Codex must proceed in small reviewable commits or checkpoints and stop at each gate.

Recommended progression:

1. `phase0-freeze-inputs`
2. `phase1-replay-derived-operations`
3. `phase2-full-operation-contracts`
4. `phase3-unified-formal-gating`
5. `phase4-zero-hspice-tests`
6. `phase5-exact-path-runner-render-only`
7. `phase6-freeze-three-decks`
8. `phase7-run-three-hspice`
9. `phase8-publish-final-decision`

At each phase:

- run the narrowest relevant tests first;
- do not touch unrelated repository areas;
- preserve baseline evidence;
- do not change frozen physical constants;
- record generated artifact paths in the phase summary;
- record whether HSPICE count changed;
- if a gate fails, stop instead of repairing by changing architecture.

---

## 13. Explicit non-goals

This plan does NOT include:

- new medium/fine cell searches;
- changing medium N;
- changing fine K;
- redesigning path-selection topology;
- introducing ConfigSkip/bypass/config-skip architecture;
- changing DFF type;
- changing XOR topology;
- changing sensor tap;
- changing two-step backoff depth;
- changing one-step fine guard;
- recovery-guard sweep;
- PVT sweep;
- post-layout extraction;
- programmable detection margin;
- droop-detection functional deployment;
- production FSM RTL/standard-cell implementation.

Those belong to later project stages only after this dynamic startup calibration protocol receives formal GO.

---

## 14. Project roadmap after this plan

Only after this plan reaches final GO should the project continue in this order:

1. **Real startup calibration control implementation**
   - implement the actual finite-state machine, counters/registers, thermometer-code update logic, reset/clock sequencing, guard/lock control.
2. **Full real-circuit startup calibration validation**
   - testbench provides only power/reset/base stimulus;
   - the real control circuit must autonomously search M/F and converge to LOCK;
   - validate transistor-level interaction between control logic and sensor macro.
3. **Programmable detection margin**
   - introduce controlled offset/margin around the calibrated lock point.
4. **Voltage-droop detection behavior**
   - verify target droop amplitudes/durations and false-positive behavior.
5. **PVT, extracted/post-layout, and macro finalization**.

Do not move programmable-margin work ahead of the real startup-control implementation and its full circuit-level validation.

---

## 15. Definition of done

This plan is complete only when one of the following two terminal states is reached.

### Terminal state A - GO

- zero-HSPICE semantic/contract/tests all pass;
- operation contracts are explicit and counts are 45/36/36;
- exactly three new HSPICE scenarios are executed;
- all three pass every reachable electrical and protocol check;
- final dynamic startup calibration decision is published as GO;
- no frozen architecture/timing parameter was tuned after observing simulator results.

### Terminal state B - NO-GO

- zero-HSPICE gate fails, or at least one exact-path HSPICE scenario has a genuine reachable failure;
- the first failing operation is identified and preserved;
- no fourth scenario is added;
- no architecture/guard/backoff/DFF/fine-stage tuning is performed inside this plan;
- final decision is published as NO-GO and a separate targeted follow-up plan is required.
