# Phase 3 RVT/LVT Reference-Free Vernier Result

## Scope and Decision

Phase 3 evaluates a same-rail RVT/LVT differential Vernier sensor.  The
physical frontend uses only `VDD_A/VSS_A`, a real 8-tap BUF/MXT2 launch
calibration path, two 32-stage inverter chains, and 32 real
`DFFRPQ_X0P5M_A9TR40` comparators.  No separate reference supply, CUSUM,
multi-lane sampler, PVT sweep, or Monte Carlo logic was added.

The selected implementation satisfies the Phase 3 completion criteria.  The
full physical sweep contains 121 grid points at 0.5 mV plus the two exact
timing-anchor voltages.  One isolated one-code local reversal is retained in
the CSV at 1.0765 V to 1.0760 V; the response remains generally monotonic and
all thermometer words are valid after the declared majority correction.

## Answers to the Seven Required Questions

### 1. Selected RVT and LVT cells

The RVT path uses `INV_X0P5M_A9TR40` and the selected real installed LVT
companion is `INV_X0P5M_A9TL40`.  The LVT CDL and Verilog source paths are
recorded in [selected_cells.json](../discovery/selected_cells.json) and the
three retained LVT candidates are listed in
[lvt_inverter_candidates.json](../discovery/lvt_inverter_candidates.json).

### 2. Stage delay versus VDD

The Step-3 two-inverter measurements use identical local rails, waveform,
load, threshold, TT corner, and 25 C temperature.  For the selected LVT cell:

| VDD | RVT stage | LVT stage | RVT-LVT differential |
|---:|---:|---:|---:|
| 1.100 V | 20.2578 ps | 16.1880 ps | 4.0698 ps |
| 1.047473942801 V | 22.0581 ps | 17.3942 ps | 4.6638 ps |
| 1.040 V | 22.3484 ps | 17.5817 ps | 4.7667 ps |

Both stages slow as VDD falls.  The RVT-LVT differential increases
continuously across the measured grid; its first-violation-minus-nominal swing
is 0.5940712 ps for the selected cell.  The complete table is in
[cell_delay.csv](../runs/cell_sensitivity/cell_delay.csv), with the candidate
comparison in [CELL_SENSITIVITY.md](CELL_SENSITIVITY.md).

### 3. Selected LVT loading

The RVT reference stage remained fixed at two RVT inverters.  One private
`INV_X0P5M_A9TL40` input dummy was added to each LVT stage.  At 1.1 V this
selected d1 pair measured RVT=20.17638222 ps, LVT=17.79107649 ps, and a
2.38530573 ps nominal gap; it retained a 0.56800045 ps differential change at
the first-violation anchor.  The full no-weighted-score comparison is in
[pair_results.csv](../runs/pair_matching/pair_results.csv) and
[PAIR_SELECTION.md](PAIR_SELECTION.md).

### 4. Calibrated nominal sensor code

The physical same-rail launch network selected `CAL_SEL=1`.  At 1.1 V the real
DFF bank produced raw word `11111111111111111100000000000000`; the configured
polarity inversion normalized it to
`00000000000000000011111111111111`, yielding code **18**, zero bubbles, and a
valid word.  All eight calibration settings are retained in
[calibration.csv](../runs/launch_calibration/calibration.csv); the frozen
configuration is [phase3_config.json](../phase3_config.json).

### 5. Sensor code versus VDD and timing anchors

The final physical RVT/LVT sensor was swept at TT/25 C from 1.040 V through
1.100 V in 0.5 mV steps, with exact anchor runs at 1.054061327707 V and
1.047473942801 V.  The code moved from 18 at nominal to 30 at last-pass
(`delta_code_last=+12`) and 32 at first-violation
(`delta_code_crit=+14`).  The low-end 1.040 V code is 32.  Every point had
zero reset failures, zero corrected bubbles, and `code_valid=1`.

The complete raw/corrected words, code, residual, final-tap RVT/LVT crossing
difference, and measurement-file provenance are in
[voltage_code.csv](../runs/voltage_sweep/voltage_code.csv).  The explicit
monotonicity and anchor gates are in
[voltage_summary.json](../runs/voltage_sweep/voltage_summary.json), and the
decimated curve is in [VOLTAGE_SWEEP.md](VOLTAGE_SWEEP.md).

### 6. Comparison with the same-rail RVT/RVT control

The control uses RVT path A and RVT path B, the same one-input dummy-load
method, calibration network, 32-stage depth, real DFF bank, voltage grid, and
local rails.  Its code remained 2 at every voltage, so its endpoint
`abs(dC/dVDD)` is 0 code/V.  RVT/LVT spans 14 codes over the same 60 mV and has
`abs(dC/dVDD)=233.333333` code/V.  Thus the required strict inequality is

`abs(dC_RVT_LVT/dVDD) > abs(dC_RVT_RVT/dVDD)`.

The control raw vectors and crossing measures are in
[voltage_code.csv](../runs/voltage_sweep_rvt_rvt/voltage_code.csv), with the
gate in [voltage_summary.json](../runs/voltage_sweep_rvt_rvt/voltage_summary.json)
and the direct comparison in [RVT_LVT_VS_RVT_RVT.md](RVT_LVT_VS_RVT_RVT.md).

### 7. Operation without `VDD_REF/VSS_REF`

The final HSPICE deck contains only `V_VDD_A` and `V_VSS_A`; all inverter,
BUF, MXT2, DFF, and well connections are local `VDD_A/VSS_A`.  The top RTL
interface has only `vdd_a_i` and `vss_a_i`; no `vdd_ref_i` or `vss_ref_i`
identifier exists in [phase3_sensor.sv](../rtl/phase3_sensor.sv).  The complete
physical structure is in [phase3_frontend_struct.sv](../rtl/phase3_frontend_struct.sv)
and its stage/comparator/calibration wrappers.  The final nominal deck is
checked directly by [test_phase3_contract.py](../tests/test_phase3_contract.py).

## RTL and Regression Evidence

The selected physical structure is packaged in:

- [phase3_sensor.sv](../rtl/phase3_sensor.sv)
- [phase3_frontend_struct.sv](../rtl/phase3_frontend_struct.sv)
- [phase3_rvt_stage_struct.sv](../rtl/phase3_rvt_stage_struct.sv)
- [phase3_lvt_stage_struct.sv](../rtl/phase3_lvt_stage_struct.sv)
- [phase3_comparator_struct.sv](../rtl/phase3_comparator_struct.sv)
- [phase3_launch_cal_struct.sv](../rtl/phase3_launch_cal_struct.sv)
- [phase3_decoder.sv](../rtl/phase3_decoder.sv)
- [phase3_calibration_pkg.sv](../rtl/phase3_calibration_pkg.sv)

The minimum regression ran six tests successfully.  VCS elaboration used
task-owned power-aware port stubs because the installed vendor Verilog file
contains mutually exclusive duplicate views; the synthesizable RTL still
instantiates the real SMIC40LL cell names and power pins.  Decoder replay was
bit-exact for all 123 retained HSPICE raw words plus two legal endpoint words.
Compiler collateral and raw replay files are confined to
[runs/rtl_elaboration](../runs/rtl_elaboration).

## Evidence Index

- [lvt_inverter_candidates.md](../discovery/lvt_inverter_candidates.md)
- [CELL_SENSITIVITY.md](CELL_SENSITIVITY.md)
- [PAIR_SELECTION.md](PAIR_SELECTION.md)
- [IDEAL_VERNIER.md](IDEAL_VERNIER.md)
- [REAL_DFF.md](REAL_DFF.md)
- [VOLTAGE_SWEEP.md](VOLTAGE_SWEEP.md)
- [RVT_LVT_VS_RVT_RVT.md](RVT_LVT_VS_RVT_RVT.md)
- [phase3_config.json](../phase3_config.json)
