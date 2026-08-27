# B-FE5-ARCH0: Frozen macro architecture contract

Status: `FROZEN`

This stage freezes the architectural and interface contract for the voltage-droop sensing macro. It does not freeze final alarm margins, PVT signoff values, DVFS policy, physical level shifters, or backend RTL micro-architecture.

## 1. Frozen top-level architecture

```text
                         B-FE5-ARCH0 FROZEN ARCHITECTURE

+------------------------------- PD_SENSE --------------------------------+
|                                                                          |
|                              CLK_SYS_MON                                 |
|                                   |                                      |
|                     +-------------+-------------+                        |
|                     |                           |                        |
|              4-stage RVT prefix          0-stage LVT prefix             |
|                     |                           |                        |
|              30-stage RVT path           30-stage LVT path              |
|                     |                           |                        |
|              rvt[29:0] taps              lvt[29:0] taps                 |
|                     |                           |                        |
|                     +-----------+---------------+                        |
|                                 |                                        |
|                         30 x XOR2[i]                                    |
|                   XOR(rvt[i], lvt[i]), i=0..29                          |
|                                 |                                        |
|                           xor[29:0]                                      |
|                                 |                                        |
+---------------------------------+----------------------------------------+
                                  |
                                  v
                    +-----------------------------+
                    | Level-0 restoration         |
                    | behavioral / ideal boundary |
                    | bit_i = 1 iff               |
                    | V(xor_i) > 0.5*VDD_SENSE    |
                    +--------------+--------------+
                                   |
                            safe_d[29:0]
                                   |
+----------------------------------+----------------------------------------+
|                                PD_SAFE                                   |
|                                                                           |
|                         +----------------+                                |
|                         | 30 x real LATQ |                                |
|                         +-------+--------+                                |
|                                 |                                         |
|                         latq_q[29:0]                                      |
|                                 |                                         |
|                         +-------v--------+      CLK_PROBE                  |
|                         | 30 x real DFF  |<---------+                      |
|                         +-------+--------+                                |
|                                 |                                         |
|                           q_ff[29:0]                                      |
|                                 |                                         |
|                         +-------v--------+                                |
|                         | Feature backend |                               |
|                         | M=sum(i*q_ff[i])|                               |
|                         |   i = 0..29    |                                |
|                         +-------+--------+                                |
|                                 | M_FF[8:0]                              |
|                                 |                                         |
|        capture/control ---------+---- event_valid                         |
|                |                +---- edge_pol (RISE/FALL)               |
|                |                                                          |
|                v                                                          |
|      +-----------------------------+                                       |
|      | Calibration / detection     |                                       |
|      | backend                     |                                       |
|      |                             |                                       |
|      | CAL_MODE                    |                                       |
|      |   |                         |                                       |
|      |   +--RISE--> SUM_RISE ----->| M_REF_RISE[8:0]                      |
|      |   |                         |                                       |
|      |   +--FALL--> SUM_FALL ----->| M_REF_FALL[8:0]                      |
|      |                             |                                       |
|      |        4 samples / polarity |                                       |
|      |                |            |                                       |
|      |                v            |                                       |
|      |             CAL_LOCK        |                                       |
|      |                |            |                                       |
|      |                v            |                                       |
|      | selected M_REF by edge_pol  |                                       |
|      |                |            |                                       |
|      |       D_M = |M_FF-M_REF|    |                                       |
|      |                |            |                                       |
|      |        +-------v--------+   |                                       |
|      |        | programmable   |   |                                       |
|      |        | M_MARGIN       |   |                                       |
|      |        +-------+--------+   |                                       |
|      |                |            |                                       |
|      |      D_M > M_MARGIN ?       |                                       |
|      |          |          |       |                                       |
|      |         no         yes      |                                       |
|      |          |          +----------> DROOP_ALARM                        |
|      |          |                     -> DROOP_ALARM_STICKY                 |
|      +----------+------------------+                                       |
|                                                                           |
+---------------------------------------------------------------------------+
```

## 2. Frozen domain boundaries

- `PD_SENSE` contains the voltage-sensitive RVT/LVT delay paths and the 30 XOR observables.
- The current source-to-safe-domain boundary remains the behavioral Level-0 restoration interface. It is explicitly not a physical A2D or identified foundry level-shifter implementation.
- `PD_SAFE` contains the 30 real latches, 30 real DFFs, feature extraction, calibration state, comparison logic, and alarm state.
- The real DFF bank is the formal digital state boundary. Backend logic consumes `q_ff[29:0]`; LATQ internal analog motion is not a backend observable or an independent failure criterion.

## 3. Frozen frontend and capture contract

- Observable taps: 30.
- RVT prefix: 4 stages.
- LVT prefix: 0 stages.
- Per-tap observable: `xor[i] = XOR(rvt[i], lvt[i])`.
- Capture topology: `XOR -> Level-0 -> LATQ -> DFF`.
- `CLK_SYS_MON` is the monitored system/chiplet clock entering the sensing paths.
- `CLK_PROBE` is the trusted safe-domain DFF/backend clock.
- Existing validated capture timing remains the reference implementation; ARCH0 does not reopen latch-aperture optimization.

## 4. Frozen backend feature contract

The primary backend scalar is

`M_FF = sum(i*q_ff[i]), i=0..29`.

Its mathematical range is `0..435`, therefore `M_FF`, `M_REF_RISE`, `M_REF_FALL`, `D_M`, `M_MARGIN_RISE`, and `M_MARGIN_FALL` are 9-bit unsigned quantities.

`q_ff[29:0]` remains preserved for debug/characterization, but ARCH0 does not require per-bit calibration or raw-code repair.

## 5. Frozen startup self-calibration contract

- Calibration is allowed only during an explicitly healthy startup/service state asserted by system control.
- Rise and fall events are calibrated separately.
- Four valid rise samples form `M_REF_RISE`; four valid fall samples form `M_REF_FALL`.
- Each reference is the rounded/implementation-defined integer mean of its four samples; an implementation may realize the divide-by-four as a right shift after accumulation.
- Four-sample accumulation requires at least 11 unsigned bits because `4*435 = 1740`.
- After both references are valid, `CAL_LOCK` is asserted.
- After `CAL_LOCK`, the references must not be continuously adapted during normal detection operation.
- No 0.8-1.1 V sweep point is automatically considered a legal calibration point. The `0.8 V .. 1.1 V` range is a sensor-characterization range, not a universal legal operating-voltage range.

## 6. Frozen detection contract

For each valid captured event:

1. `edge_pol` selects `M_REF_RISE` or `M_REF_FALL`.
2. Compute `D_M = abs(M_FF - M_REF_selected)`.
3. Select the corresponding programmable `M_MARGIN_RISE` or `M_MARGIN_FALL`.
4. A detection comparison is meaningful only when `event_valid && CAL_LOCK`.
5. Assert `DROOP_ALARM` when `D_M > M_MARGIN_selected` under a meaningful detection event.
6. `DROOP_ALARM_STICKY` records that at least one alarm has occurred until explicit reset/clear.

ARCH0 intentionally uses absolute deviation rather than assuming that every process instance must move `M_FF` in one fixed direction under a droop.

## 7. Frozen interface-level state

Required backend-visible state/signals:

- `q_ff[29:0]`
- `M_FF[8:0]`
- `event_valid`
- `edge_pol`
- `CAL_MODE`
- `CAL_LOCK`
- `M_REF_RISE[8:0]`
- `M_REF_FALL[8:0]`
- `SUM_RISE[10:0]`
- `SUM_FALL[10:0]`
- calibration sample counters for rise/fall
- `M_MARGIN_RISE[8:0]`
- `M_MARGIN_FALL[8:0]`
- `D_M[8:0]`
- `DROOP_ALARM`
- `DROOP_ALARM_STICKY`

`event_valid` and `edge_pol` belong to the capture/control contract; their internal generation is deferred to RTL design and must not be inferred by repairing `q_ff`.

## 8. Explicitly not frozen by ARCH0

The following are deferred and must not be silently invented in this stage:

- numerical alarm margins;
- temperature/PVT guard bands;
- DVFS/OPP reference-bank policy;
- physical implementation of the Level-0 domain-crossing interface;
- final calibration enable/handshake protocol with the host chiplet;
- synthesizable adder-tree micro-architecture for `M_FF`;
- alarm persistence/debounce beyond the frozen sticky-alarm state;
- clock-glitch feature fusion;
- LUT/ML/multi-feature classifiers;
- latch-aperture re-optimization;
- per-bit baseline repair or bubble correction.

## 9. Architectural rationale carried forward

CALN0 showed that absolute normal `M_FF` varies strongly across SMIC40LL Monte Carlo instances, while per-instance baseline subtraction compresses the normal residual spread substantially. ARCH0 therefore treats per-chip startup baseline acquisition as a first-class backend function, while leaving the final numerical detection margin for a later characterization stage.

Gate: `BFE5_ARCH0_CONTRACT_FROZEN`
