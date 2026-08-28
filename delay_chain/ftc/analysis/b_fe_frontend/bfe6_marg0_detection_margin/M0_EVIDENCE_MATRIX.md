# B-FE6-MARG0 M0 evidence matrix

Gate: `BFE6_MARG0_M0_EVIDENCE_AUDIT_READY`

No HSPICE, PrimeSim, VCS, or DC invocation was made. Historical source artifacts were only read and hashed.

CALN0 provides 30 paired RISE process instances at healthy 0.95 V and droop 0.92 V. VD1 provides single-instance RISE amplitude points at 0.95/0.92/0.89/0.86 V.

CALN0 raw XA CSVs also contain four healthy FALL captures for all 30 seeds. They close the healthy FALL population, but no same-seed FALL droop population is retained; FALL per-chip D_M therefore still needs droop evidence.

| Edge | VDD (V) | Seeds | Calibration | Normal | Droop | Per-chip D_M without rerun |
|---|---:|---:|---|---|---|---|
| RISE | 0.95 | 30 | population_30_seed | population_30_seed | population_30_seed | True |
| RISE | 0.92 | 30 | population_30_seed | population_30_seed | population_30_seed | True |
| RISE | 0.89 | 1 | single_instance_only | single_instance_only | single_instance_only | False |
| RISE | 0.86 | 1 | single_instance_only | single_instance_only | single_instance_only | False |
| FALL | 0.95 | 30 | population_30_seed_from_retained_raw_XA | population_30_seed_from_retained_raw_XA | absent | False |
| FALL | 0.92 | 1 | absent | single_instance_only | absent | False |
| FALL | 0.89 | 1 | absent | single_instance_only | absent | False |
| FALL | 0.86 | 1 | absent | single_instance_only | absent | False |

The full immutable-input inventory and SHA-256 values are in `M0_EVIDENCE_MATRIX.json`.
