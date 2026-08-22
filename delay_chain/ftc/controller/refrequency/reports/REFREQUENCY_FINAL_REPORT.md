# FTC SMIC40LL Re-Frequency Final Report

## RF10 conclusion

`Re-Frequency Closure Handoff = GO`

The prior 1 GHz timing-composed implementation is retained as root-cause
evidence.  The active implementation uses the reviewed 400 MHz / 2.5 ns
calibration clock and closes the complete mapped-controller, SDF, XA, and
frozen-transistor-sensor composition at 0.80 V, 0.95 V, and 1.10 V.

## 1 GHz root cause and library capability

The earliest causal 1 GHz failure was `DFFSRPQ_X1M_A9TR40` at `u_controller.\u_fsm/fail_reason_q_reg[2]`: a conditional
`CK_LOW_WIDTH` check required 1000 ps and observed 500 ps.  Its
notifier propagated controller X state in the preserved C3 evidence.  The
inventory contains 4335 width violations (2044 low-width and 2291
high-width); it establishes a frequency-dependent clock-pulse limitation, not
a hold-only issue.

The audited SMIC40LL sequential-cell timing model uses a 1.0 ns minimum CK
high/low width, 1.0 ns setup and recovery, and 0.5 ns hold and removal.  RF2
also recorded the conditional Verilog specify checks separately from Liberty
semantics.  RF8 confirmed all cells in the new mapping are inside the audited
RF2 cell set.

## Selected clock and cycle schedule

The static hard period is 2.00 ns, limited by 1.0 ns high/low CK width
at 50% duty cycle.  The explicit policy `max(1.25 * T_hard, T_hard + 0.25 ns)`
gives 2.50 ns; upward rounding on the 0.5 ns grid selects 2.50
ns (400 MHz).  The resulting half-cycle width is 1.25 ns, with
0.25 ns width margin.

The schedule is the earliest event-order-preserving integer solution, not a
scaled copy of the 1 GHz cycle table: reset release 0, S_CLK rise 1, Q sample
1 at 2, Q sample 2 at 3, reset assertion 4, S_CLK fall 5, recovery done 7;
configuration settling is re-derived to 1 cycle.

## Three-voltage validation chain

| Voltage | Operations | Configurations | Probes | Final code |
|---|---:|---:|---:|---|
| 0.80 V | 45 | 17 | 28 | M7/F6 |
| 0.95 V | 36 | 14 | 22 | M4/F6 |
| 1.10 V | 36 | 15 | 21 | M2/F9 |

- RF6: all three frozen transistor-sensor scenarios passed with one common
  timing template; the accepted HSPICE measurements prove physical CK and
  reset-before-S_CLK-return integrity.
- RF8: synthesis/STA passed with positive margins: setup 0.27 ns,
  hold 0.18 ns, q_final 1.50 ns, sense_s_clk 1.76 ns,
  sense_dff_reset 1.77 ns, thermometer 1.86 ns, and pulse width
  0.25 ns.
- RF9A: RTL plus behavioral sensor passed all three nominal trajectories.
- RF9B: mapped controller plus SDF plus behavioral sensor passed with full
  timing checks; no `+nospecify` or `+notimingcheck` bypass was used.
- RF9C: mapped controller plus corrected XA bridge plus frozen transistor
  sensor passed at all three voltages before SDF composition.
- RF9D: full SDF + XA + frozen transistor-sensor closure passed at all three
  voltages with zero causal timing violations, no notifier-driven X, exact
  operation/configuration/probe counts, one active sensor clock edge per
  probe, correct Q sample pairs, safe reset/S_CLK ordering, correct final
  codes, and stable locked M/F codes.

## Architecture and algorithm freeze

The sensor architecture and calibration algorithm are unchanged.  RF7 changed
only timing quantization and configuration settle duration; RF9C and RF9D both
record `sensor_or_algorithm_modified = false`.  No per-voltage calibration
clock or local timing template was used.

## Supersession and next handoff

Historical 1 GHz Phase 1/Phase 7/C3 evidence remains retained and reviewable.
The RF7 handoff marks the historical Phase 1 source superseded for active RTL
timing consumption, while the re-frequency handoff and synthesis/SDF are
ACTIVE.  With RF10 now GO, the existing Phase 10 final-freeze plan is authorized
to resume from this baseline.
