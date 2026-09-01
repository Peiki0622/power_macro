# BFE12 ARCH1-SIGN0 Final Report

Final gate: `BFE12_ARCH1_SIGNED_DROOP_COMPARATOR_RTL_FROZEN`

## Result

Classification: `RTL_REPRODUCES_FROZEN_SHADOW`.

The candidate implements only the required pre-ABS positive RISE signed-error
branch.  It reuses the ARCH0 split sign+magnitude subtraction and carries event
polarity and `T_POS_RISE` through the existing E4-to-E7 context pipeline.  The
absolute alarm remains unchanged and is OR-combined with the signed branch at
the existing registered output stage.

## Evidence

- ARCH0 `T_POS_RISE=435` candidate is event-equivalent to ARCH0 over all 690 retained events.
- FALL events for both signed candidates are event-equivalent to ARCH0.
- Healthy held-out FPR is `1/240` for ARCH0, SIGN0@18, and SIGN0@19.
- Healthy signed-audit additions are `0/360` at both thresholds.
- D01 is `22/30` for ARCH0 and `30/30` for both signed candidates.
- D02 is `30/30` for all configurations.
- D04 is `24/30` for ARCH0 and `30/30` for both signed candidates.
- The frozen D01/D04 recovered seed lists match exactly; no ARCH0 HIT was lost.
- P2 cycle evidence confirms E0-to-E7 is seven probe edges and sticky sets on E8.

## Architecture boundary

`bfe_backend_ctrl.sv`, `bfe_backend_top.sv`, `bfe_capture_bank.sv`,
`bfe_m_feature.sv`, and the ARCH0 RTL2 testbench remain authoritative and
unchanged.  `bfe_backend_ctrl_arch1_sign0.sv` and
`bfe_backend_arch1_sign0_top.sv` are research-candidate files only.

The fine-step tracker, runtime adaptation, trusted OPP/rebase handling, FALL
signed rule, production threshold selection, and physical/PVT signoff remain
deferred.  Values 18 and 19 are diagnostic replay configurations, not frozen
production thresholds.
