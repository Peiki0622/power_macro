# BFE14 P4 dual-reference compatibility audit

Gate: `BFE14_TEMP0_P4_DUAL_REFERENCE_CHARACTERIZED`

The audit treats `e_anchor=M_FF-M_REF_STARTUP_selected` as the fixed security-anchor quantity and does not label it as a post-tracking residual. Only strict RISE comparisons `e_anchor>18` and `e_anchor>19` were evaluated. Margins remain 22/24. The values T_TRACK=5 and B_TRACK=2 are reported only as the BFE13 directed-test probe. Machine-readable per-event values and temperature aggregates are in the accompanying CSV/JSON.

Observed event rows: 1512 (endpoint population plus retained 85 C scout). Conflict location: endpoint_only.

-40 C: signed alarms at 18/19 = 0/0; startup ABS pressure = 223.
85 C scout: signed alarms at 18/19 = 0/0; startup ABS pressure = 0.
125 C: signed alarms at 18/19 = 188/188; startup ABS pressure = 209.

Interpretation classes: SECURITY_ANCHOR_HEALTHY_CONFLICT_OBSERVED, BFE13_TEST_TRACK_WINDOW_TOO_NARROW

Simulation accounting: HSPICE=0, VCS=0.
