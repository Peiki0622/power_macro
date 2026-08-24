# FTC T0-4 瞬态电压跌落纠偏与局部原因排查报告

## 最终判定

**GO**

本轮只修正 T0-4 判门并复用既有 238 个正式场景；未进入 T0-5/T0-6，未修改传感器、H0、M0、M1、冻结 RTL 或电源域合同。

## 判门纠偏

- `last_q0_control` 是略浅于静态触发点的负控制；允许 `minimum_detectable_hold_ps = null`。通过条件是最长已测持续时间仍为稳定 Q0、所有行 valid、无 anomaly、无 Q1 误触发。
- 正式 Q1 点要求 clean-Q1 最短持续时间；遇到 ambiguous 不删除、不平滑、不强制单调，而是保留为 Q0 -> ambiguous -> clean Q1 局部边界。

## 两异常诊断

- 两点的 1 ps 诊断第二动态交叉分别为约 2.7914512985 ns 和 2.2415939837 ns，均落在恢复开始/1 ps 恢复结束沿内。两次动态交叉之间 `dff_ck/VDD_MONITORED` 最小值均为 0.5，未观察到低于门限的稳定低态。
- 10 ps 恢复沿下，两点恢复窗口内第二交叉均消失；全局第二交叉移至约 5.484930567 ns / 5.161889166 ns 的后续正常事件。
- 因此根因是极快恢复沿中的本地 `VDD_MONITORED/2` 动态门限敏感性，不是真实 `dff_ck` 低->高->低->高 二次时钟；两次 Q 采样仍为稳定 Q1。

## 持续时间证据

- 已有 18 个正式 Q1 minimum-duration 结果有效；两个异常锚点分别由相邻 clean 点确定为 1500 ps Q0 -> 1750 ps ambiguous -> 2000 ps clean Q1，以及 1000 ps Q0 -> 1250 ps ambiguous -> 1500 ps clean Q1。
- 6 个负控制点均在最长 3000 ps 测试中稳定 Q0；`minimum_detectable_hold_ps` 保持 null 且判门通过。
- 既有证据中没有 `duration_q1_to_q0_reversal`，不存在大量不可解释的 Q1->Q0 反转。

## 仿真账本与范围

- 正式 238 个 T0-4 场景全部复用，未整体重跑。
- 两异常共 4 个唯一诊断参数场景：每点 1 ps 与 10 ps 恢复沿；由于诊断测量修订保留了前一版证据，task-owned 目录累计 8 次诊断运行，摘要对此明确区分。
- T0-5/T0-6 仍按本轮范围阻塞；不得据此宣称 runtime probe period 或 cadence 已表征。
