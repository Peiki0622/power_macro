# BFE14-ARCH1-BENIGN-TEMP0: Dual-Reference Benign Temperature-Drift Compatibility Plan

Status: `ACTIVE_PLAN`

Branch: `bfe-multitap-latched-frontend`

Plan baseline commit: `77a1834516e3324b4cabfa09de52415865d8bacd`

## 0. Stage objective and macro direction

BFE13 has already frozen a correct minimal TRACK0 research RTL implementation: dual references, immutable startup/security anchor, mutable `M_REF_TRACK`, two-observation persistence, bounded +/-1 LSB E8 commit, alarm priority, stale-snapshot rejection, no E8-to-E4 bypass, and default-disable equivalence to BFE12 SIGN0.

BFE14 must **not redesign TRACK0**. It answers one narrower scientific question that BFE13 intentionally did not answer:

> Under physically generated **healthy temperature drift at nominal 1.10 V**, can the mutable tracking reference absorb benign sensor-code movement without the fixed startup/security anchor itself creating signed-RISE false alarms?

The causal structure to preserve is:

```text
healthy temperature change only
          |
          v
real frontend/capture M_FF(T)
          |
          +--------------------------+
          |                          |
          v                          v
   M_REF_TRACK path          startup security anchor
   ABS / TRACK0              signed RISE comparator
          |                          |
          v                          v
 tracking residual           e_anchor = M_FF-M_REF_STARTUP
 / ABS pressure              e_anchor > T_POS_RISE ?
```

This is a **one-dimensional healthy-temperature pilot**, not a full PVT campaign and not an attack/poisoning stage.

### Required scientific outcomes

BFE14 must characterize, without tuning the architecture to force a favorable result:

1. how much the real healthy captured `M_FF` moves with temperature relative to the frozen 25 C startup reference;
2. whether the startup/security-anchor signed-RISE rule at diagnostic `T_POS_RISE=18/19` remains quiet on the new healthy temperature samples;
3. whether the already-frozen minimal TRACK0 mechanism, using a predeclared non-production test configuration, actually reduces the mutable-reference residual on the new healthy event stream;
4. whether any observed incompatibility is caused by the fixed security anchor, by the small TRACK0 region/budget, or by neither.

A scientifically valid negative result is acceptable. Do **not** raise `T_POS_RISE`, enlarge `B_TRACK`, enlarge `T_TRACK`, change startup calibration, or regenerate process/waveform populations merely to obtain a PASS-looking detector result.

## 1. Hard scope boundaries

### Must remain unchanged

- frontend topology and cell choices;
- source-referenced Level-0 methodology;
- LATQ/DFF capture semantics;
- 30 taps and `M_FF=sum(i*q_ff[i])`;
- authoritative ARCH0 RTL;
- BFE12 SIGN0 RTL;
- BFE13 TRACK0 RTL;
- startup calibration arithmetic: four RISE + four FALL, exact `sum4 >> 2`;
- `M_MARGIN_RISE=22`, `M_MARGIN_FALL=24`;
- diagnostic signed candidates `T_POS_RISE in {18,19}` only;
- existing BFE8-BFE13 retained artifacts.

### Explicitly prohibited

- no D01/D02/D04 physical rerun;
- no D03/D05-D12;
- no droop waveform in the new physical runs;
- no VDD sweep: new physical temperature runs are at nominal `1.10 V` only;
- no process-corner matrix (`FF/SS/FNSP/SNFP`) in this stage;
- no aging model;
- no slow malicious droop / reference-poisoning experiment;
- no OPP/DVFS/rebase implementation;
- no security-anchor rebase;
- no FALL signed comparator;
- no threshold sweep beyond the already-frozen diagnostic `T_POS=18/19`;
- no production selection of `T_POS`, `T_TRACK`, or `B_TRACK`;
- no DC, STA, P&R, PrimeSim, area/power campaign, or silicon/PVT signoff claim;
- no TRACK0 RTL edits unless a reproducible implementation defect is found. If such a defect is found, stop BFE14 and classify it as a BFE13 RTL issue rather than silently repairing architecture during the temperature study.

## 2. Existing temperature authority and pilot points

The repository already contains a valid real-XOR temperature screen at TT, including nominal VDD `1.10 V`, with project-used temperature points:

```text
-40 C
 25 C
 85 C
125 C
```

Authority:

`delay_chain/ftc/analysis/real_xor_pvt_baseline/temperature_screen.csv`

At plan creation its blob SHA is `4daf454ca908a8ff7d77652a8cfc8c9c94240acd` and the 1.10 V rows are marked valid. These points are reused only as **project-supported temperature pilot coordinates**. Their existence does not imply that BFE14 is a PVT signoff campaign.

Freeze:

```text
T_STARTUP = 25 C
T_LOW     = -40 C
T_MID     = 85 C
T_HIGH    = 125 C
VDD       = 1.10 V nominal
```

New full-sensor physical data are required because the existing tap29/XOR PVT screen does not contain the complete 30-tap captured `q_ff/M_FF` behavior needed by TRACK0 and the security-anchor comparator.

## 3. BFE14-P0 - Fresh authority freeze + ARCH1 documentation sync

Create:

`delay_chain/ftc/analysis/b_fe_frontend/bfe14_arch1_benign_temp_drift/`

Fresh-read/hash at least:

- current branch HEAD;
- `delay_chain/ftc/analysis/b_fe_frontend/bfe13_arch1_track0_rtl/BFE13_TRACK0_GATE.json`;
- `delay_chain/ftc/analysis/b_fe_frontend/bfe13_arch1_track0_rtl/BFE13_TRACK0_REPORT.md`;
- `delay_chain/ftc/rtl/bfe_backend_ctrl_arch1_track0.sv`;
- `delay_chain/ftc/rtl/bfe_backend_arch1_track0_top.sv`;
- `delay_chain/ftc/analysis/b_fe_frontend/bfe5_arch1_candidate/BFE5_ARCH1_CANDIDATE.md`;
- BFE8 healthy/FPR retained artifacts and their physical-run ledger;
- BFE12 retained replay manifest/calibration authorities;
- `delay_chain/ftc/analysis/real_xor_pvt_baseline/temperature_screen.csv`.

BFE13 authority at plan creation:

```text
gate           = BFE13_ARCH1_TRACK0_RTL_FROZEN
status         = PASS
classification = DUAL_REFERENCE_EVENT_ATOMIC_TRACK0_RTL_PASS
```

### P0A architecture-document synchronization

Before new experiments, update only the ARCH1 architecture document to remove the now-stale statement that tracker implementation itself is wholly deferred. Add a concise BFE13 cross-reference stating:

- minimal TRACK0 **research candidate RTL now exists and is frozen**;
- BFE13 validated digital/event-atomic tracker mechanics only;
- real benign-drift efficacy, slow-attack poisoning robustness, trusted OPP/rebase, production parameters, PVT/silicon signoff remain deferred;
- ARCH0 remains the authoritative production contract.

Do not use this documentation sync to promote complete ARCH1 or to change the dual-reference architecture.

Create:

```text
P0_AUTHORITY.json
P0_REUSE_MATRIX.md
P0_SIMULATION_BUDGET.json
```

Gate:

`BFE14_TEMP0_P0_AUTHORITIES_AND_ARCH1_STATUS_FROZEN`

Commit and stop before P1.

## 4. BFE14-P1 - Freeze exact healthy-temperature reuse/stimulus contract, no simulation

The goal is to change **temperature only** while reusing the frozen healthy physical/capture methodology.

### 4.1 Reuse the existing process population

Use the already-frozen 30-seed healthy process population:

```text
41001..41030
```

Do not generate a new Monte Carlo population.

For every new temperature run, preserve the same seed-to-process mapping and record the existing process/random signature used by the BFE8-style flow. Cross-temperature samples for one seed must represent the same process instance; if the existing tool flow cannot guarantee that, stop before P2 and document the pairing failure.

### 4.2 Reuse the healthy waveform/event schedule

Locate the exact BFE8 healthy/FPR physical stimulus and capture runner that produced the retained 1.10 V healthy population. Reuse its:

- nominal supply waveform/background definition;
- healthy/no-droop condition;
- event timing;
- RISE/FALL event ordering;
- Level-0 conversion methodology;
- real LATQ/DFF capture mechanism;
- `q_ff -> M_FF` extraction;
- process-seed mapping.

The only intended physical variable in a new run is simulator temperature.

Do not create a new random-background waveform family merely for BFE14. Where a background seed/signature exists, preserve it across temperatures so differences are paired rather than confounded by a new noise realization.

### 4.3 Reuse 25 C data unless proven impossible

Primary rule:

> **Do not rerun the existing 25 C healthy population if retained BFE8/BFE12 artifacts can be proven stimulus-, seed-, calibration-, and capture-compatible with the new temperature flow.**

P1 must explicitly classify:

```text
NOMINAL25_REUSE_VALID
or
NOMINAL25_CONTROL_REQUIRED
```

`NOMINAL25_REUSE_VALID` requires documented equality/compatibility of process seed mapping, healthy waveform/event schedule, capture method, feature definition, and startup-reference semantics.

If compatibility cannot be established, do not automatically rerun all 30 nominal cases. P2 first permits only a small nominal control for the scout seeds. Full 25 C control population is authorized later only if the small control proves that a paired baseline is scientifically necessary.

### 4.4 Preselect scout seeds without looking at new-temperature outcomes

From retained 25 C startup/healthy data only, deterministically choose three scout seeds representing approximately low, median, and high `M_REF_STARTUP_RISE` (or, if ties make that ambiguous, low/median/high retained startup `M_FF` authority). Record the rule and exact seeds before any new temperature HSPICE run.

This prevents selecting scouts after seeing temperature behavior.

### 4.5 Freeze required output schema

Every new physical event row must carry enough provenance to pair temperatures:

```text
seed
mc/process signature
temperature_c
background/stimulus signature
event_index
polarity
q_ff
M_FF
M_REF_STARTUP_RISE
M_REF_STARTUP_FALL
source_run
capture_status
```

Create:

```text
P1_TEMP_STIMULUS_CONTRACT.json
P1_SCOUT_SEEDS.json
P1_NOMINAL25_REUSE_AUDIT.md
```

Gate:

`BFE14_TEMP0_P1_STIMULUS_AND_REUSE_FROZEN`

Simulation count remains zero. Commit and stop.

## 5. BFE14-P2 - Three-seed four-temperature scout

Run the smallest physical scout needed to validate the new one-dimensional temperature flow.

For the three preselected scout seeds, obtain full healthy captured event data at:

```text
T_LOW  = -40 C
T_MID  =  85 C
T_HIGH = 125 C
```

Use the retained 25 C result as `T_STARTUP` when P1 classified `NOMINAL25_REUSE_VALID`.

If P1 classified `NOMINAL25_CONTROL_REQUIRED`, P2 may additionally run the same three scout seeds at 25 C as a control. No other nominal rerun is allowed at P2.

### 5.1 Physical-flow rule

Reuse the exact BFE8-style source/capture methodology. If that established methodology requires a per-run VCS/LATQ-DFF capture step after HSPICE, reuse it exactly and count it separately in the run ledger. Do not replace the established capture path with a new Python threshold shortcut merely to reduce simulator count.

### 5.2 Scout checks

For every scout seed and temperature require:

- simulator completion;
- valid Level-0/capture result under the same methodology;
- `q_ff` width and `M_FF` range remain legal;
- cross-temperature process/random signature is paired correctly;
- background/stimulus signature is unchanged;
- no droop was injected;
- no frontend/capture RTL/netlist change occurred.

Compute only scout diagnostics:

```text
e_anchor = M_FF(T) - M_REF_STARTUP_selected
D_start  = abs(e_anchor)
```

For RISE, report whether `e_anchor > 18` or `e_anchor > 19`; do not modify either threshold.

### 5.3 Predeclared decision on full 85 C population

Use 85 C as an interior guard point, not automatically as a full-population campaign.

After the scout, set:

```text
FULL_85C_REQUIRED = true
```

if **any** scout seed/polarity shows that 85 C is non-monotonic relative to the 25/-40/125 trend in `M_FF`, or if 85 C is more critical than both endpoint temperatures for either:

- positive RISE `e_anchor` / signed-alarm proximity;
- absolute startup-reference displacement.

Otherwise:

```text
FULL_85C_REQUIRED = false
```

and the full population proceeds only at -40 C and 125 C. The final report must then describe 85 C as a three-seed interior scout, not population coverage.

Create:

```text
P2_SCOUT_PER_EVENT.csv
P2_SCOUT_SUMMARY.json
P2_SCOUT_RUN_LEDGER.json
```

Gate:

`BFE14_TEMP0_P2_SCOUT_VALID`

If process pairing or capture methodology fails, stop; do not broaden the experiment to hide the failure.

Commit and stop.

## 6. BFE14-P3 - Minimal full-population healthy temperature captures

Use all seeds `41001..41030`, reusing P2 physical results without rerunning them.

Mandatory full-population new temperatures:

```text
-40 C
125 C
```

Add full-population 85 C **only** if `FULL_85C_REQUIRED=true` from the frozen P2 rule.

### 6.1 No attack and no nominal duplication

- no D01/D02/D04 or any other droop runs;
- no VDD/corner/aging sweep;
- no repeated P2 scout runs;
- no 25 C rerun when `NOMINAL25_REUSE_VALID`.

If `NOMINAL25_CONTROL_REQUIRED`, first compare the three P2 nominal controls against the retained nominal artifacts. A full 30-seed 25 C control is allowed only if the P2 comparison demonstrates that retained nominal data cannot serve as a paired baseline. Record the exact reason before starting those additional runs.

### 6.2 Physical simulation budget

Expected primary new HSPICE budget when nominal reuse is valid and full 85 C is unnecessary:

```text
30 seeds x 2 endpoint temperatures = 60 unique healthy temperature runs
```

P2 runs are part of these 60 and must be reused, not repeated.

If full 85 C is required:

```text
+30 unique healthy 85 C runs
```

If a separate capture VCS step is intrinsically required by the frozen BFE8 physical-capture methodology, one capture replay per unique physical run is allowed; no additional attack/backend scientific regressions are authorized here.

Create a strict ledger distinguishing:

```text
new HSPICE physical runs
required capture-support VCS runs
reused retained 25 C data
reused P2 runs
backend scientific VCS regressions
```

### 6.3 Frozen physical output

Create at minimum:

```text
BFE14_HEALTHY_TEMP_PER_EVENT.csv
BFE14_HEALTHY_TEMP_PER_SEED.csv
BFE14_HEALTHY_TEMP_PHYSICAL_LEDGER.json
```

No threshold/parameter choice is made in P3.

Gate:

`BFE14_TEMP0_P3_HEALTHY_PHYSICS_FROZEN`

Commit and stop.

## 7. BFE14-P4 - Offline dual-reference compatibility audit, no simulator

Use only frozen P3/P2/retained 25 C data.

For every event compute two explicitly different quantities:

```text
e_anchor(T) = M_FF(T) - M_REF_STARTUP_selected
D_anchor(T) = abs(e_anchor(T))
```

and the temperature displacement relative to the paired nominal/startup authority.

Do **not** pretend that `e_anchor` is the post-tracking residual. The security anchor is intentionally fixed.

### 7.1 Security-anchor RISE audit

For RISE healthy events, evaluate only:

```text
e_anchor > 18
e_anchor > 19
```

Report per temperature and aggregate:

- number of healthy signed alarms;
- maximum positive `e_anchor`;
- minimum signed headroom `18-e_anchor` and `19-e_anchor` under the strict-comparator interpretation;
- affected seeds/events;
- whether the first conflict appears only at an endpoint or already at the 85 C scout/interior population.

No new `T_POS` sweep is allowed.

### 7.2 Startup/ARCH0 absolute-pressure audit

Using unchanged margins 22/24, report the healthy alarm pressure that would exist if the reference stayed at startup:

```text
abs(e_anchor) > margin_selected
```

This is a diagnostic baseline for why tracking may be useful; it is not a new ARCH0 signoff campaign.

### 7.3 Tracking-capacity diagnostics without tuning

Do not select `T_TRACK` or `B_TRACK` by optimizing false alarms.

Compute descriptive quantities only:

- per-seed/per-temperature signed displacement of healthy `M_FF` from startup;
- required reference displacement to recenter each observed event/steady block;
- fraction of events whose startup displacement already exceeds the **existing BFE13 directed-test-only** values `T_TRACK=5`, `B_TRACK=2`;
- maximum/median absolute temperature displacement.

The BFE13 values `5/2` remain explicitly `DIRECTED_TEST_ONLY`; they are reused only as a fixed probe, not promoted.

### 7.4 Interpretation classes

Freeze one of the following evidence outcomes (multiple secondary flags may coexist):

```text
SECURITY_ANCHOR_QUIET_ON_OBSERVED_TEMP_PILOT
SECURITY_ANCHOR_HEALTHY_CONFLICT_OBSERVED
BFE13_TEST_TRACK_WINDOW_COVERS_OBSERVED_DRIFT
BFE13_TEST_TRACK_WINDOW_TOO_NARROW
TEMPERATURE_RESPONSE_NONMONOTONIC_NEEDS_MORE_CHARACTERIZATION
```

A `SECURITY_ANCHOR_HEALTHY_CONFLICT_OBSERVED` result is not repaired inside BFE14.

Create:

```text
P4_DUAL_REFERENCE_AUDIT.csv
P4_DUAL_REFERENCE_SUMMARY.json
P4_DUAL_REFERENCE_REPORT.md
```

Gate:

`BFE14_TEMP0_P4_DUAL_REFERENCE_CHARACTERIZED`

Commit and stop.

## 8. BFE14-P5 - One TRACK0 RTL replay using the new physical healthy event stream

Run at most **one new backend scientific VCS regression**. Do not rerun the BFE12/BFE13 old retained equivalence suites; BFE13 already froze them.

### 8.1 Fixed A/B configurations; no parameter sweep

Replay the same new temperature event trajectories through:

```text
A = BFE13 TRACK0 default-disabled
    T_TRACK_RISE/FALL = 0
    B_TRACK_RISE/FALL = 0

B = BFE13 TRACK0 with the already-used BFE13 directed-test-only probe
    T_TRACK_RISE/FALL = 5
    B_TRACK_RISE/FALL = 2
```

Use `T_POS_RISE=18` and `19` as two already-frozen diagnostic subcases inside the same regression. Do not test additional `T_POS` values.

### 8.2 Event trajectory

For each seed, initialize with the frozen/reused 25 C startup calibration authority, then feed the healthy events from one temperature block in the same event order used by the physical capture. The purpose is to test the RTL response to real measured code displacement, not to invent a continuous temperature ramp.

Do not interpolate unmeasured `M_FF(T)` values and do not claim that a static temperature block reproduces a physical heating/cooling time constant.

### 8.3 Mandatory measurements

For both A and B report:

- combined healthy alarm count;
- ABS-only alarm count;
- signed-RISE-only alarm count;
- per-polarity `M_REF_TRACK` final displacement;
- accepted/rejected tracker updates;
- stale-snapshot rejections;
- residual `D_track` distribution at evaluated events;
- whether tracker movement reduces ABS pressure for any observed temperature block;
- whether any signed alarm is unchanged by tracker movement, confirming security-anchor isolation.

### 8.4 No pass-by-retuning rule

If BFE13's fixed `5/2` probe does not track the observed physical displacement, classify the result as a test-window limitation. Do not rerun VCS with enlarged parameters in BFE14.

If signed healthy alarms appear, do not raise `T_POS` or move the security anchor.

Gate:

`BFE14_TEMP0_P5_TRACK0_PHYSICAL_REPLAY_CHARACTERIZED`

Commit and stop.

## 9. BFE14-P6 - Final freeze and next-direction decision

Publish at minimum:

```text
P0_AUTHORITY.json
P0_REUSE_MATRIX.md
P0_SIMULATION_BUDGET.json
P1_TEMP_STIMULUS_CONTRACT.json
P1_SCOUT_SEEDS.json
P1_NOMINAL25_REUSE_AUDIT.md
P2_SCOUT_PER_EVENT.csv
P2_SCOUT_SUMMARY.json
P2_SCOUT_RUN_LEDGER.json
BFE14_HEALTHY_TEMP_PER_EVENT.csv
BFE14_HEALTHY_TEMP_PER_SEED.csv
BFE14_HEALTHY_TEMP_PHYSICAL_LEDGER.json
P4_DUAL_REFERENCE_AUDIT.csv
P4_DUAL_REFERENCE_SUMMARY.json
P4_DUAL_REFERENCE_REPORT.md
P5_TRACK0_REPLAY_RESULTS.csv
P5_TRACK0_REPLAY_SUMMARY.json
BFE14_BENIGN_TEMP_RUN_LEDGER.json
BFE14_BENIGN_TEMP_REPORT.md
BFE14_BENIGN_TEMP_GATE.json
```

Final gate:

`BFE14_ARCH1_BENIGN_TEMP_DRIFT_CHARACTERIZED`

The gate may be `PASS` when the characterization package is complete and internally consistent even if the architecture exposes a benign-temperature conflict. `PASS` therefore means **characterization completed**, not that ARCH1 is production-safe over temperature.

### 9.1 Final interpretation branches

#### Branch A - security anchor remains quiet on the observed pilot

If no observed healthy RISE sample crosses either diagnostic signed threshold and the physical/replay package is valid:

```text
next candidate stage = POISON0 / slow unauthorized droop
```

Do not start POISON0 inside BFE14.

#### Branch B - healthy security-anchor conflict is observed

If healthy temperature movement causes `e_anchor>18` and/or `e_anchor>19`:

```text
next candidate stage = TRUSTED-ANCHOR-MANAGEMENT / REBASE0 architecture study
```

Do not solve it by autonomous anchor tracking or by retuning `T_POS` in BFE14. The conflict means the trusted anchor policy needs a separately authorized mechanism/profile study.

#### Branch C - fixed security anchor is quiet but BFE13 `5/2` tracker probe is too narrow

Then the next stage may be a narrow TRACK-PARAM characterization using the frozen physical temperature data **without rerunning HSPICE**. Do not open a new physical campaign merely to tune `T_TRACK/B_TRACK`.

### 9.2 Claims explicitly forbidden from BFE14

Do not claim:

- full PVT robustness;
- minimum/maximum operating temperature guarantee;
- silicon guarantee;
- aging robustness;
- attack-poisoning resistance;
- trusted OPP/rebase correctness;
- production `T_POS`, `T_TRACK`, or `B_TRACK`;
- full ARCH1 promotion;
- physical Level-0 signoff.

## 10. Codex macro-direction guardrail

Execute strictly:

```text
P0 fresh authorities + ARCH1 BFE13 status sync
 -> commit / stop
P1 exact reuse and temperature stimulus freeze
 -> commit / stop
P2 3-seed temperature scout
 -> commit / stop
P3 minimal full healthy endpoint population
 -> commit / stop
P4 offline dual-reference audit
 -> commit / stop
P5 one new-physics TRACK0 RTL replay
 -> commit / stop
P6 final characterization freeze
 -> STOP
```

The intended research progression is:

```text
BFE12 SIGN0
  weak/short signed RISE recovery validated
       |
BFE13 TRACK0
  digital dual-reference tracker mechanics validated
       |
====================================================
BFE14 BENIGN-TEMP0                         <-- NOW
healthy temperature only, nominal 1.10 V
- reuse old 25 C whenever valid
- new physics only where temperature data are missing
- test fixed security anchor compatibility
- test existing TRACK0 5/2 probe without tuning
====================================================
       |
       +--> anchor quiet -> later POISON0
       |
       +--> anchor conflict -> later trusted anchor/rebase study
       |
       +--> tracker window only too narrow -> later offline parameter study
```

Do not drift from BFE14 into droop attacks, threshold optimization, OPP/rebase implementation, broad PVT, full temperature signoff, or frontend redesign. Reuse every scientifically compatible retained artifact and every completed scout run rather than rerunning it.
