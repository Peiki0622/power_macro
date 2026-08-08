# Phase 3 Wide-Range Sparse-Differential Vernier Execution Plan

## Objective

Extend the existing Phase 3 same-rail RVT/LVT Vernier sensor from its current narrow droop range to a target operating range of:

```text
VDD_A = 0.70 V ... 1.10 V
```

while keeping the hardware cost at or below the current Phase 3 frontend.

The intended direction is not to add more stages, more DFFs, a second sensor, or another reference structure. The range shall be extended by reducing excessive differential gain and by using the thermometer code range asymmetrically for the one-sided voltage-droop problem.

The desired architecture is:

```text
single local VDD_A/VSS_A
        |
32-stage RVT sense path
        |
32-stage companion path with sparse RVT/LVT differential stages
        |
32 existing real DFF comparators
        |
existing thermometer decoder
```

The current Phase 3 cell selection, real DFF topology, launch-calibration network, decoder, and no-reference-rail structure are already established. Reuse them directly. Do not repeat LVT discovery, cell-sensitivity characterization, pair matching, the original ideal-Vernier study, or the completed 1.04-1.10 V sweep.

Do not add CUSUM, glitch capture, PVT, Monte Carlo, additional lanes, or a second DFF bank in this plan.

---

## Design principle

The current frontend accumulates RVT/LVT differential delay at every one of the 32 stages and reaches code saturation after roughly 50 mV of droop. The wide-range version shall preserve 32 observation taps while reducing the number of stages that actually add RVT/LVT differential delay.

Use two companion-stage types:

```text
Neutral stage:
  sense     = RVT -> RVT
  companion = RVT -> RVT

Active differential stage:
  sense     = RVT -> RVT
  companion = LVT -> RVT
```

The second inverter of the active companion stage is RVT so the final driver seen by the DFF is RVT on both paths. The current LVT dummy-load inverter is removed from the wide-range topology.

The active differential stages shall be distributed approximately uniformly across the 32 taps. The number of active stages becomes the main analog-gain control.

The first candidate shall use 16 active stages. Reduce this count only if the 0.70 V range target is still not met.

---

## Step 1 - Add wide-range configuration without disturbing existing Phase 3 evidence

Extend `delay_chain/phase3/phase3_config.json` with a `wide_range` section rather than replacing the existing characterized values immediately.

Add fields equivalent to:

```json
{
  "wide_range": {
    "vdd_max_v": 1.10,
    "vdd_min_v": 0.70,
    "screen_vdd_points_v": [1.10, 1.00, 0.90, 0.80, 0.70],
    "coarse_step_v": 0.010,
    "final_step_v": 0.005,
    "target_nominal_code": 4,
    "acceptable_nominal_code_min": 3,
    "acceptable_nominal_code_max": 6,
    "screen_active_stage_counts": [16, 12, 8],
    "characterization_read_time_ns": 8.0,
    "characterization_stop_time_ns": 10.0
  }
}
```

Create only new result areas needed by this work:

```text
delay_chain/phase3/runs/wide_range_baseline/
delay_chain/phase3/runs/wide_range_screen/
delay_chain/phase3/runs/wide_range_final/
delay_chain/phase3/reports/PHASE3_WIDE_RANGE_RESULT.md
```

Do not rerun or rewrite previous Phase 3 run directories.

### Completion condition

- Existing Phase 3 configuration remains readable.
- New wide-range parameters are available to new scripts.
- No previous HSPICE study is repeated.

---

## Step 2 - Reuse the existing eight-tap launch calibration to move nominal code downward

The current sensor uses only part of the available 0..32 code range for droop because nominal code is near the middle. The wide-range design shall first use the existing physical CAL_SEL network to move the 1.10 V operating point toward the low end.

First check whether the existing local file:

```text
delay_chain/phase3/runs/launch_calibration/calibration.csv
```

already contains all eight physical CAL_SEL results at 1.10 V.

If it exists, parse it directly. Do not rerun those simulations.

Select the valid, reset-clean CAL_SEL whose nominal code is closest to 4, preferring a code in:

```text
3 .. 6
```

If the existing run artifact is unavailable in the working tree, run only the eight nominal 1.10 V CAL_SEL cases using the already implemented physical launch network. Do not repeat any other previous study.

Record the candidate setting as a wide-range calibration value. Do not overwrite the existing Phase 3 `selected_cal_sel` until a final wide-range topology has been chosen.

If no existing CAL_SEL places the current topology in code 3..6, use the lowest valid reset-clean nominal code for the next step. Do not enlarge the calibration network at this point.

### Completion condition

A nominal CAL_SEL candidate is available with the largest practical droop-side code headroom using the existing launch hardware.

---

## Step 3 - Measure the maximum range obtainable with zero hardware changes

Before changing the chain topology, determine how far the current physical Phase 3 frontend can be extended using only the lower nominal operating point from Step 2.

Reuse the current physical topology:

```text
RVT-RVT sense
vs
LVT-LVT + one LVT dummy companion
32 DFFs
existing physical CAL_SEL network
```

Run a coarse wide-range sweep:

```text
1.10 V down to 0.70 V
10 mV step
TT, 25 C
```

This is a new range measurement, not a repeat of the previous 1.04-1.10 V study.

For this wide-range characterization, do not keep the old 2.5 ns Q-read assumption. Use the extended characterization window from the configuration so low-voltage propagation is allowed to settle.

Record at every point:

```text
VDD
raw thermometer word
sensor code
residual from the selected nominal baseline
code_valid
reset failure count
final RVT tap crossing time
final companion tap crossing time
final differential crossing time
```

Also record whether the last chain taps have arrived before the Q-read time. This separates true code saturation from a low-voltage settling failure.

### Decision

If the current topology remains valid and unsaturated through 0.70 V, keep it and skip directly to Step 7.

Otherwise proceed to the lower-gain mixed companion topology.

### Completion condition

The zero-hardware-change range limit is known without repeating previous Phase 3 characterization.

---

## Step 4 - Add one lower-gain sparse companion topology to the HSPICE generator

Only if Step 3 fails to reach 0.70 V, extend `delay_chain/phase3/scripts/generate_phase3_deck.py` so the companion chain can be built from a static 32-bit active-stage mask.

Keep the sense path unchanged at every stage:

```text
RVT -> RVT
```

For each companion stage:

```text
mask bit = 0:
    RVT -> RVT

mask bit = 1:
    LVT -> RVT
```

Do not instantiate the current LVT dummy-load inverter in either wide-range companion stage type.

Keep unchanged:

```text
32 total stages
32 real DFFRPQ comparators
D = companion tap
CK = RVT sense tap
existing physical launch calibration
existing decoder polarity handling
single VDD_A/VSS_A domain
```

Implement one small deterministic helper that distributes `N_active` stages approximately uniformly across 32 positions. It should return both the ordered active indices and the 32-bit mask so every experiment is reproducible.

The first candidate is:

```text
N_active = 16
```

with active stages approximately every second tap.

### Completion condition

The HSPICE generator can render the selected current topology or a sparse mixed companion topology from one static active-stage count/mask, without changing DFF count or adding a new analog block.

---

## Step 5 - Screen the 16-active sparse topology before running a full sweep

Run only the minimum simulations required to decide whether the 16-active structure can cover the required range.

### 5.1 Nominal calibration

At 1.10 V, run the eight existing CAL_SEL settings for the 16-active topology.

Choose the valid, reset-clean setting closest to nominal code 4, preferably in:

```text
3 .. 6
```

Do not add calibration cells if the exact target is unavailable. Use the lowest practical valid code and rely on active-stage count for range control.

### 5.2 Five-point range screen

With that CAL_SEL, simulate only:

```text
1.10 V
1.00 V
0.90 V
0.80 V
0.70 V
```

using the extended low-voltage transient window.

For every point require real DFF Q measurements rather than ideal arrival-time decoding.

Record:

```text
sensor code
raw word
code_valid
reset failures
final crossing times
```

### 5.3 Decision

If all five points are valid and the 0.70 V code remains below saturation, keep `N_active=16`.

Use this preferred screen target:

```text
code(0.70 V) <= 30
```

because it leaves visible upper-code margin at the low end of the required supply range.

If 16 active stages still saturate too early, continue to Step 6.

### Completion condition

Either the 16-active candidate is selected, or there is direct physical evidence that lower differential gain is required.

---

## Step 6 - Reduce active-stage count only as needed

Do not perform a large combinational search.

If `N_active=16` fails the range screen, repeat only the Step-5 nominal calibration and five-point screen for:

```text
N_active = 12
```

If 12 still fails, repeat once more for:

```text
N_active = 8
```

Always distribute active stages approximately uniformly over the 32 taps.

Choose the largest active-stage count that satisfies the 0.70 V range screen, because the largest passing count preserves the best small-droop sensitivity.

The intended decision sequence is therefore:

```text
16 passes -> select 16
16 fails, 12 passes -> select 12
12 fails, 8 passes -> select 8
```

Do not explore additional stage counts unless all three fail.

If all three fail because the code still saturates, report that the current 32-tap architecture needs a further gain change before adding hardware. Do not respond by increasing stage count or DFF count.

If failure at low VDD is instead caused by reset, missing final-tap arrival, or DFF non-settlement, classify it as a low-voltage functional/timing limit rather than a Vernier range problem.

### Completion condition

One sparse active-stage count has been selected, or a clearly classified low-voltage functional limit has been identified.

---

## Step 7 - Run the final 0.70-1.10 V physical characterization

For the selected topology and CAL_SEL, run the complete wide-range physical sweep:

```text
1.10 V down to 0.70 V
5 mV step
TT, 25 C
```

Also include exact runs at the existing timing anchors:

```text
1.054061327707 V
1.047473942801 V
```

because the new frontend transfer function must retain direct comparability with the previously established timing-failure reference points.

Use the extended transient window and real DFF Q levels at every point.

Write compact evidence to:

```text
delay_chain/phase3/runs/wide_range_final/voltage_code.csv
delay_chain/phase3/runs/wide_range_final/voltage_summary.json
```

The CSV shall include:

```text
VDD
point kind
raw thermometer word
normalized word
corrected word
sensor code
residual code
code_valid
raw bubble count
corrected bubble count
reset failure count
final sense crossing
final companion crossing
final differential crossing
```

Compute:

```text
nominal code
code at 1.08 V
code at 1.05 V
code at 1.00 V
code at 0.90 V
code at 0.80 V
code at 0.70 V
first saturation voltage, if any
first invalid voltage, if any
maximum final-tap arrival time
```

### Wide-range gates

The selected topology should satisfy:

```text
1. all points from 1.10 V through 0.70 V have code_valid = 1
2. all points have reset failure count = 0
3. final chain taps arrive before the characterization read time
4. nominal code is preferably in 3..6
5. code does not reach 32 before 0.70 V
6. preferred code(0.70 V) <= 30
7. code is generally nondecreasing as VDD falls
8. no multi-code local reversal is accepted
9. a stable positive residual should appear by approximately 20-30 mV droop so later temporal accumulation still has useful input
```

Retain any isolated one-code local reversal in the evidence rather than deleting or smoothing it.

### Completion condition

A real-cell, real-DFF voltage-to-code curve exists for the entire 0.70-1.10 V range and demonstrates that the sensor no longer saturates near 50 mV droop.

---

## Step 8 - Package only the selected sparse topology into RTL

Do not modify RTL for every screened candidate. Update the structural RTL only after one active-stage count and CAL_SEL have been selected.

Add a static active-stage mask to the Phase 3 calibration/configuration package, for example:

```text
WIDE_RANGE_ACTIVE_STAGE_MASK
WIDE_RANGE_ACTIVE_STAGE_COUNT
WIDE_RANGE_DEFAULT_CAL_SEL
WIDE_RANGE_BASELINE_CODE
```

Update the physical frontend so each of the 32 companion stages is selected at elaboration time from:

```text
neutral companion stage: RVT -> RVT
active companion stage:  LVT -> RVT
```

The sense path remains RVT -> RVT for all 32 stages.

Create a small structural companion-stage wrapper if that keeps the implementation clear, but do not introduce runtime stage selection or per-stage muxes. The active mask is a static elaboration-time choice and must not add runtime hardware.

Remove the wide-range path's LVT dummy load.

Keep unchanged:

```text
32 DFF comparators
single physical launch-calibration network
single decoder
single VDD_A/VSS_A interface
no VDD_REF/VSS_REF
```

Update the fixed baseline and CAL_SEL values only after the HSPICE final sweep passes.

### Expected chain hardware direction

The current chain uses approximately five inverter cells per stage because the companion path contains two LVT functional inverters plus one LVT dummy input load.

The sparse wide-range chain uses four functional inverter cells per stage:

```text
2 on the sense path
2 on the companion path
```

Therefore the chain should reduce from approximately:

```text
160 inverter instances -> 128 inverter instances
```

while keeping the same 32 DFF comparators.

The selected LVT inverter count becomes approximately equal to `N_active` instead of 96 LVT inverter instances in the current all-LVT-plus-dummy structure.

### Completion condition

The selected 0.70-1.10 V topology is represented structurally with no runtime topology muxes and no hardware increase over the current Phase 3 chain.

---

## Step 9 - Update only the minimum regression needed for the new physical contract

Extend the existing Phase 3 contract tests rather than building a second verification framework.

Add checks for:

```text
wide-range active-stage mask contains exactly the selected number of active stages
active companion stage contains one LVT then one RVT inverter
neutral companion stage contains two RVT inverters
wide-range companion stages contain no old LVT dummy-load inverter
frontend still contains 32 comparator DFFs
frontend still exposes only VDD_A/VSS_A
selected CAL_SEL reproduces the final nominal baseline
final wide-range summary covers all requested 0.70-1.10 V points
no pre-0.70 V code saturation is reported
SPICE raw-word replay remains bit-exact through the RTL decoder
RTL elaborates with the existing power-aware cell stubs
```

Do not rerun the old original Phase 3 HSPICE sweeps as part of this regression.

### Completion condition

The selected wide-range physical topology and its RTL packaging satisfy the existing Phase 3 structural contract plus the new range contract.

---

## Step 10 - Publish one compact wide-range result report

Create:

```text
delay_chain/phase3/reports/PHASE3_WIDE_RANGE_RESULT.md
```

The report shall answer:

1. How far the existing topology reached after using a lower nominal CAL_SEL with zero hardware changes.
2. Whether sparse differential stages were required.
3. Which active-stage count was selected: 16, 12, or 8.
4. Which 32-bit active-stage mask is used.
5. Which CAL_SEL and nominal baseline code are used.
6. What codes are produced at 1.10, 1.05, 1.00, 0.90, 0.80, and 0.70 V.
7. At what voltage saturation or invalid operation first appears, if at all.
8. What the maximum measured final-tap arrival time is at low VDD.
9. How many RVT, LVT, DFF, BUF, and MXT2 instances the selected frontend contains.
10. How the selected hardware count compares with the current Phase 3 frontend.

Commit the compact CSV/JSON summary evidence needed to reproduce the report conclusions. Keep large HSPICE waveform/listing products ignored.

---

## Final completion criteria

The wide-range Phase 3 update is complete when:

```text
VDD range:                 0.70 V .. 1.10 V
physical rail domains:     one VDD_A/VSS_A only
reference rail:            none
stage count:               32
DFF comparator count:      32
runtime topology muxes:    none
nominal code:              preferably 3..6
code_valid across range:   yes
reset failures:            zero
pre-0.70 V saturation:     none
preferred code at 0.70 V:  <= 30
small-droop response:      first stable positive residual by about 20-30 mV
chain hardware cost:       no larger than current Phase 3
```

The preferred final technical direction is:

```text
lower one-sided nominal code
        +
32 observation taps
        +
sparse LVT->RVT differential stages inside an otherwise RVT->RVT companion path
        =
wide-range same-rail reference-free Vernier sensor
```

The plan intentionally preserves the existing 32-stage/32-DFF observation structure and reduces analog differential gain instead of adding hardware. The first candidate is 16 active differential stages; only reduce to 12 or 8 if the physical 0.70 V range screen requires it.
