# FTC Programmable Acceptance Window 根因分析

## 结论

当前 `Programmable Acceptance Window = NO-GO` 的直接原因是：在正式
`0.80--1.10 V` 静态范围内，按照规定的 `C_alarm = C_lock + M` 选择后，
真实 DFF 时钟边沿始终发生在 `xor_29` 脉冲结束之后。因此 DFF 采到低电平，
`Q=0`，进而 `alarm=0`。

这不是 DFF、MUX 连接或 code 极性接反造成的。证据表明当前阈值延迟 mapping
在 `tap18` 与 `tap36` 之间存在过大的物理间隔；它能够满足上一阶段的“校准后
保留两个更长 code”要求，却不能使 `C_lock+1` 和 `C_lock+2` 在本任务的合法
静态 droop 范围内形成可触发、可区分的接受窗口。

## 判定对象

本阶段没有重新搜索校准 code。它按计划固定使用：

```text
C_alarm = C_lock + M
M = 1 or 2
Alarm = Q(C_alarm)
```

冻结 mapping 为 `[10,12,14,16,18,36,37,38]`，即 code4 是 tap18，code5
直接跳到 tap36，code6 和 code7 分别为 tap37、tap38。冻结 `C_lock` 为：

| 正常 V0 (V) | C_lock | M=1 的 C_alarm | M=2 的 C_alarm |
|---:|---:|---:|---:|
| 0.85--1.00 | 5 | 6 / tap37 | 7 / tap38 |
| 1.05--1.10 | 4 | 5 / tap36 | 6 / tap37 |

因此，本阶段并未把旧的 `Q=1` code4 当作报警 code。那样会违反 `C_lock+M`
定义，也会在相应正常工作点造成误报。

来源：

- [acceptance-window 计划](../../../plans/ftc_programmable_acceptance_window_plan.md)
- [冻结 mapping](../analysis/static_self_calibration/range_mapping.json)
- [冻结 calibration trace](../analysis/static_self_calibration/calibration_trace.csv)

## DFF 比较机制

真实电路中，`xor_29` 同时驱动 DFF 数据端 `D` 和 threshold chain。MUX 选择的
threshold tap 驱动 DFF 时钟端 `CK`。因此：

```text
D_alarm = t(CK rising) - t(xor_29 rising)
W_S_int = t(xor_29 falling) - t(xor_29 rising)

D_alarm < W_S_int  -> CK 到达时 xor_29 仍为高 -> Q=1
D_alarm > W_S_int  -> CK 到达时 xor_29 已为低 -> Q=0
```

这不是软件近似判定；上述 crossing 和 `q_final_v` 均来自 HSPICE 的真实
standard-cell netlist。DFF 实例端口为：

```text
XDFF q_final vdd_a vdd_a vss_a vss_a dff_ck xor_29 dff_reset DFFRPQ_X0P5M_A9TR40
```

其中 `dff_ck` 是 7-MUX threshold tree 的输出，`xor_29` 是 DFF 数据端。
可在新旧 deck 中直接核对：

- [本轮 0.90 V / M=1 / attack 0.80 V deck](../runs/programmable_acceptance_window/r1/scenarios/v0_900mv_m1_attack_800mv_coarse/programmable_acceptance_window.sp)
- [旧 r2 的 0.80 V / code6 deck](../runs/static_self_calibration_full_range/r2/scenarios/v0p80_step14_code6/static_self_calibration.sp)

## 关键物理证据：0.80 V 边界

0.80 V 是合法范围的最低 rail，也是最有利于观察静态 droop trip 的已允许端点。
冻结 r2 的真实量测如下：

| code | tap | W_S_int (ps) | D_code (ps) | D-W (ps) | Q |
|---:|---:|---:|---:|---:|---:|
| 4 | 18 | 784.525 | 546.186 | -238.340 | 1 |
| 5 | 36 | 784.684 | 928.502 | +143.818 | 0 |
| 6 | 37 | 784.735 | 954.502 | +169.766 | 0 |
| 7 | 38 | 784.869 | 974.758 | +189.888 | 0 |

来源：[冻结 calibration trace](../analysis/static_self_calibration/calibration_trace.csv)。

表中有两个结论。

1. 旧实验中确实存在 `Q=1`，但它是 code4/tap18 的结果。此时 threshold 时钟
   比 XOR falling edge 早约 238 ps。
2. 进入 code5/tap36 后，threshold 时钟一次性越过 XOR falling edge 约 144 ps；
   code6 与 code7 更晚。这正是 `C_lock+M` 无法报警的直接时间条件。

`tap18 -> tap36` 相差 18 个 LVT buffer；而 code5 -> code6 与 code6 -> code7
只各增加一个 buffer。这种不均匀的 mapping 将实际 comparator boundary 放在
code4/code5 的大间隔内，而不是放在可由 M=1、M=2 细分的相邻 code 附近。

## 本轮 attack 与旧证据的一致性

选取 `V0=0.90 V, M=1` 为例：冻结 `C_lock=5`，所以正确的
`C_alarm=6/tap37`。当 attack rail 为 0.80 V 时，本轮量测为：

| 项目 | 本轮值 |
|---|---:|
| W_S_int | 784.735387 ps |
| D_alarm | 954.501608 ps |
| D_alarm - W_S_int | +169.766221 ps |
| Q | 0 |
| alarm | 0 |
| vdd_a_min_v | 0.800000000 V |

来源：

- [本轮 attack sweep 行](../analysis/programmable_acceptance_window/attack_sweep.csv)
- [本轮原始 HSPICE MEAS](../runs/programmable_acceptance_window/r1/scenarios/v0_900mv_m1_attack_800mv_coarse/programmable_acceptance_window.mt0.csv)

该组的 `t_xor_rise`、`t_xor_fall`、`t_ck_rise` 与旧 r2 的“正常 0.80 V、code6”
原始 MEAS 完全相同，分别为：

```text
t_xor_rise = 1.802717658 ns
t_xor_fall = 2.587453045 ns
t_ck_rise  = 2.757219266 ns
```

来源：[旧 r2 code6 原始 HSPICE MEAS](../runs/static_self_calibration_full_range/r2/scenarios/v0p80_step14_code6/static_self_calibration.mt0.csv)。

这是预期行为：本阶段的 `baseline_vdd_v` 只选择冻结的 `C_lock`；物理供电是
`attack_vdd_v`。因此，`V0=0.90 V, M=1, attack=0.80 V` 的真实电路就是一个
0.80 V、code6 的同轨比较器，不能因为标签中的 V0 是 0.90 V 而拥有额外的模拟
记忆或独立参考电压。

## 全范围 attack 证据

本轮以六个 baseline 和两个 margin 完成 42 个真实 HSPICE scenario。每一个
scenario 都有独立 deck、listing、MEAS 和命令日志，并且物理 VDD 都在
`0.80--1.10 V` 内。

结果为：

- 全部 42 行 `valid=True`；
- 全部 42 行 `Q=0`、`alarm=0`；
- 六个 baseline 的 M=1 都扫至其允许的最低 attack rail 后仍没有 `Q=1`；
- 因没有粗扫 `Q=1`，没有虚构 10 mV refinement 点；
- 12 个 `(V0,M)` trip map 条目均为 `NO_IN_RANGE_TRIP`。

来源：

- [attack sweep](../analysis/programmable_acceptance_window/attack_sweep.csv)
- [trip map](../analysis/programmable_acceptance_window/trip_map.csv)
- [结果摘要](../analysis/programmable_acceptance_window/summary.json)
- [原始 run manifest](../runs/programmable_acceptance_window/r1/manifest.json)

最高 baseline 的最小 margin 也没有例外：`V0=1.10 V, M=1` 使用 code5/tap36，
在 attack=0.80 V 时仍有 `D_alarm=928.502 ps > W_S_int=784.684 ps`，所以仍为
`Q=0`。这证明问题不只出现在 code6/code7，而是整个 `C_lock+M` 可用集合在
最低合法 rail 仍处于脉冲之后。

## 对“以前曾报警”的澄清

以前的成功报警没有被否定。旧 r2 的 0.80 V/code4 原始 MEAS 显示：

```text
t_xor_fall = 2.587242852 ns
t_ck_rise  = 2.348903234 ns
q_final_v  = 0.7999960760 V
```

它清楚地证明真实 DFF comparator 能够产生 `Q=1`。然而 code4 不属于本阶段的
合法报警 code：在 0.80--1.00 V，冻结 `C_lock=5`，最小 margin 已经是 code6。
将 code4 作为报警阈值会绕过 acceptance-window 的安全 margin 定义，并把正常
工作点误判为报警。

来源：[旧 r2 code4 原始 HSPICE MEAS](../runs/static_self_calibration_full_range/r2/scenarios/v0p80_step12_code4/static_self_calibration.mt0.csv)。

## 本轮执行一致性检查与限制

新旧 code6 deck 的 cell、rail、code rail、30 个 XOR、38 个 threshold BUF、
7 个 MUX，以及 DFF `CK/D/R` 连接一致。新旧 0.80 V/code6 的三个 timing crossing
也相同，排除了本轮错误选择 tap、错误接入 DFF clock 或错误接入 XOR data 的解释。

存在一项应在后续重跑时统一的 testbench 差异：旧 r2 code6 在
`3.376961280 ns` 读取 `q_final_v`，本轮在 `3.000000000 ns` 读取。该差异不改变
本轮 code6 的分类：时钟 crossing 为 `2.757219266 ns`，本轮读点仍在 crossing 后
约 242.8 ps，超过既有 200 ps Q-settle 要求；两次 `q_final_v` 都约为
`0.17 uV`，远低于 0.80 V rail 的 0.40 V 判定阈值。

这项差异是可复现性改进项，而不是当前 `Q=0` 的根因。任何正式 refinement
重跑都应统一复用旧 r2 的最终 Q readout 时刻，避免把 testbench 时序差异带入
新的边界结论。

## 根因归纳

根因可分为三个层次：

1. **直接电路原因：** 对每个合法 `C_lock+M`，`D_alarm-W_S_int` 在最低合法
   attack rail 仍为正，DFF 采到低电平。
2. **mapping 原因：** code4/tap18 到 code5/tap36 的 18-buffer 跳变使物理
   Q transition 落在一个很大的 code 间隙中；M=1/2 只能选择间隙之后的更长路径。
3. **架构语义：** baseline V0 在此静态实验中只用于选择 code，所有 sensor 和
   threshold cell 都由同一个 attack rail 供电。该结构没有保存独立的模拟 V0
   reference；它只能依赖降压造成的相对 `W_S_int`/`D_alarm` 变化来跨越固定 code。
   当前范围内该变化不足以跨越 code5。

因此，更准确的工程结论是：可编程 delay chain 的**当前高端 mapping 分辨率与
放置位置**不适合 `C_lock+1/C_lock+2` 静态 acceptance window，而不是整个真实
XOR/DFF comparator 不能工作。

## 有界后续方向

本报告不修改设计。若继续，合理的下一任务应是单独的窄范围 delay-code
refinement：保持 tap29 sensor、真实 DFF、3-bit/7-MUX 架构和 0.80 V 下限，只在
tap18 与 tap36 之间选择少量中间 threshold taps。新 mapping 必须重新以真实
HSPICE 验证以下条件：

1. 所有正常 baseline 的 `C_lock+1` 为 `Q=0`；
2. M=1 在各自的合法 droop 空间内出现真实 `Q=1`；
3. M=2 不比 M=1 更浅触发；
4. 至少一个 baseline 的 M=1/M=2 boundary 可在 10 mV 网格区分。

不得因为当前失败而测试 0.80 V 以下、自动扩展到 4-bit、加入第二传感器、加入
PVT 补偿或加入 baseline tracking；这些都不属于当前根因的最小修复范围。
