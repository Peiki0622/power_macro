# FTC D0-A 运行时快路径架构闭合

## 最终 Gate

**ARCHITECTURE_ESCALATION_REQUIRED**。D0-A 保留 D0-0 的 `ARCHITECTURE_REVIEW` 和 T0 的 `CONDITIONAL_GO`：T0 的 2075 ps、两个正式 L2/3002 ps 威胁及 100% CLEAN_Q1 全相位要求均未被修改。

## 已完成的最小取证

- A0 绑定 D0-0、T0、M0、M1、PD1 和 RF 权威输入；没有修改冻结合同或 runtime RTL。
- A1 重解析 91 个 M0 与 515 个 T0 retained listing，并确认没有 `.tr0` 波形；仅运行两点正式 target single-probe 诊断，补齐 CK fall/high-width、Q 90%、reset-clear 和路径 falling observability。
- A2 将真实 target CK 高宽与 RF cell timing check 合并。2075 ps 周期扣除 1.0 ns CK-high 与 1.0 ns CK-low 只余 75 ps，无法保留既有 250 ps/half-cycle guard，因此单通道为 `SENSOR_CLOCK_OR_RECOVERY_LIMITED`，根因为 `measured_dff_ck_high_width_violates_formal_cell_minimum`。
- A5 没有复制 sensor 或实现 bank；仅给出 2500 ps guarded-model lane 下界和 `N_min=2` 的后续评审起点。`P_lane_verified` 仍为未闭合，不能把这个模型数值写成物理完成结论。

本轮 HSPICE=2，均为容器内 task-owned A1 诊断；没有重跑 T0-2/T0-3/T0-4/T0-5、M0、H0、M1、RF 或 XA。下一步已限定为[独立 D0-B 两 capture bank/交错架构计划](../../../plans/ftc_d0b_interleaved_capture_architecture_plan.md)：先量化新增 D/CK 负载、合法 capture 脉冲、独立 reset/re-arm 与 M/F 共享，再允许实现。
