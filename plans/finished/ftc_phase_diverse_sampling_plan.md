# FTC Phase-Diverse Sampling Improvement Plan

## 0. Purpose

This plan starts from the completed 2-D phase/voltage analysis and follows its explicit decision:

```text
NO-GO - move to phase-diverse sampling
```

The previous analysis established that the single-snapshot FTC output cannot reliably reject sampling-phase motion with one global linear transform. Therefore the next architectural question is no longer:

```text
Can one (start,end) snapshot be made phase-invariant digitally?
```

It is now:

```text
Can multiple deliberately separated capture phases provide complementary FTC
observations that reduce deterministic blind windows and phase ambiguity while
preserving the already validated 0.75--1.10 V sensing range and reusing the
same RVT/LVT delay-line + XOR front-end?
```

The work must remain inside the standalone FTC line of development.

Do not modify Phase-3.

Do not reintroduce 0.70 V as a required operating point. The formal supply range for this work is:

```text
0.75 V <= VDD <= 1.10 V
```

The key architectural principle is:

```text
Keep the expensive analog/time front-end shared.
Create diversity in capture phase first.
Only duplicate capture/storage hardware if measured same-event coverage proves
that a second simultaneous phase is worth the cost.
```

---

## 1. Completed evidence that must be treated as fixed baseline

Do not rerun the standalone FTC reproduction or the completed C/W separability study as routine regression.

The current baseline already establishes:

```text
technology                      = SMIC40LL
high-Vt FTC branch mapping      = RVT
low-Vt FTC branch mapping       = LVT
RVT initial stages              = 4
LVT initial stages              = 0
observable stages               = 30
selected nominal capture phase  = 300 ps
formal static range             = 0.75--1.10 V
static fine step                = 10 mV
static valid points             = 36/36
distinct (start,end) states     = 21
```

The completed 2-D study found:

```text
1.10 V: |cos(vV,vPhi)| = 0.996, acute angle = 5.04 deg
0.90 V: |cos(vV,vPhi)| = 0.964, acute angle = 15.42 deg
0.75 V: |cos(vV,vPhi)| = 0.894, acute angle = 26.57 deg
```

and the tested sampling-phase motion is comparable to or larger than a local ~20 mV static-voltage movement in the raw C/W coordinates.

Therefore:

```text
single-snapshot global phase rejection is closed for now;
do not reopen integer-weight tuning without new physical evidence.
```

The previous representative glitch study also showed changed and blind placements. Those data motivate phase diversity but are not sufficient to select a phase set.

---

## 2. Scope and non-goals

### 2.1 Keep the FTC physical sensing core unchanged during phase-diversity discovery

Initially preserve:

```text
4-RVT / 0-LVT initial-delay setting
30 RVT observable buffers
30 LVT observable buffers
30 corresponding-tap XORs
current latch/FF capture semantics
same VDD_A/VSS_A rail pair
same start/end encoder convention
```

Do not change:

```text
delay-cell type
observable length
initial-delay topology
RVT/LVT mapping
XOR tap mapping
bubble-repair rule
```

while searching for useful phase diversity.

### 2.2 Do not combine every proposed improvement at once

This task is specifically about **phase diversity**.

Do not simultaneously introduce:

```text
latch-only compressed capture
new sparse delay lines
new C/W linear projection
CUSUM
PVT-adaptive delay-line resizing
second FTC delay-line sensor
```

A later task may combine phase diversity with compressed capture after the phase-diverse benefit is physically proven.

### 2.3 New HSPICE is allowed only where new phase/glitch evidence is genuinely required

The previous analysis was pure post-processing. Phase diversity requires physical data at phases that have not yet been characterized, so new HSPICE is appropriate here.

However, do not rerun:

```text
cell discovery
mechanism-only FTC reproduction
XOR loading study
original 300 ps static fine sweep
previous C/W analysis
```

unless a later hardware modification changes the relevant physical boundary.

---

## 3. Two distinct phase-diverse architectures must be kept conceptually separate

Do not use the term “multi-phase” ambiguously. This plan must evaluate two different architectures.

### Architecture S - sequential phase interleaving

One physical capture bank is reused. The selected phase changes across successive FTC sampling cycles:

```text
sample n     -> phi_A
sample n+1   -> phi_B
sample n+2   -> phi_A
sample n+3   -> phi_B
```

Advantages:

```text
minimal hardware overhead
same delay lines / XOR bank / latch / FF bank
phase schedule can later be deterministic or pseudorandom
```

Limitation:

```text
a one-shot transient is observed at only one phase in the cycle in which it occurs;
this architecture cannot claim same-event multi-phase coverage.
```

### Architecture P - parallel same-launch dual capture

The same RVT/LVT/XOR front-end is observed by two capture phases for the same launched wavefront:

```text
shared RVT/LVT delay lines
        |
shared XOR bank
   +----+----+
   |         |
phi_A      phi_B
capture    capture
   |         |
state A    state B
   +----+----+
        |
      fusion
```

Advantages:

```text
same transient can be observed at two different capture phases
common blind windows can be reduced directly
```

Cost:

```text
additional capture/storage hardware and phase-control complexity
```

### Critical rule

First measure the **physical complementarity of phases** using separate HSPICE runs. Do not duplicate the capture bank in RTL/HSPICE before the data show that a useful phase pair exists.

The virtual union of independently simulated `phi_A` and `phi_B` observations is the first upper-bound estimate for Architecture P.

Architecture S must be evaluated with an explicit temporal schedule, not by incorrectly using same-launch union coverage.

---

## 4. Step 1 - Extend FTC characterization infrastructure for explicit arbitrary capture phase

Reuse the existing FTC HSPICE deck generator and characterization runner.

Add a task-owned phase-diversity analysis mode rather than a second independent simulation framework.

The new runner must accept an explicit list of capture phases and preserve:

```text
phase_id
capture_phase_s
VDD
raw_xor_word
latch_word
captured_xor_word
start_index
end_index
one_run_length
valid
bubble/run diagnostics
```

Do not mutate the selected 300 ps baseline operating point in `ftc_config.json` while screening candidates.

Store candidate-phase settings under a new task-local analysis/config object or explicit command-line input.

Suggested task-owned directories:

```text
delay_chain/ftc/runs/phase_diverse_screen/
delay_chain/ftc/runs/phase_diverse_static/
delay_chain/ftc/runs/phase_diverse_glitch/
delay_chain/ftc/analysis/phase_diverse/
```

Large HSPICE artifacts remain ignored; commit compact CSV/JSON evidence and authored reports.

### Step-1 completion gate

The existing physical FTC sensor can be simulated at caller-selected capture phases without changing its delay-line/XOR topology or the frozen 300 ps baseline configuration.

---

## 5. Step 2 - Build a bounded candidate phase set around the validated 300 ps point

Use the already measured local phase scale:

```text
Delta_phi_ref = 13.718435 ps
```

as a **search spacing**, not as a new frozen hardware delay.

Initial bounded candidate set:

```text
phi_k = 300 ps + k * Delta_phi_ref
k in {-4,-3,-2,-1,0,+1,+2,+3,+4}
```

This spans approximately 245--355 ps and is only a first characterization grid.

Do not assume all nine phases are usable.

### 5.1 Anchor-only physical screen first

For each candidate phase, run only:

```text
VDD = 1.10 V
VDD = 0.90 V
VDD = 0.75 V
```

No glitch yet.

Record the full captured word and encoded state.

A phase remains eligible only if:

```text
captured output is valid at all three anchors
no all-zero pathological capture appears
bubble behavior is bounded and explainable
state ordering versus VDD is physically consistent with the established FTC direction
```

A left-boundary run at 0.75 V is not automatically invalid; the current FTC baseline already uses a valid low-voltage boundary state. The relevant condition is valid/decodable operation, not arbitrary “interior only” forcing.

### 5.2 Do not fine-sweep all surviving phases

After the anchor screen, take only the surviving phases into a coarse static sweep:

```text
1.10, 1.05, 1.00, 0.95, 0.90, 0.85, 0.80, 0.75 V
```

Measure:

```text
valid point count
distinct (start,end) states
monotonic/systematic direction
largest adjacent encoded jump
boundary clipping
```

Shortlist only phases that preserve useful static sensing across the formal range.

### Step-2 deliverables

```text
phase_candidate_anchor.csv
phase_candidate_coarse.csv
phase_candidate_summary.json
```

### Step-2 completion gate

Produce a shortlist of approximately 3--5 physically valid capture phases that span the available timing neighborhood and retain the 0.75--1.10 V FTC behavior.

If only one phase survives, phase diversity is physically unsupported in the current capture topology and the task should stop before glitch expansion.

---

## 6. Step 3 - Establish phase-specific nominal baselines

The previous NO-GO result proves that different phases naturally move `(start,end)`.

Therefore no phase-diverse detector may compare every phase against the 300 ps nominal word.

For every shortlisted phase `p`, define its own no-glitch nominal baseline at 1.10 V:

```text
B_p = captured_xor_word(p, 1.10 V)
E_p = (start_p, end_p)
```

Keep both full-word and encoded baselines for analysis.

Create:

```text
phase_baselines.json
```

with:

```text
phase_id
capture_phase_s
nominal captured word
nominal start
nominal end
nominal length
```

### Detection metrics to preserve during research

Do not freeze one detector metric prematurely. For every glitch result compute at least:

```text
full_word_changed        = captured_word != B_p
encoded_state_changed    = (start,end) != E_p
boundary_distance        = |start-start_p| + |end-end_p|
```

The first is an upper-bound sensitivity metric; the latter two are more realistic candidates for low-cost digital readout.

Do not declare a final threshold until local no-glitch phase-jitter evidence is measured for the selected phase set.

---

## 7. Step 4 - Map phase complementarity with a bounded glitch campaign

The purpose of this step is not yet to claim universal glitch coverage. It is to answer:

```text
Do different valid capture phases detect different transient placements?
```

All droop depths in the formal study must respect the current 0.75 V lower limit when starting from 1.10 V.

Initial representative depths:

```text
50 mV
100 mV
200 mV
350 mV
```

Initial representative widths:

```text
50 ps
100 ps
200 ps
500 ps
1 ns
```

Do not use a 400 mV droop in this formal phase-diverse study because that would drive the rail below the current 0.75 V minimum.

### 7.1 First build an onset map for one medium case

Before running every amplitude/width combination, choose one medium case such as:

```text
200 mV depth
200 ps width
```

and sweep glitch onset relative to the FTC launch across the physically relevant observation interval.

Define onset in relative time:

```text
t_rel = glitch_start - launch_time
```

Cover at least:

```text
one glitch width before launch
through the latest shortlisted capture phase plus post-capture timing
```

Use a step derived from the measured phase scale and glitch width. Do not use a needlessly sub-ps global grid.

For every shortlisted phase record detection metrics against that phase's own baseline.

This produces:

```text
D[p, onset]
```

for the medium case.

### 7.2 Refine only around detection/blind boundaries

Once coarse onset boundaries are visible, locally refine the transitions rather than globally reducing the step size.

### 7.3 Expand only after phase complementarity is observed

If different phases have meaningfully different blind intervals, then repeat the onset mapping for the shallow/short and deep/long representative cases.

If every phase has essentially the same blind interval, stop and record that phase diversity is not solving the physical problem; do not spend compute on a large Cartesian sweep.

### Step-4 deliverables

```text
glitch_phase_map.csv
glitch_phase_map_summary.json
```

The summary must contain per phase and per glitch family:

```text
detection fraction
blind onset intervals
longest continuous blind interval
minimum/maximum detected boundary displacement
```

---

## 8. Step 5 - Select phase sets by coverage union, not by arbitrary spacing

Use the measured glitch map to evaluate every surviving two-phase pair and, only if necessary, three-phase set.

For Architecture P virtual same-launch coverage:

```text
D_pair(g) = D_phiA(g) OR D_phiB(g)
```

For each pair report:

```text
union detection fraction
longest common blind interval
number and total duration of common blind intervals
coverage of shallow/short cases
coverage of medium cases
coverage of deep/long cases
```

### Pair-selection priority

Rank phase pairs by:

```text
1. minimize longest common blind interval
2. maximize worst-case coverage across glitch families
3. maximize shallow/short-glitch coverage
4. preserve static validity at both phases
5. prefer smaller phase-set size and simpler phase separation
```

Do not choose the pair solely because its average detection fraction is highest.

A security sensor should avoid one large deterministic common blind region even if its average coverage is good.

### 8.1 Evaluate the marginal value of a third phase

Compute the best 1-phase, 2-phase, and 3-phase virtual same-launch results.

Report the incremental improvement:

```text
1 -> 2 phases
2 -> 3 phases
```

Prefer the smallest phase count with clear diminishing returns.

Do not automatically adopt four phases or an LFSR because the architecture drawing contains four symbolic phases.

### Step-5 deliverables

```text
phase_set_candidates.csv
phase_set_selection.json
```

---

## 9. Step 6 - Measure local jitter robustness of the selected phases

The previous 2-D analysis showed that approximately 13.7 ps phase movement can shift the encoded state by one or more taps.

Therefore the selected phase pair/set must have a phase-specific no-glitch tolerance envelope.

For each selected phase only, run a small no-glitch local phase perturbation around the selected phase.

Use a perturbation smaller than the phase spacing and derived from the available physical timing scale. Record the exact offsets used.

At:

```text
1.10 V
0.90 V
0.75 V
```

measure:

```text
captured word
start/end
boundary distance from nominal phase state
```

Construct a phase-specific accepted no-glitch set or maximum expected encoded movement.

Then re-score the previously generated glitch evidence with a **jitter-aware detection rule** such as:

```text
alarm only when encoded displacement exceeds the measured no-glitch envelope
```

Do not tune the envelope using glitch cases.

### Step-6 completion gate

The selected phase diversity still improves glitch coverage after normal local phase uncertainty is not counted as an attack.

If the apparent coverage gain disappears after jitter tolerance, reject that phase set and return to Step 5 without rerunning earlier candidate screens.

---

## 10. Step 7 - Evaluate Architecture S correctly: sequential phase interleaving

Do not use virtual same-launch OR coverage to describe the single-bank sequential architecture.

For a selected pair `{phi_A, phi_B}`, define a schedule such as:

```text
A, B, A, B, ...
```

and separately evaluate an optional pseudorandom schedule only after deterministic A/B behavior is understood.

### 10.1 Model glitch onset modulo the FTC sampling period

Use the current sampling period as the baseline cadence.

For each transient duration, evaluate onset over one complete sampling period and determine which phase actually observes the event in the cycle where it occurs.

Report:

```text
single-event detection coverage
coverage for glitches persisting across >=2 sampling cycles
worst-case detection latency
longest temporal blind interval
```

### 10.2 Be explicit about the limitation

Sequential phase interleaving may reduce attacker predictability and improve coverage for repeated/persistent events, but it does not produce two observations of the same one-shot event.

The final report must not describe Architecture S with Architecture P's union-coverage number.

---

## 11. Step 8 - Architectural decision gate: sequential versus parallel dual capture

At this point choose one of three outcomes.

### Outcome P - same-launch dual capture is justified

Choose this if:

```text
two-phase same-launch union materially reduces the measured common blind window;
sequential scheduling cannot reproduce that single-event benefit;
static validity is preserved for both phases;
jitter-aware scoring retains the coverage gain.
```

Then implement Architecture P.

### Outcome S - sequential phase scheduling is sufficient

Choose this only if the target threat model and measured results show that:

```text
repeated/persistent droops dominate;
A/B scheduling materially improves coverage or unpredictability;
the added parallel capture bank is not justified by the measured single-event gain.
```

Then implement Architecture S.

### Outcome N - phase diversity is insufficient

Choose this if shortlisted phases have highly overlapping blind intervals or phase/jitter uncertainty erases the gain.

Then stop this direction and recommend a later study of:

```text
higher sampling cadence
asynchronous/event-driven capture
or a different physical sensing aperture
```

Do not hide a negative result by increasing the number of phases indefinitely.

---

## 12. Step 9 - Implement only the selected phase-diverse architecture

Do not package both S and P as final hardware.

### If Outcome S is selected

Add a minimal phase-schedule layer around the existing one capture bank:

```text
phase scheduler
phase_id
phase-specific baseline table
existing FTC capture bank
phase-aware detector/fusion logic
```

The physical RVT/LVT/XOR front-end remains one copy.

### If Outcome P is selected

Keep one shared:

```text
RVT delay line
LVT delay line
XOR x30
```

and add only the extra capture observation required by the selected phase count.

For a two-phase solution, conceptually:

```text
shared XOR[29:0]
      |
  +---+---+
  |       |
latch A latch B
 phi_A    phi_B
  |       |
state A  state B
  +---+---+
      |
 jitter-aware OR/fusion
```

Do not duplicate the delay lines or XOR bank.

### 12.1 Keep compressed capture out of this implementation until phase diversity works

Use the current capture semantics first so that the only architectural variable is phase diversity.

After the phase-diverse hardware is validated, a separate follow-up task may replace duplicated FF storage with latch-domain boundary compression to reduce cost.

---

## 13. Step 10 - Realize the selected phases physically only after ideal-phase benefit is proven

The current HSPICE reproduction can place capture events with explicit timing sources, while the packaged RTL exposes capture controls externally.

Do not pretend that a SystemVerilog phase scheduler alone creates ~10 ps physical phase offsets.

After a useful phase pair/set is selected, design the smallest real phase-generation mechanism supported by the target library.

Candidate implementation direction:

```text
s_clk
  |
small tapped real-cell delay line
  |
phase tap select / pulse generation
  |
phi_A / phi_B capture controls
```

Use real standard cells and no behavioral `#delay` in synthesizable RTL.

The phase generator must use no additional reference-voltage rail.

### Physical phase-generator characterization

Measure:

```text
actual phase separation at 1.10 / 0.90 / 0.75 V
loading on s_clk
pulse width / latch-close correctness
capture-clock timing margin
```

Because a same-rail delay generator is itself voltage-sensitive, do not assume the ideal requested `phi_A/phi_B` remains constant in seconds as VDD changes.

The relevant acceptance condition is that the **integrated physical phase generator + FTC sensor** preserves the selected complementary observations across 0.75--1.10 V.

If a physically realizable phase tap shifts from the ideal phase, rerun only the selected-phase integrated screen, not the complete nine-phase search.

---

## 14. Step 11 - Trusted boot calibration for phase-specific baselines

Once physical phases exist, add a minimal trusted calibration sequence.

At trusted nominal startup:

```text
for each selected phase p:
    capture nominal FTC state
    record baseline E_p / B_p
freeze baseline table
enter runtime sensing
```

Runtime droop/fault events must not continuously update these baselines.

The calibration must therefore distinguish:

```text
trusted calibration state
runtime frozen sensing state
```

If initial-delay centering is added in a later project step, it must also freeze before runtime anomaly detection.

This plan does not require a sophisticated adaptive PVT tracker yet; it requires phase-specific nominal references so the detector does not confuse the intentional phase schedule with an attack.

---

## 15. Step 12 - Fine static validation only for the final selected phases

Do not run a 10 mV static sweep for every candidate phase.

After the final phase set and physical phase generation are selected, run:

```text
1.10 V down to 0.75 V
10 mV step
```

for each selected phase.

Required evidence per phase:

```text
all 36 points valid
(start,end) transfer
unique state count
largest voltage plateau
boundary behavior
bubble statistics
```

Also report the joint phase-tagged state:

```text
(phase_id, start, end)
```

but do not claim that extra state count alone equals better voltage resolution unless a decoding rule is demonstrated.

The selected phase-diverse architecture must not sacrifice the formal 0.75--1.10 V range.

---

## 16. Step 13 - Final glitch characterization for publication

After the selected hardware/phase generator is fixed, produce a final transient map.

Use the formal droop-depth ceiling of 350 mV from the 1.10 V nominal rail.

Characterize representative depths/widths with onset refinement around measured boundaries.

Report separately:

```text
baseline single-phase 300 ps result
selected phase-diverse result
```

For Architecture P report:

```text
same-event per-phase detection
union detection
common blind intervals
longest common blind interval
```

For Architecture S report:

```text
phase schedule
single-event coverage over one sampling period
coverage for repeated/persistent events
worst-case detection latency
```

### Full-cycle honesty requirement

In addition to the focused launch-to-capture observation window, evaluate glitch onset modulo one full sampling period for representative short glitches.

This distinguishes:

```text
blindness caused by capture-phase choice
from
blindness caused by the overall sampling cadence.
```

Do not claim phase diversity eliminates temporal blind windows if a short glitch can occur entirely between observation opportunities.

---

## 17. Step 14 - Hardware-cost and timing study

Once one architecture is selected, synthesize the added digital/control hardware and count the physical capture additions.

Report at least:

```text
shared RVT/LVT delay cells
shared XOR count
latch count
FF count
phase-generation cells
phase scheduler / phase-ID storage
baseline-register bits
fusion/detection logic
critical digital timing
```

Compare against the current standalone FTC baseline.

For Architecture P, emphasize that delay lines and XORs remain shared; only capture/readout cost grows.

For Architecture S, quantify the much smaller area cost but also report its weaker same-event coverage semantics.

Do not report normalized “overhead” without absolute cell-count/area evidence.

---

## 18. Step 15 - PVT study comes after phase set and physical generator are selected

Do not run a broad PVT matrix during candidate-phase discovery.

After the architecture is fixed, evaluate the available target-process corners and representative temperatures supported by the current PDK flow.

The purpose is to answer:

```text
Do the selected physical phase relationships remain usable?
Can trusted phase-specific boot baselines recover nominal state movement?
Does phase complementarity persist under PVT?
```

If PVT shifts the ideal phase positions, first use the existing physical phase tap choices / boot phase calibration capability before changing the FTC delay lines.

A later separate plan may add automatic initial-window centering if required.

---

## 19. Required analysis metrics

Every phase-diverse result must report more than average detection percentage.

Minimum metrics:

```text
per-phase static validity
per-phase nominal baseline
per-phase glitch detection fraction
pair/set union detection fraction
longest blind interval per phase
longest common blind interval for selected phase set
total common blind duration
shallow/short glitch coverage
phase-jitter no-glitch envelope
jitter-aware coverage
full-cycle short-glitch coverage
worst-case detection latency
hardware overhead
```

Useful secondary metrics:

```text
number of common blind intervals
minimum detected glitch width versus depth
phase-set marginal benefit (1->2, 2->3 phases)
phase-specific unique static states
```

---

## 20. Required final report

Create:

```text
delay_chain/ftc/reports/FTC_PHASE_DIVERSE_SAMPLING_RESULT.md
```

The report must be a research-result document and must include these sections.

### A. Motivation from the NO-GO result

State quantitatively that the previous single-snapshot C/W analysis found near-collinear voltage and phase motion and therefore did not justify a global phase-rejection projection.

### B. Phase-diversity hypothesis

Explain that the new approach does not attempt to algebraically remove phase motion from one snapshot. Instead, it intentionally samples at multiple characterized phases and exploits complementary detection apertures.

### C. Candidate phase qualification

Report:

```text
candidate grid
anchor validity
coarse static behavior
rejected phases and reasons
shortlisted phases
```

### D. Phase-specific nominal states

Table each shortlisted phase and its baseline captured word / start / end.

### E. Glitch phase map

Show detection versus:

```text
phase
relative glitch onset
width/depth family
```

Use a heatmap or equivalent publication figure.

### F. Blind-window complementarity

Report per-phase blind intervals and common blind intervals for phase pairs.

This is the central physical evidence for the new architecture.

### G. Phase-set selection

Compare best:

```text
single phase
2-phase set
3-phase set
```

and justify the smallest selected set from measured marginal benefit.

### H. Jitter-aware result

Show that the phase-diverse gain survives a no-glitch phase-uncertainty envelope.

### I. Sequential-versus-parallel distinction

Explicitly state whether the selected architecture is:

```text
sequential phase interleaving
or
same-launch parallel capture
```

and do not mix their coverage definitions.

### J. Physical phase-generation implementation

Describe how the selected phase offsets are realized with real target-library cells and how those offsets change across VDD.

### K. Static sensing preservation

Show final 0.75--1.10 V static transfer for the selected phase set and confirm that the FTC sensing range remains valid.

### L. Final transient coverage

Compare baseline 300 ps FTC and the selected phase-diverse architecture using:

```text
coverage
longest blind interval
common blind interval
latency
```

including full-sampling-period limitations.

### M. Hardware cost

Report the actual added cells/area/timing rather than only percentage claims.

### N. Limitations

At minimum discuss:

```text
finite sampling cadence
remaining blind intervals
phase-generator PVT sensitivity
threat-model difference between one-shot and repeated glitches
current PVT coverage
```

### O. Final architectural conclusion

End with one of:

```text
GO-P: same-launch dual-phase FTC capture is justified
GO-S: sequential phase-interleaved FTC is sufficient for the target threat model
NO-GO: phase diversity does not materially reduce measured blind windows
```

The conclusion must cite measured common-blind-window and jitter-aware evidence.

---

## 21. Required publication figures/tables

Produce source data and scripts for at least:

```text
Fig. 1  phase candidate static-validity / encoded-state map
Fig. 2  phase versus glitch-onset detection heatmap
Fig. 3  blind intervals for the best individual phases
Fig. 4  common blind interval: single phase vs best 2-phase set vs best 3-phase set
Fig. 5  jitter-aware coverage comparison
Fig. 6  final static transfer of selected phases over 0.75--1.10 V
Fig. 7  final baseline-vs-phase-diverse transient coverage map
Table 1 candidate phases and static qualification
Table 2 phase-pair coverage / common-blind metrics
Table 3 selected architecture hardware cost
```

Do not smooth detection boundaries or hide blind regions.

---

## 22. Verification and regression policy

Add FTC phase-diversity-specific tests only.

Do not rerun Phase-3 tests as part of this task.

Do not make regression tests launch completed broad HSPICE sweeps.

Tests should consume committed compact evidence and cover:

```text
phase-specific baseline lookup
pair/set union calculation
blind-interval extraction
longest common blind interval
sequential schedule semantics
parallel same-launch union semantics
jitter-envelope scoring
selected phase-set replay
config/RTL phase-ID consistency after packaging
```

HSPICE is run explicitly by characterization commands, not hidden inside unit tests.

---

## 23. Macro-level execution flow for Codex

Follow this order:

```text
completed NO-GO evidence
        |
        v
add arbitrary-phase characterization mode
        |
        v
anchor-screen bounded phase candidates
        |
        v
coarse static screen only for survivors
        |
        v
record phase-specific nominal baselines
        |
        v
medium-case glitch onset x phase map
        |
        +---- no complementary blind regions ----> NO-GO phase diversity
        |
        v
refine blind boundaries + representative glitch families
        |
        v
rank 2-phase sets; measure 3rd-phase marginal benefit
        |
        v
local no-glitch jitter characterization
        |
        v
jitter-aware phase-set re-evaluation
        |
        v
evaluate sequential schedule separately
        |
        v
choose P / S / N architecture
        |
        +---- P --> implement shared-front-end dual capture
        |
        +---- S --> implement single-bank phase scheduler
        |
        +---- N --> stop and report
        |
        v
real-cell phase generator
        |
        v
final selected-phase 10 mV static validation
        |
        v
final transient map + full-cycle blind-window analysis
        |
        v
hardware cost
        |
        v
PVT only after architecture is fixed
        |
        v
publish FTC_PHASE_DIVERSE_SAMPLING_RESULT.md
```

The central rule is:

```text
Do not add multiple capture banks because “multi-phase sounds better.”
First prove that the phases have complementary physical blind windows.
Then add only the minimum hardware needed to exploit the measured complementarity.
```

---

## 24. Completion criteria

This phase-diverse improvement task is complete only when:

```text
1. The previous single-snapshot NO-GO result is treated as closed evidence.
2. The formal operating range remains 0.75--1.10 V.
3. A bounded set of physically valid capture phases is characterized.
4. Every candidate uses its own nominal baseline.
5. Glitch detection versus phase and onset is physically measured, not inferred from C/W geometry.
6. Blind intervals and common blind intervals are explicitly extracted.
7. Best 1-, 2-, and 3-phase sets are compared and marginal benefit is reported.
8. Local no-glitch phase uncertainty is measured for the selected phases.
9. Coverage improvement remains after jitter-aware scoring.
10. Sequential and same-launch parallel semantics are evaluated separately.
11. Exactly one P/S/N architecture decision is made before final hardware packaging.
12. Delay lines and XOR bank remain shared in any selected phase-diverse hardware.
13. Physical phase offsets are implemented with real target-library cells before final claims.
14. Final selected phases preserve valid 0.75--1.10 V static sensing.
15. Final transient results report remaining blind windows and full-cycle cadence limitations honestly.
16. Hardware cost and timing are quantified.
17. PVT is evaluated only after the architecture/phase set is fixed.
18. The final report explains both the gain and the remaining limitations clearly enough to support a paper contribution.
```
