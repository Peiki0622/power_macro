# C3 Timing-Composed Closure Stop

## Disposition

`timing_composed_0p80` was the only authorized new transient.  The first
failure is preserved under `timing_composition/runs/timing_composed_0p80/` and
is classified as a real mapped-controller/SDF timing-check failure, not as an
evidence-reconstruction or bridge-probe rerun.

## Observed evidence

- Phase 7 SDF annotation completed with `Total errors: 0`.
- The 1 ns external clock and corrected XA bridge were active; no
  `+nospecify` or `+notimingcheck` bypass was used.
- The first meaningful unknown controller state appeared at approximately
  `10.068 ns` during delayed sensor-reset transition.
- Standard-cell `$width` timing violations then occurred throughout the
  1 GHz run.
- The autonomous bench terminated at `24.5 ns` with
  `R6_FAIL cause=final_code M=x F=x expected=M7/F6`.
- The expected `45/17/28` operation/config/probe trajectory was not reached.

## Failure rule applied

Per the final-closure plan, C4 was not started, no 1.10 V timing-composed run
was attempted, and no RTL, sensor architecture, SDF, clock contract, or
calibration algorithm was changed.  The compact machine-readable record is
`timing_composed_0p80_failure.json`.

This result does not invalidate the independent corrected Phase 9 no-SDF GO;
it leaves the final SDF + transistor-sensor composition gate and Phase 10
freeze unresolved.
