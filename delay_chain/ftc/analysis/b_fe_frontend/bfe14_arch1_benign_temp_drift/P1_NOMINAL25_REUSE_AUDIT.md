# BFE14 P1 nominal 25 C reuse audit

Gate: `BFE14_TEMP0_P1_STIMULUS_AND_REUSE_FROZEN`

Classification: `NOMINAL25_REUSE_VALID`. The retained BFE8 cases cover all 30 seeds with 24 mapped events, 30 resolved q_ff taps, nominal 1.10 V source/safe rails, matching BFE4 MC signatures, exact four-plus-four calibration, and the same source-referenced Level-0 plus real LATQ/DFF capture method. The BFE8 healthy composite and event-map hashes are recorded in `P1_TEMP_STIMULUS_CONTRACT.json`; the new deck is permitted to differ only in simulator `.temp`. No 25 C rerun is authorized.

Simulation accounting: HSPICE=0, capture-support VCS=0.
