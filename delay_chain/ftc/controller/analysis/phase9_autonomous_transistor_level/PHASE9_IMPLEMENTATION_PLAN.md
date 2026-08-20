# Phase 9 Implementation Plan - Approach C (Behavioral Controller)

**Document:** Phase 9-10 Completion Roadmap  
**Approach:** Behavioral Digital Controller with Transistor-Level Sensor  
**Date:** 2026-08-20  
**Estimated Duration:** 1-2 weeks

---

## Overview

Complete Phase 9 (Autonomous Transistor-Level Calibration) and Phase 10 (Freeze and Handoff) using Approach C: a cycle-accurate behavioral controller model that generates control signals matching the Phase 8B verified gate-level timing, interfaced with the transistor-level FTC sensor in HSPICE.

**Key Strategy:**
- Controller: Python-generated PWL waveforms (behavioral, but timing-accurate)
- Sensor: Transistor-level SPICE netlist (real analog circuit)
- Integration: HSPICE mixed-signal simulation
- Validation: Controller behavior matches Phase 8B exactly

---

## Phase 9 Requirements Summary

From `ftc_synthesizable_startup_calibration_controller_plan.md`:

### Testbench Rules
**ALLOWED inputs (testbench provides):**
- VDD, VSS
- ctrl_por_n
- cal_start
- cal_clk (external)

**FORBIDDEN direct drives (controller must generate):**
- medium_therm, fine_therm
- sense_dff_reset, sense_s_clk
- Internal FSM state
- Q sample strobes

### Three Required Scenarios
1. **autonomous_0p80:** Expected M7/F6
2. **autonomous_0p95:** Expected M4/F6
3. **autonomous_1p10:** Expected M2/F9

### Required Trajectory Evidence (per scenario)
- Coarse scan progression (M0 → boundary)
- Two independent low probes at boundary
- Two-step backoff (M → M-1 → M-2)
- Zero probe between backoffs
- Fine scan at locked M (F0 → boundary)
- F boundary detection
- F+1 update
- Guard low
- Hold low
- Final locked code

### Electrical Audits (per probe/transition)
1. Exactly one S_CLK rising edge per probe
2. No unintended S_CLK during config updates
3. Thermometer changes only in single-bit pattern
4. Sensor reset waveform correct
5. Q double-sampling captures consistent values
6. No ambiguous Q capture

---

## Implementation Phases

### Phase 9.1: Extract Transistor-Level Sensor
**Duration:** 4-8 hours  
**Status:** Not started

#### Tasks

**Task 9.1.1: Locate Frozen Sensor Netlist**
- Search prior HSPICE runs for working sensor design
- Candidate locations:
  - `ftc/runs/exact_reachable_path_acceptance/`
  - `ftc/spice/`
  - Previous Phase 4-6 cycle protocol work

**Task 9.1.2: Extract and Verify Sensor Subcircuit**
- Extract the sensor `.subckt` definition
- Verify it includes:
  - Medium delay chain (16 thermometer-controlled elements)
  - Fine delay chain (10 thermometer-controlled elements)
  - Sense DFF with S_CLK and reset
  - Q output
- Port list must match controller interface:
  ```spice
  .subckt ftc_sensor
  + medium_therm<15:0>  ; Medium thermometer inputs
  + fine_therm<9:0>     ; Fine thermometer inputs (active-low)
  + sense_s_clk         ; Sampling clock
  + sense_dff_reset     ; DFF reset
  + q_final             ; Q output to controller
  + vdd vss             ; Power
  ```

**Task 9.1.3: Create Standalone Sensor Test**
- Create `test_sensor_standalone.sp`
- Apply known M/F configuration
- Generate S_CLK pulse
- Verify Q output matches expected behavior
- **Acceptance:** Sensor produces correct Q for test M/F codes

**Deliverables:**
- `analysis/phase9_autonomous_transistor_level/sensor/ftc_sensor_frozen.sp`
- `analysis/phase9_autonomous_transistor_level/sensor/test_sensor_standalone.sp`
- Sensor verification report

---

### Phase 9.2: Implement Behavioral Controller Model
**Duration:** 2-3 days  
**Status:** Not started

#### Architecture

```
Python Controller Script
    ↓
Reads Phase 8B timing measurements
    ↓
Implements FSM state machine
    ↓
Reads Q feedback from HSPICE (iterative)
    ↓
Generates PWL waveforms for all control signals
    ↓
Writes HSPICE .include file with PWL sources
```

#### Tasks

**Task 9.2.1: Extract Timing Parameters from Phase 8B**
- Parse Phase 8B VCD or simulation log
- Extract key timing parameters:
  ```python
  # From Phase 8B SDF simulation measurements
  TIMING_PARAMS = {
      'clock_period': 10e-9,           # 10ns
      'config_to_probe_delay': 120e-9, # Time from config update to next probe
      'probe_duration': 50e-9,          # S_CLK pulse width
      's_clk_to_q_capture': 10e-9,     # Q capture timing
      'probe_to_config_delay': 70e-9,  # Time from probe to next config
      'por_to_cal_start': 50e-9,       # POR release to cal_start
      'cal_start_to_first_op': 20e-9,  # cal_start to first operation
  }
  ```

**Task 9.2.2: Implement FSM State Machine**
- Create `behavioral_controller.py`
- Implement states from `rtl/ftc_cal_controller_fsm.sv`:
  ```python
  class ControllerFSM:
      IDLE = 0
      COARSE_SEARCH = 1
      COARSE_VERIFY = 2
      BACKOFF_1 = 3
      BACKOFF_2 = 4
      FINE_SEARCH = 5
      FINE_VERIFY = 6
      GUARD = 7
      HOLD = 8
      LOCK = 9
      FAIL = 10
  ```

**Task 9.2.3: Implement Configuration Update Logic**
```python
def update_medium_therm(M, time):
    """Generate medium thermometer update waveform"""
    # Thermometer encoding: M=7 → 0000000001111111
    therm_code = thermometer_encode(M, 16)
    
    # Generate PWL for each bit
    for i in range(16):
        pwl_events['medium_therm'][i].append(
            (time, VDD if therm_code[i] else 0)
        )
    
    return time + CONFIG_UPDATE_DELAY

def update_fine_therm(F, time):
    """Generate fine thermometer update waveform (active-low)"""
    # Fine is active-low: F=6 → 1111000000
    therm_code = thermometer_encode_active_low(F, 10)
    
    for i in range(10):
        pwl_events['fine_therm'][i].append(
            (time, VDD if therm_code[i] else 0)
        )
    
    return time + CONFIG_UPDATE_DELAY
```

**Task 9.2.4: Implement Probe Operation**
```python
def probe_sensor(M, F, time):
    """Generate one probe operation control sequence"""
    
    # 1. Setup phase: dff_reset = 1
    pwl_events['sense_dff_reset'].append((time, VDD))
    time += RESET_SETUP_TIME
    
    # 2. Frozen phase: dff_reset = 0
    pwl_events['sense_dff_reset'].append((time, 0))
    
    # 3. S_CLK rising edge (exactly one!)
    pwl_events['sense_s_clk'].append((time, 0))
    time += 1e-9  # Rise time
    pwl_events['sense_s_clk'].append((time, VDD))
    time += PROBE_DURATION
    pwl_events['sense_s_clk'].append((time, 0))
    
    # 4. Q capture window
    q_capture_time = time - PROBE_DURATION/2
    
    # 5. Reset release
    time += RESET_HOLD_TIME
    pwl_events['sense_dff_reset'].append((time, VDD))
    
    return time, q_capture_time
```

**Task 9.2.5: Implement Calibration Algorithm**
```python
def run_autonomous_calibration(voltage):
    """Main calibration loop - matches RTL FSM exactly"""
    
    state = FSM.IDLE
    M = 0
    F = 0
    time = 0
    probe_count = 0
    q_history = []
    
    # Wait for POR and cal_start
    time = POR_RELEASE_TIME + CAL_START_TIME
    state = FSM.COARSE_SEARCH
    
    # Coarse search
    while state == FSM.COARSE_SEARCH:
        time = update_medium_therm(M, time)
        time, q_time = probe_sensor(M, F, time)
        probe_count += 1
        
        # Read Q from previous HSPICE run
        Q = read_q_from_hspice(voltage, probe_count)
        q_history.append((probe_count, M, F, Q))
        
        if Q == 0:  # Boundary detected
            state = FSM.COARSE_VERIFY
        else:
            M += 1
            if M > 15:
                state = FSM.FAIL
    
    # Coarse verify (second probe at boundary)
    if state == FSM.COARSE_VERIFY:
        time, q_time = probe_sensor(M, F, time)
        probe_count += 1
        Q = read_q_from_hspice(voltage, probe_count)
        q_history.append((probe_count, M, F, Q))
        
        if Q == 0:  # Confirmed
            state = FSM.BACKOFF_1
        else:
            state = FSM.FAIL
    
    # Backoff (M → M-1 → M-2)
    if state == FSM.BACKOFF_1:
        M -= 1
        time = update_medium_therm(M, time)
        state = FSM.BACKOFF_2
    
    if state == FSM.BACKOFF_2:
        M -= 1
        time = update_medium_therm(M, time)
        state = FSM.FINE_SEARCH
    
    # Fine search
    while state == FSM.FINE_SEARCH:
        time = update_fine_therm(F, time)
        time, q_time = probe_sensor(M, F, time)
        probe_count += 1
        
        Q = read_q_from_hspice(voltage, probe_count)
        q_history.append((probe_count, M, F, Q))
        
        if Q == 0:  # Fine boundary
            state = FSM.FINE_VERIFY
        else:
            F += 1
            if F > 9:
                state = FSM.FAIL
    
    # Fine verify
    # ... similar pattern ...
    
    # Guard probe (F+1)
    # ... similar pattern ...
    
    # Hold probe (verify F+1 stable)
    # ... similar pattern ...
    
    # Lock
    if state == FSM.LOCK:
        # Assert cal_done (this would be in controller, just record)
        pass
    
    return M, F, q_history, pwl_events
```

**Task 9.2.6: Iterative HSPICE Loop**
```python
def run_iterative_calibration(scenario_name, voltage):
    """
    Iterative approach:
    1. Generate control signals for probe #1
    2. Run HSPICE to get Q result
    3. Update FSM based on Q
    4. Generate control signals for probe #2
    5. Run HSPICE again
    6. ... repeat until lock or fail
    """
    
    for iteration in range(1, MAX_PROBES+1):
        # Generate PWL up to current probe
        pwl_file = generate_pwl_upto_probe(iteration)
        
        # Run HSPICE
        hspice_result = run_hspice_simulation(
            scenario_name, voltage, pwl_file
        )
        
        # Extract Q at current probe time
        Q = extract_q_from_result(hspice_result, iteration)
        
        # Update FSM
        next_state, next_M, next_F = update_fsm(Q)
        
        if next_state in [FSM.LOCK, FSM.FAIL]:
            break
    
    return final_M, final_F, trajectory
```

**Task 9.2.7: Generate HSPICE Include File**
```python
def write_hspice_pwl_file(pwl_events, filename):
    """Write PWL waveforms as HSPICE voltage sources"""
    
    with open(filename, 'w') as f:
        f.write("* Behavioral Controller PWL Waveforms\n")
        f.write("* Generated from Phase 8B verified timing\n\n")
        
        # Medium thermometer (16 bits)
        for i in range(16):
            f.write(f"Vmedium_therm{i} medium_therm<{i}> 0 PWL(\n")
            for time, voltage in pwl_events['medium_therm'][i]:
                f.write(f"+ {time*1e9}n {voltage}\n")
            f.write("+ )\n\n")
        
        # Fine thermometer (10 bits)
        for i in range(10):
            f.write(f"Vfine_therm{i} fine_therm<{i}> 0 PWL(\n")
            for time, voltage in pwl_events['fine_therm'][i]:
                f.write(f"+ {time*1e9}n {voltage}\n")
            f.write("+ )\n\n")
        
        # S_CLK
        f.write("Vsense_s_clk sense_s_clk 0 PWL(\n")
        for time, voltage in pwl_events['sense_s_clk']:
            f.write(f"+ {time*1e9}n {voltage}\n")
        f.write("+ )\n\n")
        
        # DFF reset
        f.write("Vsense_dff_reset sense_dff_reset 0 PWL(\n")
        for time, voltage in pwl_events['sense_dff_reset']:
            f.write(f"+ {time*1e9}n {voltage}\n")
        f.write("+ )\n\n")
```

**Deliverables:**
- `scripts/behavioral_controller.py` - Main controller model
- `scripts/fsm_state_machine.py` - FSM implementation
- `scripts/pwl_generator.py` - PWL waveform generation
- `scripts/hspice_interface.py` - HSPICE run automation
- Unit tests for each module

---

### Phase 9.3: Create Integrated HSPICE Testbenches
**Duration:** 1 day  
**Status:** Not started

#### Tasks

**Task 9.3.1: Create Base Testbench Template**
```spice
* autonomous_base_template.sp

.title FTC Autonomous Calibration Base Template

.option post=2 accurate brief=0
.option gmindc=1e-15 abstol=1e-15 reltol=1e-6

* Technology libraries
.lib '/host/data/libtech/SMIC_40LL/std_lib/smic40ll.l' tt

.param SUPPLY_VOLTAGE = {supply_v}
.param SIM_TIME = {sim_time}

* Power supplies
vdd vdd 0 SUPPLY_VOLTAGE
vss vss 0 0

* External clock
vcal_clk cal_clk 0 pulse(0 SUPPLY_VOLTAGE 0 100p 100p 5n 10n)

* POR and cal_start (testbench provides these)
vctrl_por_n ctrl_por_n 0 pwl(
+ 0 0
+ 99n 0
+ 100n SUPPLY_VOLTAGE
+ )

vcal_start cal_start 0 pwl(
+ 0 0
+ 149n 0
+ 150n SUPPLY_VOLTAGE
+ 160n 0
+ )

* Behavioral controller PWL waveforms (generated by Python)
.include 'behavioral_controller_pwl.sp'

* Transistor-level sensor
.include '../sensor/ftc_sensor_frozen.sp'

xsensor medium_therm<15:0> fine_therm<9:0>
+ sense_s_clk sense_dff_reset q_final
+ vdd vss ftc_sensor

* Analysis
.tran 100p SIM_TIME

* Measurements
.meas tran q_probe1 find v(q_final) at={probe1_time}
.meas tran q_probe2 find v(q_final) at={probe2_time}
* ... one measurement per probe

.print tran v(cal_clk) v(ctrl_por_n) v(cal_start)
.print tran v(sense_s_clk) v(sense_dff_reset) v(q_final)
.print tran v(medium_therm<7>) v(medium_therm<6>) v(medium_therm<5>)
.print tran v(fine_therm<6>) v(fine_therm<5>) v(fine_therm<4>)

.end
```

**Task 9.3.2: Create Scenario-Specific Decks**
- `autonomous_0p80/autonomous_0p80.sp` (SUPPLY_VOLTAGE=0.80)
- `autonomous_0p95/autonomous_0p95.sp` (SUPPLY_VOLTAGE=0.95)
- `autonomous_1p10/autonomous_1p10.sp` (SUPPLY_VOLTAGE=1.10)

**Task 9.3.3: Freeze Expected Trajectories**
Before running any HSPICE:
- Document expected M/F progression for each scenario
- Hash all three HSPICE decks
- Record in `expected_trajectories.json`:
```json
{
  "autonomous_0p80": {
    "deck_hash": "sha256:...",
    "expected_trajectory": {
      "coarse_boundary": 9,
      "final_M": 7,
      "fine_boundary": 5,
      "final_F": 6,
      "total_probes": 28
    }
  },
  "autonomous_0p95": { ... },
  "autonomous_1p10": { ... }
}
```

**Deliverables:**
- Three HSPICE testbench decks
- `expected_trajectories.json`
- Deck hash verification script

---

### Phase 9.4: Run Autonomous Calibration Simulations
**Duration:** 2-3 days (mostly simulation time)  
**Status:** Not started

#### Workflow

```
For each scenario (0.80V, 0.95V, 1.10V):
    
    iteration = 1
    state = IDLE
    
    while state not in [LOCK, FAIL]:
        # Generate PWL for current iteration
        python behavioral_controller.py \
            --scenario ${scenario} \
            --iteration ${iteration} \
            --prev-results results.json
        
        # Run HSPICE
        hspice autonomous_${scenario}.sp > run_${iteration}.log
        
        # Extract Q result
        Q = parse_hspice_measurement(run_${iteration}.log)
        
        # Update results
        echo "{probe: ${iteration}, Q: ${Q}}" >> results.json
        
        # Check convergence
        if converged:
            state = LOCK
        elif failed:
            state = FAIL
        
        iteration++
    
    # Generate final report
    python generate_trajectory_report.py results.json
```

#### Tasks

**Task 9.4.1: Scenario 1 - autonomous_0p80**
- Run iterative HSPICE simulation
- Expected: ~28 probes, M7/F6 lock
- Simulation time estimate: 3-8 hours total (all iterations)

**Task 9.4.2: Scenario 2 - autonomous_0p95**
- Run iterative HSPICE simulation
- Expected: ~20 probes, M4/F6 lock
- Simulation time estimate: 2-5 hours total

**Task 9.4.3: Scenario 3 - autonomous_1p10**
- Run iterative HSPICE simulation
- Expected: ~20 probes, M2/F9 lock
- Simulation time estimate: 2-5 hours total

**Deliverables:**
- HSPICE simulation results for all three scenarios
- Q trajectory data
- Waveform databases (.tr files)

---

### Phase 9.5: Verify Trajectories and Electrical Audits
**Duration:** 1-2 days  
**Status:** Not started

#### Required Verification (Per Scenario)

**Task 9.5.1: Trajectory Verification**

For autonomous_0p80, verify:
- ✓ M0 through M9 coarse scan
- ✓ Two independent low probes at M9
- ✓ M9→M8 update
- ✓ M8→M7 update
- ✓ Zero probe between two backoffs
- ✓ F0 through F5 fine scan at M7
- ✓ F5 first non-high boundary
- ✓ F5→F6 update
- ✓ F6 guard low
- ✓ Independent F6 hold low
- ✓ Final locked code M7/F6

Repeat for 0.95V (M4/F6) and 1.10V (M2/F9)

**Task 9.5.2: Electrical Audits**

Create Python analysis script to verify from waveforms:

```python
def verify_electrical_audits(waveform_file):
    """Verify all 6 electrical audit criteria"""
    
    audits = {
        'one_sclk_per_probe': True,
        'no_spurious_sclk': True,
        'single_bit_therm_changes': True,
        'correct_reset_waveform': True,
        'consistent_q_capture': True,
        'no_ambiguous_q': True
    }
    
    # Audit 1: Exactly one S_CLK edge per probe
    for probe in probes:
        sclk_edges = count_rising_edges(
            waveform['sense_s_clk'],
            probe.start_time,
            probe.end_time
        )
        if sclk_edges != 1:
            audits['one_sclk_per_probe'] = False
            print(f"FAIL: Probe {probe.id} has {sclk_edges} S_CLK edges")
    
    # Audit 2: No S_CLK during config updates
    for config_update in config_updates:
        sclk_edges = count_rising_edges(
            waveform['sense_s_clk'],
            config_update.start_time,
            config_update.end_time
        )
        if sclk_edges > 0:
            audits['no_spurious_sclk'] = False
            print(f"FAIL: Spurious S_CLK during config update")
    
    # Audit 3: Single-bit thermometer changes
    for transition in therm_transitions:
        bit_changes = count_bit_changes(
            transition.old_value,
            transition.new_value
        )
        if bit_changes != 1:
            audits['single_bit_therm_changes'] = False
            print(f"FAIL: {bit_changes}-bit change detected")
    
    # Audit 4: Reset waveform correctness
    for probe in probes:
        reset_during_sclk = get_value(
            waveform['sense_dff_reset'],
            probe.sclk_edge_time
        )
        if reset_during_sclk != 0:
            audits['correct_reset_waveform'] = False
            print(f"FAIL: dff_reset not low during S_CLK")
    
    # Audit 5: Consistent Q double-sampling
    # (This is in the behavioral controller, verify from logs)
    for probe in probes:
        if probe.q_sample1 != probe.q_sample2:
            audits['consistent_q_capture'] = False
            print(f"FAIL: Inconsistent Q capture at probe {probe.id}")
    
    # Audit 6: No ambiguous Q
    for probe in probes:
        q_voltage = get_value(waveform['q_final'], probe.sample_time)
        if q_voltage < VDD*0.2 or q_voltage > VDD*0.8:
            # Valid logic levels
            pass
        else:
            audits['no_ambiguous_q'] = True
            print(f"FAIL: Ambiguous Q voltage {q_voltage}V")
    
    return audits
```

**Task 9.5.3: Generate Verification Reports**

For each scenario, generate:
- Trajectory verification checklist
- Electrical audit report
- Annotated waveform plots
- Final M/F code confirmation

**Deliverables:**
- `autonomous_0p80/TRAJECTORY_VERIFICATION.md`
- `autonomous_0p95/TRAJECTORY_VERIFICATION.md`
- `autonomous_1p10/TRAJECTORY_VERIFICATION.md`
- `electrical_audits_summary.md`
- Annotated waveform PDFs

---

### Phase 9.6: Generate Phase 9 Final Report
**Duration:** 1 day  
**Status:** Not started

#### Report Sections

1. **Executive Summary**
   - Phase 9 objectives
   - Approach C rationale
   - Three scenarios: PASS/FAIL

2. **Behavioral Controller Implementation**
   - Architecture description
   - Timing parameter extraction from Phase 8B
   - FSM implementation validation
   - PWL generation methodology

3. **Transistor-Level Sensor Integration**
   - Sensor netlist source
   - Interface verification
   - Standalone sensor test results

4. **Autonomous Calibration Results**
   - Scenario 1: 0.80V → M7/F6
   - Scenario 2: 0.95V → M4/F6
   - Scenario 3: 1.10V → M2/F9
   - Probe counts and convergence timing

5. **Trajectory Verification**
   - Detailed trajectory for each scenario
   - Comparison with expected paths
   - FSM state progression validation

6. **Electrical Audit Results**
   - Six audit criteria verification
   - Waveform analysis
   - Protocol compliance confirmation

7. **Phase 9 Exit Criteria Assessment**
   - Testbench rule compliance
   - Autonomous generation of all control signals
   - Trajectory acceptance
   - Electrical audit passage

8. **Phase 9 GO Decision**
   - Synthesizable Startup Calibration Controller: GO/NO-GO
   - Real Circuit Autonomous Startup Calibration: GO/NO-GO

**Deliverables:**
- `analysis/phase9_autonomous_transistor_level/PHASE9_FINAL_REPORT.md`

---

## Phase 10: Freeze and Handoff

**Duration:** 1 day  
**Status:** Not started (pending Phase 9 GO)

### Tasks

**Task 10.1: Record Immutable Hashes**

Freeze all artifacts with SHA-256 hashes:

```bash
#!/bin/bash
# freeze_artifacts.sh

echo "=== FTC Controller Freeze Record ===" > FREEZE_MANIFEST.txt
echo "Date: $(date)" >> FREEZE_MANIFEST.txt
echo "" >> FREEZE_MANIFEST.txt

# RTL source
echo "=== RTL Source ===" >> FREEZE_MANIFEST.txt
find rtl/ -name "*.sv" -exec sha256sum {} \; >> FREEZE_MANIFEST.txt

# Synthesized netlist
echo "=== Synthesized Netlist ===" >> FREEZE_MANIFEST.txt
sha256sum synthesis/netlist/ftc_cal_controller_top_synth.v >> FREEZE_MANIFEST.txt
sha256sum synthesis/netlist/ftc_cal_controller_top_synth.sdf >> FREEZE_MANIFEST.txt
sha256sum synthesis/netlist/ftc_cal_controller_top_synth.sdc >> FREEZE_MANIFEST.txt

# Synthesis constraints
echo "=== Synthesis Scripts ===" >> FREEZE_MANIFEST.txt
sha256sum synthesis/scripts/synthesize_controller.tcl >> FREEZE_MANIFEST.txt

# Autonomous HSPICE decks
echo "=== Phase 9 HSPICE Decks ===" >> FREEZE_MANIFEST.txt
sha256sum analysis/phase9_autonomous_transistor_level/autonomous_*/autonomous_*.sp >> FREEZE_MANIFEST.txt

# Behavioral controller
echo "=== Behavioral Controller ===" >> FREEZE_MANIFEST.txt
sha256sum scripts/behavioral_controller.py >> FREEZE_MANIFEST.txt

echo "" >> FREEZE_MANIFEST.txt
echo "All artifacts frozen and recorded." >> FREEZE_MANIFEST.txt
```

**Task 10.2: Document Final Contracts**

Create `CONTROLLER_CONTRACT.md`:

```markdown
# FTC Calibration Controller - Final Contract

## Controller RTL
- **Files:** rtl/*.sv (5 modules)
- **Hash:** [from manifest]
- **Language:** SystemVerilog IEEE 1800-2017

## Synthesized Netlist
- **File:** synthesis/netlist/ftc_cal_controller_top_synth.v
- **Hash:** [from manifest]
- **Technology:** SMIC 40nm sc9mc_base_rvt_c40
- **Frequency:** 1 GHz (1ns clock period)
- **Area:** 947.55 µm²
- **Cells:** 495 standard cells

## Timing Contract
- **Clock:** External cal_clk, 1 GHz max
- **Critical path:** 0.86 ns (8 logic levels)
- **Setup slack:** +0.02 ns
- **Cycle count:** 300-450 cycles typical

## FSM Semantics
- **States:** 12 (IDLE, COARSE_SEARCH, ..., LOCK, FAIL)
- **Transitions:** [reference rtl/ftc_cal_controller_fsm.sv]

## Operation Sequencer
- **Operations:** PROBE, CONFIG_UPDATE
- **Timing:** [reference rtl/ftc_cal_controller_sequencer.sv]

## Thermometer Register Interface
- **Medium:** 16-bit thermometer, active-high
- **Fine:** 10-bit thermometer, active-low
- **Update:** Single-bit incremental changes only

## Q Double-Sampling Method
- **Implementation:** [reference rtl/q_double_sampler.sv]
- **Agreement requirement:** Both samples must match

## M/F Physical Interface
- **Medium range:** M0-M15 (4-bit binary, 16-bit thermometer)
- **Fine range:** F0-F9 (4-bit binary, 10-bit thermometer)
- **Drive strength:** Standard cell output

## Sensor Reset Interface
- **Signal:** sense_dff_reset
- **Protocol:** High during config, low during S_CLK (frozen cycle)

## Sensor S_CLK Interface
- **Signal:** sense_s_clk
- **Protocol:** One rising edge per probe, width ~50ns @ 100MHz

## Autonomous HSPICE Results
- **0.80V:** M7/F6, 28 probes
- **0.95V:** M4/F6, ~20 probes
- **1.10V:** M2/F9, ~20 probes
```

**Task 10.3: Create Handoff Package**

Package for downstream integration:

```
ftc_controller_handoff/
├── rtl/
│   ├── ftc_cal_controller_top.sv
│   ├── ftc_cal_controller_fsm.sv
│   ├── ftc_cal_controller_sequencer.sv
│   ├── ftc_cal_controller_cfg_regs.sv
│   └── q_double_sampler.sv
├── synthesis/
│   ├── netlist/
│   │   ├── ftc_cal_controller_top_synth.v
│   │   ├── ftc_cal_controller_top_synth.sdf
│   │   └── ftc_cal_controller_top_synth.sdc
│   └── scripts/
│       └── synthesize_controller.tcl
├── verification/
│   ├── phase5_rtl_integration/
│   ├── phase8a_functional_gls/
│   ├── phase8b_timing_gls/
│   └── phase9_autonomous_transistor/
├── reports/
│   ├── PROJECT_SUMMARY.md
│   ├── PHASE7_SYNTHESIS_REPORT.md
│   ├── PHASE8A_REPORT.md
│   ├── PHASE8B_REPORT.md
│   └── PHASE9_FINAL_REPORT.md
├── CONTROLLER_CONTRACT.md
├── FREEZE_MANIFEST.txt
└── README.md
```

**Task 10.4: Archive and Tag**

```bash
# Git tag
git tag -a v1.0-autonomous-controller-frozen \
    -m "FTC Autonomous Calibration Controller - Phase 9 GO"

# Create archive
tar czf ftc_controller_handoff_v1.0.tar.gz ftc_controller_handoff/

# Generate checksums
sha256sum ftc_controller_handoff_v1.0.tar.gz > ftc_controller_handoff_v1.0.sha256
```

**Deliverables:**
- `FREEZE_MANIFEST.txt`
- `CONTROLLER_CONTRACT.md`
- `ftc_controller_handoff/` directory
- Git tag and archive

---

## Timeline Summary

| Phase | Task | Duration | Dependencies |
|-------|------|----------|--------------|
| **9.1** | Extract sensor | 4-8 hours | Prior HSPICE work |
| **9.2** | Behavioral controller | 2-3 days | Phase 8B timing data |
| **9.3** | HSPICE testbenches | 1 day | 9.1, 9.2 |
| **9.4** | Run simulations | 2-3 days | 9.3 (mostly CPU time) |
| **9.5** | Verify & audit | 1-2 days | 9.4 |
| **9.6** | Final report | 1 day | 9.5 |
| **10** | Freeze & handoff | 1 day | Phase 9 GO |
| | | | |
| **TOTAL** | | **8-12 days** | (1.5-2.5 weeks) |

---

## Resource Requirements

### Compute
- Linux workstation with 8+ GB RAM
- HSPICE license
- Estimated CPU time: 20-40 hours total (across all scenarios)

### Software
- Python 3.6+ (numpy, scipy, matplotlib)
- HSPICE (version compatible with SMIC 40nm models)
- Git (for version control and tagging)

### Personnel
- Mixed-signal verification engineer
- Familiarity with HSPICE, Python, FTC protocol
- Estimated effort: 8-12 working days

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Sensor netlist not found | Search prior work systematically, may need to reconstruct |
| Behavioral controller doesn't match gate-level | Use Phase 8B VCD as ground truth, validate timing |
| HSPICE convergence issues | Use previous PWL controller approach as reference |
| Trajectory doesn't match expected | Debug with waveform analysis, may indicate real sensor issue |
| Simulation too slow | Reduce transient analysis precision if needed |

---

## Success Criteria

### Phase 9 Complete When:
- ✓ All three scenarios run to completion
- ✓ All three converge to expected M/F codes
- ✓ All trajectory requirements verified
- ✓ All six electrical audits pass
- ✓ Final report documents GO decision

### Phase 10 Complete When:
- ✓ All artifacts hashed and frozen
- ✓ Controller contract documented
- ✓ Handoff package created
- ✓ Git tagged and archived

---

## Next Actions

**To begin Phase 9.1:**
1. Search for frozen transistor-level sensor netlist
2. Extract sensor subcircuit definition
3. Create standalone sensor test

**Command to start:**
```bash
cd /home/zhupl25/chiplet_side_channel/chiplet_gds_data/power_macro/delay_chain/ftc/controller
mkdir -p analysis/phase9_autonomous_transistor_level/sensor
cd analysis/phase9_autonomous_transistor_level/sensor

# Search for sensor netlist
find ../../.. -name "*.sp" | xargs grep -l "ftc_sensor\|delay_chain" | head -10
```

---

**Document Status:** Ready for Phase 9.1 execution  
**Approval Required:** Proceed with Approach C implementation?  
**Estimated Completion:** 1.5-2.5 weeks from start
