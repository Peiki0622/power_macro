# FTC Two-Stage Real-DFF Hierarchical Calibration

## Decision

**Two-Stage Real-DFF Hierarchical Self-Calibration = GO**

## Frozen Inputs

- Historical fine waveform, path-selection medium, real-XOR, minimal real-DFF, and static-calibration evidence was read only; none of their HSPICE campaigns was rerun.
- Driver/load/K: `BUF_X0P8M_A9TL40` / `NOR2_X4A_A9TL40__signal_A` / `10`; medium: N=16 `BUF_X0P7M_A9TL40` / `MXT2_X0P5M_A9TL40`.
- Static integration is `GO`: tap29/XOR/DFF and the approved medium/fine cells are retained without threshold tree, bypass, config-skip, ideal delay, or ideal capacitor.
- All historical rerun counters are zero.

## Q Read Contract

- `q_read_time_s = 3.3e-09` and `q_settle_s = 2e-10`; the next sensor/XOR event is at 7e-09 s.
- 3 ns was not reused because the retained 0.80 V projection needs 3.2552261910000005e-09 s before the settled Q read.

## Per-Voltage Result

| VDD (V) | Status | Coarse Q | M transition | Fine Q | F lock |
|---:|---|---|---:|---|---:|
| 0.95 | GO | 11111100000000000 | 6 (M fine 5) | 10000000000 | 1 |
| 1.10 | GO | 11110000000000000 | 4 (M fine 3) | 11110000000 | 4 |
| 0.80 | GO | 11111111100000000 | 9 (M fine 8) | 10000000000 | 1 |

All coarse and fine `D_code_ps` sequences are strictly increasing, each Q sequence has exactly one `1→0`, every CK satisfies the 200 ps settle rule, every `W_xor_ps` is positive, and no Q is ambiguous.
K=10 remains sufficient because the three `F_lock` values are within 1..10. `D_minus_W_ps` is analysis-only and does not replace the real DFF Q decision.

## Accounting and Scope

- New integrated HSPICE scenarios: 84; reused new-task scenarios in this publication: 84.
- This is not a complete FTC droop macro GO: bypass, configuration skip, programmable margin, droop detection, PVT, RTL, and layout remain outside this task.
