# Stage 2A: Vernier Sensor RTL Packaging and Synthesizable Macro Boundary Plan

## 1. Objective

Convert the currently validated SMIC40LL SPICE Vernier sensor structure into a reusable macro-level implementation boundary.

Stage 2A does not implement CUSUM yet. The output of this stage is a stable digital sensor interface consumed by the future `cusum_V07_H008` detector.

Final interface target:

```
VDD_A/VSS_A local power domain
        |
        v
+--------------------------+
|     vernier_sensor       |
|                          |
| physical delay frontend  |
| comparator DFF bank      |
| digital decoder backend  |
+--------------------------+
        |
        +--> sensor_code[5:0]
        +--> code_valid
        +--> sample_valid
        +--> sensor_fault
```

## 2. Frozen Electrical Contract

Do not change the validated Phase-2 Vernier characterization.

Frozen parameters:

```
Technology : SMIC40LL
Sensor     : 32-stage Vernier
Sense chain:
    2 x INV_X0P5M_A9TR40 per stage
    power = VDD_A/VSS_A

Reference chain:
    2 x INV_X0P5M_A9TR40 per stage
    dummy_load_count = 1
    power = VDD_REF/VSS_REF

Comparator:
    DFFRPQ_X0P5M_A9TR40
    D = sense_i
    CK = reference_i
    R = sensor_reset
    Q = raw_code[i]

Calibration:
    CAL_SEL = 2
    baseline sensor_code = 15

Thermometer encoding:
    0*1*

Code:
    sensor_code = first_one_position
```

The physical delay chain is not replaced by behavioral delays.
No `#delay` constructs are allowed.

## 3. Repository Structure

Create:

```
delay_chain/phase2_vernier/rtl/

    vernier_sensor.sv
    vernier_frontend_struct.sv
    vernier_sense_stage_struct.sv
    vernier_reference_stage_struct.sv
    vernier_comparator_struct.sv
    vernier_launch_cal_struct.sv
    vernier_sample_adapter.sv

    vernier_sensor_digital_backend.sv
    vernier_sensor_calibration_pkg.sv
```

Existing digital backend should be reused and incrementally adapted.

## 4. Step 1: Physical Stage Wrappers

Implement structural wrappers matching validated SPICE topology.

### vernier_sense_stage_struct.sv

Requirements:

- instantiate two SMIC40LL inverter cells;
- expose VDD_A/VSS_A explicitly;
- preserve hierarchy;
- prevent synthesis removal.

Required synthesis attributes:

```
keep_hierarchy
keep
 dont_touch
```

### vernier_reference_stage_struct.sv

Requirements:

- instantiate reference inverter chain;
- preserve dummy inverter load;
- dummy output must not be optimized away.

### vernier_comparator_struct.sv

Instantiate:

```
DFFRPQ_X0P5M_A9TR40
```

No behavioral always_ff replacement is allowed.

## 5. Step 2: Implement Physical Launch Calibration

Current calibration uses an ideal launch offset. Replace it with a structural implementation.

Implement:

```
vernier_launch_cal_struct.sv
```

Requirements:

- use selected SMIC40LL delay/mux cells;
- provide physical tap selection;
- implement CAL_SEL=2 path;
- characterize actual delay through HSPICE.

Do not assume:

```
one buffer = fixed ps
```

The contract is:

```
CAL_SEL=2 -> baseline sensor_code=15
```

not a fixed abstract delay number.

## 6. Step 3: Top-Level Physical Frontend

Create:

```
vernier_frontend_struct.sv
```

Instantiate:

```
32 sense stages
32 reference stages
32 comparator DFFs
launch calibration
```

Outputs:

```
raw_code[31:0]
```

No thermometer decoding in this module.

## 7. Step 4: Digital Backend Adaptation

Reuse:

```
vernier_sensor_digital_backend.sv
```

Required changes:

Current:

```
capture_clk
sample_done(level)
```

Target:

```
clk
capture_enable
sample_valid(pulse)
```

Keep:

- majority bubble correction;
- bubble counting;
- leading-zero encoder;
- code_valid.

The backend output must remain:

```
sensor_code[5:0]
code_valid
sample_valid
```

## 8. Step 5: Final Macro Wrapper

Implement:

```
vernier_sensor.sv
```

Responsibilities:

- connect physical frontend;
- connect digital backend;
- expose clean macro interface;
- hide raw taps from upper modules.

Interface:

```
clk_i
rst_i
sample_req_i

sensor_code_o[5:0]
code_valid_o
sample_valid_o
sensor_fault_o
```

CUSUM must only see this interface.

## 9. Verification Plan

### 9.1 Digital decoder equivalence

Verify:

```
Python thermometer decoder
        ==
SystemVerilog backend
```

Vectors:

- all-zero
- all-one
- ideal thermometer words
- single bubbles
- multiple bubbles
- invalid words

### 9.2 SPICE raw-Q replay

Input:

```
HSPICE raw_q[31:0]
```

Compare:

```
SPICE decode
RTL decode
```

Requirement:

```
mismatch = 0
```

### 9.3 Calibration verification

After structural launch implementation:

Run HSPICE sweep.

Check:

```
CAL_SEL=2
baseline_code=15
```

## 10. Synthesis Constraints

Separate two regions.

### Physical sensor region

Must preserve:

- inverter chain;
- dummy loads;
- comparator DFFs;
- launch structure.

Disable:

```
logic optimization
retiming
buffer replacement
cell collapsing
```

### Digital backend region

Normal synthesis allowed.

Report separately:

- physical frontend cell count;
- backend synthesized area;
- total macro area.

## 11. Timing Methodology

Do not use normal STA to optimize Vernier delay comparison paths.

Use:

```
SPICE characterization:
    sense/reference timing difference

STA:
    digital backend only
```

The sensor contribution is evaluated by:

```
VDD_A
  -> delay difference
  -> thermometer code
  -> sensor_code
```

## 12. Required Reports

Generate:

```
reports/

VERNIER_STAGE2A_STRUCTURE.md
VERNIER_STAGE2A_CALIBRATION.md
VERNIER_STAGE2A_RTL_EQUIVALENCE.md
VERNIER_STAGE2A_SYNTHESIS.md
VERNIER_STAGE2A_SIGNOFF.md
```

## 13. Stage 2A Gate

Stage 2A passes only when:

- structural frontend exists;
- launch calibration is physical, not ideal;
- CAL_SEL=2 produces baseline code 15;
- digital backend matches Python reference;
- SPICE raw-Q replay matches RTL;
- synthesis preserves physical sensor structure;
- macro exports stable `sensor_code/code_valid/sample_valid` interface.

After Stage 2A completion, proceed to:

```
Stage 2B:
cusum_V07_H008 RTL implementation
```
