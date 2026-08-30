# BFE8 D02 R0 polarity-aware diagnostic reparse

Gate: `BFE8_D02_R0_POLARITY_AWARE_PRE_ATTACK_REPARSE_PASS`

Bug: P6 pre-attack diagnostics used `M_REF_RISE` and `M_MARGIN_RISE_P0` for every event, including FALL events.
Fix: each event selects `M_REF_RISE`/`M_MARGIN_RISE_P0` for RISE or `M_REF_FALL`/`M_MARGIN_FALL_P0` for FALL before computing `D_M` and the strict alarm comparison.

Reuse evidence: all 30 existing D02_CASE.json records, healthy per-seed references, frozen margins, and captured vectors were read in place. No source deck, waveform, RTL, calibration, or population artifact was regenerated.
Simulation accounting for R0: HSPICE=0, VCS=0, PrimeSim=0, DC=0.

Corrected result: 30/30 seeds have `pre_attack_alarm_count=0`; the per-event polarity, selected reference, selected margin, `D_M`, and alarm vector are recorded in `BFE8_D02_PER_SEED.csv`.
Formal metrics verified unchanged: Detection Coverage=30/30; Decision Headroom=min 19 / median 38 M-codes; First-Alarm Latency=20.534524618567 ns; Healthy FPR=1/240.
