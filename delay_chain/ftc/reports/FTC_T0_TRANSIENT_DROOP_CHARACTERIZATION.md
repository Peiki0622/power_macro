# FTC T0 瞬态电压跌落检测能力表征报告

## 最终判定

**NO-GO / STOP（停止阶段：T0-4）**

T0-2 已纠偏通过，T0-3 已证明两个 L2 代表点存在可重复相位窗口；但 T0-4 duration refine 保留了两个 `active_ck_edge_count_not_one` 的 ambiguous 场景。因此六个工作点的完整、可解释 amplitude-duration 合同未闭合，T0-5/T0-6 与 D0 不得继续。

## T0-3 相位窗口

| 基准电压 | 稳定 Q1 窗口（采样格点） | 最大盲区 | 边界分辨率 | ambiguous |
|---:|---|---:|---:|---:|
| 0.95 V | -1000.0..75.0 ps | 2400.0 ps | 25 ps | 0 |
| 1.10 V | -1000.0..25.0 ps | 2450.0 ps | 25 ps | 0 |

## T0-4 停止证据

- 238 个正式自适应场景；没有暴力二维网格。
- 停止原因：ambiguous_duration_boundary: active_ck_edge_count_not_one。
- 这两个场景均出现两个 active CK 边沿，双采样 Q 判定因此无效；它们不是被平滑或删除的普通 Q0/Q1 边界点。
- 各 depth 已获得的部分 minimum-duration 数值只保留为原始观测，不构成六 margin 完整能力声明。

## 下游边界

- `VDD_MONITORED < 0.80 V`：D0 只能使用 heartbeat、stuck-Q、timeout 或无有效检测结果等 fail-safe 语义，禁止精确 timing trip 声明。
- T0-5/T0-6 被阻塞；1 ns 威胁的最大 runtime probe period 与 400 MHz 复用资格均未被表征。

## 仿真与审计账本

- T0-2E：新增 HSPICE 0；复核纠偏四点和正式十二点摘要。
- T0-3：新增 HSPICE 44；T0-4：新增 HSPICE 238。
- 旧 T0-2 固定高电平场景：62，均为 `HISTORICAL_SUPERSEDED_NOT_DELETED`。
- 本轮曾由已修复 dispatcher 错误调用 12 个 legacy long-pulse 场景；它们保留在 task-owned run 目录，已在 `T0_PROCESS_AUDIT.json` 标记为非权威，后续结论未消费。
- 禁止流程（H0/M0/M1/M1-T/RF/XA/D0 RTL）新增运行：0。
