# FTC Minimal Programmable Threshold Pulse Comparator

## Decision

**GO**

## Required Answers

1. 真实标准单元可编程 delay 是否产生单调 `D(code)`？是。
2. 真实 DFF 是否实现 `W_S_int > D(code)` 的 1-bit 脉宽比较？是，除相邻翻转 code 外均与时间关系一致。
3. 这个硬件 primitive 是否足以进入下一阶段的 static self-calibration？是。

## Per-VDD Evidence

| VDD (V) | D 单调 | 脉宽 bracket | 时间边界对 | Boundary 外 Q 一致 |
|---:|---:|---:|---|---:|
| 1.10 | 1 | 1 | 2->3 | 1 |
| 0.90 | 1 | 1 | 5->6 | 1 |

## Gate Reason

- all two-VDD monotonic threshold and DFF comparison gates passed
