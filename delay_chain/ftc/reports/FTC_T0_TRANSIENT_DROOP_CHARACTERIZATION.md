# FTC T0 瞬态电压跌落检测表征报告

## 最终判定

**NO-GO / STOP（停止阶段：T0-2）**

T0-2 的有限斜率长脉冲无法在全部六个正式候选上复现 M0 最近静态 Q0/Q1 bracket。该结果是当前冻结传感器的物理一致性失败，不是通过增加数字逻辑可以掩盖的问题。

## 证据

- M0 原始 `trip_sweep.csv` 被直接读取，没有重新执行静态扫描。
- T0-2 共运行 12 个正式 long-pulse 场景；每个场景均使用当前 medium/fine、真实 tap29 XOR 和真实 DFF 双采样。
- PWL 起点依次检查到 0.5 ns、1 ps 和 1 fs，下降/恢复斜率保持非零；反转仍然存在。
- 失败点保留在 `delay_chain/ftc/runs/t0_transient_droop/`，没有覆盖或删除。

## 禁止越过的阶段

T0-3 相位窗口、T0-4 持续时间边界、T0-5 覆盖率和 T0-6 cadence 均标记为 BLOCKED，未进行新的 HSPICE 扩展。

## D0 下游边界

精确 timing detection 不能扩展到低于 0.80 V；D0 必须为该范围采用 heartbeat、stuck-Q、timeout 或无有效检测结果等失效保护语义。当前没有经过 T0-3 至 T0-6 验证的运行时检测间隔。

## 仿真统计

- 新增 T0 HSPICE 场景（含两次试跑和五轮 T0-2 bracket 复核）：62。
- 复用旧 HSPICE 场景：0。
- 仅重解析旧场景：0。
- 禁止流程新增运行：0。
