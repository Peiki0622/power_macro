# FTC SMIC40LL Sequential-Cell Timing Capability and `cal_clk` Re-Frequency Root-Cause Plan

**Repository:** `Peiki0622/power_macro`  
**Target branch:** `main`  
**Baseline commit at plan creation:** `f213a88efbeb39b9360b71088b1c6d5b731caf3f`  
**Purpose:** resolve the current 1 GHz timing-composed closure failure by identifying the exact SMIC40LL sequential-cell timing constraint, deriving a safe calibration clock without blind frequency sweeping, re-quantizing the sensor protocol while preserving its physical event order, and then rebuilding the controller timing evidence through staged digital and mixed-signal closure.

---

# 0. Executive scope and current problem statement

The current failure must not be described loosely as “SMIC40LL cannot run at 1 GHz.”

The evidence currently supports the narrower and technically correct statement:

> The present 1 GHz `cal_clk` cannot pass the current timing-composed configuration consisting of the mapped FTC controller, Phase 7 SDF, enabled standard-cell timing checks, corrected VCS-XA bridge, and frozen transistor-level FTC sensor.

The plan therefore does **not** begin by choosing 500 MHz, 667 MHz, 800 MHz, or any other guessed frequency.

It begins by proving the exact standard-cell timing-check root cause and only permits re-frequency if that root cause is genuinely frequency-related.

The plan must preserve all previously accepted sensor/calibration behavior and may not modify the frozen physical sensor merely to make the digital library easier to satisfy.

---

# 1. Existing accepted evidence that must remain immutable

Codex must read and hash the existing evidence before changing any timing implementation.

## 1.1 Phase 1 timing handoff

Canonical source:

```text
delay_chain/ftc/controller/spec/phase1_timing_handoff.json
```

Current historical timing handoff:

```text
cal_clk              = 1 GHz
Tcal                 = 1 ns
CONFIG_SETTLE        = 2 cycles
RESET_RELEASE        = local cycle 0
S_CLK_RISE           = local cycle 1
Q_SAMPLE_1           = local cycle 4
Q_SAMPLE_2           = local cycle 5
RESET_ASSERT         = local cycle 6
S_CLK_FALL           = local cycle 7
RECOVERY_DONE        = local cycle 10
```

This file remains immutable historical evidence throughout this plan. Do not overwrite it.

## 1.2 Exact physical event order

Canonical source:

```text
delay_chain/ftc/controller/analysis/cycle_protocol_event_order_v2/
  exact_path_event_order_audit.json
```

The accepted physical order is:

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

The accepted adjacent physical separations extracted from the corrected path are approximately:

```text
RESET_RELEASE_COMPLETE -> S_CLK_RISE       0.49 ns
S_CLK_RISE             -> Q_SAMPLE_1       2.30 ns
Q_SAMPLE_1             -> Q_SAMPLE_2       0.20 ns
Q_SAMPLE_2             -> RESET_ASSERT     0.20 ns
RESET_ASSERT duration                       0.01 ns
RESET complete          -> S_CLK_FALL       0.29 ns
S_CLK_FALL              -> RECOVERY_DONE    2.70 ns
```

These physical ordering requirements, not the old integer cycle numbers, are the authoritative constraints for re-quantization.

## 1.3 Existing 1 GHz evidence

The following existing results are frozen historical evidence and must not be deleted or overwritten:

- corrected Phase 1 three-voltage transistor HSPICE GO;
- Phase 6 protocol GO;
- Phase 7 1 GHz synthesis / STA GO;
- Phase 8 SDF GLS GO at the permitted relaxed digital clock;
- corrected Phase 9 1 GHz no-SDF mixed-signal GO;
- final-closure C3 1 GHz + SDF + transistor-sensor NO-GO.

The C3 failure is particularly important root-cause evidence and must remain preserved exactly as generated.

---

# 2. Frozen functional architecture and algorithm

This plan is a timing/root-cause plan. It is not permission to redesign the sensor or calibration algorithm.

The following are frozen and MUST NOT change:

- medium N = 16;
- medium delay/mux architecture;
- fine K = 10;
- fine load architecture;
- sensor tap 29;
- XOR / sensor DFF topology;
- two independent coarse probes per M;
- first M with both probes stable-low = coarse boundary;
- exactly two medium backoff configuration steps;
- no probe between the two backoff steps;
- fine scan rule = stable-high continues;
- first non-high fine result = fine boundary;
- guard = boundary + 1 legal fine step;
- guard stable-low followed by independent hold stable-low;
- Q double sampling;
- direct registered thermometer architecture;
- existing failure semantics;
- nominal final trajectories:
  - 0.80 V -> M7/F6;
  - 0.95 V -> M4/F6;
  - 1.10 V -> M2/F9.

No phase in this plan may alter the sensor cells or calibration semantics to compensate for a controller timing problem.

---

# 3. Task-owned directory

Create a new root-cause/re-frequency directory without overwriting previous closure evidence:

```text
delay_chain/ftc/controller/refrequency/
├── baseline/
│   ├── baseline_manifest.json
│   └── immutable_input_sha256.json
├── root_cause/
│   ├── first_failure_trace.json
│   ├── timing_violation_inventory.json
│   └── REFREQUENCY_ELIGIBILITY.md
├── library_audit/
│   ├── sequential_cell_usage.json
│   ├── sequential_cell_timing_capability.json
│   ├── liberty_vs_verilog_timing_check_audit.json
│   └── allowed_sequential_cell_superset.json
├── clock_selection/
│   ├── cal_clk_hard_limit.json
│   ├── cal_clk_selection.json
│   └── guard_band_policy.json
├── timing_contract/
│   ├── event_order_refrequency_constraints.json
│   ├── cycle_timing_contract_refrequency.json
│   ├── cycle_path_refreq_0p80_contract.json
│   ├── cycle_path_refreq_0p95_contract.json
│   └── cycle_path_refreq_1p10_contract.json
├── hspice/
│   ├── cycle_path_refreq_0p80/
│   ├── cycle_path_refreq_0p95/
│   └── cycle_path_refreq_1p10/
├── handoff/
│   └── phase1_timing_handoff_refrequency.json
├── synthesis/
│   ├── netlist/
│   ├── reports/
│   └── phase_refrequency_synthesis_results.json
├── verification/
│   ├── rtl_behavioral/
│   ├── sdf_behavioral/
│   ├── mixed_signal_no_sdf/
│   └── mixed_signal_sdf/
└── reports/
    ├── REFREQUENCY_STATUS.md
    ├── REFREQUENCY_GATE_STATUS.json
    └── REFREQUENCY_FINAL_REPORT.md
```

The exact subdirectory implementation may adapt to existing repository conventions, but the evidence categories above must remain distinct and reviewable.

---

# 4. RF0 — Re-Frequency Baseline Freeze

## Goal

Freeze every input needed to explain the 1 GHz failure before any timing implementation is changed.

## Simulation budget

```text
HSPICE       = 0
VCS          = 0
XA           = 0
Synthesis    = 0
STA          = 0
```

## Required reads

At minimum consume:

```text
delay_chain/ftc/controller/spec/phase1_timing_handoff.json

delay_chain/ftc/controller/analysis/cycle_protocol_event_order_v2/
  exact_path_event_order_audit.json
  cycle_timing_contract_v2.json
  three accepted HSPICE scenario files

delay_chain/ftc/controller/analysis/phase7/phase7_results.json

delay_chain/ftc/controller/synthesis/netlist/
  ftc_cal_controller_top_synth.v
  ftc_cal_controller_top_synth.sdc
  ftc_cal_controller_top_synth.sdf

delay_chain/ftc/controller/synthesis/reports/
  timing.rpt
  constraints.rpt
  cell_usage.rpt
  q_final_sampling_path.rpt

delay_chain/ftc/controller/analysis/phase8_gate_level/delayed/

delay_chain/ftc/controller/analysis/phase9_autonomous_transistor_level/
  vcs_xa_corrected/

delay_chain/ftc/controller/final_closure/timing_composition/reports/
  SDF_ANNOTATION_PREFLIGHT.json
  timing_composed_0p80_failure.json
  TIMING_COMPOSED_C3_STOP.md
```

Also identify and hash:

- the VCS SMIC40LL Verilog timing model used by C3;
- the Liberty / `.db` timing library used by synthesis/STA;
- tool versions for DC, VCS, XA, and HSPICE.

## Required output

`refrequency/baseline/baseline_manifest.json`

At minimum record:

```json
{
  "historical_cal_clk_hz": 1000000000,
  "historical_clock_period_ns": 1.0,
  "historical_phase7_status": "GO",
  "historical_phase9_status": "GO_NO_SDF",
  "historical_timing_composed_status": "NO-GO",
  "sensor_architecture_frozen": true,
  "calibration_algorithm_frozen": true
}
```

## Exit gate

```text
Re-Frequency Baseline Freeze = GO
```

If any accepted input hash cannot be resolved, STOP and report the mismatch. Do not regenerate old simulations.

---

# 5. RF1 — First-Failure Timing-Check Forensics

## Goal

Identify the exact standard-cell timing check responsible for the earliest C3 corruption.

This phase determines whether re-frequency is even a valid fix.

## Simulation budget

No new simulation is allowed by default.

Use the preserved C3 run/log artifacts and the installed standard-cell timing model.

If raw C3 logs still exist locally, inspect them read-only. If not, use committed failure evidence plus the standard-cell model and clearly mark any limitation.

## Required first-failure trace

Start from:

```text
u_controller.u_fsm.fail_reason_q_reg[2]
```

Trace:

```text
RTL register
-> mapped instance
-> mapped cell type
-> CK/R/SN/D connectivity
-> standard-cell Verilog specify block
-> exact $width/$setup/$hold/$recovery/$removal statement
-> notifier/X propagation
```

The output must identify the exact check, for example:

```text
cell_type         = DFFSRPQ_X1M_A9TR40
check_type        = CK_NEGEDGE_WIDTH
required_value_ps = ...
observed_value_ps = ...
violation_ps      = ...
```

or explicitly identify a reset/set/recovery/removal constraint if that is the true cause.

## Full violation inventory

Create:

`root_cause/timing_violation_inventory.json`

Classify all available violations into:

```text
CK_HIGH_WIDTH
CK_LOW_WIDTH
ASYNC_RESET_WIDTH
ASYNC_SET_WIDTH
SETUP
HOLD
RECOVERY
REMOVAL
OTHER
```

For each class record:

- count;
- first occurrence;
- instance;
- cell;
- pin/check;
- required value if recoverable;
- observed value if recoverable;
- whether the violation caused notifier/X propagation.

## Re-frequency eligibility decision

### Case A — clock pulse width

If the first causal failure is a CK high/low width violation attributable to the 0.5 ns half-period:

```text
Re-Frequency Root Cause Eligibility = GO
```

### Case B — setup

If the failure is a setup constraint that can be improved by increasing `Tcal`:

```text
Re-Frequency Root Cause Eligibility = GO
```

### Case C — asynchronous reset/set width or recovery/removal

Determine whether the violating interval scales with `cal_clk` cycle spacing.

If yes:

```text
Re-Frequency Root Cause Eligibility = GO
```

If no, and the violation instead comes from synthesis structure, combinational glitching, asynchronous-control implementation, or another frequency-independent mechanism:

```text
Re-Frequency Root Cause Eligibility = NO-GO
```

STOP this plan and create a separate controller/mapping root-cause plan.

### Case D — hold-only failure

A pure hold failure must not be “fixed” by lowering clock frequency.

If the first causal failure is hold-only:

```text
Re-Frequency Root Cause Eligibility = NO-GO
```

and a dedicated hold/mapping/physical implementation plan is required.

## Required outputs

```text
root_cause/first_failure_trace.json
root_cause/timing_violation_inventory.json
root_cause/REFREQUENCY_ELIGIBILITY.md
```

## Exit gate

```text
1 GHz Timing-Check Root Cause = GO
```

No frequency may be selected before this gate passes.

---

# 6. RF2 — SMIC40LL Sequential-Cell Timing Capability Audit

## Goal

Derive the timing capability of the actual sequential-cell implementation from the library/model instead of guessing by simulation.

## Simulation budget

```text
Transient simulation = 0
```

Static parsing/reporting is allowed.

## RF2A — actual sequential-cell usage

Parse the existing synthesized netlist and produce:

`library_audit/sequential_cell_usage.json`

For every sequential cell type record:

- cell type;
- instance count;
- representative instances;
- whether used in FSM, Q sampler, thermometer registers, sensor control outputs, fail/status registers, or counters.

Explicitly identify the cells driving:

```text
sense_s_clk
sense_dff_reset
q_sample_1
q_class
FSM state
medium thermometer
fine thermometer
fail_reason
```

## RF2B — timing-check extraction

For every used sequential cell, extract from both:

1. the Liberty/STA model;
2. the Verilog/VCS specify timing model.

Record where available:

```text
minimum CK high width
minimum CK low width
minimum reset width
minimum set width
setup
hold
recovery
removal
conditional timing-check variants
```

Do not assume the Liberty and Verilog timing-check semantics are identical.

## RF2C — Liberty vs VCS model consistency

Create:

`library_audit/liberty_vs_verilog_timing_check_audit.json`

Flag cases where:

- STA has no equivalent constraint but VCS does;
- VCS specify check is stricter than the Liberty-derived interpretation;
- conditional timing checks depend on R/SN/data state;
- units/scales differ;
- the Phase 7 STA evidence did not explicitly close a simulation-visible check.

## RF2D — allowed sequential-cell superset

Re-synthesis may select different FF variants.

Therefore determine the legal sequential-cell family available to the synthesis flow and build:

`library_audit/allowed_sequential_cell_superset.json`

This need not include every unrelated library cell, but it must cover plausible replacements for the current controller's sequential elements.

For each candidate cell, record the relevant minimum width / recovery / removal constraints when available.

## Required output

```text
sequential_cell_usage.json
sequential_cell_timing_capability.json
liberty_vs_verilog_timing_check_audit.json
allowed_sequential_cell_superset.json
```

## Exit gate

```text
SMIC40LL Sequential Timing Capability = GO
```

---

# 7. RF3 — Deterministic Safe `cal_clk` Selection

## Goal

Choose the fastest safe calibration clock using static timing/library constraints and explicit engineering guard band.

Blind frequency sweep is forbidden.

## RF3A — derive the digital hard lower bound on period

Define:

```text
T_hard
```

as the minimum clock period required by all relevant frequency-dependent constraints, including at least:

- worst applicable CK high pulse-width requirement;
- worst applicable CK low pulse-width requirement;
- duty-cycle assumption;
- current/predicted setup requirement;
- frequency-dependent recovery/removal spacing;
- frequency-dependent asynchronous-control spacing.

Hold constraints are checked independently and must not be hidden inside `T_hard` as though slowing the clock fixes them.

For a nominal 50% duty cycle, CK width limits must be converted into a full-period lower bound correctly.

## RF3B — engineering guard band

Default review policy for this plan:

```text
T_guarded = max(
    1.25 * T_hard,
    T_hard + 0.25 ns
)
```

Then round the selected clock period upward to a practical implementation grid:

```text
0.5 ns period grid
```

Examples only:

```text
T_guarded = 1.22 ns -> T_selected = 1.5 ns
T_guarded = 1.67 ns -> T_selected = 2.0 ns
```

These examples are not target frequencies.

If library evidence justifies a different guard-band policy, Codex may propose it in `guard_band_policy.json`, but it must explain why and must not reduce margin merely to preserve 1 GHz.

## RF3C — fastest safe frequency rule

Do not choose the slowest possible clock.

The selected period must be the **smallest practical period that satisfies the guarded digital constraint**, because sensor timing is quantized by this same clock and excessive slowing destroys timing resolution.

The optimization target is therefore:

```text
maximize safe cal_clk frequency
subject to
all guarded digital timing constraints
```

not:

```text
make cal_clk arbitrarily slow
```

## Required outputs

```text
clock_selection/cal_clk_hard_limit.json
clock_selection/guard_band_policy.json
clock_selection/cal_clk_selection.json
```

`cal_clk_selection.json` must include:

```text
old period/frequency
limiting cell
limiting timing check
raw hard limit
selected guard-band rule
selected period
selected frequency
predicted timing margin
```

## Exit gate

```text
Safe Calibration Clock Selection = GO
```

---

# 8. RF4 — Event-Order-Preserving Re-Quantization

## Goal

Generate a new integer-cycle probe schedule from the accepted physical event-order constraints.

The old cycle numbers are not preserved automatically.

## Forbidden shortcut

Do not do either of the following:

```text
new_time = old_cycle * new_Tclk
```

or

```text
keep cycles 0/1/4/5/6/7/10 and only slow the clock
```

The new schedule must be solved from the accepted physical separation constraints.

## Authoritative constraints

Use the exact-path physical order:

```text
RESET_RELEASE_COMPLETE
< S_CLK_RISE
< Q_SAMPLE_1
< Q_SAMPLE_2
< RESET_ASSERT_START
< RESET_ASSERT_COMPLETE
< S_CLK_FALL
< RECOVERY_DONE
```

and the accepted minimum physical separations extracted from the corrected Phase 1 evidence.

## Integer-cycle solver requirements

For selected `Tcal`:

1. preserve strict event order;
2. convert every adjacent physical minimum separation into an integer cycle inequality;
3. solve forward for the earliest feasible cycle placement;
4. minimize total probe duration subject to all constraints;
5. use one common local timing template at 0.80/0.95/1.10 V;
6. explicitly account for registered-controller output delay and D2A edge delay only where the contract requires it;
7. do not insert arbitrary extra cycles without documenting the constraint that requires them.

## Reset / S_CLK fall invariant

The schedule must retain:

```text
Q_SAMPLE_2
< RESET_ASSERT
< S_CLK_FALL
```

and later physical validation must prove:

```text
reset assertion completes
before
S_CLK falling-return activity can create a dangerous active CK event
```

## CONFIG_UPDATE re-quantization

The old `configuration_settle_cycles = 2` must not be retained merely because it was 2 at 1 GHz.

Read the authoritative physical settle requirement and derive the minimum legal integer settle cycles at the new `Tcal`.

Preserve the functional meaning:

- configuration changes while reset asserted and S_CLK low;
- next accepted probe cannot begin until the physical settle requirement is satisfied.

## Required outputs

```text
timing_contract/event_order_refrequency_constraints.json
timing_contract/cycle_timing_contract_refrequency.json
timing_contract/cycle_path_refreq_0p80_contract.json
timing_contract/cycle_path_refreq_0p95_contract.json
timing_contract/cycle_path_refreq_1p10_contract.json
```

## Exit gate

```text
Re-Frequency Event-Ordered Cycle Schedule = GO
```

---

# 9. RF5 — Zero-HSPICE Contract Regression

## Goal

Catch schedule-generation or protocol mistakes before spending transistor simulation time.

## Simulation budget

```text
HSPICE = 0
XA      = 0
```

Pure scripting/behavioral checks are allowed.

## Mandatory checks

For the generated local schedule prove:

```text
RESET_RELEASE < S_CLK_RISE
S_CLK_RISE < Q_SAMPLE_1
Q_SAMPLE_1 < Q_SAMPLE_2
Q_SAMPLE_2 < RESET_ASSERT
RESET_ASSERT < S_CLK_FALL
S_CLK_FALL < RECOVERY_DONE
```

Also prove every converted physical minimum separation is satisfied.

## Protocol checks

Prove statically/behaviorally:

- one intended S_CLK rising event per probe;
- two Q sample events per probe;
- reset asserted during configuration changes;
- S_CLK low during configuration changes;
- exactly one thermometer bit per configuration step;
- no M/F change during an active probe;
- paired coarse probes unchanged;
- exactly two medium backoff updates;
- no probe between backoff updates;
- fine boundary/guard/hold semantics unchanged.

## Expected nominal trajectories remain unchanged

```text
0.80 V : 45 operations, 17 configs, 28 probes, final M7/F6
0.95 V : 36 operations, 14 configs, 22 probes, final M4/F6
1.10 V : 36 operations, 15 configs, 21 probes, final M2/F9
```

Changing the physical clock must not change algorithmic operation counts.

## Important wording rule

This phase may prove:

```text
one_intended_sclk_rise_event = PASS
```

It may not prove:

```text
one_physical_dff_ck_edge = PASS
```

Physical sensor clock integrity belongs to RF6.

## Exit gate

```text
Re-Frequency Cycle Contract Tests = GO
```

---

# 10. RF6 — Three-Voltage Open-Loop Transistor Sensor Validation

## Goal

Determine whether the selected safe digital frequency and newly quantized single-rate schedule remain compatible with the frozen transistor sensor.

This is the critical architectural feasibility gate.

## Pre-run freeze

Before launching HSPICE, freeze all three scenarios at once:

- selected `cal_clk`;
- selected period;
- one common local cycle template;
- config settle cycles;
- full 0.80 V trajectory/deck/hash;
- full 0.95 V trajectory/deck/hash;
- full 1.10 V trajectory/deck/hash;
- expected classifications;
- expected final M/F codes.

Do not tune 0.95/1.10 after seeing 0.80.

## Required scenarios

Run exactly:

```text
cycle_path_refreq_0p80
cycle_path_refreq_0p95
cycle_path_refreq_1p10
```

These are new timing-contract validation scenarios, not reruns of the historical 1 GHz decks.

## Required per-probe checks

### Q classification

```text
Q_SAMPLE_1 == expected rail
Q_SAMPLE_2 == expected rail
sample pair stable
classification == expected
```

### physical active CK integrity

Measure actual sensor `dff_ck`.

Require exactly one active CK rising edge before reset assertion.

If S_CLK falling return creates a later CK transition, that transition must occur only after reset has safely reasserted.

### physical reset ordering

Measure:

```text
reset assertion completion
S_CLK falling return
```

Require reset to complete first with positive margin.

### recovery

Retain the frozen physical recovery requirement and verify it at the new schedule.

### configuration operations

For every config update verify:

- one thermometer bit changes;
- reset asserted;
- S_CLK low;
- no active CK event;
- physical settle time satisfied.

## Aggregate acceptance

All three voltages must preserve:

```text
0.80 V -> M7/F6
0.95 V -> M4/F6
1.10 V -> M2/F9
```

with the same classification sequence and algorithmic operation counts as the historical accepted protocol.

## Critical architectural branch

If the selected digitally safe clock produces a re-quantized schedule that fails the frozen transistor sensor protocol:

**do not continue lowering `cal_clk` and retrying.**

Publish:

```text
Single-Rate Re-Frequency = NO-GO
```

This means the design may have no acceptable overlap between:

```text
SMIC40LL digital minimum-safe period
```

and

```text
sensor timing-resolution / pulse-window requirements
```

The next project must then be a separate architecture plan such as:

```text
slow controller FSM clock
+
fine sensor timing sequencer
```

That architecture is explicitly out of scope here.

## Exit gate

```text
Re-Frequency Transistor Sensor Protocol = GO
```

---

# 11. RF7 — New Controller Timing Handoff

## Goal

Only after the new schedule is proven by RF6, make it consumable by RTL.

## Historical file rule

Do not overwrite:

```text
delay_chain/ftc/controller/spec/phase1_timing_handoff.json
```

Create:

```text
refrequency/handoff/phase1_timing_handoff_refrequency.json
```

## Required handoff contents

At minimum:

```text
new cal_clk_hz
new Tcal
new configuration settle cycles
new local event cycle positions
source exact-event-order hashes
three RF6 HSPICE scenario hashes
three RF6 acceptance hashes
old 1 GHz handoff reference
supersession status
```

Explicitly state:

```text
historical 1 GHz handoff = retained evidence
new refrequency handoff = active controller timing source
```

## RTL modifications allowed

Only timing implementation may change, including:

- operation-sequencer event constants;
- timing counters/terminal values;
- config-settle counters;
- clock parameter/constraint consumption;
- comments/documentation tied to active timing source.

## RTL modifications forbidden

Do not alter:

- search algorithm;
- paired probes;
- backoff depth;
- fine boundary/guard/hold semantics;
- thermometer update semantics;
- Q classification semantics;
- M/F legal ranges;
- nominal final codes.

## Drift prevention

Prefer one of:

1. generate timing constants from the JSON handoff; or
2. add a machine audit that proves RTL constants exactly match the handoff.

Do not permit another manual timing-contract drift.

## Exit gate

```text
Re-Frequency Controller Timing Handoff = GO
```

---

# 12. RF8 — Re-Synthesis and Static Timing Closure

## Goal

Rebuild the controller against the selected safe `cal_clk` and produce an independent mapped baseline.

## Output isolation

Do not overwrite historical Phase 7 artifacts.

Use a dedicated output tree, for example:

```text
refrequency/synthesis/netlist/
refrequency/synthesis/reports/
```

## Required synthesis/static checks

Re-run synthesis and static timing for the new target and audit:

```text
setup
hold
clock pulse-width capability
recovery/removal
async reset/set timing constraints
fanout
transition
q_final sampling path
registered sense_s_clk
registered sense_dff_reset
thermometer output registers
unmapped/black-box logic
```

## Positive-margin requirement

Do not accept another result that merely reports:

```text
worst setup slack = 0.000 ns
```

The new report must explicitly quantify positive engineering headroom for:

- setup;
- clock pulse width;
- relevant async-control timing;
- q_final sampling path.

The margins must be consistent with the RF3 guard-band policy.

## New mapping audit

Extract the new sequential-cell set after synthesis.

If the new mapping introduces a cell whose timing constraints were not covered in RF2, or a cell whose requirement exceeds the selected guarded period:

```text
STOP
return to RF2/RF3
```

Do not enter dynamic timing validation.

## Required output

`refrequency/synthesis/phase_refrequency_synthesis_results.json`

## Exit gate

```text
Re-Frequency Synthesized Controller = GO
```

---

# 13. RF9 — Staged Dynamic Timing Validation

The expensive timing-composed XA run is the last step, not the first.

---

## RF9A — RTL / behavioral-sensor regression

### Goal

Verify that new timing constants did not alter algorithmic behavior.

### Required scenarios

Run the nominal behavioral scenarios and verify:

```text
0.80 V -> 45 / 17 / 28 -> M7/F6
0.95 V -> 36 / 14 / 22 -> M4/F6
1.10 V -> 36 / 15 / 21 -> M2/F9
```

Also run the already-required protocol/negative checks affected by timing-counter changes.

Do not create new algorithmic tests unrelated to timing.

### Gate

```text
Re-Frequency RTL Behavior = GO
```

---

## RF9B — Mapped Controller + SDF + Behavioral Sensor

### Goal

Prove the new clock is digitally safe before invoking transistor mixed-signal simulation.

### Required configuration

```text
new mapped controller
+ new SDF
+ selected cal_clk
+ behavioral sensor
+ full timing checks
```

Do not use:

```text
+nospecify
+notimingcheck
```

### Required acceptance

For all three nominal trajectories:

- no causal standard-cell timing violation;
- no notifier corruption;
- no unexpected X propagation;
- exact operation counts;
- exact final M/F;
- no protocol violation.

If `$width`, setup, recovery/removal, or similar timing failures remain:

```text
Target-Frequency Digital SDF Closure = NO-GO
```

STOP before XA.

### Gate

```text
Target-Frequency Digital SDF Closure = GO
```

---

## RF9C — Mapped Controller + Transistor Sensor, No SDF

### Goal

Confirm the re-quantized autonomous timing works through the corrected mixed-signal bridge before adding gate delay.

### Configuration

```text
selected cal_clk
+ refrequency mapped controller logic
+ corrected XA bridge
+ frozen transistor sensor
+ no SDF delay
```

This is new evidence because the timing handoff and controller cycle schedule have changed.

### Required nominal results

All three voltages must preserve the frozen trajectories and final codes.

### Gate

```text
Re-Frequency Autonomous Mixed-Signal Function = GO
```

---

## RF9D — Mapped Controller + SDF + Transistor Sensor

### Goal

Close the exact composition that failed at 1 GHz.

### Configuration

```text
selected safe cal_clk
+ refrequency mapped controller
+ refrequency SDF
+ full standard-cell timing checks
+ corrected XA bridge
+ frozen transistor sensor
+ real q_final feedback
```

### Required acceptance

For all three nominal voltages prove:

- zero causal standard-cell timing violations;
- no notifier-driven X propagation;
- autonomous calibration completes;
- exact operation/config/probe counts;
- one active sensor CK edge per probe;
- Q sample pair/classification correct;
- reset/S_CLK physical ordering remains safe;
- M/F final code correct;
- `cal_done = 1`;
- `lock_valid = 1`;
- `cal_fail = 0`;
- M/F frozen after lock.

### Final dynamic gate

```text
Re-Frequency Timing-Composed Startup Calibration = GO
```

If any nominal scenario fails, STOP. Do not retune the bridge or sensor per voltage.

---

# 14. RF10 — Supersession and Final Re-Frequency Handoff

## Goal

Publish a clean project truth after the new timing implementation is accepted.

## Required status model

After successful RF9D:

```text
Historical 1 GHz Phase 1 timing handoff
  = retained historical evidence
  = superseded for active RTL timing consumption

Historical 1 GHz Phase 7 synthesis
  = retained historical implementation evidence

Historical 1 GHz C3 timing-composed failure
  = retained root-cause evidence

New refrequency timing handoff
  = ACTIVE

New refrequency synthesis/SDF
  = ACTIVE

New three-voltage timing-composed closure
  = GO
```

## Required reports

Create:

```text
refrequency/reports/REFREQUENCY_STATUS.md
refrequency/reports/REFREQUENCY_GATE_STATUS.json
refrequency/reports/REFREQUENCY_FINAL_REPORT.md
```

The final report must state:

- exact 1 GHz first-failure timing check;
- library timing capability evidence;
- selected safe clock and guard band;
- new integer-cycle schedule;
- three-voltage RF6 transistor result;
- new synthesis margins;
- RF9B SDF digital closure;
- RF9C no-SDF mixed-signal closure;
- RF9D timing-composed mixed-signal closure;
- explicit statement that sensor architecture and calibration algorithm were unchanged.

## Handoff to existing final-closure plan

Only after RF10 GO may the project return to:

```text
plans/ftc_startup_calibration_final_closure_and_freeze_plan.md
```

and resume Phase 10 freeze from the new active timing baseline.

## Exit gate

```text
Re-Frequency Closure Handoff = GO
```

---

# 15. Hard STOP rules

Codex must obey all of the following:

1. RF1 must identify the exact causal timing check before frequency selection.
2. If the root cause is frequency-independent, this plan stops.
3. A hold-only failure cannot be fixed by lowering the clock.
4. Frequency sweep is forbidden as a substitute for library analysis.
5. Do not choose 500/667/800 MHz by intuition.
6. Do not disable timing checks to obtain a pass.
7. Do not use `+nospecify` or `+notimingcheck` in RF9B/RF9D.
8. Do not modify the frozen physical sensor architecture.
9. Do not modify the calibration algorithm.
10. Do not use per-voltage `cal_clk` values.
11. Do not use per-voltage local timing templates.
12. Do not mechanically scale old cycle numbers by the new period.
13. Do not retain old integer cycle positions without re-deriving them.
14. Do not change old Phase 1/7/8/9 evidence in place.
15. Do not rerun historical simulations merely to regenerate reports.
16. Do not continue lowering frequency if RF6 proves the single-rate schedule physically incompatible with the transistor sensor.
17. Do not start a slow-FSM/fine-timing-sequencer architecture inside this plan.
18. Do not start programmable detection-margin work before re-frequency closure and Phase 10 freeze.

---

# 16. Out of scope

This plan does not implement or evaluate:

```text
medium/fine sensor cell replacement
sensor tap relocation
N/K changes
sensor DFF replacement
XOR replacement
ConfigSkip
calibration algorithm redesign
programmable detection margin
voltage-droop injection
fault/glitch detection sweeps
false-positive characterization
PVT sweeps
Monte Carlo
post-layout extraction
CTS/signoff implementation
PLL/DLL
ring oscillator
second controller clock domain
slow-FSM + fine-timing-sequencer architecture
```

If RF6 proves single-rate timing infeasible, the final item becomes the subject of a separate future architecture plan.

---

# 17. Simulation discipline

The plan is deliberately structured to spend expensive simulation only after static evidence is sufficient.

| Gate | HSPICE | VCS | XA | Purpose |
|---|---:|---:|---:|---|
| RF0 | 0 | 0 | 0 | baseline freeze |
| RF1 | 0 normally | 0 normally | 0 normally | forensic analysis of existing failure |
| RF2 | 0 | 0 | 0 | library capability audit |
| RF3 | 0 | 0 | 0 | deterministic clock selection |
| RF4 | 0 | 0 | 0 | schedule generation |
| RF5 | 0 | cheap/script only | 0 | contract checks |
| RF6 | 3 new transistor scenarios | 0 | 0 | sensor timing feasibility |
| RF7 | 0 | 0 | 0 | handoff update |
| RF8 | 0 | 0 | 0 | synthesis/STA |
| RF9A | 0 | behavioral | 0 | RTL timing regression |
| RF9B | 0 | SDF GLS | 0 | digital timing isolation |
| RF9C | 0 | mixed-signal digital side | 3 nominal XA scenarios | no-SDF autonomous closure |
| RF9D | 0 | SDF mixed-signal | 3 nominal XA scenarios | final timing composition |
| RF10 | 0 | 0 | 0 | reporting/handoff |

Do not launch RF9C/RF9D if any earlier gate is NO-GO.

---

# 18. Codex execution checklist

```text
[ ] RF0 baseline and immutable hashes frozen
[ ] RF1 first violating mapped instance traced to exact timing check
[ ] RF1 timing violation inventory classified
[ ] RF1 re-frequency eligibility proven
[ ] RF2 actual sequential-cell usage extracted
[ ] RF2 Liberty vs Verilog specify timing checks compared
[ ] RF2 plausible sequential-cell superset audited
[ ] RF3 digital hard period derived without frequency sweep
[ ] RF3 guard-band policy applied
[ ] RF3 fastest safe practical cal_clk selected
[ ] RF4 physical event order converted to new integer-cycle schedule
[ ] RF4 config settle cycles re-derived from physical requirement
[ ] RF5 static/behavioral contract checks pass
[ ] RF6 all three new open-loop HSPICE scenarios pass
[ ] RF6 real dff_ck edge integrity proven
[ ] RF6 reset-before-S_CLK-return ordering proven
[ ] RF7 new active timing handoff published without overwriting historical 1 GHz handoff
[ ] RF7 RTL timing constants match new handoff
[ ] RF8 new synthesis/STA has positive timing headroom
[ ] RF8 new mapping remains inside RF2 audited timing envelope
[ ] RF9A RTL/behavioral nominal trajectories pass
[ ] RF9B mapped+SDF+behavioral sensor passes with full timing checks
[ ] RF9C mapped+transistor sensor no-SDF three-voltage autonomous closure passes
[ ] RF9D mapped+SDF+transistor sensor three-voltage timing-composed closure passes
[ ] RF10 new timing baseline marked ACTIVE
[ ] RF10 historical 1 GHz evidence retained as superseded/root-cause evidence
[ ] RF10 existing Phase 10 freeze plan is resumed only after successful handoff
```

---

# 19. Gate summary

```text
RF0  Re-Frequency Baseline Freeze
 ↓
RF1  1 GHz Timing-Check Root Cause
 ↓
RF2  SMIC40LL Sequential Timing Capability
 ↓
RF3  Safe Calibration Clock Selection
 ↓
RF4  Re-Frequency Event-Ordered Cycle Schedule
 ↓
RF5  Re-Frequency Cycle Contract Tests
 ↓
RF6  Re-Frequency Transistor Sensor Protocol
 ↓
RF7  Re-Frequency Controller Timing Handoff
 ↓
RF8  Re-Frequency Synthesized Controller
 ↓
RF9A Re-Frequency RTL Behavior
 ↓
RF9B Target-Frequency Digital SDF Closure
 ↓
RF9C Re-Frequency Autonomous Mixed-Signal Function
 ↓
RF9D Re-Frequency Timing-Composed Startup Calibration
 ↓
RF10 Re-Frequency Closure Handoff
```

Decision flow:

```text
                 1 GHz C3 NO-GO
                        |
                        v
            exact timing-check forensics
                        |
                 frequency-related?
                   /          \
                 NO            YES
                 |              |
                STOP            v
                       SMIC40LL library audit
                                |
                                v
                         derive safe Tcal
                                |
                                v
                    preserve physical event order
                                |
                                v
                    regenerate integer schedule
                                |
                                v
                    3-voltage transistor HSPICE
                         /               \
                       NO                 GO
                       |                   |
        single-rate architecture NO-GO    v
                       |            new timing handoff
                      STOP                 |
                                           v
                                      re-synthesis
                                           |
                                           v
                                    full-timing SDF GLS
                                           |
                                           v
                                  no-SDF XA closed loop
                                           |
                                           v
                                  SDF + XA + transistor
                                           |
                                           v
                                          GO
```

---

# 20. Final intended outcome

The successful result of this plan is not merely “a slower clock passes simulation.”

The required final conclusion is:

> The previously failing 1 GHz timing-composed implementation has been traced to an explicit SMIC40LL sequential-cell timing limitation; a guarded safe `cal_clk` has been derived from library/model constraints rather than trial-and-error; the FTC sensor protocol has been re-quantized from the accepted physical event-order constraints; the frozen sensor and calibration algorithm remain unchanged; and the new mapped controller passes both digital SDF closure and three-voltage SDF + transistor-sensor autonomous mixed-signal closure.

Only then may startup calibration return to the Phase 10 final-freeze path.
