# B-FE5-ARCH1-CANDIDATE: Gated fine-step background tracking + signed-error droop comparator

Status: `FUTURE_CANDIDATE_FROZEN`

Relationship to ARCH0: `B-FE5-ARCH0` remains the current frozen implementation contract. This document freezes the intended ARCH1 research architecture so that later work does not lose either of its two required backend functions: **bounded background reference tracking** and a **signed-error droop alarm branch**. ARCH1 is still **not authorized for production RTL implementation**, is not yet a replacement for ARCH0, and does not reopen the frozen sensing/capture path.

## 1. Purpose

ARCH0 performs healthy startup calibration and then freezes `M_REF_RISE/FALL` after `CAL_LOCK`. The original ARCH1 candidate added a tightly gated, bounded, 1-LSB runtime reference tracker to absorb slow benign drift such as temperature/aging/process-environment evolution while preventing the detector from learning an attack as the new normal.

Subsequent retained-data evidence exposed a second requirement that is now part of the ARCH1 architecture contract: ARCH0 discards the sign of

```text
e = M_FF - M_REF
```

when it forms `D_M=abs(e)`. For the frozen RISE-droop cases studied so far, this sign removal causes shallow/short droop responses to overlap the healthy absolute-error tail even though the **positive signed error remains separated** in the retained population. Therefore ARCH1 must preserve signed `e` not only for tracking direction, but also for a parallel droop-specific alarm decision.

ARCH1 hence has two distinct backend objectives:

1. **Benign-drift tolerance:** startup-anchored, fine-step, temporally filtered, safety-gated reference tracking.
2. **Weak/short droop sensitivity:** a signed-error droop comparator operating before the `abs()` information loss, in parallel with the inherited absolute-error alarm.

The key architectural distinctions are:

- the physical frontend and real capture path remain frozen;
- the **reference** may move slowly only under a safety gate;
- the inherited absolute alarm margin remains fixed/programmable and is not continuously learned;
- signed `e` is preserved as a first-class backend signal;
- a signed droop alarm has priority over reference tracking and must freeze tracking when asserted;
- runtime adaptation remains bounded to the startup anchor unless trusted system context authorizes a new operating point.

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
                           |
             +-------------+-------------------+
             |                                 |
             v                                 v
        D_M = abs(e)                    signed droop test
             |                                 |
             v                                 v
      D_M > M_MARGIN ?              polarity-aware signed rule
             |                       evidence-backed RISE form:
             |                         e > T_POS_RISE
             |                                 |
             +---------------+-----------------+
                             |
                             v
                    ABS_ALARM || SIGNED_DROOP_ALARM
                             |
                    +--------+--------+
                    |                 |
                   yes                no
                    |                 |
                    v                 v
                  ALARM        track/hold-region test
                    |                 |
                    v          +------+------+
             freeze reference  |             |
                               v             v
                        persistent small   HOLD
                         signed error      no update
                               |
                        temporal voting
                               |
                        safety gate pass?
                               |
                               v
                    M_REF_TRACK +=/-= 1 LSB
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

The signed alarm is intentionally drawn **before/parallel to `abs(e)`**. It is not a replacement for the existing absolute-error alarm; the two alarm sources are OR-combined. The signed alarm must be evaluated before any tracking update is accepted so that a weak droop cannot be learned into `M_REF_TRACK`.

## 3. Frozen candidate invariants

The following are architectural invariants and must not be silently weakened in a future implementation:

1. `B-FE5-ARCH0` sensing and capture topology remains unchanged: `RVT/LVT -> XOR -> Level-0 -> LATQ -> DFF -> M_FF`.
2. ARCH1 backend logic does not alter the delay paths, tap count, latch timing, DFF timing, or raw `q_ff[29:0]` semantics.
3. Rise and fall references remain independent.
4. Startup calibration establishes immutable anchors `M_REF_STARTUP_RISE` and `M_REF_STARTUP_FALL` before runtime tracking begins.
5. Runtime tracking uses mutable `M_REF_TRACK_RISE/FALL` initialized from the corresponding startup anchor.
6. When a tracking update is permitted, the selected reference changes by at most one `M_FF` LSB per accepted update event.
7. The inherited absolute alarm margin remains fixed or software/CSR programmable; it is not automatically widened from the monitored stream.
8. **ARCH1 must preserve signed `e=M_FF-M_REF_TRACK` and must include a droop-specific signed comparator branch in parallel with `abs(e)>M_MARGIN`.**
9. The signed droop alarm has priority over TRACK/HOLD decisions. Any signed-droop suspicion/alarm freezes reference updates for that event and subsequent protected state.
10. For the currently evidence-backed RISE-droop direction, the candidate rule is `e > T_POS_RISE`. The exact production value of `T_POS_RISE` is not frozen by this document.
11. FALL signed-direction semantics and any `T_NEG`/polarity-specific rule require separate characterization; they must not be invented from RISE-only evidence.
12. Any confirmed or pending suspicious excursion freezes reference updates until a trusted recovery/clear policy permits tracking again.
13. Runtime tracking remains bounded relative to the startup anchor. Without explicit trusted authorization, the reference may not drift indefinitely.
14. A legal DVFS/AVS/OPP transition must be indicated by trusted safe-domain context. The detector must not classify a slowly moving `M_FF` as legitimate merely because it is slow.
15. The tracker must never repair or rewrite `q_ff[29:0]`; raw capture remains preserved for characterization/debug.
16. ARCH1 does not reopen LATQ aperture, source-free reflip, analog closure-time, or sub-cycle off-edge observability research.

## 4. Runtime alarm and tracking regions

For the selected polarity, define:

```text
M_REF = M_REF_TRACK_selected
e     = M_FF - M_REF
D_M   = abs(e)
```

The inherited absolute alarm remains:

```text
ABS_ALARM = (D_M > M_MARGIN)
```

ARCH1 additionally requires a signed droop branch. For the currently characterized RISE-droop direction:

```text
SIGNED_DROOP_ALARM_RISE = RISE_event && (e > T_POS_RISE)
```

Future FALL behavior must be established from evidence before defining a corresponding signed rule.

The effective alarm policy is conceptually:

```text
ALARM_REQUEST = ABS_ALARM || SIGNED_DROOP_ALARM
```

with priority:

```text
if ALARM_REQUEST:
    assert/funnel into alarm pipeline
    freeze reference update
else if 0 < D_M <= T_TRACK and safety/temporal gates pass:
    update M_REF_TRACK by sign(e) * 1 LSB
else:
    hold reference
```

Thus an event can legitimately satisfy:

```text
D_M <= M_MARGIN
but
e > T_POS_RISE
```

and still be classified as a droop alarm candidate. This is the intended mechanism for recovering weak/short RISE droops that ARCH0 loses after `abs()` and a single symmetric margin.

The numerical values of `T_TRACK`, `B_TRACK`, `M_MARGIN`, exact alarm persistence, and production `T_POS_RISE` remain signoff parameters. Their eventual inequalities must ensure that signed alarm priority cannot be bypassed by the tracking region.

## 5. Evidence basis for the signed-error comparator requirement

The signed-error comparator is now frozen into ARCH1 because it has independent retained-data support across two distinct weak-response dimensions.

### 5.1 D01 amplitude-sensitivity evidence

The frozen signed-error audit evaluated `e=M_FF-M_REF_RISE` before `abs()` using retained BFE8/BFE9/BFE10 data:

```text
Healthy RISE, 360 samples: signed-e max = +18
D01 30 mV target, 30 samples: signed-e min = +20
D02 60 mV target, 30 samples: signed-e min = +41
```

For the retained population, the diagnostic rule `e > T_POS` had a non-empty separation interval:

```text
continuous candidate interval = [18,20)
integer candidates            = 18 or 19
```

At `e>18`, D01 changed from the formal ARCH0 result `22/30` to diagnostic `30/30` while the retained healthy RISE set had zero observed positive false alarms. This was an offline diagnostic, not a formal threshold change.

Authority:

`delay_chain/ftc/analysis/b_fe_frontend/arch1_signed_error_separability_audit/`

Gate: `ARCH1_SIGNED_ERROR_SEPARABILITY_AUDIT_FROZEN`

### 5.2 D04 duration-sensitivity generalization evidence

BFE11 then held droop depth at 60 mV and shortened the full-depth dwell from D02 3.0 ns to D04 0.6 ns. Formal ARCH0 produced:

```text
D04 formal ARCH0 coverage = 24/30
D04 headroom min/median   = -2 / +10.5 M-codes
```

Without tuning a new threshold, BFE11 applied the already-frozen signed candidates `T_POS=18` and `19` as shadow diagnostics. Both recovered all six ARCH0 D04 MISS seeds:

```text
41007, 41012, 41015, 41016, 41022, 41025
```

and both produced diagnostic `30/30` D04 coverage, with no ARCH0 HIT lost. D04 signed `e` was `+20..+45`, while the reused healthy RISE signed maximum remained `+18`.

Authority:

`delay_chain/ftc/analysis/b_fe_frontend/bfe11_d04_arch0_duration_sensitivity/BFE11_D04_SIGNED_SHADOW.json`

Gate: `BFE11_D04_P5_SIGNED_SHADOW_FROZEN`

These results justify freezing the **presence of the signed-error droop comparator** into ARCH1. They do **not** yet justify treating 18 or 19 as silicon/PVT-signoff threshold values.

## 6. Frozen safety gate concept

A runtime reference update is permitted only if all candidate safety conditions are satisfied. The exact Boolean implementation is deferred, but future logic must preserve at least:

```text
TRACK_UPDATE_ALLOWED =
    event_valid
    && CAL_LOCK
    && selected_reference_valid
    && !ABS_ALARM
    && !SIGNED_DROOP_ALARM
    && no_pending_or_confirmed_alarm
    && no_untrusted_transition_context
    && error_is_inside_track_region
    && temporal_vote_accepts_same_signed_small_error
    && startup_anchor_budget_not_exceeded
```

The explicit `!SIGNED_DROOP_ALARM` term is an architectural requirement. A positive RISE excursion that meets the signed droop rule must never be consumed as a normal tracking sample simply because `abs(e)` remains below the inherited margin.

## 7. Startup-anchor drift budget

To prevent a slow malicious voltage reduction from being absorbed indefinitely, the runtime reference remains inside a bounded neighborhood of the startup anchor unless trusted system control explicitly authorizes a new operating point:

```text
abs(M_REF_TRACK - M_REF_STARTUP) <= B_TRACK
```

`B_TRACK` remains a future programmable/signoff parameter. Reaching the bound must stop further unauthenticated movement in that direction. A later policy may raise maintenance, drift-limit, or alarm status.

The signed droop comparator does not eliminate the need for this bound: the tracker and signed comparator protect against different failure modes.

## 8. Trusted operating-point context

A future chiplet may legitimately alter voltage/frequency through AVS/DVFS. `M_FF` alone cannot distinguish a legal slow operating-point transition from an attacker producing the same observed trajectory. ARCH1 therefore reserves trusted safe-domain context such as:

```text
OPP_CHANGE_VALID
REBASE_AUTH
OPP_PROFILE_ID
```

Authorization to exceed the startup-anchor drift budget or establish a new baseline must originate from trusted power-management/system context rather than from the sensor stream itself.

A future implementation may use separate reference/threshold profiles per authorized OPP or a trusted rebaseline sequence. Exact protocol is deferred.

## 9. Why ARCH1 keeps both the absolute alarm and signed droop alarm

The signed branch is not intended to replace `abs(e)>M_MARGIN`.

The inherited absolute detector remains useful for large excursions regardless of direction and preserves continuity with ARCH0. The signed branch is a targeted recovery of direction information that ARCH0 discards before thresholding.

Conceptually:

```text
large excursion, either sign
    -> abs(e) > M_MARGIN
    -> ABS_ALARM

weak/short evidence-backed droop direction
    -> e > T_POS_RISE
    -> SIGNED_DROOP_ALARM

small safe persistent drift
    -> no alarm
    -> temporal vote + safety gate
    -> +/-1 LSB tracking
```

The monitored stream is never allowed to teach the detector to continuously widen its own acceptance window.

## 10. Literature-derived rationale and project-specific extension

### Directly source-backed architectural ideas

- **He et al., Design-Agnostic Distributed Timing Fault Injection Monitor With End-to-End Design Automation (JSSC, 2025):** startup/reset locking followed by fine-grained dynamic tracking, with Temporal Majority Voting to filter slow tracking observables.
- **Giron et al., Delay Based Auto-Calibrated PVT Monitor System and Method (2020):** feedback auto-calibration and periodic recalibration to keep sensed delay centered.
- **GUARD (Li et al., 2025):** thresholded digital timing/voltage-monitor outputs that reject normal disturbance while retaining glitch sensitivity.
- **Augustine et al., all-digital CoRO VDM (2023):** calibration granularity materially changes droop measurement error.
- **Diwall (El Bouazzati et al.):** low-cost EWMA-style filtering can be hardware efficient while control limits remain separately established.

### Security rationale from adjacent anomaly-detection literature

- **Korycki and Krawczyk (2023):** unrestricted adaptation can be poisoned by adversarial concept drift.
- **Abedin et al. (2027):** gated nominal-reference updates provide an algorithmic precedent for refusing adaptation when detector/context evidence is suspicious.

### Project-specific inference and evidence

No cited work implements this exact combination:

```text
startup anchor
+ fine-step bounded tracking
+ temporal voting
+ fixed absolute alarm window
+ signed-error droop comparator
+ alarm-priority tracker freeze
+ trusted OPP authorization
```

The signed comparator is specifically a project-derived architectural extension supported by the frozen D01 signed-separability audit and D04 cross-duration shadow generalization. Its presence is now frozen; its production threshold and full operating-range signoff remain future validation tasks.

## 11. Required validation before promotion

A successor validation stage must compare frozen ARCH0 against the updated ARCH1 candidate without changing the physical frontend/capture path.

At minimum it must cover:

1. **slow benign drift:** bounded fine-step tracking reduces harmless reference error/false-alarm pressure relative to ARCH0;
2. **D01-like shallow droop:** signed comparator recovers the retained weak-amplitude blindspot without being learned by the tracker;
3. **D04-like short droop:** signed comparator retains the observed cross-duration benefit when integrated with real ARCH1 reference-tracking state;
4. **sudden strong droop:** inherited absolute detector remains functional and a real fast excursion is not learned away;
5. **slow unauthorized droop:** startup-anchor bound and alarm/hold priority prevent indefinite baseline poisoning;
6. **trusted authorized voltage/OPP transition:** enlarged tracking/rebaseline behavior occurs only with trusted authorization;
7. **tracker/comparator interaction:** after legitimate bounded reference movement, signed-error droop detection remains effective and does not create an unsafe tracking path;
8. **polarity scope:** characterize FALL behavior before enabling any FALL signed comparator rule.

Promotion requires evidence that ARCH1 improves benign-drift tolerance and weak/short droop sensitivity without reducing strong-droop sensitivity, materially worsening healthy false alarms, or allowing an attacker to drag the reference around the signed alarm path.

## 12. Candidate backend-visible state

The following state/signals are reserved conceptually for a future implementation; exact RTL names and widths are not frozen unless inherited from ARCH0:

- inherited `q_ff[29:0]`
- inherited `M_FF[8:0]`
- inherited `event_valid`
- inherited `edge_pol`
- inherited startup calibration state and `CAL_LOCK`
- `M_REF_STARTUP_RISE`
- `M_REF_STARTUP_FALL`
- `M_REF_TRACK_RISE`
- `M_REF_TRACK_FALL`
- signed `e`
- inherited `D_M=abs(e)`
- inherited/fixed-programmable `M_MARGIN_RISE/FALL`
- `T_POS_RISE` or equivalent RISE signed-droop threshold representation
- future polarity-specific signed threshold/state only after characterization
- `SIGNED_DROOP_ALARM`
- `ABS_ALARM`
- combined alarm request before tracker update acceptance
- `T_TRACK_RISE/FALL`
- `B_TRACK_RISE/FALL`
- signed-error direction/persistence state
- temporal vote/persistence state
- track freeze/enable state
- optional trusted `OPP_CHANGE_VALID` / `REBASE_AUTH` / profile context

## 13. Explicitly deferred / not authorized by this freeze

This candidate freeze does **not** authorize or decide:

- production RTL implementation;
- final numerical `T_POS_RISE` value, despite retained-data candidates 18/19;
- FALL signed comparator polarity/direction/threshold;
- final `T_TRACK`, `B_TRACK`, or inherited `M_MARGIN` values;
- exact K-of-N/majority/persistence parameters;
- EWMA coefficients or two-timescale estimators;
- adaptive `M_MARGIN` learning;
- final DVFS/AVS/OPP protocol;
- number or organization of OPP reference/threshold banks;
- background recalibration frequency;
- final alarm debounce/persistence policy;
- PVT/silicon signoff ranges;
- physical Level-0 crossing implementation;
- any modification to sensor path, latch aperture, DFF timing, tap structure, or raw-code semantics;
- `N=sum(q)`, LUT/ML classifiers, broad spatial-feature expansion, or clock-glitch feature fusion unless later evidence shows the signed comparator is insufficient.

The important distinction is: **the signed-error droop comparator block itself is no longer deferred; its exact implementation parameters and signoff are deferred.**

## 14. Freeze statement

`B-FE5-ARCH1-CANDIDATE` is frozen as the preferred future research architecture with two required backend capabilities:

```text
(1) startup-anchored, fine-step, temporally filtered,
    safety-gated, bounded background reference tracking

AND

(2) a pre-ABS signed-error droop comparator in parallel with
    the inherited absolute-error alarm, with alarm priority
    over any reference-tracking update
```

For the currently characterized RISE droop direction, the evidence-backed candidate form is `e > T_POS_RISE`; retained D01/D04 evidence identifies 18/19 as diagnostic candidates but does not yet freeze either as the production threshold.

Until an integration/validation stage explicitly promotes this architecture, `B-FE5-ARCH0` remains the authoritative production implementation contract.

Candidate tag: `BFE5_ARCH1_GATED_FINE_TRACK_SIGNED_DROOP_CANDIDATE_FROZEN`
