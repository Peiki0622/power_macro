# FTC Phase/Voltage 2-D Separability Analysis Plan

## 0. Purpose

This task is a **forward-only data-analysis step** built on the already completed standalone FTC RVT/LVT reproduction at commit `ce44a9bd7532430eadf051ea8df5a8e628c4d2d3`.

Do **not** redesign the FTC sensor, do **not** rerun the reproduction flow, and do **not** launch new HSPICE characterization unless a later plan explicitly asks for new physical evidence.

The only research question for this task is:

```text
Can the existing FTC output pair (start, end) be transformed into a 2-D feature
space in which supply-voltage motion and sampling-phase motion are sufficiently
non-collinear to support a low-cost phase-robust digital readout?
```

The analysis shall use the already characterized formal FTC operating range:

```text
VDD = 0.75 V .. 1.10 V
```

Do not reintroduce 0.70 V as a required operating point.

The two derived coordinates are:

```text
C = start + end
W = end - start + 1
```

where `C` captures XOR-window position and `W` captures XOR-window width.

The task is a **go/no-go experiment** for the proposed phase-aware 2-D decoding direction. It must end with a clear architectural decision, not merely a set of plots.

---

## 1. Existing baseline that must be treated as completed work

Do not rerun or re-prove the following results.

The current standalone FTC reproduction already establishes:

```text
technology                  = SMIC40LL
FTC high-Vt branch mapping  = RVT
FTC low-Vt branch mapping   = LVT
observable stages           = 30
selected RVT initial stages = 4
selected LVT initial stages = 0
selected capture phase      = 300 ps
formal VDD range            = 0.75 .. 1.10 V
static fine step            = 10 mV
static valid points         = 36/36
distinct (start,end) states = 21
longest reported plateau    = 20 mV
phase step                  = 13.718435 ps
phase anchors               = 1.10 V, 0.90 V, 0.75 V
```

The completed reproduction report also records nonzero phase-induced movement of the encoded boundaries and representative voltage-glitch blind placements. Those facts motivate this analysis but are not to be regenerated here.

This task must not touch:

```text
delay-line topology
initial-buffer topology
XOR bank
latch/FF capture topology
capture phase selection
selected FTC operating range
FTC structural RTL
Phase-3 files
CUSUM
```

---

## 2. Required input evidence and provenance handling

The analysis requires two existing physical datasets:

```text
delay_chain/ftc/runs/static_fine/static_transfer.csv
delay_chain/ftc/runs/phase_sensitivity/phase_sensitivity.csv
```

The static file supplies the 0.75--1.10 V `(start,end)` transfer at 10 mV spacing.
The phase file supplies `(start,end)` under `phi-delta`, `phi`, and `phi+delta` at 1.10 V, 0.90 V, and 0.75 V.

### 2.1 Do not rerun HSPICE if compact evidence is missing from a clean checkout

The current repository ignore policy may prevent some completed run CSV/JSON files from being available on a clean remote checkout.

If Codex finds the required compact CSVs in the existing working environment:

```text
use them directly
```

If Codex does **not** find them:

```text
STOP before analysis;
report exactly which completed compact evidence files are unavailable;
do not regenerate them by rerunning HSPICE.
```

If the files are locally available but untracked, preserve only the minimal compact analysis inputs in a tracked task-owned evidence directory such as:

```text
delay_chain/ftc/analysis/phase_voltage_2d/evidence/
```

with clear provenance fields pointing back to the completed reproduction run and selected operating point.

Do not commit raw HSPICE decks, `.lis`, waveforms, solver databases, or generated simulation state.

### 2.2 Input validation

Before calculating any metric, verify:

```text
static transfer has VDD points from 1.10 down to 0.75 V
all static points used in the analysis have valid=1
phase sensitivity contains all three VDD anchors
phase sensitivity contains negative, nominal, and positive phase offsets per anchor
start/end indices lie inside 0..29
end >= start whenever valid=1
```

Write an input-audit JSON. If the physical evidence is incomplete, fail explicitly rather than filling gaps by interpolation or assumptions.

---

## 3. Create one pure-analysis implementation

Create a task-owned analysis script, for example:

```text
delay_chain/ftc/scripts/analyze_phase_voltage_2d.py
```

The script must be a **pure post-processing tool**:

```text
no HSPICE invocation
no deck generation
no modification of ftc_config.json
no modification of selected operating point
no RTL simulation requirement
```

It shall accept explicit input paths and an output directory.

Suggested output root:

```text
delay_chain/ftc/analysis/phase_voltage_2d/
```

The script should be deterministic and suitable for unit testing with synthetic CSV inputs.

---

## 4. Step 1 - Build the canonical C/W dataset

For every valid static and phase-sensitivity sample compute:

```text
C = start_index + end_index
W = end_index - start_index + 1
```

Retain the original fields. Do not replace `(start,end)` with `(C,W)` in evidence.

Create:

```text
static_cw.csv
phase_cw.csv
```

Each static row must contain at least:

```text
VDD
start
end
C
W
valid
```

Each phase row must contain at least:

```text
VDD
phase_offset_s
start
end
C
W
valid
```

Also report exact unique counts and plateau information for:

```text
(start,end)
C
W
(C,W)
```

The purpose is to establish how much information each representation preserves before any phase-rejection transform is attempted.

### Step-1 completion gate

The complete existing physical dataset has been transformed into `(C,W)` without altering, smoothing, or rerunning any electrical result.

---

## 5. Step 2 - Plot the static VDD trajectory in the C-W plane

Generate a publication-oriented C-W trajectory using the static 10 mV dataset.

The figure must show:

```text
x-axis = C
 y-axis = W
points connected in VDD order
VDD direction clearly indicated
labels or callouts at least every 50 mV
1.10 V and 0.75 V endpoints explicitly marked
```

Do not smooth the trajectory.

A second companion plot should show:

```text
C versus VDD
W versus VDD
```

so that the origin of any 2-D motion remains interpretable.

The report must state whether VDD primarily produces:

```text
window translation (C change),
window-width change (W change),
or a combination of both.
```

Do not infer this qualitatively without reporting the measured values.

---

## 6. Step 3 - Overlay measured sampling-phase motion

At each existing phase anchor:

```text
1.10 V
0.90 V
0.75 V
```

place the three measured phase points on the same C-W plane:

```text
phi-delta
phi
phi+delta
```

Draw an arrow from `phi-delta` to `phi+delta` when the endpoints differ.

Do not invent a phase vector if all measured phase points map to the same `(C,W)` state. In that case record:

```text
phase-insensitive at the tested phase step
```

The key figure for this task must visually contain both:

```text
static VDD trajectory
measured phase perturbation arrows
```

This figure is the main qualitative evidence for or against 2-D separability.

---

## 7. Step 4 - Estimate local VDD-motion vectors robustly

Because `(start,end)`, `C`, and `W` are quantized integers, do **not** define the VDD direction from only one 10 mV adjacent difference. A single plateau could create a false zero derivative.

For each phase anchor, estimate a local VDD-motion direction from the existing static data using a small local neighborhood.

Recommended primary method:

```text
fit C(VDD) and W(VDD) by ordinary least squares in a local 40-60 mV neighborhood;
use the fitted slopes as the local VDD vector.
```

Use:

```text
one-sided neighborhood at 1.10 V
centered neighborhood near 0.90 V
one-sided neighborhood at 0.75 V
```

Record the exact VDD samples used for each fit.

Define the droop-direction vector consistently so that increasing droop has one sign convention across all anchors.

Also compute a simple endpoint displacement over the same local neighborhood as a sanity check. If the fitted and endpoint directions disagree strongly, report that the quantized trajectory is locally unstable and do not conceal the disagreement.

Output:

```text
local_voltage_vectors.csv
```

with at least:

```text
anchor_vdd
samples_used
vV_C
vV_W
fit_quality
endpoint_dC
endpoint_dW
```

---

## 8. Step 5 - Estimate measured phase-motion vectors

For each phase anchor, use the existing measured `phi-delta` and `phi+delta` samples.

Primary phase displacement:

```text
vPhi = [ C(phi+delta) - C(phi-delta),
         W(phi+delta) - W(phi-delta) ]
```

Also retain the nominal `phi` sample to show whether the response is symmetric around nominal.

Do not divide by phase time unless a per-second derivative is specifically needed for reporting; vector direction is the main quantity for this decision.

Output:

```text
phase_vectors.csv
```

with at least:

```text
anchor_vdd
phase_delta_s
C_minus
W_minus
C_nominal
W_nominal
C_plus
W_plus
vPhi_C
vPhi_W
phase_span_C
phase_span_W
```

If `vPhi=[0,0]`, explicitly mark the anchor as phase-insensitive at the tested perturbation rather than forcing an angle calculation.

---

## 9. Step 6 - Quantify VDD/phase separability

For every anchor where both vectors are nonzero, compute:

```text
cosine similarity
acute separation angle in degrees
```

Use the absolute cosine when discussing collinearity, because opposite directions are still non-separable for a scalar snapshot.

Interpretation:

```text
|cos(theta)| close to 1  -> voltage and phase motion are nearly collinear
|cos(theta)| close to 0  -> voltage and phase motion are close to orthogonal
```

Do not reduce the entire conclusion to one global number. Report all three anchors separately.

Also compute a pooled phase-nuisance direction from all measured phase displacements, but clearly label it as a derived global approximation.

Recommended pooled method:

```text
principal direction / first singular vector of the nonzero phase-displacement vectors
```

or an equivalent normalized least-squares direction.

Output:

```text
separability_metrics.json
```

containing:

```text
per-anchor voltage vector
per-anchor phase vector
cosine similarity
separation angle
pooled phase direction
variation of phase direction across VDD
```

### Critical interpretation requirement

The report must distinguish these cases:

```text
A. phase vectors are small everywhere;
B. phase vectors are significant but non-collinear with voltage vectors;
C. phase vectors are significant and nearly collinear with voltage vectors;
D. phase direction changes strongly with VDD so one global projection is questionable.
```

These cases lead to different architecture decisions.

---

## 10. Step 7 - Construct an ideal continuous phase-rejected projection

Only if the data show meaningful non-collinearity, construct a continuous-valued screening projection.

Let the pooled nuisance direction be:

```text
vPhi_global = [pC, pW]
```

A perpendicular projection can use:

```text
w_float = [pW, -pC]
```

For each static/phase sample compute a baseline-relative score:

```text
DeltaC = C - C_baseline
DeltaW = W - W_baseline
S_float = wC * DeltaC + wW * DeltaW
```

Use the nominal 1.10 V selected FTC state as the initial analysis baseline unless the data-processing report explicitly requires another reference. Do not modify the physical FTC calibration.

This floating projection is not a proposed hardware implementation. Its purpose is to answer:

```text
Is phase rejection mathematically available in the measured 2-D output at all?
```

Measure:

```text
static S_float versus VDD
number of distinct static score values
monotonicity with droop
maximum VDD plateau after projection
phase-induced S_float span at each anchor
full-range static S_float span
```

If the floating projection destroys VDD observability, stop the projection path and classify the direction as NO-GO for single-snapshot linear rejection.

---

## 11. Step 8 - Search only low-complexity hardware-friendly weights

If `S_float` is useful, search a deliberately small hardware-friendly set:

```text
a, b in {-4,-2,-1,0,1,2,4}
S_hw = a * DeltaC + b * DeltaW
```

Exclude `(a,b)=(0,0)`.

Equivalent sign/scaling duplicates should be normalized so the report does not pretend they are different architectures.

The objective is not to maximize one arbitrary scalar. Rank candidates by a transparent tuple such as:

```text
1. preserve correct/static droop direction
2. minimize phase-induced score span
3. preserve static distinguishability
4. minimize maximum static VDD plateau
5. prefer lower arithmetic cost / smaller coefficients
```

Do not use multipliers in the proposed hardware interpretation. Coefficients `1/2/4` map to sign, add/subtract, and shift operations.

For every shortlisted candidate report:

```text
(a,b)
static score range
distinct score states
maximum plateau width
phase span at 1.10/0.90/0.75 V
phase span normalized by full static score range
```

Also compare each candidate directly with using only:

```text
C
W
start
end
```

so the new projection must demonstrate value beyond simply renaming one existing boundary metric.

Output:

```text
projection_candidates.csv
projection_selection.json
```

---

## 12. Step 9 - Add a local voltage-versus-phase ambiguity metric

A projection can look globally good while still being useless near one operating region.

At each phase anchor, compare the measured phase-induced score span with the static score movement over a local voltage interval derived from existing data.

Use a 20 mV or nearest available symmetric/one-sided static interval and record the exact samples used.

For a score `S` report:

```text
phase_span_S
local_20mV_voltage_span_S
phase_to_voltage_ratio = phase_span_S / local_20mV_voltage_span_S
```

If the local voltage span is zero because of quantization, report the ratio as undefined/infinite and explicitly identify a local plateau. Do not add epsilon to hide the condition.

This metric gives an intuitive answer to:

```text
Is the tested sampling-phase uncertainty smaller or larger than the score change caused by a ~20 mV VDD movement?
```

Compute this for:

```text
C
W
S_float
selected S_hw
```

---

## 13. Step 10 - Define the architectural go/no-go decision

The task must end in exactly one of the following macro-level outcomes.

### Outcome A - GO: single-snapshot 2-D phase-rejected decoding is promising

Choose this only if the measured data show that:

```text
voltage and phase motion are clearly non-collinear at most tested anchors;
a useful floating projection exists;
a low-complexity integer projection retains meaningful static VDD response;
phase-induced score movement is materially lower than for raw position metrics;
the result is not obtained by collapsing nearly all static voltage states.
```

Then the next architecture task should be:

```text
implement only the selected low-cost phase-aware digital score;
keep the physical FTC front-end unchanged initially;
verify with replayed physical evidence before new HSPICE.
```

### Outcome B - CONDITIONAL: local separability exists but one global projection is not reliable

Choose this when:

```text
phase/voltage directions differ at some VDD regions but phase direction rotates strongly across VDD,
or a global integer projection helps one region while hurting another.
```

Do not immediately add analog hardware.

Recommend the next study as one of:

```text
2-D distance-to-baseline-manifold decoding
region-aware digital decoding
or phase-diverse sampling
```

The report must explain why a single global `a*C+b*W` score is insufficient.

### Outcome C - NO-GO: single-snapshot 2-D rejection is not physically supported

Choose this when:

```text
voltage and phase motion are near-collinear,
or phase-rejected projection also rejects most voltage information,
or static quantization makes the projection unusable.
```

In this case explicitly recommend moving to:

```text
phase-diverse / multi-phase sampling
```

rather than spending more time tuning a single-snapshot projection.

### Important rule

Do not force Outcome A because it is the desired hypothesis. A negative result is useful and should redirect the architecture cleanly.

---

## 14. Required report

Create:

```text
delay_chain/ftc/reports/FTC_PHASE_VOLTAGE_2D_SEPARABILITY.md
```

The report must be written as a research-result document, not a script log.

Required sections:

### A. Research question

State that the goal is to determine whether `(start,end)` contains a voltage-sensitive direction separable from sampling-phase motion.

### B. Baseline and data provenance

State:

```text
formal range = 0.75--1.10 V
selected FTC operating point
static dataset source
phase dataset source
no new HSPICE was run for this analysis
```

### C. Feature definition

Define:

```text
C = start + end
W = end - start + 1
```

and explain physically:

```text
C -> XOR-window spatial position
W -> XOR-window width / path-separation information
```

Phrase the physical interpretation as a measured working model, not as an assumed proof of invariance.

### D. Static C-W trajectory

Include measured tables/figures showing the VDD trajectory and separate C(VDD), W(VDD) behavior.

### E. Sampling-phase vectors

At 1.10, 0.90, and 0.75 V show the measured phase triplets and phase displacement vectors.

### F. Separability metrics

Include a table with:

```text
anchor VDD
local voltage vector
phase vector
|cos(theta)|
separation angle
interpretation
```

### G. Projection experiment

Compare:

```text
C only
W only
floating orthogonal score
best low-complexity integer score
```

For each include static distinguishability, plateau behavior, and phase sensitivity.

### H. Local ambiguity analysis

Report phase-induced score span versus local ~20 mV static VDD movement at all three phase anchors.

### I. Limitations

Explicitly state:

```text
only the already measured TT/25 C physical evidence is used;
phase characterization currently exists at three VDD anchors;
the analysis does not yet prove PVT robustness;
quantized start/end values make local derivatives discrete;
no claim of phase invariance is allowed unless supported by the measured data.
```

### J. Final architectural decision

End with exactly one headline:

```text
GO - pursue low-complexity single-snapshot 2-D phase-rejected readout
```

or

```text
CONDITIONAL - retain 2-D information but do not use one global projection
```

or

```text
NO-GO - move to phase-diverse sampling
```

Then explain in 3-6 concrete evidence-based bullets why that decision follows from the measurements.

---

## 15. Required figures and tables

Produce at least these compact publication-oriented outputs:

```text
Fig. 1  C-W static VDD trajectory with phase perturbation arrows
Fig. 2  C and W versus VDD
Fig. 3  raw C/W versus selected phase-rejected score under phase perturbation
Fig. 4  selected score versus VDD
Table 1 local voltage/phase vectors and angles
Table 2 projection candidates and phase/static metrics
```

Use existing project plotting conventions if available.

Do not smooth, interpolate away plateaus, or hide discrete code jumps.

If rendered figures remain ignored by repository policy, commit the exact CSV/JSON source data and the plotting script so figures are reproducible without HSPICE.

---

## 16. Unit and contract tests

Add analysis-only tests. They must not invoke HSPICE or VCS.

Cover at least:

```text
C/W calculation from known start/end
input validity rejection
phase-vector calculation
zero phase-vector handling
cosine/angle calculation
collinear synthetic example
orthogonal synthetic example
projection weight normalization
plateau detection
phase-to-voltage ratio with zero local voltage span
```

Also add one regression that reads the committed compact physical evidence and verifies the generated summary/report metrics can be regenerated deterministically.

Do not run Phase-3 regressions.

Do not rerun FTC electrical characterization as a test.

---

## 17. Repository deliverables

Expected task-owned outputs:

```text
plans/ftc_phase_voltage_2d_separability_plan.md

delay_chain/ftc/scripts/analyze_phase_voltage_2d.py

delay_chain/ftc/analysis/phase_voltage_2d/
    evidence/                    # only minimal tracked completed-run inputs if needed
    input_audit.json
    static_cw.csv
    phase_cw.csv
    local_voltage_vectors.csv
    phase_vectors.csv
    separability_metrics.json
    projection_candidates.csv
    projection_selection.json
    figures/ or figure-source data as repository policy permits

delay_chain/ftc/reports/FTC_PHASE_VOLTAGE_2D_SEPARABILITY.md

delay_chain/ftc/tests/test_phase_voltage_2d.py
```

Keep generated heavy simulation artifacts out of the commit because none are required for this task.

---

## 18. Macro-level execution flow for Codex

Follow this sequence exactly:

```text
verify existing compact evidence
        |
        v
build start/end -> C/W dataset
        |
        v
plot static VDD trajectory
        |
        v
overlay measured phase perturbations
        |
        v
estimate local voltage vectors
        |
        v
estimate measured phase vectors
        |
        v
compute angle / collinearity metrics
        |
        +---- near-collinear --------------------------+
        |                                             |
        |                                             v
        |                                    NO-GO: recommend
        |                                    phase-diverse sampling
        |
        v
construct ideal floating phase-rejected projection
        |
        +---- destroys voltage information ------------+
        |                                             |
        |                                             v
        |                                    NO-GO / CONDITIONAL
        |
        v
search low-complexity integer weights
        |
        v
compare phase span vs local ~20 mV VDD response
        |
        +---- one global projection stable ------------> GO
        |
        +---- only local/region-specific separation ---> CONDITIONAL
```

The central rule is:

```text
Use the completed FTC reproduction as immutable physical evidence.
This task decides whether phase robustness can be gained in the digital
(start,end)->(C,W) domain before any new analog or timing hardware is added.
```

---

## 19. Completion criteria

This task is complete only when:

```text
1. No new HSPICE reproduction/sweep was launched.
2. Existing static and phase evidence was audited and preserved with provenance.
3. Every physical sample has explicit start/end/C/W values.
4. The C-W VDD trajectory is plotted and quantified.
5. Phase perturbation vectors are plotted and quantified at all three existing anchors.
6. Local VDD vectors use a quantization-robust neighborhood rather than a single 10 mV difference.
7. Voltage/phase collinearity is reported per anchor.
8. A floating phase-rejection projection is tested only if supported by the data.
9. A small hardware-friendly integer-weight search is performed only after the floating projection is useful.
10. Raw C, raw W, and projected scores are compared fairly.
11. Local phase uncertainty is compared against an approximately 20 mV static voltage movement.
12. The final report states exactly one GO / CONDITIONAL / NO-GO decision.
13. The report clearly states what the result means for the next FTC architecture step.
14. All plots/tables are reproducible from committed compact evidence without rerunning HSPICE.
```
