# FTC Synthesizable Startup Calibration Controller Plan

## 0. Purpose, baseline, and non-negotiable execution rules

This plan converts the already accepted dynamic startup calibration protocol into a real synthesizable controller, then proves that the synthesized standard-cell controller can autonomously calibrate the existing transistor-level FTC sensor without the testbench directly driving M/F configuration, sensor DFF reset, or sensor S_CLK.

Baseline commit:

- `4e69acca9e82ae32f982014ced969d270ab8c8fa`
- baseline result: `Exact Reachable-Path Dynamic Startup Calibration = GO`
- baseline result: `Dynamic Startup Calibration Protocol = GO`

The baseline commit and all existing exact reachable-path acceptance artifacts are read-only golden evidence for this plan.

### 0.1 Frozen physical and protocol choices

This plan MUST NOT reopen or retune any of the following unless a later dedicated root-cause plan is explicitly created after a NO-GO:

- medium path-selection architecture;
- medium delay cell and mux selection;
- fine standard-cell load architecture;
- fine driver/load cell choices;
- sensor tap, XOR, and real-DFF topology;
- paired coarse-probe decision rule;
- two-step coarse backoff;
- one-step fine guard;
- fine-boundary semantics: first result that is not `stable_high`;
- guard and lock-hold semantics: both must be `stable_low`;
- existing 2.7 ns reachable functional recovery guard as the physical reference;
- the already accepted TT / 25 C nominal physical architecture.

### 0.2 Controller architecture frozen by this plan

Implement the controller as four separable blocks plus a thin top-level wrapper:

1. **High-level calibration finite-state machine (FSM)**
   - decides what operation comes next;
   - does not directly implement nanosecond timing.

2. **Operation sequencer**
   - executes `CONFIG_UPDATE` and `PROBE` operations;
   - owns sensor `dff_reset`, sensor `s_clk`, wait counters, and probe timing.

3. **Direct thermometer configuration registers**
   - own the physical medium/fine control vectors;
   - physical M/F outputs come directly from registered thermometer state;
   - binary code may exist only as an internal position/debug representation, never as the source of a combinational thermometer decoder.

4. **Double-sample Q classifier**
   - samples `q_final` twice with real controller registers;
   - returns exactly one of `STABLE_LOW`, `STABLE_HIGH`, or `AMBIGUOUS`.

Recommended top-level hierarchy:

```text
ftc_cal_controller_top
├── ftc_cal_fsm
├── ftc_operation_sequencer
├── ftc_q_sampler
└── ftc_cfg_therm_regs
```

### 0.3 Phase discipline

Codex MUST execute this plan phase by phase.

For every phase:

- inspect all stated inputs before editing;
- create only the artifacts required by that phase;
- run only the tests/simulations explicitly allowed by that phase;
- publish machine-readable evidence plus a short Markdown report;
- declare the phase `GO` or `NO-GO` from structured evidence, not from hand-written prose;
- do not continue to the next phase after a `NO-GO`;
- do not silently change an already frozen timing or algorithmic assumption to obtain a `GO`;
- on failure, preserve the first failing evidence and end this plan at that gate.

No PVT sweep, programmable detection margin work, droop detection work, ring-oscillator design, ConfigSkip work, or layout optimization belongs in this plan.

---

# Phase 0 — Freeze the controller functional contract

## Goal

Translate the accepted exact reachable-path protocol into one unique controller specification before RTL is written.

## Inputs

Read and cross-check at minimum:

- `delay_chain/ftc/analysis/reachable_path_acceptance/exact_path_0p80_contract.json`
- `delay_chain/ftc/analysis/reachable_path_acceptance/exact_path_0p95_contract.json`
- `delay_chain/ftc/analysis/reachable_path_acceptance/exact_path_1p10_contract.json`
- `delay_chain/ftc/analysis/reachable_path_acceptance/exact_hspice/final_acceptance.json`
- `delay_chain/ftc/analysis/reachable_path_acceptance/decision_semantics.json`
- `delay_chain/ftc/scripts/run_reachable_path_acceptance.py`
- `delay_chain/ftc/scripts/run_exact_reachable_path_hspice.py`

## Required controller semantics

### Coarse search

- start from `M=0`, `F=0`;
- perform two complete and independent probes at each M;
- only `probe_a == STABLE_LOW` AND `probe_b == STABLE_LOW` confirms the coarse boundary;
- any other pair continues to the next M;
- a move from M to M+1 is an explicit configuration-update operation.

### Two-step backoff

After the coarse boundary is found:

- execute exactly one update from `M_boundary` to `M_boundary-1`;
- execute exactly one update from `M_boundary-1` to `M_boundary-2`;
- perform zero probes between the two updates;
- each update changes exactly one medium thermometer bit.

### Fine search

At selected medium base `M_boundary-2`:

- start at `F=0`;
- probe once per F;
- only `STABLE_HIGH` continues to F+1;
- the first `STABLE_LOW` or `AMBIGUOUS` result is the fine boundary.

### Guard and lock hold

- explicitly update to `F_boundary+1`;
- run one guard probe;
- guard probe must be `STABLE_LOW`;
- run one independent lock-hold probe at the same code;
- lock-hold probe must be `STABLE_LOW`;
- only then assert `lock_valid` and freeze the configuration.

## Required defensive failure states

The controller specification MUST define at least:

- `COARSE_RANGE_FAIL`
- `COARSE_BACKOFF_UNDERFLOW`
- `FINE_RANGE_FAIL`
- `GUARD_RANGE_FAIL`
- `GUARD_NOT_LOW`
- `HOLD_NOT_LOW`

These are defensive controller behaviors and MUST NOT be described as physical failures already observed in the accepted three nominal scenarios.

## Golden nominal trajectories

The specification MUST freeze the three existing nominal outcomes:

- 0.80 V: coarse boundary M9, selected M7, fine boundary F5, final M7/F6;
- 0.95 V: coarse boundary M6, selected M4, fine boundary F5, final M4/F6;
- 1.10 V: coarse boundary M4, selected M2, fine boundary F8, final M2/F9.

## Files to create

```text
delay_chain/ftc/controller/spec/
├── FTC_CALIBRATION_CONTROLLER_SPEC.md
└── ftc_calibration_controller_contract.json
```

The JSON contract must be the machine-readable source for later tests.

## Simulation budget

- HSPICE: 0

## Exit gate

Publish:

`Controller Functional Contract = GO`

Only if the generated contract matches all three accepted golden trajectories and all protocol semantics above.

---

# Phase 1 — Quantize the accepted continuous-time protocol into a synchronous controller timing contract

The current accepted exact-path HSPICE uses physical times. A real synchronous controller acts in integer `cal_clk` cycles. This phase proves that the synchronous mapping does not change the accepted physical behavior before complete RTL is built.

## Phase 1A — Zero-HSPICE cycle schedule construction

### Initial one-shot candidate

Use an external calibration clock candidate of:

- `cal_clk = 1 GHz`
- period = 1 ns

Do not sweep frequency in this plan.

Map the physical requirements conservatively to integer cycles:

| Requirement | Accepted physical reference | Initial synchronous mapping |
|---|---:|---:|
| configuration settle | at least 1.5 ns | 2 cycles |
| reset release to S_CLK launch | at least 0.49 ns | 1 cycle |
| S_CLK high interval | about 3 ns in accepted deck | 3 cycles |
| launch to Q sample 1 | at least 2.3 ns | 3 cycles |
| sample 1 to sample 2 | at least 0.2 ns | 1 cycle |
| recovery wait | at least 2.7 ns | 3 cycles |

The controller MUST NOT attempt to synthesize a 10 ps delay element. The old 10 ps edge is a testbench edge-shape assumption, not a digital delay primitive.

### Required schedule model

Create a cycle-level operation scheduler that models:

```text
CONFIG_UPDATE:
  sensor reset asserted
  sensor S_CLK low
  change exactly one thermometer bit
  wait 2 full cal_clk cycles
  done

PROBE:
  code stable
  release sensor reset
  wait 1 cycle
  drive one registered S_CLK rising edge
  hold high 3 cycles
  drive registered S_CLK low
  wait until Q sample-1 point
  sample Q #1
  wait 1 cycle
  sample Q #2
  reassert sensor reset
  wait recovery window
  done
```

If the exact integer-cycle ordering required to preserve the accepted launch/read/recovery inequalities differs by one conservative cycle, choose the longer safe ordering once during Phase 1A and freeze it before Phase 1B. Do not use any HSPICE result to adapt later voltage scenarios.

### Structural checks

Require:

- every M/F change is an explicit config update;
- every config update changes one thermometer bit;
- M/F are constant during a probe;
- exactly two consecutive backoff updates and zero probes between them;
- exactly one intended S_CLK rising edge per probe;
- exactly two Q sample events per probe;
- all three complete cycle schedules are generated before any Phase 1B HSPICE run.

### Files

```text
delay_chain/ftc/controller/analysis/cycle_protocol/
├── cycle_timing_contract.json
├── cycle_path_0p80_contract.json
├── cycle_path_0p95_contract.json
├── cycle_path_1p10_contract.json
└── pre_run_freeze.json
```

### Simulation budget

- HSPICE: 0

## Phase 1B — Open-loop transistor-level synchronous timing bridge

### Goal

Prove that the future controller's integer-cycle timing still produces the accepted physical behavior.

### Method

Reuse the frozen physical sensor/deck rendering infrastructure. The testbench may still drive M/F, sensor reset, and sensor S_CLK in this phase, but all edges and waits MUST come from the frozen Phase 1A integer-cycle schedule.

Run exactly three new scenarios:

- `cycle_path_0p80`
- `cycle_path_0p95`
- `cycle_path_1p10`

Do not run historical scenarios, a fourth diagnostic scenario, a timing sweep, or a frequency sweep.

### Acceptance

All three must reproduce:

- 0.80 V -> M7/F6;
- 0.95 V -> M4/F6;
- 1.10 V -> M2/F9.

For every reachable probe require:

- Q sample 1 and Q sample 2 classify to the same rail;
- measured Q classification matches the frozen expected decision;
- exactly one active CK rising edge;
- physical recovery passes;
- code does not change during the probe.

For every config update require:

- exactly one thermometer bit changes;
- sensor reset is asserted;
- S_CLK is low;
- no configuration-induced CK edge/glitch;
- the full synchronous settle wait is honored.

### Failure rule

If any of the three fails, publish `Cycle-Quantized Startup Protocol = NO-GO` and STOP.

Do not change the medium/fine architecture, DFF, two-step backoff, fine guard, or recovery philosophy inside this plan. A new timing-quantization root-cause plan is required.

### Exit gate

`Cycle-Quantized Startup Protocol = GO`

---

# Phase 2 — Implement direct thermometer configuration registers

## Goal

Create the first synthesizable RTL block and guarantee glitch-resistant single-bit physical configuration updates.

## Files

```text
delay_chain/ftc/controller/rtl/
├── ftc_cal_pkg.sv
└── ftc_cfg_therm_regs.sv
```

## Required interface behavior

Inputs should support controlled operations equivalent to:

- medium increment;
- medium decrement;
- fine increment;
- fine decrement;
- initialization;
- permanent lock after successful calibration.

Outputs:

- registered `medium_therm[]`;
- registered `fine_therm[]`;
- debug/position `medium_code` and `fine_code`;
- range status such as min/max flags.

## Mandatory implementation rule

Physical medium/fine outputs MUST come directly from registered thermometer state.

Do not implement the physical controls as:

`binary counter -> combinational thermometer decoder -> sensor`.

A binary position counter may exist only as internal bookkeeping/debug state.

## Required unit tests

Prove:

- every legal medium increment changes exactly one bit;
- every legal medium decrement changes exactly one bit;
- every legal fine increment changes exactly one bit;
- every legal fine decrement changes exactly one bit;
- underflow/overflow requests do not create illegal codes;
- after `cfg_locked`, no M/F output changes until controller POR/reset.

## HSPICE budget

- 0

## Exit gate

`Thermometer Configuration Block = GO`

---

# Phase 3 — Implement the operation sequencer and real double-sample Q classifier

## Goal

Move all low-level timing ownership out of the high-level FSM.

## Files

```text
delay_chain/ftc/controller/rtl/
├── ftc_operation_sequencer.sv
└── ftc_q_sampler.sv
```

## Operation sequencer commands

Support at least:

- `OP_CONFIG_UPDATE`
- `OP_PROBE`

The exact command/handshake encoding may be idiomatic SystemVerilog, but the high-level FSM must observe a clean request/busy/done style interface.

## CONFIG_UPDATE behavior

The sequencer must guarantee:

1. sensor DFF reset asserted;
2. sensor S_CLK low;
3. one requested M/F thermometer update occurs;
4. wait the frozen configuration-settle cycle count;
5. issue operation done.

## PROBE behavior

The sequencer must guarantee:

1. M/F remain constant for the whole probe;
2. sensor reset starts asserted;
3. release reset;
4. wait frozen reset-arm cycles;
5. create exactly one registered sensor S_CLK rising edge;
6. keep S_CLK high for the frozen high interval;
7. return S_CLK low;
8. sample `q_final` with a real controller register at sample point 1;
9. sample `q_final` again at sample point 2;
10. classify the pair;
11. reassert sensor reset;
12. wait the frozen recovery interval;
13. issue probe done.

## S_CLK implementation rule

Do not generate sensor S_CLK with an unsafe combinational expression such as raw `cal_clk & enable`.

The first implementation must use registered state transitions so that a probe cannot acquire a narrow enable glitch as an extra active edge.

## Q classifier

The sampler must return exactly:

- `STABLE_LOW` for `0,0`;
- `STABLE_HIGH` for `1,1`;
- `AMBIGUOUS` for `0,1` or `1,0`.

Do not collapse `AMBIGUOUS` into either stable rail inside the sampler.

## New risk that must remain explicit

The accepted exact-path HSPICE measured analog `q_final` at ideal testbench sample times. The real controller samples `q_final` with actual standard-cell registers. Therefore later gate-level and transistor-level phases MUST verify the sampling register path explicitly; Phase 3 must not claim that this has already been physically proven.

## Unit tests

Test each sequencer operation independently and prove exact cycle counts, exact sample count, exact S_CLK active-edge count, reset ownership, and M/F stability.

## HSPICE budget

- 0

## Exit gate

`Operation Sequencer = GO`

---

# Phase 4 — Implement the high-level calibration FSM

## Goal

Implement only algorithmic sequencing; keep cycle timing inside the sequencer.

## File

```text
delay_chain/ftc/controller/rtl/ftc_cal_fsm.sv
```

## Recommended high-level states

At minimum:

- `IDLE`
- `INIT`
- `COARSE_PROBE_A`
- `COARSE_PROBE_B`
- `COARSE_EVAL`
- `COARSE_INC`
- `BACKOFF_1`
- `BACKOFF_2`
- `FINE_PROBE`
- `FINE_EVAL`
- `FINE_INC`
- `GUARD_INC`
- `GUARD_PROBE`
- `HOLD_PROBE`
- `LOCKED`
- `FAIL`

Equivalent naming is allowed if semantics remain exact.

## Mandatory decision semantics

### Coarse

Store independent results for coarse probe A and B. Only two `STABLE_LOW` results confirm the boundary.

### Fine

- `STABLE_HIGH` -> continue fine scan;
- `STABLE_LOW` -> fine boundary;
- `AMBIGUOUS` -> fine boundary.

### Guard / hold

- guard must be `STABLE_LOW`;
- hold must independently be `STABLE_LOW`;
- otherwise enter `FAIL` with a stable fail reason.

### Lock

On successful lock:

- assert `lock_valid`;
- assert `cal_done`;
- freeze configuration;
- do not issue any additional config or probe operation before controller POR/reset.

## Defensive paths

Implement and unit-test all Phase 0 failure reasons.

## HSPICE budget

- 0

## Exit gate

`Calibration Algorithm FSM = GO`

---

# Phase 5 — Integrate complete RTL controller and reproduce the accepted trajectories with a behavioral sensor model

## Files

```text
delay_chain/ftc/controller/rtl/ftc_cal_controller_top.sv

delay_chain/ftc/controller/tb/
├── ftc_sensor_behavior_model.sv
├── tb_ftc_cal_controller.sv
└── scenarios/
```

## Top-level controller interface

Freeze at least:

Inputs:

- `cal_clk`
- `ctrl_por_n`
- `cal_start`
- `q_final`

Outputs:

- `sense_dff_reset`
- `sense_s_clk`
- `medium_therm[]`
- `fine_therm[]`
- `cal_busy`
- `cal_done`
- `cal_fail`
- `lock_valid`
- `medium_code`
- `fine_code`
- `fail_reason`
- debug state if useful.

`ctrl_por_n` is the controller's own reset. It is not the same signal as the sensor-path DFF reset controlled by the sequencer.

## Behavioral sensor model

The model is a verification oracle only. It must not be presented as new physical evidence.

Create nominal behavior tables derived from the already accepted trajectories so that the real RTL controller must autonomously produce the same operation sequence.

## Golden regressions

The RTL controller must reproduce all three:

### 0.80 nominal model

- scan M0 through M9;
- detect M9 from two independent low probes;
- backoff M9->M8->M7 with zero probe between updates;
- scan F0 through F5;
- treat F5 as first non-high fine boundary;
- update to F6;
- guard low;
- independent hold low;
- lock at M7/F6.

### 0.95 nominal model

- final lock M4/F6.

### 1.10 nominal model

- final lock M2/F9.

## Operation-count regression

The high-level executable operation count, excluding internal sequencer wait cycles, must remain:

- 0.80: 45 operations;
- 0.95: 36 operations;
- 1.10: 36 operations.

The RTL testbench must derive these counts from observed controller requests/events rather than hard-code a final success flag only.

## HSPICE budget

- 0

## Exit gate

`RTL Golden-Path Reproduction = GO`

---

# Phase 6 — Add protocol assertions and negative-path verification

## Goal

Prove that the controller cannot generate an illegal control trajectory even when the sensor response is adversarial.

## Files

```text
delay_chain/ftc/controller/assertions/ftc_cal_controller_sva.sv
```

and extend the RTL testbench with negative response scenarios.

## Mandatory assertions

At minimum cover:

1. every configuration update changes at most one thermometer bit;
2. any M/F change occurs only while sensor reset is asserted;
3. any M/F change occurs only while sensor S_CLK is low;
4. the required settle-cycle interval is honored after each update;
5. M/F remain constant during every probe;
6. each probe generates exactly one active sensor S_CLK rising edge;
7. each probe generates exactly two Q sample events;
8. coarse boundary cannot be accepted without two independent `STABLE_LOW` results;
9. backoff consists of exactly two single-step updates;
10. no probe is issued between backoff step 1 and step 2;
11. fine scan can continue only after `STABLE_HIGH`;
12. guard code is exactly fine-boundary plus one legal thermometer step;
13. successful lock requires guard probe and independent hold probe;
14. after lock, M/F remain unchanged until POR/reset;
15. `cal_done` and `cal_fail` are mutually exclusive;
16. fail reason remains stable after entering `FAIL`.

## Required negative scenarios

Use the behavioral sensor model to force at least:

- no coarse boundary before medium max;
- coarse boundary below two-step-backoff minimum;
- fine search remains high through fine max;
- fine boundary at maximum code so guard cannot be allocated;
- guard result high;
- guard result ambiguous;
- hold result high;
- hold result ambiguous.

Each case must terminate with the expected stable fail reason and without an illegal physical control sequence.

## HSPICE budget

- 0

## Exit gate

`RTL Protocol Safety = GO`

---

# Phase 7 — Synthesize the controller and close the initial timing contract

## Goal

Generate a real standard-cell implementation of the controller under the same library environment used by the existing FTC work and check that the proposed 1 GHz control clock is implementable without changing protocol semantics.

## Directory

```text
delay_chain/ftc/controller/synthesis/
├── constraints/
├── scripts/
├── netlist/
└── reports/
```

## Required outputs

At minimum preserve:

- synthesized standard-cell netlist;
- SDC or equivalent timing constraints;
- synthesis log;
- area report;
- timing report;
- fanout report;
- warnings report;
- cell-usage report.

## Timing/implementation checks

### cal_clk

Check the 1 GHz timing target. Do not silently lower the clock frequency inside this plan to obtain a pass.

### thermometer outputs

Inspect actual fanout and buffering on `medium_therm[]` and `fine_therm[]`.

### sense_s_clk

Verify synthesis did not turn sensor S_CLK into an unsafe combinational-gating structure. Preserve a registered-edge architecture with any required ordinary buffering.

### sense_dff_reset

Inspect actual fanout, slew-driving structure, and timing.

### q_final sampling path

Explicitly document how `q_final` reaches the controller sampling registers and how the path is constrained. Do not let it be optimized away or accidentally treated as an unrelated synchronous path.

## Allowed implementation fixes within Phase 7

Only non-semantic synthesis fixes are allowed, for example:

- FSM encoding;
- ordinary buffering;
- register duplication for fanout;
- non-functional RTL coding cleanup;
- constraint corrections that match the already frozen cycle protocol.

Do not change algorithm, cycle counts, two-step backoff, guard semantics, physical sensor cells, or nominal clock target.

## Failure rule

If the 1 GHz implementation does not close or physical controller outputs cannot meet the intended registered architecture, publish `Synthesized Calibration Controller = NO-GO` and STOP for a dedicated implementation/timing plan.

## HSPICE budget

- 0

## Exit gate

`Synthesized Calibration Controller = GO`

---

# Phase 8 — Gate-level controller regression before transistor-level integration

## Goal

Verify that synthesis preserved controller behavior and that real cell delays do not introduce a digital protocol error before expensive mixed controller/sensor HSPICE runs.

## Subphase A — Functional gate-level simulation

Use the same behavioral sensor model and reproduce all three nominal golden trajectories and all essential negative failure paths.

Require the same final codes and the same high-level operation counts as RTL.

## Subphase B — Delayed gate-level simulation

If the available flow supports SDF or equivalent cell-delay annotation, verify at minimum:

- one probe -> exactly one sensor S_CLK rising edge;
- one config command -> exactly one intended thermometer bit changes;
- reset sequencing still obeys the frozen cycle contract;
- Q sample events occur in the intended controller cycles;
- no synthesis delay produces a digital double-trigger or skipped operation;
- lock freezes physical control vectors.

If the available flow cannot produce SDF, record that limitation explicitly and require the missing electrical concerns to be covered in Phase 9 HSPICE; do not fabricate a delayed-GLS result.

## HSPICE budget

- 0

## Exit gate

`Gate-Level Calibration Controller = GO`

---

# Phase 9 — Autonomous transistor-level startup calibration with the synthesized controller

## Goal

Replace the open-loop PWL controller stimulus with the real synthesized standard-cell controller and prove autonomous startup calibration of the frozen transistor-level sensor.

This is the final acceptance phase of this plan.

## Testbench ownership rule

The Phase 9 testbench may provide only the environment/control inputs required to start the macro, including:

- VDD;
- VSS;
- `ctrl_por_n`;
- `cal_start`;
- external `cal_clk`.

The testbench MUST NOT directly drive:

- medium configuration;
- fine configuration;
- sensor DFF reset;
- sensor S_CLK;
- internal FSM state;
- Q sample strobes.

Those signals must be generated by the synthesized controller itself.

## Integrated topology

```text
external cal_clk / POR / cal_start
             |
             v
synthesized standard-cell calibration controller
             |
             +--> medium_therm
             +--> fine_therm
             +--> sense_dff_reset
             +--> sense_s_clk
             |
             v
frozen transistor-level sensor
medium path select + fine load + XOR + real DFF
             |
             +-------------------- q_final --------------------+
                                                                  |
                                                                  v
                                                     controller Q sampler
```

## Scenario budget

Before running any HSPICE, render and hash all three complete integrated decks and freeze their expected trajectories.

Run exactly three nominal scenarios:

- `autonomous_0p80`
- `autonomous_0p95`
- `autonomous_1p10`

Do not run a fourth diagnostic scenario, PVT sweep, frequency sweep, recovery sweep, or post-failure tuned rerun in this phase. A clearly recorded simulator infrastructure failure may be retried once only if the controller netlist, sensor netlist, contract, and deck hashes remain unchanged.

## Required trajectory acceptance

### 0.80 V

Observed autonomous controller activity must prove:

- M0 through M9 coarse scan;
- two independent low probes at M9;
- M9->M8 update;
- M8->M7 update;
- zero probe between the two backoffs;
- F0 through F5 fine scan at M7;
- F5 first non-high boundary;
- F5->F6 update;
- F6 guard low;
- independent F6 hold low;
- final locked code M7/F6.

### 0.95 V

Must autonomously end at M4/F6 with the corresponding M6 boundary, two-step backoff, F5 boundary, F6 guard/hold.

### 1.10 V

Must autonomously end at M2/F9 with the corresponding M4 boundary, two-step backoff, F8 boundary, F9 guard/hold.

## New electrical audits required because the controller is now real

For every probe and relevant controller transition, audit at minimum:

1. synthesized controller produces exactly one active sensor S_CLK rising edge per probe;
2. no unintended S_CLK edge appears during configuration-update quiet windows;
3. actual thermometer outputs change only in the intended single-bit pattern;
4. actual sensor reset waveform obeys the controller contract;
5. real controller sampling registers capture two consistent Q values for accepted stable decisions;
6. the Q sampling path shows no observed ambiguous/mis-captured nominal result;
7. physical recovery remains acceptable under the synchronous controller timing;
8. guard and hold classifications are both stable low;
9. `cal_done` / `lock_valid` assert only after the hold probe completes;
10. M/F remain physically frozen after lock;
11. controller never enters a fail state in the three nominal scenarios;
12. final locked code equals the frozen golden code.

Store per-probe, per-config-update, controller-state, Q-sample, CK-edge, reset, recovery, and final-lock audits as machine-readable CSV/JSON.

## Failure rule

If any one of the three nominal autonomous scenarios fails, publish:

`Real Circuit Autonomous Startup Calibration = NO-GO`

and STOP.

Do not alter recovery guard, medium/fine cells, DFF, cycle counts, backoff depth, fine guard, or sampling policy in the same plan. Create a new targeted plan from the first real failing mechanism.

## Final exit gate

All three must pass before publishing both:

- `Synthesizable Startup Calibration Controller = GO`
- `Real Circuit Autonomous Startup Calibration = GO`

---

# Phase 10 — Freeze the autonomous calibration subsystem and hand off to programmable detection margin

Execute this phase only after Phase 9 GO.

## Freeze

Record immutable hashes and final contracts for:

- controller RTL;
- synthesized controller netlist;
- synthesis constraints;
- calibration clock target;
- cycle-count timing contract;
- high-level FSM semantics;
- operation sequencer semantics;
- direct thermometer register implementation;
- Q double-sampling method;
- M/F physical interface;
- sensor reset interface;
- sensor S_CLK interface;
- three autonomous nominal HSPICE decks/results.

## Final report

Create a single report under:

```text
delay_chain/ftc/controller/reports/FTC_AUTONOMOUS_STARTUP_CALIBRATION_FINAL_ACCEPTANCE.md
```

The report must distinguish clearly between:

- what was proven by prior open-loop exact-path HSPICE;
- what was proven by RTL and assertions;
- what was proven by synthesis/gate-level checks;
- what was newly proven by autonomous transistor-level HSPICE.

## Next-project handoff

Only after this freeze may the project proceed to:

1. programmable detection margin;
2. voltage-droop detection behavior;
3. broader PVT validation;
4. post-layout extraction and macro finalization.

Do not start any of those tasks inside this plan.

---

# Repository layout expected by the end of the plan

```text
delay_chain/ftc/controller/
├── spec/
│   ├── FTC_CALIBRATION_CONTROLLER_SPEC.md
│   └── ftc_calibration_controller_contract.json
├── rtl/
│   ├── ftc_cal_pkg.sv
│   ├── ftc_cfg_therm_regs.sv
│   ├── ftc_q_sampler.sv
│   ├── ftc_operation_sequencer.sv
│   ├── ftc_cal_fsm.sv
│   └── ftc_cal_controller_top.sv
├── tb/
│   ├── ftc_sensor_behavior_model.sv
│   ├── tb_ftc_cal_controller.sv
│   └── scenarios/
├── assertions/
│   └── ftc_cal_controller_sva.sv
├── synthesis/
│   ├── constraints/
│   ├── scripts/
│   ├── netlist/
│   └── reports/
├── analysis/
│   ├── cycle_protocol/
│   ├── rtl/
│   ├── gate_level/
│   └── autonomous_hspice/
└── reports/
    └── FTC_AUTONOMOUS_STARTUP_CALIBRATION_FINAL_ACCEPTANCE.md
```

---

# Compact gate checklist for Codex

Codex must treat the following as hard sequential gates:

1. `Controller Functional Contract = GO`
2. `Cycle-Quantized Startup Protocol = GO`
3. `Thermometer Configuration Block = GO`
4. `Operation Sequencer = GO`
5. `Calibration Algorithm FSM = GO`
6. `RTL Golden-Path Reproduction = GO`
7. `RTL Protocol Safety = GO`
8. `Synthesized Calibration Controller = GO`
9. `Gate-Level Calibration Controller = GO`
10. `Real Circuit Autonomous Startup Calibration = GO`

A failure at any gate terminates this plan. No downstream phase may be used to tune an upstream failed assumption.
