# M1 programmable detection-margin safe configuration

## Gate decision

**GO** — all required M1-8 checks are true.

## Closed scope

M1 uses the exact 12-entry M0 codebook and legal detection-only F10 (active-low `10'b0000000000`).  It preloads H0's immutable calibration snapshot, lets frozen H0 grant ownership, applies the registered target only with reset high/S_CLK low, and waits one full 2.5 ns controller cycle before `margin_cfg_valid_o`.  No probe, Q decision, alarm, dynamic recalibration, HSPICE, XA, RF6/RF9C/RF9D, or complete calibration rerun belongs to this stage.

## Verification evidence

- RTL/SVA: `delay_chain/ftc/controller/m1_detection_margin/verification/rtl/run/rtl_20260823T001000Z`.
- Mapped+SDF: `delay_chain/ftc/controller/m1_detection_margin/verification/gate_sdf/run/gate_20260823T001200Z`.
- Worst setup slack: 0.001168 ns; worst hold slack: 0.037843 ns.
- Frozen H0 plus six calibration RTL: hash and HEAD-blob checks passed.
- DC LINT observations are documented in `timing/M1_TIMING_SUMMARY.json`; they arise from intentional literal constant rails and do not waive any timing or functional check.

## Downstream handoff

Proceed only to T0 to define the transient threat and detection timing contract.  D0 must later define runtime reset/S_CLK, Q decision, and alarm policy; M1 intentionally leaves the sensor reset and idle.
