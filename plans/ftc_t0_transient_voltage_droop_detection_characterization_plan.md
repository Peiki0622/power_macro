# FTC T0 瞬态电压跌落检测能力表征逐阶段推进计划

**仓库：** `Peiki0622/power_macro`  
**目标分支：** `main`  
**T0 原始输入基线：** `46ebf25e9bb15aba29be23f79e8aa3ed8b8ad474`  
**T0-2 纠偏完成提交：** `b3fe480c461b6b8a5d2f10a276d763ba9aae9526`  
**当前阶段状态：** T0-2 已在本地电源归一化接口抽象下纠偏通过；下一步不是重跑 T0-2，而是先进行零 HSPICE 的 T0-2E 证据闭合与 T0-3 解封，然后进入 T0-3 相位敏感窗口表征。  
**阶段定位：** H0 校准到检测所有权切换已通过，M0/M0-E 静态检测裕量与静态触发电压已闭合，M1 可编程检测配置已通过，M1-T 时序证据已闭合；T0 只研究当前冻结传感器面对真实瞬态电压跌落时的物理检测边界，并为后续 D0 运行时检测状态机给出必须满足的检测时序合同。

---

# 0. T0 的唯一宏观目标

T0 不再回答“静态电压下降多少会触发”，这个问题已经由 M0 完成；T0 也不负责写运行时检测状态机、报警、心跳或动态重校准，这些属于 D0。

T0 只回答以下几个物理问题：

1. 一个有限持续时间的电压跌落，至少要多深、持续多久，当前传感器才会被真实触发器检测到；
2. 同样的瞬态跌落出现在一次检测动作的不同时间位置时，哪些位置可检测、哪些位置属于盲区；
3. 不同检测裕量等级下，电压跌落深度与最短可检测持续时间之间是什么关系；
4. 为了覆盖目标攻击持续时间，未来 D0 最多允许多长的检测间隔；
5. 低于 0.80 V 的严重欠压应继续使用精确时序比较，还是应转入失效保护语义。

T0 的最终输出必须是一套可以直接约束 D0 的**瞬态威胁与检测时序合同**，而不是一批互不相干的 HSPICE 波形。

---

# 1. 冻结基线与已有证据

T0 必须把以下内容视为只读基线，非必要不得重跑。

## 1.1 冻结结构

- 当前冻结 `FTC_SENSOR`；
- medium 级 N=16；
- medium delay cell `BUF_X0P7M_A9TL40`；
- medium mux `MXT2_X0P5M_A9TL40`；
- fine driver `BUF_X0P8M_A9TL40`；
- fine load `NOR2_X4A_A9TL40`，信号 A；
- fine K=10；
- sensor tap 29；
- 初始 RVT 4 级、LVT 0 级；
- 30 个可观测级；
- XOR `XOR2_X0P5M_A9TL40`；
- DFF `DFFRPQ_X0P5M_A9TR40`；
- Q settle 200 ps；
- H0 所有权切换结构；
- M1 12 项精确检测配置表；
- 400 MHz / 2.5 ns 控制时钟合同。

## 1.2 已有静态检测证据

M0/M0-E 的静态触发深度只作为 T0 的参考锚点，不允许重新扫一遍来“复现”已有工作：

```text
0.95 V 正常工作点：
L1 -> 0.88 V，静态跌落深度约 70 mV
L2 -> 0.86 V，静态跌落深度约 90 mV
L3 -> 0.83 V，静态跌落深度约 120 mV

1.10 V 正常工作点：
L1 -> 1.01 V，静态跌落深度约 90 mV
L2 -> 0.96 V，静态跌落深度约 140 mV
L3 -> 0.93 V，静态跌落深度约 170 mV
```

对应 M1 精确检测配置：

```text
M4/F6 锚点：
L1 -> M4/F9
L2 -> M5/F6
L3 -> M5/F9

M2/F9 锚点：
L1 -> M2/F10
L2 -> M3/F8
L3 -> M3/F10
```

0.80 V 锚点只保留“配置合法、正常点已表征”的意义，不具有 `<0.80 V` 正式瞬态触发资格。

## 1.3 M1-T 风险记录

当前 M1-T 已确认：

```text
最差全局 setup +1.168 ps 是输入到寄存器路径，包含外部输入预算；
真正内部最差寄存器到寄存器 setup 约 +7.005 ps；
该路径属于一次性检测配置路径，不属于 T0 的实时传感路径。
```

因此 T0 **不修改 M1，也不因为 +7.005 ps 重新综合或重跑 M1**。该余量只作为未来 D0 集成/布局布线阶段的实现风险保留。

## 1.4 T0-2 纠偏后的权威证据

提交 `b3fe480c461b6b8a5d2f10a276d763ba9aae9526` 已完成 T0-2 测试平台纠偏，后续 T0 必须以该提交及其后续明确取代证据作为物理基础，不得再使用原先固定高电平版本的结果作为正式结论。

纠偏后的正式事实为：

```text
PD_CTRL 内部保持稳定 0/1 逻辑语义；
PD_CTRL -> PD_SENSE 的 28 条验证跨域信号在 PD_SENSE 侧按瞬时 VDD_MONITORED 归一化；
S_CLK、复位、16 条 medium、10 条 fine 的本地高电平随 VDD_MONITORED；
XOR/CK 的时序测量阈值使用瞬时本地 VDD_MONITORED/2；
M0 0.87 V、M5/F6 与 T0 恒定低压兼容模式通过零 HSPICE 电气等价审计；
四个先行纠偏点全部恢复原 M0 的 Q0/Q1 方向；
六个正式检测配置的 12 个长脉冲场景全部通过；
T0-2 = CORRECTED PASS。
```

原 62 个使用固定 `VDD_VALUE` 作为跨域高电平的 T0 场景必须永久保留，但状态只能是：

```text
HISTORICAL_SUPERSEDED_NOT_DELETED
```

它们可以用于说明纠偏过程，不得用于后续 T0-3/T0-4/T0-5/T0-6 的物理结论，也不得再次被当成 T0-2 的正式失败证据。

---

# 2. 本阶段绝对禁止事项

除非后续某个明确停止门证明已有结构本身有错误，否则禁止：

```text
重跑 H0
重跑 H0-E
重跑完整启动校准
重跑 M0 静态局部面
重跑 M0 静态 trip sweep
重跑 M0-E
重跑 M1 RTL/SVA
重跑 M1 综合
重跑 M1 mapped+SDF
重跑 M1-T STA
重跑 RF6 / RF8 / RF9C / RF9D
重跑 XA 全流程
修改六个冻结校准 RTL
修改 H0 RTL
修改 M1 mapper / manager RTL
修改 FTC_SENSOR
修改 medium/fine/XOR/DFF 拓扑
修改 400 MHz 校准合同
设计 D0 检测状态机
设计报警逻辑
设计 heartbeat/timeout RTL
做动态重校准
做 PVT / Monte Carlo / post-layout
搜索或引入真实跨压 level shifter / isolation cell
```

从纠偏完成后开始，额外禁止：

```text
因为修改 T0 runner 而自动重跑已经通过的 T0-2 正式 12 点
再次尝试 0.5 ns / 1 ps / 1 fs 等多轮 T0-2 起点试探
重新运行旧的固定高电平 T0-2 流程
把旧 long_pulse_consistency/summary.json 中的 STOP 当成当前权威 Gate
删除、覆盖或改写旧 62 个历史场景
```

**核心原则：** T0 只新增“现有证据回答不了的瞬态物理问题”的仿真。能由已有 CSV/JSON/报告直接复用的内容一律不得通过重新跑仿真获得。

---

# 3. T0 的正式研究范围

## 3.1 正式检测工作点

只把以下六个工作点定义为正式瞬态检测候选：

```text
0.95 V：L1 / L2 / L3
1.10 V：L1 / L2 / L3
```

L0 只作为正常/控制工作点，不用于宣称电压跌落触发能力。

0.80 V 的 L0-L3 只可用于必要的合法性或正常点控制，不允许在 T0 中升级为 `<0.80 V` 正式检测能力。

## 3.2 唯一权威判决

真实 DFF 的 Q 结果以及后续双采样可解释状态是唯一检测判据。

```text
R = W_xor - D_ref
```

只能作为机理解释量，不得替代真实 DFF 判决。

对 T0-3 及其后的动态相位场景，两个 Q 采样点必须分别按**各自采样时刻的本地 `VDD_MONITORED`**进行高低判决，不能继续把固定 `Vdroop` 作为两个采样点共同的判决电压。

至少需要记录：

```text
VDD_at_Q_sample_1
VDD_at_Q_sample_2
Q_sample_1 / VDD_at_Q_sample_1
Q_sample_2 / VDD_at_Q_sample_2
Q_final
```

如果任一采样点处于电源边沿且无法形成稳定高/低状态，应标记为 `ambiguous`，不得强行归类成 Q0 或 Q1。

---

# 4. T0-0 —— 冻结瞬态威胁与单次检测实验合同

本阶段已经完成；后续不得无理由重新定义其相位参考和波形语义。

## 4.1 统一瞬态电压跌落波形

所有正式 T0 瞬态必须使用有限斜率的梯形/PWL 电源波形：

```text
正常电压 Vbase
   ↓ 下降时间 t_fall
最低电压 Vdroop
   ↓ 保持时间 t_hold
恢复到 Vbase
   ↑ 恢复时间 t_rise
```

统一参数：

```text
Vbase
跌落深度 DeltaV = Vbase - Vdroop
t_fall
t_hold
t_rise
phase
```

`phase` 已冻结为：

> 电源下降开始时刻相对于本次真实检测 `S_CLK` 上升沿的时间偏移。

后续所有扫描必须保持同一相位定义。

## 4.2 不允许理想电压跳变

PWL 不允许同一时刻从 Vbase 直接跳到 Vdroop。必须有非零 `t_fall/t_rise`。

主研究斜率仍属于实验假设，不得写成真实芯片电源网络已经证明的边沿速度。

## 4.3 权威合同

至少继续冻结：

```text
delay_chain/ftc/analysis/t0_transient_droop/contract/T0_TRANSIENT_THREAT_CONTRACT.json
delay_chain/ftc/controller/final_closure/freeze/POWER_DOMAIN_CONTRACT.json
以及 S_CLK / reset / configuration 的跨域合同
```

后续 T0 任何物理场景都必须保持 PD_SENSE 本地电源归一化接口抽象。

---

# 5. T0-1 —— 当前 FTC 专用瞬态单次检测 runner

T0-1 已经完成并在 T0-2 纠偏中修正。后续不得重新建立另一套近似传感器模型。

## 5.1 冻结原则

必须继续保持：

```text
当前 FTC_SENSOR
当前 medium/fine 拓扑
当前 XOR
当前真实 DFF
当前 M1 精确 M_det/F_det
当前单次 probe 时序
PD_CTRL 稳定逻辑语义
PD_SENSE 本地 VDD 归一化跨域抽象
```

唯一允许变化的物理研究变量仍然是：

```text
VDD_MONITORED 的瞬态波形参数
```

## 5.2 后续 runner 修改约束

后续为了实现 T0-3/T0-4/T0-5 可以扩展：

```text
相位扫描
持续时间扫描
自适应边界搜索
采样时刻本地 VDD 记录
窗口/覆盖率后处理
```

但不得改变：

```text
传感器拓扑
M/F 物理编码
DFF 连接
PD_SENSE 本地电平归一化方式
M0 单次 probe 事件时序
```

## 5.3 场景身份与复用规则

后续代码修改可能改变 runner 文件哈希，因此**不得把“runner 文件整体哈希发生变化”作为必须重跑 T0-2 已通过物理场景的理由**。

T0-2 的纠偏后权威结果必须通过单独的冻结证据哈希和提交身份引用，而不是通过再次执行物理仿真来“重新确认”。

新 T0-3 以后场景可以使用新的场景身份；但 T0-2 历史结论应读取已提交的纠偏结果，不重新生成。

---

# 6. T0-2 —— 长脉冲静态到瞬态一致性硬门【已纠偏通过】

T0-2 已完成，不再是待执行阶段。

## 6.1 纠偏后的正式判定

权威判定：

```text
T0-2 CORRECTED PASS
```

四个先行纠偏点：

```text
0.95 V / L2 / 0.87 V：期望 Q0，实际 Q0
0.95 V / L2 / 0.86 V：期望 Q1，实际 Q1
1.10 V / L2 / 0.97 V：期望 Q0，实际 Q0
1.10 V / L2 / 0.96 V：期望 Q1，实际 Q1
```

随后六个正式检测配置的 12 个长脉冲点全部保持 M0 最近 Q0/Q1 bracket 的方向与总体顺序。

## 6.2 旧失败结果的处理

旧目录：

```text
delay_chain/ftc/analysis/t0_transient_droop/long_pulse_consistency/
```

其中原始 `STOP` 是纠偏前测试平台产生的历史证据。不得删除，但后续机器流程不得把它作为当前 T0-2 Gate。

后续权威 T0-2 入口必须指向：

```text
delay_chain/ftc/analysis/t0_transient_droop/correction/
```

及纠偏后的 `T0_GATE_STATUS.json`。

## 6.3 不允许再次执行

进入 T0-3 前不得再次运行：

```text
phase_long_pulse()
旧 --phase long-pulse
旧固定高电平 12 点
纠偏后正式 12 点
```

除非未来明确发现纠偏后保存的 deck/listing/measurement 已损坏或无法复核；仅仅因为 Python 脚本变更、哈希变化、增加 T0-3 功能都不是重跑理由。

---

# 7. T0-2E —— 纠偏后证据闭合与 T0-3 解封【零 HSPICE】

这是当前下一步，必须在 T0-3 新物理仿真之前完成。

## 7.1 目标

把“本轮纠偏任务主动阻塞 T0-3～T0-6”的状态，转换成“基于已通过的纠偏证据允许进入 T0-3”，同时修复远程仓库中仍存在的证据链歧义。

**本阶段新增 HSPICE：0。**

## 7.2 必须闭合的证据

首先检查并提交远程可复核的机器可读摘要：

```text
correction/four_point_summary.json
correction/formal_12_summary.json
```

如果它们只存在于本地运行目录或未进入版本库，必须直接由已经提交的 `four_point_results.csv`、`formal_12_results.csv` 和现有 Gate 重新生成；禁止为生成摘要重新跑 HSPICE。

随后必须对旧 `long_pulse_consistency/summary.json` 做**证据取代标记**：

- 不删除原 STOP；
- 不修改原始历史场景；
- 新增机器可读 `superseded_by` / `authoritative_gate` / `reason` 信息，或者建立单独的 supersession JSON；
- 明确当前权威结论来自 `correction/formal_12_summary.json` 和 `T0_GATE_STATUS.json`；
- 后续代码不得读取旧 STOP 作为执行阻塞条件。

## 7.3 T0 Gate 解封

将当前纠偏任务中的：

```text
blocked_later_stages = [T0-3, T0-4, T0-5, T0-6]
```

解释为“纠偏任务本身的主动边界”，而不是新的物理 NO-GO。

T0-2E 完成后应发布新的执行状态：

```text
T0-2 = CORRECTED PASS
T0-3 = ENABLED
T0-4/T0-5/T0-6 = WAITING_FOR_UPSTREAM_GATE
```

此处只是允许进入 T0-3，不得提前宣称 T0-4/T0-5/T0-6 已通过。

## 7.4 切断无意义重跑路径

当前 `--phase phase-window` 不得再执行：

```text
phase_contract()
phase_long_pulse()
phase_window()
```

应修改成只做：

```text
读取并验证 T0-2 CORRECTED PASS 机器可读证据
验证纠偏后的电源域合同哈希/模式
直接进入 phase_window()
```

验证只检查文件存在、摘要内容、哈希/提交身份和纠偏模式，不调用 HSPICE。

## 7.5 动态 Q 判决修正

在真正进入 T0-3 前，扩展测量和分类逻辑，记录两个 Q 采样时刻的实际本地电源：

```text
VDD_at_Q_sample_1
VDD_at_Q_sample_2
```

并按各自本地电源判断：

```text
Q_sample_1 是否为稳定高/低
Q_sample_2 是否为稳定高/低
```

不得继续统一使用 `Vdroop` 作为两个采样点的 Q 高低判决基准。

该修改只针对未来动态相位场景的正确解释，不构成重跑 T0-2 的理由。

## 7.6 Gate

只有全部满足以下条件才允许执行 T0-3：

```text
纠偏后四点摘要可远程复核
纠偏后正式十二点摘要可远程复核
旧 STOP 已机器可读地标记为被纠偏结果取代
T0 Gate 已明确 T0-3 ENABLED
phase-window 不会调用任何 T0-2 HSPICE
PD_SENSE 本地 VDD 归一化合同仍冻结
两个 Q 采样点使用各自采样时刻的本地 VDD 判决
```

任何一项缺失都只修证据/代码，不运行新的物理扫描。

---

# 8. T0-3 —— 中等裕量的相位敏感窗口试探

只有 T0-2E 通过才执行。

## 8.1 先只研究两个代表点

只研究：

```text
0.95 V 的 L2：M5/F6
1.10 V 的 L2：M3/F8
```

理由：L2 位于三个检测裕量的中间位置，更适合先判断当前冻结结构是否存在清楚、可重复的时间敏感窗口。

不得一开始就对六个 margin 做完整相位扫描。

## 8.2 固定跌落深度和持续时间，只扫相位

为每个代表点选择一个已经明显进入静态 Q1 区、但仍满足 `Vdroop >= 0.80 V` 的跌落深度；固定一个足够覆盖感知区间的持续时间，只移动跌落相对于 probe 的开始时刻。

先做粗扫描，寻找：

```text
稳定 Q0 区域
Q0/Q1 转换边界
稳定 Q1 区域
恢复到 Q0 的区域
```

再只对状态转换附近做细扫描。

不得在尚未看到状态转换时直接扩大到六个检测裕量。

## 8.3 每个场景必须输出

至少记录：

```text
phase
VDD_at_Q_sample_1
VDD_at_Q_sample_2
Q_sample_1
Q_sample_2
Q_final / ambiguous
R
实际最小 VDD
droop 与 XOR/CK/Q 的相对位置
```

并提取：

```text
所有连续可检测窗口区间
所有连续盲区区间
每个窗口宽度
最大盲区宽度
窗口相对于 S_CLK 的边界
```

不要只输出一个全局 `phase_min/phase_max`，因为真实结果可能存在多个不连续窗口。

## 8.4 加强后的 Gate

不能再用“至少出现一个 Q1 点”作为 T0-3 通过条件。

两个基准电压都必须至少具备：

```text
一个合法稳定 Q0 区域
一个合法稳定 Q1 区域
至少一个可定位、可重复的状态转换边界
无大量 ambiguous 点主导整个扫描
窗口/盲区可以用连续区间解释
```

如果两个代表点都形成可解释、可重复的相位敏感窗口：

```text
T0-3 = GO
```

如果相位行为高度混乱、主要由 ambiguous 状态构成或无法形成可重复边界：

```text
T0-3 = STOP
```

此时只允许检查物理波形、采样时刻本地 VDD、Q 判决和相位定义，不得直接扩大到六个 margin。

---

# 9. T0-4 —— 六个正式工作点的“跌落深度—最短可检测持续时间”边界

只有 T0-3 通过才执行。

## 9.1 禁止暴力二维网格

不得直接做巨大 `DeltaV × duration` 笛卡尔积。

每个正式候选采用**自适应 bracket + refine**：

```text
固定 DeltaV
先粗略改变 duration 找到 Q0/Q1 边界
然后只在边界附近细化
得到该 DeltaV 下的最短可检测持续时间
```

再换下一个 DeltaV。

## 9.2 跌落深度选择

不同 margin 不共用一套绝对 mV 列表。

每个候选以自己的 M0 静态 Vtrip 为锚，至少选择：

```text
略浅于静态 trip 的控制点
接近静态 trip 的点
明显深于静态 trip 的点
必要时再增加 1-2 个中间点
```

所有正式场景必须满足：

```text
Vdroop >= 0.80 V
```

不得越过 0.80 V 正式下限后继续宣称精确时序检测能力。

## 9.3 单调性审计

在相同相位下，应检查：

```text
跌落更深，检测不应系统性变差
持续时间更长，检测不应系统性从 Q1 反转为 Q0
```

任何 `Q1 -> Q0` 反转必须保留为异常场景并检查，不得在后处理中平滑、删除或强制单调化。

## 9.4 核心输出

最终每个候选形成：

```text
DeltaV -> minimum detectable duration
```

并保留原始 bracket 点、细化点以及每个边界点对应的实际采样时刻本地 VDD。

---

# 10. T0-5 —— 将持续时间边界放回完整相位，量化时间覆盖率

T0-4 得到的是特定有利/代表相位下的边界，不能直接等价为任意时间到达都可检测。

## 10.1 代表场景选择

每个基准电压至少选：

```text
一个接近检测边界的场景
一个明显可检测的场景
```

必要时优先覆盖 L1/L2/L3 中差异最大的检测裕量。

## 10.2 完整相位扫描

将攻击开始时刻在一个完整 probe interval 内移动，统计：

```text
总相位点数
有效判决相位点数
检测到的相位点数
ambiguous 相位点数
phase coverage fraction
连续 blind window 最大宽度
是否存在所有相位都能检测的 guaranteed region
```

## 10.3 结果必须区分三个概念

```text
最佳相位可检测
时间覆盖率
全相位保证检测
```

禁止把“某个相位能检测 1 ns droop”写成“保证检测 1 ns droop”。

---

# 11. T0-6 —— 由物理相位窗口反推未来运行时检测间隔

这一阶段不写 D0 RTL。

## 11.1 目标

根据 T0-3/T0-5 的真实时间敏感窗口，计算或用轻量事件级仿真推导：

```text
probe period
目标 droop duration
最坏攻击 phase
检测覆盖率
```

之间的关系。

## 11.2 不要默认检测频率等于 400 MHz

当前 400 MHz 是校准/所有权/配置控制时钟，不自动等于未来运行时检测频率。

T0 必须先回答：

```text
现有 400 MHz 能否满足目标瞬态威胁类别？
```

如果可以：

```text
未来 D0 可以优先复用 400 MHz 节拍
```

如果不可以：

```text
T0 输出“需要更快的专用运行时检测时序”约束
```

但 T0 不得自行设计新的高速时钟、DLL、分频器或检测状态机。

## 11.3 优先轻量后处理

该阶段优先使用 T0 已有相位窗口数据做数学/脚本级覆盖率推导，不应为了每一个 probe period 都新跑一套 HSPICE。

只有当简单窗口叠加无法描述真实多次 probe 物理交互时，才允许增加极少量多 probe HSPICE 验证，并必须先说明现有单 probe 数据为什么无法回答该问题。

---

# 12. T0-7 —— `<0.80 V` 严重欠压的失效保护语义

本阶段不要求新 HSPICE。

## 12.1 明确边界

当前正式精确时序检测只在：

```text
VDD_MONITORED >= 0.80 V
```

范围内讨论。

低于 0.80 V 时：

- 传感路径标准单元可能进入未正式表征区；
- DFF 行为也不能继续当作精确时间比较器；
- 因此不得通过几条深跌落波形宣称精确 Vtrip 能力。

## 12.2 给 D0 的要求

T0 应输出一个清楚的下游需求：

```text
低于正式工作范围时，D0 应使用 heartbeat / stuck-Q / timeout / 无有效检测结果等失效保护语义，
而不是继续依赖精细 timing trip 数值。
```

T0 只定义需求，不实现 RTL。

---

# 13. T0-8 —— 正式论文级证据、图和最终 Gate

## 13.1 必须形成的核心图

至少形成以下五类正式图。

### 图 T0-1：代表性瞬态波形

同一时间轴显示：

```text
VDD_MONITORED
XOR 有效脉冲/窗口
采样 CK
真实 Q
```

并清楚标注电压跌落的下降、保持、恢复和相位。

### 图 T0-2：单 probe 时间敏感窗口

横轴为攻击相位；纵向/符号为 Q0/Q1/ambiguous 或检测状态；同时给出连续可检测窗口、盲区和边界。

### 图 T0-3：跌落深度—持续时间二维检测边界

至少分别展示 0.95 V 和 1.10 V。

### 图 T0-4：跌落深度—最短可检测持续时间

同一基准电压下比较 L1/L2/L3，强调可编程检测裕量对瞬态能力的影响。

### 图 T0-5：检测间隔—时间覆盖率/保证检测关系

用于直接支撑未来 D0 的检测节拍选择。

## 13.2 绘图环境

继续统一使用现有 Miniconda `DL` 环境和 matplotlib。

正式图：

```text
PDF
600 dpi PNG
```

并生成 manifest，至少记录：

```text
原始 CSV/JSON hash
绘图脚本 hash
Python 路径
matplotlib 版本
conda_env=DL
图尺寸/DPI
```

禁止手工编辑正式图片。

## 13.3 纠偏历史在论文证据中的处理

正式 T0 图和结论只能消费纠偏后的本地 VDD 归一化场景。旧 62 个固定高电平场景不得进入正式性能曲线；它们只能在方法学或验证附录中作为“测试平台错误被发现并纠正”的审计证据。

---

# 14. T0 最终判定标准

## 14.1 T0 = GO

至少满足：

1. 纠偏后的长脉冲 transient 与 M0 static Q0/Q1 ordering 一致；
2. 0.95 V 和 1.10 V 都存在可解释、可重复的瞬态检测区域；
3. 六个 trip-qualified margin 的 `DeltaV -> minimum detectable duration` 已提取；
4. 相位敏感窗口和盲区已量化；
5. 动态 Q 判决使用各采样时刻的本地 `VDD_MONITORED`，没有用固定 `Vdroop` 错判边沿场景；
6. 不存在大量无法解释的“更深/更长反而稳定漏检”反转；
7. 至少针对一个明确瞬态威胁类别，可以推导出可实现的最大 probe period；
8. 已区分“最佳相位可检测”“覆盖率”“全相位保证检测”；
9. `<0.80 V` 已明确转为失效保护语义；
10. 论文级图和机器可读合同完整；
11. 没有无意义重跑 H0/M0/M1/M1-T/T0-2 已完成仿真。

## 14.2 T0 = CONDITIONAL_GO

如果：

```text
物理瞬态检测机制成立，
但当前 400 MHz 节拍无法保证目标短脉冲在所有 phase 下被检测，
```

则允许：

```text
T0 = CONDITIONAL_GO
```

条件必须明确写为：

> 未来 D0 需要满足由 T0 推导出的更短 probe period / 更高运行时检测频率。

不得把不足的相位覆盖率隐藏成普通 GO。

## 14.3 T0 = NO-GO / STOP

以下情况至少任一出现，应停止进入 D0：

```text
纠偏后的 long-pulse 无法重现 M0 静态方向
真实 DFF Q 与预期物理机制持续矛盾
phase 行为无可重复边界
动态相位场景主要由不可解释的 ambiguous 状态构成
amplitude-duration 关系出现大量不可解释反转
即使最佳 phase + 足够长 pulse 也无法得到稳定检测区域
```

NO-GO 后先检查瞬态物理感知机制、采样判决和 deck，不得用更复杂的数字 FSM 掩盖物理问题。

---

# 15. 仿真预算与“非必要不重跑”规则

Codex 必须遵守以下优先级：

```text
已有 JSON/CSV/报告可回答 -> 直接复用，仿真数 0
已有 raw run 可重解析 -> 重解析，仿真数 0
只缺后处理/摘要/证据取代标记 -> 只做后处理，仿真数 0
只有新的瞬态物理问题无法由已有证据回答 -> 才允许新增 HSPICE
```

禁止为了“保险”“回归”“顺便确认”重新执行：

```text
完整 startup calibration
M0 local surface
M0 trip sweep
M1 RTL/SDF
M1-T STA
RF 系列
XA 全链路
T0-2 纠偏四点
T0-2 纠偏后正式十二点
```

特别规定：

> **修改 `run_t0_transient_droop_characterization.py` 导致源码哈希变化，不构成重跑 T0-2 的理由。T0-2 已经通过的物理证据必须通过冻结的结果文件、场景 deck 哈希、提交 SHA 和纠偏合同继续引用。**

每一阶段报告必须明确记录：

```text
本阶段新增 HSPICE 场景数
复用旧场景数
仅重解析场景数
禁止流程新增运行数
```

如果某一步必须重跑旧实验，报告中必须写清楚**为什么现有原始证据不能回答当前问题**，否则视为流程违规。

---

# 16. 推荐任务目录

```text
delay_chain/ftc/analysis/t0_transient_droop/
├── baseline/
│   └── frozen_input_sha256.json
├── contract/
│   ├── T0_TRANSIENT_THREAT_CONTRACT.json
│   └── T0_DOWNSTREAM_D0_TIMING_CONTRACT.json
├── correction/
│   ├── constant_low_equivalence_audit.json
│   ├── correction_audit.json
│   ├── four_point_results.csv
│   ├── four_point_summary.json
│   ├── formal_12_results.csv
│   ├── formal_12_summary.json
│   └── legacy_62_scenarios_marker.json
├── long_pulse_consistency/
│   └── 历史纠偏前结果及其 superseded 标记
├── phase_window/
├── amplitude_duration/
├── phase_coverage/
├── cadence/
├── figures/
├── scripts/
└── reports/
    ├── T0_GATE_STATUS.json
    └── FTC_T0_TRANSIENT_DROOP_CHARACTERIZATION.md
```

大体积 HSPICE deck/listing/waveform 放 task-owned run 目录并忽略；提交机器可读摘要、代表性证据、正式图和可重复脚本。

---

# 17. Codex 严格逐阶段执行顺序

当前正确执行序列更新为：

```text
T0-0  瞬态威胁 / 相位 / 波形合同                         已完成
  ↓
T0-1  当前 FTC 瞬态单次检测 runner                      已完成并纠偏
  ↓
T0-2  本地 VDD 归一化后的长脉冲静态→瞬态一致性         CORRECTED PASS
  ↓
T0-2E 证据闭合 + 旧 STOP superseded + T0-3 解封          ← 当前下一步，0 HSPICE
  ├─ FAIL -> 只修证据/代码，不运行新物理扫描
  ↓ GO
T0-3  两个 L2 代表点提取相位敏感窗口
  ├─ FAIL -> STOP，不扩大到六个 margin
  ↓ GO
T0-4  六个 margin 自适应提取 DeltaV→minimum duration
  ↓
T0-5  代表边界点做完整 phase coverage
  ↓
T0-6  用已有 phase 数据反推未来最大 probe period / cadence
  ↓
T0-7  冻结 <0.80 V fail-safe 下游需求
  ↓
T0-8  论文级图 + 正式报告 + T0 GO / CONDITIONAL_GO / NO-GO
```

任何后续入口都不得隐式重新调用 T0-2 HSPICE。

---

# 18. 宏观防跑偏原则

Codex 在整个 T0 必须始终遵守以下方向：

> **T0 的任务是测清楚当前冻结传感器的瞬态物理能力，不是继续优化 M1，不是重做 M0，不是提前写 D0，也不是为了得到漂亮结果去扩大架构。T0-2 已经在正确的本地 VDD 归一化接口抽象下纠偏通过，后续不得因脚本修改重新跑 T0-2；先用零 HSPICE 完成证据解封，再只用两个 L2 代表点找出真实时间敏感窗口，并用采样时刻的本地 VDD 对真实 DFF 双采样进行判决。只有 T0-3 机制清楚后才扩大到六个 margin 的深度—持续时间边界，最后才用已有相位数据推导运行时检测间隔。任何已有证据能回答的问题都禁止通过重跑仿真回答；任何物理机制没有通过停止门的问题都禁止用更复杂的数字逻辑绕过去。**

---

# 19. T0 结束后的唯一正确下一步

只有 T0 最终给出 GO 或带明确 cadence 条件的 CONDITIONAL_GO，才允许进入：

```text
D0：运行时检测状态机
```

D0 才负责：

```text
运行时 reset/S_CLK 序列
probe cadence
Q 双采样判决
报警锁存/清除
状态寄存器
低于 0.80 V 的 heartbeat / stuck-Q / timeout 失效保护
```

总体路线冻结为：

```text
H0    校准→检测所有权切换                       PASS
 ↓
M0    静态检测裕量 / 静态触发电压               CONDITIONAL_GO（仅范围边界）
 ↓
M1    精确检测配置 / 安全装载                    GO
 ↓
M1-T  检测配置时序证据闭合                       PASS
 ↓
T0-2  瞬态长脉冲静态一致性                       CORRECTED PASS
 ↓
T0-2E 证据闭合与 T0-3 解封                       当前下一步
 ↓
T0-3~8 瞬态深度×持续时间×相位 + 检测间隔         待执行
 ↓
D0    运行时检测状态机 / 判决 / 报警 / 失效保护
 ↓
V0/V1 完整控制器 + 混合信号 + 晶体管级瞬态闭环
```
