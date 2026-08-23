# FTC T0 瞬态电压跌落检测能力表征逐阶段推进计划

**仓库：** `Peiki0622/power_macro`  
**目标分支：** `main`  
**T0 输入基线：** `46ebf25e9bb15aba29be23f79e8aa3ed8b8ad474`  
**阶段定位：** H0 校准→检测所有权切换已通过，M0/M0-E 静态检测裕量与静态触发电压已闭合，M1 可编程检测配置已通过，M1-T 时序证据已闭合；T0 只研究当前已冻结传感器面对真实瞬态电压跌落时的物理检测边界，并为后续 D0 运行时检测状态机给出必须满足的检测时序合同。

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

T0 必须把以下内容视为只读基线，非必要不得重跑：

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

**核心原则：** T0 只新增“现有静态数据回答不了的瞬态物理问题”的仿真。能由已有 CSV/JSON/报告直接复用的内容一律不得通过重新跑仿真获得。

---

# 3. T0 的正式研究范围

## 3.1 正式检测工作点

只把以下六个工作点定义为正式瞬态检测候选：

```text
0.95 V：L1 / L2 / L3
1.10 V：L1 / L2 / L3
```

L0 只作为正常/控制工作点，不用于宣称 droop trip 能力。

0.80 V 的 L0-L3 只可用于必要的合法性或正常点控制，不允许在 T0 中升级为 `<0.80 V` 正式检测能力。

## 3.2 唯一权威判决

真实 DFF 的 Q 结果以及后续双采样可解释状态是唯一检测判据。

```text
R = W_xor - D_ref
```

只能作为机理解释量，不得替代真实 DFF 判决。

---

# 4. T0-0 —— 冻结瞬态威胁与单次检测实验合同

本阶段不运行 HSPICE。

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

其中 `phase` 必须统一定义为：

> 电源下降开始时刻相对于本次真实检测参考事件的时间偏移。

默认优先以本次检测 `S_CLK` 上升沿作为零时刻；如果实际 M0 单次 probe 的更底层物理事件更适合作为参考，可以改用固定且唯一的参考事件，但一旦 T0-0 冻结后后续所有 sweep 必须使用同一相位定义。

## 4.2 不允许理想电压跳变

PWL 不允许同一时刻从 Vbase 直接跳到 Vdroop。必须有非零 `t_fall/t_rise`。

若仓库没有当前 FTC 已正式冻结的电源下降斜率，则 T0-0 可以选一个主研究斜率作为**实验假设**，同时再保留一个较慢斜率作为斜率敏感性检查；不得把这个选择写成“真实芯片 PDN 已证明的边沿速度”。

## 4.3 推荐合同文件

```text
delay_chain/ftc/analysis/t0_transient_droop/contract/T0_TRANSIENT_THREAT_CONTRACT.json
```

至少记录：

```text
正式 Vbase 列表
正式 margin 列表
波形定义
相位零点定义
主 t_fall / t_rise
备用斜率
正式最低电压下限 0.80 V
真实 DFF 为唯一判决
R 仅为诊断量
```

## 4.4 Gate

合同冻结后才允许进入 T0-1。

**新增 HSPICE：0。**

---

# 5. T0-1 —— 建立当前 FTC 专用瞬态单次检测 runner

## 5.1 宏观原则

不得新建一套脱离 M0 的近似传感器模型。

必须从当前 M0 已验证的物理单次检测 runner / deck renderer 派生，保持：

```text
当前 FTC_SENSOR
当前 medium/fine 拓扑
当前 XOR
当前真实 DFF
当前 M1 精确 M_det/F_det
当前单次 probe 时序
```

唯一新增物理变量是：

```text
VDD_MONITORED 从恒定电压改为参数化 PWL 瞬态
```

## 5.2 优先复用已有基础设施

优先复用当前仓库已有的：

- M0 physical renderer；
- `run_m0_detection_margin_characterization.py` 中已验证的 sensor/XOR/medium/fine/DFF 渲染逻辑；
- `run_dynamic_startup_calibration_protocol.py` 中当前 FTC 的实际物理拓扑语义；
- 仓库历史 PWL runner 的有限斜率、波形参数校验、场景 manifest、resume、HSPICE 完成性检查等工程机制。

可以借用旧 PWL 工具的“软件工程方法”，但**不能借用旧 Vernier 传感器的数值结论或电路结构**。

## 5.3 建议 runner

```text
delay_chain/ftc/scripts/run_t0_transient_droop_characterization.py
```

建议每个场景输出紧凑字段：

```text
scenario_id
Vbase
margin_level
M_det
F_det
DeltaV_mv
Vdroop_v
t_fall_ps
t_hold_ps
t_rise_ps
phase_ps
实际最小 VDD
W_xor_ps
D_ref_ps
R_ps
Q_sample_1
Q_sample_2
Q_final
检测状态
HSPICE 完成性
源数据 hash
```

大体积 deck、listing、波形仍放 task-owned run 目录并忽略，只提交紧凑 CSV/JSON 和必要代表性波形。

## 5.4 Gate

在真正进行大规模 transient sweep 前，先完成少量 dry-run / 单元测试，证明：

```text
恒定 VDD 模式可以退化回 M0 单次检测语义
M/F 编码与 M1 codebook 完全一致
F10 仍等于 0000000000
相位只改变 droop 时刻，不改变 probe 时序
PWL 无理想跳变
Q 读取仍使用真实 DFF
```

此阶段只允许极少量必要的 smoke HSPICE，不允许直接展开完整六个 margin sweep。

---

# 6. T0-2 —— 长脉冲静态→瞬态一致性硬门

这是 T0 第一轮正式新物理仿真，也是第一个必须通过的停止门。

## 6.1 目的

证明新 transient deck 在“足够长、足够早到达低电压”的极限下，与 M0 静态结果具有一致的物理方向和触发顺序。

## 6.2 场景选择原则

不要重新扫完整静态电压。

直接从已有 M0/M0-E `trip_sweep.csv / trip_summary.json` 读取每个候选已经存在的：

```text
last Q=0 电压
first Q=1 电压
```

对六个正式候选，每个只运行必要的少量 long-pulse 场景。

PWL 必须在真正的有效 sensing interval 之前已经稳定到目标 Vdroop，并保持到 Q 双采样完成之后，使其近似静态低电压。

## 6.3 通过标准

每个候选至少应满足：

```text
原 static last-Q0 点仍不应无原因变成稳定 Q1
原 static first-Q1 点应能保持进入检测区
L1/L2/L3 的总体 ordering 不得颠倒
```

允许有限斜率和瞬态初始化带来很小差异，但如果 long-pulse 连静态方向都无法复现：

```text
T0-2 = STOP
```

此时只允许检查 transient deck、时间参考、PWL source、测量定义，不得直接扩大 sweep，也不得回头重跑完整 M0。

## 6.4 新仿真控制

此阶段严格只跑 long-pulse consistency 所需场景，不要顺手跑 duration/phase 网格。

---

# 7. T0-3 —— 中等裕量的相位敏感窗口试探

只有 T0-2 通过才执行。

## 7.1 先只研究两个代表点

优先选择：

```text
0.95 V 的 L2：M5/F6
1.10 V 的 L2：M3/F8
```

理由：L2 位于三个检测裕量的中间位置，更适合先用来判断当前结构是否存在清楚的相位敏感窗口。

不要一开始就对六个 margin 做完整 phase sweep。

## 7.2 固定 amplitude 和 duration，只扫 phase

为每个代表点选择一个已经明显进入 static Q1 区、但仍高于 0.80 V formal floor 的 droop depth；固定一个足够覆盖 sensing 区域的 duration，只移动 droop 相对于 probe 的开始时刻。

先 coarse phase sweep，找到：

```text
始终 Q0 的区域
Q0/Q1 转换边界
稳定 Q1 的区域
恢复到 Q0 的区域
```

再只对转换附近做 fine sweep。

## 7.3 必须输出

```text
phase -> Q 状态
phase -> R
phase -> 实际最小 VDD
phase -> droop 与 XOR/CK/Q 的相对位置
```

并提取：

```text
单 probe 时间敏感窗口
单 probe 时间盲区
窗口宽度
窗口相对于 S_CLK 的中心/边界
```

## 7.4 Gate

如果两个代表点都表现出可解释的 phase-sensitive detection window：

```text
T0-3 = GO
```

如果 phase 行为高度混乱、没有可重复边界，先检查物理波形和 Q 判决，不要直接跑六个 margin。

---

# 8. T0-4 —— 六个正式工作点的“跌落深度—最短可检测持续时间”边界

只有 T0-3 通过才执行。

## 8.1 禁止暴力二维网格

不得直接做巨大 `DeltaV × duration` 笛卡尔积。

每个正式候选采用**自适应 bracket + refine**：

```text
固定 DeltaV
先粗略改变 duration 找到 Q0/Q1 边界
然后只在边界附近细化
得到该 DeltaV 下的 minimum detectable duration
```

再换下一个 DeltaV。

## 8.2 amplitude 选择

不同 margin 不共用一套绝对 mV 列表。

每个候选以自己的 M0 static Vtrip 为锚，至少选择：

```text
略浅于 static trip 的控制点
接近 static trip 的点
明显深于 static trip 的点
必要时再增加 1-2 个中间点
```

所有正式场景必须满足：

```text
Vdroop >= 0.80 V
```

若为了研究某个 1.10 V/L3 候选需要更深跌落，也仍不得越过 0.80 V formal floor 后继续宣称精确 timing detection。

## 8.3 单调性审计

在相同 phase 下，应检查：

```text
跌落更深，检测不应系统性变差
持续时间更长，检测不应系统性从 Q1 反转为 Q0
```

任何 `Q1 -> Q0` 反转必须保留为异常场景并检查，不得在后处理中平滑或删除。

## 8.4 核心输出

最终每个候选形成：

```text
DeltaV -> minimum detectable duration
```

并保留原始 bracket 点。

---

# 9. T0-5 —— 将 duration 边界放回完整 phase，量化时间覆盖率

T0-4 得到的是特定有利/代表 phase 下的边界，不能直接等价为任意时间到达都可检测。

## 9.1 代表场景选择

每个 baseline 至少选：

```text
一个接近 detection boundary 的场景
一个明显可检测的场景
```

必要时优先覆盖 L1/L2/L3 中差异最大的 margin。

## 9.2 完整 phase sweep

将攻击开始时刻在一个完整 probe interval 内移动，统计：

```text
总 phase 点数
检测到的 phase 点数
phase coverage fraction
连续 blind window 最大宽度
是否存在所有 phase 都能检测的 guaranteed region
```

## 9.3 结果必须区分三个概念

```text
最佳相位可检测
时间覆盖率
全相位保证检测
```

禁止把“某个 phase 能检测 1 ns droop”写成“保证检测 1 ns droop”。

---

# 10. T0-6 —— 由物理相位窗口反推未来运行时检测间隔

这一阶段不写 D0 RTL。

## 10.1 目标

根据 T0-3/T0-5 的真实时间敏感窗口，计算或用轻量事件级仿真推导：

```text
probe period
目标 droop duration
最坏攻击 phase
检测覆盖率
```

之间的关系。

## 10.2 不要默认检测频率等于 400 MHz

当前 400 MHz 是校准/所有权/配置控制时钟，不自动等于未来 runtime detection cadence。

T0 必须先回答：

```text
现有 400 MHz 能否满足目标 threat class？
```

如果可以：

```text
未来 D0 可以优先复用 400 MHz 节拍
```

如果不可以：

```text
T0 输出“需要更快的专用运行时检测时序”约束
```

但 T0 不得自行设计新的高速时钟、DLL、分频器或 detector FSM。

## 10.3 允许轻量后处理

该阶段优先使用 T0 已有 phase-window 数据做数学/脚本级覆盖率推导，不应为了每一个 probe period 都新跑一套 HSPICE。

只有当简单窗口叠加无法描述真实多次 probe 物理交互时，才允许增加极少量多 probe HSPICE 验证。

---

# 11. T0-7 —— `<0.80 V` 严重欠压的失效保护语义

本阶段不要求新 HSPICE。

## 11.1 明确边界

当前正式精确 timing detection 只在：

```text
VDD_MONITORED >= 0.80 V
```

范围内讨论。

低于 0.80 V 时：

- 传感路径标准单元可能进入未正式表征区；
- DFF 行为也不能继续当作精确时间比较器；
- 因此不得通过几条深跌落波形宣称精确 Vtrip 能力。

## 11.2 给 D0 的要求

T0 应输出一个清楚的下游需求：

```text
低于正式工作范围时，D0 应使用 heartbeat / stuck-Q / timeout / 无有效检测结果 等失效保护语义，
而不是继续依赖精细 timing trip 数值。
```

T0 只定义需求，不实现 RTL。

---

# 12. T0-8 —— 正式论文级证据、图和最终 Gate

## 12.1 必须形成的核心图

至少形成以下五类正式图：

### 图 T0-1：代表性瞬态波形

同一时间轴显示：

```text
VDD_MONITORED
XOR 有效脉冲/窗口
采样 CK
真实 Q
```

并清楚标注 droop 的下降、保持、恢复和相位。

### 图 T0-2：单 probe 时间敏感窗口

横轴：attack phase；
纵向/符号：Q0/Q1 或检测状态；
同时给出相位边界和盲区。

### 图 T0-3：跌落深度—持续时间二维检测边界

至少分别展示 0.95 V 和 1.10 V。

### 图 T0-4：跌落深度—最短可检测持续时间

同一 baseline 下比较 L1/L2/L3，强调 programmable margin 对 transient capability 的影响。

### 图 T0-5：检测间隔—时间覆盖率/保证检测关系

用于直接支撑未来 D0 cadence 选择。

## 12.2 绘图环境

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

---

# 13. T0 最终判定标准

## 13.1 T0 = GO

至少满足：

1. 长脉冲 transient 与 M0 static Q0/Q1 ordering 一致；
2. 0.95 V 和 1.10 V 都存在可解释、可重复的瞬态检测区域；
3. 六个 trip-qualified margin 的 `DeltaV -> minimum detectable duration` 已提取；
4. 相位敏感窗口和盲区已量化；
5. 不存在大量无法解释的“更深/更长反而稳定漏检”反转；
6. 至少针对一个明确 threat class，可以推导出可实现的最大 probe period；
7. 已区分“最佳相位可检测”“覆盖率”“全相位保证检测”；
8. `<0.80 V` 已明确转为失效保护语义；
9. 论文级图和机器可读合同完整；
10. 没有无意义重跑 H0/M0/M1/M1-T 已完成仿真。

## 13.2 T0 = CONDITIONAL_GO

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

> 未来 D0 需要满足由 T0 推导出的更短 probe period / 更高 runtime detection cadence。

不得把不足的 phase coverage 隐藏成普通 GO。

## 13.3 T0 = NO-GO / STOP

以下情况至少任一出现，应停止进入 D0：

```text
long-pulse 无法重现 M0 静态方向
真实 DFF Q 与预期物理机制持续矛盾
phase 行为无可重复边界
amplitude-duration 关系出现大量不可解释反转
即使最佳 phase + 足够长 pulse 也无法得到稳定检测区域
```

NO-GO 后先检查 transient physical sensing 机制和 deck，不得用更复杂的数字 FSM 掩盖物理问题。

---

# 14. 仿真预算与“非必要不重跑”规则

Codex 必须遵守以下优先级：

```text
已有 JSON/CSV/报告可回答 -> 直接复用，仿真数 0
已有 raw run 可重解析 -> 重解析，仿真数 0
只缺后处理 -> 只做后处理，仿真数 0
只有新的 transient 物理问题无法由已有证据回答 -> 才允许新增 HSPICE
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
```

每一阶段报告必须明确记录：

```text
本阶段新增 HSPICE 场景数
复用旧场景数
仅重解析场景数
禁止流程新增运行数
```

如果某一步必须重跑旧实验，报告中必须写清楚**为什么现有原始证据不能回答当前问题**，否则视为流程违规。

---

# 15. 推荐任务目录

```text
delay_chain/ftc/analysis/t0_transient_droop/
├── baseline/
│   └── frozen_input_sha256.json
├── contract/
│   ├── T0_TRANSIENT_THREAT_CONTRACT.json
│   └── T0_DOWNSTREAM_D0_TIMING_CONTRACT.json
├── long_pulse_consistency/
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

# 16. Codex 严格逐阶段执行顺序

```text
T0-0  冻结 transient threat / phase / waveform 合同
  ↓
T0-1  从 M0 renderer 派生当前 FTC transient single-probe runner
  ↓
T0-2  六个 qualified margin 的 long-pulse static→transient 一致性硬门
  ├─ FAIL -> STOP，只查 deck/时序/判决
  ↓ GO
T0-3  只用两个 L2 代表点提取 phase sensitivity window
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

---

# 17. 宏观防跑偏原则

Codex 在整个 T0 必须始终遵守以下方向：

> **T0 的任务是测清楚当前冻结传感器的瞬态物理能力，不是继续优化 M1，不是重做 M0，不是提前写 D0，也不是为了得到漂亮结果去扩大架构。先用最少的新 HSPICE 证明 long-pulse 与静态证据一致，再用两个代表点找出时间敏感窗口，只有机制清楚后才扩大到六个 margin 的深度—持续时间边界，最后才用已有相位数据推导运行时检测间隔。任何已有证据能回答的问题都禁止通过重跑仿真回答；任何物理机制没有通过停止门的问题都禁止用更复杂的数字逻辑绕过去。**

---

# 18. T0 结束后的唯一正确下一步

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
H0    校准→检测所有权切换                 PASS
 ↓
M0    静态检测裕量 / 静态触发电压         CONDITIONAL_GO（仅范围边界）
 ↓
M1    精确检测配置 / 安全装载              GO
 ↓
M1-T  检测配置时序证据闭合                 PASS
 ↓
T0    瞬态深度×持续时间×相位 + 检测间隔    ← 当前阶段
 ↓
D0    运行时检测状态机 / 判决 / 报警 / 失效保护
 ↓
V0/V1 完整控制器 + 混合信号 + 晶体管级瞬态闭环
```
