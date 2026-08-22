# Re-Frequency Status

## RF10 decision

`Re-Frequency Closure Handoff = GO`

The active FTC controller timing baseline is the 400 MHz / 2.5 ns re-frequency
handoff.  This RF10 publication is evidence-only: it does not modify the
controller RTL, the frozen transistor sensor, the calibration algorithm, or
historical 1 GHz artifacts.

## Active and retained evidence

| Evidence | Published status |
|---|---|
| Historical 1 GHz Phase 1 handoff | Retained historical evidence; superseded for active RTL timing consumption |
| Historical 1 GHz Phase 7 synthesis | Retained historical implementation evidence |
| Historical 1 GHz C3 timing-composed failure | Retained root-cause evidence |
| Re-frequency timing handoff | ACTIVE |
| Re-frequency synthesis/SDF | ACTIVE |
| Three-voltage SDF + XA + transistor closure | GO |

## Active timing contract

- `cal_clk`: 400 MHz (`Tcal = 2.5 ns`), selected from the guarded static limit.
- Configuration settle: 1 cycle.
- Local probe actions: reset release 0, S_CLK rise 1, Q samples 2/3,
  reset assert 4, S_CLK fall 5, recovery done 7.

The existing Phase 10 freeze path may now resume from this active baseline;
Phase 10 work itself is governed by its separate final-closure plan.
