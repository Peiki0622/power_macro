# Phase 9 VCS-XA Result: NO-GO

## Decision

`Real Circuit Autonomous Startup Calibration = NO-GO`

The first required nominal scenario, `autonomous_0p80`, did not reach the
required autonomous lock of M7/F6.  The Phase 9 plan requires stopping at the
first real-circuit failure, so `autonomous_0p95` and `autonomous_1p10` were not
run.

## Environment

- VCS: `P-2019.06-SP2_Full64`
- PrimeSim XA: `S-2021.09-SP2`
- Clock: 10 ns
- Transient stop: 8 us
- Mixed-signal comparison errors: 0
- XA DC operating point: converged

## Observed Failure

The synthesized controller and the frozen transistor sensor ran through the
full 8 us transient, but the controller did not assert `cal_done` or
`lock_valid`.  The observed medium trajectory reached M10 and returned to M9;
the fine trajectory only reached F1.  The final sampled state was `0x0a`
(`ST_FINE_INC`), with final codes M9/F1 rather than the required M7/F6.

The machine-readable audit is in
`vcs_xa/reports/autonomous_0p80_audit.json`.  The complete event CSV, XA log,
VCS log, and selected XA FSDB remain under
`vcs_xa/runs/autonomous_0p80/`.

## Gate Assessment

The following required gates are not met: exact coarse trajectory, two-step
backoff, fine boundary/guard/hold, one S_CLK edge per accepted probe, lock
after hold, frozen final code, and final golden-code equality.

No controller RTL, synthesized netlist, sensor netlist, recovery guard, cell,
DFF, cycle count, backoff depth, fine guard, or sampling policy was changed
after the failure.  A new targeted root-cause plan is required before any
future rerun.
