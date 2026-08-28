# B-FE6-MARG0 M0 evidence matrix

Gate: `BFE6_MARG0_M0_EVIDENCE_AUDIT_READY`

No HSPICE, PrimeSim, VCS, or DC invocation was made. Historical source artifacts were only read and hashed.

CALN0 provides 30 paired RISE process instances at healthy 0.95 V and droop 0.92 V. VD1 provides single-instance RISE amplitude points at 0.95/0.92/0.89/0.86 V.

Retained CLK/VD products provide single-instance FALL observations, but no same-seed FALL droop population; FALL per-chip D_M therefore remains unavailable without new evidence.

| Edge | VDD (V) | Seeds | Calibration | Normal | Droop | Per-chip D_M without rerun |
|---|---:|---:|---|---|---|---|
| RISE | 0.95 | 30 | population_30_seed | population_30_seed | population_30_seed | True |
| RISE | 0.92 | 30 | population_30_seed | population_30_seed | population_30_seed | True |
| RISE | 0.89 | 1 | single_instance_only | single_instance_only | single_instance_only | False |
| RISE | 0.86 | 1 | single_instance_only | single_instance_only | single_instance_only | False |
| FALL | 0.95 | 1 | single_instance_only | single_instance_only | absent | False |
| FALL | 0.92 | 1 | absent | single_instance_only | absent | False |
| FALL | 0.89 | 1 | absent | single_instance_only | absent | False |
| FALL | 0.86 | 1 | absent | single_instance_only | absent | False |

The full immutable-input inventory and SHA-256 values are in `M0_EVIDENCE_MATRIX.json`.
