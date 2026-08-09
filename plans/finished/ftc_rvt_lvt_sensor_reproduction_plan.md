# Standalone FTC-Style RVT/LVT Sensor Reproduction Plan

## 0. Goal

Create a **standalone reproduction of the FTC sensor architecture** described in:

> M. R. Muttaki et al., “FTC: A Universal Framework for Fault-Injection Attack Detection and Prevention,” IEEE TVLSI, 2024.

This work is intentionally independent of the existing Phase-3 Vernier sensor.

The purpose of this task is only to answer:

```text
Can the FTC dual-delay-line / corresponding-tap XOR / capture / longest-1-run
architecture operate correctly with the real cells available in the target
SMIC40LL library over the intended 0.70 V .. 1.10 V supply range?
```

Do **not** use this work as a Phase-3 comparison study and do **not** merge the two architectures during this task.

The first implementation shall preserve the FTC architectural idea as directly as the target library permits:

```text
sampling clock
    |
    +--> initial delay --> RVT observable delay line --+
    |                                                  |
    +--> initial delay --> LVT observable delay line --+--> corresponding-tap XOR bank
                                                       |
                                                       v
                                                   latch bank
                                                       |
                                                       v
                                                     FF bank
                                                       |
                                                       v
                                            bubble-proof longest-1 encoder
                                                       |
                                                       v
                                                start / end indices
```

The original FTC ASIC architecture uses HVT/LVT cells. The target SMIC40LL library available to this project provides RVT and LVT but no HVT. Therefore the only intentional technology mapping in the reproduction is:

```text
FTC high-Vt path  -> RVT path
FTC low-Vt path   -> LVT path
```

Do not invent an HVT device and do not claim device-exact HVT/LVT reproduction. The report must call the result an **FTC-style RVT/LVT reproduction** while preserving the original dual-delay-line/XOR/capture/encoder structure.

---

## 1. Strict scope boundaries

Create a new independent work area:

```text
delay_chain/ftc/
```

Suggested structure:

```text
delay_chain/ftc/
├── discovery/
├── rtl/
├── scripts/
├── runs/
├── reports/
├── tests/
└── ftc_config.json
```

Do not implement this under `delay_chain/phase3/`.

Do not modify Phase-3 RTL, configuration, reports, run artifacts, or tests unless a generic repository helper must be reused without changing Phase-3 behavior.

The FTC reproduction shall **not** contain:

```text
Phase-3 sparse active-stage masks
Phase-3 D-versus-CK Vernier comparator bank
Phase-3 CAL_SEL aperture calibration
Phase-3 launch-load tuning
CUSUM
reference-voltage rail
second sensor lane
hybrid FTC/Vernier logic
PVT signoff in the initial reproduction pass
Monte Carlo in the initial reproduction pass
```

The initial task is architecture reproduction and physical validation, not final product signoff.

---

## 2. Forward-only execution rule

This plan is deliberately incremental.

### 2.1 Do not freeze every intermediate experiment into the final design

Parameters such as:

```text
initial delay length
sampling period / sampling phase
capture phase
```

are characterization variables until an integrated real-cell FTC sensor has been demonstrated.

Do not turn an early candidate into a permanent RTL constant merely because one intermediate experiment passed.

### 2.2 Do not rerun completed previous steps as routine regression

When a step produces compact evidence that is sufficient for the next step, consume that evidence and move forward.

Examples:

```text
- Once real RVT/LVT/XOR cells are discovered and their ports are recorded,
  do not repeat cell discovery in every later run.

- Once the mechanism-only nominal search selects a useful sampling region,
  do not rerun the entire search before every integrated experiment.

- Once the 9-point coarse sweep has identified the useful range, do not
  rerun the mechanism-only coarse sweep after the real capture bank is added.
  Run only the integrated cases needed to validate the changed capture layer.

- Unit/contract regression must consume compact recorded evidence; it must not
  regenerate earlier HSPICE sweeps.
```

### 2.3 Revisit an earlier physical experiment only when its interface changed

If a later modification changes the physical load seen by the delay line, only rerun the smallest experiment necessary to revalidate that affected interface.

Do not restart the plan from Step 1.

---

## 3. Source-derived FTC architecture to reproduce

The reproduction shall preserve these architectural properties from the FTC paper:

1. One sampling-clock source drives two delay paths.
2. The two paths use different threshold-voltage cell classes.
3. The observable sections contain corresponding stages on the two paths.
4. Corresponding observable taps feed XOR gates.
5. XOR outputs are captured through a latch stage and then a flip-flop stage.
6. The captured word is processed by a bubble-proof encoder.
7. The encoder identifies the start and end of the longest continuous string of `1`s.
8. Initial delay length is a tuning mechanism.
9. Observable delay length is kept fixed while the useful sensing window is positioned.
10. The paper uses an observable length of `N=30` in its implementation; use `30` for the first reproduction unless real-cell evidence proves that the target process cannot place a valid window inside it.

The primary sensor output contract is therefore:

```text
raw_xor_word[29:0]
captured_xor_word[29:0]
start_index
end_index
one_run_length
valid
```

Additional analysis metrics such as `start+end`, center, or unique-state count may be generated in reports, but they must not replace the FTC `start/end` output contract.

---

## 4. Step 1 - Discover only the physical cells required by FTC

Do not reuse a Phase-3 topology. Reuse only already-known PDK paths/cell names when they truly match this structure.

Discover and record real SMIC40LL cells for:

```text
RVT non-inverting delay element, preferably a buffer or two-inverter equivalent
LVT non-inverting delay element, preferably the matching drive family
2-input XOR
transparent latch
flip-flop for the post-latch register stage
clock buffer/inverter only if the physical capture schedule requires one
```

The initial preference is to use matching RVT/LVT drive strengths and matching logical topology on the two delay lines.

If a single real buffer cell is available in both RVT and LVT, prefer that direct mapping because it most closely matches the paper’s buffer-chain description.

If the library provides only suitable inverter cells for one or both paths, use two cascaded inverters per logical delay element so each observable stage is non-inverting. Record that implementation choice explicitly.

For every selected cell record:

```text
cell name
Vt class
CDL/netlist source path
Verilog model path if available
pin names
power/well pin mapping
logical truth function
```

For XOR and latch, also confirm input/enable polarity from the real library model. Do not infer polarity from the cell name.

### Latch availability gate

The FTC paper explicitly includes latches before the FF stage.

If no usable transparent latch exists in the installed target library:

```text
STOP the physical-capture implementation at that point,
record the library limitation,
list the nearest available sequential primitives,
and do not silently substitute a DFF while claiming exact FTC capture reproduction.
```

Mechanism-only delay/XOR characterization may continue, but the report must distinguish it from a complete capture-chain reproduction.

### Step-1 deliverables

```text
delay_chain/ftc/discovery/selected_cells.json
delay_chain/ftc/reports/CELL_DISCOVERY.md
```

### Step-1 completion gate

The exact real-cell topology and ports needed to build the FTC reproduction are known. No Phase-3 simulation is rerun.

---

## 5. Step 2 - Create FTC configuration and deck generator

Create `delay_chain/ftc/ftc_config.json` with characterization parameters rather than frozen final constants.

Initial values:

```text
technology                 = SMIC40LL
corner                     = TT
temperature                = 25 C
nominal VDD                = 1.10 V
minimum reproduction VDD   = 0.70 V
observable stages          = 30
coarse VDD points          = [1.10,1.05,1.00,0.95,0.90,0.85,0.80,0.75,0.70]
```

Include explicit characterization fields for:

```text
initial_rvt_stages
initial_lvt_stages
sampling_period
capture_phase
observable_stages
```

These are not runtime controls in the first reproduction. They are physical-characterization variables.

Create a dedicated HSPICE deck generator capable of rendering:

```text
A. mechanism-only dual line + XOR deck
B. integrated dual line + XOR + latch + FF capture deck
```

Both paths must use the same `VDD_A/VSS_A` rail pair.

Do not introduce `VDD_REF` or another reference rail.

### Step-2 completion gate

The generator can emit the FTC structure without using any Phase-3 sparse/Vernier module.

---

## 6. Step 3 - Validate the basic RVT/LVT wavefront mechanism at nominal VDD

Before adding capture cells, prove that the two real delay lines produce the spatial separation that the FTC XOR scheme requires.

Build:

```text
sampling edge
    |
    +--> RVT initial section --> 30-stage RVT observable line
    |
    +--> LVT initial section --> 30-stage LVT observable line
```

At every observable stage save or measure:

```text
RVT tap crossing time
LVT tap crossing time
RVT-LVT crossing-time difference
```

Do not add sparse stages, per-stage comparator DFFs, or Phase-3 launch calibration.

### 6.1 Nominal initial-delay/sampling search

The FTC paper states that initial delay length is adjusted while observable length remains fixed to position a useful XOR window.

The paper does not publish enough gate-level detail to justify fabricating one exact initial-length value for this target process. Therefore perform a bounded physical search using the real selected cells.

Search only enough combinations to place a nonempty XOR window well inside the 30-stage observable region at 1.10 V.

For each candidate sampling instant `Ts`, derive the logic state from the real HSPICE tap crossing times:

```text
rvt_bit[i] = 1 if t_rvt[i] <= Ts else 0
lvt_bit[i] = 1 if t_lvt[i] <= Ts else 0
xor_bit[i] = rvt_bit[i] XOR lvt_bit[i]
```

Do not yet instantiate a latch or FF.

Select a useful nominal region with these priorities:

```text
nonempty longest-1 window
window not clipped by observable stage 0
window not clipped by observable stage 29
room for the window/position to move as VDD decreases
simple initial-delay setting; avoid unnecessary extra cells
```

Do not optimize for a Phase-3 code target.

### Step-3 deliverables

```text
delay_chain/ftc/runs/mechanism_nominal_search/search.csv
delay_chain/ftc/runs/mechanism_nominal_search/selection.json
delay_chain/ftc/reports/MECHANISM_NOMINAL.md
```

Commit compact CSV/JSON/report evidence only, not large HSPICE listings/waveforms.

### Step-3 completion gate

At 1.10 V the real RVT/LVT paths can form a clear corresponding-tap XOR window inside the fixed 30-stage observable section.

If no such window can be formed with practical initial delay and sampling time, stop and report that the RVT/LVT separation in the target process does not reproduce the FTC mechanism under the tested structure. Do not invent sparse or offset-XOR modifications in this baseline.

---

## 7. Step 4 - Mechanism-only 0.70-1.10 V coarse sweep

Using the useful nominal region from Step 3, run the first supply sweep at:

```text
1.10
1.05
1.00
0.95
0.90
0.85
0.80
0.75
0.70 V
```

Do not rerun the nominal search.

For every VDD record:

```text
all 30 RVT tap crossing times
all 30 LVT tap crossing times
RVT wavefront word at Ts
LVT wavefront word at Ts
corresponding-tap XOR word
longest-1 start
longest-1 end
longest-1 length
number of 1-runs
whether the longest run touches either observable boundary
```

Use a software longest-run decoder only for this mechanism stage. The purpose is to understand the physical XOR pattern before capture logic is allowed to perturb the paths.

### Step-4 success direction

The expected qualitative FTC behavior is:

```text
VDD changes -> propagation position changes -> XOR encoded state changes
```

Do not require a predetermined numerical code slope that is not specified by the paper.

Require at minimum:

```text
- the XOR response is not constant across the full supply range;
- a valid nonempty window exists over a meaningful portion of the range;
- start/end or window position changes systematically with VDD;
- the response is not dominated by pathological alternating XOR bits.
```

If the window exits the 30-stage observable region at one end of the supply range, adjust the **initial delay placement or sampling period** as FTC intends and rerun only this 9-point coarse screen for the new candidate. Do not rerun Steps 1-3 from scratch.

If multiple candidate settings work, choose the one providing the broadest 0.70-1.10 V observable coverage with the simplest initial-delay hardware.

### Step-4 deliverables

```text
delay_chain/ftc/runs/mechanism_coarse/voltage_xor.csv
delay_chain/ftc/runs/mechanism_coarse/summary.json
delay_chain/ftc/reports/MECHANISM_COARSE.md
```

### Step-4 completion gate

The physical RVT/LVT delay lines show a usable FTC-style XOR response versus supply voltage before capture cells are added.

---

## 8. Step 5 - Add real corresponding-tap XOR cells and quantify observer loading

The mechanism study derived XOR logically from measured wavefronts. Now instantiate the selected real XOR cell at all 30 corresponding taps:

```text
xor[i] = RVT_observable[i] XOR LVT_observable[i]
```

Do not use tap offsets and do not cross-connect different stage indices in the baseline reproduction.

At nominal VDD, compare the delay-line crossing times before and after the 30 XOR input loads are attached.

Measure:

```text
per-path final observable crossing time
selected representative tap crossing times
RVT-LVT separation profile
raw real-XOR waveform/pattern at the selected sampling time
```

If the XOR input pins A/B have measurably different loading, first use the library-characterized pin mapping that minimizes systematic branch asymmetry. Do not add compensation hardware unless the measured asymmetry prevents a valid FTC window.

If compensation becomes necessary, document it as a target-library implementation detail and use the minimum real-cell change required.

### Step-5 completion gate

Real XOR loading does not destroy the FTC wavefront mechanism and a usable XOR window still exists.

Do not rerun the previous mechanism-only full sweep unless the XOR loading moves the observable window outside the supply range. In that case rerun only the 9-point real-XOR coarse screen.

---

## 9. Step 6 - Reproduce the FTC capture chain with real latch + FF cells

After the real XOR bank is validated, add the capture structure:

```text
30 real XOR outputs
       |
30 real transparent latches
       |
30 real FFs
       |
captured_xor_word[29:0]
```

### 9.1 Sampling-clock generator boundary

The FTC paper states that an external clock is scaled by a sampling clock generator and the resulting `s_clk` drives the FTC sensor, but the TVLSI article does not publish a complete gate-level sampling-clock-generator/capture-phase implementation.

Therefore do not claim an unpublished exact circuit.

Implement the minimum functional reproduction boundary:

```text
sampling clock period/frequency is explicit
launch edge is explicit
latch-enable/capture phase relative to s_clk is explicit
```

Keep the capture phase parameterized during characterization until a stable physical capture point is demonstrated.

The final report must distinguish:

```text
paper-specified architecture
versus
target-process implementation choice for the unpublished capture phase detail
```

### 9.2 Capture-phase characterization

At nominal VDD, sweep only a small timing neighborhood around the mechanism-selected sampling instant.

For each capture phase record:

```text
analog XOR state immediately before capture
latch outputs
FF outputs
captured_xor_word
longest-1 start/end
bubble/run count
```

Choose a phase that captures the intended XOR window without placing a large number of bits simultaneously inside ambiguous transitions.

Do not alter the delay-line architecture to force a preferred code.

### Step-6 deliverables

```text
delay_chain/ftc/runs/capture_nominal/capture_phase.csv
delay_chain/ftc/runs/capture_nominal/selection.json
delay_chain/ftc/reports/CAPTURE_NOMINAL.md
```

### Step-6 completion gate

The real latch/FF chain can physically capture a nonendpoint FTC XOR word corresponding to the analog XOR window.

---

## 10. Step 7 - Implement the bubble-proof longest-1 encoder

Create standalone FTC RTL under:

```text
delay_chain/ftc/rtl/
```

The digital encoder input is the 30-bit captured XOR word.

Required outputs:

```text
start_index
end_index
one_run_length
valid
optional diagnostic run_count / bubble_count
```

The core behavior is:

```text
find every contiguous run of 1s
select the longest run
return that run's start and end indices
```

Define deterministic tie behavior for two equal longest runs, e.g. choose the lower start index, and document it. The tie rule is an implementation detail; it must not silently change between software and RTL.

Do not convert the result into the Phase-3 thermometer-code format.

### 10.1 Decoder unit tests

Use synthetic patterns only; no HSPICE rerun.

Cover at least:

```text
single clean 1-run
single-bit run
run at left boundary
run at right boundary
all zeros
all ones
one small bubble splitting a long physical window
two unequal runs
two equal longest runs
```

If a bubble-repair step is introduced before longest-run extraction, keep the unmodified raw captured word available for evidence.

### Step-7 completion gate

Software reference decoder and RTL decoder agree bit-exactly on the synthetic contract set.

---

## 11. Step 8 - Integrated real-cell FTC coarse voltage characterization

Now combine:

```text
sampling clock
initial delay sections
30-stage RVT observable line
30-stage LVT observable line
30 real XORs
30 real latches
30 real FFs
longest-1 encoder
```

Use the selected characterization values from the previous steps.

Do not rerun mechanism-only sweeps.

Run integrated HSPICE at the same 9 coarse supply points:

```text
1.10, 1.05, 1.00, 0.95, 0.90, 0.85, 0.80, 0.75, 0.70 V
```

For each voltage commit compact evidence containing:

```text
raw analog XOR word at capture
latch word
FF captured word
encoded start
encoded end
one_run_length
valid
run/bubble diagnostics
last RVT observable crossing
last LVT observable crossing
```

### Integrated coarse gates

The integrated FTC reproduction is considered physically functional when:

```text
- real capture produces valid start/end data rather than a constant endpoint;
- encoded response changes with VDD;
- capture does not create persistent pathological bubbles across the range;
- the useful XOR window remains observable through the intended 0.70-1.10 V range,
  or any uncovered endpoint is explicitly attributable to observable-window placement;
- no extra reference-voltage rail is required.
```

If the integrated capture layer shifts the useful window because of physical loading/timing, retune only the affected `initial delay / sampling period / capture phase` variables and rerun the 9-point integrated screen. Do not repeat cell discovery or mechanism-only studies.

### Step-8 deliverables

```text
delay_chain/ftc/runs/integrated_coarse/voltage_xor.csv
delay_chain/ftc/runs/integrated_coarse/summary.json
delay_chain/ftc/reports/INTEGRATED_COARSE.md
```

---

## 12. Step 9 - Fine static voltage characterization

Only after the integrated 9-point screen is stable, run a finer static characterization over:

```text
1.10 V down to 0.70 V
```

Start with:

```text
10 mV step
```

Do not immediately use sub-mV resolution.

If the encoded states change on a scale smaller than 10 mV in a specific region, refine only that local region to 5 mV or finer as justified by observed transitions.

The purpose is to measure, not pre-assume:

```text
number of distinct (start,end) states
number of distinct start indices
number of distinct end indices
longest plateau in VDD
state transition voltages
monotonicity/systematic movement of window position
one-run-length behavior versus VDD
```

For analysis also report:

```text
position_sum = start + end
```

but keep `(start,end)` as the sensor's primary encoded output.

### Step-9 completion gate

A real-cell integrated FTC-style RVT/LVT sensor has a characterized static transfer over 0.70-1.10 V with all observable state transitions preserved in compact evidence.

---

## 13. Step 10 - Characterize sampling-phase sensitivity

FTC relies on a sampling clock, so sensitivity to sampling phase is part of the architecture and must be measured rather than hidden.

At a small set of representative VDD values such as:

```text
1.10 V
0.90 V
0.70 V
```

perturb the selected capture phase around nominal using a small physically meaningful timing offset derived from measured cell delays.

Do not hardcode +/-10 ps if the selected cell delays make that scale irrelevant; choose offsets from actual HSPICE transition spacing.

Record how much these values change:

```text
start
end
one_run_length
captured word
```

Report a sampling-phase sensitivity metric such as:

```text
maximum index movement per tested phase perturbation
```

This step characterizes a known architectural dependency; it is not a reason to redesign the FTC baseline yet.

---

## 14. Step 11 - Voltage-glitch reproduction after static behavior is proven

Only after the static FTC sensor is working, test the FTC claim that transient supply disturbances perturb the encoded response.

Use nominal supply:

```text
VDD = 1.10 V
```

Start with a small, interpretable matrix rather than a large attack search.

Suggested initial droop depths:

```text
50 mV
100 mV
200 mV
300 mV
400 mV
```

Suggested initial widths:

```text
50 ps
100 ps
200 ps
500 ps
1 ns
2 ns
4 ns
```

Perform phase placement relative to the sampling event, but do not generate every Cartesian combination immediately.

First choose representative shallow/medium/deep droops and short/medium/long widths to identify the capture window. Expand only around observed boundaries.

Record:

```text
pre-glitch nominal encoded state
glitch timing/depth/width
captured XOR word
start/end/length
detection state change yes/no
```

Do not claim arbitrary sub-cycle glitches are always detected. Publish blind phases/windows if observed.

This transient study remains inside the standalone FTC directory.

---

## 15. Step 12 - Package standalone structural RTL only after physical selection

Do not write final structural RTL for every characterization candidate.

After the integrated physical structure and capture schedule are selected, package:

```text
ftc_sampling_frontend.sv
ftc_rvt_delay_stage_struct.sv
ftc_lvt_delay_stage_struct.sv
ftc_xor_stage_struct.sv
ftc_capture_struct.sv
ftc_longest_run_encoder.sv
ftc_sensor.sv
ftc_config_pkg.sv
```

Names may be adjusted to repository style, but keep the hierarchy conceptually separated into:

```text
sampling/launch
physical delay lines
XOR observation
capture
encoder
```

Use only real standard-cell wrappers for physical cells.

No behavioral `#delay` may appear in synthesizable RTL.

The public standalone FTC interface should expose only what the reproduced architecture requires, e.g.:

```text
clock / reset / enable or sample request as required by the selected schedule
VDD_A / VSS_A
start_index
end_index
valid
```

Raw captured XOR may remain an internal retained net or optional debug output; do not force it into the final public macro interface unless needed.

---

## 16. Step 13 - FTC-only verification contract

Create tests under:

```text
delay_chain/ftc/tests/
```

Do **not** run the Phase-3 regression as part of this FTC task.

FTC tests should verify:

```text
selected real cell provenance
RVT/LVT mapping is explicit and no HVT is falsely claimed
observable length is 30 for baseline reproduction
corresponding tap i connects only to XOR i
no sparse masks or Vernier D/CK comparators exist
no VDD_REF/VSS_REF exists
real latch + FF capture structure matches selected physical implementation
longest-1 encoder contract
RTL elaboration with power-aware cell stubs
committed HSPICE captured words replay bit-exactly through the RTL encoder
config / HSPICE / RTL selected parameters agree
```

Tests must consume compact committed evidence and must not regenerate completed HSPICE sweeps.

---

## 17. Step 14 - Publish final reproduction report

Create:

```text
delay_chain/ftc/reports/FTC_REPRODUCTION_RESULT.md
```

Required sections:

### A. Reproduction scope

State clearly:

```text
original FTC: HVT/LVT
this target library: RVT/LVT because HVT is unavailable
architecture preserved: dual line, corresponding XOR, latch, FF, longest-1 encoder
```

### B. Real selected cells

List the exact delay, XOR, latch, and FF cells and source libraries.

### C. Initial/observable delay structure

Record:

```text
observable length = 30
selected initial delay structure
selected sampling period
selected capture phase
```

Clearly distinguish paper-defined concepts from target-process characterization choices.

### D. Mechanism evidence

Show nominal RVT/LVT wavefront timing and corresponding XOR window.

### E. Coarse voltage behavior

Table the 9 supply points with raw/captured word and start/end/length.

### F. Fine voltage behavior

Report all distinct stable encoded states and plateau widths over 0.70-1.10 V.

### G. Sampling-phase sensitivity

Quantify output movement under capture-phase perturbation.

### H. Transient voltage-glitch behavior

If Step 11 is completed, report detected and blind timing regions without overstating coverage.

### I. Hardware structure

Count:

```text
RVT delay cells
LVT delay cells
XOR cells
latches
FFs
sampling-clock support cells
encoder logic
```

### J. Final conclusion

Answer only:

```text
Does an FTC-style RVT/LVT sensor reproduce a usable fault-to-time/XOR response
in the target SMIC40LL environment?
```

Do not turn the report into a Phase-3 comparison unless a later, separate task explicitly asks for that comparison.

---

## 18. Final completion criteria

The standalone FTC reproduction is complete when:

```text
1. A separate delay_chain/ftc implementation exists.
2. The implementation contains full RVT and full LVT delay lines, not a sparse Vernier chain.
3. Observable length is 30 for the baseline reproduction unless a documented physical impossibility requires change.
4. Corresponding observable taps feed real XOR cells.
5. Real latch and FF capture stages reproduce the published FTC capture hierarchy, or a library limitation is explicitly documented if a latch is unavailable.
6. A bubble-proof longest-1 encoder returns start/end indices.
7. The real integrated sensor produces a nonconstant encoded response versus VDD.
8. The static transfer is characterized from 1.10 V to 0.70 V.
9. Sampling-phase dependence is explicitly characterized.
10. Transient voltage-glitch behavior is tested only after static operation is proven.
11. No Phase-3 sparse/Vernier/CAL_SEL/CUSUM logic is introduced into the FTC reproduction.
12. No Phase-3 HSPICE studies or regressions are rerun as part of this task.
13. Compact evidence is committed; large simulation products remain ignored.
14. The final report distinguishes paper-specified FTC behavior from unavoidable RVT-for-HVT and capture-phase implementation choices.
```

The macro-level execution direction is:

```text
real-cell discovery
    -> mechanism-only dual wavefront proof
    -> corresponding real XOR loading
    -> real latch/FF capture
    -> longest-1 encoder
    -> integrated coarse VDD screen
    -> fine static characterization
    -> sampling-phase sensitivity
    -> transient voltage-glitch characterization
    -> final structural RTL and report
```

Move forward through this chain. Do not repeatedly freeze intermediate candidates or restart completed earlier studies as regression. Only re-characterize the smallest physical boundary that a later design change actually affects.
