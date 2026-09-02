# BFE13 TRACK0 P0 Authority and Reuse Matrix

Gate: `BFE13_TRACK0_P0_AUTHORITIES_FROZEN`

## Reused without physical rerun

- BFE5 ARCH1 dual-reference architecture and the retained reference-interaction audit.
- BFE12 SIGN0 RTL, gate, retained replay manifest, and signed-error conclusions.
- ARCH0 controller/top, capture bank, weighted `M_FF` feature pipeline, and TIM0 E0/E4/E7/E8 timing contract.
- Existing BFE8/BFE9/BFE11 retained rows through the frozen BFE12 replay pack.

## New candidate scope

- Add only `bfe_backend_ctrl_arch1_track0.sv` and `bfe_backend_arch1_track0_top.sv`.
- Add task-local documentation, static audit, and two authorized logical VCS regressions.

## Explicitly excluded

- HSPICE, PrimeSim, LATQ/DFF regeneration, waveform regeneration, DC, STA, P&R, PVT, and D01/D02/D04 physical reruns.
- ARCH0/BFE12 source edits, frontend changes, threshold sweeps, production threshold selection, FALL signed logic, OPP/rebase, or ADAPT0 behavior.
