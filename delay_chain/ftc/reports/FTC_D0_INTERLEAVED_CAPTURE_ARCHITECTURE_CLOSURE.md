# FTC D0-BR 合法捕获与交错架构闭合

## BR1R Gate

**SHARED_SENSOR_CADENCE_RETIMING_GO**。这是一次仅重解析既有 8 个 physical scenario 的 0-HSPICE 判门修正：原 BR1 的 `1687.575705 ps` fixed-fall result保留为部分观测端点；BR1R 的 750/1000/1250 ps crossing 全部按 E0/EF/E1 波前身份重新审计。2075 ps probe period、正式 M/F、真实 sensor/DFF input load 和所有既有 topology 均未改变。

## 范围与方法

- E0=`S_CLK rise0`、EF=`S_CLK fall0`、E1=`S_CLK rise1` 以 XOR ingress 的序列及 XOR→medium→raw CK 拓扑顺序匹配。没有使用 `[rise0,fall0)`、`[fall0,rise1)`、`[rise1,stop)` 作为全链必须完成的硬时间窗。
- Gate 只检查同一节点上 E0→EF→E1 的 rise/fall 交替、每个脉冲非重叠/不合并，以及相邻事件至少 25.0 ps 的低电平间隔；EF 可在 E1 的 source rise 后仍处于下游级，只要 EF 在 E1 到达同一节点前结束。
- 每条波前独立报告 `D_ref=t(raw_dff_ck rise)-t(xor_29 rise)`。未把 T0 的 25 ps phase 搜索分辨率当作 D_ref 漂移阈值：正的、已分离波前上的 D_ref 变化归为瞬态供电下的物理延迟变化报告，而非 collision。
- 本次没有新 HSPICE，也没有重跑 M0/T0/H0/M1/RF/XA；没有创建 legalizer、capture bank、runtime FSM 或 sensor copy。
- 1250 ps 为本次优先复审点；它在两个正式 target 都通过同节点波前分离 Gate。

## 有限 retiming 结果

- fall0 offset 750.0 ps：br1_0p95_l2_repeated_sensor=WAVEFRONT_SEPARATION_PASS, br1_1p10_l2_repeated_sensor=WAVEFRONT_SEPARATION_PASS；两个 target 的最小同节点低电平间隔=239.201997 ps；共同 Gate=WAVEFRONT_SEPARATION_PASS。
- fall0 offset 1000.0 ps：br1_0p95_l2_repeated_sensor=WAVEFRONT_SEPARATION_PASS, br1_1p10_l2_repeated_sensor=WAVEFRONT_SEPARATION_PASS；两个 target 的最小同节点低电平间隔=489.120414 ps；共同 Gate=WAVEFRONT_SEPARATION_PASS。
- fall0 offset 1250.0 ps：br1_0p95_l2_repeated_sensor=WAVEFRONT_SEPARATION_PASS, br1_1p10_l2_repeated_sensor=WAVEFRONT_SEPARATION_PASS；两个 target 的最小同节点低电平间隔=265.146203 ps；共同 Gate=WAVEFRONT_SEPARATION_PASS。

## D_ref 逐波前报告（非漂移判门）

- fall0 offset 750.0 ps：br1_0p95_l2_repeated_sensor: E0/EF/E1=495.193012/491.250453/466.739913 ps, ΔE1-E0=-28.453099 ps; br1_1p10_l2_repeated_sensor: E0/EF/E1=324.722968/325.467076/324.705455 ps, ΔE1-E0=-0.017513 ps。
- fall0 offset 1000.0 ps：br1_0p95_l2_repeated_sensor: E0/EF/E1=495.267684/497.104198/468.019246 ps, ΔE1-E0=-27.248438 ps; br1_1p10_l2_repeated_sensor: E0/EF/E1=324.726837/325.256722/324.928606 ps, ΔE1-E0=0.201769 ps。
- fall0 offset 1250.0 ps：br1_0p95_l2_repeated_sensor: E0/EF/E1=495.249981/496.181747/465.954874 ps, ΔE1-E0=-29.295107 ps; br1_1p10_l2_repeated_sensor: E0/EF/E1=324.726837/325.357583/324.865521 ps, ΔE1-E0=0.138684 ps。

## 后续边界

BR1R 仅授权进入 BR2 的合法 capture event/pulse legalizer 研究；尚未实现任何该结构。
