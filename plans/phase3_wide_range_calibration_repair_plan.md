# Phase 3 Wide-Range Calibration Repair and Debug Plan

## 0. Purpose and current diagnosis

This plan repairs the current Phase 3 wide-range sparse Vernier implementation after commit `1a9b05e8b20570c1905fd46390080cba8130a7bd` produced a valid but useless all-zero sensor curve.

The goal is **not** to redesign the sparse Vernier immediately. The first task is to place the physical DFF bank back inside a useful timing aperture by repairing the launch-calibration flow and, only if the evidence requires it, the launch-calibration loading/range.

Reuse the already established facts from the current repository:

```text
wide-range topology        = 16 active sparse stages
active mask                = 0x55555555
sense path                 = RVT -> RVT at all 32 stages
active companion stage     = LVT -> RVT
neutral companion stage    = RVT -> RVT
DFF mapping                = D=companion tap, CK=RVT tap
current wide CAL_SEL       = 0
current wide baseline      = 0
current final sweep        = code 0 at all 83 points from 1.10 V to 0.70 V
```

The existing final physical data also proves that the sparse analog timing difference is not dead:

```text
at 1.10 V:
  RVT tap31 crossing       = 1.603082839 ns
  companion tap31 crossing = 1.636778817 ns
  D-CK final difference    = +33.695978 ps

at 0.70 V:
  RVT tap31 crossing       = 3.664658760 ns
  companion tap31 crossing = 3.624874391 ns
  D-CK final difference    = -39.784369 ps

movement across range      ~= 73.48 ps
```

Therefore do **not** interpret the all-zero result as proof that the sparse topology has no voltage sensitivity. The immediate problem is that the physical DFF transition aperture is not being used correctly.

There are four already identified implementation defects that must be corrected during this work:

1. `run_launch_calibration.py` writes a calibration failure and then, in wide-range mode, falls back to any valid endpoint code. This allowed `CAL_SEL=0, baseline=0` to be selected even though the requested nominal window was 3..6.
2. `validate_wide_rows()` allows a constant-zero curve to pass because it checks validity/reset/arrival/saturation/monotonicity but does not require a useful nominal code or nonzero sensor span.
3. The sparse topology reused the old launch-balance network, including two private BUF input loads on the companion launch, without re-establishing whether those loads are still appropriate.
4. The committed RTL top still drives `DEFAULT_CAL_SEL=1` while the wide-range HSPICE result records `WIDE_RANGE_DEFAULT_CAL_SEL=0`; RTL and characterized SPICE are not currently the same configuration.

This plan must determine which physical calibration correction is actually required before changing active-stage count or any other sensor architecture choice.

---

## 1. Execution rules

Follow these rules throughout the task.

### 1.1 Do not rerun completed broad studies

Do not rerun:

```text
LVT discovery
cell-sensitivity sweep
pair-matching study
original ideal Vernier study
original 1.04-1.10 V Phase 3 sweep
existing 83-point broken wide-range sweep
```

Those results already exist and are sufficient as historical evidence.

### 1.2 Do not overwrite the broken evidence

Keep the current `runs/wide_range_final/` data intact because it is useful failure evidence.

Create new task-scoped directories, for example:

```text
delay_chain/phase3/runs/wide_range_cal_debug/
delay_chain/phase3/runs/wide_range_cal_load_ab/
delay_chain/phase3/runs/wide_range_repaired_screen/
delay_chain/phase3/runs/wide_range_repaired_final/
```

Large HSPICE products remain ignored. Commit only compact CSV/JSON/report evidence.

### 1.3 Do not change the sparse gain architecture before calibration is repaired

Until a valid nominal timing aperture has been demonstrated, keep:

```text
active stage count = 16
active mask        = 0x55555555
32 stages
32 DFFs
D=companion
CK=RVT
```

Do not switch to 12 or 8 active stages merely because the present code is constant zero. The current failure does not yet measure the sparse topology's usable code gain.

### 1.4 Do not fix an analog endpoint by changing decoder polarity

Do not change `THERMOMETER_INVERT` as a repair for this problem. An all-zero raw DFF word converted to an all-one normalized word is still an endpoint; changing polarity would only convert the endpoint from code 0 to code 32.

### 1.5 Prefer corrections that remove or reuse hardware

Physical repair priority is:

```text
A. select a different existing CAL_SEL
B. remove/adjust obsolete launch-balance loads
C. repurpose existing calibration cells/tap spacing
D. only then consider adding calibration hardware
```

Do not add stages, DFFs, a second sensor lane, or a separate reference rail.

---

## 2. Step 1 - Fix failure semantics before running any new HSPICE experiment

The current automation can transform a failed calibration into a nominal PASS. Fix this first so subsequent experiments cannot silently accept another endpoint.

### 2.1 Repair `run_launch_calibration.py`

Current wide-range behavior must no longer do this:

```text
no code in requested nominal window
    -> write FAIL
    -> replace acceptable list with all valid rows
    -> select endpoint
    -> rewrite completion as PASS
```

Required behavior:

```text
if one or more valid/reset-clean rows are inside requested nominal window:
    choose the row nearest target
    status = PASS
else:
    still write all eight measured rows
    still write calibration_selection.json with diagnostic ranking
    status = FAIL
    reason = no_nominal_center_setting
    return nonzero
    do not publish a selected wide-range CAL_SEL/baseline as characterized
```

The diagnostic JSON may include the nearest valid row, but name it clearly, e.g.:

```json
"nearest_valid_diagnostic": {...}
```

It must not be named or consumed as `selected` when the acceptance window failed.

### 2.2 Repair wide-range validation

Extend `validate_wide_rows()` with at least these gates:

```text
nominal_not_endpoint
nominal_in_requested_window
nonzero_code_span
```

For this repair task use the configured nominal target/window:

```text
target = 4
acceptable nominal = 3..6
```

Also compute and report:

```text
minimum sensor code
maximum sensor code
code span = max - min
first positive residual voltage/droop
```

A constant-zero or constant-32 curve must be `FAIL` even when every thermometer word is syntactically valid.

### 2.3 Add regression tests for both bugs

Add unit tests that explicitly prove:

```text
all valid CAL_SEL rows but none in 3..6 -> calibration returns FAIL
constant-zero wide-range rows           -> wide-range validation returns FAIL
```

These tests should use small synthetic rows and must not invoke HSPICE.

### Step-1 completion gate

Before new HSPICE runs:

```text
software can no longer label endpoint calibration as PASS
software can no longer label constant-zero transfer as PASS
existing historical evidence is untouched
```

---

## 3. Step 2 - Instrument the physical calibration experiment at 1.10 V

The next task is to see exactly where the DFF aperture lies relative to each physical CAL_SEL.

Do not run a voltage sweep yet.

### 3.1 Add timing probes to the real-DFF calibration deck

For wide-range calibration debug only, measure the rising crossing time of both calibrated launch outputs:

```text
t_rvt_launch
t_companion_launch
```

Also measure representative D and CK tap crossings at:

```text
stage 0
stage 7
stage 15
stage 23
stage 31
```

For each probe produce:

```text
t_ck_i  = RVT tap crossing
t_d_i   = companion tap crossing
d_minus_ck_i = t_d_i - t_ck_i
```

Keep all 32 real DFF Q measurements and the decoded raw word exactly as before.

The debug data is diagnostic instrumentation only; it must not change the signal path.

### 3.2 Verify actual CAL_SEL-to-tap mapping

Do not assume the numeric selector automatically maps to taps 0..7 in increasing physical delay.

For each `CAL_SEL=0..7`, use measured launch crossing times to determine the actual selected RVT launch delay.

Also inspect the installed/available MXT2 logical model used by this project and confirm the A/B selection polarity of `S0`. If the library truth table is available in the local PDK, record it in the debug report. Do not change the mux implementation based only on the signal name.

The resulting table must contain:

```text
CAL_SEL
actual selected RVT launch delay
companion launch delay
launch D-CK skew
sensor code
raw thermometer word
valid
reset failures
```

### 3.3 Run exactly eight nominal cases

Configuration:

```text
VDD              = 1.10 V
corner           = TT
T                = 25 C
active stages    = 16
active mask      = 0x55555555
CAL_SEL          = 0..7
real DFFs        = yes
characterization read window = existing wide-range 8 ns setting
```

Write compact evidence:

```text
runs/wide_range_cal_debug/calibration_debug.csv
runs/wide_range_cal_debug/calibration_debug.json
```

### Step-2 decision classification

Classify the measured eight cases into exactly one of these categories:

**Case A - an existing tap already works**

```text
at least one CAL_SEL has code 3..6
valid = 1
reset failures = 0
```

Then select the closest existing tap and skip directly to Step 6. No calibration hardware change is needed.

**Case B - CAL_SEL brackets the DFF transition but skips over code 3..6**

Example pattern:

```text
CAL n     -> code 0 or 1
CAL n+1   -> code 10 or larger
```

and the measured `D-CK` timing crosses the aperture between them.

This means calibration step granularity is too coarse. Continue to Steps 3 and 5.

**Case C - all eight taps remain on the same DFF side**

For example all codes stay 0 and measured D remains too late relative to CK.

This means the physical calibration range/matching is misplaced, or the selector/tap mapping is wrong. Continue to Step 3.

**Case D - codes/timing are inconsistent with the expected selected tap order**

Investigate MUX selection polarity, deck rendering, and selected-node extraction before modifying hardware.

Do not proceed to a wide voltage sweep until this classification is resolved.

---

## 4. Step 3 - Quantify the old companion launch-balance load error

The current calibration network still adds two private `BUF_X0P7M_A9TR40` input loads to the companion launch output. Those loads were inherited from the previous all-LVT companion topology and were never re-qualified for the sparse LVT->RVT/RVT->RVT chain.

Determine whether they are responsible for a significant fraction of the nominal +33.7 ps final D-CK skew.

### 4.1 Make balance-load count an explicit diagnostic parameter

In the deck renderer, separate launch-balance loading from the old chain dummy-load parameter.

Introduce an explicit static renderer parameter such as:

```text
launch_balance_load_count
```

Default it to the current value `2` so existing historical decks are not semantically changed.

For this diagnostic allow only:

```text
0
1
2
```

Each load remains a real BUF input with a private output; no behavioral capacitor is allowed.

### 4.2 First A/B experiment: only two HSPICE cases

At 1.10 V, keep:

```text
16 active stages
same active mask
same CAL_SEL
```

Use the CAL_SEL that Step 2 identifies as nearest to the transition. If all taps are equally endpointed, begin with CAL_SEL=0 because it is the currently frozen failing setting.

Run:

```text
balance loads = 2  (current)
balance loads = 0
```

Measure:

```text
launch D-CK skew
D-CK at stages 0/7/15/23/31
raw thermometer
sensor code
```

### 4.3 Interpret before running a larger matrix

If removing the two loads moves the DFF operating point substantially toward the transition window, then the old launch loads are obsolete and should not remain frozen into the sparse design.

Only then run the minimum additional case needed to test `load_count=1` if one load may place the launch closer to the aperture.

Do **not** automatically run all `3 load counts x 8 CAL_SEL` combinations.

### Step-3 completion gate

Produce a small table that answers:

```text
How many ps of launch/tap skew are caused by the two inherited balance loads?
Does 0, 1, or 2 loads place the existing CAL range closer to the DFF transition?
```

If zero loads is best, prefer removing the obsolete loads because it reduces hardware.

---

## 5. Step 4 - Reuse existing DFF-aperture evidence before creating any new ideal-offset sweep

The repository already contains the previous real-DFF characterization that placed the old topology inside the DFF transition region. Reuse that evidence first to estimate the setup/aperture scale of `DFFRPQ_X0P5M_A9TR40` at 1.10 V.

Do not rerun that previous study merely to regenerate the same result.

### 5.1 Compare physical CAL timing against known aperture scale

Using Step-2/3 measured `D-CK` values, determine whether:

```text
the physical CAL taps never reach the known aperture region
```

or

```text
they cross it but with insufficient resolution
```

### 5.2 Conditional diagnostic only if the cause remains ambiguous

Only if the existing evidence cannot distinguish calibration-range failure from DFF-aperture behavior, run a tiny ideal source-offset diagnostic at 1.10 V on the 16-active sparse chain.

Do not perform a broad sweep. Use 3-5 offsets centered around the measured physical skew from Steps 2/3.

Purpose:

```text
prove that a suitable launch offset can produce an interior thermometer code
```

This experiment is diagnostic only and must never become the final implementation.

### Step-4 completion gate

By the end of this step, state explicitly whether the failure is:

```text
wrong launch matching/range
coarse calibration resolution
selector mapping/implementation bug
or an unexpected DFF-aperture limitation
```

Do not redesign the sparse chain without this statement.

---

## 6. Step 5 - Repair the physical launch calibration with minimum hardware cost

Perform this step only if Step 2 did not find an already valid CAL_SEL.

Choose the smallest correction supported by measured data.

### Repair priority A - remove obsolete companion balance loads

If Step 3 shows that the inherited loads push D too late, reduce:

```text
2 -> 1
```

or preferably:

```text
2 -> 0
```

if that places the existing 8-tap range over the desired DFF aperture.

Mirror the selected load count in both HSPICE and structural RTL.

### Repair priority B - repurpose calibration tap spacing

If the existing taps bracket the aperture but jump over the required nominal code window, improve fine resolution without increasing the total calibration-cell budget where practical.

First characterize/reuse the already available real-cell delay increments of:

```text
MXT2_X0P5M_A9TR40 with A=B
BUF_X0P7M_A9TR40
```

Then alter the sequence of existing fine/coarse tap cells so multiple taps cover the measured transition region more densely.

Do not blindly append more delay elements. Prefer replacing/rearranging coarse increments with finer existing-cell increments if the total instance count can remain unchanged.

### Repair priority C - extend calibration range only if measurements prove the range is insufficient

If all eight physical taps remain on one side of the aperture even after the correct launch loading is used, extend the RVT/CK delay range by the minimum number of real cells necessary.

Any added cell must be justified by:

```text
measured missing delay in ps
measured delay provided by the chosen cell
predicted target CAL_SEL region
```

Do not add generic delay-chain stages or a second calibration network.

### Required physical direction

Remember the current nominal failing case has approximately:

```text
D later than CK
```

with D=companion and CK=RVT.

The repair must therefore move the relative timing toward an interior DFF capture transition, normally by delaying CK and/or removing avoidable delay/load from D. Do not choose a modification that moves the two paths farther apart in the failing direction.

### Step-5 completion gate

A repaired physical launch network must have at least one 1.10 V setting satisfying:

```text
code_valid = 1
reset failures = 0
sensor code = 3..6
raw thermometer is not all 0 and not all 1
```

If no such setting exists, stop and report the measured gap. Do not proceed by accepting code 0 again.

---

## 7. Step 6 - Re-run only nominal calibration after the physical repair

Once the launch network/load choice changes, run the eight 1.10 V physical CAL_SEL settings once for the repaired topology.

Do not rerun any voltage range yet.

Selection rule:

```text
1. valid and reset-clean
2. inside code 3..6
3. nearest target code 4
4. if tied, prefer the setting with more neighboring CAL_SEL margin before an endpoint
```

Record:

```text
selected CAL_SEL
selected baseline code
launch skew
representative D-CK tap skews
raw thermometer
```

Update only a task-local repaired selection JSON at this stage. Do not freeze RTL constants until the voltage screen passes.

### Step-6 completion gate

The nominal calibration is a true PASS under the repaired fail semantics.

---

## 8. Step 7 - Run a small repaired voltage screen before any 83-point sweep

Use the selected repaired calibration and the unchanged 16-active sparse mask.

Run only:

```text
1.10 V
1.08 V
1.05 V
1.00 V
0.90 V
0.80 V
0.70 V
```

Use the extended low-voltage read window already established by the wide-range work.

Record the complete raw/normalized/corrected thermometer data plus final-tap timing.

### Required screen behavior

Hard requirements:

```text
nominal code remains 3..6
all points code_valid = 1
all reset failures = 0
all final taps arrive before read time
curve is not constant
no code 32 occurs above 0.70 V
```

Small-droop requirement:

```text
by approximately 20-30 mV droop there should be a stable positive residual of at least one code
```

Range requirement:

```text
0.70 V must still be below the hard saturation endpoint (sensor_code < 32)
```

Preferred margin:

```text
sensor_code(0.70 V) <= 30
```

### Step-7 decisions

**If the screen passes:** proceed to Step 8.

**If nominal calibration is correct but the curve saturates too early:** only now return to active-stage gain tuning (16 -> 12 -> 8) from the wide-range architecture plan. This is a gain problem, not a calibration problem.

**If nominal calibration is correct but the code barely moves over 0.40 V:** the sparse gain is too low. Do not reduce active-stage count; reassess active-stage count upward or stage placement using measured timing gain.

**If the curve moves in the wrong polarity:** inspect D/CK timing and polarity handling. Do not hide the problem by merely flipping the decoder unless the physical comparator direction and code convention are intentionally redefined together.

---

## 9. Step 8 - Synchronize HSPICE, configuration, and RTL only after the repaired screen passes

The current repository has a known mismatch: the sparse frontend RTL is paired with `DEFAULT_CAL_SEL=1` at the top level even though the wide-range result recorded CAL_SEL 0.

After a repaired selection passes Step 7, make one configuration authoritative.

### 9.1 Update configuration

In `phase3_config.json`, update the `wide_range.selected` object with the repaired physical result:

```text
active_stage_count
active_stage_indices
active_stage_mask
baseline_code
cal_sel
launch_balance_load_count
topology
```

Do not change the original narrow-range Phase 3 `selected_cal_sel=1, baseline=18` historical fields unless the project intentionally replaces that historical configuration. Keep historical and wide-range selections distinguishable.

### 9.2 Update RTL constants

Update `phase3_calibration_pkg.sv` so the wide-range constants match the repaired HSPICE selection.

### 9.3 Fix the top-level selector mismatch

The wide-range sparse frontend currently uses the wide-range stage mask but `phase3_sensor.sv` drives the frontend with `DEFAULT_CAL_SEL`.

For the wide-range implementation, drive the launch frontend with:

```text
WIDE_RANGE_DEFAULT_CAL_SEL
```

not the old narrow-range `DEFAULT_CAL_SEL`.

Keep the calibration choice static; do not add a public runtime calibration port in this task.

### 9.4 Mirror any balance-load repair in RTL

If the selected physical solution removes or changes the two companion launch loads, modify `phase3_launch_cal_struct.sv` to exactly match the selected HSPICE topology.

No HSPICE-only repair is acceptable.

### Step-8 completion gate

A structural audit must show:

```text
same sparse mask in config/HSPICE/RTL
same CAL_SEL in config/HSPICE/RTL
same launch-balance load count in HSPICE/RTL
same D/CK mapping
same thermometer inversion convention
no VDD_REF/VSS_REF
```

---

## 10. Step 9 - Strengthen regression around the repaired physical contract

Extend the existing Phase 3 tests; do not build a parallel test framework.

Add checks for:

```text
1. failed nominal calibration cannot publish a selected endpoint
2. wide-range constant-zero/constant-32 curves cannot PASS
3. WIDE_RANGE_DEFAULT_CAL_SEL equals phase3_config wide_range.selected.cal_sel
4. WIDE_RANGE_BASELINE_CODE equals phase3_config wide_range.selected.baseline_code
5. phase3_sensor uses WIDE_RANGE_DEFAULT_CAL_SEL for the sparse frontend
6. active mask in RTL package equals config selected mask
7. launch-balance load count/topology matches the repaired physical deck
8. frontend still has 32 DFF comparators
9. no reference rail appears
10. repaired SPICE raw words replay bit-exact through the existing decoder
```

If compact repaired screen evidence is committed, add a test that nominal code is interior and screen code span is nonzero.

Do not make the test suite regenerate the old broad HSPICE studies.

---

## 11. Step 10 - Run the repaired final 0.70-1.10 V characterization only once

Only after Steps 6-9 pass, run the final physical characterization:

```text
1.10 V down to 0.70 V
5 mV step
TT / 25 C
plus exact existing last-pass and first-violation timing anchors
```

Use the same real DFF measurements and extended read window as the previous wide-range characterization.

Write new evidence to:

```text
delay_chain/phase3/runs/wide_range_repaired_final/voltage_code.csv
delay_chain/phase3/runs/wide_range_repaired_final/voltage_summary.json
```

Do not overwrite the old broken `wide_range_final` evidence.

### Final hard gates

```text
all code words valid
all reset failures = 0
all final taps arrive before read time
nominal code in configured interior window (target 4, accepted 3..6)
code span > 0
first stable positive residual appears by roughly 20-30 mV droop
sensor code is generally nondecreasing as droop increases
no multi-code local reversal
no saturation above 0.70 V
sensor_code(0.70 V) < 32
```

Preferred endpoint margin:

```text
sensor_code(0.70 V) <= 30
```

Retain isolated one-code local reversals in evidence; do not smooth data.

---

## 12. Step 11 - Publish a calibration-repair report

Create:

```text
delay_chain/phase3/reports/PHASE3_WIDE_RANGE_CALIBRATION_REPAIR.md
```

The report must include the causal chain, not only the final curve.

Required sections:

### A. Original failure

Record:

```text
CAL_SEL=0
baseline=0
all-zero raw DFF result across the old 83-point run
nominal final-tap D-CK ~= +33.7 ps
```

### B. Software-contract defects

Explain:

```text
calibration fallback bug
constant-zero PASS-gate bug
RTL/HSPICE CAL_SEL mismatch
```

### C. Eight-tap nominal debug

Table:

```text
CAL_SEL
actual launch skew
stage 0/7/15/23/31 D-CK
raw word
code
```

### D. Balance-load A/B result

Quantify the timing impact of the inherited two BUF input loads and state whether 0, 1, or 2 were selected.

### E. Physical repair

State exactly what changed and why, including hardware delta.

### F. Repaired nominal calibration

Record selected CAL_SEL and baseline code.

### G. Repaired 0.70-1.10 V transfer

Report codes at least at:

```text
1.10
1.08
1.05
1.00
0.90
0.80
0.70 V
```

and the two existing timing anchors.

### H. Hardware cost

Compare final repaired launch/sparse frontend instance counts with the previous sparse implementation. The intended repair should preferably remove or reuse cells; any added cell must be called out explicitly.

---

## 13. Final decision tree for Codex

Use this exact macro-level flow. Do not skip directly to another full sweep.

```text
fix FAIL/PASS semantics
        |
        v
instrument 1.10 V CAL_SEL 0..7
        |
        +--> existing CAL_SEL gives code 3..6?
        |        |
        |        +-- YES --> select it --> repaired screen
        |        |
        |        +-- NO
        |             |
        v             v
measure inherited companion balance-load effect
        |
        +--> removing/reducing loads brings aperture into range?
        |        |
        |        +-- YES --> choose minimum-load solution
        |        |
        |        +-- NO
        |             |
        v             v
compare CAL tap range/resolution against measured DFF aperture
        |
        +--> range brackets aperture but steps are too coarse?
        |        |
        |        +-- YES --> repurpose existing tap spacing for finer coverage
        |        |
        |        +-- NO --> minimally extend calibration range only if measured gap proves necessary
        |
        v
rerun only 8 nominal CAL cases
        |
        +--> no interior code --> STOP and report measured gap
        |
        v
7-point repaired voltage screen
        |
        +--> calibration correct but early saturation --> only now tune sparse active-stage gain
        |
        +--> calibration correct and useful range --> synchronize RTL/config
        |
        v
regression
        |
        v
one final 0.70-1.10 V sweep
        |
        v
publish repair report
```

---

## 14. Completion criteria

This repair task is complete only when all of the following are true:

```text
1. No failed calibration can silently fall back to code 0 or code 32.
2. The actual CAL_SEL-to-delay mapping is measured and documented.
3. The effect of the inherited two companion launch BUF loads is measured.
4. A physical 1.10 V calibration setting produces an interior thermometer code, target 4 and accepted 3..6.
5. The raw DFF word at nominal is not all zero and not all one.
6. A small repaired voltage screen produces a nonconstant, correctly directed code response.
7. HSPICE/config/RTL use the same sparse mask, CAL_SEL, launch loading, D/CK mapping, and decoder convention.
8. The final 0.70-1.10 V real-DFF characterization does not saturate before the lower endpoint.
9. Small droop still produces a usable positive residual for later CUSUM accumulation.
10. No unnecessary stage/DFF/reference-domain hardware has been added.
```

The central repair principle is:

```text
first align the existing DFF sampling aperture correctly;
only after that measurement is valid should sparse Vernier gain be tuned.
```

Do not use the current all-zero curve to justify changing the sparse active-stage count before the calibration problem is resolved.
