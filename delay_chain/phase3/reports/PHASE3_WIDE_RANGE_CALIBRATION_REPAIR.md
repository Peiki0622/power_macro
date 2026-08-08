# Phase 3 宽范围校准修复

## 结论

修复后的物理实现使用 11 个均匀分布的活动级（`0x24924925`）、
`CAL_SEL=0`、基线码 4、companion launch 侧 0 个 BUF 输入负载，以及
RVT/CK launch 侧 6 个 BUF 输入负载。最终 83 点真实 DFF 表征全部有效、
无 reset 失败、末级均在 8 ns 读窗前到达，0.70 V 的码为 11，未饱和。

需要明确的限制是：最终首次正残差在 0.970 V（130 mV droop），没有达到
原计划中“约 20--30 mV 即 +1”的增强灵敏度目标。因此该实现修复了错误的
all-zero 成功判定和宽范围可用性，但尚不满足小 droop CUSUM 灵敏度目标。

## 原始失败与软件缺陷

旧的 16 活动级结果固定 `CAL_SEL=0`、baseline=0，83 点原始 DFF 码均为 0。
在 1.10 V，末级 D-CK 为 +33.696 ps，说明模拟路径并未失效，而是 DFF
aperture 未被正确使用。

修复了两条软件错误：校准 runner 不再把不在 3--6 窗口内的合法端点重新写成
PASS；宽范围 validator 现在要求 nominal 非端点、位于 3--6 且总码跨度非零。
顶层 RTL 同时由旧的 `DEFAULT_CAL_SEL` 改为 `WIDE_RANGE_DEFAULT_CAL_SEL`。

## 八档名义调试与 selector

本地 MXT2 UDP 真值表确认 `S0=0` 选择 A、`S0=1` 选择 B。原 16 级/两颗
companion 负载的八档实测为：CAL 0 码 0、CAL 1 码 20、CAL 2--7 码 32；
launch D-CK 分别为 +4.886、-30.748、-61.517、-78.032、-94.603、-111.179、
-128.127、-141.902 ps。CAL 0 到 1 的约 35.6 ps 细步进跨过 DFF aperture，
因此属于“范围跨越但步进过粗”，不是 selector 极性错误。

最终 11 级/修复 load 的 CAL 0 为码 4、有效、零 reset；代表性 D-CK
（stage 0/7/15/23/31）为 -19.464/-10.552/-2.849/+5.849/+17.859 ps。

## balance-load 与物理修复

在 CAL 0 的 A/B 中，移除两颗 companion BUF 输入负载把 launch D-CK 从
+4.886 ps 变为 +0.702 ps，末级 D-CK 从 +33.696 ps 变为 +27.384 ps；方向正确
但仍不足以进入 aperture。保留两颗旧 BUF 并把它们移至 CK 侧，再增加四颗
相同真实 BUF 输入负载，得到 6 颗 CK-side 输入负载。此时末级 D-CK 为
+3.213 ps，名义码为 4。没有增加 stage、DFF、参考电源或运行时 topology mux。

## 增益筛选与最终曲线

16 级在 0.80 V 饱和；14 级在 1.08 V 已出现无效 bubble；12 级仅在 0.70 V
无效；8 级无效问题消失但方向错误/增益不足。11 级在七点 screen 和最终 83 点
均保持有效和非饱和，因此被固定。

| VDD (V) | 最终码 | 残差 | 有效 |
|---:|---:|---:|---:|
| 1.10 | 4 | 0 | 1 |
| 1.08 | 4 | 0 | 1 |
| 1.05 | 4 | 0 | 1 |
| 1.00 | 4 | 0 | 1 |
| 0.90 | 5 | +1 | 1 |
| 0.80 | 5 | +1 | 1 |
| 0.70 | 11 | +7 | 1 |

两条既有 timing anchor（1.054061327707 V、1.047473942801 V）均为码 4、有效。
最终结果位于 `runs/wide_range_repaired_final/voltage_code.csv` 与
`voltage_summary.json`；旧的 `wide_range_final` all-zero 证据未被覆盖。

## 硬件成本

活动 companion stage 从 16 降至 11；DFF 始终为 32。companion launch 的两颗
BUF 输入负载被移除，RVT launch 使用 6 颗 BUF 输入负载，净增加 4 颗真实 BUF
输入负载。所有其它校准 MXT2/BUF tap 与三层 MUX 树保持不变。
