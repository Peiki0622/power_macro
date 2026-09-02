# BFE14 P0 Authority and Reuse Matrix

Gate: `BFE14_TEMP0_P0_AUTHORITIES_AND_ARCH1_STATUS_FROZEN`

## Reused without new physical simulation

- BFE8 healthy 1.10 V process population, BFE7-style healthy stimulus, event schedule, and retained 25 C captures.
- BFE8 source-referenced Level-0 threshold, real LATQ/DFF capture, q_ff-to-M_FF extraction, and BFE4 MC signature mapping.
- BFE8 startup calibration and locked margins `M_MARGIN_RISE=22`, `M_MARGIN_FALL=24`.
- BFE12 replay manifest/calibration authority and BFE13 TRACK0 RTL gate.
- TT nominal temperature coordinates `-40/25/85/125 C` from the real-XOR temperature screen.

## New BFE14 scope

- Healthy temperature-only source/capture cases at nominal 1.10 V.
- Offline dual-reference audit and one controller-level TRACK0 replay.
- Task-local evidence under this directory and task-scoped raw runs only.

## Explicitly unchanged or excluded

- ARCH0, BFE12 SIGN0, and BFE13 TRACK0 RTL; frontend topology; 30 taps; LATQ/DFF semantics; `M_FF`; startup arithmetic.
- No droop waveform, D01/D02/D04 rerun, VDD/process/aging sweep, OPP/rebase, FALL signed comparator, threshold/parameter tuning, or signoff campaign.

## ARCH1 status after synchronization

BFE13 supplies a frozen minimal TRACK0 research candidate and validates digital/event-atomic mechanics only. Real benign-drift efficacy, poisoning robustness, trusted OPP/rebase, production parameters, PVT/silicon signoff, and complete ARCH1 promotion remain deferred. ARCH0 remains the authoritative production contract.
