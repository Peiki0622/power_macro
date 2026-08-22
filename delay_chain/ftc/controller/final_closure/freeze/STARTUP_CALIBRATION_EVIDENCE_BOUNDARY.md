# Startup Calibration Cross-Layer Evidence Boundary

## Final Phase 10 interpretation

The startup-calibration subsystem is frozen on the active 400 MHz / 2.5 ns re-frequency baseline. No HSPICE, VCS, XA, synthesis, or STA run was performed for Phase 10. Phase 10 reuses the already accepted RF0-RF10 evidence, publishes the power-domain boundary, and freezes the upstream subsystem for later detection work.

## Active implementation

- Active calibration clock: 400 MHz (`Tcal = 2.5 ns`).
- Active timing handoff: `refrequency/handoff/phase1_timing_handoff_refrequency.json`.
- Active local probe schedule: reset release 0, S_CLK rise 1, Q samples 2/3, reset assert 4, S_CLK fall 5, recovery done 7.
- Configuration settling: 1 full calibration-clock cycle.
- Active mapped implementation: `refrequency/synthesis/netlist/`.
- Final timing-composed evidence: `refrequency/verification/mixed_signal_sdf/RF9D_TIMING_COMPOSED_MIXED_SIGNAL.json`.

Historical 1 GHz Phase 1/Phase 7/C3 evidence remains retained for traceability and root-cause documentation, but it is not the active implementation baseline.

## Power-domain boundary

### PD_SENSE — monitored analog/transistor domain

`PD_SENSE` is the complete frozen `FTC_SENSOR` under `VDD_MONITORED`. It includes:

- voltage-sensitive delay paths;
- medium path-selection network;
- fine driver/load network;
- XOR timing-comparison network;
- sensor capture DFF.

The boundary is intentionally placed **after** the sensor capture DFF. `Q_FINAL` is therefore a held sensor state rather than an XOR pulse or a pair of raw timing-critical edges.

### PD_CTRL — stable/trusted digital domain

`PD_CTRL` contains:

- M/F thermometer state registers;
- operation sequencer;
- Q double sampler and classifier;
- startup-calibration FSM;
- future calibration-to-detection ownership logic;
- future programmable-margin logic;
- future detection FSM and alarm/status logic.

The current VCS digital model does not electrically model the PD_CTRL supply; it represents a timing-valid stable/trusted digital domain.

### Crossings

Current verification uses 28 PD_CTRL-to-PD_SENSE XA D2A crossings (`sense_s_clk`, `sense_dff_reset`, 16 medium thermometer rails, 10 fine thermometer rails) and one PD_SENSE-to-PD_CTRL A2D crossing (`Q_FINAL`). These are verification abstractions. They are **not** proof that physical level shifters or return receivers have been implemented or signed off. That work is reserved for the subsequent PD1 stage.

## Evidence layers

| Layer | Active/retained evidence | What it proves | What it does not prove |
|---|---|---|---|
| Historical transistor timing | corrected Phase 1 exact-path HSPICE | Original sensor physical event-order basis and nominal trajectories | Active 400 MHz mapped-controller implementation |
| RF6 transistor protocol | `refrequency/hspice/summary.json` and accepted scenario evidence | The frozen transistor sensor works with the common 400 MHz re-quantized protocol at 0.80/0.95/1.10 V; one common timing template | Synthesized autonomous control |
| RTL/protocol | Phase 2-6 evidence plus RF9A | Calibration algorithm, state sequencing, configuration rules and nominal trajectories | Transistor behavior or mapped timing |
| RF8 synthesis/STA | `refrequency/synthesis/phase_refrequency_synthesis_results.json` | Active 400 MHz mapped implementation with positive setup, hold, pulse-width and sensor-control timing margins | Analog sensor behavior |
| RF9B digital SDF | active mapped controller + new SDF + behavioral sensor | Full standard-cell timing checks at the active calibration frequency without timing-check bypass | Transistor sensor interaction |
| RF9C mixed signal no-SDF | mapped controller + corrected XA bridge + frozen transistor sensor | Three-voltage autonomous mixed-signal function under the active timing contract | Controller SDF delay composition |
| RF9D timing-composed mixed signal | mapped controller + active SDF + full timing checks + corrected XA bridge + frozen transistor sensor + real `q_final` feedback | Final three-voltage startup-calibration composition: exact counts/codes, one active sensor clock edge per probe, safe reset/S_CLK ordering, no causal timing violations/notifier corruption | Full-transistor implementation of every controller standard cell; post-layout parasitics; physical level shifter signoff; PD_CTRL power-integrity behavior |

## Frozen nominal results

| VDD_MONITORED | Operations | Configurations | Probes | Final code |
|---:|---:|---:|---:|---|
| 0.80 V | 45 | 17 | 28 | M7/F6 |
| 0.95 V | 36 | 14 | 22 | M4/F6 |
| 1.10 V | 36 | 15 | 21 | M2/F9 |

## Historical 1 GHz C3 disposition

The preserved 1 GHz timing-composed failure is not deleted or rewritten. Its root cause was traced during re-frequency work to the standard-cell conditional CK high/low width requirement. The active calibration implementation therefore moved to the evidence-derived guarded 2.5 ns period. The old 1 GHz C2-C4 final-closure path is superseded and must not be rerun as an active Phase 10 requirement.

## Freeze boundary for later work

The following may not change without a dedicated architecture-change or root-cause plan:

- frozen FTC_SENSOR topology and cell choices;
- XOR and sensor capture DFF membership in PD_SENSE;
- N=16/K=10 direct registered thermometer architecture;
- calibration algorithm semantics: paired coarse probes, exact two-step backoff, fine-boundary rule, +1 guard and independent hold;
- Q double sampling;
- active 400 MHz startup-calibration timing handoff and 0/1/2/3/4/5/7 probe schedule;
- nominal locked codes M7/F6, M4/F6 and M2/F9.

The next allowed work is downstream: PD1 physical domain-crossing architecture, H0 calibration-to-detection handoff, then detection-margin and detection-mode development that consumes this frozen upstream baseline.
