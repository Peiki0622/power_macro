# FTC T0-2 瞬态电压跌落纠偏报告

## 最终判定

**T0-2 CORRECTED PASS**

本轮只纠正 PD_CTRL→PD_SENSE 的验证电平抽象；未修改 FTC_SENSOR、H0、M1、冻结 RTL 或任何传感器拓扑。

## 纠偏审计

- POWER_DOMAIN_CONTRACT 已加入 T0 冻结输入，28 条 crossing 均由瞬时 `V(vdd_a,vss_a)` 归一化。
- S_CLK、复位、16 条 medium 和 10 条 fine 控制均采用稳定 PD_CTRL 0/1 源加本地 VDD 归一化 D2A 抽象。
- XOR/CK 测量阈值已改为 `V(vdd_a,vss_a)/2`。
- M0 0.87 V/M5/F6 与 T0 恒定低压兼容模式通过零仿真网络、电源、端口和时序等价审计：等价。

## 四个纠偏点

| 点 | 期望 Q | 实际 Q | valid |
|---|---:|---:|---:|
| 0p95_L2_last_q0 | 0 | 0 | 1 |
| 0p95_L2_first_q1 | 1 | 1 | 1 |
| 1p10_L2_last_q0 | 0 | 0 | 1 |
| 1p10_L2_first_q1 | 1 | 1 | 1 |

## 正式十二点

- 判定：`PASS`。
- 场景数：12；新增 HSPICE：8。
- 纠偏四点新增 HSPICE：4；正式十二点新增 HSPICE：8；成功新增合计：12。
- 另有 1 个保留的 HSPICE 源语法诊断失败场景，不计入有效纠偏结果：1。
- 旧 62 个场景全部保留，统一标记为 `HISTORICAL_SUPERSEDED_NOT_DELETED`，原因是固定 VDD_VALUE 跨域高电平未按本地 VDD 归一化。

## 范围边界

T0-3/T0-4/T0-5/T0-6 本轮未执行；因此没有相位窗口、持续时间边界、覆盖率或运行时 cadence 结论。

## 仿真预算

- 纠偏审计新增 HSPICE：0。
- 纠偏四点新增 HSPICE：4。
- 正式十二点新增 HSPICE：8。
- 复用旧 62 场景：0；复用先行纠偏点：4；仅重解析旧场景：0；禁止流程新增运行：0。
