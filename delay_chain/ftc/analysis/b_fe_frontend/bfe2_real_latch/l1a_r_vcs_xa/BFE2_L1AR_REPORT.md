# B-FE2-L1A-R report

Gate: `BFE2_L1AR_REAL_SAFE_LATCH_PASS`

VCS W-2024.09 + PrimeSim XA W-2024.09; frozen B-FE2.2C 0.95 V normal and 0.95->0.86 V L2 only.
`sample_close=534.524618567 ps`, launch=1000 ps, therefore fixed `G close=1534.524618567 ps`.
`VDD_SAFE=VNW=0.95 V`, `VPW=VSS=0 V`; latch=`LATQ_X0P5M_A9TR40`; Level-0 rule has no delay/slew/hysteresis/X-region.

| Scenario | Final Q code | Ones | Source-free re-flip | Post-close safe_d changed Q | Unresolved | Mid-rail | Tail unstable |
|---|---|---:|---|---|---|---|---|
| BFE2L-095-N | `000000000000001111111111111100` | 14 | [] | [] | [] | [] | [] |
| BFE2L-095-L2 | `000000000011111111111110000000` | 13 | [] | [] | [] | [] | [] |

Hamming distance: `9` (required >=9).

Initial-state audit: normal mismatches=[], L2 mismatches=[].

Normal tap27: final=0.949999698 V, pre-close safe_d crossings=[{'direction': 'rise', 'logic_state': 1, 'time_ps': 1498.554093337465}], post-close safe_d crossings=[{'direction': 'fall', 'logic_state': 0, 'time_ps': 1884.3530407008059}], post-close Q events=[].
L2 tap27: final=0.000000157 V, pre-close safe_d crossings=[], post-close safe_d crossings=[{'direction': 'rise', 'logic_state': 1, 'time_ps': 1604.1746510777702}, {'direction': 'fall', 'logic_state': 0, 'time_ps': 2167.020435370153}], post-close Q events=[].

Tap24-29 normal post-close safe_d crossings: [[{'direction': 'fall', 'logic_state': 0, 'time_ps': 1797.7416503691989}], [{'direction': 'fall', 'logic_state': 0, 'time_ps': 1826.6136105968837}], [{'direction': 'fall', 'logic_state': 0, 'time_ps': 1855.4621123216318}], [{'direction': 'fall', 'logic_state': 0, 'time_ps': 1884.3530407008059}], [{'direction': 'fall', 'logic_state': 0, 'time_ps': 1913.0957133896695}], [{'direction': 'fall', 'logic_state': 0, 'time_ps': 1939.4632597447746}]].
Tap24-29 L2 post-close safe_d crossings: [[{'direction': 'rise', 'logic_state': 1, 'time_ps': 1540.6922521768247}, {'direction': 'fall', 'logic_state': 0, 'time_ps': 2050.377435532154}], [{'direction': 'rise', 'logic_state': 1, 'time_ps': 1561.7278107859815}, {'direction': 'fall', 'logic_state': 0, 'time_ps': 2089.138220968705}], [{'direction': 'rise', 'logic_state': 1, 'time_ps': 1582.992309819965}, {'direction': 'fall', 'logic_state': 0, 'time_ps': 2128.263942830317}], [{'direction': 'rise', 'logic_state': 1, 'time_ps': 1604.1746510777702}, {'direction': 'fall', 'logic_state': 0, 'time_ps': 2167.020435370153}], [{'direction': 'rise', 'logic_state': 1, 'time_ps': 1625.419238163655}, {'direction': 'fall', 'logic_state': 0, 'time_ps': 2206.1439160660266}], [{'direction': 'rise', 'logic_state': 1, 'time_ps': 1643.276388426368}, {'direction': 'fall', 'logic_state': 0, 'time_ps': 2241.745180514711}]].

Capture classification: `PASS`; spatial classification: `PASS`.

The independent L1A-R stage stops here regardless of Gate outcome; no close, geometry, or later-stage interface is authorized.
