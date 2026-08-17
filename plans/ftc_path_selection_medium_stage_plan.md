# FTC 路径选择中调级逐步骤执行计划（重构版）

## 0. 本计划的架构位置：只验证“路径选择中调级”，不是最终检测器

本计划是对上一版 `plans/ftc_path_selection_medium_stage_plan.md` 的直接重构。Codex 必须先理解：本轮不是要把路径选择中调级单独做成最终的完整可编程阈值链，也不是要立刻重新接回传感器、D触发器和自校准控制器。

当前设计主线已经经过两次明确的结构性失败和一次架构转向：

```text
旧 3 位稀疏抽头可编程阈值
        |
        +-- 3-bit Boundary-Centered Mapping = NO-GO
        |
        v
每级“快速/慢速”二选一的单位可控延时链
        |
        +-- Fine-Grained Controllable Delay = NO-GO
        |
        v
本轮：论文式路径选择中调级
        |
        +-- 只验证范围扩展、最短路径固定开销、单调性、步长包络
        |
        v
未来独立计划：标准单元负载细调级
        |
        v
未来独立计划：细调范围覆盖一个中调步长
        |
        v
未来独立计划：加入两级组合所需的旁路与配置跳过
        |
        v
未来独立计划：完整“中调 + 细调”两级可编程延时线
        |
        v
之后才重新接入 tap29 传感器 + 异或门 + D触发器 + 启动自校准
        |
        v
之后才验证“锁定码 + 可编程裕量”的电压跌落检测
```

**因此，本计划的唯一研究问题是：**

> **论文式路径选择中调级能否打破上一种单位可控延时链中“为了增大最大延时范围，就必须让最短代码同时承担越来越大的固定选择器延时”这一结构性死结？**

只要这个物理性质没有先被证明，后续细调、自校准、跌落检测都没有继续实现的价值。

反过来，即使本轮得到 GO，也只表示“路径选择中调级值得作为未来两级延时线的中调部分继续使用”，**不表示完整 FTC 检测宏已经 GO**。

---

## 1. Codex 必须先读取的最新仓库事实

### 1.1 当前远程基线

执行前必须读取远程 `main` 最新提交，并确认最新已完成电气结论仍然来自：

```text
d0b4c491b587bfc20629f31e0b9afabd44cd6d41
feat(ftc): add fine-grained controllable delay gate
```

如果 `main` 已经出现更新的、与本任务直接相关的已完成实验，Codex 必须先停在“证据冻结”阶段，读取新证据并更新本任务输入；不得假装仓库仍停在旧状态。

### 1.2 最新单位可控延时链的结构性 NO-GO

必须只读：

```text
delay_chain/ftc/analysis/fine_grained_controllable_delay/requirements.json
delay_chain/ftc/analysis/fine_grained_controllable_delay/summary.json
delay_chain/ftc/analysis/fine_grained_controllable_delay/unit_cell.csv
delay_chain/ftc/analysis/fine_grained_controllable_delay/unit_cell_decision.json
delay_chain/ftc/reports/FTC_FINE_GRAINED_CONTROLLABLE_DELAY.md
delay_chain/ftc/scripts/run_fine_grained_controllable_delay.py
```

必须冻结以下已证明事实，不得重复 HSPICE：

```text
1. 候选 A 已经完成 6 个单位单元场景；
2. 1.10 V 的单位附加延时约为 10.865 ps；
3. 0.95 V 的单位附加延时约为 14.052 ps；
4. 0.80 V 的单位附加延时约为 20.655 ps；
5. 三个电压点的单位附加延时都为正，逻辑电平和边沿质量本身不是失败主因；
6. 慢速/快速总延时比只有约 1.687--1.737；
7. 上一拓扑所需的历史全范围结构下界为 3.247270...；
8. 候选 A 因固定选择结构开销过大而 NO-GO；
9. 候选 B 因缺少已确认的同极性低开销旁路原语而 ARCHITECTURE_BLOCKED；
10. 8 级短链、级数求解、完整链、真实 D触发器校准、锁定码加裕量均为 NOT_RUN。
```

上一拓扑的关键问题必须被 Codex 明确写进新任务的 `requirements.json`：

```text
所有代码都穿过全部 N 个单位单元的选择结构
        |
        +-- N 增大时最大延时增加
        |
        +-- 但最小延时也同时累积 N 份固定选择器开销
        |
        +-- 所以“增加范围”与“抬高最小固定延时”被结构性绑定
```

这里的 `N` 表示串联的可控延时单元数量。

### 1.3 更早的粗粒度路线只作为历史背景，不再继续修补

只读：

```text
delay_chain/ftc/analysis/delay_code_refinement/summary.json
delay_chain/ftc/analysis/delay_code_refinement/calibration_gate.csv
delay_chain/ftc/analysis/delay_code_refinement/tap_screen.csv
delay_chain/ftc/reports/FTC_DELAY_CODE_BOUNDARY_REFINEMENT.md

delay_chain/ftc/analysis/programmable_acceptance_window/summary.json
delay_chain/ftc/reports/FTC_PROGRAMMABLE_ACCEPTANCE_WINDOW_ROOT_CAUSE.md

delay_chain/ftc/analysis/static_self_calibration/calibration_trace.csv
delay_chain/ftc/analysis/static_self_calibration/range_mapping.json
```

这些证据只用于保留以下设计上下文：

```text
- 3 位、8 个稀疏抽头的路线已经停止继续修补；
- “数字代码 +1”曾经可能跨越多个甚至十几个真实缓冲级；
- 旧路线的根因之一是数字码空间没有形成稳定的物理时间步长；
- 当前研究目标仍然是保留数字可编程延时和后续自校准能力，而不是改成纯并行边界读取器。
```

**禁止生成第三组 3 位候选映射。**

### 1.4 当前可复用标准单元证据

只读：

```text
delay_chain/ftc/discovery/selected_cells.json
delay_chain/phase2_vernier/discovery/mux_candidates.md
```

已知可优先复用的器件：

```text
延时缓冲器：BUF_X0P7M_A9TL40
已知二选一传输型多路选择器：MXT2_X0P5M_A9TR40
上一 runner 还使用过 LVT 版本：MXT2_X0P5M_A9TL40
```

“LVT”表示低阈值电压标准单元；“RVT”表示常规阈值电压标准单元。

本计划不允许无边界地扫描整个标准单元库。首先使用已经有证据的缓冲器和二选一多路选择器；只有静态库定义证明当前首选单元无法表达论文式路径选择时，才允许在**同一类二选一同极性选择器**中做一次有界替换。

---

## 2. 本轮必须修正上一版计划的三个误区

### 2.1 中调级不需要单独承担“最终细分辨率”

上一版计划把成功条件写成“路径选择中调级自身既要覆盖全范围，又要足够细，并直接形成真实 D触发器的全部锁定边界”。这与当前已经确定的两级路线不一致。

本轮中调级只负责：

```text
1. 提供可扩展的主要延时范围；
2. 保持代码递增时路径延时单调增加；
3. 避免总级数增加时最短代码固定延时同步线性增加；
4. 测出真实“中调步长包络”，供下一阶段细调级决定需要覆盖多大的间隔。
```

中调步长可以明显大于未来细调步长。**本轮不因为“中调步长不够细”而判 NO-GO。**

### 2.2 本轮不接回真实传感器和 D触发器

本轮禁止把以下内容加入新 HSPICE deck：

```text
tap29 电压敏感传感器
异或脉冲产生路径
DFFRPQ_X0P5M_A9TR40 比较器
启动自校准控制
锁定码搜索
锁定码 + 裕量
静态/瞬态电压跌落攻击
```

原因：这些属于两级可编程延时线完成之后的系统级验证。现在把它们提前接回，只会把“中调级本身是否解决结构问题”和“传感器/比较器加载”混在一起。

### 2.3 历史 3.247 调节比不再是本拓扑 Gate

历史字段：

```text
required_delay_ratio_lower_bound = 3.247270227553231
```

只用于解释上一种“所有代码都穿过 N 个选择器”的单位可控延时链为什么结构性失败。

路径选择中调级的核心不是让一个单位单元本身达到 3.247 的慢速/快速比，而是让：

```text
最短代码只经过浅层合法路径
最长代码才经过更深的选择路径
```

从而使总级数主要扩展最大延时，而不是同步抬高最小延时。

因此 `3.247270...` 必须在新任务中标记为：

```text
historical_diagnostic_only = true
```

不得成为本轮早停条件。

---

# 3. 固定的中调级拓扑：论文式局部路径选择，不是大型抽头多路选择器树

## 3.1 论文式行为定义

本轮必须实现的行为是：

```text
控制全为 0：输入只走最浅的一段合法延时路径，然后直接到输出；
控制逐级增加：信号继续进入更深一级路径；
控制全为 1：信号传播到最深路径后到输出。
```

这是一种“路径选择延时线”：代码本身决定实际传播路径有多深。

它**不是**：

```text
先生成很多抽头
        |
        v
再把所有抽头送进 16选1 / 32选1 / 64选1 的大型平衡多路选择器树
```

也**不是**上一轮：

```text
每一级都有“快速/慢速”二选一
        |
        v
但所有代码最终仍穿过全部 N 个选择器
```

## 3.2 允许的第一版局部级联表达

在没有发现库结构冲突前，优先用“串行延时节点 + 局部级联二选一选择器”表达论文式路径选择：

```text
输入
 |
 v
X0 -> BUF -> X1 -> BUF -> X2 -> BUF -> X3 -> ... -> X(N+1)
             |            |            |                 |
             +--浅层出口--+--更深出口--+------ ... -------+
                  \            \                         /
                   \       局部二选一选择级             /
                    +-------- 路径选择 -----------------+
                                  |
                                  v
                                 OUT
```

其中 `BUF` 表示延时缓冲单元；`X0...X(N+1)` 表示逐级更深的串行延时节点；`N` 表示可继续向深层传播的受控级数。

实现可以采用递归连接：

```text
Y[N] = X[N+1]
Y[i] = SEL(X[i+1], Y[i+1], T[i])
OUT  = Y[0]
```

符号说明：`Y[i]` 表示第 `i` 个局部选择级的输出；`X[i+1]` 表示当前层的直接退出节点；`Y[i+1]` 表示继续进入更深路径后的返回节点；`SEL(a,b,s)` 表示由控制位 `s` 在输入 `a` 与输入 `b` 中选择一路的二选一选择函数；`T[i]` 表示第 `i` 个连续控制位；`=` 表示连接或定义关系；`i+1` 中 `+` 表示索引加一。

**重要：这只是允许的网表表达方式，不允许 Codex凭空假定实际标准单元的 S0 极性。** 必须先解析真实 Verilog/CDL 定义，再决定 A/B 端如何连接。

## 3.3 连续控制编码

控制代码只允许使用连续开启形式：

```text
C = 0 : 00000000
C = 1 : 10000000
C = 2 : 11000000
C = 3 : 11100000
...
C = 8 : 11111111
```

这种编码也称为温度计编码，即随着代码增加，连续的“1”从低级向深层逐级扩展。

形式化定义：

```text
T[i](C) = 1, 当 i < C
T[i](C) = 0, 当 i >= C
```

符号说明：`T[i](C)` 表示代码 `C` 下第 `i` 个连续控制位；`1` 表示允许继续走向更深一级路径；`0` 表示在当前深度退出；`i` 是从 0 开始的控制位索引；`C` 是整数控制代码；`<` 表示“小于”；`>=` 表示“大于或等于”；`=` 表示定义关系。

## 3.4 本轮最关键的结构性指标

定义：

```text
D_min(N,V) = D(N,0,V)
D_max(N,V) = D(N,N,V)
Span(N,V)  = D_max(N,V) - D_min(N,V)
```

符号说明：`D(N,C,V)` 表示总受控级数为 `N`、控制代码为 `C`、供电电压为 `V` 时从输入到输出的真实传播延时；`D_min(N,V)` 表示同一规模下的最短代码延时；`D_max(N,V)` 表示同一规模下的最深代码延时；`Span(N,V)` 表示该中调级的可编程延时范围；`-` 表示最大延时减去最小延时；`=` 表示定义关系。

本轮所有单调性 Gate 以**上升沿传播延时**作为主判据，因为未来该中调级将驱动比较器时钟端；下降沿传播延时和转换时间必须同时记录，用于检查边沿完整性。下文未特别注明时，`D` 默认指上升沿传播延时。

本轮真正要证明的是：

```text
N 增大时：
Span(N,V) 明显增大
而 D_min(N,V) 不应随 N 同比例增长
```

如果 `N` 从 4 增加到 8、再增加到 16 时，最短代码延时也近似线性增加，说明实现仍然退化成了上一种“所有代码都承担深链固定开销”的错误物理结构，必须 NO-GO。

---

# 4. 全局禁止项

Codex 在本计划内不得自动转向：

```text
1. 第三组 3 位 / 8 抽头候选映射；
2. 16选1、32选1、64选1大型平衡抽头选择树；
3. 上一轮“每级快速/慢速二选一且所有代码穿过全部 N 级”的单位可控延时链；
4. 标准单元负载细调级；
5. 可变电容细调；
6. 环形振荡器粗调；
7. 中调 + 细调两级组合；
8. 后续两级组合专用的全局旁路或配置跳过；
9. tap29 传感器集成；
10. 异或脉冲集成；
11. D触发器比较；
12. 启动自校准；
13. 锁定码 + 裕量；
14. 电压跌落攻击扫描；
15. 工艺/电压/温度全角验证；
16. 监测器 RTL；
17. 功耗、面积、版图优化；
18. 外部参考电压、第二传感器、第二参考延时线、时间数字转换器；
19. 无边界标准单元族扫描；
20. 为了“凑 GO”而修改正式 0.80--1.10 V 背景范围。
```

注意：第 4--8 项是**未来路线的一部分，不是被永久否定**；只是本轮必须停止在中调级，避免一次实现过多结构后无法定位根因。

---

# 5. 新 runner、输出目录与防重复仿真机制

## 5.1 新文件

新增/更新：

```text
delay_chain/ftc/scripts/run_path_selection_medium_stage.py
delay_chain/ftc/analysis/path_selection_medium_stage/
delay_chain/ftc/runs/path_selection_medium_stage/r1/
delay_chain/ftc/reports/FTC_PATH_SELECTION_MEDIUM_STAGE.md
delay_chain/ftc/tests/test_path_selection_medium_stage.py
```

如果上一版错误计划尚未被 Codex 执行，上述文件可能不存在；直接按本计划创建。

如果已经存在任何由上一版计划产生的未提交或已提交数据，Codex 必须先检查其 `topology_version`、场景参数和 SHA256。**不同拓扑/不同验收目标的数据不得混写。** 新设计必须进入新的 run revision。

## 5.2 历史 runner 永远只读

本任务禁止调用：

```text
delay_chain/ftc/scripts/run_static_self_calibration.py
delay_chain/ftc/scripts/run_programmable_acceptance_window.py
delay_chain/ftc/scripts/run_delay_code_refinement.py
delay_chain/ftc/scripts/run_fine_grained_controllable_delay.py
```

可以复制已经审查过的通用 HSPICE 完整性检查函数，例如 listing 检查、测量有效性检查、哈希函数，但不得 import 或 subprocess 调用这些历史 runner 的主执行流程。

## 5.3 每个新场景必须可恢复、可复用

每个场景的确定性 ID 至少包含：

```text
phase
topology_version
mux_cell
delay_cell
N
code
vdd_v
input_slew_contract
output_load_contract
```

每个场景目录写：

```text
scenario_manifest.json
```

至少保存：

```text
netlist_sha256
runner_sha256
requirements_sha256
cell_contract_sha256
parameters
completion_status
measurement_file
```

只有在以下条件全部一致时才能复用：

```text
completion_status = PASS
netlist_sha256 完全一致
runner_sha256 完全一致
requirements_sha256 完全一致
参数完全一致
listing 与 measurement 完整
```

若任何哈希变化，创建新的 revision；不得覆盖旧 raw run。

---

# Phase 0 — 冻结架构决策与历史证据（0 个新 HSPICE）

## Step 0.1：验证最新历史输入

读取第 1 节列出的历史证据并计算 SHA256，生成：

```text
delay_chain/ftc/analysis/path_selection_medium_stage/requirements.json
```

必须至少记录：

```text
architecture_decision = path_selection_medium_stage_only
future_architecture = medium_then_standard_cell_load_fine_then_two_stage_integration
historical_sparse_3bit_route = closed
historical_fast_slow_unit_chain = NO-GO
historical_fast_slow_failure_mode = minimum_delay_scales_with_fixed_selector_overhead
historical_required_delay_ratio_lower_bound = diagnostic_only
formal_background_vdd_range_v = [0.80, 1.10]
initial_corner = TT_25C
anchor_vdd_v = [1.10, 0.95, 0.80]
source_file_sha256
```

还必须把 `requirements.json` 中历史 `required_delay_span_ps = 617.031773...` 保存为：

```text
historical_system_span_reference_ps
```

该字段只用于本轮结束时做“未来最终级数的大致投影”，**不是本轮必须直接实现完整 617 ps 的硬 Gate**。

## Step 0.2：写出本轮明确停止边界

同一个 `requirements.json` 必须包含：

```text
sensor_integration = forbidden
real_dff_calibration = forbidden
droop_sweep = forbidden
fine_stage = future_work
bypass_and_skip = future_work
full_two_stage_delay_line = future_work
```

Phase 0 完成后只运行纯 Python 测试，不运行 HSPICE。

---

# Phase 1 — 静态确认标准单元与路径拓扑（0 个新 HSPICE）

## Step 1.1：解析实际二选一选择器契约

从真实标准单元 Verilog/CDL 中只读确认首选 `MXT2` 的：

```text
单元名
端口顺序
A/B/S0 语义
S0=0 选择哪一路
S0=1 选择哪一路
输出是否同极性
电源与阱连接顺序
```

优先检查上一 runner 实际使用的：

```text
MXT2_X0P5M_A9TL40
```

并对仓库已有 `mux_candidates.md` 中：

```text
MXT2_X0P5M_A9TR40
```

做静态一致性记录。

输出：

```text
delay_chain/ftc/analysis/path_selection_medium_stage/cell_contract.json
```

如果首选 LVT 单元不存在、不是同极性二选一、或库定义不完整，只允许切到已知 RVT `MXT2` 做**同一拓扑**验证；不得开启新的标准单元大搜索。

## Step 1.2：实现纯 Python 路径生成与路径追踪

runner 中至少实现：

```text
thermometer_code(N, code)
build_path_selection_medium_stage(N, code, ...)
trace_selected_path(N, code)
count_selected_path_cells(N, code)
```

对 `N = 1, 4, 8, 16` 做静态路径证明。

必须证明：

```text
1. code=0 始终只选择最浅合法出口；
2. code=N 始终选择最深出口；
3. code 每增加 1，路径只加深一级；
4. code=0 的“被选中传播路径”所含选择级数量不随 N 线性增长；
5. code=N 的传播路径深度随 N 增加；
6. 无组合环；
7. 无多驱动；
8. 无悬空关键节点；
9. 无大型平衡抽头选择树；
10. 无上一轮快速/慢速单位模板；
11. 无细调、粗调、传感器、D触发器。
```

输出：

```text
delay_chain/ftc/analysis/path_selection_medium_stage/topology_contract.json
```

如果第 4 条在静态网表上不成立，直接：

```text
Path-Selection Medium Stage = ARCHITECTURE_BLOCKED
```

并以 0 个新 HSPICE 结束。

---

# Phase 2 — N=8 中调原型：先证明真实代码单调与步长包络

本阶段只测路径选择中调级本身。统一输入脉冲、输入转换时间和输出负载必须固定并写入 `requirements.json`，不得在不同代码之间改变测试台条件。

## Step 2.1：Gate A，在 0.95 V 完整扫描 N=8 的 9 个代码

固定：

```text
N = 8
VDD = 0.95 V
code = 0,1,2,3,4,5,6,7,8
```

总计 9 个新 HSPICE 场景。

每个场景至少测：

```text
D_rise_ps
D_fall_ps
output_rise_time_ps
output_fall_time_ps
output_logic_high
output_logic_low
unexpected_transition_count
```

必须计算所有相邻中调步长：

```text
Step(C,V) = D(C+1,V) - D(C,V)
```

符号说明：`Step(C,V)` 表示供电电压 `V` 下，从控制代码 `C` 增加到 `C+1` 时的真实中调延时增量；`D(C,V)` 表示该中调原型在代码 `C` 下的传播延时；`C+1` 表示控制代码增加一级；`-` 表示相邻两次传播延时相减；`=` 表示定义关系。

Gate A 必须满足：

```text
1. D(0) < D(1) < ... < D(8)；
2. 所有 Step(C,0.95V) > 0；
3. 输出高低电平合法；
4. 没有额外毛刺；
5. 上升沿和下降沿均可稳定测量；
6. 不要求每个 Step 完全相等。
```

若失败，直接 NO-GO，不继续高低电压。

## Step 2.2：Gate B，只在 1.10 V 与 0.80 V 做稀疏但能检查两端的代码集合

若 Gate A GO，再跑：

```text
N = 8
VDD = 1.10 V, 0.80 V
code = 0,1,4,7,8
```

共 10 个新场景。

这样可以直接检查：

```text
浅层第一步：0 -> 1
中间跨度：1 -> 4 -> 7
深层最后一步：7 -> 8
端点：0 与 8
```

Gate B 必须满足：

```text
1. 1.10 V 与 0.80 V 都保持 D(0) < D(1) < D(4) < D(7) < D(8)；
2. 浅层 Step(0,V) > 0；
3. 深层 Step(7,V) > 0；
4. 输出逻辑和边沿完整。
```

Phase 2 新 HSPICE 上限固定为：

```text
9 + 10 = 19 个场景
```

符号说明：`9` 表示 0.95 V 下完整 9 代码扫描；`10` 表示高低两个电压点各 5 个代码；`+` 表示场景数相加；结果 `19` 是 Phase 2 的最大新增场景数。

输出：

```text
delay_chain/ftc/analysis/path_selection_medium_stage/n8_code_sweep.csv
delay_chain/ftc/analysis/path_selection_medium_stage/n8_step_envelope.json
```

`n8_step_envelope.json` 必须记录三个锚点的已测：

```text
step_min_ps
step_median_ps
step_max_ps
span_ps
edge_quality
```

---

# Phase 3 — 关键结构 Gate：证明“增加范围”不再同步抬高最短路径

这是本计划最重要的一阶段。只有这一阶段通过，才能说路径选择中调级真正针对了上一轮结构性 NO-GO。

## Step 3.1：0.95 V 下做 N 缩放端点实验

复用 Phase 2 的 `N=8, code=0/8`，只新增：

```text
VDD = 0.95 V
N = 1,4,16
code = 0,N
```

最多新增 6 个场景。

如果 `N=1` 的场景与任何前置新任务已有完全同哈希结果重合，必须复用，不重跑。

得到：

```text
D_min(1), D_max(1)
D_min(4), D_max(4)
D_min(8), D_max(8)
D_min(16), D_max(16)
```

并计算每个规模的可编程范围 `Span(N,0.95V)`。

## Step 3.2：用“最短路径增长”对比“最大路径增长”

对相邻规模 `N1 < N2`，计算：

```text
Growth_min = D_min(N2,V) - D_min(N1,V)
Growth_max = D_max(N2,V) - D_max(N1,V)
```

符号说明：`Growth_min` 表示规模从 `N1` 增大到 `N2` 后最短代码延时增加了多少；`Growth_max` 表示相同规模变化后最深代码延时增加了多少；`D_min` 和 `D_max` 分别是最短和最深代码的真实传播延时；`V` 表示固定供电电压；`-` 表示两个规模的传播延时之差；`N1 < N2` 表示第二个原型包含更多可选深度。

结构性 GO 必须满足：

```text
1. Span(1) < Span(4) < Span(8) < Span(16)；
2. D_max 随 N 明显增加；
3. D_min 不得像 D_max 一样近似线性随 N 增加；
4. 从 N=4 增大到 N=16 时，D_min 的总漂移不得达到或超过同一 0.95 V 下一个“典型中调步长”的量级；
5. 静态路径追踪与电气结果必须一致：浅层代码没有偷偷穿过后续所有选择级。
```

第 4 条中的“典型中调步长”使用 Phase 2 在 0.95 V 测得的 `step_median_ps`，不是人工写死的皮秒阈值。

若第 1--5 条任一失败，发布：

```text
Path-Selection Medium Stage = NO-GO
reason = minimum_path_still_scales_with_stage_count
```

并停止。

## Step 3.3：只对 N=16 的端点补高低电压

若 0.95 V 缩放 Gate GO，再新增：

```text
N = 16
VDD = 1.10 V, 0.80 V
code = 0,16
```

共 4 个场景。

目的不是完整电压扫描，而是确认在正式范围两端：

```text
最短路径仍然可测且没有固定延时灾难性膨胀；
最长路径仍然保持合法逻辑和边沿；
可编程范围仍显著为正。
```

Phase 3 新 HSPICE 上限为 10 个场景；若 `N=1` 场景被复用则更少。

输出：

```text
delay_chain/ftc/analysis/path_selection_medium_stage/scaling_endpoints.csv
delay_chain/ftc/analysis/path_selection_medium_stage/scaling_summary.json
```

---

# Phase 4 — 为未来细调级导出“中调步长覆盖要求”，不实现细调级

本阶段只做数据整理和极少量局部补点，不允许加入任何细调器件。

## Step 4.1：选择本轮原型规模

如果 `N=16` 已经通过 Phase 3，则固定：

```text
N_characterize = 16
```

这里的 16 只是**中调级表征原型规模**，不是最终完整两级延时线的冻结级数。

不允许在本计划里继续扩到 24、32、64 去追求历史完整系统范围。

## Step 4.2：只在浅、中、深三个区域测相邻步长

对：

```text
VDD = 1.10, 0.95, 0.80 V
```

选择以下相邻代码对：

```text
浅层：0,1
中层：7,8
深层：15,16
```

Phase 2 或 Phase 3 已存在的完全相同场景必须复用，只补缺失场景。

最坏情况下最多需要 18 个“代码场景”，但由于 0、1、8、16 等多项已经存在，实际新增必须显著少于 18；runner 必须在 `summary.json` 中统计“计划代码数、复用数、新增数”。

输出：

```text
delay_chain/ftc/analysis/path_selection_medium_stage/medium_step_characterization.csv
delay_chain/ftc/analysis/path_selection_medium_stage/future_fine_stage_interface.json
```

`future_fine_stage_interface.json` 必须至少包含：

```text
medium_step_min_ps_by_vdd
medium_step_max_ps_by_vdd
medium_step_global_max_ps
medium_step_global_min_ps
medium_span_n16_by_vdd
minimum_path_delay_n16_by_vdd
maximum_path_delay_n16_by_vdd
future_requirement = fine_stage_range_must_cover_at_least_one_worst_case_medium_step
```

这一步的目的，是给下一份“标准单元负载细调级”计划一个明确输入。未来必须满足：

```text
Fine_range >= medium_step_global_max_ps
```

符号说明：`Fine_range` 表示未来细调级能够提供的完整可调延时范围；`medium_step_global_max_ps` 表示本轮在所有已测电压与浅/中/深位置中得到的最大中调相邻步长；`>=` 表示细调范围必须大于或等于最坏中调步长。这样才能让“中调码 + 细调码”之间没有不可覆盖的延时空洞。

本轮**只导出这个要求，不实现细调级。**

在前面各 Gate 全部 GO 的最坏情况下，本计划新 HSPICE 总预算为：

```text
19 + 10 + 12 = 41 个场景
```

符号说明：`19` 是 Phase 2 的 N=8 代码单调性与高低电压锚点场景上限；`10` 是 Phase 3 的级数缩放与 N=16 高低电压端点场景上限；`12` 是 Phase 4 在 N=16、三个锚点补齐浅/中/深相邻步长所需的最大新增场景数；`+` 表示场景数相加；`41` 是整个本计划允许的新 HSPICE 场景硬上限。任何已经存在且哈希完全一致的场景都必须复用，因此实际新增数只能小于或等于 41。

## Step 4.3：历史完整系统范围只做离线投影

可以使用历史：

```text
historical_system_span_reference_ps = 617.031773...
```

和本轮测得的中调步长，对未来可能需要的中调级数做一个 `projection_only` 估计，写入：

```text
delay_chain/ftc/analysis/path_selection_medium_stage/future_range_projection.json
```

必须明确：

```text
final_N_frozen = false
projection_requires_future_fine_stage_and_two_stage_integration = true
```

禁止因为这个投影结果去新增完整 N 级 HSPICE 链；最终级数要等细调级、旁路/配置跳过以及两级固定开销都可用后再共同决定。

---

# Phase 5 — 最终中调级判定、报告和测试

## Step 5.1：最终 GO 条件

只有同时满足以下条件，才能发布：

```text
Path-Selection Medium Stage = GO
```

条件：

```text
1. 静态网表证明代码越大，实际选中路径越深；
2. 浅层代码不穿过全部 N 个选择级；
3. N=8 在 0.95 V 的 0..8 全码真实传播延时严格单调；
4. 1.10 V 与 0.80 V 的浅层和深层关键步长均为正；
5. Span 随 N=1,4,8,16 明显扩大；
6. D_min 没有随 N 近似线性增长；
7. 从 N=4 到 N=16 的最短路径漂移小于一个 0.95 V 典型中调步长；
8. N=16 在 1.10 V 与 0.80 V 的最短/最长路径都保持合法逻辑和可测边沿；
9. 已导出未来细调级需要覆盖的最坏中调步长；
10. 全过程中没有重跑历史 runner，也没有提前加入细调、传感器、D触发器或自校准。
```

若任一条件失败，则发布：

```text
Path-Selection Medium Stage = NO-GO
```

根因枚举至少包含：

```text
static_topology_not_true_path_selection
non_monotonic_medium_code
minimum_path_still_scales_with_stage_count
range_does_not_scale
edge_or_logic_integrity_failure
medium_step_not_stable_enough_to_characterize
library_cell_contract_blocked
other_explicit_measured_cause
```

## Step 5.2：统一 summary

输出：

```text
delay_chain/ftc/analysis/path_selection_medium_stage/summary.json
```

阶段状态固定为：

```text
Historical Evidence Freeze
Static Path-Selection Contract
N8 Code Monotonicity
Stage-Count Scaling
Medium-Step Characterization
Future Fine-Stage Interface
```

每一项只能为：

```text
GO
NO-GO
ARCHITECTURE_BLOCKED
NOT_RUN
```

任何前级失败，后续阶段必须 `NOT_RUN`。

summary 还必须统计：

```text
new_hspice_scenarios
reused_new_task_scenarios
historical_scenarios_reused_as_read_only_evidence
historical_runners_invoked = 0
sensor_scenarios = 0
dff_scenarios = 0
droop_scenarios = 0
```

## Step 5.3：最终报告

生成：

```text
delay_chain/ftc/reports/FTC_PATH_SELECTION_MEDIUM_STAGE.md
```

报告必须直接回答：

```text
1. 上一轮单位可控延时链为什么结构性 NO-GO？
2. 本轮路径选择中调级如何从物理拓扑上改变“最短代码也穿过全部选择器”的问题？
3. N=8 的真实代码延时是否严格单调？
4. 三个锚点的中调步长最小值、中位值、最大值是多少？
5. N 从 1/4/8/16 增加时，最短延时和最大延时分别如何变化？
6. 可编程范围是否随 N 明显扩展，而最短延时不再同速增长？
7. 未来细调级至少需要覆盖多大的最坏中调步长？
8. 本轮新增了多少 HSPICE 场景，复用了多少新任务场景？
9. 哪些历史仿真明确没有重跑？
10. 为什么本轮没有接传感器、D触发器、自校准和跌落扫描？
11. GO 的严格含义为什么只是“中调级可进入下一阶段”，而不是“完整 FTC 宏 GO”？
```

---

# 6. 测试要求

新增：

```text
delay_chain/ftc/tests/test_path_selection_medium_stage.py
```

至少覆盖：

```text
1. thermometer_code(8,0..8) 正确；
2. code 越界拒绝；
3. trace_selected_path(N,0) 的选中路径深度不会随 N=1/4/8/16 线性增长；
4. trace_selected_path(N,N) 的路径深度随 N 增长；
5. code 每增加 1，只增加一级路径深度；
6. deck 不含 16选1/32选1/64选1大型抽头树；
7. deck 不含上一轮快速/慢速单位模板；
8. deck 不含细调负载或可变电容；
9. deck 不含 tap29 sensor、XOR、DFF；
10. 历史四个 runner 不被 import 或 subprocess 调用；
11. 场景哈希完全一致时 resume/reuse，不重跑 HSPICE；
12. Phase 2 最大新增场景数为 19；
13. Gate A 失败时 Gate B 不运行；
14. Phase 3 缩放 Gate 失败时 Phase 4 不运行；
15. 不允许本计划生成 final_N_frozen=true；
16. 不允许本计划生成 calibration_gate.csv 或 droop attack 输出；
17. summary 下游状态在失败后正确写成 NOT_RUN。
```

执行至少：

```text
python3 -m unittest delay_chain.ftc.tests.test_path_selection_medium_stage
git diff --check
```

若仓库已有快速纯 Python FTC 回归入口，可额外运行；任何测试入口都不得触发历史 HSPICE runner。

---

# 7. Codex 严格执行顺序

Codex 必须严格按以下顺序推进：

```text
Step 1  读取远程 main 最新提交，确认当前已完成电气结论仍是 Fine-Grained Controllable Delay = NO-GO。
Step 2  读取本计划和第 1 节历史证据，冻结 SHA256；绝不运行四个历史 runner。
Step 3  生成新的 path_selection_medium_stage/requirements.json；0 个 HSPICE。
Step 4  解析 MXT2 实际标准单元选择极性、端口、同极性属性；0 个 HSPICE。
Step 5  实现连续控制编码、论文式局部路径选择网表生成器和静态路径追踪；0 个 HSPICE。
Step 6  对 N=1/4/8/16 做静态路径证明；若浅层路径随 N 线性增长，直接 ARCHITECTURE_BLOCKED。
Step 7  只跑 N=8、0.95 V、code=0..8 的 9 个场景；验证全码严格单调。
Step 8  Gate A GO 后才跑 N=8、1.10/0.80 V、code={0,1,4,7,8} 的 10 个场景。
Step 9  复用 N=8 端点，只补 0.95 V 下 N={1,4,16} 的 code={0,N} 缩放场景。
Step 10 计算 Span、D_min、D_max 与缩放关系；若最短路径仍随 N 同速增长，立即 NO-GO。
Step 11 缩放 GO 后，只补 N=16 在 1.10/0.80 V 的 code={0,16} 四个端点场景。
Step 12 固定 N_characterize=16，只补浅/中/深相邻代码缺失场景，导出中调步长包络。
Step 13 写 future_fine_stage_interface.json，明确未来细调范围至少覆盖一个最坏中调步长。
Step 14 使用历史 617.031773... ps 仅做 future_range_projection；禁止据此扩建完整链。
Step 15 生成 summary、报告和纯 Python 回归。
Step 16 无论 GO 还是 NO-GO，本计划在“路径选择中调级表征”处停止；禁止接 sensor/XOR/DFF、自校准、裕量检测、跌落扫描、PVT、RTL、功耗、面积和版图。
```

---

# 8. Codex 最重要的宏观提醒

本计划不是把上一版错误计划“少跑几个仿真”而已，而是**成功判据发生了变化**。

上一版错误地想让中调级单独完成：

```text
全 0.80--1.10 V 最终边界覆盖
+
细粒度分辨率
+
真实 D触发器锁定
+
上侧代码余量
```

本轮正确目标只有：

```text
论文式路径选择确实成立
+
中调代码延时严格单调
+
增加 N 主要扩展最大延时
+
最短路径不再承担随 N 线性增长的固定开销
+
输出未来细调级必须覆盖的中调步长包络
```

正确的研究逻辑是：

```text
上一轮结构性 NO-GO
        |
        v
路径选择中调级是否解决“范围/最小固定延时耦合”？
        |
        +-- NO-GO：停止，记录中调拓扑根因
        |
        +-- GO
             |
             v
下一份独立计划才研究标准单元负载细调级
             |
             v
再下一步验证“细调范围 >= 一个最坏中调步长”
             |
             v
再加入两级组合的旁路与配置跳过
             |
             v
最后才形成完整两级可编程延时线并重新进入 FTC 系统校准
```

**不要提前做后面的事情。**
