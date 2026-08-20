# FTC Phase 1 Event-Order Timing Quantization Correction v2

## Final Decision

**Corrected Phase 1 Timing Handoff = GO**

The six required gates completed in order.  The rejected v1 directory and its
NO-GO evidence were preserved and were not used as v2 timing inputs.

## Gate Evidence

| Gate | Result | Evidence |
|---|---|---|
| Exact-path event extraction | GO | `controller/analysis/cycle_protocol_event_order_v2/exact_path_event_order_audit.json` |
| Ordered cycle construction | GO | `controller/analysis/cycle_protocol_event_order_v2/cycle_timing_contract_v2.json` |
| Zero-HSPICE contract tests | GO | `tests/test_cycle_protocol_event_order_v2.py`, 6 tests passed |
| HSPICE deck freeze | GO | `controller/analysis/cycle_protocol_event_order_v2/hspice/pre_run_freeze.json` |
| Three-scenario HSPICE protocol | GO | `controller/analysis/cycle_protocol_event_order_v2/hspice/summary.json` |
| Timing handoff | GO | `controller/spec/phase1_timing_handoff.json` |

## Corrected Timing

The accepted exact-path schedules contain 71 probes across 0.80 V, 0.95 V, and
1.10 V.  All use the same strict event order.  The earliest 1 GHz local probe
template is:

```text
RESET_RELEASE_COMPLETE = 0
S_CLK_RISE             = 1
Q_SAMPLE_1             = 4
Q_SAMPLE_2             = 5
RESET_ASSERT           = 6
S_CLK_FALL             = 7
RECOVERY_DONE          = 10
```

The derived S_CLK high interval is 6 cycles.  Configuration updates use a
2-cycle settle interval and remain separate from probe activity.

## HSPICE Results

All three pre-frozen scenarios completed once with HSPICE W-2024.09:

| Voltage | Probes | Config updates | Final code | Result |
|---:|---:|---:|---|---|
| 0.80 V | 28/28 pass | 17/17 pass | M7/F6 | GO |
| 0.95 V | 22/22 pass | 14/14 pass | M4/F6 | GO |
| 1.10 V | 21/21 pass | 15/15 pass | M2/F9 | GO |

No RTL was changed or started in this correction phase.  Later RTL timing
constants must consume or validate against `phase1_timing_handoff.json`; the
historical v1 `cycle_timing_contract.json` is superseded and must not be used.
