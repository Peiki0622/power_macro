# FTC Composite Reference Sensitivity-Shaping

## Decision

**NO-GO**

## Required Answers

1. 正确 composite scaling 后，是否存在预测可行组合？否；45 个合法组合均未在 1.10 V 和 0.90 V 同时通过温度 residual 与 M_100 门限。
2. 真实 composite HSPICE 是否保留这种温度/VDD 可分性？未运行；预测 shortlist 为空，计划要求直接停止而不启动新 HSPICE。
3. 这条 passive reference 路线最终是 GO 还是 NO-GO，下一阶段进入哪里？`Passive Sensitivity-Contrast Reference = NO-GO`；下一阶段转为 programmable timing threshold、self-calibration 与 security-aware slow tracking。

## Provenance

- 预测仅使用冻结的 simple reference、tap29 fine/temperature/PVT evidence；没有复跑 sensor、旧 simple reference 或 prior finalist PVT。
- 搜索空间固定为一个 RVT unit 加一个 LVT unit，比例仅为 1:1、1:2、2:1，且总标准单元数不超过 4。
- 每个 composite 先反解 parent delay movement，再以 composite nominal delay 重算 k_C；没有相加 parent residual。
