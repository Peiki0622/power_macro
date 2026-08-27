# B-FE5-TIM0 Pipeline Contract

Baseline: `2b6f2e17aaa2ee3af3510ac422b7d31a55240e66` on
`bfe-multitap-latched-frontend`.  TIM0 is a narrow verification/freeze stage;
it adds no feature, does not modify ARCH0 arithmetic, does not implement ARCH1,
and does not add FIFO, ready/valid, event-ID, debug ports, or pipeline stages.
The existing 30 x `LATQ` -> 30 x `DFF` capture bank is unchanged.

## Event Alignment

The RTL extraction is:

| Event | Existing implementation boundary | Fixed interpretation |
|---|---|---|
| E0 | `bfe_capture_bank.q_ff` | Capture DFF samples the stable LATQ output |
| E1 | `bfe_m_feature.pair_q` | Fifteen pair sums register |
| E2 | `bfe_m_feature.level_two_q` | Eight level-two reductions register |
| E3 | `bfe_m_feature.m_ff_o` | Nine-bit M_FF registers |
| E4 | `bfe_backend_ctrl.event_pending_q` qualifier | `event_valid` is the consume strobe paired with stable M_FF; `edge_pol` is sampled for that same logical event |
| E7 | `bfe_backend_ctrl.delta_valid_q` / `droop_alarm_o` | Registered detector result becomes the current alarm pulse |
| E8 | `droop_alarm_sticky_o` | Sticky state observes the preceding alarm pulse |

The TIM0 bench drives one new capture every probe-clock cycle.  It presents the
corresponding `event_valid`, `edge_pol`, and margin four edges later, at E4.
The bench checks `event_m_q`, `event_ref_q`, and `event_margin_q` against the
same source event while four detector events overlap.  It also checks that
eight calibration samples (four RISE followed by four FALL) are consumed once,
produce references 25 and 65, and reach lock without polarity mixing.

The approved fix adds only `alarm_margin_q` at the existing P4b register
boundary.  It holds the pre-edge P4a margin alongside `delta_q`; it is a
companion context register, not a new arithmetic stage or a new externally
visible protocol phase.  The 30-LATQ/30-DFF capture bank, E0--E4 latency, and
one-event-per-clock throughput are unchanged.

## Throughput Result

The continuous A/B/C/D sequence alternates RISE/FALL and uses independent
margins.  The expected outcomes are A alarm, B quiet equality, C alarm, and D
alarm.  After the P4b companion-context fix, all four outcomes match, including
the former failing case A (`delta=5`, margin `4`).  The bench also confirms
eight calibration samples are consumed exactly once, references are 25 and 65,
and lock is reached without polarity mixing.  The accepted fixed latencies are
four edges from E0 capture to E4 consume and seven edges from E0 capture to the
registered alarm pulse.

## Timing Audit

`run_tim0_timing_audit.tcl` reads the fixed
`backend/netlist/timing_opt/bfe_backend_timing_opt_mapped.ddc` and performs no
compile or RTL transformation.  It records reports for 2.40, 2.45, 2.50,
2.60, and 2.75 ns clock periods.  Each report preserves Synopsys startpoint,
endpoint, arrival, required time, slack, and point-by-point logic depth for
the q_ff->P1, P1->P2, P2->M_FF, event/context->operand, operand->P4a,
P4a->P4b, and P4b->alarm/sticky classes.  It also audits the selected
Liberty DFF/LATQ minimum high/low pulse widths, minimum period,
recovery/removal attributes.  A missing path or library attribute is reported
as an audit gap; TIM0 never manufactures a passing number.

The audit completed with no missing requested path classes and emitted
`BFE5_TIM0_TIMING_MARGIN_CHARACTERIZED`.  At 2.40 ns the P2->M_FF path has
slack `-0.0476298 ns`; at 2.45 ns it has `+0.00237012 ns`; at 2.50, 2.60,
and 2.75 ns it has `+0.0523701`, `+0.15237`, and `+0.30237 ns`.  The other
six audited classes remain positive at every sweep point.  Thus the result is
timing-margin characterization, not a claim that the 2.40 ns point closes.
The characterization is at the single mapped
`ss_typical_max_0p99v_125c` Liberty corner.  It is not physical signoff,
extraction, multi-corner closure, or silicon validation.

## TIM0 Result

- `BFE5_TIM0_EVENT_ALIGNMENT_PASS`
- `BFE5_TIM0_PIPELINE_THROUGHPUT_PASS`
- `BFE5_TIM0_TIMING_MARGIN_CHARACTERIZED`
