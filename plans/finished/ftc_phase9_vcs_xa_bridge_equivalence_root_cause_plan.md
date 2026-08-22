# FTC Phase 9 VCS-XA Bridge-Equivalence Root-Cause and Recovery Plan

**Repository:** `Peiki0622/power_macro`  
**Baseline branch:** `main`  
**Baseline commit at plan creation:** `47825697efdd0f5119f10fb58e40247e7bc07781`  
**Target subsystem:** `delay_chain/ftc/controller/analysis/phase9_autonomous_transistor_level/`  
**Plan purpose:** diagnose and correct the current Phase 9 mixed-signal NO-GO without reopening the frozen sensor architecture or calibration algorithm, then re-enter autonomous Phase 9 acceptance through a sequence of cheap, auditable gates.

---

## 0. Executive decision and scope

The existing Phase 9 VCS-XA result must remain recorded as a real **mixed-signal harness NO-GO**, but it is **not yet evidence that the frozen transistor-level FTC sensor or the calibration algorithm is physically invalid**.

The current repository establishes the following facts:

1. The corrected Phase 1 timing handoff is a **1 GHz / 1 ns cycle contract**.
2. The synthesizable RTL and Phase 7 synthesis constraints still implement that 1 GHz contract.
3. Phase 8 used a **10 ns clock only as a digital GLS relaxation**.
4. The current Phase 9 VCS-XA testbench reused a **10 ns clock**, thereby multiplying every physical sequencer interval by 10 at the real transistor sensor.
5. The current VCS-XA boundary does not freeze and audit the D2A/A2D electrical contract for sensor supply, S_CLK, reset, thermometer rails, and `q_final`.
6. The current Phase 9 event CSV samples on `posedge cal_clk`; that is insufficient to prove real output-edge counts or post-clock settled gate-level state.
7. The frozen sensor extraction and the Phase 9 copied synthesized controller netlist are not presently identified as the primary defect. The copied controller netlist has the same repository blob as the current synthesis netlist.

Therefore this plan treats the first failed run as a **bridge-equivalence failure until disproved**.

### Mandatory top-level rule

Do **not** rerun the full 8 us autonomous 0.80 V mixed-signal transient first.

The next expensive autonomous run is allowed only after the corrected VCS-XA bridge has independently proven:

- the original 1 GHz physical cycle timing;
- correct analog supply rails;
- explicit and repeatable D2A control levels/slew;
- explicit and repeatable A2D `q_final` interpretation;
- real edge-based digital audit instrumentation;
- short-probe equivalence at the 0.80 V M0/F0 and M9/F0 anchor points.

---

# 1. Non-negotiable frozen design constraints

This recovery plan is **not** permission to retune the FTC sensor or calibration protocol.

The following are frozen and MUST NOT change while executing this plan:

- medium search size / physical path-selection architecture;
- medium delay cell `BUF_X0P7M_A9TL40`;
- medium mux `MXT2_X0P5M_A9TL40`;
- fine driver `BUF_X0P8M_A9TL40`;
- fine load cell `NOR2_X4A_A9TL40`;
- fine K = 10;
- XOR and sense-DFF topology;
- two independent coarse probes per M;
- coarse boundary criterion = both probes `STABLE_LOW`;
- exactly two medium backoff configuration steps;
- zero probe between those two backoff updates;
- fine scan rule = only `STABLE_HIGH` continues;
- first non-high fine result = fine boundary;
- guard code = fine boundary + 1 legal step;
- guard and independent hold must both be `STABLE_LOW`;
- Q double-sampling policy;
- Phase 1 sequencer cycle constants;
- expected nominal final codes:
  - 0.80 V -> M7/F6;
  - 0.95 V -> M4/F6;
  - 1.10 V -> M2/F9.

No plan step may modify the physical sensor merely to make mixed-signal simulation pass.

---

# 2. Frozen reference contracts to consume

Codex must read these files before making any Phase 9 correction:

```text
plans/ftc_synthesizable_startup_calibration_controller_plan.md

delay_chain/ftc/controller/spec/phase1_timing_handoff.json
delay_chain/ftc/controller/rtl/ftc_cal_pkg.sv
delay_chain/ftc/controller/rtl/ftc_operation_sequencer.sv
delay_chain/ftc/controller/rtl/ftc_q_sampler.sv
delay_chain/ftc/controller/rtl/ftc_cal_fsm.sv
delay_chain/ftc/controller/rtl/ftc_cfg_therm_regs.sv

delay_chain/ftc/controller/synthesis/netlist/ftc_cal_controller_top_synth.v
delay_chain/ftc/controller/synthesis/netlist/ftc_cal_controller_top_synth.sdc
delay_chain/ftc/controller/synthesis/netlist/ftc_cal_controller_top_synth.sdf

delay_chain/ftc/controller/analysis/phase8_gate_level/functional/PHASE8A_REPORT.md
delay_chain/ftc/controller/analysis/phase8_gate_level/delayed/PHASE8B_REPORT.md

delay_chain/ftc/controller/analysis/phase9_autonomous_transistor_level/vcs_xa/inputs/ftc_sensor_frozen.sp
delay_chain/ftc/controller/analysis/phase9_autonomous_transistor_level/vcs_xa/inputs/ftc_cal_controller_top_synth.v
delay_chain/ftc/controller/analysis/phase9_autonomous_transistor_level/vcs_xa/src/ftc_sensor_ams_stub.sv
delay_chain/ftc/controller/analysis/phase9_autonomous_transistor_level/vcs_xa/src/ftc_sensor_ams_wrapper.sp
delay_chain/ftc/controller/analysis/phase9_autonomous_transistor_level/vcs_xa/src/tb_ftc_vcs_xa.sv
delay_chain/ftc/controller/analysis/phase9_autonomous_transistor_level/vcs_xa/vcsAD.init
delay_chain/ftc/controller/analysis/phase9_autonomous_transistor_level/vcs_xa/xa.cfg
delay_chain/ftc/controller/analysis/phase9_autonomous_transistor_level/vcs_xa/reports/PHASE9_NO_GO_REPORT.md
delay_chain/ftc/controller/analysis/phase9_autonomous_transistor_level/vcs_xa/reports/autonomous_0p80_audit.json
```

### Canonical Phase 1 timing contract

Codex must mechanically extract these values from `phase1_timing_handoff.json`; do not duplicate them as an independent source of truth in RTL:

```text
cal_clk = 1 GHz
Tcal = 1 ns
CONFIG_SETTLE = 2 cycles
RESET_RELEASE = local cycle 0
S_CLK_RISE = local cycle 1
Q_SAMPLE_1 = local cycle 4
Q_SAMPLE_2 = local cycle 5
RESET_ASSERT = local cycle 6
S_CLK_FALL = local cycle 7
RECOVERY_DONE = local cycle 10
```

### Phase 8 10 ns clock rule

The existing Phase 8 10 ns clock is historical digital verification evidence only. Do not rewrite Phase 8 reports or claim that 10 ns is the physical Phase 9 sensor timing contract.

---

# 3. New corrected-flow directory

Do not overwrite the current `vcs_xa/` tree that produced the NO-GO. It is historical evidence.

Create a sibling corrected flow:

```text
delay_chain/ftc/controller/analysis/phase9_autonomous_transistor_level/
├── vcs_xa/                         # historical NO-GO; preserve
└── vcs_xa_corrected/
    ├── README.md
    ├── inputs/
    │   ├── baseline_manifest.json
    │   ├── bridge_contract.json
    │   ├── expected_trajectories.json
    │   └── input_sha256.txt
    ├── src/
    │   ├── ftc_sensor_ams_stub.sv
    │   ├── ftc_sensor_ams_wrapper.sp
    │   ├── tb_ftc_vcs_xa_1ghz.sv
    │   ├── tb_ftc_vcs_xa_bridge_probe.sv
    │   └── optional helper/connect-module sources if required by the installed tool
    ├── scripts/
    │   ├── freeze_baseline.py
    │   ├── audit_phase1_contract.py
    │   ├── audit_interface_elements.py
    │   ├── audit_digital_events.py
    │   ├── audit_analog_boundary.py
    │   ├── audit_bridge_probe.py
    │   ├── audit_autonomous_run.py
    │   └── run_* scripts required by the local Synopsys environment
    ├── diagnostics/
    │   ├── digital_1ghz/
    │   ├── interface_smoke_0p80/
    │   └── bridge_probe_0p80/
    ├── runs/                       # reproducible raw run products; normally gitignored
    │   ├── autonomous_0p80/
    │   ├── autonomous_0p95/
    │   └── autonomous_1p10/
    └── reports/
        ├── ROOT_CAUSE_BASELINE.json
        ├── DIGITAL_1GHZ_GATE.json
        ├── INTERFACE_ELEMENT_AUDIT.json
        ├── BRIDGE_PROBE_EQUIVALENCE.json
        ├── autonomous_0p80_audit.json
        ├── autonomous_0p95_audit.json
        ├── autonomous_1p10_audit.json
        ├── PHASE9_CORRECTED_REPORT.md
        └── evidence_sha256.txt
```

Raw FSDB/log/database products may remain ignored, but compact machine-readable reports and SHA256 manifests must be committed.

---

# 4. Root-cause hypotheses and decision tree

Treat the following as ordered hypotheses, not as permission to tune multiple things at once.

## H1 — confirmed timing-contract propagation error

The 10 ns Phase 8 simulation-only clock was reused in Phase 9. The sequencer cycle counts stayed unchanged, so transistor-level physical intervals became 10x longer.

**Expected fix class:** Phase 9 harness/testbench only.  
**Forbidden response:** changing RTL cycle constants.

## H2 — mixed-signal D2A power/control contract is not frozen

The current mixed-signal boundary does not provide a repository-visible proof of:

- actual analog sensor VDD/VSS;
- whether supply rails cross a normal D2A resistance map;
- actual analog HIGH/LOW levels seen by S_CLK/reset/M/F;
- D2A rise/fall times;
- D2A output resistance / powernet treatment.

**Expected fix class:** mixed-signal wrapper / interface-element configuration only.

## H3 — A2D `q_final` interpretation is not frozen

The current flow does not commit a clear threshold/hysteresis contract or compare analog `Q_FINAL` against the digital `q_final` seen by the synthesized controller.

**Expected fix class:** A2D interface contract / verification only.

## H4 — current event audit is not edge-accurate

A CSV row sampled on `posedge cal_clk` cannot by itself prove post-clock gate-level output state or count actual `sense_s_clk` edges. `sclk_high_samples` is not an edge count.

**Expected fix class:** verification instrumentation only.

## H5 — tool-version skew may alter interface behavior

The existing NO-GO report uses an older VCS / PrimeSim XA pair than the W-2024.09 VCS used for later digital verification. This is not automatically a defect, but the selected mixed-signal pair and interface-element behavior must be explicitly frozen.

**Expected fix class:** tool-selection documentation or compatible tool invocation only; never circuit tuning.

---

# 5. Gate R0 — freeze the forensic baseline before any modification

## Goal

Create a machine-readable record of exactly what failed and exactly what is being changed later.

## Tasks

1. Confirm current HEAD before execution.
2. Hash these historical Phase 9 inputs:
   - controller netlist snapshot;
   - frozen sensor SPICE;
   - stub;
   - analog wrapper;
   - testbench;
   - `vcsAD.init`;
   - `xa.cfg`;
   - expected trajectories;
   - current NO-GO audit/report.
3. Hash the current canonical synthesis netlist and compare it with the historical Phase 9 copy.
4. Parse `phase1_timing_handoff.json` and record the canonical 1 GHz constants.
5. Record the historical Phase 9 10 ns clock as a mismatch, not as a new contract.
6. Record tool versions actually available in the execution environment:
   - VCS;
   - PrimeSim XA / XA;
   - HSPICE if present;
   - Design Compiler only for provenance, not rerun.
7. Do not run a transient simulation in R0.

## Required output

`vcs_xa_corrected/reports/ROOT_CAUSE_BASELINE.json`

At minimum contain:

```json
{
  "baseline_commit": "...",
  "phase1_cal_clk_hz": 1000000000,
  "historical_phase9_clock_period_ns": 10,
  "timing_contract_mismatch": true,
  "sensor_hash_matches_frozen_input": true,
  "phase9_controller_snapshot_matches_current_synth_netlist": true,
  "historical_phase9_decision": "NO-GO",
  "classification": "mixed_signal_harness_not_yet_equivalent"
}
```

## Exit gate

`Phase 9 Root-Cause Baseline Freeze = GO`

If hashes do not match the expected repository state, STOP and publish the mismatch; do not continue on an unknown baseline.

## Suggested commit

`docs(ftc): freeze phase9 mixed-signal root-cause baseline`

---

# 6. Gate R1 — prove the synthesized controller behaves correctly at 1 GHz in a cheap digital-only run

## Goal

Separate a true controller/1 GHz problem from an analog-bridge problem before invoking XA.

## Important rule

Do not modify the existing Phase 8 evidence. Create a new Phase 9 diagnostic run using the **same synthesized netlist** and a verification-only behavioral sensor/oracle.

## Tasks

1. Build a focused gate-level diagnostic bench with `Tcal = 1 ns`.
2. Use the current synthesized controller netlist, not RTL.
3. Use the existing behavioral sensor model only for this diagnostic.
4. Run nominal 0.80 V behavior only; no analog simulation yet.
5. Audit exact operation counts and trajectory:
   - 45 total operations;
   - 17 configuration operations;
   - 28 probes;
   - 28 sample-1 events;
   - 28 sample-2 events;
   - M9 boundary;
   - M9 -> M8 -> M7 backoff;
   - F5 boundary;
   - F6 guard/hold;
   - final M7/F6.
6. Count `sense_s_clk` using `always @(posedge sense_s_clk)`, not sampled-high rows.
7. Confirm 28 S_CLK rising edges for 28 probes.
8. Confirm every M/F change is one bit and occurs while reset is asserted and S_CLK is low.

## Pass criteria

All digital protocol results must match Phase 8 nominal 0.80 V, but now at the physical 1 ns period.

## Failure classification

If R1 fails, this is **not** a VCS-XA bridge failure. Classify as:

`1 GHz Gate-Level Controller Diagnostic = NO-GO`

STOP and create a controller/timing implementation plan. Do not continue into analog mixed-signal diagnosis.

## Exit gate

`1 GHz Gate-Level Controller Diagnostic = GO`

## Suggested commit

`test(ftc): add 1ghz phase9 gate-level diagnostic`

---

# 7. Gate R2 — define the corrected mixed-signal electrical boundary contract

## Goal

Make every digital/analog crossing explicit and auditable before any meaningful sensor result is accepted.

## 7.1 Sensor supply topology

Preferred corrected topology:

- do **not** use an ordinary Verilog `reg VDD` / `reg VSS` as the analog sensor's physical supply through a generic D2A element;
- generate the sensor VDD/VSS with ideal SPICE sources inside the XA analog deck/wrapper or another explicitly supported analog powernet mechanism;
- parameterize the scenario supply as `VDD_VALUE`;
- the three formal values are exactly 0.80 V, 0.95 V, and 1.10 V;
- the digital controller remains a digital VCS model; its physical power is outside this Phase 9 mixed-domain abstraction.

If the installed VCS-XA version strongly prefers an explicit `d2a powernet` mechanism, that is acceptable **only if** Codex proves from the generated interface-element report that no unintended series resistance or wrong voltage mapping remains on the sensor supply.

Do not guess simulator syntax. Inspect the installed tool's help/examples or generated interface report first, then use the syntax supported by that exact version.

## 7.2 D2A control crossings

The following controller outputs cross from digital to transistor-level analog:

- `sense_s_clk`;
- `sense_dff_reset`;
- `medium_therm[15:0]`;
- `fine_therm[9:0]`.

For each crossing, freeze and record:

- low voltage;
- high voltage;
- reference supply;
- rise time;
- fall time;
- output resistance or equivalent source model;
- whether the interface is treated as a normal signal or a powernet.

The analog HIGH value must scale with the scenario sensor supply. Do not keep a hard-coded 1.0 V or other default level across all three scenarios.

The control edge model must be chosen to reproduce the already-accepted corrected-v2 HSPICE boundary conditions. Do not tune the D2A slew independently per M/F or per voltage to force a boundary.

## 7.3 A2D `q_final`

Freeze one normalized A2D contract for the three scenarios.

At minimum document:

- analog low threshold;
- analog high threshold or transition threshold;
- hysteresis / X-region behavior if supported;
- reference supply used for normalized thresholds.

Do not tune the A2D threshold independently at 0.80/0.95/1.10 V.

Because the real `Q_FINAL` is a standard-cell DFF output expected to settle near a rail, the key acceptance is that analog `Q_FINAL` and digital `q_final` agree at both controller sample events.

## 7.4 Interface report

Add an audit script that parses the generated VCS-XA / PrimeSim XA interface-element report and emits a compact JSON summary. It must fail if:

- any required crossing is missing;
- any bus bit is omitted;
- any control HIGH is not supply-referenced as intended;
- sensor VDD is not the intended analog source;
- an unexpected generic supply D2A element remains;
- A2D `q_final` has an undocumented threshold model.

## Required output

`vcs_xa_corrected/inputs/bridge_contract.json`

and

`vcs_xa_corrected/reports/INTERFACE_ELEMENT_AUDIT.json`

## Exit gate

`VCS-XA Electrical Boundary Contract = GO`

No autonomous calibration transient is allowed before this gate passes.

## Suggested commit

`fix(ftc): define explicit phase9 vcs-xa electrical boundary`

---

# 8. Gate R3 — run a very short 0.80 V interface smoke transient

## Goal

Prove that the actual analog nodes produced by the corrected bridge match the intended boundary conditions before exercising calibration behavior.

## Runtime target

Only enough time to inspect a few digital transitions and one reset/clock sequence. Do not run a full calibration.

## Required analog probes

At minimum preserve compact measurements for:

- analog sensor VDD;
- analog sensor VSS;
- analog `S_SCLK`;
- analog `S_RESET`;
- at least one medium thermometer bit toggled by the diagnostic;
- at least one fine thermometer bit toggled by the diagnostic;
- analog `Q_FINAL`.

If practical, also probe the sensor-internal nodes:

- `xor_29`;
- `medium_out`;
- `dff_ck`.

Use the actual XA hierarchy discovered by the simulator; do not invent a hierarchical probe name and silently ignore failures.

## Required checks

1. Sensor supply is 0.80 V within simulator numerical tolerance and remains stable.
2. Analog LOW levels are near VSS.
3. Analog HIGH levels are near sensor VDD.
4. Actual analog transition times match the configured D2A contract.
5. No supply-crossing series-droop artifact is observed during the tiny diagnostic.
6. `q_final` digitalization is stable and deterministic.

## Exit gate

`VCS-XA Analog Boundary Smoke = GO`

If this fails, remain in harness diagnosis. Do not run M0/M9 sensor-equivalence probes yet.

## Suggested commit

`test(ftc): add vcs-xa analog boundary smoke audit`

---

# 9. Gate R4 — two-anchor short-probe equivalence at 0.80 V

## Goal

Answer the key root-cause question with the smallest useful analog experiment:

> Does the corrected VCS-XA bridge reproduce the already-accepted transistor sensor classification at M0/F0 and M9/F0?

This gate is diagnostic and belongs to this new root-cause plan; it is not a fourth formal Phase 9 nominal acceptance scenario.

## Two required anchors

### Anchor A — M0/F0

Expected corrected-v2 behavior:

- stable-high sensor decision;
- both controller-equivalent Q sample observations high;
- no extra S_CLK edge;
- correct recovery.

### Anchor B — M9/F0

Expected corrected-v2 behavior:

- stable-low sensor decision;
- both controller-equivalent Q sample observations low;
- no extra S_CLK edge;
- correct recovery.

The two probes must use the exact Phase 1 local-cycle event order at 1 ns/cycle.

## Diagnostic bench rule

It is acceptable for this isolated bridge testbench to directly select M/F and issue the probe sequence because the purpose is to validate the mixed-signal boundary independently of the controller algorithm. These direct drives are **not** formal Phase 9 autonomous acceptance evidence and must live only under `diagnostics/bridge_probe_0p80/`.

## Required waveform/measurement audit

For each anchor record:

- intended digital M/F;
- actual analog thermometer rails;
- analog S_CLK t50 rise/fall;
- analog reset release/assert times;
- analog `xor_29` activity if available;
- analog `medium_out` activity if available;
- analog `dff_ck` activity if available;
- analog `Q_FINAL` at sample 1;
- analog `Q_FINAL` at sample 2;
- digital `q_final` at sample 1;
- digital `q_final` at sample 2;
- resulting LOW/HIGH/AMBIG classification;
- recovery status.

## Comparison policy

First compare against already archived corrected-v2 HSPICE evidence. Reuse existing machine-readable measurements when present; do not rerun historical HSPICE merely to make new plots.

If an exact historical numeric timing quantity is unavailable, do not invent a tight ps tolerance. In that case require:

- boundary waveform contract correctness;
- identical binary classification at both sample points;
- correct internal event ordering;
- recovered low/quiet state before probe completion.

## Root-cause interpretation

### Case 1 — M0 high and M9 low after bridge correction

Primary conclusion:

`Historical Phase 9 NO-GO was caused by mixed-signal harness non-equivalence.`

Proceed to R5.

### Case 2 — analog Q is correct but digital `q_final` is wrong

Primary conclusion:

`A2D q_final bridge defect.`

Fix A2D modeling only, rerun R3/R4, and do not touch the sensor.

### Case 3 — analog controls/supply are correct but M9 remains physically high

Primary conclusion:

`PrimeSim-XA sensor result differs from corrected-v2 HSPICE despite boundary equivalence.`

STOP. Produce a focused simulator-model-equivalence report comparing:

- transistor model library/corner;
- CDL includes;
- temperature;
- source edge models;
- timestep / XA simulation level;
- device/subcircuit resolution;
- exact sensor netlist hash.

Do not tune M/F cells or protocol.

## Required output

`vcs_xa_corrected/reports/BRIDGE_PROBE_EQUIVALENCE.json`

## Exit gate

`0.80 V M0/M9 Bridge Equivalence = GO`

## Suggested commit

`test(ftc): prove phase9 short-probe bridge equivalence`

---

# 10. Gate R5 — repair Phase 9 event/audit instrumentation before full run

## Goal

Ensure the next autonomous result can actually prove the contract.

## Required digital event counters

Use event-driven monitors:

```systemverilog
always @(posedge sense_s_clk)          ...
always @(posedge probe_start_event)    ...
always @(posedge config_update_event)  ...
always @(posedge q_sample_1_event)     ...
always @(posedge q_sample_2_event)     ...
always @(medium_therm or fine_therm)   ...
```

Do not infer `sense_s_clk` rising-edge count from the number of CSV rows where S_CLK happens to be high.

## State snapshot timing

Do not use same-edge `posedge cal_clk` snapshots as the sole record of a gate-level state transition.

Preferred stable snapshot choices:

- `negedge cal_clk`, or
- an explicitly documented post-clock observation point that is safely after mapped clock-to-Q delay.

Event counters remain edge-triggered independently of that snapshot stream.

## Required audit semantics

For each accepted probe prove:

1. exactly one `probe_start_event`;
2. exactly one physical `sense_s_clk` rising edge;
3. exactly one sample-1 event;
4. exactly one sample-2 event;
5. M/F unchanged from probe start through recovery completion;
6. reset low during active sensing window and reasserted per contract;
7. Q sample pair classification recorded;
8. no extra S_CLK during config updates.

For each config update prove:

1. exactly one configuration event;
2. exactly one thermometer bit changed;
3. reset asserted;
4. S_CLK low;
5. two-cycle settle window completed before next accepted probe.

## Audit self-consistency checks

The script must reject internally contradictory summaries, including cases such as:

- `cal_fail == 0` but a derived `no_fail_state` field says false without explicit evidence;
- `probe_count != sclk_rise_count`;
- sample counts differ from probe count;
- config event count differs from physical thermometer transition count.

## Exit gate

`Phase 9 Event Instrumentation = GO`

No full autonomous result may be called GO if this instrumentation gate is not already passing on the short diagnostic.

## Suggested commit

`test(ftc): make phase9 mixed-signal audits edge-accurate`

---

# 11. Gate R6 — corrected autonomous 0.80 V acceptance

## Goal

Run the first real autonomous transistor-sensor mixed-signal acceptance only after R0-R5 pass.

## Inputs allowed from the external testbench/deck

Only:

- analog sensor supply / ground;
- `ctrl_por_n`;
- `cal_start`;
- external `cal_clk`.

The autonomous testbench must not directly drive:

- medium thermometer;
- fine thermometer;
- sensor reset;
- sensor S_CLK;
- FSM state;
- Q sample strobes.

## Clock

`Tcal = 1 ns` exactly, derived from the Phase 1 handoff.

Do not change RTL cycle counts.

## Simulation stop budget

Do not retain the historical 8 us stop merely because the old harness ran at 10 ns.

Derive a corrected timeout from:

- known 0.80 V controller cycle count / Phase 8 completion behavior;
- 1 ns period;
- POR/startup allowance;
- a conservative but bounded safety margin.

The timeout computation must be documented in `bridge_contract.json` or the run metadata. A value around the sub-microsecond to roughly 1 us scale is expected, but Codex must compute it from actual controller event/cycle accounting rather than hard-coding this plan's prose.

## Required 0.80 V trajectory

Exactly prove:

- M0 through M9 coarse scan;
- two independent stable-low probes at M9;
- M9 -> M8 configuration update;
- M8 -> M7 configuration update;
- zero probe between backoff updates;
- fine F0..F4 high;
- F5 first non-high boundary;
- F5 -> F6 guard update;
- F6 guard stable-low;
- independent F6 hold stable-low;
- final M7/F6;
- `cal_done = 1`;
- `lock_valid = 1`;
- `cal_fail = 0`;
- M/F frozen after lock.

## Required operation totals

- 45 operations;
- 17 config updates;
- 28 probes;
- 28 S_CLK rising edges;
- 28 sample-1 events;
- 28 sample-2 events.

## Required analog checks

For every probe or at least via an automated full-run audit:

- real analog sensor supply correct;
- real S_CLK edge count and level valid;
- reset waveform valid;
- Q analog and digital values agree at sample points;
- recovery is complete by controller recovery-done;
- no unexpected analog control glitch crosses the sensor threshold.

## Failure rule

If corrected 0.80 V fails, STOP immediately.

Do not run 0.95 or 1.10 V.

Classify the first divergence by the earliest mismatching event:

```text
controller request
-> config transition
-> reset release
-> S_CLK rise
-> internal sensor response
-> analog Q
-> A2D q_final
-> sample 1
-> sample 2
-> classification
-> FSM decision
```

Publish the first divergent stage and do not tune unrelated layers.

## Exit gate

`Corrected Autonomous 0.80 V = GO`

## Suggested commit

`test(ftc): recover autonomous 0p80 on corrected vcs-xa bridge`

---

# 12. Gate R7 — complete 0.95 V and 1.10 V with the same bridge contract

## Goal

Prove that the corrected harness is not a one-voltage tuned workaround.

## Hard rule

Do not change between scenarios:

- controller netlist;
- sensor netlist;
- sequencer timing;
- D2A normalized slew policy;
- A2D normalized threshold policy;
- audit logic;
- backoff/guard/sampling semantics.

Only scenario supply and frozen expected trajectory may differ.

## 0.95 V acceptance

Require:

- coarse boundary M6;
- backoff to M4;
- fine boundary F5;
- guard/hold F6 low;
- final M4/F6;
- 36 operations;
- 14 config updates;
- 22 probes;
- 22 S_CLK rises;
- 22 sample-1 events;
- 22 sample-2 events;
- done/lock asserted and no fail.

## 1.10 V acceptance

Require:

- coarse boundary M4;
- backoff to M2;
- fine boundary F8;
- guard/hold F9 low;
- final M2/F9;
- 36 operations;
- 15 config updates;
- 21 probes;
- 21 S_CLK rises;
- 21 sample-1 events;
- 21 sample-2 events;
- done/lock asserted and no fail.

## Stop rule

If 0.95 V fails after 0.80 V passes, stop before 1.10 V and classify whether the mismatch is caused by supply scaling of the bridge or a genuine transistor-sensor difference.

If 1.10 V fails, stop and publish that specific divergence.

No per-voltage bridge retuning is allowed inside R7.

## Exit gate

`Corrected Three-Voltage Autonomous Mixed-Signal Acceptance = GO`

## Suggested commit

`test(ftc): complete corrected phase9 nominal mixed-signal acceptance`

---

# 13. Gate R8 — publish the final Phase 9 disposition

## Goal

Update project truth without erasing the original failure evidence.

## Preserve historical evidence

Keep:

```text
vcs_xa/reports/PHASE9_NO_GO_REPORT.md
vcs_xa/reports/autonomous_0p80_audit.json
```

Do not delete them.

Add a short historical status note or supersession pointer explaining that the run used the rejected 10 ns physical timing inheritance and an unfrozen bridge contract.

## Publish corrected evidence

Create:

`vcs_xa_corrected/reports/PHASE9_CORRECTED_REPORT.md`

The report must include:

- baseline commit and corrected-flow commit;
- selected VCS / XA versions;
- 1 GHz clock contract;
- supply topology;
- D2A/A2D interface contract;
- short M0/M9 bridge-equivalence result;
- all three autonomous trajectory summaries;
- exact operation counts;
- physical S_CLK edge counts;
- Q sample counts;
- final M/F codes;
- raw evidence SHA256 manifests;
- explicit statement of whether the historical NO-GO root cause was confirmed as harness non-equivalence.

Update:

`delay_chain/ftc/controller/reports/FTC_CONTROLLER_GATE_STATUS.json`

only after all three scenarios pass.

Then Phase 9 may publish:

```text
Synthesizable Startup Calibration Controller = GO
Real Circuit Autonomous Startup Calibration = GO
```

If any required scenario remains failing, Phase 9 stays NO-GO and Phase 10 must not begin.

## Suggested final commit

`docs(ftc): publish corrected phase9 mixed-signal acceptance`

---

# 14. Tool-version policy

The historical NO-GO used a VCS / PrimeSim XA mixed-signal tool pair different from the VCS version used by later digital verification.

At R0/R2, Codex must discover which mixed-signal-capable combinations are actually installed and licensed.

Select one supported pair before R3 and freeze it for all R3-R7 runs.

Do not alternate simulator versions between voltage scenarios.

If only the historical VCS-XA pair is available, that is acceptable provided:

- the synthesized standard-cell Verilog models compile cleanly;
- mixed-signal comparison errors remain zero;
- interface-element generation is explicitly audited;
- the short-probe equivalence gate passes.

A tool upgrade is not by itself a circuit fix and must not be used to hide a failed boundary audit.

---

# 15. Evidence-retention policy

Because raw XA/FSDB products can be very large, repository commits should retain compact reproducibility evidence instead of forcing raw waveforms into Git.

For every diagnostic/acceptance run preserve at minimum:

- rendered SPICE/XA top deck hash;
- controller netlist hash;
- sensor netlist hash;
- wrapper/config hash;
- testbench hash;
- tool version text;
- compact event CSV or compressed/filtered event evidence when small enough;
- machine-readable audit JSON;
- SHA256 of raw logs/FSDB if raw files remain local;
- exact command line in a small text file or JSON field;
- pass/fail decision.

Never publish GO based only on a Markdown narrative.

---

# 16. Simulation-budget discipline

This targeted root-cause plan supersedes the original Phase 9 instruction that prohibited an extra diagnostic scenario, because the original first nominal run has already failed and a dedicated root-cause plan is now required.

Still keep the budget strict:

| Gate | Analog/XA work | Budget intent |
|---|---|---|
| R0 | none | static only |
| R1 | none | cheap digital VCS |
| R2 | no long transient | elaboration/interface inspection |
| R3 | one tiny 0.80 V boundary smoke | shortest possible |
| R4 | one focused 0.80 V two-anchor diagnostic | short only |
| R5 | none beyond existing diagnostic evidence | instrumentation |
| R6 | one corrected full 0.80 V autonomous run | only after R0-R5 GO |
| R7 | one 0.95 V + one 1.10 V run | only after 0.80 GO |
| R8 | none | reporting only |

Do not run frequency sweeps, PVT sweeps, recovery sweeps, or ad-hoc M/F sweeps in this plan.

---

# 17. Failure-classification matrix

Codex must classify the earliest failing layer and stop there.

| First failure | Classification | Allowed next action |
|---|---|---|
| 1 GHz digital gate-level diagnostic | controller/implementation timing | new controller timing plan |
| analog sensor supply wrong | mixed-signal power bridge | fix wrapper/powernet only |
| control HIGH/LOW/slew wrong | D2A bridge | fix D2A config only |
| analog Q correct, digital q_final wrong | A2D bridge | fix A2D config only |
| M0/M9 classifications wrong with correct boundary waveforms | XA vs HSPICE model-equivalence | compare models/corner/timestep/includes |
| short probes pass, full 0.80 diverges before sensor response | controller/harness handshake | fix testbench/instrumentation only if proven |
| short probes pass, full 0.80 sensor analog response diverges | physical autonomous interaction | targeted physical timing diagnosis; no random tuning |
| 0.80 passes, 0.95 fails | supply-scaling or voltage-specific physical response | stop; compare same frozen bridge across supplies |
| all three pass but audit counts disagree | audit infrastructure | fix audit before GO |

---

# 18. Codex execution checklist

Codex should execute this plan in order and mark each item in its working notes.

```text
[ ] R0 baseline hashes/tool versions frozen
[ ] R0 Phase1-vs-historical-Phase9 clock mismatch recorded
[ ] R1 synthesized netlist passes 1 GHz digital 0.80 diagnostic
[ ] R1 exact 45/17/28 event counts reproduced
[ ] R2 analog sensor supply no longer depends on an undocumented generic D2A path
[ ] R2 S_CLK/reset/M/F D2A contract explicit
[ ] R2 q_final A2D contract explicit
[ ] R2 generated interface-element audit passes
[ ] R3 0.80 V analog boundary smoke passes
[ ] R4 M0/F0 stable-high reproduced
[ ] R4 M9/F0 stable-low reproduced
[ ] R4 analog Q agrees with digital q_final at both sample events
[ ] R5 actual S_CLK edge counter implemented
[ ] R5 config transition and Q sample audits are event-accurate
[ ] R6 autonomous 0.80 reaches M7/F6
[ ] R6 45/17/28 and 28/28 Q samples proven
[ ] R7 autonomous 0.95 reaches M4/F6 with 36/14/22
[ ] R7 autonomous 1.10 reaches M2/F9 with 36/15/21
[ ] R7 bridge parameters were not retuned per voltage
[ ] R8 historical NO-GO preserved with supersession context
[ ] R8 final machine-readable evidence published
[ ] R8 gate ledger updated only if all three nominal scenarios pass
```

---

# 19. Explicitly forbidden shortcuts

Codex must not do any of the following:

- change medium/fine sensor cells to obtain a mixed-signal pass;
- change the sense DFF;
- change backoff depth;
- change fine guard semantics;
- change Q double-sampling semantics;
- change Phase 1 cycle constants to accommodate the historical 10 ns Phase 9 bench;
- call a 10 ns Phase 9 sensor run equivalent to the 1 ns corrected-v2 HSPICE protocol;
- treat `sclk_high_samples` as S_CLK rising-edge count;
- infer an analog supply value from a digital logic `1` without measuring the analog node;
- tune A2D thresholds differently for 0.80/0.95/1.10 V;
- tune D2A slew differently for specific M/F codes;
- rerun full autonomous XA repeatedly while still debugging the interface;
- delete the original NO-GO evidence;
- publish GO from Markdown only without machine-readable audits;
- proceed to Phase 10 while any nominal Phase 9 scenario is unresolved.

---

# 20. Final intended outcome

The successful path of this plan is:

```text
Historical Phase 9 VCS-XA NO-GO
        |
        v
R0 forensic baseline freeze
        |
        v
R1 1 GHz synthesized-controller digital diagnostic
        |
        v
R2 explicit VCS-XA D2A/A2D + analog-supply contract
        |
        v
R3 tiny analog boundary smoke
        |
        v
R4 M0/F0 HIGH + M9/F0 LOW bridge equivalence
        |
        v
R5 edge-accurate Phase 9 audit infrastructure
        |
        v
R6 autonomous 0.80 V -> M7/F6
        |
        v
R7 autonomous 0.95 V -> M4/F6
        |
        +--> autonomous 1.10 V -> M2/F9
        |
        v
R8 publish corrected Phase 9 evidence
        |
        v
Real Circuit Autonomous Startup Calibration = GO
```

Only after this gate is genuinely achieved may the project freeze the startup-calibration-controller layer and proceed toward programmable detection margin, droop/fault detection, PVT, post-layout, and macro convergence.
