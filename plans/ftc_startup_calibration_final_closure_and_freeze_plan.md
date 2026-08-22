# FTC Startup Calibration Final Closure and Freeze Plan

**Repository:** `Peiki0622/power_macro`  
**Target branch:** `main`  
**Baseline commit at plan creation:** `eeaf5d6e8cff814c6c47c3c2257dded38f26d171`  
**Purpose:** close the remaining evidence and timing-composition gaps after corrected Phase 9 GO, then freeze the startup-calibration subsystem before any programmable-detection-margin work begins.

---

# 0. Executive rule: do not rerun work that is already complete

This plan is intentionally a **closure plan**, not a new calibration-development plan.

The following completed simulations/flows are frozen evidence and MUST NOT be rerun merely to regenerate reports, logs, hashes, screenshots, or cleaner documentation:

- corrected Phase 1 event-ordered HSPICE scenarios;
- Phase 2/3 RTL block/unit verification;
- Phase 4/5 nominal controller regressions;
- Phase 6 protocol assertions and eight negative scenarios;
- Phase 7 synthesis / STA / report generation;
- Phase 8 functional GLS;
- Phase 8 SDF-delayed GLS;
- corrected Phase 9 R1 1 GHz digital diagnostic;
- corrected Phase 9 R3/R4 bridge-equivalence diagnostic;
- corrected Phase 9 autonomous 0.80 V mixed-signal run;
- corrected Phase 9 autonomous 0.95 V mixed-signal run;
- corrected Phase 9 autonomous 1.10 V mixed-signal run.

## 0.1 Evidence-reuse policy

For every completed phase, Codex must use this priority order:

1. read committed machine-readable evidence;
2. read committed reports/source/hashes;
3. if the original local raw run directory still exists, perform **read-only extraction** from it;
4. if the raw artifact no longer exists, record that limitation explicitly;
5. **never rerun the completed simulation solely to recreate missing evidence.**

A missing old log is an evidence-retention limitation, not permission to spend simulation time reproducing an already accepted scenario.

## 0.2 Only new simulation allowed by this plan

The only new dynamic simulation class authorized here is the previously unperformed composition:

```text
1 GHz external cal_clk
+ synthesized controller
+ controller gate delays from Phase 7 SDF
+ corrected VCS-XA bridge
+ frozen transistor-level FTC sensor
+ real q_final feedback
```

This is not a rerun of Phase 8 or Phase 9 because neither existing evidence layer contains this full timing composition.

No PVT sweep, frequency sweep, recovery sweep, droop injection, programmable margin, layout extraction, or new sensor tuning is allowed in this plan.

---

# 1. Frozen facts that this plan must preserve

The current project baseline contains the following accepted results.

## 1.1 Phase 1 corrected timing handoff

Canonical source:

```text
delay_chain/ftc/controller/spec/phase1_timing_handoff.json
```

The controller timing contract remains:

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

Do not change these constants in this plan.

## 1.2 Phase 6 current machine result

Canonical source:

```text
delay_chain/ftc/controller/analysis/phase6/phase6_results.json
```

Current result is:

```text
RTL Protocol Safety = GO
```

It contains the eight required negative scenarios and the mandatory protocol assertion classes. Do not rerun Phase 6.

## 1.3 Phase 7 current machine result

Canonical source:

```text
delay_chain/ftc/controller/analysis/phase7/phase7_results.json
```

Current result is:

```text
Synthesized Calibration Controller = GO
```

The current result records:

- 1.0 ns clock target;
- no negative setup/hold slack in the accepted report;
- generated mapped netlist;
- SDC;
- SDF;
- q_final sampling-path checks;
- registered `sense_s_clk` and `sense_dff_reset`;
- no mapped black-box/unmapped-logic issue.

Do not resynthesize and do not rerun STA unless this plan detects a hash mismatch proving that the accepted netlist/report set no longer corresponds to current RTL.

## 1.4 Phase 8 current result

Phase 8 already proves mapped-controller functional behavior and SDF-delayed digital protocol behavior.

The 10 ns Phase 8 simulation clock is a **digital GLS relaxation**, not the physical Phase 9 sensor timing contract.

Do not rerun Phase 8.

## 1.5 Corrected Phase 9 current result

Canonical corrected report:

```text
delay_chain/ftc/controller/analysis/phase9_autonomous_transistor_level/
  vcs_xa_corrected/reports/PHASE9_CORRECTED_REPORT.md
```

Current nominal autonomous results are frozen:

| Supply | Coarse boundary | Selected M | Fine boundary | Final | Operations | Configs | Probes |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.80 V | M9 | M7 | F5 | M7/F6 | 45 | 17 | 28 |
| 0.95 V | M6 | M4 | F5 | M4/F6 | 36 | 14 | 22 |
| 1.10 V | M4 | M2 | F8 | M2/F9 | 36 | 15 | 21 |

The historical VCS-XA NO-GO remains immutable superseded evidence. Do not delete or rewrite it.

## 1.6 Important evidence boundary

The corrected Phase 9 autonomous compile currently uses a timing-disabled digital gate model (`+nospecify +notimingcheck`) and does not back-annotate the Phase 7 SDF into the mixed-signal run.

Therefore current evidence is correctly interpreted as:

```text
Phase 7: 1 GHz static timing closure                    GO
Phase 8: mapped/SDF digital protocol behavior           GO
Phase 9: 1 GHz mapped-logic + transistor sensor loop    GO
```

but it does not yet contain one run combining:

```text
1 GHz + SDF controller delay + transistor sensor
```

Closing that single composition gap is the only new simulation objective in this plan.

---

# 2. Final closure directory

Create a task-owned directory:

```text
delay_chain/ftc/controller/final_closure/
├── evidence/
│   ├── phase_gate_reconciliation.json
│   ├── committed_evidence_manifest.json
│   ├── phase9_evidence_retention.json
│   ├── phase9_claim_normalization.json
│   └── optional extracted_existing_run_evidence/
├── timing_composition/
│   ├── inputs/
│   │   ├── baseline_manifest.json
│   │   ├── sdf_composition_contract.json
│   │   └── input_sha256.json
│   ├── src/
│   ├── scripts/
│   ├── diagnostics/
│   ├── runs/
│   └── reports/
└── freeze/
    ├── STARTUP_CALIBRATION_FREEZE.json
    ├── STARTUP_CALIBRATION_FROZEN_FILES.json
    ├── STARTUP_CALIBRATION_EVIDENCE_BOUNDARY.md
    └── FTC_AUTONOMOUS_STARTUP_CALIBRATION_FINAL_ACCEPTANCE.md
```

Raw simulator databases may remain ignored. Compact JSON/Markdown evidence required for review must be committed and must use filenames not accidentally ignored by `.gitignore`.

---

# 3. Gate C0 — reconcile project truth using existing evidence only

## Goal

Remove status contradictions before performing any new simulation.

## Simulation budget

- HSPICE: 0
- VCS: 0
- XA: 0
- synthesis: 0
- STA: 0

## Required reads

Read at minimum:

```text
delay_chain/ftc/controller/reports/FTC_CONTROLLER_GATE_STATUS.json
delay_chain/ftc/controller/analysis/phase6/phase6_results.json
delay_chain/ftc/controller/analysis/phase7/phase7_results.json
delay_chain/ftc/controller/analysis/phase8_gate_level/phase8_results.json
delay_chain/ftc/controller/analysis/phase9_autonomous_transistor_level/vcs_xa_corrected/reports/PHASE9_CORRECTED_REPORT.md
delay_chain/ftc/controller/analysis/phase9_autonomous_transistor_level/vcs_xa_corrected/reports/autonomous_0p80_audit.json
delay_chain/ftc/controller/analysis/phase9_autonomous_transistor_level/vcs_xa_corrected/reports/autonomous_0p95_audit.json
delay_chain/ftc/controller/analysis/phase9_autonomous_transistor_level/vcs_xa_corrected/reports/autonomous_1p10_audit.json
delay_chain/ftc/controller/PROJECT_SUMMARY.md
```

If `phase8_results.json` lives at a slightly different existing path, discover and use that file; do not rerun Phase 8.

## Required reconciliation

The current gate ledger contains stale Phase 6/7 status entries even though their latest machine-readable phase results are GO.

Codex must build:

```text
final_closure/evidence/phase_gate_reconciliation.json
```

For every Phase 0-9 record:

- canonical evidence path;
- evidence SHA256;
- machine-readable status if available;
- current ledger status;
- whether they agree;
- corrected ledger value;
- whether the correction requires simulation (`false` for all C0 entries).

## Update rule

Update `FTC_CONTROLLER_GATE_STATUS.json` only from already-existing accepted evidence.

Do not convert a phase to GO based only on prose if no accepted evidence exists.

Expected corrected high-level state after reconciliation:

```text
Phase 0 = GO
Phase 1 = GO
Phase 2 = GO
Phase 3 = GO
Phase 4 = GO
Phase 5 = GO
Phase 6 = GO
Phase 7 = GO
Phase 8 = GO
Phase 9 = GO
Phase 10 = NOT_STARTED
```

If any canonical evidence disagrees with this expectation, preserve the real status and STOP for review rather than rerunning the phase.

## Project-summary update

Update stale project documentation that still says Phase 9 is pending/infrastructure-ready.

The updated summary must not claim that timing-aware mixed-signal composition is already complete. It should state:

```text
Autonomous Phase 9 mixed-signal function = GO
Final SDF + transistor-sensor composition closure = pending this plan
Phase 10 freeze = pending this plan
```

## Exit gate

`Project Gate Reconciliation = GO`

---

# 4. Gate C1 — close evidence-retention gaps without rerunning any old simulation

## Goal

Make the accepted Phase 9 GO reviewable from the repository as far as possible, while explicitly refusing to rerun old simulations merely to recreate deleted raw files.

## Simulation budget

- all simulation/synthesis tools: 0

## 4.1 Build a committed evidence manifest

Create:

```text
final_closure/evidence/committed_evidence_manifest.json
```

Hash committed files covering:

- Phase 1 timing handoff;
- Phase 6 result;
- Phase 7 result;
- synthesis netlist;
- SDC;
- SDF;
- Phase 8 result/report;
- corrected Phase 9 sensor SPICE;
- corrected Phase 9 wrapper/stub;
- corrected Phase 9 testbench;
- corrected Phase 9 bridge contract;
- corrected Phase 9 interface audit;
- corrected Phase 9 bridge-probe audit;
- three corrected autonomous scenario audits;
- corrected Phase 9 final report.

Do not use the currently ignored names `evidence_sha256.txt` / `input_sha256.txt` as the only permanent manifest. Use committed JSON in `final_closure/evidence/`.

## 4.2 Existing raw-run artifact harvesting

Check whether these already-generated local artifacts still exist for the corrected Phase 9 runs:

```text
controller_events.csv
run.log
compile.log
*_independent_audit.json
XA interface-element report
FSDB / raw XA database
```

### If they exist

Perform read-only extraction only. Generate compact committed evidence such as:

```text
final_closure/evidence/optional_extracted_existing_run_evidence/
  autonomous_0p80_trajectory.json
  autonomous_0p95_trajectory.json
  autonomous_1p10_trajectory.json
```

A compact trajectory should preserve, when recoverable from the existing event stream:

- operation index;
- operation type;
- M/F code;
- probe index;
- S_CLK edge count;
- Q sample 1;
- Q sample 2;
- observed classification if reconstructable without guessing;
- final done/lock/fail state.

### If they do not exist

Do **not** rerun Phase 9.

Record:

```text
raw_artifact_available = false
reconstruction_simulation_performed = false
```

in:

`phase9_evidence_retention.json`.

The already accepted Phase 9 technical decision remains governed by its committed compact evidence; the missing raw artifact becomes an evidence-retention limitation.

## 4.3 Normalize the A2D threshold claim

Current Phase 9 documentation states a normalized 0.30/0.70 VDD `q_final` A2D contract, but the committed simulator configuration does not itself visibly prove that those values were applied by the tool.

Codex must not rerun XA just to recover this information.

Instead:

1. inspect any already-existing generated interface-element report if locally available;
2. if it explicitly proves A2D threshold settings, extract and commit that proof;
3. if it does not, create:

```text
final_closure/evidence/phase9_claim_normalization.json
```

and distinguish:

```text
requested/declared bridge contract
vs.
actually archived simulator-generated proof
```

Update Phase 9 final prose if needed so it does not claim a simulator-applied 0.30/0.70 threshold unless that fact is actually evidenced.

This wording correction does not require rerunning the accepted three scenarios.

## Exit gate

`Existing Evidence Retention Closure = GO`

A missing old raw artifact does not by itself cause NO-GO as long as the limitation is explicitly recorded and no unsupported claim remains.

---

# 5. Gate C2 — freeze the new timing-composition experiment before running it

## Goal

Define the one genuinely new experiment required before final freeze:

```text
1 GHz + mapped controller + Phase 7 SDF + corrected XA bridge + frozen transistor sensor
```

No transient is allowed until this gate passes.

## Simulation budget

- transient simulation: 0
- elaboration/static file inspection: allowed

## Inputs

Use the exact already-accepted artifacts:

```text
controller mapped netlist:
  delay_chain/ftc/controller/synthesis/netlist/ftc_cal_controller_top_synth.v

controller SDF:
  delay_chain/ftc/controller/synthesis/netlist/ftc_cal_controller_top_synth.sdf

controller SDC/reference timing:
  delay_chain/ftc/controller/synthesis/netlist/ftc_cal_controller_top_synth.sdc

corrected Phase 9 sensor:
  existing corrected-flow frozen transistor sensor

corrected Phase 9 bridge:
  vcs_xa_corrected/src/ftc_sensor_ams_stub.sv
  vcs_xa_corrected/src/ftc_sensor_ams_wrapper.sp
  corrected bridge configuration

canonical timing:
  phase1_timing_handoff.json
```

## Hash invariant

Before any new run, freeze all input hashes.

No source/netlist/sensor/SDF tuning is allowed after the first timing-composition transient begins.

## SDF annotation requirement

The new bench must annotate the Phase 7 SDF onto the synthesized controller instance.

Do not use:

```text
+nospecify
+notimingcheck
```

as a way to obtain a pass.

The exact SDF invocation syntax may depend on the installed VCS/XA pair. Codex must use a supported method and prove annotation before transient acceptance.

## Static SDF mapping checks

Before transient simulation, prove:

- SDF design/top matches the synthesized controller instance;
- annotation target hierarchy is correct;
- no fatal/unmatched instance pattern invalidates annotation;
- setup/hold timing checks are enabled unless a tool-specific documented exception is unavoidable;
- `sense_s_clk`, `sense_dff_reset`, thermometer output registers, and q-sampling registers are present in the annotated design;
- Phase 1 external clock period remains exactly 1 ns.

Create:

```text
final_closure/timing_composition/inputs/sdf_composition_contract.json
final_closure/timing_composition/reports/SDF_ANNOTATION_PREFLIGHT.json
```

The preflight must contain annotation statistics/messages sufficient to show that SDF is genuinely active.

## New-scenario minimization policy

Do not rerun all previous three no-SDF Phase 9 cases.

The timing-composition run set is deliberately minimized:

### Mandatory scenario A

```text
timing_composed_0p80
```

Reason:

- longest nominal operation sequence (45 operations);
- largest coarse scan;
- slowest sensor supply among nominal points;
- previously most demanding recovery/settling case;
- exercises coarse, two-step backoff, fine, guard, hold, and final lock.

### Conditional scenario B

```text
timing_composed_1p10
```

Run this only if one of the following is true after static coverage review or after 0.80 V:

- F7/F8/F9 physical thermometer outputs are not exercised by the 0.80 V timing-composed run and per-bit controller SDF delay differences are material;
- 0.80 V timing margins are close enough that the fast-sensor extreme could expose a different reset/S_CLK return-window interaction;
- q_final sampling aperture analysis identifies a fast-supply-specific risk;
- Codex can justify in the pre-run contract that 1.10 V adds a distinct timing-composition coverage class.

Otherwise do **not** run 1.10 V merely for symmetry.

### Explicitly do not rerun 0.95 V

0.95 V is an interior nominal supply already covered by:

- corrected Phase 1 HSPICE;
- Phase 8 controller GLS evidence;
- corrected Phase 9 autonomous mixed-signal evidence.

This final closure plan does not authorize another 0.95 V run unless 0.80/1.10 evidence exposes a specific, documented mechanism unique to the interior point.

## Exit gate

`SDF Mixed-Signal Composition Preflight = GO`

---

# 6. Gate C3 — run only the new 0.80 V timing-composed autonomous closure

## Goal

Prove that controller gate delays do not break the autonomous closed-loop behavior when the transistor sensor is present.

This is the first new transient simulation in the plan.

## External ownership

The testbench may drive only:

- `cal_clk`;
- `ctrl_por_n`;
- `cal_start`;
- scenario analog supply parameter/environment.

It must not directly drive:

- M/F;
- sensor S_CLK;
- sensor reset;
- Q sampling strobes;
- FSM state.

## Required clock

```text
Tcal = 1 ns
```

No relaxed 10 ns clock is allowed.

## Required 0.80 V functional result

The run must autonomously reproduce the already-frozen trajectory:

```text
coarse M0 ... M9
M9 paired-low boundary
M9 -> M8 -> M7 backoff
no probe between the two backoff updates
fine F0 ... F5
F5 first non-high boundary
F6 guard stable-low
F6 independent hold stable-low
lock M7/F6
```

Expected counts remain:

```text
operations = 45
configs    = 17
probes     = 28
S_CLK rises = 28
sample1     = 28
sample2     = 28
```

## Timing-composition audits

In addition to existing Phase 9 checks, record the timing effects that this new experiment exists to prove.

At minimum audit:

1. actual mapped-controller `sense_s_clk` edge time relative to `cal_clk` after SDF delay;
2. actual mapped-controller `sense_dff_reset` release/assert time after SDF delay;
3. actual thermometer output transition times for configuration updates;
4. analog sensor S_CLK crossing time after D2A conversion;
5. analog sensor reset crossing time after D2A conversion;
6. analog `q_final` at sample 1 and sample 2;
7. digital q-sampler register capture results;
8. one active sensor S_CLK rising edge per probe;
9. reset reassertion still precedes dangerous S_CLK-fall return activity;
10. no setup/hold timing-check violation relevant to q sampling, sensor control outputs, or controller state progression;
11. no double trigger / skipped probe / multi-bit config transition;
12. final lock freezes M/F.

## Evidence boundary

This run uses gate-timed digital controller models plus transistor-level sensor. It is **not** equivalent to a transistor-level SPICE implementation of all 516 controller standard cells.

The final report must preserve this distinction.

## Failure rule

If 0.80 V fails:

- preserve the first failing run;
- classify the earliest divergence;
- STOP;
- do not run 1.10 V;
- do not alter the calibration algorithm or sensor architecture inside this plan.

Possible failure classes:

```text
SDF annotation defect
controller output clock-to-Q/timing-check failure
D2A timing interaction
q_final sampling aperture failure
sensor return-edge interaction
verification-instrumentation failure
```

## Exit gate

`1 GHz SDF + Transistor Sensor 0.80 V = GO`

---

# 7. Gate C4 — decide whether the 1.10 V timing-composed run adds new coverage

## Goal

Avoid an unnecessary second expensive mixed-signal run unless it closes a real coverage hole.

## Simulation budget before decision

- 0 additional transient runs

## Required coverage review

After C3, compare:

- per-bit M/F register usage in 0.80 V;
- Phase 7 SDF delays for fine thermometer bits that 0.80 V never toggles;
- Phase 8 SDF evidence for F7/F8/F9;
- corrected Phase 9 1.10 V analog sensor evidence;
- q-sampling and reset/S_CLK timing margins from C3.

Create:

```text
final_closure/timing_composition/reports/EXTREME_VOLTAGE_COVERAGE_DECISION.json
```

with either:

```text
run_1p10 = true
```

plus a concrete distinct-risk reason, or:

```text
run_1p10 = false
```

plus evidence that existing Phase 8 + Phase 9 layers and C3 already cover the missing composition risk.

## If 1.10 V is required

Run exactly one new scenario:

```text
timing_composed_1p10
```

Require the frozen nominal result:

```text
M4 boundary
backoff to M2
F8 boundary
F9 guard/hold
final M2/F9
operations = 36
configs = 15
probes = 21
```

Use exactly the same:

- controller netlist;
- SDF;
- clock;
- bridge parameters;
- sensor netlist;
- audit logic.

Only the analog supply and frozen expected trajectory may change.

## Exit gate

Either:

`1.10 V Additional Timing Composition Not Required = JUSTIFIED`

or:

`1 GHz SDF + Transistor Sensor 1.10 V = GO`

Both are valid closure outcomes if properly evidenced.

---

# 8. Gate C5 — final cross-layer evidence synthesis

## Goal

State exactly what each verification layer proves without overstating any layer.

## Simulation budget

- 0

## Create evidence matrix

Create:

```text
final_closure/freeze/STARTUP_CALIBRATION_EVIDENCE_BOUNDARY.md
```

The matrix must distinguish at least:

### Layer A — corrected Phase 1 transistor HSPICE

Proves:

- frozen sensor electrical behavior under open-loop accepted protocol timing;
- three nominal VDD trajectories;
- physical DFF CK/recovery behavior.

Does not prove synthesized autonomous control.

### Layer B — RTL / assertions

Proves:

- algorithm semantics;
- failure handling;
- one-bit config rules;
- protocol ordering.

Does not prove transistor sensor behavior.

### Layer C — synthesis / STA

Proves:

- mapped standard-cell implementation;
- 1 GHz timing closure under the accepted synthesis corner/model;
- mapped q_final sampling path;
- fanout/registered-control structure.

Does not prove analog sensor behavior.

### Layer D — Phase 8 SDF GLS

Proves:

- gate-delayed digital protocol behavior.

The 10 ns GLS relaxation must be stated explicitly.

### Layer E — corrected Phase 9 no-SDF mixed signal

Proves:

- true transistor sensor + mapped controller logic closed-loop autonomous calibration at 1 GHz;
- three nominal supplies;
- corrected mixed-signal bridge behavior.

Does not include controller SDF delay.

### Layer F — this plan's timing-composed closure

Proves:

- selected nominal extreme(s) with 1 GHz + mapped-controller SDF + transistor sensor in one closed loop.

Does not equal full-transistor controller SPICE or post-layout extraction.

## Exit gate

`Startup Calibration Cross-Layer Evidence = GO`

---

# 9. Gate C6 — execute Phase 10 final freeze

## Goal

Freeze the startup-calibration subsystem so later programmable-detection-margin work cannot silently alter it.

## Simulation budget

- all simulation/synthesis tools: 0

## 9.1 Freeze manifest

Create:

```text
final_closure/freeze/STARTUP_CALIBRATION_FREEZE.json
```

and:

```text
final_closure/freeze/STARTUP_CALIBRATION_FROZEN_FILES.json
```

Freeze SHA256 for at least:

- Phase 1 timing handoff;
- calibration RTL package;
- thermometer registers;
- Q sampler;
- operation sequencer;
- calibration FSM;
- calibration top;
- mapped netlist;
- SDC;
- SDF;
- Phase 6 evidence;
- Phase 7 evidence;
- Phase 8 evidence;
- frozen transistor sensor;
- corrected mixed-signal stub/wrapper/config;
- corrected Phase 9 three-voltage compact audits;
- timing-composition contract and accepted result(s);
- gate ledger;
- final acceptance report.

## 9.2 Frozen semantics

The freeze file must state that the following may not change without a new dedicated change/root-cause plan:

- physical medium/fine sensor architecture;
- N=16 / K=10 logical configuration space;
- direct registered thermometer architecture;
- paired coarse probes;
- two-step backoff;
- fine-boundary rule;
- +1 guard;
- independent hold;
- 1 GHz calibration clock contract;
- event order/cycle constants;
- Q double sampling;
- controller/sensor calibration ownership behavior;
- final nominal trajectories M7/F6, M4/F6, M2/F9.

## 9.3 Final acceptance report

Create the report originally required by the parent plan:

```text
delay_chain/ftc/controller/final_closure/freeze/
  FTC_AUTONOMOUS_STARTUP_CALIBRATION_FINAL_ACCEPTANCE.md
```

It must include:

- corrected final Phase 0-10 gate table;
- explicit no-rerun evidence-reuse policy;
- historical Phase 1 v1 NO-GO disposition;
- historical Phase 9 harness NO-GO disposition;
- corrected Phase 9 three-voltage result;
- timing-composition result from this plan;
- exact evidence boundary;
- frozen file hashes;
- unresolved future-only items.

## 9.4 Gate ledger final state

After successful C6:

```text
Phase 0  = GO
Phase 1  = GO
Phase 2  = GO
Phase 3  = GO
Phase 4  = GO
Phase 5  = GO
Phase 6  = GO
Phase 7  = GO
Phase 8  = GO
Phase 9  = GO
Phase 10 = GO
```

and publish:

```text
Synthesizable Startup Calibration Controller = GO
Real Circuit Autonomous Startup Calibration = GO
Startup Calibration Subsystem Freeze = GO
```

## Exit gate

`Startup Calibration Subsystem Freeze = GO`

---

# 10. What explicitly does NOT start in this plan

After C6, STOP.

Do not implement or simulate any of the following here:

- programmable detection margin;
- detection-mode controller;
- calibration/detection ownership mux;
- voltage-droop waveform injection;
- glitch-detection sweep;
- false-positive characterization;
- ROC-like detection tradeoff;
- PVT sweep;
- Monte Carlo;
- post-layout extraction;
- macro physical integration.

Those belong to the next plan after the startup-calibration freeze is complete.

---

# 11. Codex hard execution sequence

Codex must execute these gates in order:

```text
C0 Project Gate Reconciliation
C1 Existing Evidence Retention Closure
C2 SDF Mixed-Signal Composition Preflight
C3 1 GHz SDF + Transistor Sensor 0.80 V
C4 Extreme-Voltage Coverage Decision
C5 Startup Calibration Cross-Layer Evidence
C6 Startup Calibration Subsystem Freeze
```

Any technical failure at C2/C3/C4 stops the plan.

A documentation/evidence-retention limitation at C1 must be recorded honestly but must not trigger a historical simulation rerun.

---

# 12. Simulation-budget table

| Gate | New simulation allowed? | Rule |
|---|---|---|
| C0 | No | reuse committed evidence only |
| C1 | No | read-only extraction from existing raw artifacts only |
| C2 | No transient | SDF mapping/elaboration/static preflight only |
| C3 | Yes | exactly one new 0.80 V timing-composed autonomous run |
| C4 | Conditional | at most one new 1.10 V timing-composed run if justified |
| C5 | No | evidence synthesis only |
| C6 | No | freeze/report only |

Explicit total new nominal mixed-signal transient budget:

```text
minimum = 1 scenario (0.80 V)
maximum = 2 scenarios (0.80 V + justified 1.10 V)
```

New 0.95 V run budget:

```text
0
```

Historical completed-run rerun budget:

```text
0
```

---

# 13. Forbidden shortcuts

Codex MUST NOT:

- rerun corrected Phase 9 no-SDF 0.80/0.95/1.10 solely for nicer evidence;
- rerun Phase 1 HSPICE solely to regenerate archived values;
- rerun Phase 6 assertions/negative scenarios unless a source hash mismatch proves the source changed;
- resynthesize merely to regenerate reports;
- rerun Phase 8 GLS merely because the project summary is stale;
- change the 1 GHz Phase 1 timing constants;
- change the sensor architecture;
- change the backoff/guard algorithm;
- change M/F final expected trajectories;
- disable timing checks in C3 to force a pass;
- remove SDF annotation in C3 to force a pass;
- tune D2A/A2D per voltage;
- change the sensor netlist between C3 and optional C4;
- treat missing old raw evidence as a reason to regenerate it with simulation;
- claim full-transistor controller validation from gate-timed mixed-signal simulation;
- start detection-margin work before C6 GO.

---

# 14. Final handoff to the next research stage

Only after:

```text
Startup Calibration Subsystem Freeze = GO
```

may the project create the next design plan for:

```text
Calibration -> Detection handoff
        +
Programmable Detection Margin
```

At that point, the startup-calibration subsystem becomes a frozen upstream dependency. The next stage should consume its locked M/F calibration point and interfaces rather than modifying its internal protocol.
