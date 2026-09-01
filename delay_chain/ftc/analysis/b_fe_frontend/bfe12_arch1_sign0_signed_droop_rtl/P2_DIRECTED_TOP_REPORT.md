# BFE12 P2 Directed Full-Top RTL Report

Gate: `BFE12_SIGN0_P2_DIRECTED_TOP_RTL_PASS`

The candidate top was exercised through the unchanged capture bank, weighted
feature pipeline, startup calibration, detector pipeline, and sticky output.
The VCS test passed all required polarity, strict-threshold, invalid-event, and
reset checks.  The recorded cycle table shows E0-to-E7 of seven probe edges for
both signed-only and absolute-only alarms; sticky sets on the following E8 edge.

The signed-only cases have `abs_alarm=0` and `signed_rise_alarm=1`.  The
absolute-only cases use the plan-authorized `T_POS_RISE=435` regression disable
configuration and prove the inherited comparator independently.  No production
RTL, threshold, frontend, or physical evidence was changed.

Artifacts: `p2_directed/compile.log`, `p2_directed/run.log`, and
`p2_directed/P2_DIRECTED_CYCLE_TABLE.csv`.
