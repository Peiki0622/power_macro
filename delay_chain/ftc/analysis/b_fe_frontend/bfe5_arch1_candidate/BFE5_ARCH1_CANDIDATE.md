# B-FE5-ARCH1-CANDIDATE: Gated fine-step background tracking

Status: `FUTURE_CANDIDATE_FROZEN`

Relationship to ARCH0: `B-FE5-ARCH0` remains the current frozen implementation contract. This document only freezes a future candidate architecture so that the intended direction, safety constraints, and source-derived rationale are not lost. ARCH1 is **not** authorized for RTL implementation, is **not** a replacement for ARCH0, and does **not** reopen the frozen sensing/capture path.

## 1. Purpose

ARCH0 performs healthy startup calibration and then freezes `M_REF_RISE/FALL` after `CAL_LOCK`. ARCH1-CANDIDATE preserves that startup anchor, but adds a tightly gated, bounded, 1-LSB runtime reference tracker intended to absorb only slow benign drift such as temperature/aging/process-environment evolution while preventing the detector from learning an attack as the new normal.

The key architectural distinction is:

- the **reference** may move slowly and only under a safety gate;
- the **alarm margin** remains fixed/programmable and is not continuously learned;
- any runtime adaptation remains anchored to the startup reference and bounded by a drift budget;
- authorized operating-point changes must come from trusted system context, not be inferred from `M_FF` alone.

## 2. Frozen candidate top-level architecture

```text
                         B-FE5-ARCH1 FUTURE CANDIDATE

                 ARCH0 FRONTEND/CAPTURE REMAINS FROZEN

PD_SENSE
CLK_SYS_MON
    |
4-stage RVT prefix / 0-stage LVT prefix
    |
30-stage RVT/LVT paths
    |
30 x XOR
    |
Level-0 restoration
    |
PD_SAFE
30 x LATQ -> 30 x DFF
    |
q_ff[29:0]
    |
M_FF = sum(i*q_ff[i]), i=0..29
    |
    +-------------------- event_valid / edge_pol
    |
    v
+-------------------------------------------------------------+
| Startup calibration                                         |
|                                                             |
|  4 valid RISE samples -> M_REF_STARTUP_RISE                 |
|  4 valid FALL samples -> M_REF_STARTUP_FALL                 |
|                          |                                  |
|                        CAL_LOCK                              |
|                          |                                  |
|                          v                                  |
|        M_REF_TRACK_RISE/FALL := M_REF_STARTUP_RISE/FALL     |
+--------------------------+----------------------------------+
                           |
                           v
                  select by edge_pol
                           |
                           v
              e = M_FF - M_REF_TRACK
              D_M = abs(e)
                           |
             +-------------+-------------+
             |                           |
             v                           v
      D_M > M_MARGIN ?              D_M <= M_MARGIN
             |                           |
            yes                          v
             |                   track-region test
             v                           |
          ALARM                +---------+---------+
             |                 |                   |
             v                 v                   v
      freeze reference    small persistent     hold region
                          signed error          no update
                               |
                        temporal voting
                               |
                        safety gate pass?
                               |
                               v
                     +/- 1 LSB reference
                           update only
                               |
                    bounded by startup anchor
                               |
                               v
                       next valid event

Trusted safe-domain context (future optional):

OPP_CHANGE_VALID / REBASE_AUTH
             |
             +----> permits only an explicitly authorized
                    operating-point transition/rebaseline policy
                    defined by a later stage
```

## 3. Frozen candidate invariants

The following are architectural invariants of this candidate and must not be silently weakened in a future implementation:

1. `B-FE5-ARCH0` sensing and capture topology remains unchanged: `RVT/LVT -> XOR -> Level-0 -> LATQ -> DFF -> M_FF`.
2. Runtime adaptation operates only on the backend reference representation; it does not alter the delay paths, tap count, latch timing, DFF timing, or raw `q_ff[29:0]`.
3. Rise and fall references remain independent.
4. Startup calibration still establishes immutable anchors `M_REF_STARTUP_RISE` and `M_REF_STARTUP_FALL` before runtime tracking begins.
5. Runtime tracking uses a separate mutable reference `M_REF_TRACK_RISE/FALL` initialized from the corresponding startup anchor.
6. The first implementation candidate is a **fine-step tracker**: when an update is permitted, the selected reference changes by at most one `M_FF` LSB per accepted update event.
7. The alarm threshold/margin is fixed or software/CSR programmable; it is **not** automatically widened from the same stream that is being monitored.
8. Any confirmed or pending suspicious excursion freezes reference updates until a trusted recovery/clear policy permits tracking again.
9. Runtime tracking is bounded relative to the startup anchor. Without explicit trusted authorization, the reference may not drift indefinitely.
10. A legal DVFS/AVS/OPP transition must be indicated by trusted safe-domain context. The detector must not classify a slowly moving `M_FF` as legitimate merely because it is slow.
11. The tracker must never repair or rewrite `q_ff[29:0]`; raw capture remains preserved for characterization/debug.
12. ARCH1 does not reopen LATQ aperture, source-free reflip, analog closure-time, or sub-cycle off-edge observability research.

## 4. Candidate runtime decision regions

For the selected polarity, define:

```text
M_REF = M_REF_TRACK_selected
e     = M_FF - M_REF
D_M   = abs(e)
```

The candidate uses three logical regions:

```text
D_M > M_MARGIN
    -> ALARM region
    -> assert alarm
    -> freeze reference update

0 < D_M <= T_TRACK
    -> TRACK candidate region
    -> require temporal persistence/majority
    -> require safety gate
    -> update M_REF_TRACK by sign(e) * 1 LSB

T_TRACK < D_M <= M_MARGIN
    -> HOLD region
    -> no alarm yet
    -> no reference update
```

`e = 0` never requires a reference update.

The numerical values of `T_TRACK`, `M_MARGIN`, the persistence rule, and any hysteresis are intentionally deferred. A later stage must establish the required inequality and signoff range, with at minimum:

```text
0 <= T_TRACK < M_MARGIN
```

for each polarity/profile in which this architecture is used.

## 5. Frozen safety gate concept

A runtime reference update is permitted only if **all** candidate safety conditions are satisfied. The exact Boolean implementation is deferred, but the future logic must preserve the following semantics:

```text
TRACK_UPDATE_ALLOWED =
    event_valid
    && CAL_LOCK
    && selected_reference_valid
    && no_pending_or_confirmed_alarm
    && no_untrusted_transition_context
    && error_is_inside_track_region
    && temporal_vote_accepts_same_signed_small_error
    && startup_anchor_budget_not_exceeded
```

A confirmed alarm must freeze tracking. A suspicious excursion in the HOLD/ALARM direction must not itself be used to drag the reference toward the observed value.

If the architecture later distinguishes raw alert, confirmed alert, sticky alert, service state, or recovery state, those signals may refine the gate but must not bypass the invariants above.

## 6. Startup-anchor drift budget

To prevent a slow malicious voltage reduction from being absorbed indefinitely, the candidate keeps the runtime reference inside a bounded neighborhood of the startup anchor unless trusted system control explicitly authorizes a new operating point.

For each polarity:

```text
abs(M_REF_TRACK - M_REF_STARTUP) <= B_TRACK
```

where `B_TRACK` is a future programmable/signoff parameter.

Reaching the bound does not automatically imply an attack, but it must stop further unauthenticated reference movement in that direction. A later detector-policy stage may choose to raise a maintenance, drift-limit, or alarm indication.

## 7. Trusted operating-point context

A future chiplet may legitimately alter voltage/frequency through AVS/DVFS. `M_FF` alone cannot distinguish a legal slow operating-point transition from an attacker producing the same observed trajectory. Therefore ARCH1 reserves a trusted safe-domain context such as:

```text
OPP_CHANGE_VALID
REBASE_AUTH
OPP_PROFILE_ID
```

The exact interface is **not** frozen here. What is frozen is the security requirement that any authorization to exceed the ordinary startup-anchor drift budget or to establish a new baseline must originate from trusted system/power-management context rather than from the sensor observation alone.

A future implementation may choose either:

- separate reference banks per authorized OPP/profile, or
- a trusted service/recalibration sequence that establishes a new anchor.

ARCH1-CANDIDATE does not select between those policies yet.

## 8. Why the first candidate is fine-step tracking, not a continuously learned margin

The first ARCH1 candidate intentionally does **not** require a two-timescale EWMA or an adaptive alarm margin.

The intended minimal hardware behavior is closer to:

```text
persistent small positive e -> M_REF_TRACK := M_REF_TRACK + 1
persistent small negative e -> M_REF_TRACK := M_REF_TRACK - 1
otherwise                   -> hold
```

Temporal majority/persistence filtering prevents a single noisy sample from moving the reference. A moving-average/EWMA estimator may be evaluated later, but it is not part of the frozen candidate contract.

`M_MARGIN_RISE/FALL` remains fixed/programmable. The monitored stream is not allowed to teach the detector to continuously widen its own acceptance window.

## 9. Literature-derived rationale and limits

This candidate is intentionally separated into source-backed ideas and project-specific inference.

### Directly source-backed architectural ideas

- **He et al., Design-Agnostic Distributed Timing Fault Injection Monitor With End-to-End Design Automation (JSSC, 2025):** performs an initial startup/reset locking procedure and then enters `Full Range Linear Tracking`; the finest delay step is used for dynamic tracking, and Temporal Majority Voting low-pass-filters the tracking observable. Its purpose is to tolerate slow clock-source/environment/aging drift while keeping an independent acceptance window.
- **Giron et al., Delay Based Auto-Calibrated PVT Monitor System and Method (2020):** uses feedback auto-calibration that explores clock/delay-chain settings and selects a setting that keeps the sensed delay level centered; recalibration is repeated after a defined interval.
- **GUARD (Li et al., 2025):** compares TDC outputs against preset thresholds and demonstrates that threshold choice can reject small normal dynamic IR-drop-like disturbances while still protecting against glitch attacks.
- **Augustine et al., all-digital CoRO VDM (2023):** shows experimentally that calibration granularity (per-instance/temperature/die versus coarser calibration) materially changes voltage-droop measurement error.
- **Diwall (El Bouazzati et al.):** demonstrates that EWMA can be implemented cheaply in hardware with shift/add operations, but its control limits are separately established; this supports low-cost filtering as an option, not a continuously self-expanding alarm window.

### Security rationale borrowed from adjacent anomaly-detection literature

- **Korycki and Krawczyk (2023):** adversarial concept drift/poisoning can force false adaptation or prevent correct adaptation. This motivates refusing unrestricted online baseline learning in a security monitor.
- **Abedin et al. (2027):** uses a gated nominal-reference update in which the online reference is updated only when detector outputs and operating context indicate safe nominal operation. This is an algorithmic precedent for gating adaptation; it is not claimed to be an on-chip voltage-sensor implementation.

### Project-specific inference

No cited work implements this exact `M_FF` fine-step, bounded, trusted-context-gated tracker. The combination of:

```text
startup anchor
+ fine-step runtime tracking
+ temporal voting
+ fixed alarm window
+ bounded unauthenticated drift
+ trusted OPP authorization
```

is therefore a project architecture hypothesis derived from the above evidence and must be validated experimentally before promotion from candidate to implementation contract.

## 10. Required validation before promotion

The narrow validation stage reserved for this candidate is `ADAPT0`. It must compare the frozen ARCH0 static-reference detector against ARCH1-CANDIDATE without changing the physical frontend or capture path.

At minimum, ADAPT0 must contain four classes:

1. **slow benign drift**: demonstrate that bounded fine-step tracking reduces harmless reference error/false-alarm pressure relative to ARCH0;
2. **sudden droop**: demonstrate that a real fast droop is not learned away and still produces a large residual/alarm;
3. **slow unauthorized droop**: demonstrate that the startup-anchor budget and HOLD/ALARM freeze prevent indefinite baseline poisoning;
4. **trusted authorized voltage/OPP transition**: demonstrate that any enlarged tracking/rebaseline behavior occurs only when trusted authorization is asserted.

Promotion requires evidence that ARCH1 improves benign-drift tolerance without reducing relevant droop sensitivity or enabling an attacker to monotonically drag the reference outside the allowed anchor budget.

## 11. Candidate backend-visible state

The following state/signals are reserved conceptually for a future implementation. Their exact RTL names and widths are not frozen unless already inherited from ARCH0:

- inherited `q_ff[29:0]`
- inherited `M_FF[8:0]`
- inherited `event_valid`
- inherited `edge_pol`
- inherited startup calibration state and `CAL_LOCK`
- `M_REF_STARTUP_RISE`
- `M_REF_STARTUP_FALL`
- `M_REF_TRACK_RISE`
- `M_REF_TRACK_FALL`
- `T_TRACK_RISE/FALL`
- inherited/fixed-programmable `M_MARGIN_RISE/FALL`
- `B_TRACK_RISE/FALL`
- signed-error direction/persistence state
- temporal vote/persistence state
- track freeze/enable state
- optional trusted `OPP_CHANGE_VALID` / `REBASE_AUTH` / profile context

## 12. Explicitly deferred / not authorized by this freeze

This candidate freeze does **not** authorize or decide:

- RTL implementation;
- numerical `T_TRACK`, `B_TRACK`, or `M_MARGIN` values;
- exact K-of-N/majority/persistence parameters;
- EWMA coefficients or two-timescale estimators;
- adaptive `M_MARGIN` learning;
- final DVFS/AVS/OPP protocol;
- number or organization of OPP reference banks;
- background recalibration frequency;
- alarm debounce/persistence policy beyond the freeze semantics above;
- PVT signoff ranges;
- physical Level-0 crossing implementation;
- any modification to the sensor path, latch aperture, DFF timing, tap structure, or raw-code semantics;
- clock-glitch feature fusion, LUT/ML classifiers, or multi-feature backend expansion.

## 13. Freeze statement

`B-FE5-ARCH1-CANDIDATE` is frozen as the preferred **future research architecture** for continuous self-calibration: startup-anchored, fine-step, temporally filtered, safety-gated, bounded background reference tracking with a separately fixed/programmed alarm margin and trusted authorization for operating-point changes.

Until `ADAPT0` or a successor stage validates and explicitly promotes it, `B-FE5-ARCH0` remains the authoritative implementation contract.

Candidate tag: `BFE5_ARCH1_GATED_FINE_TRACK_CANDIDATE_FROZEN`
