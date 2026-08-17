# FTC 路径选择中调级逐步骤执行计划

## 0. 任务定位：本计划只做“路径选择中调级”

当前远程 `main` 的最新已完成结构性结论是：

```text
Fine-Grained Controllable Delay = NO-GO
```

该结论来自 `main@d0b4c491b587bfc20629f31e0b9afabd44cd6d41`：上一份方案把完整阈值路径实现成大量相同的 FAST/SLOW（快/慢）单位可控延时单元串联。候选 A 的单位单元虽然在 1.10/0.95/0.80 V 下均得到正的细粒度延时增量，但每级都必须付出固定多路选择器延时，导致 SLOW/FAST（慢/快）调节比只有约 1.69--1.74，无法满足旧拓扑推导出的全范围结构性下界 3.247；候选 B 又因缺少已确认的低固定开销同极性旁路原语而被结构性阻断。因此后续 8 级链、完整链、真实 D 触发器校准均正确地没有继续运行。

本计划**不再救援“每一级都包含 FAST/SLOW 二选一”的串联单位单元结构**，也不再继续扫描新的单位单元。

新的宏观方向固定为：

> **只实现 He 等工作中“路径选择中调级”的核心思想：使用一条串行标准单元延时链产生逐级更深的路径节点，再用局部级联的路径选择结构和温度计编码控制，使数字代码增加时信号选择更深一级的传播路径。最短代码只经过最短合法路径，最长代码才经过完整深路径，因此增加总级数主要扩展最大延时，而不会像上一方案那样让最小延时同时承担 N 个固定多路选择器开销。**

这里“中调级”指 medium stage（中等分辨率调节级），但本计划**只保留这一层**：

```text
不做 coarse stage（粗调级 / 环形振荡器计数）
不做 fine stage（细调级 / 可变电容或亚门延时调节）
不做 coarse+medium+fine 多级组合
```

本计划的唯一问题是：

> **单独使用路径选择中调级，能否在 0.80--1.10 V、TT/25 C 下形成单调、足够细、范围足够大的可编程阈值延时，并重新覆盖现有真实 D 触发器比较边界？**

只回答这个问题。若回答为 GO，后续电压跌落检测窗口、PVT（工艺/电压/温度）、最终 RTL（寄存器传输级逻辑）、面积功耗和版图必须由下一份独立计划推进；本计划不得自动扩展范围。

---

## 1. Codex 开始前必须读取并冻结的已有证据

### 1.1 最新 NO-GO 证据：只读，不重跑

必须读取：

```text
delay_chain/ftc/analysis/fine_grained_controllable_delay/requirements.json
delay_chain/ftc/analysis/fine_grained_controllable_delay/summary.json
delay_chain/ftc/analysis/fine_grained_controllable_delay/unit_cell.csv
delay_chain/ftc/analysis/fine_grained_controllable_delay/unit_cell_decision.json
delay_chain/ftc/reports/FTC_FINE_GRAINED_CONTROLLABLE_DELAY.md
delay_chain/ftc/scripts/run_fine_grained_controllable_delay.py
```

必须把以下事实视为已经证明，不得重复花 HSPICE 预算：

```text
1. 上一方案候选 A 的 6 个单位单元场景已经完成；
2. 其 Delta_unit 均为正，逻辑电平与边沿质量已检查；
3. 其 SLOW/FAST 调节比不足是结构性问题；
4. 8-Stage Short Chain、N Sizing、Full Chain、Real-DFF Calibration、C_lock+M 均为 NOT_RUN；
5. 因为上一方案在 Unit Cell Gate 已 NO-GO，所以没有任何理由重跑该 runner。
```

### 1.2 更早的 FTC 基线证据：只读，不重跑

必须读取：

```text
delay_chain/ftc/analysis/delay_code_refinement/summary.json
delay_chain/ftc/analysis/delay_code_refinement/calibration_gate.csv
delay_chain/ftc/analysis/delay_code_refinement/tap_screen.csv
delay_chain/ftc/reports/FTC_DELAY_CODE_BOUNDARY_REFINEMENT.md

delay_chain/ftc/analysis/programmable_acceptance_window/summary.json
delay_chain/ftc/analysis/programmable_acceptance_window/attack_sweep.csv
delay_chain/ftc/reports/FTC_PROGRAMMABLE_ACCEPTANCE_WINDOW_ROOT_CAUSE.md

delay_chain/ftc/analysis/static_self_calibration/calibration_trace.csv
delay_chain/ftc/analysis/static_self_calibration/range_mapping.json

delay_chain/ftc/analysis/minimal_pulse_comparator/architecture.json
delay_chain/ftc/discovery/selected_cells.json

delay_chain/phase2_vernier/discovery/mux_candidates.md
```

以下结论继续冻结：

```text
Formal VDD range    = 0.80--1.10 V
Initial corner      = TT / 25 C
Sensor tap          = tap29
Sensor initial path = 4 RVT / 0 LVT
Sensor XOR          = XOR2_X0P5M_A9TR40
Comparator DFF      = DFFRPQ_X0P5M_A9TR40
Delay cell          = BUF_X0P7M_A9TL40 优先
Supply              = same VDD_A / VSS_A
```

真实 D 触发器边界继续以：

```text
delay_chain/ftc/analysis/delay_code_refinement/calibration_gate.csv
```

为最高优先级证据；`tap_screen.csv` 只允许作为相邻 LVT（低阈值电压）缓冲器延时步长的数量级参考。

### 1.3 明确禁止重跑的历史脚本

本计划执行过程中禁止调用：

```text
delay_chain/ftc/scripts/run_static_self_calibration.py
delay_chain/ftc/scripts/run_programmable_acceptance_window.py
delay_chain/ftc/scripts/run_delay_code_refinement.py
delay_chain/ftc/scripts/run_fine_grained_controllable_delay.py
```

也禁止通过复制旧 runner 循环、改输出目录的方式变相重复这些历史场景。

旧 54 个静态自校准探针、旧 42 个接受窗口场景、边界细化 59 个场景、以及最新单位单元 6 个场景全部视为不可重复的已完成证据。

---

## 2. 为什么本次不能继续沿用上一方案的“单位调节比”早停逻辑

上一方案对 N 个完全相同的 FAST/SLOW 单元串联，每一个代码都必须穿过全部 N 个多路选择器，因此最小延时和最大延时都会随 N 增长；这使单位单元自身的慢/快比成为结构上限。

路径选择中调级的结构不同：

```text
短代码：在浅层节点退出
长代码：继续传播到更深层节点后再退出
```

因此增加总级数主要增加“最长可选路径”，而最短合法路径仍只停留在最浅层。上一份 `requirements.json` 中的：

```text
required_delay_ratio_lower_bound = 3.247270...
```

只作为“上一拓扑为什么失败”的历史诊断字段保留，**不得再作为路径选择中调级的单元 Gate**。

本次真正的结构 Gate 是“端到端可覆盖区间”。对任意工作电压 V，完整路径选择级最终应满足：

```text
D_min(V) < D_last_Q1(V)
D_max(V) > D_first_Q0(V)
```

符号说明：`V` 表示当前供电电压；`D_min(V)` 表示该电压下最短控制代码的真实阈值路径延时；`D_max(V)` 表示该电压下最长控制代码的真实阈值路径延时；`D_last_Q1(V)` 表示历史真实 D 触发器数据中最后一个 `Q=1` 对应的路径延时；`D_first_Q0(V)` 表示第一个 `Q=0` 对应的路径延时；`<` 表示左侧延时必须小于右侧边界；`>` 表示左侧延时必须大于右侧边界。

只有端点覆盖后，才有资格讨论中间代码分辨率与真实 D 触发器锁定。

---

## 3. 固定的新架构：只允许路径选择中调级

### 3.1 路径节点

定义输入节点：

```text
X0 = threshold_launch
```

串联 `BUF_X0P7M_A9TL40` 形成：

```text
X0 -> BUF -> X1 -> BUF -> X2 -> BUF -> X3 -> ... -> X(N+1)
```

其中 `X1` 是最浅合法路径节点，`X(N+1)` 是最深节点。

### 3.2 局部级联路径选择器，而不是大型平衡多路选择器树

使用局部 2:1 路径选择单元形成从深到浅的级联选择：

```text
Y(N) = X(N+1)
Y(i) = MUX( X(i+1), Y(i+1), T[i] )
OUT  = Y(0)
```

符号说明：`N` 表示温度计控制位数量；`i` 表示当前局部选择级索引；`X(i+1)` 表示当前深度的直接退出节点；`Y(i+1)` 表示继续进入更深路径后的返回节点；`T[i]` 表示第 i 个温度计控制位；`MUX(a,b,s)` 表示由选择位 `s` 在输入 `a` 与 `b` 中选择一个输出的 2:1 多路选择器；`=` 表示定义或连接关系；`i+1` 中 `+` 表示索引加一。

**不要在代码里硬编码 `S0=0` 一定选 A、`S0=1` 一定选 B。** Codex 必须先从实际 Verilog/CDL（晶体管级网表）定义确认 `MXT2` 的选择极性；若库定义与上面的抽象语义相反，只允许交换 A/B 连接，不能改变宏观结构。

第一实现优先使用当前已经在 FTC 阈值路径中实际使用过的：

```text
MXT2_X0P5M_A9TL40
```

禁止为了“找更快 MUX”进行无边界标准单元族扫描。若该单元在路径选择拓扑中结构性失败，只允许做一次只读静态审查，确认现有 `mux_candidates.md` 中的已知 `MXT2_X0P5M_A9TR40` 是否值得作为**同拓扑、不同 VT（阈值电压类别）**的唯一备选；不得转向另一类架构。

### 3.3 温度计编码语义

控制代码 C 的含义固定为“继续向更深路径传播多少级”。

```text
C = 0 : 000000...000  -> 选择 X1
C = 1 : 100000...000  -> 选择 X2
C = 2 : 110000...000  -> 选择 X3
...
C = N : 111111...111  -> 选择 X(N+1)
```

形式化定义：

```text
T[i](C) = 1,  当 i < C
T[i](C) = 0,  当 i >= C
```

符号说明：`T[i](C)` 表示控制代码 `C` 下第 `i` 个温度计位；`1` 表示继续进入更深路径；`0` 表示在当前层退出；`i` 是从 0 开始的控制位索引；`C` 是整数控制代码，范围为 0 到 `N`；`<` 表示“小于”；`>=` 表示“大于或等于”；`=` 表示定义关系。

### 3.4 相邻代码必须物理单调

对同一 VDD，必须满足：

```text
Delta_D(C,V) = D(C+1,V) - D(C,V) > 0
```

符号说明：`D(C,V)` 表示电压 `V`、控制代码 `C` 下的真实传播延时；`C+1` 表示比 `C` 深一级的相邻代码，其中 `+` 表示整数加法；`-` 表示两个真实传播延时之差；`Delta_D(C,V)` 表示相邻代码的增量；`>` 表示该增量必须严格为正。

这里不要求每一步完全相等，但不得出现负步长或零步长。

---

## 4. 全局禁止项

Codex 在本计划内不得自动转向：

```text
1. 第三组 3-bit / 8-tap 稀疏映射；
2. 16:1 / 32:1 / 64:1 大型平衡抽头多路选择器；
3. 上一方案的“每级 FAST/SLOW 二选一”串联单元；
4. 环形振荡器计数粗调级；
5. 标准单元可变电容细调级；
6. coarse+medium 或 medium+fine 两层组合；
7. 第二条参考延时链；
8. 第二个电压传感器；
9. 外部 Vref；
10. TDC（时间数字转换器）；
11. 运行时慢跟踪；
12. PVT 补偿；
13. 最终 monitor RTL；
14. 面积/功耗/版图优化；
15. 无边界标准单元家族 sweep（扫描）；
16. 为了“凑 GO”而修改正式 0.80--1.10 V 范围。
```

若路径选择中调级最终 NO-GO，停止并写根因报告；不得在同一 runner 内自行救援到其他结构。

---

## 5. 仿真复用与防浪费契约

新 runner 必须实现“历史证据只读 + 新场景可恢复”的机制。

### 5.1 新 runner 与目录

新增：

```text
delay_chain/ftc/scripts/run_path_selection_medium_stage.py
```

新增任务目录：

```text
delay_chain/ftc/analysis/path_selection_medium_stage/
delay_chain/ftc/runs/path_selection_medium_stage/r1/
```

最终报告：

```text
delay_chain/ftc/reports/FTC_PATH_SELECTION_MEDIUM_STAGE.md
```

测试：

```text
delay_chain/ftc/tests/test_path_selection_medium_stage.py
```

### 5.2 每个新 HSPICE 场景必须有确定性场景 ID

场景 ID 至少由以下字段决定：

```text
phase
topology_version
mux_cell
delay_cell
N
code
vdd_v
sensor_included
dff_included
```

每个场景目录写入 `scenario_manifest.json`，至少保存：

```text
netlist_sha256
runner_sha256
input_evidence_sha256
parameters
completion_status
measurement_file
```

如果场景目录已经存在，并且：

```text
1. completion_status = PASS；
2. netlist_sha256 与当前将要运行的 deck 完全一致；
3. 参数完全一致；
4. HSPICE listing 与 measurement 完整；
```

则必须直接复用，禁止再次调用 HSPICE。

若哈希不同，视为新设计，不得覆盖旧场景；创建新的 run revision（例如 `r2`）。

### 5.3 禁止“为了确认一下”重复历史仿真

历史 sensor、XOR、DFF、3-bit mapping、acceptance-window、单位 FAST/SLOW cell 均不再单独重跑。

只有当新的**路径选择拓扑**首次引入新的加载与传播路径时，才允许产生新的 HSPICE 数据。

---

# Phase 0 — 冻结需求与写出路径选择专用 requirements（0 个新 HSPICE）

## 6. Step 0.1：读取现有真实 DFF 边界

从：

```text
delay_chain/ftc/analysis/fine_grained_controllable_delay/requirements.json
```

直接复用已经提取好的：

```text
real_boundary_brackets_by_vdd
high_vdd_boundary_bracket
low_vdd_boundary_bracket
reference_adjacent_lvt_step_ps_by_vdd
required_delay_span_ps
source_file_sha256
```

同时重新校验这些字段对应的历史源文件 SHA256，但**不要重新生成历史数据**。

## 7. Step 0.2：写出新任务 requirements

输出：

```text
delay_chain/ftc/analysis/path_selection_medium_stage/requirements.json
```

至少记录：

```text
formal_vdd_range_v
anchor_vdd_v = [1.10, 0.95, 0.80]
real_boundary_brackets_by_vdd
reference_adjacent_lvt_step_ps_by_vdd
historical_fine_grained_no_go
historical_unit_cell_result_sha256
historical_required_delay_ratio_lower_bound_diagnostic_only
architecture = path_selection_medium_only
coarse_stage = forbidden
fine_stage = forbidden
source_file_sha256
```

这里必须明确把 `historical_required_delay_ratio_lower_bound_diagnostic_only` 标记为“仅历史诊断，不是本拓扑 Gate”。

Phase 0 完成后运行纯 Python 测试；不得运行 HSPICE。

---

# Phase 1 — 静态搭建路径选择中调级并做拓扑证明（0 个新 HSPICE）

## 8. Step 1.1：先解析实际 MUX 选择极性

从已经存在的标准单元源文件中，只读解析：

```text
MXT2_X0P5M_A9TL40
```

确认：

```text
CDL port order
Verilog port order
S0=0 选择哪一路
S0=1 选择哪一路
输出是否同极性
电源/阱连接顺序
```

把结果写入：

```text
delay_chain/ftc/analysis/path_selection_medium_stage/cell_contract.json
```

不允许通过 HSPICE 扫描来“猜”选择极性；先从库定义得到确定事实。

## 9. Step 1.2：实现纯网表拓扑生成器

在新 runner 中实现：

```text
build_path_selection_medium_stage(N, code, ...)
thermometer_code(N, code)
trace_selected_path(N, code)
```

`trace_selected_path()` 必须是纯 Python 图/连接分析，不依赖 HSPICE。

对 `N_test = 8`，所有 `code = 0..8` 必须证明：

```text
1. code=0 选择 X1；
2. code=8 选择 X9；
3. code 每增加 1，只把退出点向深处移动一级；
4. 没有组合环；
5. 没有多驱动；
6. 没有悬空选择节点；
7. 不存在 16:1/32:1 平衡 MUX 树；
8. 不存在 FAST/SLOW 串联单位单元；
9. 不存在粗调级或细调级器件。
```

输出：

```text
delay_chain/ftc/analysis/path_selection_medium_stage/topology_contract.json
```

若静态拓扑不能满足以上条件，直接 `ARCHITECTURE_BLOCKED`，0 个新 HSPICE，结束。

---

# Phase 2 — 8 控制位短链的最小电气证明

这里的 `N_test=8` 只用于证明路径选择拓扑的单调性和边沿质量，不代表最终范围。

## 10. Step 2.1：Gate A，只跑 9 个新场景

固定：

```text
VDD  = 1.10, 0.95, 0.80 V
code = 0, 4, 8
N    = 8
```

总计 9 个场景。

本阶段只含路径选择中调级，不接 sensor/XOR/DFF；用统一输入边沿直接测量 `OUT`。

测量：

```text
D_code_rise_ps
D_code_fall_ps
output_rise_time_ps
output_fall_time_ps
output_logic_high
output_logic_low
unexpected_transition_count
```

Gate A 必须满足：

```text
1. 三个 VDD 下 D(0) < D(4) < D(8)；
2. 输出逻辑高低电平合法；
3. 没有额外毛刺；
4. 边沿可被真实 DFF CK 接收；
5. 0.80 V 与 1.10 V 都没有失真到无法测量。
```

任一失败立即 NO-GO，不进入后续 10 个短链场景。

## 11. Step 2.2：Gate B，只补中间代码，不重跑 Gate A

若 Gate A 通过，在 0.95 V 只补：

```text
code = 1,2,3,5,6,7
```

因为 `0,4,8` 已经存在并必须复用，所以只新增 6 个场景。

合并后检查 `code=0..8` 全部相邻步长严格为正。

## 12. Step 2.3：Gate C，只检查两端相邻步长的电压鲁棒性

若 Gate B 通过，在 1.10 V 和 0.80 V 只补：

```text
code = 1,7
```

共新增 4 个场景；`code=0,8` 继续复用 Gate A。

因此 Phase 2 新 HSPICE 上限固定为：

```text
9 + 6 + 4 = 19
```

符号说明：`9` 是 Gate A 场景数；`6` 是 0.95 V 中间代码补充场景数；`4` 是高低电压两端相邻代码场景数；`+` 表示场景数相加；结果 `19` 是 Phase 2 允许的新 HSPICE 最大数量。

输出：

```text
delay_chain/ftc/analysis/path_selection_medium_stage/short_chain.csv
delay_chain/ftc/analysis/path_selection_medium_stage/short_chain_summary.json
```

---

# Phase 3 — 只用 Phase 2 新数据 + 历史 DFF 边界进行 N 尺寸推导（0 个新 HSPICE）

## 13. Step 3.1：建立保守延时模型

从 8 控制位短链测得的数据提取：

```text
D0(V)             最短代码真实延时
positive_steps(V) 已测正步长集合
step_min(V)       已测最小正步长
step_median(V)    已测中位正步长
```

不得把上一方案 `unit_cell.csv` 的 FAST/SLOW 比值带入 sizing Gate。

## 14. Step 3.2：用真实 DFF 边界估计最小 N

对每个已有正式电压点，寻找使预测路径能够跨过 `D_first_Q0(V)` 的最小代码，同时要求高压端 `code=0` 仍位于 `D_last_Q1(V)` 之前。

最终选择最小的 `N_candidate`，并额外保留至少两个上侧代码作为未来 `C_lock+1` / `C_lock+2` 的物理余量。

本计划设置硬上限：

```text
N_candidate <= 64
```

如果保守模型要求 `N_candidate > 64`，不要自动生成更大的链，也不要转向 coarse stage（粗调级）；记录：

```text
Path-Selection Medium Stage = NO-GO_FOR_BOUNDED_SIZE
```

并结束。

输出：

```text
delay_chain/ftc/analysis/path_selection_medium_stage/sizing.json
```

至少记录：

```text
N_candidate
predicted_lock_code_by_vdd
predicted_min_delay_by_vdd
predicted_max_delay_by_vdd
headroom_codes_by_vdd
model_source_scenarios
model_uncertainty_note
```

---

# Phase 4 — 完整 N 路径选择中调级端点验证

## 15. Step 4.1：先验证完整链没有因 N 增大破坏最短路径

只跑：

```text
VDD  = 1.10, 0.95, 0.80 V
code = 0, N_candidate
```

共 6 个新场景。

必须检查：

```text
1. 最短路径仍可测、逻辑合法；
2. 最长路径仍可测、逻辑合法；
3. D_min 与 D_max 的真实范围覆盖历史 DFF 边界；
4. 增加 N 没有让 code=0 出现灾难性固定延时膨胀；
5. 最长路径没有边沿退化、毛刺或逻辑幅度失败。
```

任一失败立即停止。

## 16. Step 4.2：只在三个锚点验证预测锁定代码附近

对每个：

```text
VDD = 1.10, 0.95, 0.80 V
```

从 `sizing.json` 得到 `k_pred`，仅补：

```text
k_pred-1, k_pred, k_pred+1
```

超出合法范围的代码跳过；与 Step 4.1 重叠的场景必须复用。

本阶段目标不是全码 sweep，而是确认 sizing 模型没有严重偏移。

输出：

```text
delay_chain/ftc/analysis/path_selection_medium_stage/full_chain_anchor.csv
```

如果三个锚点都无法在预测附近形成“延时跨越真实 DFF 边界”的迹象，停止，不进入真实 DFF 集成。

---

# Phase 5 — 接回真实 sensor/XOR/DFF，只做静态校准边界，不做 droop sweep

这是本计划最后的电气阶段。

## 17. Step 5.1：保持传感器与比较器完全冻结

完整 deck 必须继续使用：

```text
Sensor tap29
4 RVT / 0 LVT initial path
real XOR2_X0P5M_A9TR40
real DFFRPQ_X0P5M_A9TR40
same VDD_A / VSS_A
TT / 25 C
```

唯一替换项是：

```text
旧 3-bit sparse threshold path
或上一份 FAST/SLOW unit chain
        ↓
本计划 path-selection medium stage
```

不得趁集成阶段修改 sensor、XOR、DFF、readout settle（读出稳定时间）或正式供电范围。

## 18. Step 5.2：对 7 个正式 VDD 做“预测点附近局部搜索”

正式点：

```text
0.80, 0.85, 0.90, 0.95, 1.00, 1.05, 1.10 V
```

每个 VDD 从 `predicted_lock_code_by_vdd` 开始，不允许从 `code=0` 做全线性 sweep。

首批只跑：

```text
k_pred-1, k_pred, k_pred+1
```

若没有形成相邻 `Q=1 -> Q=0` 边界，只允许根据结果向**一个方向**逐步扩展，单个 VDD 总场景数上限为 7。

如果 7 个场景内仍找不到边界，标记该 VDD 为 calibration failure，不继续扩大搜索。

## 19. Step 5.3：真实 DFF 校准 Gate

对每个正式 VDD，必须存在相邻代码：

```text
C_last_Q1
C_first_Q0 = C_last_Q1 + 1
```

符号说明：`C_last_Q1` 表示真实 D 触发器仍输出 `Q=1` 的最后一个控制代码；`C_first_Q0` 表示紧邻其后的第一个 `Q=0` 控制代码；`=` 表示定义关系；`+1` 表示控制代码增加一级，其中 `+` 表示整数加法。

并定义：

```text
C_lock = C_first_Q0
```

符号说明：`C_lock` 表示该供电电压下的启动静态锁定代码；`C_first_Q0` 是上一步找到的第一个 `Q=0` 代码；`=` 表示把二者定义为同一个值。

必须同时满足：

```text
1. 7 个 VDD 全部能找到相邻 Q=1 -> Q=0；
2. C_lock 不得位于 code=0；
3. 每个 VDD 至少保留 2 个更大合法代码；
4. Q 读出稳定、没有异常中间电平；
5. C_lock 随 VDD 的变化允许非线性，但不得出现由路径非单调导致的多重边界；
6. 实际边界与 Phase 4 预测差异必须记录，不允许静默重拟合后重跑。
```

输出：

```text
delay_chain/ftc/analysis/path_selection_medium_stage/calibration_gate.csv
delay_chain/ftc/analysis/path_selection_medium_stage/calibration_summary.json
```

### 本计划到此停止

即使 Phase 5 GO，也**不要**继续运行：

```text
droop attack sweep
C_lock + M attack characterization
PVT
monitor RTL
runtime tracking
power/area/layout
```

因为用户本轮明确要求只做“路径选择中调级”。

下一份 plan 才能决定是否使用：

```text
C_alarm = C_lock + M
```

符号说明：`C_alarm` 表示未来监测阶段使用的告警阈值代码；`C_lock` 表示本计划得到的静态锁定代码；`M` 表示未来可编程的物理代码裕量；`=` 表示定义关系；`+` 表示整数加法。本计划只保留至少两个上侧代码余量，不执行该检测窗口的攻击仿真。

---

# Phase 6 — 证据、测试与最终判定

## 20. Step 6.1：输出统一 summary

输出：

```text
delay_chain/ftc/analysis/path_selection_medium_stage/summary.json
```

阶段状态固定包含：

```text
Historical Evidence Freeze
Static Topology Contract
8-Control Short Chain
N Sizing
Full-Chain Anchor
Real-DFF Calibration
```

每个阶段只能是：

```text
GO
NO-GO
ARCHITECTURE_BLOCKED
NOT_RUN
```

任一前级失败，所有后续电气阶段必须 `NOT_RUN`。

## 21. Step 6.2：最终 GO 条件

只有同时满足下列条件，才能发布：

```text
Path-Selection Medium Stage = GO
```

条件：

```text
1. 静态拓扑确认为路径选择中调级，不是大型抽头 MUX 树；
2. 8 控制位短链所有已测相邻代码严格正增量；
3. 完整 N 链在 0.80--1.10 V 的边界需求上有端点覆盖能力；
4. 7 个正式 VDD 全部由真实 DFF 找到唯一相邻 Q=1 -> Q=0 边界；
5. 每个 C_lock 至少保留两个上侧代码；
6. 没有通过重跑历史实验、修改 sensor 或扩大架构范围来获得 GO。
```

任一不满足，则发布：

```text
Path-Selection Medium Stage = NO-GO
```

并明确根因属于：

```text
short-path fixed offset too large
range insufficient within N<=64
non-monotonic code delay
edge/logic integrity failure
real-DFF boundary not bracketed
insufficient upper-code headroom
other explicit measured cause
```

## 22. Step 6.3：报告

生成：

```text
delay_chain/ftc/reports/FTC_PATH_SELECTION_MEDIUM_STAGE.md
```

报告必须回答：

```text
1. 为什么上一份 FAST/SLOW 单位链 NO-GO 不等于路径选择中调级 NO-GO？
2. 新拓扑是否真正做到“短代码浅层退出、长代码深层传播”？
3. 8 控制位短链的真实单调性与步长是多少？
4. 最终 N 是如何仅由新短链数据和历史 DFF 边界推导的？
5. 完整链的最短/最长延时是否覆盖 0.80--1.10 V 边界？
6. 7 个正式 VDD 的真实 C_lock 和上侧代码余量是多少？
7. 本轮具体新增了多少 HSPICE 场景、复用了多少历史场景？
8. 哪些历史 runner 明确没有重跑？
9. 本轮没有做哪些后续工作？
```

---

## 23. 测试要求

新增：

```text
delay_chain/ftc/tests/test_path_selection_medium_stage.py
```

至少覆盖：

```text
1. thermometer_code(8,0) 到 thermometer_code(8,8) 正确；
2. code 越界拒绝；
3. trace_selected_path(8,C) 的退出节点严格为 X(C+1)；
4. deck 不含 ring oscillator（环形振荡器）；
5. deck 不含 fine varactor（细调可变电容）；
6. deck 不含 16:1/32:1 大 MUX 树；
7. deck 不含上一方案 FAST/SLOW unit-cell 模板；
8. 历史 runner 不被 import 或 subprocess 调用；
9. 已完成同哈希场景会被 resume/reuse（恢复/复用）而不是再次运行；
10. Gate A 失败后 Gate B/C 不调 HSPICE；
11. Phase 2 最大新场景预算为 19；
12. N_candidate > 64 时立即早停；
13. 真实 DFF 局部搜索每个 VDD 不超过 7 个新场景；
14. 任一 calibration failure 后不进入任何 droop sweep；
15. summary 的下游状态正确写成 NOT_RUN。
```

执行至少：

```text
python3 -m unittest delay_chain.ftc.tests.test_path_selection_medium_stage
git diff --check
```

如果仓库现有 FTC 测试入口有稳定、快速的纯 Python 回归，可额外运行；不得为了回归重新触发历史 HSPICE。

---

# 24. Codex 严格执行顺序

Codex 必须按下列顺序推进，不得跳步：

```text
Step 1  读取 main 最新提交与本 plan，确认最新 Fine-Grained Controllable Delay = NO-GO。
Step 2  读取并校验所有历史证据 SHA256；禁止运行四个历史 runner。
Step 3  生成 path_selection_medium_stage/requirements.json；0 个 HSPICE。
Step 4  解析 MXT2 实际选择极性与端口；0 个 HSPICE。
Step 5  实现温度计编码、局部级联路径选择拓扑与静态图检查；0 个 HSPICE。
Step 6  先跑 N=8、code={0,4,8}、3 个 VDD 的 9 个 Gate A 场景。
Step 7  Gate A GO 才补 0.95 V 的 6 个中间代码；复用已有 0/4/8。
Step 8  Gate B GO 才补 1.10/0.80 V 的 code={1,7} 共 4 个场景。
Step 9  只用 Phase 2 数据 + 历史真实 DFF 边界推导 N；0 个 HSPICE。
Step 10 若 N>64，立即 NO-GO；否则只跑完整链端点 6 个场景。
Step 11端点 GO 才跑三个锚点预测锁码附近场景；不做全码 sweep。
Step 12锚点 GO 才接回真实 sensor/XOR/DFF。
Step 13对 7 个 VDD 从预测点附近局部搜索，每个 VDD 最多 7 个新场景。
Step 14若 7 个 VDD 全部形成唯一相邻 Q=1 -> Q=0 且至少保留两个上侧代码，发布 GO。
Step 15否则发布 NO-GO，并把所有未执行后续阶段标成 NOT_RUN。
Step 16无论 GO/NO-GO，本计划都在静态校准处停止；禁止继续 droop、PVT、RTL、功耗、面积、版图。
```

---

## 25. 最重要的架构提醒

Codex 不要把“路径选择中调级”误实现成下列任一种旧结构：

```text
错误 1：每级都有 FAST/SLOW MUX，然后所有代码都穿过全部 N 个 MUX。
错误 2：先做 N 个 tap，再用 16:1/32:1/64:1 平衡 MUX 树选一个 tap。
错误 3：加入 ring oscillator 作为 coarse stage。
错误 4：加入 varactor 作为 fine stage。
```

本轮正确的宏观图只有：

```text
threshold_launch
      |
      v
 X0 -> BUF -> X1 -> BUF -> X2 -> BUF -> X3 -> ... -> X(N+1)
             |            |            |                 |
             +----exit----+----exit----+------ ... -------+
                  \            \                         /
                   \        local cascaded 2:1 MUX      /
                    +---- thermometer path select ------+
                                      |
                                      v
                                    OUT
                                      |
                                      v
                              real DFF clock input
```

控制代码越大，退出点越深；**最短代码不穿过完整 N 级选择固定开销**。这就是本轮从上一份结构性 NO-GO 中真正要改变的物理本质。
