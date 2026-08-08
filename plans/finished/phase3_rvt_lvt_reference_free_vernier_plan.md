# Phase 3 RVT/LVT Reference-Free Vernier Sensor Execution Plan

## Objective

Create a new implementation under `delay_chain/phase3/` that replaces the separate `VDD_REF/VSS_REF` sensing reference with a same-rail RVT/LVT differential Vernier structure.

The Phase 3 sensing path shall use only `VDD_A/VSS_A` and shall exploit the different voltage-delay sensitivities of RVT and LVT standard cells. The target implementation remains a 32-stage Vernier sensor with a real standard-cell DFF comparator bank and a digitally encoded sensor code.

Phase 3 shall answer one primary question:

> Can an RVT/LVT same-rail differential delay structure provide a stable and useful voltage-dependent sensor code without a separate reference supply?

Do not add CUSUM, glitch guard logic, multi-lane sampling, PVT sweeps, Monte Carlo, or other later-stage features in this phase.

---

## Step 1 - Create the Phase 3 workspace and configuration

Create:

```text
delay_chain/phase3/
├── phase3_config.json
├── discovery/
├── spice/
│   └── includes/
├── scripts/
├── runs/
├── rtl/
├── tests/
└── reports/
```

Create `delay_chain/phase3/phase3_config.json` with the initial constants:

```json
{
  "technology": "SMIC40LL",
  "corner": "tt",
  "temperature_c": 25.0,
  "vnom_v": 1.1,
  "last_pass_v": 1.054061327707,
  "first_violation_v": 1.047473942801,
  "coarse_vdd_start_v": 1.04,
  "coarse_vdd_stop_v": 1.10,
  "coarse_vdd_step_v": 0.005,
  "fine_vdd_start_v": 1.04,
  "fine_vdd_stop_v": 1.10,
  "fine_vdd_step_v": 0.0005,
  "stages": 32,
  "rvt_inverter_cell": "INV_X0P5M_A9TR40",
  "rvt_dff_cell": "DFFRPQ_X0P5M_A9TR40",
  "rvt_buffer_cell": "BUF_X0P7M_A9TR40",
  "rvt_mux_cell": "MXT2_X0P5M_A9TR40",
  "target_nominal_code": 16,
  "acceptable_nominal_code_min": 14,
  "acceptable_nominal_code_max": 18
}
```

Do not hard-code an LVT cell name yet. It must be discovered from the installed SMIC40LL LVT library.

### Completion condition

- `delay_chain/phase3/` exists with the directory structure above.
- `phase3_config.json` parses successfully.

---

## Step 2 - Discover real LVT inverter cells

Implement:

```text
delay_chain/phase3/scripts/discover_lvt_cells.py
```

Starting from the known SMIC40LL library installation, locate the LVT standard-cell CDL and Verilog libraries.

Search only for inverter cells needed for the first experiment. Do not build a general standard-cell discovery framework.

For every usable LVT inverter candidate, record:

```text
cell name
CDL source path
Verilog source path
CDL port order
Verilog port order
drive strength
```

Write:

```text
delay_chain/phase3/discovery/lvt_inverter_candidates.json
delay_chain/phase3/discovery/lvt_inverter_candidates.md
```

Retain at most three practical LVT inverter candidates, prioritizing cells closest in size/drive class to the RVT `INV_X0P5M_A9TR40` while also keeping immediate neighboring drive strengths if they exist.

If RVT and LVT libraries reuse identical subcircuit names, generate local renamed copies only for the cells used by Phase 3 under:

```text
delay_chain/phase3/spice/includes/
```

For example:

```text
RVT_<cell>
LVT_<cell>
```

Do not rewrite entire libraries.

Create:

```text
delay_chain/phase3/discovery/selected_cells.json
```

containing the RVT cells already used by the design and the discovered LVT inverter candidates.

### Completion condition

- At least one real LVT inverter has been found from the installed library.
- Its CDL and Verilog definitions are traceable.
- `selected_cells.json` contains the cells required for the next step.

---

## Step 3 - Characterize RVT/LVT single-stage voltage sensitivity

Build a minimal non-inverting two-inverter delay stage:

```text
input -> INV -> INV -> output
```

Use:

```text
RVT stage = 2 x RVT inverter
LVT stage = 2 x LVT inverter
```

Both test structures must use identical:

```text
VDD
VSS
input waveform
input slew
output load
measurement thresholds
```

Implement:

```text
delay_chain/phase3/scripts/run_cell_sensitivity.py
```

Run the first sweep from:

```text
1.040 V to 1.100 V
step = 5 mV
TT, 25 C
```

Measure both propagation directions and calculate:

```text
t_stage(V) = (t_rise(V) + t_fall(V)) / 2
```

For every LVT candidate calculate:

```text
t_R(V)
t_L(V)
delta_t(V) = t_R(V) - t_L(V)
```

Also calculate the differential change between nominal and the first timing-violation anchor:

```text
delta_t_swing = delta_t(1.047473942801 V) - delta_t(1.1 V)
```

Write:

```text
delay_chain/phase3/runs/cell_sensitivity/cell_delay.csv
delay_chain/phase3/reports/CELL_SENSITIVITY.md
```

The report shall contain plots or tabulated curves for:

```text
RVT delay vs VDD
LVT delay vs VDD
RVT-LVT differential delay vs VDD
```

### Completion condition

At least one RVT/LVT pair shows a clear and continuous change in differential delay as VDD changes.

Do not yet build a 32-stage Vernier chain.

---

## Step 4 - Match the nominal RVT/LVT stage delays

Keep the RVT sensing stage fixed:

```text
2 x INV_X0P5M_A9TR40
```

Tune only the LVT companion path.

For the retained LVT inverter candidates, evaluate:

```text
LVT inverter candidate
x
dummy load count = 0, 1, 2, 3
```

Use an LVT inverter input as the dummy capacitive load. The dummy inverter output does not participate in the signal path.

Implement:

```text
delay_chain/phase3/scripts/run_pair_matching.py
```

For each candidate, initially simulate only:

```text
1.100000000000 V
1.054061327707 V
1.047473942801 V
```

Calculate:

```text
E_nom = abs(t_R(1.1 V) - t_L(1.1 V))
```

and:

```text
G_droop = abs(delta_t(1.047473942801 V) - delta_t(1.1 V))
```

Generate a simple comparison table containing:

```text
candidate ID
LVT cell
dummy count
t_R_nom
t_L_nom
nominal gap
differential change at last-pass voltage
differential change at first-violation voltage
```

Do not introduce a complicated weighted scoring function.

Select at most three candidates that jointly provide:

- small nominal delay mismatch, and
- large voltage-dependent differential-delay change.

Write:

```text
delay_chain/phase3/runs/pair_matching/pair_results.csv
delay_chain/phase3/reports/PAIR_SELECTION.md
```

### Completion condition

A short list of no more than three practical RVT/LVT stage pairs exists for 32-stage evaluation.

---

## Step 5 - Build the ideal 32-stage RVT/LVT Vernier

For each retained candidate, create a same-rail 32-stage structure:

```text
                         VDD_A / VSS_A
                              |
                 +------------+------------+
                 |                         |
           32-stage RVT chain        32-stage LVT chain
                 |                         |
           R[0..32]                   L[0..32]
```

Do not add real DFFs yet.

Use HSPICE to measure the arrival time at every corresponding stage:

```text
T_R[i]
T_L[i]
```

Construct an ideal thermometer decision in Python from those arrival times.

Introduce one ideal launch offset only to place the nominal crossing near the middle of the 32-stage chain.

Estimate the required initial offset from:

```text
ideal_launch_offset ~= 16 x abs(t_R_nom - t_L_nom)
```

Then evaluate only a small local sweep around that estimate, for example:

```text
offset_estimate - 20 ps
offset_estimate - 10 ps
offset_estimate
offset_estimate + 10 ps
offset_estimate + 20 ps
```

The nominal target is:

```text
code(1.1 V) in [14, 18]
```

Evaluate the coarse VDD range using the selected offset and confirm that the transition position moves consistently in one direction as VDD falls.

Do not require a particular raw polarity. Record the polarity and normalize it later.

Write:

```text
delay_chain/phase3/runs/ideal_vernier/ideal_vernier.csv
delay_chain/phase3/reports/IDEAL_VERNIER.md
```

Select one final RVT/LVT candidate and write these values into `phase3_config.json`:

```text
selected_lvt_cell
selected_dummy_load_count
ideal_launch_offset_ps
code_polarity
```

### Completion condition

One RVT/LVT pair has been selected and its 32-stage ideal Vernier transition:

- lies near the middle at nominal VDD, and
- moves consistently with droop.

From this point onward, stop carrying multiple RVT/LVT candidates.

---

## Step 6 - Replace ideal comparison with a real same-rail DFF bank

Build a real 32-DFF comparator bank using:

```text
DFFRPQ_X0P5M_A9TR40
```

All DFFs shall use:

```text
VDD = VDD_A
VSS = VSS_A
```

There shall be no `VDD_REF` or `VSS_REF` in this experiment.

Connect the RVT and LVT paths to D and CK according to the propagation direction found in Step 5.

If the raw thermometer polarity is opposite to the existing decoder convention, normalize the bit polarity before decoding rather than redesigning the Vernier structure.

Initially run only:

```text
1.100000000000 V
1.054061327707 V
1.047473942801 V
```

Record:

```text
raw thermometer word
corrected thermometer word
sensor code
bubble count
code valid
```

### Completion condition

The real DFF bank produces:

- a nominal code near the center of the 32-stage range,
- a code change at the last-pass voltage,
- a further code movement in the same direction at the first-violation voltage.

Do not run the full fine sweep yet.

---

## Step 7 - Replace ideal launch offset with physical same-rail calibration

Replace the ideal time offset with a physical calibration network using the existing standard-cell types:

```text
BUF_X0P7M_A9TR40
MXT2_X0P5M_A9TR40
```

Implement an 8-tap calibration path selected by:

```text
CAL_SEL[2:0]
```

All launch-calibration cells shall use:

```text
VDD_A / VSS_A
```

Do not create a separate reference power domain.

At 1.1 V, run all eight `CAL_SEL` values and choose the setting whose real-DFF sensor code is closest to 16.

Write:

```text
delay_chain/phase3/runs/launch_calibration/calibration.csv
```

Update `phase3_config.json` with:

```text
selected_cal_sel
baseline_code
```

### Completion condition

A physical same-rail `CAL_SEL` setting places the nominal real-DFF sensor code inside:

```text
[14, 18]
```

---

## Step 8 - Run the complete reference-free voltage-to-code sweep

Use the final physical structure:

```text
same-rail launch calibration
+ 32-stage RVT chain
+ 32-stage LVT chain
+ 32 real DFFs
+ decoder
```

All physical frontend cells use only:

```text
VDD_A / VSS_A
```

Run:

```text
1.040 V to 1.100 V
step = 0.5 mV
TT, 25 C
```

For every point record:

```text
VDD
raw thermometer word
sensor code
bubble count
code valid
```

Write:

```text
delay_chain/phase3/runs/voltage_sweep/voltage_code.csv
```

Generate:

```text
sensor_code vs VDD
sensor_code - baseline_code vs droop magnitude
RVT-LVT differential delay vs VDD
```

Calculate:

```text
delta_code_last = code(1.054061327707 V) - baseline_code
delta_code_crit = code(1.047473942801 V) - baseline_code
```

Normalize the residual direction using the previously recorded polarity:

```text
residual(V) = polarity x (code(V) - baseline_code)
```

Choose `polarity` so that a larger droop produces a larger positive residual.

### Completion condition

The final physical sensor produces a generally monotonic and usable voltage-to-code response over the target range.

---

## Step 9 - Run one RVT/RVT same-rail control

Build one control sensor using:

```text
RVT path A
RVT path B
same VDD_A / VSS_A
same 32-stage depth
same launch-calibration methodology
same real DFF bank
```

Run the same fine VDD sweep.

Compare the voltage-to-code sensitivity of:

```text
RVT/LVT same-rail sensor
vs
RVT/RVT same-rail control
```

The key comparison is:

```text
abs(dC_RVT_LVT / dVDD) > abs(dC_RVT_RVT / dVDD)
```

Write:

```text
delay_chain/phase3/reports/RVT_LVT_VS_RVT_RVT.md
```

Do not add more control architectures in Phase 3.

### Completion condition

The RVT/LVT pair shows a clearly stronger differential voltage response than the same-rail RVT/RVT control.

---

## Step 10 - Package the selected Phase 3 structure into RTL

Only after the physical SPICE structure has been selected and verified, create:

```text
delay_chain/phase3/rtl/phase3_sensor.sv
delay_chain/phase3/rtl/phase3_frontend_struct.sv
delay_chain/phase3/rtl/phase3_rvt_stage_struct.sv
delay_chain/phase3/rtl/phase3_lvt_stage_struct.sv
delay_chain/phase3/rtl/phase3_comparator_struct.sv
delay_chain/phase3/rtl/phase3_launch_cal_struct.sv
delay_chain/phase3/rtl/phase3_decoder.sv
delay_chain/phase3/rtl/phase3_calibration_pkg.sv
```

The top-level interface shall contain only the local power rail:

```systemverilog
module phase3_sensor (
    input  logic       clk_i,
    input  logic       rst_i,
    input  logic       sample_req_i,

    inout  wire        vdd_a_i,
    inout  wire        vss_a_i,

    output logic [5:0] sensor_code_o,
    output logic       code_valid_o,
    output logic       sample_valid_o
);
```

There shall be no:

```text
vdd_ref_i
vss_ref_i
```

The physical frontend shall instantiate the selected real SMIC40LL standard cells directly.

The digital backend remains limited to:

```text
raw thermometer capture
-> local polarity normalization if required
-> majority correction
-> transition encoding
-> sensor_code
-> code_valid
```

Do not add CUSUM or glitch-capture logic in Phase 3.

---

## Step 11 - Add the minimum regression tests

Create only the tests needed to preserve the implementation contract:

```text
LVT cell discovery succeeds
phase3_config.json parses
selected HSPICE deck contains both RVT and LVT stages
final physical deck contains no VDD_REF/VSS_REF
decoder handles legal thermometer words
selected CAL_SEL produces a nominal center-region code
RTL elaborates
SPICE raw-code replay matches the RTL decoder
```

Do not build a large verification framework in this phase.

### Completion condition

All Phase 3 tests pass and SPICE-to-RTL decoder replay is bit-exact for the retained vectors.

---

## Step 12 - Generate the Phase 3 result report

Create one main report:

```text
delay_chain/phase3/reports/PHASE3_RESULT.md
```

It shall answer exactly these questions:

1. What RVT and LVT cells were selected?
2. How do their stage delays change with VDD?
3. What LVT loading was selected to match nominal delay?
4. What is the calibrated nominal sensor code?
5. How does sensor code change with VDD and at the two timing anchors?
6. Is RVT/LVT more voltage-sensitive than the RVT/RVT same-rail control?
7. Does the final implementation operate without `VDD_REF/VSS_REF`?

Include links to the compact CSV/JSON evidence produced by each step.

---

## Phase 3 completion criteria

Phase 3 is complete when all of the following are true:

1. The selected LVT inverter is taken from a real installed SMIC40LL LVT library.
2. RVT/LVT differential delay changes consistently with VDD.
3. A physical same-rail calibration setting places the nominal 1.1 V code in `[14, 18]`.
4. The physical sensor code is generally monotonic over `1.04-1.10 V`.
5. The first-violation voltage produces a target code change of at least three codes relative to nominal.
6. The RVT/LVT same-rail sensor is clearly more voltage-sensitive than the RVT/RVT same-rail control.
7. The final HSPICE frontend and RTL top level contain no `VDD_REF` or `VSS_REF` interface.
8. The physical frontend uses real SMIC40LL standard cells rather than behavioral delay elements.

---

## Required execution order

Codex shall execute Phase 3 in this order and shall not skip ahead to the RTL packaging step before the physical candidate has been selected:

```text
create phase3 workspace
        |
discover real LVT inverter
        |
measure RVT/LVT single-stage delay vs VDD
        |
match nominal RVT/LVT stage delays
        |
select a short RVT/LVT candidate list
        |
build ideal 32-stage same-rail Vernier
        |
select one RVT/LVT pair and polarity
        |
replace ideal comparison with real same-rail DFF bank
        |
replace ideal launch offset with physical CAL_SEL
        |
run complete 1.04-1.10 V voltage-to-code sweep
        |
run one RVT/RVT same-rail control
        |
package the selected structure into RTL
        |
run minimum regression and SPICE-to-RTL replay
        |
generate PHASE3_RESULT.md
```

The intended technical direction is:

```text
RVT/LVT device-level voltage sensitivity
        -> 32-stage Vernier spatial accumulation
        -> same-rail reference-free sensor code
```
