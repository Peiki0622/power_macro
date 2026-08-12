# FTC Reference Sensitivity Contrast Feasibility

This report measures reference-only HSPICE paths with local HSPICE W-2024.09. Existing tap29 evidence is read-only and no sensor campaign is rerun.

## Decision

**CONDITIONAL**

## Candidate results

| Candidate | V0 (V) | E_T max (ps) | E_V 50 mV (ps) | E_V 100 mV (ps) | M_50 (ps) | M_100 (ps) |
|---|---:|---:|---:|---:|---:|---:|
| buf_rvt | 1.10 | 10.783 | 8.863 | 23.452 | -1.919 | 12.669 |
| buf_rvt | 0.90 | 53.496 | 29.290 | 85.543 | -24.206 | 32.047 |
| mux_rvt | 1.10 | 9.573 | 5.167 | 17.697 | -4.405 | 8.124 |
| mux_rvt | 0.90 | 41.031 | 28.048 | 70.676 | -12.983 | 29.645 |
| inv_rvt | 1.10 | 8.045 | 3.464 | 19.920 | -4.581 | 11.875 |
| inv_rvt | 0.90 | 34.553 | 29.876 | 81.223 | -4.676 | 46.671 |
| nand2_rvt | 1.10 | 8.079 | 4.063 | 16.631 | -4.016 | 8.552 |
| nand2_rvt | 0.90 | 36.710 | 32.523 | 89.886 | -4.187 | 53.176 |
| nor2_rvt | 1.10 | 19.378 | 4.049 | 11.897 | -15.329 | -7.481 |
| nor2_rvt | 0.90 | 34.855 | 25.926 | 71.546 | -8.929 | 36.691 |
| buf_lvt | 1.10 | 8.410 | 13.492 | 37.737 | 5.082 | 29.326 |
| buf_lvt | 0.90 | 48.974 | 50.993 | 153.617 | 2.019 | 104.643 |
| mux_lvt | 1.10 | 8.233 | 10.761 | 31.261 | 2.528 | 23.028 |
| mux_lvt | 0.90 | 55.115 | 53.161 | 146.862 | -1.954 | 91.747 |
| inv_lvt | 1.10 | 7.769 | 11.326 | 32.140 | 3.556 | 24.371 |
| inv_lvt | 0.90 | 55.673 | 64.398 | 158.212 | 8.725 | 102.540 |
| nand2_lvt | 1.10 | 9.400 | 12.238 | 32.569 | 2.839 | 23.169 |
| nand2_lvt | 0.90 | 55.706 | 57.420 | 142.555 | 1.713 | 86.848 |
| nor2_lvt | 1.10 | 7.124 | 8.597 | 26.824 | 1.473 | 19.700 |
| nor2_lvt | 0.90 | 57.844 | 57.410 | 143.655 | -0.434 | 85.811 |

## Required answers

1. **Single-cell reference quantum:** 有 functionally verified single-cell candidate.
2. **Smallest composite:** 不需要或未找到.
3. **Local margins:** see the candidate table above for both 1.10 V and 0.90 V M_50/M_100.
4. **Per-process temperature tracking:** see `finalist_pvt_confirmation.csv`; each row compares calibrated residual with raw sensor movement.
5. **Next stage:** 本阶段不支持直接进入最小可编程参考延迟线.

## Provenance

- Measured evidence: reference candidate HSPICE D_R rows under the task-owned run directory.
- Reused evidence: frozen tap29 `fine.csv`, temperature screen, and TT/FF/SS PVT matrix.
- Analysis-only: continuous k; it is not a hardware unit count and does not implement self-calibration.
- Future inference: no bypass network, FSM, detector, or P&R is implemented here.
