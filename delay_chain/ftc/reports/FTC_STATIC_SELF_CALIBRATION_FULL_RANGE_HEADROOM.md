# FTC Static Self Calibration + Full-Range Headroom

## Decision

**Static Self Calibration + Full-Range Code Headroom = GO**

## Required Answers

1. 冻结 3-bit tap mapping 是否覆盖 0.80--1.10 V 的正常工作范围？是。
2. 真实 DFF 驱动的静态自校准是否在每个 VDD 锚点自动找到唯一 C_lock？是。
3. 每个工作点校准后是否至少保留两个更长延迟 code？是。
4. 是否可以进入下一阶段 Programmable Acceptance Window？可以。

## Mapping

- decision: VERIFIED_FOR_0P80_TO_1P10
- taps: [10, 12, 14, 16, 18, 36, 37, 38]
- selection basis: reused_r2_verified_mapping
- new-range minimum mapping claimed: no

## Per-VDD Evidence

| VDD (V) | C_lock | H_up | Decision |
|---:|---:|---:|---|
| 0.80 | 5 | 2 | GO |
| 0.85 | 5 | 2 | GO |
| 0.90 | 5 | 2 | GO |
| 0.95 | 5 | 2 | GO |
| 1.00 | 5 | 2 | GO |
| 1.05 | 4 | 3 | GO |
| 1.10 | 4 | 3 | GO |

## Gate Reason

- all seven normal VDD anchors passed
