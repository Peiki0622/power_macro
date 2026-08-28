# B-FE7-DROOP12-W0: 12-scenario voltage-droop waveform contract

Status: `ACTIVE_PLAN`

Baseline branch: `bfe-multitap-latched-frontend`
Baseline commit at plan creation: `9794e960374a0e8b881a6c936ddbc69816d87cba`

## 0. Macro objective and hard stop boundary

This round constructs and freezes **twelve HSPICE-feedable voltage-supply waveforms only**. It does **not** evaluate ARCH0, does not tune any detector margin, does not implement ARCH1, and does not change the sensor/backend RTL. The output is a reusable benchmark stimulus package that later ARCH0 and ARCH1 studies must consume unchanged.

The benchmark shall be described as **12 representative elemental voltage-droop scenarios**, not as an exhaustive mathematical enumeration of every possible supply attack. The organizing principle is to span four orthogonal disturbance dimensions: amplitude, single-event temporal shape, repeated/compound behavior, and edge-relative timing.

The monitored-domain nominal supply for this benchmark is **1.10 V at 25 C**, taken from `delay_chain/ftc/ftc_config.json` (`nominal_vdd_v=1.1`, `temperature_c=25.0`). The previous 0.95 V CALN0/MARG0 operating point remains historical methodology evidence and must not be silently reused as the nominal operating point of DROOP12.

### Mandatory scope rules

- No ARCH0 detector experiment in this round.
- No ARCH0 margin selection or recalibration in this round.
- No ARCH1 design, RTL, tracking algorithm, temporal accumulator, extra feature, or anti-poisoning logic in this round.
- No production RTL edits.
- No DC/STA/P&R/PrimeSim/VCS-XA runs.
- **Default simulation count is exactly zero HSPICE runs.** These waveforms must be validated offline as HSPICE-compatible PWL sources; do not run HSPICE merely to prove that a text PWL file was generated.
- Do not rerun BFE3/BFE4/BFE5/BFE6 experiments. Old results may be read only to recover authoritative timing conventions and provenance.
- Do not reopen Level-0 physical implementation, latch aperture, runtime capture cadence, blind-window work, DVFS, PVT, or post-layout work.
- Do not modify `ftc_config.json`; read and hash it as authority.
- All generated waveforms shall be deterministic, hashable, and reproducible. No simulator-internal random noise source is allowed.
- The exact same frozen waveform files must be usable later for both ARCH0 and ARCH1 so the detector comparison cannot be biased by changing the attack set.

## 1. Authoritative repository inputs to audit before generation

Read and hash, without simulation:

- `delay_chain/ftc/ftc_config.json`
  - authority for SMIC40LL, TT, 25 C, and nominal VDD = 1.10 V.
- `delay_chain/ftc/analysis/t0_transient_droop/contract/T0_TRANSIENT_THREAT_CONTRACT.json`
  - authority for finite-slope PWL semantics, prohibition of zero-time voltage jumps, and attack phase definition.
- `delay_chain/ftc/scripts/bfe1_frontend.py`
  - authority for monitored rail node name `vdd_monitored`, source naming convention, and historical finite-slope HSPICE source rendering.
- `delay_chain/ftc/analysis/b_fe_frontend/bfe4_caln0_self_calibration/run_bfe4_caln0_self_calibration.py`
  - authority for the periodic system-edge convention: edges begin at 1 ns and repeat every 10 ns; the existing RISE study uses the 21 ns system edge.
- Existing BFE3/BFE4/BFE6 reports only for provenance and reuse accounting. Do not re-execute them.

Freeze the canonical waveform time frame:

```text
T_STOP      = 65 ns
T_E         = 21 ns   # canonical reference RISE edge
T_E1        = 31 ns   # following FALL edge
T_E2        = 41 ns   # following RISE edge
T_E3        = 51 ns   # following FALL edge
EDGE_SPACING= 10 ns
V_NOM       = 1.10 V
TEMP        = 25 C
```

The phase labels RISE/FALL are only reference markers for waveform construction in this round; no detector consumes them yet.

Gate: `BFE7_DROOP12_W0_AUTHORITY_FROZEN`

Stop and commit before proceeding.

## 2. W1 - Deterministic normal-supply background model

Purpose: prevent the future benchmark from treating a perfectly flat 1.100000 V rail as the only healthy operating condition. Every DROOP12 attack waveform shall be superposed on the same deterministic small-amplitude supply-ripple/noise realization.

Define

```text
VDD_k(t) = V_NOM + n_bg(t) - d_k(t)
```

where `n_bg(t)` is the normal background and `d_k(t) >= 0` is the scenario-specific attack depth. The background model is a **synthetic benchmark assumption**, not a foundry-guaranteed SMIC40LL ripple specification.

### W1.1 Canonical background noise contract

Generate `n_bg(t)` offline in Python from two seeded, piecewise-linear components:

1. `n_slow(t)` - low-frequency load/IR-drop wander
   - knot spacing: 2.5 ns
   - zero-mean bounded pseudorandom samples in `[-5 mV, +5 mV]`
   - linear interpolation between knots.
2. `n_fast(t)` - small fast switching/ripple component
   - knot spacing: 250 ps
   - seeded pseudorandom samples in `[-3 mV, +3 mV]`
   - remove sample mean over the full waveform before interpolation.
3. Sum and hard-limit the final background to `[-8 mV, +8 mV]` so the healthy rail remains inside `1.092...1.108 V`.

Use one canonical random seed, `7301`, for the twelve published benchmark waveforms. The same background realization is intentionally shared across D01-D12 so differences between scenario plots come only from the attack component. Future studies may add more noise seeds, but that must not redefine the twelve canonical attack components or replace seed 7301 in the paper-facing waveform atlas.

Do not use HSPICE `NOISE`, white-noise, or simulator-random sources. Use only explicit deterministic PWL points.

Create:

- `normal_background/NBG_7301.csv` containing at least `time_s,n_slow_v,n_fast_v,n_bg_v,vdd_healthy_v`.
- `normal_background/NBG_7301.inc` containing a HSPICE-compatible monitored-rail PWL source for healthy 1.10 V + noise.
- background SHA256 and generation metadata in the main contract.

Offline assertions:

- first and last point exist at 0 and 65 ns;
- time is strictly increasing;
- no non-finite values;
- `abs(n_bg) <= 8 mV` at every exported point;
- exported healthy VDD stays in `1.092...1.108 V`;
- rerunning the generator with seed 7301 reproduces byte-identical CSV/INC files.

Gate: `BFE7_DROOP12_W1_NORMAL_BACKGROUND_FROZEN`

Stop and commit. Zero simulator calls.

## 3. W2 - Freeze the twelve elemental attack components

Use a common fast edge slew of **10 ps** for abrupt trapezoidal transitions. This value is a benchmark stimulus parameter, not a claim about the fastest physically realizable board/package attack. It is finite by construction and consistent with the existing T0 contract's finite-slope sensitivity convention. No zero-time voltage jump is allowed.

For a rectangular pulse, define `plateau` as the time held at full attack depth; fall/rise slews are additional to the plateau. All depths below are voltage drops from the noisy instantaneous baseline, not absolute fixed rail voltages.

### Group A - Amplitude / positive controls

**D01 - SHALLOW_CANONICAL**

- depth: 30 mV
- fall: 10 ps
- plateau: 3000 ps
- rise: 10 ps
- plateau centered on `T_E=21 ns`.
- purpose: shallow single-event canonical challenge.

**D02 - MEDIUM_CANONICAL**

- depth: 60 mV
- same timing as D01.
- purpose: medium single-event control.

**D03 - STRONG_CANONICAL**

- depth: 140 mV
- same timing as D01.
- purpose: strong positive-control attack; 140 mV also preserves continuity with the repository's historical 1.10 V -> 0.96 V T0 stress point without rerunning that old experiment.

### Group B - Single-event temporal shape

**D04 - SHORT_MEDIUM**

- depth: 60 mV
- fall/rise: 10 ps
- plateau: 600 ps
- centered on `T_E`.
- purpose: same medium depth as D02 but much shorter exposure.

**D05 - DEEP_V_SHAPE**

- peak depth: 140 mV exactly at `T_E`
- no low-voltage plateau
- attack depth ramps linearly from 0 at `T_E-750 ps` to 140 mV at `T_E`, then linearly back to 0 at `T_E+750 ps`.
- purpose: deep transient with no steady low-voltage dwell.

**D06 - SLOW_FALL_FAST_RECOVERY**

- final depth: 60 mV
- linear fall of attack rail from zero depth at `T_E-2.5 ns` to full 60 mV depth at `T_E-0.1 ns` (2.4 ns fall)
- full-depth hold from `T_E-0.1 ns` to `T_E+0.1 ns`
- recovery from 60 mV depth to zero in 10 ps starting at `T_E+0.1 ns`.
- purpose: distinguish slow supply sag from abrupt rectangular glitches while still crossing the meaningful edge.

### Group C - Repeated / compound attacks

**D07 - DOUBLE_SHALLOW**

- two identical pulses
- depth: 30 mV
- each pulse: 10 ps fall + 800 ps plateau + 10 ps rise
- pulse centers: `T_E` and `T_E1` (21 ns, 31 ns).
- purpose: two consecutive weak events on alternating meaningful-edge polarity.

**D08 - FOUR_PULSE_SHALLOW_BURST**

- four identical 30 mV pulses
- each pulse: 10 ps fall + 800 ps plateau + 10 ps rise
- centers: `T_E`, `T_E1`, `T_E2`, `T_E3` = 21/31/41/51 ns.
- purpose: repeated weak evidence across four consecutive meaningful edges.

**D09 - STAIRCASE_SAG**

- cumulative attack depth steps: 10, 20, 30, 40 mV
- transition to the next depth occurs with a 10 ps finite ramp at 21/31/41/51 ns respectively
- retain 40 mV depth until 58 ns, then recover to zero depth in 10 ps.
- purpose: gradual malicious/abnormal supply sag over multiple system edges; later useful for adaptation/anti-poisoning studies, but no ARCH1 work is allowed now.

### Group D - Edge-relative timing / multi-edge extent

**D10 - PRE_EDGE_MEDIUM**

- depth: 60 mV
- 10 ps fall ending at `T_E-3000 ps`
- 3000 ps full-depth plateau ending exactly at `T_E`
- 10 ps recovery beginning at `T_E`.
- purpose: medium droop whose energy is overwhelmingly before the reference edge while the rail is still at full depth immediately before that edge.

**D11 - POST_EDGE_MEDIUM**

- depth: 60 mV
- 10 ps fall ending exactly at `T_E`
- 3000 ps full-depth plateau beginning at `T_E`
- 10 ps recovery after the plateau.
- purpose: mirror of D10, with energy overwhelmingly after the reference edge.

**D12 - DUAL_EDGE_SHALLOW_SPAN**

- depth: 30 mV
- 10 ps fall
- full-depth plateau from `T_E-1 ns` through `T_E1+1 ns` (12 ns plateau)
- 10 ps recovery
- purpose: one shallow supply event spanning both the 21 ns RISE and 31 ns FALL markers.

### W2 invariants

For every scenario:

- actual exported rail is `1.10 V + NBG_7301 - attack_depth`;
- the background realization is byte-identical/common across all twelve cases;
- no attack changes system clocks, capture gates, reset, or any circuit parameter;
- no PWL point occurs at negative time or after 65 ns;
- every finite-slope segment is explicit;
- no attack waveform is tuned using future ARCH0/ARCH1 alarm results;
- D01-D12 identifiers and numeric definitions become immutable once W2 gate passes.

Create `DROOP12_SCENARIOS.csv` and `DROOP12_WAVEFORM_CONTRACT.json` with exact parameters, semantic descriptions, group membership, reference-edge markers, generator version, baseline commit, source hashes, and `frozen=true` only after validation.

Gate: `BFE7_DROOP12_W2_SCENARIO_CONTRACT_FROZEN`

Stop and commit.

## 4. W3 - Generate HSPICE-feedable stimulus files, but do not simulate

Implement one generator, preferably:

`delay_chain/ftc/analysis/b_fe_frontend/bfe7_droop12_waveforms/generate_droop12_waveforms.py`

The generator must consume only the frozen contract and background seed and emit each waveform into:

```text
waveforms/
  D01_SHALLOW_CANONICAL.csv
  D01_SHALLOW_CANONICAL.inc
  ...
  D12_DUAL_EDGE_SHALLOW_SPAN.csv
  D12_DUAL_EDGE_SHALLOW_SPAN.inc
```

Each CSV must contain at least:

```text
time_s,noise_v,attack_depth_v,vdd_v
```

Each `.inc` must contain exactly one monitored-domain source with the current project node convention, e.g.:

```spice
V_VDD_MONITORED vdd_monitored vss_a PWL(
+ <time0> <voltage0>
+ <time1> <voltage1>
+ ...
)
```

Do not include detector, sensor, clock, LATQ, DFF, or backend circuitry in these files. They are reusable supply-stimulus includes only.

The generator shall merge all noise knots and attack breakpoints, linearly evaluate the background at any added attack breakpoint, sort times, and reject duplicate or nonmonotonic timestamps. Do not emit unnecessarily dense 1-ps sampled files when a much smaller exact piecewise-linear knot set represents the same waveform.

Gate: `BFE7_DROOP12_W3_HSPICE_PWL_PACKAGE_READY`

Stop and commit. HSPICE/VCS/DC invocation count remains zero.

## 5. W4 - Offline waveform validation and anti-drift regression

Implement `validate_droop12_waveforms.py` and deterministic unit tests. This stage validates the stimulus files themselves; it does not run a circuit.

Required checks:

- exactly 12 unique D01-D12 scenarios exist;
- every scenario uses `V_NOM=1.10 V`, `TEMP=25 C`, `NBG seed=7301`, and 65 ns stop time;
- `.inc` source name/node contract is exactly `V_VDD_MONITORED vdd_monitored vss_a`;
- PWL times are strictly increasing and SI-formatted;
- no zero-time voltage jumps;
- expected attack breakpoints, depths, widths, centers, staircase steps, and pulse counts exactly match W2;
- actual `vdd_v = 1.10 + noise_v - attack_depth_v` at every CSV point within numerical tolerance;
- healthy background range remains 1.092...1.108 V;
- attack rail remains above the current project formal 0.8 V minimum;
- D10 and D11 are time-mirrored around `T_E` in attack component semantics;
- D07 has exactly 2 pulses and D08 exactly 4 pulses at 10 ns spacing;
- D12 spans both `T_E` and `T_E1` at full attack depth;
- regenerated artifacts are byte-identical and all hashes match the manifest;
- source files contain no ARCH0/ARCH1 logic or detector-dependent parameter.

Create `DROOP12_MANIFEST.json` with SHA256 for the contract, generator, normal background, all 24 CSV/INC scenario artifacts, validation script, and final figures when available.

Gate: `BFE7_DROOP12_W4_WAVEFORM_VALIDATION_PASS`

Stop and commit. Any failure must be fixed only in waveform-generation logic/contract consistency; do not launch detector experiments to debug it.

## 6. W5 - SCI-style visualization of all twelve scenarios

This visualization is a mandatory deliverable and the terminal activity of the round.

Implement `plot_droop12_waveforms.py` that reads the **generated CSV files**, never re-derives the scenario values independently. The plot is therefore a visualization of the exact HSPICE-feedable stimuli.

Produce one paper-facing 12-panel waveform atlas:

- filename: `BFE7_DROOP12_WAVEFORM_ATLAS.pdf` (vector) and `BFE7_DROOP12_WAVEFORM_ATLAS.png` (>=600 dpi);
- layout: 4 rows x 3 columns, with rows corresponding to Groups A/B/C/D;
- each panel title contains scenario ID and short name only, e.g. `(a) D01 Shallow canonical`;
- x-axis: time relative to `T_E`, in ns; choose a panel window that exposes the full scenario, while keeping the time reference explicit;
- y-axis: `VDD_MONITORED (V)` with consistent limits wherever possible;
- actual noisy HSPICE input waveform is the primary solid trace;
- 1.10 V nominal reference is a thin dashed horizontal line;
- meaningful system edges covered by a panel are thin vertical dotted markers labeled R/F only when necessary to avoid clutter;
- optionally overlay the noiseless attack envelope `1.10-d_k(t)` as a thin secondary trace, but the noisy actual waveform must remain visually dominant;
- use a restrained SCI-paper aesthetic: white background, serif/Times-like text if available without bundling fonts, compact 7-9 pt labels, thin axes, no decorative gradients, no 3-D effects, no large title banner, no saturated rainbow palette;
- figure must remain readable in grayscale and at single-column/two-column paper scaling;
- legend appears at most once for the whole figure;
- annotate amplitude/width only when it materially helps; do not clutter every panel with redundant text.

Also produce `BFE7_DROOP12_WAVEFORM_ATLAS_CAPTION.md` containing a publication-ready caption that states: nominal 1.10 V, deterministic bounded normal background, scenario groups, and that these are stimulus definitions only with no detector-result implication.

Before accepting the figure, mechanically verify that every plotted trace hash/source path maps to the frozen CSV manifest. Do not manually redraw idealized versions for the paper.

Gate: `BFE7_DROOP12_W5_SCI_VISUALIZATION_PASS`

Stop and commit.

## 7. W6 - Final package and terminal gate

Publish under:

`delay_chain/ftc/analysis/b_fe_frontend/bfe7_droop12_waveforms/`

at minimum:

```text
DROOP12_WAVEFORM_CONTRACT.json
DROOP12_SCENARIOS.csv
DROOP12_MANIFEST.json
DROOP12_RUN_LEDGER.json
generate_droop12_waveforms.py
validate_droop12_waveforms.py
plot_droop12_waveforms.py
normal_background/NBG_7301.csv
normal_background/NBG_7301.inc
waveforms/D01_*.csv/.inc
...
waveforms/D12_*.csv/.inc
BFE7_DROOP12_WAVEFORM_ATLAS.pdf
BFE7_DROOP12_WAVEFORM_ATLAS.png
BFE7_DROOP12_WAVEFORM_ATLAS_CAPTION.md
BFE7_DROOP12_REPORT.md
BFE7_DROOP12_GATE.json
```

`DROOP12_RUN_LEDGER.json` must explicitly record:

```text
hspice_runs = 0
vcs_runs     = 0
primesim_runs= 0
dc_runs      = 0
arch0_tests  = 0
arch1_tests  = 0
```

The final report shall state only that twelve deterministic, HSPICE-feedable, noisy-1.10-V voltage-droop scenarios have been constructed, validated offline, hashed, frozen, and visualized. It shall make **no claim** about ARCH0 detection rate, ARCH1 improvement, false-positive rate, fault coverage, victim timing faults, or optimality of the waveform amplitudes.

Final gate:

`BFE7_DROOP12_WAVEFORM_CONTRACT_FROZEN`

The next stage may evaluate the frozen files on ARCH0, but that is explicitly outside this plan and must be separately authorized.

## 8. Execution discipline for Codex

- Execute W0 -> W6 exactly in order; commit after each stage gate.
- This round is stimulus construction, not detector research. If code starts importing `bfe_backend_top`, calculating `D_M`, choosing margins, running VCS, or checking alarms, stop: that is scope drift.
- Do not rerun old simulations to obtain waveforms that can be reconstructed analytically from the frozen contract.
- Read old HSPICE scripts only to preserve node names, time conventions, and finite-slope semantics; never overwrite historical artifacts.
- Never tune D01-D12 based on whether ARCH0 is expected to pass or fail. The benchmark must be frozen before detector results are observed.
- All randomness is explicit, seeded, exported, and hashable; simulator-random noise is forbidden.
- Maintain one canonical normal background realization for the paper-facing twelve waveforms so scenario-to-scenario differences are attributable to attack shape.
- If a waveform definition must change after W2, invalidate W2-W6 gates, increment a contract revision, regenerate all twelve stimuli and the atlas, and document why. Do not silently edit one scenario after detector testing.
- The macro research direction remains: establish a reproducible supply-attack benchmark first, then use the unchanged benchmark to expose ARCH0 limitations and later justify ARCH1. This plan stops before that comparison.
