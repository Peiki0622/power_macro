# B-FE6-MARG0: ARCH0 calibrated detection-margin characterization plan

Status: `ACTIVE_PLAN`

Baseline branch: `bfe-multitap-latched-frontend`
Baseline commit at plan creation: `a397c84622ff7255c037ebaf4133279d4999014e`

## 0. Macro objective and hard direction

This plan does not redesign the sensor or backend. Its only objective is to turn the already validated voltage sensitivity + startup self-calibration + TIM0-pipelined ARCH0 backend into an empirical end-to-end detection-margin characterization at the existing 0.95 V / 25 C methodology anchor.

Question to answer: after each process instance acquires its own healthy startup reference, what are the empirical distributions of `D_M = abs(M_FF - M_REF)` for normal and voltage-droop events, and what fixed programmable `M_MARGIN_RISE/FALL` values are supported by those data?

This is a characterization stage, not physical signoff or a universal operating-range claim.

### Frozen architecture; do not change

- 30 taps; RVT prefix 4; LVT prefix 0.
- Ideal behavioral Level-0 restoration remains intentional. Do not restart physical level-shifter work.
- `30 x LATQ -> 30 x DFF -> q_ff[29:0]` remains frozen.
- `M_FF = sum(i*q_ff[i]), i=0..29`, 9-bit, remains frozen.
- Startup calibration remains 4 valid RISE + 4 valid FALL samples, separate references, then `CAL_LOCK`; no continuous adaptation.
- Detection remains `D_M = abs(M_FF - M_REF_selected)` and strict `D_M > M_MARGIN_selected`.
- TIM0 protocol remains E0 capture, E4 consume, E7 alarm, E8 sticky, one event per probe clock.
- ARCH1/GFBT, DVFS/OPP banks, LUT/ML/fusion, raw-code repair, bubble correction, clock-glitch fusion, latch-aperture work, off-edge blind-window work, physical Level-0 implementation and new backend features are out of scope.
- `0.8...1.1 V` is only a sensor-characterization envelope. MARG0 uses 0.95 V / 25 C only as the existing methodology anchor.

### Mandatory reuse-first rule

Before any HSPICE/PrimeSim/VCS/DC run, first prove the requested datum cannot be obtained from retained repository evidence. Reparse/recompute retained CSV/JSON/manifest/waveform products whenever possible. Do not rerun a case merely to make this stage self-contained.

Do not rerun:

- B-FE3-VD1 0.95/0.92/0.89/0.86 V single-instance amplitude sweep merely to reproduce published M values.
- B-FE4-CALN0 existing 30 paired seeds, their four calibration samples, 0.95 V normal sample, or existing 0.95->0.92 V sample.
- B-FE5 backend synthesis/TIM0 timing closure, event-alignment test, LATQ/DFF preservation tests, or timing sweep unless this plan exposes a real backend RTL bug.
- Four identical HSPICE nominal samples for deterministic calibration. If fixed seed/fixed stimulus gives one deterministic nominal code and no event-to-event noise model exists, one physical result may be replayed four times into RTL to exercise the 4-sample protocol.

Every new physical simulation must be justified by a concrete missing-data item and counted in a run ledger.

## 1. Authoritative retained evidence

Inventory and hash at least:

- `delay_chain/ftc/analysis/b_fe_frontend/bfe3_vd1_droop_amplitude_response/`
  - `BFE3_VD1_REPORT.md`, `BFE3_VD1_ANALYSIS.json`, `BFE3_VD1_DFF_SAMPLES.csv/json`, `BFE3_VD1_MANIFEST.json`
- `delay_chain/ftc/analysis/b_fe_frontend/bfe4_caln0_self_calibration/`
  - `BFE4_CALN0_REPORT.md`, `BFE4_CALN0_RESULTS.csv/json`, `BFE4_CALN0_ANALYSIS.json`, `BFE4_CALN0_MANIFEST.json`
- `delay_chain/ftc/backend/reports/BFE5_TIM0_PIPELINE_CONTRACT.md`
- current `bfe_backend_top.sv`, `bfe_backend_ctrl.sv`, `bfe_m_feature.sv`, capture-bank RTL.

Preserve known history:

- VD1 fixed-timing single-instance points: 0.95/0.92/0.89/0.86 V with M_FF 287/273/234/208 for the published RISE case.
- CALN0: 30 paired process instances with healthy 0.95 V calibration/normal and 0.95->0.92 V shallow-droop evidence; its historical gate was `BFE4_CALN0_INCONCLUSIVE`, not PASS.
- CALN0 signed `DeltaM_DROOP_i` is not the ARCH0 decision variable when sign can reverse. MARG0 must derive `D_M = abs(M_DROOP_i - M_REF_i)` explicitly.

# Stage M0 - Evidence inventory and exact availability matrix

Purpose: determine exactly what can be answered with zero new simulation.

Allowed: repository parsing, hashes, schema inspection, CSV/JSON recomputation.
Forbidden: HSPICE, PrimeSim, VCS, DC, RTL changes.

Create under `delay_chain/ftc/analysis/b_fe_frontend/bfe6_marg0_detection_margin/`:

- `M0_EVIDENCE_MATRIX.md`
- `M0_EVIDENCE_MATRIX.json`

For RISE/FALL and voltage targets 0.95/0.92/0.89/0.86 V record: source artifact/hash, process-seed count, calibration availability, normal-validation availability, droop availability, q_ff/M_FF availability, seed/random-vector identity proof, and whether per-chip D_M is derivable without rerun.

Also inspect retained CALN0/VD0/VD1/periodic products for usable FALL data even if prior reports focused on RISE. Exhaust retained data before declaring FALL absent.

Gate: `BFE6_MARG0_M0_EVIDENCE_AUDIT_READY`

Stop and commit. Do not launch missing simulations in M0.

# Stage M1 - Zero-new-simulation shallow-droop calibrated screen

Entry: M0 gate.
Simulation budget: zero HSPICE, zero PrimeSim, zero DC; VCS unnecessary.

Using the retained 30-seed CALN0 population:

1. Reconstruct each startup reference with the same integer arithmetic as ARCH0 from retained four calibration samples.
2. Compute `D_NORMAL = abs(M_NORMAL - M_REF)`.
3. Compute `D_DROOP_092 = abs(M_DROOP_092 - M_REF)`.
4. Keep reverse/no-response seeds; never assume one sign of M movement.
5. Preserve seed/q_ff provenance.

Emit:

- `M1_PER_SEED_DM.csv`
- `M1_DISTRIBUTION_SUMMARY.json`
- `M1_MARGIN_SWEEP.csv`, threshold `T=0..435`, exact rule `D_M > T`
- empirical CDF/histogram for normal and 0.92 V D_M
- normal max/high quantiles, droop min, `G=min(D_droop)-max(D_normal)`, FPR(T), TPR(T), FNR(T)

Do not require perfect separation. If `G<=0`, report overlap and characterize the tradeoff; do not modify detector logic to force PASS.

Ablation: reproduce the historical CALN0 absolute-M screen only if its exact rule is recoverable from retained artifacts. If not, report the gap; do not invent a favorable absolute detector.

Gate: `BFE6_MARG0_M1_RETAINED_SHALLOW_MARGIN_CHARACTERIZED`

Stop and commit. No new HSPICE in M1 regardless of result.

# Stage M2 - Minimal RISE amplitude extension across same process population

Entry: M1 complete and M0 proves paired 0.89/0.86 V process-population data are missing.

Purpose: obtain amplitude-dependent D_M distributions without rerunning calibration/normal/0.92 cases.

Use the exact CALN0 seed list/process-randomization method and frozen RISE timing. Reuse each seed's existing M_REF and healthy evidence. Run only the missing 0.89 V and 0.86 V droop cases. Do not rerun 0.95 or 0.92 V.

Before running, establish a deterministic seed/provenance contract. Every new case must prove it is the same process instance as the retained CALN0 seed using the existing random-signature mechanism or equally direct repository-authoritative identity check. Mismatched seed evidence is invalid.

Freeze droop timing, clocks, topology, cells, ideal Level-0, LATQ/DFF capture timing and probe schedule. Vary only droop floor. Default voltage set is exactly 0.92/0.89/0.86 V; do not add points without a documented need.

Merge new samples with retained 0.92 V data and emit amplitude-wise empirical CDFs, per-seed paired traces, gap/FPR/TPR tables and `VDD_DROOP x margin` detection matrix.

Gate: `BFE6_MARG0_M2_RISE_AMPLITUDE_POPULATION_CHARACTERIZED`

If seed identity cannot be maintained, stop with `BFE6_MARG0_M2_PROVENANCE_BLOCKED`; do not rerun all calibration/normal data to work around provenance.

Stop and commit.

# Stage M3 - FALL-path evidence closure, reuse first

Entry: M2 complete unless M0 already proves complete FALL population evidence exists.

Purpose: close independent RISE/FALL references and margins without assuming RISE results apply to FALL.

First reparse retained periodic/capture/VD/CALN0 products for FALL q_ff/M_FF. If sufficient same-seed FALL evidence already exists, do offline analysis only.

Only if evidence is genuinely absent may new physical simulation run. Minimal authorized FALL set:

- one deterministic healthy 0.95 V FALL capture per required process seed;
- missing FALL droop captures at 0.92/0.89/0.86 V for the same seeds.

Do not run four identical healthy HSPICE captures per seed only because RTL consumes four calibration events. Replay a verified deterministic healthy FALL code four times later in RTL. If retained evidence contains genuine event-to-event variation, use those distinct retained samples instead.

Do not redesign falling-edge frontend, gate timing, latch aperture, or sensor structure. Emit separate RISE/FALL distributions and threshold tables; never pool polarities before margin selection.

Gate: `BFE6_MARG0_M3_RISE_FALL_DISTRIBUTIONS_READY`

If FALL cannot be closed without changing frozen capture architecture, stop with `REVIEW_REQUIRED`.

Stop and commit.

# Stage M4 - Margin selection and calibrated-detector ablation

Entry: M3 distributions ready.
Simulation budget: zero HSPICE/PrimeSim/DC; analysis only.

Sweep every integer margin 0..435 independently for RISE and FALL with exact RTL rule `D_M > margin`. Report:

- fixed-condition healthy FPR;
- TPR/FNR for 0.92/0.89/0.86 V;
- normal p95/p99/max and droop min/median/p05 where meaningful;
- separation gap per amplitude;
- Pareto table of margin versus FPR/TPR;
- if zero empirical FPR is possible, report its shallow-droop TPR but do not call it final silicon margin;
- if distributions overlap, retain overlap honestly and choose at most a candidate margin using an explicit criterion.

Do not add temperature, arbitrary VDD drift, synthetic noise or random jitter in MARG0. Label all results `0.95 V / 25 C fixed-condition process-population characterization`. PVT/benign guardband is a later stage.

Perform calibration ablation on the same population using the exact historical CALN0 absolute-M rule if recoverable. Otherwise restrict claims to observed spread reduction and do not invent an optimistically tuned comparator.

Candidate outputs: `M_MARGIN_RISE_CANDIDATE`, `M_MARGIN_FALL_CANDIDATE`. They are characterization candidates, not frozen product settings.

Gate: `BFE6_MARG0_M4_MARGIN_SWEEP_COMPLETE`

Stop and commit.

# Stage M5 - Real ARCH0 RTL replay

Entry: M4 complete with candidate margins or explicit no-single-margin result.

Purpose: prove offline decisions match the implemented TIM0-correct ARCH0 RTL. Do not resynthesize backend.

Use retained/new q_ff/safe_d vectors:

1. Replay four healthy RISE and four healthy FALL calibration events with frozen E0/E4 protocol.
2. Verify CAL_LOCK and internal references against golden analysis values.
3. Replay representative healthy/droop events from multiple seeds and characterized amplitudes.
4. Check DROOP_ALARM at E7 and sticky at E8 against strict-`>` offline decision.
5. Include `D_M == margin` quiet boundary, `D_M == margin+1` alarm boundary, reverse-direction M movement, alternating RISE/FALL and overlapped events.

No HSPICE is required for RTL replay; use captured vectors. No DC rerun is required because RTL/timing architecture is unchanged.

Gate: `BFE6_MARG0_M5_RTL_REPLAY_PASS`

If a real RTL bug appears, fix only the minimal bug with dedicated regression and rerun only affected RTL regressions plus TIM0 event alignment, not the historical HSPICE campaign.

Stop and commit.

# Stage M6 - Final package and paper-facing claims

Entry: M5 PASS. No new simulation.

Publish under `delay_chain/ftc/analysis/b_fe_frontend/bfe6_marg0_detection_margin/`:

- provenance/evidence matrix
- per-seed calibration and D_M tables
- margin sweeps
- separate RISE/FALL normal-vs-droop empirical CDF figures
- droop-amplitude detection table
- calibration ablation figure/table if historically reproducible
- RTL replay summary
- run ledger distinguishing reused versus new simulations
- `BFE6_MARG0_REPORT.md`
- `BFE6_MARG0_GATE.json`

Allowed conclusion: at the 0.95 V / 25 C methodology anchor, across the characterized process population, per-chip startup normalization produces empirical normal/droop D_M distributions from which fixed RISE/FALL candidate margins and measured FPR/TPR are reported, and those decisions reproduce in implemented ARCH0 RTL.

Do not claim universal 0.8...1.1 V normal operation, final silicon false-positive rate, temperature/PVT robustness not simulated here, physical Level-0 correctness, post-layout signoff, continuous-adaptation robustness, or coverage outside the defined meaningful sampling threat model.

Final Gate: `BFE6_MARG0_DETECTION_MARGIN_CHARACTERIZED`

This gate means fixed-condition ARCH0 detection margin is empirically characterized and RTL-replayed; it does not mean final PVT guardband/signoff is complete.

## Execution discipline for Codex

- Execute exactly one stage at a time in order; emit stage gate/report and commit before entering the next stage.
- A stage may skip new simulation only when M0 proves required evidence already exists; record the reuse explicitly.
- Reuse first, simulate only missing evidence, and keep a run ledger with reason/count for each new HSPICE/PrimeSim/VCS invocation.
- Never turn overlap/INCONCLUSIVE into PASS by adding backend logic, changing threat model, deleting reverse-response seeds, selecting favorable seeds, changing M_FF, or adding adaptive thresholds.
- Preserve raw outputs and provenance; derived analysis must not rewrite historical CALN0/VD1 source artifacts.
- Do not reopen LATQ aperture, periodic blind-window, physical Level-0, ARCH1, DVFS, temperature, or P&R work in MARG0.
- Keep the macro direction centered on the paper's core: low-area spatial voltage sensing plus per-chip startup-calibrated digital decision making, with measured end-to-end detection performance rather than interface implementation details.
