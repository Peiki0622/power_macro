# FTC 标准单元负载细调级及单中调步长覆盖逐步骤执行计划

## 0. 本阶段任务定位

本计划承接已经完成并判定为 `GO` 的路径选择中调级（path-selection medium stage，路径选择式中等粒度调节级）。当前已完成提交为：

```text
d376ff58e8a4f432d38e189d5b7d566c639afe20
feat(ftc): validate path-selection medium stage
```

当前设计主线固定为：

```text
已完成：路径选择中调级
        |
        +-- GO
        |
        v
本计划：标准单元负载细调级
        |
        +-- 证明细调代码产生严格正的真实延时增量
        +-- 证明单个细调步长显著小于中调步长
        +-- 证明完整细调范围可以覆盖一个真实中调步长
        |
        v
本计划到此停止
        |
        v
下一独立计划：旁路 + 配置跳过
        |
        v
后续：完整“中调 + 细调”两级可编程延时线
        |
        v
后续：tap29 传感器 + 异或门 + D触发器 + 启动自校准
        |
        v
后续：锁定码 + 可编程裕量的电压跌落检测
```

**本计划只回答两个问题：**

> **问题 1：标准单元输入负载状态变化能否提供严格单调、稳定且明显小于中调步长的真实细调延时步长？**

> **问题 2：有限数量的细调负载单元能否在三个电压锚点下覆盖一个真实中调代码间隔，使“当前中调码 + 最大细调”能够达到或超过“下一中调码 + 最小细调”？**

若本计划 `GO`，只表示“标准单元负载细调级以及一个中调步长覆盖”可以进入下一阶段的旁路与两级集成；**不表示完整 FTC 检测宏已经 GO。**

## 0.1 最大 LVT 后续实验的已授权门限

最大尺寸 LVT 负载的独立 follow-on 可以将输出高电平门限从：

```text
output_logic_high >= 0.90 × VDD
```

调整为：

```text
output_logic_high >= 0.88 × VDD
```

该调整只适用于使用 `--max-lvt-load` 的新证据 revision；原始 0.90 × VDD
证据必须保留且不得覆盖。低电平门限 `output_logic_low <= 0.10 × VDD`、
无额外转换、正传播延时、边沿测量、单调性、耦合覆盖和 `K <= 64` 的全部
要求保持不变。最终报告必须显式说明该非默认门限，不能声称满足原始 0.90 ×
VDD 规则。

## 0.2 中间尺寸 LVT 负载扫描的已授权边界

在保留 X0P5 默认证据和 X8 maximum-LVT follow-on 证据不变的前提下，允许
一个独立的中间尺寸扫描 revision。扫描尺寸固定为：

```text
X0P7, X1, X1P4, X2, X3, X4, X6
```

对每个尺寸和每个 NAND2/NOR2 逻辑族，必须从真实 LVT CDL 的 A/B/M 物理
实现中静态选择晶体管总宽度最大的一个；总宽度相同则优先 M，再按单元名
排序。每个选定单元必须保留 signal=A/control=B 与 signal=B/control=A 两个
方向，因此静态候选数量固定为 28。该有限集合不是无边界库 sweep。

扫描使用原始波形合同：

```text
output_logic_high >= 0.90 × VDD
output_logic_low  <= 0.10 × VDD
```

0.88 × VDD 例外继续只属于已完成的 --max-lvt-load X8 follow-on。每个候选
必须用三电压、K_test=8、F=0..8 的真实 HSPICE 数据同时发布单位调节量、
K_candidate、最大 10%-90% 输出建立时间和最大相邻细调步长。满足原有
波形、单调性、K<=64 和细调步长小于冻结中调最小步长 Gate 的候选，按最小
K、最大归一化细调步长、最大建立时间、candidate_id 的顺序选择唯一赢家。
只有该赢家允许继续原计划的完整 K 耦合覆盖与分辨率验收；历史中调场景和
历史 runner 均不得重跑。

若四指标排序第一的候选在完整耦合验收中出现真实电气 Gate 失败，而不是
HSPICE/measurement 工具失败，则允许只对排序第二的候选执行一次同样的完整
验收。最多验证两个候选，不允许继续向第三、第四名扩展；两个候选都失败后
才发布本轮最终 NO-GO。第二候选必须复用已经完成的 8 单元扫描结果，不得
重复 927 个尺寸扫描场景。

---

# 1. Codex 开始前必须读取并冻结的现有证据

## 1.1 当前中调级 GO 证据：只读，不重跑

必须读取：

```text
delay_chain/ftc/analysis/path_selection_medium_stage/summary.json
delay_chain/ftc/analysis/path_selection_medium_stage/future_fine_stage_interface.json
delay_chain/ftc/analysis/path_selection_medium_stage/future_range_projection.json
delay_chain/ftc/analysis/path_selection_medium_stage/cell_contract.json
delay_chain/ftc/analysis/path_selection_medium_stage/requirements.json
delay_chain/ftc/analysis/path_selection_medium_stage/n8_step_envelope.json
delay_chain/ftc/analysis/path_selection_medium_stage/medium_step_characterization.csv
delay_chain/ftc/analysis/path_selection_medium_stage/scaling_endpoints.csv
delay_chain/ftc/reports/FTC_PATH_SELECTION_MEDIUM_STAGE.md
delay_chain/ftc/scripts/run_path_selection_medium_stage.py
```

必须冻结以下事实：

```text
Path-Selection Medium Stage = GO

N_characterize = 16

Anchor VDD = 1.10, 0.95, 0.80 V

N=16 最大已测中调步长：
1.10 V : 33.703762 ps
0.95 V : 44.069195 ps
0.80 V : 66.862606 ps

全局已测最坏中调步长：
66.862606 ps

N=16 最小已测中调步长：
1.10 V : 10.232424 ps
0.95 V : 13.209050 ps
0.80 V : 20.958529 ps
```

还必须冻结：

```text
当前中调延时缓冲器：BUF_X0P7M_A9TL40
当前中调 2:1 多路选择器：MXT2_X0P5M_A9TL40
MXT2 选择语义：S0=0 选择 A，S0=1 选择 B
MXT2 输出极性：同极性
```

上述 41 个中调 HSPICE 场景全部视为已完成只读证据，**不得重新运行。**

## 1.2 中调级当前输出负载条件必须明确记录

当前中调级 HSPICE 表征的输出负载条件为：

```text
intrinsic_y0_mux_output_no_external_receiver
```

即中调输出端没有外部接收器。

因此：

```text
66.862606 ps
```

只能作为已经完成的“无外接细调结构条件下的最坏已测中调步长”，**不能直接作为最终两级结构永远不变的常数。**

本阶段细调驱动器和负载阵列接入后，必须重新测量耦合条件下的相邻中调步长。

## 1.3 历史更早 runner 全部继续只读

禁止调用：

```text
delay_chain/ftc/scripts/run_static_self_calibration.py
delay_chain/ftc/scripts/run_programmable_acceptance_window.py
delay_chain/ftc/scripts/run_delay_code_refinement.py
delay_chain/ftc/scripts/run_fine_grained_controllable_delay.py
delay_chain/ftc/scripts/run_path_selection_medium_stage.py
```

可以复用经过审查的通用 HSPICE listing / measurement 完整性辅助函数，但禁止 import 或 subprocess 调用这些历史 runner 的主执行流程。

---

# 2. 本轮固定的细调物理结构

## 2.1 固定加入一个细调驱动缓冲器

本轮不要把可变负载直接挂在中调最后一级多路选择器输出上。

固定结构为：

```text
路径选择中调级
      |
      v
 MEDIUM_OUT
      |
      v
+------------------------+
| 固定细调驱动缓冲器       |
| BUF_X0P7M_A9TL40        |
+-----------+------------+
            |
            +----------------------> FINE_OUT
            |
            +-- 可变负载 V0
            +-- 可变负载 V1
            +-- 可变负载 V2
            |        ...
            +-- 可变负载 V(K-1)
```

这里 `K` 表示细调可变负载单元总数。

固定细调驱动器的目的：

```text
1. 将细调负载变化主要隔离在固定驱动器之后；
2. 避免直接改变中调最后一级 MUX 的负载而污染中调自身物理含义；
3. 为下一阶段“旁路 + 细调路径”提供清晰接口；
4. 复用已经验证过的同极性 BUF_X0P7M_A9TL40，不重新搜索驱动器。
```

本计划不允许为了优化固定开销而扫描其他驱动器。如果该结构本身 NO-GO，应记录原因并停止；不要在同一 runner 内无限救援。

## 2.2 标准单元负载不是串联主传播门

每个细调单元必须作为**并联输入负载**接在 `FINE_OUT` 上，而不是串在主传播路径上。

抽象结构：

```text
                         可变负载单元 Vi

FINE_OUT ----------------> signal_pin
                           +-----------+
控制 fi ----------------->| control_pin|
                           | NAND/NOR   |----> zi
                           +-----------+

zi 不回接主传播路径
```

这里 `Vi` 表示第 `i` 个细调可变负载单元；`fi` 表示控制该负载高/低输入电容状态的数字控制；`zi` 是该标准单元自己的输出内部节点，不参与主信号传播。

## 2.3 不预先假定 NAND 还是 NOR

Codex 必须从 SMIC40LL 实际 LVT（低阈值电压）标准单元 Verilog/CDL 中静态发现：

```text
最小尺寸二输入 NAND 类单元
最小尺寸二输入 NOR 类单元
```

对于同一个逻辑单元：

```text
signal=A, control=B
```

和：

```text
signal=B, control=A
```

允许作为两个不同物理候选，因为不同输入脚对应的晶体管堆叠位置和输入电容可能不同。

禁止直接假定：

```text
control=1 一定是高电容状态
```

或：

```text
control=0 一定是低电容状态
```

必须由真实 HSPICE 延时结果确定。

---

# 3. 新 runner、目录和证据文件

新增：

```text
delay_chain/ftc/scripts/run_standard_cell_load_fine_stage.py

delay_chain/ftc/analysis/standard_cell_load_fine_stage/

delay_chain/ftc/runs/standard_cell_load_fine_stage/r1/

delay_chain/ftc/reports/FTC_STANDARD_CELL_LOAD_FINE_STAGE.md

delay_chain/ftc/tests/test_standard_cell_load_fine_stage.py
```

输出至少包括：

```text
requirements.json
fine_varactor_candidates.json
selected_fine_load_contract.json
single_load_screen.csv
single_load_decision.json
fine8_code_sweep.csv
fine8_summary.json
fine_bank_sizing.json
full_bank_coverage.csv
full_bank_monotonicity.csv
coupled_medium_coverage.csv
future_bypass_interface.json
summary.json
```

---

# 4. 防重复仿真与可恢复执行契约

每个新场景 ID 至少由以下字段决定：

```text
phase
topology_version
medium_N
medium_code
medium_mux_cell
medium_delay_cell
fine_driver_cell
fine_load_cell
signal_pin
control_pin
low_cap_control_value
high_cap_control_value
K
fine_code
vdd_v
input_slew_contract
output_load_contract
```

每个场景目录必须保存：

```text
scenario_manifest.json
```

至少包含：

```text
netlist_sha256
runner_sha256
requirements_sha256
candidate_contract_sha256
parameters
completion_status
measurement_file
```

只有以下条件全部满足时才能直接复用：

```text
completion_status = PASS
netlist_sha256 完全一致
runner_sha256 完全一致
requirements_sha256 完全一致
candidate_contract_sha256 完全一致
参数完全一致
listing 和 measurement 完整
```

任何哈希变化都必须创建新的 run revision，不得覆盖旧 raw run。

---

# Phase 0 — 冻结本阶段输入和停止边界（0 个新 HSPICE）

## Step 0.1：生成 requirements.json

输出：

```text
delay_chain/ftc/analysis/standard_cell_load_fine_stage/requirements.json
```

至少记录：

```text
medium_stage_decision = GO
medium_topology_version = path_selection_medium_stage_v1
N_characterize = 16
anchor_vdd_v = [1.10, 0.95, 0.80]

published_medium_step_max_ps:
1.10 = 33.703762
0.95 = 44.069195
0.80 = 66.862606

published_medium_step_min_ps:
1.10 = 10.232424
0.95 = 13.209050
0.80 = 20.958529

published_global_worst_medium_step_ps = 66.862606

fine_driver_cell = BUF_X0P7M_A9TL40

bypass = future_work
config_skip = future_work
sensor = forbidden
xor = forbidden
dff = forbidden
calibration = forbidden
droop = forbidden
pvt = forbidden
rtl = forbidden
power = forbidden
area = forbidden
layout = forbidden
```

同时记录所有冻结输入文件 SHA256。

## Step 0.2：本阶段最终级数都不得冻结

必须明确：

```text
final_medium_N_frozen = false
final_fine_K_frozen = false
```

本轮得到的 `K_candidate` 只是在 TT/25 C（典型工艺、25 摄氏度）和当前无旁路条件下的候选值。下一阶段加入旁路和配置跳过后还需要重新确认。

---

# Phase 1 — 纯静态发现标准单元负载候选（0 个新 HSPICE）

## Step 1.1：从真实标准单元库解析候选

读取：

```text
delay_chain/ftc/discovery/selected_cells.json
```

使用其中已经冻结的 LVT Verilog/CDL 路径。

只允许发现：

```text
二输入 NAND 类
二输入 NOR 类
```

排除：

```text
时序单元
锁存器
触发器
三态单元
时钟专用单元
AOI/OAI 复杂逻辑
XOR/XNOR
多输入大逻辑门
```

## Step 1.2：候选 HSPICE 数量硬限制

最多允许：

```text
4 个“单元 + signal_pin 方向”物理候选
```

输出：

```text
fine_varactor_candidates.json
```

每个候选至少记录：

```text
cell
signal_pin
control_pin
output_pin
cdl_ports
verilog_ports
truth_function
vt_class
estimated_transistor_or_structure_note
source_file_sha256
```

如果没有任何合法候选，直接发布：

```text
Standard-Cell Load Fine Stage = ARCHITECTURE_BLOCKED
```

0 个新 HSPICE 结束。

---

# Phase 2 — 单个标准单元负载的真实电气筛选

## Step 2.1：先测固定细调驱动器基准

固定：

```text
medium_N = 16
medium_code = 8
VDD = 1.10, 0.95, 0.80 V
```

结构只包含：

```text
中调级 -> BUF_X0P7M_A9TL40 -> FINE_OUT
```

不接任何可变负载。

共：

```text
3 个新场景
```

测量至少包含：

```text
D_rise_ps
D_fall_ps
output_rise_time_ps
output_fall_time_ps
output_logic_high
output_logic_low
unexpected_transition_count
```

## Step 2.2：每个候选只测两种控制状态

对每个候选、每个锚点：

```text
control = 0
control = 1
```

最多 4 个候选，因此最大候选场景数：

```text
4 × 3 × 2 = 24
```

符号说明：`4` 是最多候选数量；`3` 是三个电压锚点；`2` 是控制端两种逻辑状态；`×` 表示乘法；结果 `24` 是候选负载筛选的最大新场景数。

加上固定驱动器 3 个基准：

```text
Phase 2 最大新 HSPICE = 27
```

## Step 2.3：由实测定义高负载和低负载状态

对每个候选、每个电压，定义：

```text
D_low(V)  = 两个控制状态中传播延时较小者
D_high(V) = 两个控制状态中传播延时较大者
Delta_cell(V) = D_high(V) - D_low(V)
```

符号说明：`D_low(V)` 表示供电电压 `V` 下低负载状态的传播延时；`D_high(V)` 表示同一电压下高负载状态的传播延时；`Delta_cell(V)` 表示单个负载单元切换状态带来的细调延时增量；`-` 表示两个延时相减；`=` 表示定义关系。

必须满足：

```text
Delta_cell(V) > 0
```

符号说明：`Delta_cell(V)` 是上述单个细调负载的真实延时增量；`>` 表示该增量必须严格为正。

而且高负载控制逻辑值在三个电压锚点必须保持一致。

例如若：

```text
1.10 V : control=1 更慢
0.95 V : control=1 更慢
0.80 V : control=0 更慢
```

则该候选直接淘汰。

## Step 2.4：单个细调步长必须小于中调最小步长

首轮 Gate 固定为：

```text
Delta_cell(V) < MediumStep_min(V)
```

符号说明：`Delta_cell(V)` 表示单个标准单元负载的细调延时增量；`MediumStep_min(V)` 表示已经完成的 N=16 中调级在相同供电电压下测得的最小中调步长；`<` 表示细调一步必须严格小于中调最小一步。

对应当前冻结值：

```text
1.10 V : Delta_cell < 10.232424 ps
0.95 V : Delta_cell < 13.209050 ps
0.80 V : Delta_cell < 20.958529 ps
```

同时要求：

```text
逻辑高低电平合法
无额外毛刺
上升沿传播可测
下降沿传播可测
输出转换时间没有失控
```

候选选择优先级：

```text
1. 三个锚点都满足细调一步小于中调最小步长；
2. 高/低负载控制语义跨电压稳定；
3. 预计覆盖一个中调步长需要的单元数量较少；
4. 低负载状态固定开销较小。
```

只允许选出一个首选细调负载结构继续。

输出：

```text
single_load_screen.csv
single_load_decision.json
selected_fine_load_contract.json
```

若无候选通过，立即 NO-GO，后续阶段全部 NOT_RUN。

---

# Phase 3 — 8 单元细调阵列：先证明代码单调性和位置稳定性

## 3.1 8 单元阵列结构

固定 `K_test = 8`：

```text
FINE_OUT
   +-- V0
   +-- V1
   +-- V2
   +-- V3
   +-- V4
   +-- V5
   +-- V6
   +-- V7
```

所有 8 个负载始终物理存在。

细调代码 `F` 使用连续开启编码：

```text
F=0 : 00000000
F=1 : 10000000
F=2 : 11000000
...
F=8 : 11111111
```

前 `F` 个负载处于高负载状态，其余负载处于低负载状态。

## Step 3.1：0.95 V 全代码扫描

固定：

```text
medium_N = 16
medium_code = 8
K_test = 8
VDD = 0.95 V
F = 0..8
```

共 9 个新场景。

定义相邻细调步长：

```text
delta_F(M,F,V) = D(M,F+1,V) - D(M,F,V)
```

符号说明：`M` 表示中调代码；`F` 表示当前细调代码；`V` 表示供电电压；`D(M,F,V)` 表示中调代码为 `M`、细调代码为 `F` 时从中调入口传播到细调输出的真实上升沿传播延时；`F+1` 表示细调代码增加一级；`delta_F(M,F,V)` 表示相邻两个细调代码的真实延时增量；`-` 表示传播延时相减。

必须满足所有：

```text
delta_F(M,F,V) > 0
```

符号说明：`delta_F(M,F,V)` 是相邻细调代码的延时增量；`>` 表示每次增加一个高负载单元后，传播延时必须严格增加。

## Step 3.2：1.10 V 和 0.80 V 做有界抽样

固定：

```text
medium_N = 16
medium_code = 8
VDD = 1.10, 0.80 V
F = 0,1,4,7,8
```

共 10 个新场景。

要求：

```text
D(0) < D(1) < D(4) < D(7) < D(8)
```

这里 `D(F)` 表示固定中调代码和固定电压下、细调代码为 `F` 时的传播延时；`<` 表示随着细调代码增加，延时必须严格增加。

## Step 3.3：检查浅/中/深中调位置依赖

在 0.95 V 再补：

```text
medium_code = 0, 15
F = 0,1,8
```

共 6 个新场景。

目标是检查：

```text
浅中调路径
中间中调路径
深中调路径
```

下的细调灵敏度是否保持同方向。

不要求不同 `M` 下的细调增量完全相等，但必须满足：

```text
high-load delay > low-load delay
```

且不能出现明显异常的负步长或失真。

Phase 3 新 HSPICE 最大数量：

```text
9 + 10 + 6 = 25
```

符号说明：`9` 是 0.95 V 下 9 个完整细调代码；`10` 是高低两个电压点各 5 个抽样代码；`6` 是浅、深两个中调位置各 3 个细调代码；`+` 表示场景数相加；结果 `25` 是 Phase 3 的最大新增场景数。

输出：

```text
fine8_code_sweep.csv
fine8_summary.json
```

---

# Phase 4 — 纯离线推导完整细调阵列数量（0 个新 HSPICE）

## Step 4.1：从 8 单元阵列得到实测细调范围

定义：

```text
FineRange_8(V) = D(M,8,V) - D(M,0,V)
```

符号说明：`FineRange_8(V)` 表示供电电压 `V` 下 8 个细调负载从全部低负载状态到全部高负载状态能够提供的真实延时范围；`D(M,8,V)` 表示细调代码为 8 时的传播延时；`D(M,0,V)` 表示细调代码为 0 时的传播延时；`M` 固定为当前中调表征代码；`-` 表示两个端点延时相减。

## Step 4.2：初步估计完整 K

对每个锚点：

```text
K_pred(V) = ceil(8 × MediumStep_max(V) / FineRange_8(V))
```

符号说明：`K_pred(V)` 表示供电电压 `V` 下预计至少需要多少个细调负载；`8` 是已经实测的小阵列单元数量；`MediumStep_max(V)` 是当前中调接口在同一电压下给出的最大已测中调步长；`FineRange_8(V)` 是 8 单元细调阵列的实测范围；`×` 表示乘法；`/` 表示除法；`ceil` 表示向上取整。

取：

```text
K_candidate = max(K_pred(1.10), K_pred(0.95), K_pred(0.80))
```

符号说明：`K_candidate` 表示三个电压锚点中最保守的完整细调阵列候选数量；`max` 表示取三个预测值中的最大值。

硬限制：

```text
K_candidate <= 64
```

如果：

```text
K_candidate > 64
```

则发布：

```text
Standard-Cell Load Fine Stage = NO-GO_FOR_BOUNDED_FINE_BANK
```

并停止，不允许自动扩展到更大的无限阵列。

输出：

```text
fine_bank_sizing.json
```

---

# Phase 5 — 完整 K 阵列：证明真实“一个中调步长覆盖”

这是本计划最核心的 Gate。

## Step 5.1：首先验证当前已知最坏中调位置 7 -> 8

当前 N=16 接口中，三个锚点的最大已测中调步长都位于或接近中层 `7 -> 8`。

对完整 `K_candidate` 阵列，三个锚点分别运行：

```text
M=7, F=0
M=7, F=K
M=8, F=0
```

这里 `M` 是中调代码，`F` 是细调代码，`K` 是完整细调阵列的最高合法细调代码。

三个电压共：

```text
9 个新场景
```

## Step 5.2：必须在细调已接入条件下重新定义中调步长

定义完整细调范围：

```text
FineRange(M,V) = D(M,K,V) - D(M,0,V)
```

符号说明：`FineRange(M,V)` 表示中调代码为 `M`、供电电压为 `V` 时，完整细调阵列从最低细调代码到最高细调代码能够提供的真实延时范围；`K` 表示完整细调阵列的最高代码；`D(M,K,V)` 和 `D(M,0,V)` 分别表示最大、最小细调代码的传播延时；`-` 表示两端延时相减。

定义耦合后的中调步长：

```text
MediumStep_coupled(M,V) = D(M+1,0,V) - D(M,0,V)
```

符号说明：`MediumStep_coupled(M,V)` 表示完整细调结构已经物理接入、但保持细调代码为 0 时，相邻两个中调代码的真实传播延时差；`M+1` 表示下一个中调代码；`0` 表示所有细调负载处于低负载状态；`-` 表示相邻两档传播延时相减。

真正的无空洞覆盖 Gate 是：

```text
D(M,K,V) >= D(M+1,0,V)
```

符号说明：左侧 `D(M,K,V)` 表示较低中调代码配合最大细调代码时的传播延时；右侧 `D(M+1,0,V)` 表示下一个中调代码配合最小细调代码时的传播延时；`>=` 表示当前中调档位的细调上限必须能够达到或越过下一中调档位的起点。

**不得只用历史 66.862606 ps 做静态比较后直接宣布覆盖。**

## Step 5.3：只允许一次 K 重估

如果某个电压出现：

```text
D(7,K,V) < D(8,0,V)
```

且：

```text
逻辑完整性正常
边沿质量正常
所有已测细调代码仍严格单调
```

只允许根据实际缺口重新估算一次：

```text
K_candidate -> K_rescaled
```

不允许：

```text
K=20
K=21
K=22
K=23
...
```

逐个暴力试探。

如果修正后的第二个 K 仍不能覆盖，则直接 NO-GO。

输出：

```text
full_bank_coverage.csv
```

---

# Phase 6 — 最终 K 的细调单调性和浅/中/深无空洞验证

## Step 6.1：0.95 V 唯一一次完整 K 全码扫描

固定最终候选 K：

```text
medium_N = 16
medium_code = 7
VDD = 0.95 V
F = 0..K
```

必须满足：

```text
D(7,0) < D(7,1) < ... < D(7,K)
```

这里 `D(7,F)` 表示中调代码固定为 7、细调代码为 `F` 时的传播延时；`<` 表示每增加一级细调代码，传播延时必须严格增加。

这是本计划**唯一允许的一次完整 K 细调代码扫描**。

## Step 6.2：1.10 V 与 0.80 V 只做有界抽样

在高低电压点，只验证：

```text
F = 0
F = 1
F ~= K/4
F ~= K/2
F ~= 3K/4
F = K-1
F = K
```

其中 `~=` 表示取最接近目标比例的合法整数代码；`K/4`、`K/2`、`3K/4` 分别代表约四分之一、二分之一和四分之三的细调范围。

要求：

```text
首步为正
末步为正
抽样代码顺序严格递增
逻辑高低电平合法
无额外毛刺
边沿质量可接受
```

## Step 6.3：浅、中、深三个代表中调边界都必须无空洞

最终验证：

```text
M = 0 -> 1
M = 7 -> 8
M = 15 -> 16
```

供电电压：

```text
1.10 V
0.95 V
0.80 V
```

每个组合直接检查：

```text
D(M,K,V) >= D(M+1,0,V)
```

符号说明：`M` 表示三个代表位置中的较低中调代码；`K` 表示最终完整细调阵列的最大代码；`V` 表示当前供电电压；左侧表示“当前中调档位 + 最大细调”的传播延时；右侧表示“下一中调档位 + 最小细调”的传播延时；`>=` 表示两个相邻中调档位之间不存在不可覆盖的延时空洞。

共：

```text
3 个中调位置 × 3 个电压 = 9 个覆盖组合
```

这些组合必须全部通过。

输出：

```text
coupled_medium_coverage.csv
full_bank_monotonicity.csv
```

---

# 7. 细调分辨率 Gate：范围覆盖并不等于细调成立

完整细调阵列除了必须覆盖一个中调步长，还必须保持“细调一步显著小于中调一步”的层级关系。

定义某电压下已测最大的相邻细调步长：

```text
delta_fine_max(V)
```

定义同一电压下、细调结构已接入时，浅/中/深三个代表位置中最小的耦合中调步长：

```text
MediumStep_coupled_min(V)
```

最终必须满足：

```text
delta_fine_max(V) < MediumStep_coupled_min(V)
```

符号说明：`delta_fine_max(V)` 表示供电电压 `V` 下所有已测相邻细调代码中最大的延时一步；`MediumStep_coupled_min(V)` 表示同一电压下细调结构已经物理接入后，三个代表中调位置中最小的相邻中调步长；`<` 表示最大的细调一步仍必须小于最小的中调一步。

本阶段真正需要同时满足：

```text
单个细调步长 < 中调步长
```

以及：

```text
多个细调步长累计范围 >= 一个中调步长
```

前者解决**分辨率**；后者解决**范围覆盖**。

---

# 8. 零代码固定开销：必须记录，但本轮不作为硬 NO-GO

## 8.1 固定细调驱动器开销

定义：

```text
Offset_driver(M,V) = D_driver_only(M,V) - D_medium_only(M,V)
```

符号说明：`D_driver_only(M,V)` 表示中调代码为 `M`、供电电压为 `V` 时，在中调输出后加入固定细调驱动缓冲器但尚未加入可变负载阵列的传播延时；`D_medium_only(M,V)` 表示已完成中调级在相同条件下的传播延时；`Offset_driver(M,V)` 表示细调驱动器引入的固定延时；`-` 表示两个传播延时相减。

## 8.2 完整负载阵列在细调代码 0 下的固定开销

定义：

```text
Offset_bank0(M,V) = D(M,0,V) - D_driver_only(M,V)
```

符号说明：`D(M,0,V)` 表示完整 K 个负载全部存在且处于最低细调代码时的传播延时；`D_driver_only(M,V)` 表示只有固定细调驱动器、没有可变负载阵列时的传播延时；`Offset_bank0(M,V)` 表示即使细调代码为 0，完整负载阵列仍带来的固定延时；`-` 表示传播延时相减。

这些固定开销必须写入：

```text
future_bypass_interface.json
```

至少记录：

```text
fine_driver_offset_ps_by_vdd
fine_bank_code0_offset_ps_by_vdd
selected_load_cell
signal_pin
control_pin
low_cap_control_value
high_cap_control_value
K_candidate_tt25
fine_range_by_vdd
coverage_margin_by_vdd
bypass_not_implemented = true
final_K_frozen = false
```

本轮**不因为零代码固定开销较大就直接 NO-GO**，因为下一阶段本来就要研究旁路与配置跳过。

---

# 9. 本计划明确禁止的范围扩展

Codex 在本计划内不得自动加入：

```text
1. 细调旁路 MUX；
2. 配置跳过；
3. 完整二维中调/细调编码器；
4. 最终中调 N 冻结；
5. 最终细调 K 永久冻结；
6. tap29 电压敏感传感器；
7. XOR 脉冲产生器；
8. DFF 比较器；
9. 启动自校准；
10. C_lock 锁定码；
11. 报警裕量 M；
12. 电压跌落攻击扫描；
13. PVT 全角验证；
14. 最终 RTL；
15. 功耗；
16. 面积；
17. 版图；
18. 外部 Vref；
19. 第二条参考延时链；
20. 第二传感器；
21. TDC（时间数字转换器）；
22. 理想电容作为最终细调器件；
23. 自定义 MOS 可变电容；
24. 离开标准单元库重新造模拟 varactor（可变电容结构）；
25. 无边界标准单元家族 sweep（扫描）。
```

细调必须来自**标准单元输入负载状态变化**。

---

# 10. 最终 GO 条件

只有同时满足以下条件，才能发布：

```text
Standard-Cell Load Fine Stage + One-Medium-Step Coverage = GO
```

条件：

```text
1. 从真实 SMIC40LL 标准单元库找到合法可变负载候选；
2. 同一个控制逻辑状态在三个电压锚点下始终对应同一高负载/低负载物理语义；
3. 单个负载产生的上升沿延时增量在三个锚点均严格为正；
4. 单负载增量在三个锚点均小于相同电压下已测最小中调步长；
5. 8 单元阵列在 0.95 V 的 F=0..8 全代码严格单调；
6. 1.10 V 与 0.80 V 的抽样细调代码严格单调；
7. 浅/中/深不同中调位置下，细调负载方向不翻转；
8. 最终 K 不超过 64；
9. 0.95 V 下最终 K 阵列所有细调代码严格单调；
10. M=0->1、7->8、15->16 与三个锚点组成的 9 个边界全部满足无空洞覆盖；
11. 最大已测相邻细调步长仍小于耦合后的最小中调步长；
12. 所有逻辑电平、毛刺和边沿质量检查通过；
13. 全过程没有重跑中调和更早历史 runner；
14. 本轮没有偷偷加入旁路、自校准、DFF 或跌落检测。
```

若任一条件失败，则发布：

```text
Standard-Cell Load Fine Stage + One-Medium-Step Coverage = NO-GO
```

根因必须从以下类别中明确选择或扩充为一个具体实测原因：

```text
no_valid_standard_cell_varactor
control_to_load_mapping_not_voltage_stable
single_fine_step_too_large
fine_code_non_monotonic
fine_range_insufficient
K_exceeds_bounded_limit
medium_fine_gap_remains
edge_or_logic_integrity_failure
fine_load_breaks_medium_behavior
library_cell_contract_blocked
other_explicit_measured_cause
```

---

# 11. summary 阶段状态与输出报告

## 11.1 summary.json 阶段固定为

```text
Historical Medium Evidence Freeze
Static Fine-Load Candidate Discovery
Single-Load Electrical Screen
8-Unit Fine Bank
Fine-Bank Sizing
Full-Bank One-Step Coverage
Full-Bank Monotonicity
Coupled Medium/Fine Gap Check
Future Bypass Interface
```

每个阶段只能使用：

```text
GO
NO-GO
ARCHITECTURE_BLOCKED
NOT_RUN
```

任何前级失败，后续阶段必须写为 `NOT_RUN`。

summary 必须统计：

```text
new_hspice_scenarios
reused_new_task_scenarios
historical_medium_scenarios_rerun = 0
historical_runner_invocations = 0
sensor_scenarios = 0
dff_scenarios = 0
droop_scenarios = 0
bypass_scenarios = 0
```

## 11.2 最终报告

生成：

```text
delay_chain/ftc/reports/FTC_STANDARD_CELL_LOAD_FINE_STAGE.md
```

报告必须直接回答：

```text
1. 最终选择了哪个标准单元、哪个 signal_pin、哪个 control_pin？
2. 哪个控制逻辑值对应高负载，哪个对应低负载？
3. 单个可变负载在三个锚点产生多少真实细调延时增量？
4. 单个细调步长是否小于同电压的最小中调步长？
5. 8 单元阵列的细调代码是否严格单调？
6. 完整 K 是如何仅用 8 单元实测结果推导的？
7. 是否发生过唯一一次 K_rescaled 修正？如果发生，为什么？
8. 最终 K 在 0.95 V 下是否全码严格单调？
9. 浅/中/深三个中调边界与三个电压是否全部无空洞覆盖？
10. 接入细调结构后真实 MediumStep_coupled 如何变化？
11. 最大细调步长是否仍小于最小耦合中调步长？
12. 固定细调驱动器和 code=0 负载阵列分别引入多少固定开销？
13. 下一阶段旁路至少需要解决哪些固定开销？
14. 本轮新增多少 HSPICE 场景、复用多少场景？
15. 哪些历史 runner 明确没有重跑？
16. 为什么 GO 只代表细调级与单中调步长覆盖成立，而不是完整 FTC 宏 GO？
```

---

# 12. 测试要求

新增：

```text
delay_chain/ftc/tests/test_standard_cell_load_fine_stage.py
```

至少覆盖：

```text
1. 候选发现只允许 NAND/NOR 类且数量 <= 4；
2. signal_pin/control_pin 不得相同；
3. 可变负载输出不回接主传播路径；
4. 细调驱动器固定为 BUF_X0P7M_A9TL40；
5. fine_code 越界拒绝；
6. fine_code=F 时恰有 F 个负载处于高负载状态；
7. 所有 K 个负载在所有代码下始终物理存在；
8. deck 不含 sensor、XOR、DFF；
9. deck 不含旁路 MUX 和配置跳过；
10. deck 不含理想电容或自定义 MOS varactor；
11. 历史 5 个 runner 不被 import 或 subprocess 调用；
12. 相同哈希和参数场景会 resume/reuse 而不是重复 HSPICE；
13. Phase 2 最大新场景预算为 27；
14. Phase 3 最大新场景预算为 25；
15. K_candidate > 64 时立即早停；
16. K 只允许一次 rescale；
17. 0.95 V 最终 K 只允许一次完整全码 sweep；
18. 高低电压最终 K 禁止完整全码暴力 sweep；
19. 任一覆盖 Gate 失败后不得进入旁路阶段；
20. final_medium_N_frozen 必须保持 false；
21. final_fine_K_frozen 必须保持 false；
22. summary 下游阶段在失败后正确传播 NOT_RUN。
```

至少执行：

```text
python3 -m unittest delay_chain.ftc.tests.test_standard_cell_load_fine_stage
git diff --check
```

如果仓库已有稳定快速的纯 Python FTC 回归入口，可以额外执行；不得因此触发任何历史 HSPICE runner。

---

# 13. Codex 严格执行顺序

Codex 必须严格按下列顺序推进：

```text
Step 1  读取远程 main 最新提交；确认中调级最新完成结果仍为 GO。
Step 2  冻结中调 summary/interface/report/runner 等输入 SHA256；禁止重跑中调 41 个 HSPICE 场景。
Step 3  生成 standard_cell_load_fine_stage/requirements.json；0 HSPICE。
Step 4  从真实 LVT Verilog/CDL 静态发现 NAND/NOR 负载候选；0 HSPICE。
Step 5  最多保留 4 个“单元 + signal_pin”物理候选；禁止无边界库扫描。
Step 6  运行 3 个“中调 + 固定细调驱动器”基准场景。
Step 7  对最多 4 个候选运行 control=0/1、三个锚点的单负载筛选；最多 24 个候选场景。
Step 8  由实测确定高负载控制逻辑和低负载控制逻辑；若跨电压翻转，淘汰候选。
Step 9  选出唯一通过单负载 Gate 的候选；无候选则 NO-GO。
Step 10 构建 K_test=8 的细调阵列。
Step 11 在 0.95 V、medium_code=8 下完整扫描 F=0..8。
Step 12 Gate GO 后，在 1.10/0.80 V 补 F={0,1,4,7,8}。
Step 13 再在 0.95 V 补 medium_code={0,15}、F={0,1,8}，检查位置依赖。
Step 14 仅用 8 单元实测数据离线推导 K_candidate；0 HSPICE。
Step 15 如果 K_candidate>64，立即 NO-GO。
Step 16 完整 K 阵列先验证当前最坏 M=7->8 的三个电压覆盖。
Step 17 若仅范围稍不足且电气完整性正常，只允许一次 K_rescaled 重算；第二次仍失败则 NO-GO。
Step 18 对最终 K，在 0.95 V、M=7 下完整扫描 F=0..K。
Step 19 在 1.10/0.80 V 对最终 K 只做 7 个代表细调代码抽样，不做全码暴力 sweep。
Step 20 验证 M=0->1、7->8、15->16 与三个锚点组成的 9 个无空洞覆盖 Gate。
Step 21 计算 delta_fine_max 与 MediumStep_coupled_min，确认细调仍保持比中调更细。
Step 22 计算固定驱动器开销和 code=0 负载阵列固定开销。
Step 23 写 future_bypass_interface.json，明确下一阶段旁路要处理的固定开销。
Step 24 生成 summary、报告和纯 Python 回归。
Step 25 无论 GO/NO-GO，本计划在“标准单元负载细调 + 单中调步长覆盖”处停止；禁止实现旁路、配置跳过、两级最终编码、自校准、跌落扫描、PVT、RTL、功耗、面积和版图。
```

---

# 14. Codex 最重要的架构提醒

本阶段不能把“细调范围覆盖一个中调步长”错误理解为：

```text
只要单独的 fine bank 在理想环境下能产生 >= 66.862606 ps 就算 GO
```

真正必须验证的是**细调结构接到已经 GO 的中调级之后**：

```text
D(M,K,V) >= D(M+1,0,V)
```

符号说明：`M` 表示较低中调代码；`K` 表示完整细调阵列最大代码；`V` 表示供电电压；左侧表示“当前中调档位 + 最大细调”的真实传播延时；右侧表示“下一中调档位 + 最小细调”的真实传播延时；`>=` 表示两个中调档位之间不存在不可覆盖的延时空洞。

同样，不能只追求范围而牺牲分辨率。必须同时满足：

```text
单个细调步长 < 中调步长
```

以及：

```text
完整细调范围 >= 一个中调步长
```

只有两者同时成立，才真正形成后续“中调 + 细调”两级延时线所需要的物理基础。

下一阶段才允许研究：

```text
旁路
配置跳过
两级固定开销
最终 N/K 联合尺寸
二维数字编码
```

**不要提前做后面的事情。**
