# FTC Dynamic Startup Calibration Protocol

## Decision

**Dynamic Startup Calibration Protocol = NO-GO**

## Accounting

1. Upstream 84 static scenarios were read only; all upstream rerun counters are zero.
2. New continuous HSPICE scenarios: 3 of the allowed 3; reused: 3.
3. The only topology difference is DC M/F rails replaced by single-bit PWL testbench rails; no hardware cell or signal path changed.
4. M/F PWL changes only control state over time, so the same physical delay cells, loads, sensor, XOR, and DFF remain in the circuit.

## Timing and Windows

5. q-read offset is 2.300 ns from the historical 1.0 ns launch to 3.3 ns read; Q settle is 0.200 ns; code-settle is 1.500 ns; recovery is 2.500 ns, all derived from retained evidence.
6. S_CLK fall occurs after reset reassertion; its functional return activity is therefore audited separately from code-update quiet activity.

## Dynamic Results

| VDD | Status | Coarse Q | Fine Q | Hold Q | Final (M,F) |
|---:|---|---|---|---|---:|
| 0.95 | GO | 1111110 | 10 | [0] | (5,1) |

7. 0.95 V trajectory: p0 M0 F0 Q1 launch=2.000ns; p1 M1 F0 Q1 launch=9.510ns; p2 M2 F0 Q1 launch=17.020ns; p3 M3 F0 Q1 launch=24.530ns; p4 M4 F0 Q1 launch=32.040ns; p5 M5 F0 Q1 launch=39.550ns; p6 M6 F0 Q0 launch=47.060ns; p7 M5 F0 Q1 launch=54.570ns; p8 M5 F1 Q0 launch=62.080ns; p9 M5 F1 Q0 launch=68.080ns
| 1.10 | GO | 11110 | 11110 | [0] | (3,4) |

8. 1.1 V trajectory: p0 M0 F0 Q1 launch=2.000ns; p1 M1 F0 Q1 launch=9.510ns; p2 M2 F0 Q1 launch=17.020ns; p3 M3 F0 Q1 launch=24.530ns; p4 M4 F0 Q0 launch=32.040ns; p5 M3 F0 Q1 launch=39.550ns; p6 M3 F1 Q1 launch=47.060ns; p7 M3 F2 Q1 launch=54.570ns; p8 M3 F3 Q1 launch=62.080ns; p9 M3 F4 Q0 launch=69.590ns; p10 M3 F4 Q0 launch=75.590ns
| 0.80 | NO-GO | 1111111110 | 10 | [0] | (8,1) |

9. 0.8 V trajectory: p0 M0 F0 Q1 launch=2.000ns; p1 M1 F0 Q1 launch=9.510ns; p2 M2 F0 Q1 launch=17.020ns; p3 M3 F0 Q1 launch=24.530ns; p4 M4 F0 Q1 launch=32.040ns; p5 M5 F0 Q1 launch=39.550ns; p6 M6 F0 Q1 launch=47.060ns; p7 M7 F0 Q1 launch=54.570ns; p8 M8 F0 Q1 launch=62.080ns; p9 M9 F0 Q0 launch=69.590ns; p10 M8 F0 Q1 launch=77.100ns; p11 M8 F1 Q0 launch=84.610ns; p12 M8 F1 Q0 launch=90.610ns

## Acceptance Questions

10. Every coarse increment changes one thermometer bit; every transition audit records one bit.
11. Backoff changes one M bit; measured configuration CK edge count is 0 and status is PASS.
12. Every fine increment changes one F control bit; all measured transition statuses are PASS.
13. Dynamic coarse and fine D_code sequences are strictly monotonic for every voltage result.
14. Every reported probe is valid with one measured active CK edge; no extra active CK edge was observed.
15. No q_ambiguous result was observed.
16. Minimum Q-settle margin: 481.42945999998165 ps.
17. Maximum code-update dff_ck quiet peak: 0.0543299 V; minimum quiet margin: 1509.9999999999898 ps.
18. Dynamic lock codes match static references for all three voltages; 0.80 V remains NO-GO because recovery did not finish.
19. A GO would certify only this dynamic protocol, not the real startup-control circuit; this run is NO-GO and therefore grants no downstream authorization.
20. After a future recovery-protocol repair and a new GO, the next stage is real standard-cell control logic; programmable margin remains later.

## Gate Interpretation

- D/W deltas are diagnostic only; no unsupported tolerance was introduced.
- The sole terminal reason is `recovery_window_insufficient`; no hardware rescue, configuration skip, FSM, margin, droop, PVT, RTL, or layout was added.

## Recovery Diagnosis

`recovery_window_insufficient` means that the return activity after an S_CLK falling edge did not settle before the next code-update slot.
The guard is 2.500 ns and was derived from retained upstream timing evidence; at its end and throughout the final 0.200 ns tail, xor_29, medium_out, and dff_ck must each remain below 10% of VDD.
The failing voltage is 0.80 V. Its worst measured recovery endpoint/tail signal was 1.003 x VDD, above the 0.100 x VDD limit. This is functional return-wave activity from the falling clock edge, not a configuration-induced CK edge: all transition audits still report zero configuration CK edges.
The Q reads, coarse/fine monotonicity, lock-hold probes, and code-update quiet windows passed. Therefore this NO-GO identifies an insufficient recovery protocol window only; it does not justify changing the delay-line hardware or adding a margin bypass.

## NO-GO Reasons

- recovery_window_insufficient
