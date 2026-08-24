# FTC T0-5 单 probe 时间覆盖进展报告

## 阶段判定

**T0-5 COMPLETE：GO**

所有区间均为已采样相位格点边界；CLEAN_Q1 之外的 Q0 或 ambiguous 区间均不计入保证检测。

| 场景 | 总脉冲 (ps) | CLEAN_Q1 点 | ambiguous 点 | 左/右 Q0 闭合 | 最大非保证窗口 (ps) |
|---|---:|---:|---:|---|---:|
| t0_5a_0p95_l2_boundary | 1456.0 | 4 | 0 | True/True | 225.0 |
| t0_5a_0p95_l2_long | 3002.0 | 12 | 0 | True/True | 2400.0 |
| t0_5a_1p10_l2_boundary | 1190.0 | 4 | 0 | True/True | 225.0 |
| t0_5a_1p10_l2_long | 3002.0 | 13 | 0 | True/True | 2450.0 |
| t0_5b_0p95_l3_recovery | 2002.0 | 19 | 1 | True/True | 225.0 |
| t0_5b_1p10_l1_recovery | 1502.0 | 22 | 1 | True/True | 150.0 |

## 仿真账本

- 本报告覆盖的 T0-5 证据：新增 HSPICE：139；精确复用：0；电气等价 source-hash 复用：46。
- T0-5A 因进程恢复而保留并重解析的既有点：60；本报告唯一物理场景总数：185。
- 未运行 H0、M0、M1、T0-2、T0-3 已有点或 T0-4 全量场景。
- 本阶段未计算 T0-6 cadence；T0-6 是否解封只由当前 Gate 记录。
- 本次 T0-5B：新增 HSPICE：64；复用旧场景：2；精确复用：0；电气等价 source-hash 复用：2。
