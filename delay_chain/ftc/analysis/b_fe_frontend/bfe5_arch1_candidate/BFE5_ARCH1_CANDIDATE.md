# B-FE5-ARCH1-CANDIDATE: Gated fine-step background tracking + security-anchor signed-error droop comparator

Status: `FUTURE_CANDIDATE_FROZEN`

Relationship to ARCH0: `B-FE5-ARCH0` remains the current frozen implementation contract. This document freezes the intended ARCH1 research architecture so that later work does not lose either of its two required backend functions: **bounded background reference tracking** and a **signed-error droop alarm branch**. Following the frozen reference-interaction audit, these two functions no longer share one mutable runtime reference by default: the tracking/absolute path uses `M_REF_TRACK`, while the signed droop path uses a startup/trusted **security anchor**. ARCH1 is still **not authorized for production RTL implementation**, is not yet a replacement for ARCH0, and does not reopen the frozen sensing/capture path.

## 1. Purpose

ARCH0 performs healthy startup calibration and then freezes `M_REF_RISE/FALL` after `CAL_LOCK`. The original ARCH1 candidate added a tightly gated, bounded, 1-LSB runtime reference tracker to absorb slow benign drift such as temperature/aging/process-environment evolution while preventing the detector from learning an attack as the new normal.

Subsequent retained-data evidence exposed a second requirement: ARCH0 discards the sign of the reference error when it forms an absolute magnitude. For the frozen RISE-droop cases studied so far, shallow/short droop responses overlap the healthy absolute-error tail even though positive signed error remains separated in the retained population. BFE12 then validated a real RTL signed-RISE comparator that reproduces the retained shadow benefit.

The later reference-interaction audit established an additional architectural requirement: **ordinary runtime tracking must not move the reference used by the signed droop comparator**. If the signed comparator directly uses `M_REF_TRACK`, even small tracker displacement consumes the narrow D01/D04 signed headroom or can create healthy positive alarms. Therefore ARCH1 now freezes a dual-reference policy.

ARCH1 has two distinct backend objectives and two corresponding reference roles:

1. **Benign-drift tolerance:** use mutable `M_REF_TRACK_RISE/FALL` for the fine-step tracking path and the inherited absolute-error path.
2. **Weak/short droop sensitivity:** use a startup/trusted `M_REF_SECURITY_ANCHOR` for the signed-error droop comparator so ordinary tracker updates cannot move the security decision baseline.

The key architectural distinctions are:

- the physical frontend and real capture path remain frozen;
- `M_REF_TRACK` may move slowly only under a safety gate and bounded drift policy;
- `M_REF_SECURITY_ANCHOR` is initialized from the trusted startup calibration anchor and is **not modified by ordinary background tracking**;
- the inherited absolute alarm margin remains fixed/programmable and is not continuously learned;
- the tracking/absolute error and security signed error are separate backend quantities;
- a signed droop alarm has priority over reference tracking and must freeze tracking when asserted;
- any future security-anchor rebase must come from trusted system context, not from autonomous observation of `M_FF`.

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
    +-------------------------- event_valid / edge_pol
    |
    v
+----------------------------------------------------------------+
| Startup calibration                                            |
|                                                                |
| 4 valid RISE samples -> M_REF_STARTUP_RISE                     |
| 4 valid FALL samples -> M_REF_STARTUP_FALL                     |
|                         |                                      |
|                       CAL_LOCK                                 |
|                         |                                      |
|             +-----------+-----------+                          |
|             |                       |                          |
|             v                       v                          |
| M_REF_TRACK_RISE/FALL :=      M_REF_SECURITY_ANCHOR_RISE/FALL  |
| M_REF_STARTUP_RISE/FALL       := M_REF_STARTUP_RISE/FALL       |
+-------------+-------------------------+-------------------------+
              |                         |
              |                         |
      mutable tracking ref      trusted security anchor
              |                 ordinary tracker cannot move it
              |                         |
              v                         v
      select by edge_pol         select by edge_pol
              |                         |
              v                         v
 e_track = M_FF-M_REF_TRACK  e_anchor = M_FF-M_REF_SECURITY_ANCHOR
              |                         |
       +------+-------+                 |
       |              |                 |
       v              v                 v
D_track=abs(e_track) track/hold     signed droop test
       |              logic             |
       v                                v
D_track>M_MARGIN ?            evidence-backed RISE form:
       |                         e_anchor > T_POS_RISE
       |                                |
       +---------------+----------------+
                       |
                       v
              ABS_ALARM || SIGNED_DROOP_ALARM
                       |
              +--------+--------+
              |                 |
             yes                no
              |                 |
              v                 v
            ALARM        track/hold decision
              |                 |
              v          +------+------+
       freeze tracking   |             |
                         v             v
                  persistent small    HOLD
                    e_track          no update
                         |
                  temporal voting
                         |
                  safety gate pass?
                         |
                         v
               M_REF_TRACK +=/-= 1 LSB
                         |
             bounded relative to trusted anchor policy
                         |
                         v
                   next valid event

Trusted safe-domain context (future optional):

OPP_CHANGE_VALID / REBASE_AUTH
             |
             +----> may authorize an explicitly defined OPP transition,
                    tracker rebaseline, and/or security-anchor rebase policy
                    in a later stage; autonomous tracker activity alone may not.
```

The two references serve different purposes and must not be silently collapsed back into one mutable value. `M_REF_TRACK` follows authorized benign drift within its bounded policy. `M_REF_SECURITY_ANCHOR` preserves the signed droop security baseline. The signed alarm remains in parallel with the inherited absolute-error alarm and is evaluated before any tracking update is accepted.

## 3. Frozen candidate invariants

The following are architectural invariants and must not be silently weakened in a future implementation:

1. `B-FE5-ARCH0` sensing and capture topology remains unchanged: `RVT/LVT -> XOR -> Level-0 -> LATQ -> DFF -> M_FF`.
2. ARCH1 backend logic does not alter the delay paths, tap count, latch timing, DFF timing, or raw `q_ff[29:0]` semantics.
3. Rise and fall startup references remain independent.
4. Startup calibration establishes immutable audit anchors `M_REF_STARTUP_RISE` and `M_REF_STARTUP_FALL` before runtime tracking begins.
5. Runtime tracking uses separate mutable `M_REF_TRACK_RISE/FALL`, initialized from the corresponding startup reference.
6. ARCH1 reserves separate `M_REF_SECURITY_ANCHOR_RISE/FALL`, initialized from the corresponding startup reference. Ordinary background tracking must never update these security anchors.
7. When a tracking update is permitted, the selected `M_REF_TRACK` changes by at most one `M_FF` LSB per accepted update event.
8. The inherited absolute alarm margin remains fixed or software/CSR programmable; it is not automatically widened from the monitored stream.
9. The tracking/absolute path uses `e_track = M_FF - M_REF_TRACK` and `D_track = abs(e_track)`.
10. **The signed droop path uses `e_anchor = M_FF - M_REF_SECURITY_ANCHOR`; it must not use the ordinary mutable `M_REF_TRACK` as its default reference source.**
11. The signed-error droop comparator remains in parallel with the inherited absolute-error alarm.
12. The signed droop alarm has priority over TRACK/HOLD decisions. Any signed-droop suspicion/alarm freezes reference updates for that event and subsequent protected state.
13. For the currently evidence-backed RISE-droop direction, the candidate rule is `e_anchor > T_POS_RISE`. The exact production value of `T_POS_RISE` is not frozen by this document.
14. FALL signed-direction semantics and any `T_NEG`/polarity-specific rule require separate characterization; they must not be invented from RISE-only evidence.
15. Any confirmed or pending suspicious excursion freezes reference updates until a trusted recovery/clear policy permits tracking again.
16. Runtime tracking remains bounded relative to the trusted startup/anchor policy. Without explicit trusted authorization, the tracking reference may not drift indefinitely.
17. A legal DVFS/AVS/OPP transition must be indicated by trusted safe-domain context. The detector must not classify a slowly moving `M_FF` as legitimate merely because it is slow.
18. Any future rebase or replacement of `M_REF_SECURITY_ANCHOR` must require trusted authorization; autonomous tracker observation is insufficient authority.
19. The tracker must never repair or rewrite `q_ff[29:0]`; raw capture remains preserved for characterization/debug.
20. ARCH1 does not reopen LATQ aperture, source-free reflip, analog closure-time, or sub-cycle off-edge observability research.

## 4. Runtime alarm and tracking regions

For the selected polarity, define two errors:

```text
M_REF_TRACK    = M_REF_TRACK_selected
M_REF_ANCHOR   = M_REF_SECURITY_ANCHOR_selected

e_track        = M_FF - M_REF_TRACK
D_track        = abs(e_track)

e_anchor       = M_FF - M_REF_ANCHOR
```

The inherited absolute alarm becomes relative to the mutable tracking reference:

```text
ABS_ALARM = (D_track > M_MARGIN)
```

ARCH1 additionally requires a signed droop branch relative to the trusted security anchor. For the currently characterized RISE-droop direction:

```text
SIGNED_DROOP_ALARM_RISE = RISE_event && (e_anchor > T_POS_RISE)
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
    freeze M_REF_TRACK update
else if 0 < D_track <= T_TRACK and safety/temporal gates pass:
    update M_REF_TRACK by sign(e_track) * 1 LSB
else:
    hold M_REF_TRACK
```

Thus an event can legitimately satisfy:

```text
D_track <= M_MARGIN
but
e_anchor > T_POS_RISE
```

and still be classified as a droop alarm candidate. This is the intended mechanism for preserving weak/short RISE droop sensitivity even after the benign-drift reference has moved.

The numerical values of `T_TRACK`, `B_TRACK`, `M_MARGIN`, exact alarm persistence, production `T_POS_RISE`, and trusted security-anchor rebase semantics remain signoff parameters. Their eventual implementation must preserve the dual-reference separation and signed-alarm priority.

## 5. Evidence basis for the signed-error comparator and dual-reference requirement

The signed-error comparator is frozen into ARCH1 because it has independent retained-data support across two weak-response dimensions. The dual-reference source policy is frozen because a later retained-data audit showed that directly coupling that comparator to `M_REF_TRACK` makes the signed decision fragile to tracker displacement.

### 5.1 D01 amplitude-sensitivity evidence

The frozen signed-error audit evaluated startup-reference signed error before `abs()` using retained BFE8/BFE9/BFE10 data:

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

BFE11 held droop depth at 60 mV and shortened the full-depth dwell from D02 3.0 ns to D04 0.6 ns. Formal ARCH0 produced:

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

### 5.3 BFE12 SIGN0 RTL evidence

BFE12 implemented the positive RISE signed comparator as a research-candidate RTL fork while leaving authoritative ARCH0 and the frontend unchanged. Retained replay reproduced the frozen shadow result:

```text
D01: ARCH0 22/30 -> SIGN0 30/30 at T_POS 18 and 19
D02: ARCH0 30/30 -> SIGN0 30/30 at T_POS 18 and 19
D04: ARCH0 24/30 -> SIGN0 30/30 at T_POS 18 and 19
healthy held-out FPR remained 1/240
healthy signed-RISE additions remained 0/360
no ARCH0 attack HIT was lost
```

The signed and absolute alarm requests share the existing output stage; BFE12 did not implement the tracker and did not freeze a production `T_POS_RISE`.

Authority:

`delay_chain/ftc/analysis/b_fe_frontend/bfe12_arch1_sign0_signed_droop_rtl/`

Gate: `BFE12_ARCH1_SIGNED_DROOP_COMPARATOR_RTL_FROZEN`

### 5.4 Tracking-reference interaction audit and Policy-B freeze

The retained-data-only reference-interaction audit evaluated hypothetical tracker displacement

```text
DeltaR = M_REF_TRACK - M_REF_STARTUP
```

using 360 healthy RISE samples plus 30 D01, 30 D02, and 30 D04 targets. It compared three reference-source policies without any new simulation or threshold tuning.

For direct coupling of the signed comparator to `M_REF_TRACK` (Policy A), the integer safe displacement interval was only:

```text
T_POS=18: DeltaR in [0,1]
T_POS=19: DeltaR in [-1,0]
```

where safety required zero healthy positive false alarms and 30/30 signed detection for D01, D02, and D04.

Using the startup/trusted anchor for the signed branch (Policy B) made the retained signed metrics invariant to hypothetical tracker displacement across the common analyzed representable range. Exact threshold compensation (Policy C) was algebraically equivalent but added threshold arithmetic/encoding/saturation contracts and was therefore retained only as a fallback comparison.

The audit recommendation is therefore frozen into this architecture:

```text
TRACK / ABS source:      M_REF_TRACK
SIGNED DROOP source:     M_REF_SECURITY_ANCHOR
ordinary tracker update: must not modify M_REF_SECURITY_ANCHOR
```

The analyzed representable `DeltaR` range is **not** an authorization for the tracker to move by that amount; actual `B_TRACK` remains a separate future signoff parameter.

Authority:

`delay_chain/ftc/analysis/b_fe_frontend/arch1_signed_tracking_reference_interaction_audit/`

Gate: `ARCH1_SIGNED_TRACKING_REFERENCE_INTERACTION_AUDIT_FROZEN`

These results justify freezing both the **presence of the signed-error droop comparator** and the **dual-reference source policy** into ARCH1. They do not freeze 18 or 19 as silicon/PVT-signoff threshold values. BFE13 now provides a minimal TRACK0 research-candidate RTL implementation and validates its digital/event-atomic mechanics; it does not establish real benign-drift efficacy or production readiness.

## 6. Frozen safety gate concept

A runtime tracking-reference update is permitted only if all candidate safety conditions are satisfied. The exact Boolean implementation is deferred, but future logic must preserve at least:

```text
TRACK_UPDATE_ALLOWED =
    event_valid
    && CAL_LOCK
    && track_reference_valid
    && security_anchor_valid
    && !ABS_ALARM
    && !SIGNED_DROOP_ALARM
    && no_pending_or_confirmed_alarm
    && no_untrusted_transition_context
    && error_is_inside_track_region
    && temporal_vote_accepts_same_signed_small_e_track
    && startup_anchor_budget_not_exceeded
```

The explicit `!SIGNED_DROOP_ALARM` term is an architectural requirement. A RISE excursion that meets the anchor-referenced signed droop rule must never be consumed as a normal tracking sample simply because `D_track` remains below the inherited absolute margin.

Ordinary `TRACK_UPDATE_ALLOWED` authorizes changes to `M_REF_TRACK` only. It does **not** authorize changes to `M_REF_SECURITY_ANCHOR`.

## 7. Startup-anchor drift budget

To prevent a slow malicious voltage reduction from being absorbed indefinitely, the mutable runtime tracking reference remains inside a bounded neighborhood of the trusted startup/anchor policy unless trusted system control explicitly authorizes a new operating point:

```text
abs(M_REF_TRACK - trusted_tracking_anchor) <= B_TRACK
```

For the initial candidate, `trusted_tracking_anchor` is derived from startup calibration. `B_TRACK` remains a future programmable/signoff parameter. Reaching the bound must stop further unauthenticated tracking movement in that direction. A later policy may raise maintenance, drift-limit, or alarm status.

The signed droop comparator uses its separate security anchor, so ordinary movement of `M_REF_TRACK` cannot by itself drag the signed droop decision baseline. This separation does not eliminate the need for a tracking drift bound; the two mechanisms protect against different failure modes.

## 8. Trusted operating-point context and security-anchor rebase

A future chiplet may legitimately alter voltage/frequency through AVS/DVFS. `M_FF` alone cannot distinguish a legal operating-point transition from an attacker producing the same observed trajectory. ARCH1 therefore reserves trusted safe-domain context such as:

```text
OPP_CHANGE_VALID
REBASE_AUTH
OPP_PROFILE_ID
```

Authorization to exceed the ordinary tracking drift budget or establish a new trusted baseline must originate from trusted power-management/system context rather than from the sensor stream itself.

A future implementation may use separate reference/threshold profiles per authorized OPP or a trusted rebaseline sequence. The exact protocol is deferred. What is frozen now is the authority boundary:

```text
autonomous fine-step tracker
    -> may update M_REF_TRACK only

trusted REBASE_AUTH / trusted profile transition
    -> may, under a later validated contract, establish or select
       a new M_REF_SECURITY_ANCHOR
```

`M_REF_STARTUP_RISE/FALL` remain immutable audit provenance even if a future trusted service policy selects a different authorized security anchor.

## 9. Why ARCH1 keeps both references and both alarm branches

The signed branch is not intended to replace the absolute detector, and the security anchor is not intended to replace the tracking reference.

The mutable tracking reference serves benign-drift tolerance:

```text
small safe persistent e_track
    -> no alarm
    -> temporal vote + safety gate
    -> +/-1 LSB M_REF_TRACK update
```

The inherited absolute detector remains useful for excursions relative to the current tracked operating point:

```text
large |e_track|
    -> D_track > M_MARGIN
    -> ABS_ALARM
```

The trusted security anchor preserves the weak/short droop discriminator against ordinary tracker motion:

```text
weak/short evidence-backed RISE droop
    -> e_anchor > T_POS_RISE
    -> SIGNED_DROOP_ALARM
```

The effective detector keeps both alarm sources:

```text
ABS_ALARM || SIGNED_DROOP_ALARM -> ALARM -> freeze M_REF_TRACK
```

The monitored stream is never allowed to teach the detector to continuously widen its own acceptance window or autonomously move the security anchor.

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
immutable startup provenance
+ separate mutable fine-step tracking reference
+ separate trusted security anchor
+ temporal voting
+ fixed absolute alarm window
+ security-anchor signed-error droop comparator
+ alarm-priority tracker freeze
+ trusted OPP/rebase authorization
```

The signed comparator is a project-derived extension supported by the frozen D01 signed-separability audit, D04 cross-duration generalization, and BFE12 research RTL replay. The **dual-reference source policy** is a further project-specific conclusion from the frozen reference-interaction audit. Their presence is now frozen; production thresholds, tracker parameters, trusted rebase mechanics, and full operating-range signoff remain future validation tasks.

## 11. Required validation before promotion

A successor validation stage must compare frozen ARCH0 against the updated ARCH1 candidate without changing the physical frontend/capture path.

At minimum it must cover:

1. **slow benign drift:** bounded fine-step tracking reduces harmless tracking-reference error/false-alarm pressure relative to ARCH0;
2. **D01-like shallow droop:** the security-anchor signed comparator retains the validated weak-amplitude benefit while `M_REF_TRACK` moves;
3. **D04-like short droop:** the security-anchor signed comparator retains the validated short-duration benefit while `M_REF_TRACK` moves;
4. **sudden strong droop:** the combined absolute + signed detector remains functional and a real fast excursion is not learned away;
5. **slow unauthorized droop:** tracking bound and alarm/hold priority prevent indefinite baseline poisoning;
6. **tracker/security-anchor isolation:** ordinary tracker updates change `M_REF_TRACK` only and never change the security anchor;
7. **trusted authorized voltage/OPP transition:** any enlarged tracking/rebaseline or security-anchor update occurs only when trusted authorization is asserted;
8. **trusted rebase interaction:** if a later stage implements security-anchor rebase, signed sensitivity and false-alarm behavior must be re-established for the authorized profile;
9. **polarity scope:** characterize FALL behavior before enabling any FALL signed comparator rule.

Promotion requires evidence that ARCH1 improves benign-drift tolerance and preserves weak/short droop sensitivity without reducing relevant strong-droop sensitivity, materially worsening healthy false alarms, or allowing an attacker to drag either the tracking reference beyond its budget or the security anchor through autonomous observation.

## 12. Candidate backend-visible state

The following state/signals are reserved conceptually for a future implementation; exact RTL names and widths are not frozen unless inherited from ARCH0:

- inherited `q_ff[29:0]`
- inherited `M_FF[8:0]`
- inherited `event_valid`
- inherited `edge_pol`
- inherited startup calibration state and `CAL_LOCK`
- immutable `M_REF_STARTUP_RISE`
- immutable `M_REF_STARTUP_FALL`
- mutable `M_REF_TRACK_RISE`
- mutable `M_REF_TRACK_FALL`
- trusted `M_REF_SECURITY_ANCHOR_RISE`
- trusted `M_REF_SECURITY_ANCHOR_FALL`
- signed `e_track = M_FF - M_REF_TRACK`
- `D_track = abs(e_track)`
- signed `e_anchor = M_FF - M_REF_SECURITY_ANCHOR`
- inherited/fixed-programmable `M_MARGIN_RISE/FALL`
- `T_POS_RISE` or equivalent RISE signed-droop threshold representation
- future polarity-specific signed threshold/state only after characterization
- `SIGNED_DROOP_ALARM`
- `ABS_ALARM`
- combined alarm request before tracker update acceptance
- `T_TRACK_RISE/FALL`
- `B_TRACK_RISE/FALL`
- `e_track` direction/persistence state
- temporal vote/persistence state
- track freeze/enable state
- optional trusted `OPP_CHANGE_VALID` / `REBASE_AUTH` / profile context

## 13. Explicitly deferred / not authorized by this freeze

This candidate freeze does **not** authorize or decide:

- production RTL implementation of the complete ARCH1 architecture;
- final numerical `T_POS_RISE` value, despite retained-data candidates 18/19;
- FALL signed comparator polarity/direction/threshold;
- final `T_TRACK`, `B_TRACK`, or inherited `M_MARGIN` values;
- exact K-of-N/majority/persistence parameters;
- EWMA coefficients or two-timescale estimators;
- adaptive `M_MARGIN` learning;
- final DVFS/AVS/OPP protocol;
- exact trusted security-anchor rebase/update sequence;
- number or organization of OPP reference/security-anchor/threshold banks;
- background recalibration frequency;
- final alarm debounce/persistence policy;
- PVT/silicon signoff ranges;
- physical Level-0 crossing implementation;
- any modification to sensor path, latch aperture, DFF timing, tap structure, or raw-code semantics;
- `N=sum(q)`, LUT/ML classifiers, broad spatial-feature expansion, or clock-glitch feature fusion unless later evidence shows the current architecture is insufficient.

The important distinction is: **the signed-error droop comparator and its default startup/trusted security-anchor source are no longer deferred, and a minimal TRACK0 research RTL candidate now exists; exact production parameters, trusted rebase mechanics, benign-drift efficacy, and signoff remain deferred.**

## 14. Freeze statement

`B-FE5-ARCH1-CANDIDATE` is frozen as the preferred future research architecture with two required backend capabilities and a dual-reference authority boundary:

```text
(1) startup-initialized, fine-step, temporally filtered,
    safety-gated, bounded background tracking using M_REF_TRACK

AND

(2) a signed-error droop comparator using M_REF_SECURITY_ANCHOR,
    in parallel with the inherited absolute-error alarm,
    with alarm priority over any M_REF_TRACK update
```

Ordinary runtime tracking may move `M_REF_TRACK` but may not move `M_REF_SECURITY_ANCHOR`. The initial security anchor is established from trusted startup calibration. Any future security-anchor rebase requires trusted system authorization and a separately validated policy.

For the currently characterized RISE droop direction, the evidence-backed candidate form is `e_anchor > T_POS_RISE`; retained D01/D04 evidence identifies 18/19 as diagnostic candidates but does not yet freeze either as the production threshold.

Until an integration/validation stage explicitly promotes this architecture, `B-FE5-ARCH0` remains the authoritative production implementation contract.

Candidate tag: `BFE5_ARCH1_DUAL_REFERENCE_GATED_FINE_TRACK_SIGNED_DROOP_CANDIDATE_FROZEN`

## BFE12 SIGN0 evidence cross-reference

The required positive RISE signed-error comparator has a validated SIGN0 research RTL implementation and retained-data replay gate in:

`delay_chain/ftc/analysis/b_fe_frontend/bfe12_arch1_sign0_signed_droop_rtl/BFE12_SIGN0_GATE.json`

BFE12 used the startup/frozen reference because the tracker was not implemented. This remains consistent with the security-anchor source role. The cross-reference does not promote the complete ARCH1 architecture; the fine-step tracker and all production/PVT threshold decisions remain deferred.

## BFE13 TRACK0 status cross-reference

`delay_chain/ftc/analysis/b_fe_frontend/bfe13_arch1_track0_rtl/BFE13_TRACK0_GATE.json`
records `BFE13_ARCH1_TRACK0_RTL_FROZEN` with a PASS classification for the
minimal dual-reference, event-atomic TRACK0 research candidate. BFE13 validates
the digital tracker mechanics only. Real benign-temperature efficacy,
slow-attack poisoning robustness, trusted OPP/rebase behavior, production
parameters, PVT/silicon signoff, and promotion over authoritative ARCH0 remain
deferred.

## Reference-interaction evidence cross-reference

The dual-reference source policy is supported by:

`delay_chain/ftc/analysis/b_fe_frontend/arch1_signed_tracking_reference_interaction_audit/REFERENCE_INTERACTION_REPORT.md`

Gate: `ARCH1_SIGNED_TRACKING_REFERENCE_INTERACTION_AUDIT_FROZEN`

That audit freezes Policy B as the preferred next-stage direction: `M_REF_TRACK` for tracking/absolute-error behavior and startup/trusted `M_REF_SECURITY_ANCHOR` for the signed droop comparator. It does not implement the tracker, select a new `T_POS_RISE`, or authorize any particular security-anchor rebase protocol.
