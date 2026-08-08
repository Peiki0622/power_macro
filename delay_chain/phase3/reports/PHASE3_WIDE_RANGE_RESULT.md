# Phase 3 Wide-Range Sparse Vernier Result

## Decision

The selected topology is the 16-active-stage sparse companion with mask
`0x55555555`: even-numbered stages are LVT->RVT and odd-numbered stages are
RVT->RVT.  It uses `CAL_SEL=0` and baseline code 0.  The final physical
real-DFF characterization contains 83 points from 1.10 V to 0.70 V, including
the two prior timing anchors.

## Physical Result

All 83 points have valid thermometer words, zero reset failures, and both
final chain taps arrive before the configured 8 ns read time.  No saturation
or multi-code reversal occurs before 0.70 V; the maximum final-tap arrival is
3.664659 ns at 0.70 V.

The retained 16-stage screen and final curve both report code 0 at every
measured voltage.  Thus the topology meets the range, validity, settling, and
hardware-cost gates, but does **not** meet the preferred positive small-droop
residual criterion.  This limitation is retained as measured evidence rather
than being hidden by interpolation, a fitted delay model, or an unplanned
hardware change.

The zero-hardware baseline using the same low-code `CAL_SEL=0` first produced
an invalid thermometer word at 0.93 V, while final taps still arrived before
8 ns; sparse stages were therefore required for word validity.  The selected
curve codes are 0 at 1.10, 1.05, 1.00, 0.90, 0.80, and 0.70 V.  No saturation
or invalid voltage appears in the selected final curve.

## Hardware Count

The chain has 128 functional inverter instances: 112 RVT and 16 LVT.  It
retains 32 DFF comparators, seven BUF instances, and 16 MXT2 instances in the
unchanged launch network.  Compared with the prior 160-inverter chain
(64 RVT plus 96 LVT including dummy loads), the selected chain removes all
32 dummy loads and does not add hardware.

## Evidence

- Final compact curve: `../runs/wide_range_final/voltage_code.csv`
- Final gate summary: `../runs/wide_range_final/voltage_summary.json`
- Baseline and screening products remain task-scoped ignored run data.
