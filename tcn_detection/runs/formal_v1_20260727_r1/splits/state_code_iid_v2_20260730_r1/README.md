# IID repartition evidence

- Policy: `state_code_iid_v2_20260730_r1`
- Source corpus SHA256: `d566f2978188c793012bc39e6cb56a3c4de7f35d67dc603bcefa2e5e74f45899`
- Published corpus SHA256: `029ad57b410210b1f5b27ca75aa70569634c82a6791113b52affe7a10a686875`
- Assignment SHA256: `b21e59d04d969458a67e1867e18f998db6eb0e35c79de490173987e7aa4f686b`
- Connected components: 212
- OOD split retained: no
- Pristine blind-test claim: no (prior trace-level results were viewed)

| Split | Traces |
|---|---:|
| train | 144 |
| validation | 48 |
| iid_test | 48 |

| Acceptance check | Observed | Limit | Result |
|---|---:|---:|---|
| Current-state proportion deviation | 0.000025000 | 0.010000000 | PASS |
| Supported-stratum proportion deviation | 0.016666667 | 0.050000000 | PASS |
| Repeated assignment digest | `b21e59d04d969458a67e1867e18f998db6eb0e35c79de490173987e7aa4f686b` | identical twice | PASS |

The IID holdout is frozen for one final evaluation after all model and
post-processing choices are selected using training and validation only.
