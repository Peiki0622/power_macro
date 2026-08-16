# FTC Programmable Acceptance Window

## Decision

**Programmable Acceptance Window = NO-GO**

- Current 3-bit Mapping: **NOT_READY**

## Required Answers

1. `C_lock + M` 的真实 DFF acceptance-window 机制是否成立？否。
2. `M=1` 和 `M=2` 分别对应多大的静态 droop trip depth？见下表。
3. 当前 `[10,12,14,16,18,36,37,38]` mapping 的安全分辨率是否足够？否。
4. 下一阶段是进入 PVT detector verification，还是先做一次窄的 delay-code refinement？本阶段停止，不增加 monitor RTL。

## Trip Map

| V0 (V) | C_lock | M | C_alarm | Status | V_trip (V) | Trip depth (mV) |
|---:|---:|---:|---:|---|---:|---:|
| 0.85 | 5 | 1 | 6 | NO_IN_RANGE_TRIP |  |  |
| 0.85 | 5 | 2 | 7 | NO_IN_RANGE_TRIP |  |  |
| 0.90 | 5 | 1 | 6 | NO_IN_RANGE_TRIP |  |  |
| 0.90 | 5 | 2 | 7 | NO_IN_RANGE_TRIP |  |  |
| 0.95 | 5 | 1 | 6 | NO_IN_RANGE_TRIP |  |  |
| 0.95 | 5 | 2 | 7 | NO_IN_RANGE_TRIP |  |  |
| 1.00 | 5 | 1 | 6 | NO_IN_RANGE_TRIP |  |  |
| 1.00 | 5 | 2 | 7 | NO_IN_RANGE_TRIP |  |  |
| 1.05 | 4 | 1 | 5 | NO_IN_RANGE_TRIP |  |  |
| 1.05 | 4 | 2 | 6 | NO_IN_RANGE_TRIP |  |  |
| 1.10 | 4 | 1 | 5 | NO_IN_RANGE_TRIP |  |  |
| 1.10 | 4 | 2 | 6 | NO_IN_RANGE_TRIP |  |  |

## Gate Evidence

- M=1 has no in-range trip at 0.85V, 0.90V, 0.95V, 1.00V, 1.05V, 1.10V
