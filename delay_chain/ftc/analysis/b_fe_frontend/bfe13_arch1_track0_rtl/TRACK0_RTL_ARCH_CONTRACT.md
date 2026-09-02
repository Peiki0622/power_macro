# BFE13 ARCH1 TRACK0 RTL Architecture Contract

Gate: `BFE13_TRACK0_P1_RTL_ARCH_FROZEN`

This document freezes the smallest synthesizable dual-reference tracker
required by BFE13.  It is a candidate fork only.  The ARCH0 controller/top,
the BFE12 SIGN0 controller/top, the 30-lane capture bank, and the weighted
`M_FF` feature pipeline remain unchanged authorities.

## 1. Module boundary and compile-time configuration

The candidate top is `bfe_backend_arch1_track0_top`; its external interface is
byte-for-byte the BFE12 SIGN0 interface:

| Port | Direction/width | Contract |
|---|---|---|
| `safe_d` | input `[29:0]` | Unchanged Level-0-restored capture word. |
| `latch_gate` | input | Shared LATQ transparency control. |
| `clk_probe` | input | Shared capture, feature, and backend clock. |
| `reset` | input | Active-high asynchronous reset. |
| `event_valid` | input | E4 consume strobe for a stable `M_FF`. |
| `edge_pol` | input | `0` selects RISE; `1` selects FALL. |
| `cal_mode` | input | Qualifies the four-sample startup calibration epochs. |
| `m_margin_rise` | input `[8:0]` | Existing strict RISE absolute margin. |
| `m_margin_fall` | input `[8:0]` | Existing strict FALL absolute margin. |
| `t_pos_rise` | input `[8:0]` | Existing BFE12 signed-RISE threshold input. |
| `cal_lock` | output | High after four accepted samples of each polarity. |
| `droop_alarm` | output | Registered E7 ABS-or-signed-RISE alarm pulse. |
| `droop_alarm_sticky` | output | E8 sticky alarm state, reset-only clear. |

No tracking, debug, OPP, rebase, or status port is allowed.  The only
TRACK0-specific configuration is compile/elaboration-time parameters on the
top and controller, all defaulting to zero:

```text
T_TRACK_RISE = 0
T_TRACK_FALL = 0
B_TRACK_RISE = 0
B_TRACK_FALL = 0
```

Zero defaults disable all autonomous reference movement and are the required
SIGN0-equivalence configuration.  Nonzero overrides are local directed-test
values and are not production selections.

## 2. Reference state and calibration

The controller stores four independent nine-bit registers:

```text
m_ref_startup_rise_q, m_ref_startup_fall_q
m_ref_track_rise_q,   m_ref_track_fall_q
```

For each polarity, the fourth accepted calibration sample writes
`(sum_previous_three + current_M_FF) >> 2` to both its startup and track
register.  Startup registers have no write path after that calibration
completion event except asynchronous reset.  TRACK0 aliases the security
anchor to the startup register; no third physical anchor register is added.

At the same calibration completion, precompute 10-bit saturated bounds:

```text
track_upper = min(435, startup_ref + B_TRACK)
track_lower = max(0,   startup_ref - B_TRACK)
```

The bounds are registered per polarity and are the only runtime drift limit.

## 3. Event pipeline and arithmetic lanes

The existing TIM0 event timing is preserved:

```text
E4: capture M_FF, selected M_REF_TRACK, startup anchor, polarity,
    absolute margin, T_POS_RISE, and the track-reference snapshot.
E5: tracking lane performs the existing high/low split P4a subtraction;
    security lane registers a 10-bit startup-anchor-plus-threshold trip point.
E6: tracking lane completes P4b sign and absolute magnitude; security lane
    compares the event M_FF to its registered trip point.
E7: ABS_ALARM = valid && (D_track > margin);
    SIGNED_RISE_ALARM = valid && RISE && signed-trip-hit;
    DROOP_ALARM = ABS_ALARM || SIGNED_RISE_ALARM.
E8: sticky state observes the E7 pulse; tracker FSM/commit logic runs here.
```

The tracking lane uses `e_track = M_FF - M_REF_TRACK_selected` and
`D_track = abs(e_track)` with the existing split sign+magnitude structure;
no monolithic second wide signed subtractor is permitted.

The security lane implements the algebraically equivalent RISE rule with a
10-bit trip point:

```text
zero_extend(M_FF) > zero_extend(m_ref_startup_rise_q)
                         + zero_extend(t_pos_rise)
```

The strict comparator and `M_FF <= 435` naturally make `t_pos_rise=435`
disabled.  No FALL signed comparator is implemented.  Tracker state or
commit signals must not feed the E7 alarm compare/OR cone.

## 4. E8 event-atomic commit and stale guard

No reference update occurs at E4, E5, E6, or E7.  At E8, priority is fixed:

1. If the current E7 `droop_alarm` is high, update neither reference and
   clear both polarity FSMs to `IDLE`.
2. Else if `droop_alarm_sticky` was already high, freeze both references and
   states until reset.
3. Else if the event's captured selected track reference differs from the
   current selected `M_REF_TRACK`, reject the event and clear only that
   polarity FSM.
4. Otherwise evaluate the selected polarity FSM and, if committing, change
   its track reference by exactly one LSB subject to its registered bound.

The captured reference snapshot is carried through the same alignment stages
as `M_FF`, sign, polarity, and margin.  There is no E8-to-E4 combinational
bypass.  An event captured before an E8 update is allowed to become stale and
must be discarded rather than counted as persistence evidence.

## 5. Minimal temporal state

Each polarity has exactly one independent two-bit register:

```text
2'b00 IDLE
2'b01 WAIT_POS
2'b10 WAIT_NEG
2'b11 RESERVED; recover as IDLE
```

For a non-alarming, non-stale event after all guards:

- `D_track == 0` clears the selected state.
- `0 < D_track <= T_TRACK` and positive sign: `IDLE→WAIT_POS`; a second
  positive observation commits `+1` when below `track_upper`, then returns IDLE;
  `WAIT_NEG` changes to `WAIT_POS` without update.
- `0 < D_track <= T_TRACK` and negative sign: symmetric `WAIT_NEG` behavior,
  with `-1` permitted only above `track_lower`.
- `D_track > T_TRACK` clears the selected state without updating.

An opposite-polarity event never changes the other polarity state.  The E8
update cone contains only state decode, equality/bound comparisons, and a
nine-bit `+1/-1`; it contains no runtime absolute-difference calculation.

## 6. Structural prohibitions and observability names

The implementation must have zero new external ports, zero added alarm
stages, zero alarm-cone tracker logic, zero bypass muxes, zero ordinary writes
to startup references, exactly two FSM bits per polarity, and a maximum
one-LSB accepted update.

For hierarchical directed assertions, retain readable internal names at
minimum: `m_ref_startup_rise_q/fall_q`, `m_ref_track_rise_q/fall_q`,
`track_lower_*`, `track_upper_*`, `track_state_rise_q/fall_q`, `abs_alarm`,
`signed_rise_alarm`, and captured/aligned track-reference snapshot registers.

## 7. P1 verification boundary

P1 performs documentation and consistency review only.  It does not edit RTL
and does not invoke a simulator.  The next permitted mutation is the two-file
candidate RTL addition in P2.
