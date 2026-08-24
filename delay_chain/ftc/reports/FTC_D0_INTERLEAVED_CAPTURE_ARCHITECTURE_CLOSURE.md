# FTC D0-BR 合法捕获与交错架构闭合

## 最终 Gate

**SHARED_SENSOR_CADENCE_FAIL**。BR1 已在两个正式 T0 L2 / 3002 ps target 点直接检查共享 RVT/LVT/XOR/medium/fine sensing path 的 2075 ps re-arm；该 Gate 在任何 pulse legalizer、capture bank 或 D0 runtime RTL 之前执行。

## 结论边界

- D0-A 的窄 raw `dff_ck` 根因和 T0 的 2075 ps / 100% CLEAN_Q1 要求均未修改。
- 本轮只执行 BR1 允许的两项 task-owned sensor-only HSPICE diagnostics；未重跑 M0、T0、H0、M1、RF 或 XA。
- capture-bank-only 不能隐藏 sensing path 自身的 re-arm 限制，因此本计划在 BR1 正确终止；后续必须另立 multi-sensor-lane interleave 计划。

## BR1 物理观测

- `br1_0p95_l2_repeated_sensor`: medium=3, raw_ck=3, xor=3; D_ref0/D_ref1=495.249981 / 496.249353 ps。
- `br1_1p10_l2_repeated_sensor`: medium=2, raw_ck=2, xor=3; D_ref0/D_ref1=324.726837 / 325.294157 ps。

`P_sensor_verified_ps` 仍为 `null`：本轮只证明 2075 ps 不可用，没有执行未经授权的更长周期搜索。因此也不能把 `N_sensor_min` 写成一个伪精确数字。
