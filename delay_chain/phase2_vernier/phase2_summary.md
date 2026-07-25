# Phase 2 Differential Vernier Sensor Summary

## Scope and timing baseline

This report records the completed Phase 2 work through the real-DFF,
cross-domain, and isolated-reference-island experiments.  The design point is
anchored only to the 765 MHz r3 result; the historical 770 MHz result is not
used anywhere in the Phase 2 configuration or conclusions.

| Item | Value | Evidence |
|---|---:|---|
| Clock frequency | 765 MHz | `phase2_config.json` timing anchor |
| Last passing point | 35 RO banks at `1.054061327707 V` | `phase2_config.json` |
| First violation point | 40 RO banks at `1.047473942801 V` | `phase2_config.json` |
| First-violation worst slack | `-0.000810029733 ns` | `phase2_config.json` |
| Process/corner/temperature | SMIC40LL TT, 25 C | `phase2_config.json` |

All standard-cell SPICE experiments use the discovered SMIC40LL CDL models and
the explicit local well-rail connections documented in
`discovery/selected_cells.json`.

## Completed steps and verification

| Plan step | Implemented result | Verification |
|---|---|---|
| 0. Phase 1 reuse | Phase 2 inherits the Phase 1 model, CDL, HSPICE path, and timing anchor through `phase2_config.json`. | Phase 1 tests remain passing; no Phase 1 result was modified. |
| 1. Delay extraction | The measured first non-inverting stage is `12.03 ps` at nominal and `13.11 ps` at the first-violation voltage, giving `epsilon=1.08 ps` and `8.977556110%` increase. | [`reports/phase1_delay_delta.md`](reports/phase1_delay_delta.md) and the 9-row anchor run. |
| 2. Cell discovery | Selected DFF `DFFRPQ_X0P5M_A9TR40`, MUX `MXT2_X0P5M_A9TR40`, and buffer candidate `BUF_X0P7M_A9TR40`; no level shifter was invented because none was found in the configured base-rvt CDL. | [`discovery/dff_candidates.md`](discovery/dff_candidates.md), [`discovery/mux_candidates.md`](discovery/mux_candidates.md), [`discovery/selected_cells.json`](discovery/selected_cells.json). |
| 3-4. Ideal Vernier and candidate selection | 1,107 HSPICE arrival scenarios were scanned over M, dummy loads, voltage, launch offset, and guard sensitivity. The retained candidates are `m32_d2_offset_+0.0`, `m32_d3_offset_+0.5`, and `m32_d1_offset_+1.0`. | [`runs/ideal_arrival_fine_20260724_r1/selection_ideal.md`](runs/ideal_arrival_fine_20260724_r1/selection_ideal.md), `completion.rpt=status=PASS`. |
| 5. Real DFF bank | 12 real-DFF HSPICE scenarios were run. Candidate summaries report nominal/first-violation codes of `24/32` (delta 8), `21/27` (delta 6), and `32/32` (delta 0), respectively. All captured words are bubble-free and all reset checks pass. | [`runs/dff_sweep_20260724_r3/dff_candidate_summary.json`](runs/dff_sweep_20260724_r3/dff_candidate_summary.json), [`runs/dff_sweep_20260724_r3/dff_raw_metrics.csv`](runs/dff_sweep_20260724_r3/dff_raw_metrics.csv). |
| 6. Decoder/reference model | The decoder implements majority filtering, leading-zero encoding, bubble counting, and explicit validity reporting. | 9 Phase 2 Python tests, including ideal, single-bubble, double-bubble, all-zero, and all-one vectors. |
| 7. Launch calibration | For M=32 and one reference dummy load, `CAL_SEL=2` / `20 ps` was selected with baseline code `15` and variation `0` over 32 samples; every configured tap completed with zero median bubbles. | [`runs/dff_calibration_20260724_r1/calibration_result.json`](runs/dff_calibration_20260724_r1/calibration_result.json), 256-scenario `completion.rpt=status=PASS`. |
| 8. Cross-domain input | With DFF supply fixed at `VDD_REF=1.1 V`, static 0/1 decisions are correct for every `VDD_A` point from `0.95 V` to `1.10 V`. The `-5 ps` setup-boundary cases fail as an intentional timing-constraint witness, while the separated static cases pass. | [`runs/cross_domain_20260724_r2/cross_domain_metrics.csv`](runs/cross_domain_20260724_r2/cross_domain_metrics.csv), 51-scenario `completion.rpt=status=PASS`. |
| 9. Isolated reference island | The selected island is `R_ISO=1 ohm`, `C_REF=10 pF`. At the 40-bank anchor, `VDD_A,min=1.0475 V`, `VDD_REF,min=1.0999 V`, `VDD_REF(3.5 ns)=1.1000 V`, and upstream peak current is `76.49 uA`. | [`reports/reference_island_report.md`](reports/reference_island_report.md), [`runs/reference_island_20260724_r1/reference_island_selection.json`](runs/reference_island_20260724_r1/reference_island_selection.json), 16-point `completion.rpt=status=PASS`. |
| Direct VDD_A-to-code characterization | The calibrated M=32/dummy=1/CAL_SEL=2/20 ps circuit was simulated at 301 0.5 mV grid points plus two exact timing anchors. Baseline code is `15`; 35-bank and 40-bank points both saturate at `32`; the static curve is monotonic and contains no bubbles or reset failures. Slow/medium/fast direct PWL drops to the 40-bank voltage capture codes `16/18/32`, exposing real slope dependence. | [`reports/voltage_code_20260725_r1/voltage_code_curve.md`](reports/voltage_code_20260725_r1/voltage_code_curve.md), [`runs/voltage_code_sweep_20260725_r1/voltage_code_summary.json`](runs/voltage_code_sweep_20260725_r1/voltage_code_summary.json), [`runs/voltage_code_pwl_20260725_r1/pwl_code_summary.json`](runs/voltage_code_pwl_20260725_r1/pwl_code_summary.json). |
| Direct chiplet-A rail timeline | One 200 ns HSPICE transient directly drove only `VDD_A` and made 40 real-DFF captures at 5 ns intervals. Four 25 ns nonmonotonic 4--30 mV PWL windows produced 14 distinct valid window codes (`16` through `31`, with gaps); closed-window baseline remained `15`, all 40 thermometer words were valid, all reset checks passed, and the maximum capture-rail error versus the configured direct PWL was `2.22e-16 V`. | [`reports/direct_rail_sensor_timeline_20260725_r1/direct_rail_sensor_timeline.md`](reports/direct_rail_sensor_timeline_20260725_r1/direct_rail_sensor_timeline.md), [`runs/direct_rail_sensor_timeline_20260725_r1/timeline_result.json`](runs/direct_rail_sensor_timeline_20260725_r1/timeline_result.json), `completion.rpt=status=PASS`. |
| Direct chiplet-A high-density timeline | One complete 2 us HSPICE transient directly drove only `VDD_A` and made 500 real-DFF captures at 4 ns intervals. Four frame-aligned 248 ns nonmonotonic 4--30 mV PWL windows produced 16 distinct valid window codes (`16` through `31`); closed-window baseline remained `15`, all 500 thermometer words were valid, all reset checks passed, and the maximum capture-rail error versus the saved `.tr0` was `5.0e-5 V`. | [`reports/direct_rail_sensor_timeline_20260725_r2/direct_rail_sensor_timeline.md`](reports/direct_rail_sensor_timeline_20260725_r2/direct_rail_sensor_timeline.md), [`runs/direct_rail_sensor_timeline_20260725_r2/timeline_result.json`](runs/direct_rail_sensor_timeline_20260725_r2/timeline_result.json), `completion.rpt=status=PASS`. |

## Digital implementation boundary

[`rtl/vernier_sensor_digital_backend.sv`](rtl/vernier_sensor_digital_backend.sv)
contains the synthesizable capture, bubble correction, leading-zero encoder,
validity flag, and `sample_done` interface.  The analog delay chains and the
real DFF bank remain SPICE/standard-cell structures; the RTL does not replace
their physical timing.  [`rtl/vernier_sensor_calibration_pkg.sv`](rtl/vernier_sensor_calibration_pkg.sv)
records the measured default `CAL_SEL=2` and baseline code `15`.

The RTL was statically checked for the two project constraints: it contains no
`function` declaration and no `#delay` construct.  Port comments describe the
clock/reset polarity, calibration ownership, bit ordering, and captured-output
contract.

## Reproducibility and retained evidence

The compact evidence files are retained in these task-owned run directories:

- `phase1_anchors_20260724_r1` (9 scenarios)
- `ideal_arrival_fine_20260724_r1` (1,107 scenarios)
- `dff_sweep_20260724_r3` (12 scenarios)
- `dff_calibration_20260724_r1` (256 scenarios)
- `cross_domain_20260724_r2` (51 scenarios)
- `reference_island_20260724_r1` (16 scenarios)
- `voltage_code_sweep_20260725_r1` (303 static real-DFF scenarios)
- `voltage_code_pwl_20260725_r1` (3 dynamic real-DFF scenarios)
- `direct_rail_sensor_timeline_20260725_r1` (one 200 ns / 40-capture real-DFF direct-rail scenario)
- `direct_rail_sensor_timeline_20260725_r2` (one 2 us / 500-capture real-DFF direct-rail scenario; raw `.tr0` retained only in the task-owned run directory)

Each directory has a manifest or resume record, a completion report, and the
compact CSV/JSON/Markdown result needed to reproduce the conclusion.  Raw
HSPICE products are retained under the run directories for inspection and are
not part of the source interface.

## Explicitly deferred scope

The following work is intentionally not claimed by this report:

1. The shared two-chiplet RLC/RO-bank integration and `T_lead` measurement
   from the later integration step were not run.
2. Plan Step 11, PVT (`TT/SS/FF`, 25/85 C) and post-calibration robustness,
   was not run.
3. Plan Step 12, sensor self-disturbance and attack-result delta, was not run.

The direct-rail timeline also does not claim a shared-PDN warning lead, PVT
coverage, sensor overhead limit, RO-bank detection ability, or unchanged attack
conclusion.  Those claims require the deferred integration and experiments and
must not be inferred from a controlled local PWL source.

## Test status

- Phase 1 unit tests: 3 tests passed.
- Phase 2 unit tests: 20 tests passed, including 6 direct-rail timeline tests.
- All Phase 2 Python scripts compiled with `py_compile`.
- RTL static checks: no `function`, no `#delay`.
- HSPICE completion reports: the completed direct-rail timeline and all prior
  retained run classes report `PASS`.
