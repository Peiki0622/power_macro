# FTC D0-BR 合法捕获与交错架构闭合

## BR1R Gate

**SHARED_SENSOR_CADENCE_PHYSICALLY_BLOCKED**。原 BR1 的 `1687.575705 ps` fixed-fall result被重新解释为单一 S_CLK 占空比证据；BR1R 在保持 2075 ps probe period、正式 M/F、真实 sensor/DFF input load 和所有既有 topology 不变的前提下，只重定时第一笔 S_CLK fall。

## 范围与方法

- 已重解析两个 retained BR1 listing，按测得的 `rise0 -> fall0 -> rise1` 三个因果窗口归属 XOR、medium、raw CK crossing；未按全局 `rise1/rise2/rise3` 序号配对 probe。
- 新运行只允许共同的 750、1000、1250 ps fall offset 与两个正式 L2/3002 ps target；没有 M0/T0/H0/M1/RF/XA campaign，也没有任何 legalizer、capture bank、runtime FSM 或 sensor copy。
- 单一 target 只有在三窗口各 node 均为一个完整 rise/fall、falling-wave 在 rise1 前清空、probe1 D_ref 完整且与 probe0 相差不超过 25 ps 时才通过。

## 有限 retiming 结果

- fall0 offset 750.0 ps：br1_0p95_l2_repeated_sensor=CAUSAL_WINDOW_FAIL, br1_1p10_l2_repeated_sensor=CAUSAL_WINDOW_FAIL；共同 Gate=CAUSAL_WINDOW_FAIL。
- fall0 offset 1000.0 ps：br1_0p95_l2_repeated_sensor=CAUSAL_WINDOW_FAIL, br1_1p10_l2_repeated_sensor=CAUSAL_WINDOW_FAIL；共同 Gate=CAUSAL_WINDOW_FAIL。
- fall0 offset 1250.0 ps：br1_0p95_l2_repeated_sensor=CAUSAL_WINDOW_FAIL, br1_1p10_l2_repeated_sensor=CAUSAL_WINDOW_FAIL；共同 Gate=CAUSAL_WINDOW_FAIL。

## 后续边界

两个正式 target 在规定的共同 retiming 集合内均未闭合；后续必须另立 multi-sensor-lane 计划。`P_sensor_verified_ps` 与 `N_sensor_min` 保持 `null`。
