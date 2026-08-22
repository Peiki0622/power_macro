# FTC Autonomous Startup Calibration Final Acceptance

## Decision

`Startup Calibration Subsystem Freeze = GO`

The active startup-calibration implementation is the completed 400 MHz / 2.5 ns re-frequency baseline. Phase 10 performs no new simulation, synthesis, or STA. It reconciles the active evidence, freezes the power-domain boundary, records the exact upstream implementation artifacts, and closes the startup-calibration phase.

## Final gate state

| Phase | Status | Final basis |
|---|---|---|
| 0 | GO | Frozen functional contract and golden trajectories |
| 1 | GO | Corrected transistor timing evidence retained; active timing superseded by RF7 handoff |
| 2 | GO | Unit verification retained |
| 3 | GO | Sequencer verification retained |
| 4 | GO | FSM nominal/failure verification retained |
| 5 | GO | Integrated nominal verification retained |
| 6 | GO | RTL protocol-safety evidence retained |
| 7 | GO | Historical 1 GHz synthesis retained; RF8 is active synthesis/STA baseline |
| 8 | GO | Historical GLS retained; RF9B supplies active 400 MHz full-timing SDF digital closure |
| 9 | GO | RF9C/RF9D supply active three-voltage autonomous mixed-signal closure |
| 10 | GO | Active baseline reconciled, power-domain boundary frozen, evidence boundary and frozen-file manifest published |

Published conclusions:

- `Synthesizable Startup Calibration Controller = GO`
- `Real Circuit Autonomous Startup Calibration = GO_WITH_EVIDENCE_BOUNDARY`
- `Startup Calibration Subsystem Freeze = GO`

## Active timing baseline

- `cal_clk = 400 MHz`
- `Tcal = 2.5 ns`
- configuration settle = 1 cycle
- reset release = 0
- S_CLK rise = 1
- Q sample 1 = 2
- Q sample 2 = 3
- reset assert = 4
- S_CLK fall = 5
- recovery done = 7

This schedule is the RF7 event-order-preserving re-quantization and is not a scaled copy of the historical 1 GHz table.

## Active implementation and closure evidence

The accepted RF8 mapped controller closes with positive engineering margins at 400 MHz. RF9D then combines the mapped controller, active SDF, full standard-cell timing checks, corrected XA bridge, frozen transistor sensor and real `q_final` feedback. All three nominal supplies pass with exact expected operation/configuration/probe counts and final codes:

- 0.80 V: 45 / 17 / 28, M7/F6
- 0.95 V: 36 / 14 / 22, M4/F6
- 1.10 V: 36 / 15 / 21, M2/F9

The accepted RF9D evidence records no timing-check bypass, no causal timing violations/notifier corruption, one active sensor S_CLK edge per probe, correct Q sample pairs, safe reset/S_CLK ordering and stable locked M/F values.

## Final power-domain contract

### PD_SENSE

`PD_SENSE` is powered by `VDD_MONITORED` and contains the complete frozen transistor sensor:

- voltage-sensitive delay/tuning network;
- medium path-selection network;
- fine driver/load network;
- XOR timing-comparison network;
- sensor capture DFF.

The sensor capture DFF remains part of the transducer. `Q_FINAL` is the power-domain boundary state returned to PD_CTRL.

### PD_CTRL

`PD_CTRL` is an independent stable/trusted digital supply domain containing the startup-calibration controller, M/F state, Q double sampler/classifier and all future detection/margin/alarm logic.

The current VCS representation abstracts the PD_CTRL electrical supply. The existing XA D2A/A2D crossings are mixed-signal verification interfaces, not signed-off physical level shifters.

## No-rerun policy followed

Phase 10 did not rerun:

- corrected Phase 1 HSPICE;
- Phase 2-6 RTL/protocol simulations;
- historical Phase 7/8 flows;
- corrected Phase 9 no-SDF mixed-signal runs;
- RF6 HSPICE;
- RF8 synthesis/STA;
- RF9A/B/C/D dynamic verification.

No historical simulation was regenerated merely to create cleaner evidence.

## Historical evidence disposition

The historical 1 GHz Phase 1 handoff and Phase 7 synthesis remain retained for traceability. The preserved 1 GHz timing-composed C3 failure remains root-cause evidence. Re-frequency work traced the causal failure to standard-cell clock-pulse-width capability and selected the guarded 2.5 ns operating period.

Therefore the old final-closure plan's active 1 GHz C2-C4 path is superseded by RF0-RF10 and is not executed again.

## Evidence boundary

The final acceptance proves a gate-timed mapped digital controller operating in closed loop with the transistor-level frozen sensor through the corrected mixed-signal boundary. It does **not** claim:

- full-transistor SPICE implementation of every controller standard cell;
- physical UPF/CPF or power-grid signoff;
- implemented/signed-off physical level shifters;
- post-layout parasitic closure;
- PVT/Monte Carlo detection characterization;
- deep-droop operating-region characterization of the PD_SENSE capture DFF.

Those are downstream tasks and do not invalidate the startup-calibration freeze.

## Frozen upstream semantics

The following are frozen and may not change without a dedicated architecture-change/root-cause plan:

- physical FTC_SENSOR topology and cell choices;
- XOR and capture DFF remain in PD_SENSE;
- N=16 / K=10 direct registered thermometer architecture;
- paired coarse probes;
- exact two-step backoff without an intervening probe;
- first non-high fine-boundary rule;
- +1 guard and independent hold;
- Q double sampling;
- active 400 MHz timing contract and event schedule;
- nominal locked codes M7/F6, M4/F6 and M2/F9.

## Handoff to next stage

Startup calibration is now a frozen upstream dependency. The next authorized work is:

1. `PD1` — physical domain-crossing contract and level-shifter/receiver architecture;
2. `H0` — calibration-to-detection atomic ownership handoff;
3. downstream programmable detection-margin and detection-mode design.

Those stages must consume this baseline rather than modify it silently.
