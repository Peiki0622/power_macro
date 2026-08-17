# FTC 细粒度可控延时链逐步骤执行计划

## 0. 任务定位

当前 `main` 的最新已完成实验结论为：

```text
3-bit Boundary-Centered Mapping = NO-GO
```

该结果已经足以关闭当前“3 位控制 + 8 个稀疏物理抽头 + 7 个多路选择器”的粗粒度阈值路线。本计划**不再生成第三组 3 位抽头映射，也不再尝试通过继续调整稀疏抽头位置救援旧架构**。

新的宏观方向固定为：

> **保留现有 tap29 电压敏感脉冲传感器、异或脉冲和真实 D 触发器比较机制，将阈值路径改造成由多个“单位可控延时单元”串联组成的细粒度数字可控延时链。相邻数字代码必须对应“恰好多开启一个单位延时单元”，最终恢复 `C_lock + M` 的自校准和可编程检测裕量。**

本阶段最优先解决的问题不是完整监测器，也不是工艺/电压/温度全覆盖，而是先回答：

> **能否实现一个低固定开销、严格正延时增量、可级联、可形成足够大调节范围的单位可控延时单元？**

如果这个问题不能通过，立即输出结构级 NO-GO，不继续堆叠更长链、更宽代码或更多仿真。

---

## 1. 开始前必须读取并冻结的已有证据

Codex 开始前必须读取以下文件，只做解析和复用，不重新运行产生它们的历史仿真：

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
```

以下结论全部视为已证明事实，不再花 HSPICE 预算重复证明：

```text
1. 正式工作电压范围为 0.80--1.10 V；
2. tap29 电压敏感传感器在当前 TT/25 C 基线下有效；
3. 真实 XOR 脉冲产生机制有效；
4. DFFRPQ_X0P5M_A9TR40 可以完成真实脉冲宽度比较；
5. 现有启动自校准的 first-Q=0 语义有效；
6. 旧 [10,12,14,16,18,36,37,38] 映射的可编程接受窗口已经 NO-GO；
7. 最新 primary/fallback 两组 3 位边界映射均已经 NO-GO；
8. 粗粒度数字代码存在“数字 headroom 不等于真实物理时间 headroom”的根本问题。
```

### 明确禁止重跑

不得重新运行：

```text
delay_chain/ftc/scripts/run_static_self_calibration.py
delay_chain/ftc/scripts/run_programmable_acceptance_window.py
delay_chain/ftc/scripts/run_delay_code_refinement.py
```

不得重新生成旧 54 个静态自校准探针、旧 42 个接受窗口场景或最新边界细化的 59 个场景。

历史 runner、历史 CSV/JSON、历史 raw run 一律只读。

---

## 2. 新架构的固定定义

### 2.1 必须保留

```text
Sensor tap          = tap29
Sensor initial path = 4 RVT / 0 LVT
Sensor XOR          = XOR2_X0P5M_A9TR40
Comparator DFF      = DFFRPQ_X0P5M_A9TR40
Formal VDD range    = 0.80--1.10 V
Initial corner      = TT / 25 C
Supply              = same VDD_A / VSS_A
```

现有 LVT 缓冲器优先继续使用：

```text
BUF_X0P7M_A9TL40
```

若候选单元需要二选一选择功能，第一候选优先复用已经在旧阈值路径中验证过的：

```text
MXT2_X0P5M_A9TL40
```

### 2.2 新延时链的语义

设完整链包含 `N` 个单位可控延时单元 `U0...U(N-1)`。

每个单元只有两种稳定状态：

```text
FAST：快速状态
SLOW：慢速状态
```

必须保持输入输出逻辑同极性。

控制代码 `C` 不允许产生任意离散组合，而必须译码成“连续开启编码”：

```text
C = 0 : 000000...000
C = 1 : 100000...000
C = 2 : 110000...000
C = 3 : 111000...000
...
C = N : 111111...111
```

因此必须保证：

```text
C -> C+1
```

只改变**一个**单位可控延时单元，由 FAST 切换到 SLOW。

最终目标仍为：

```text
C_alarm = C_lock + M
```

其中 `M=1` 必须具有“增加一个真实单位延时”的明确物理意义。

---

## 3. 全局禁止项

本计划执行期间禁止 Codex 自动转向下列路线：

```text
1. 第三组 3-bit / 8-tap mapping；
2. 4-bit 或 5-bit 大型抽头多路选择器；
3. 连续抽头 + 16:1 / 32:1 多路选择器作为替代方案；
4. coarse/fine 双层延时链；
5. 第二条参考延时链；
6. 第二个电压传感器；
7. 外部 Vref；
8. TDC；
9. 运行时慢跟踪；
10. PVT compensation；
11. 在模拟结构尚未 GO 前编写最终 monitor RTL；
12. 对标准单元库做无边界的大规模 cell-family sweep。
```

如果当前单位可控延时结构最终 NO-GO，先形成明确根因报告，再由下一份 plan 决定架构转向，不得在本 runner 内自行救援。

---

# Phase 0 — 只用历史真实 DFF 数据建立目标延时走廊

## 4. Step 0.1：解析真实比较边界，不运行 HSPICE

从：

```text
delay_chain/ftc/analysis/delay_code_refinement/calibration_gate.csv
```

提取每个已有电压锚点的真实：

```text
最后一个 Q=1 的 D_code_ps
第一个 Q=0 的 D_code_ps
```

形成真实 D 触发器比较边界区间：

```text
[D_last_Q1, D_first_Q0]
```

优先使用真实 DFF 结果，不允许使用 `tap_screen.csv` 的 `D_est` 代替比较边界。

`tap_screen.csv` 只允许用于计算现有 LVT 物理相邻 tap 的典型延时步长，作为“单位延时应该处于什么数量级”的参考。

输出：

```text
delay_chain/ftc/analysis/fine_grained_controllable_delay/requirements.json
```

至少记录：

```text
formal_vdd_range_v
real_boundary_brackets_by_vdd
high_vdd_boundary_bracket
low_vdd_boundary_bracket
required_delay_span_ps
required_delay_ratio_lower_bound
reference_adjacent_lvt_step_ps_by_vdd
source_file_sha256
```

### 关键要求

这里必须显式计算高压端到低压端所需的延时调节比例。

原因是对 `N` 个完全相同的串联可控单元：

```text
D_min ≈ D_common + N * d_fast
D_max ≈ D_common + N * d_slow
```

单纯增大 `N` 会同时增大最小延时和最大延时。**如果单元的 SLOW/FAST 延时比本身不足，则增加级数不能救援调节范围，反而会增加固定延时。**

这条物理约束是本计划最重要的早停依据之一。

Phase 0 不允许产生任何新的 HSPICE raw run。

---

# Phase 1 — 单位可控延时单元最小验证

## 5. Step 1.1：建立独立新 runner，不改历史 runner

新增：

```text
delay_chain/ftc/scripts/run_fine_grained_controllable_delay.py
```

新增任务目录：

```text
delay_chain/ftc/analysis/fine_grained_controllable_delay/
delay_chain/ftc/runs/fine_grained_controllable_delay/r1/
```

runner 必须：

```text
1. 启动时读取并校验 Phase 0 requirements.json；
2. 校验历史 NO-GO evidence 的 SHA256；
3. 只复用已经审查过的 HSPICE 执行/结果完整性检查函数；
4. 不导入历史 runner 的实验循环；
5. 所有新 raw data 只写入本任务目录；
6. 任何前级 Gate 失败后立即停止后续电气阶段。
```

---

## 6. Step 1.2：候选 A — 最简单可解释单元

第一候选固定为：

```text
FAST：输入直接进入二选一选择器
SLOW：输入先经过 1 个 BUF_X0P7M_A9TL40，再进入同一二选一选择器
选择器：MXT2_X0P5M_A9TL40
```

结构示意：

```text
                 +--------------------+
                 |                    |
IN --------------+------ FAST --------+---> MUX ---> OUT
                 |                    |       ^
                 +-> LVT BUF -> SLOW -+       |
                                             EN
```

这里的“单位延时”定义为完整单元两种状态的真实差值，而不是 BUF 的孤立延时：

```text
Delta_unit = t_slow - t_fast
```

### 只运行 6 个新 HSPICE 场景

```text
VDD = 1.10 V, 0.95 V, 0.80 V
state = FAST, SLOW
```

不要扫 0.85/0.90/1.00/1.05 V。

测量：

```text
t_fast_rise_ps
t_slow_rise_ps
Delta_unit_rise_ps
slow_fast_ratio
output_rise_time
output_fall_time
output_logic_high
output_logic_low
```

输出：

```text
delay_chain/ftc/analysis/fine_grained_controllable_delay/unit_cell.csv
```

---

## 7. Step 1.3：单位单元 Gate

候选必须同时满足：

```text
1. 三个 VDD 下 Delta_unit_rise_ps > 0；
2. FAST/SLOW 均保持正确逻辑极性；
3. 无毛刺、无异常中间电平；
4. 输出边沿可以被后级同类单元可靠接收；
5. Delta_unit 与历史相邻 LVT tap 延时处于同一数量级，而不是一个新的粗粒度大跳变；
6. 固定 FAST 延时必须被明确记录，不能只报告 Delta_unit；
7. 使用 requirements.json 检查该单元的可实现调节比是否有资格覆盖高压端到低压端的真实比较边界。
```

### 极重要的早停规则

计算：

```text
rho_unit(V) = t_slow(V) / t_fast(V)
```

同时从 Phase 0 得到系统要求的最低调节比例 `rho_required`。

若候选 A 在三个锚点下表现出明显的结构性不足，使其单位调节比不可能覆盖 `rho_required`，则：

```text
不要增加 N
不要构建 16/24/32 级链
不要进入系统级仿真
```

因为对相同单元串联，增加 `N` 不能突破单位结构的固有 FAST/SLOW 调节比，而且额外固定路径只会进一步恶化整体调节比。

---

## 8. Step 1.4：最多允许一个候选 B

只有候选 A 因“每级 MUX 固定延时过大 / 调节比不足”失败时，允许一个候选 B。

候选 B 的目标不是增加更多缓冲器，而是：

> **降低每一级 FAST 状态的固定通过延时，提高可旁路延时单元的调节效率。**

Codex 在运行候选 B 前只允许进行一次静态结构审查：

```text
1. 检查当前 SMIC40LL 已有 CDL/Verilog collateral 中是否存在可用于低开销旁路/插入的已知原语；
2. 不做全库性能 sweep；
3. 必须先把候选 B 的确切器件、端口、FAST/SLOW 路径写入 architecture_candidate.json；
4. 若当前库中没有可信的低开销实现，直接记录 ARCHITECTURE_BLOCKED，不得凭空发明不可复现器件。
```

候选 B 仍然只运行同样的 6 个场景。

本阶段最多：

```text
候选 A = 6 scenarios
候选 B = 6 scenarios（仅 A 失败时）
```

禁止第三候选。

输出：

```text
delay_chain/ftc/analysis/fine_grained_controllable_delay/unit_cell_decision.json
```

如果 A/B 都失败：

```text
Fine-Grained Controllable Delay Unit = NO-GO
```

立即停止整个计划。

---

# Phase 2 — 8 级短链验证“一级代码 = 一级真实延时”

只有 Phase 1 GO 才执行。

## 9. Step 2.1：构建 8 个完全相同单位单元

结构：

```text
IN -> U0 -> U1 -> U2 -> U3 -> U4 -> U5 -> U6 -> U7 -> OUT
```

控制采用连续开启编码：

```text
C=0 ... C=8
```

### 新仿真预算

只运行：

```text
VDD = 1.10, 0.95, 0.80 V
C = 0..8
```

最多 27 个新电气场景。

不要加入 sensor、XOR、DFF；这里只验证延时链本体。

输出：

```text
delay_chain/ftc/analysis/fine_grained_controllable_delay/short_chain.csv
```

每个点至少记录：

```text
D_code_ps
Delta_D_ps = D(C+1)-D(C)
output_slew
logic_valid
```

---

## 10. Step 2.2：短链 Gate

三个电压锚点全部必须满足：

```text
D(0) < D(1) < ... < D(8)
```

硬性要求：

```text
1. 所有 Delta_D_ps > 0；
2. 不出现某一级代码增加但延时减小；
3. 不出现异常毛刺；
4. 第 8 级输出仍保持可用边沿；
5. 相邻步长不得出现明显的单级巨跳；
6. 记录 min/median/max Delta_D_ps 和 max/min step ratio；
7. 记录 8 级全 FAST 到全 SLOW 的真实整体调节比。
```

如果短链调节比已经明确低于 Phase 0 的系统最低调节要求，则直接 NO-GO；**不要尝试通过增大 N 修复**。

如果严格单调性失败，也直接返回 Phase 1 根因分析，不进入长链。

输出：

```text
delay_chain/ftc/analysis/fine_grained_controllable_delay/short_chain_decision.json
```

---

# Phase 3 — 不运行 HSPICE，先计算是否存在合法级数 N

只有 Phase 2 GO 才执行。

## 11. Step 3.1：拟合短链延时模型

利用 8 级真实结果拟合仅用于 sizing 的模型：

```text
D_N(C,V) ≈ D_common(V) + (N-C)*d_fast_eff(V) + C*d_slow_eff(V)
```

其中：

```text
0 <= C <= N
```

模型只用于确定候选 `N`，不能作为最终系统 GO 证据。

---

## 12. Step 3.2：搜索最小合法 N

只做 Python 离线计算，不调用 HSPICE。

对合理整数 `N` 从小到大搜索，要求在：

```text
0.80, 0.85, 0.90, 0.95, 1.00, 1.05, 1.10 V
```

每个正常工作点都存在一个预测 first-zero 位置 `k`，并满足：

```text
1 <= k <= N-2
```

含义：

```text
低侧至少保留 1 个更短 code
高侧至少保留 2 个更长 code
```

高侧两个 code 是后续 `M=1`、`M=2` 可编程裕量的最低要求。

优先寻找**最小合法 N**，不要为了“更保险”直接使用 32 或 64 级。

若不存在任何合理 `N` 能同时覆盖 0.80--1.10 V 真实边界并保留两级物理裕量，则：

```text
Identical-Series Fine-Grained Delay Line = NO-GO
```

立即停止。

输出：

```text
delay_chain/ftc/analysis/fine_grained_controllable_delay/chain_sizing.json
```

必须包含：

```text
selected_N
predicted_lock_code_by_vdd
predicted_D_min_by_vdd
predicted_D_max_by_vdd
headroom_codes_by_vdd
model_residuals_from_8_stage_chain
no_go_reason_if_any
```

---

# Phase 4 — 完整 N 级可控延时链最小物理验证

只有 Phase 3 找到合法 `N` 才执行。

## 13. Step 4.1：不要全代码暴力扫

构建完整 `N` 级链，但第一轮只验证三个锚点：

```text
1.10 V
0.95 V
0.80 V
```

每个电压只测试：

```text
C = 0
C = predicted_k-1
C = predicted_k
C = predicted_k+1
C = predicted_k+2
C = N
```

去重后运行。

目的：

```text
1. 校验完整链的最小/最大延时范围；
2. 校验真实边界附近仍然严格单调；
3. 校验长链累计边沿退化没有破坏信号；
4. 校验短链模型没有产生不可接受的外推错误。
```

不要在这个阶段把所有 `0..N` 代码、7 个 VDD 全扫一遍。

输出：

```text
delay_chain/ftc/analysis/fine_grained_controllable_delay/full_chain_probe.csv
```

### Phase 4 Gate

必须满足：

```text
1. 三个锚点的 D_min/D_max 覆盖 Phase 0 所需比较边界；
2. predicted_k-1 .. predicted_k+2 局部严格单调；
3. predicted_k <= N-2；
4. 输出逻辑和边沿有效；
5. 不出现由长链累计造成的代码顺序反转。
```

失败则停止，不进入 sensor + DFF 系统级仿真。

---

# Phase 5 — 接回真实传感器和真实 DFF，重新做自校准 Gate

只有 Phase 4 GO 才执行。

## 14. Step 5.1：完整真实路径

最终测试结构固定为：

```text
                tap29 sensor
                     |
                     v
                 XOR pulse
                     |
                     | D
                     v
                real DFF
                     ^ CK
                     |
       fine-grained controllable delay line
                     ^
                     |
                 code C
```

不得修改 sensor tap、XOR 或 DFF 来适配新延时链。

---

## 15. Step 5.2：7 个正常电压锚点最小校准

对：

```text
0.80, 0.85, 0.90, 0.95, 1.00, 1.05, 1.10 V
```

先使用 Phase 3/4 的预测 `k`，每个 VDD 只运行：

```text
k-1
k
k+1
k+2
```

要求真实 DFF：

```text
Q(k-1) = 1
Q(k)   = 0
Q(k+1) = 0
Q(k+2) = 0
```

且：

```text
D(k-1) < D(k) < D(k+1) < D(k+2)
```

若预测 `k` 偏移，最多允许在该 VDD 附近补测 `±2 code` 来定位真实 first-zero。

禁止重新扫整个 `0..N`。

若真实 first-zero 最终落在：

```text
k < 1
或
k > N-2
```

则该完整链失败，不得通过增加 N 临时救援；回到 Phase 3 解释模型/结构根因，再形成新的计划。

输出：

```text
delay_chain/ftc/analysis/fine_grained_controllable_delay/calibration_gate.csv
```

---

# Phase 6 — 仅在校准 GO 后验证 C_lock + M

## 16. Step 6.1：最小静态跌落可行性

只使用三个 baseline：

```text
0.85 V
0.95 V
1.10 V
```

只测试：

```text
M = 1
M = 2
```

定义仍为：

```text
C_alarm = C_lock + M
```

采用与历史接受窗口一致的自适应电压扫描原则：

```text
从 baseline - 50 mV 开始
每次下降 50 mV
最低到 0.80 V
首次出现 Q=1 后停止粗扫
只在最后 Q=0 / 首次 Q=1 之间做 10 mV 细化
```

注意：这里运行的是**新细粒度可控延时链**，因此属于新实验；不得重新运行旧 3 位 mapping 的 42 个历史场景。

### 最小通过条件

```text
1. 三个 baseline 的 M=1 均应在合法范围内出现真实 Q=1；
2. M=2 不得比 M=1 更浅触发；
3. 随 attack VDD 降低，Q 不得出现 0 -> 1 -> 0 回退；
4. 至少一个 baseline 的 M=1 与 M=2 在 10 mV 网格上具有可区分的触发边界；
5. C_lock+1 和 C_lock+2 必须分别对应一个、两个真实单位延时增量，而不是新的大跳变。
```

输出：

```text
delay_chain/ftc/analysis/fine_grained_controllable_delay/acceptance_feasibility.csv
```

---

# Phase 7 — 结果冻结与后续边界

## 17. Step 7.1：统一结果文件

最终生成：

```text
delay_chain/ftc/analysis/fine_grained_controllable_delay/summary.json
delay_chain/ftc/reports/FTC_FINE_GRAINED_CONTROLLABLE_DELAY.md
```

报告必须明确区分：

```text
Unit Cell
8-Stage Short Chain
N Sizing
Full Chain
Real-DFF Calibration
C_lock + M Feasibility
```

每一级给出：

```text
GO / NO-GO / NOT_RUN
```

后一级因为前一级失败而未运行时必须写 `NOT_RUN`，不能伪装成通过。

---

## 18. 只有最终 TT/25 C GO 后才允许的下一步

只有同时满足：

```text
Unit Cell                  = GO
8-Stage Short Chain        = GO
N Sizing                   = GO
Full Chain                 = GO
Real-DFF Calibration       = GO
C_lock + M Feasibility     = GO
```

才允许下一份 plan 进入：

```text
1. PVT 验证；
2. 校准控制器代码宽度参数化；
3. monitor RTL；
4. 功耗/面积评估；
5. 版图负载和寄生敏感性。
```

本计划内不提前执行这些工作。

---

# 19. Codex 执行顺序清单

严格按以下顺序执行，不允许跨阶段：

```text
[0] 读取历史证据并校验 SHA256
    |
    v
[1] 从真实 DFF calibration_gate.csv 建 requirements.json
    |   不运行 HSPICE
    v
[2] 候选 A 单单元：3 VDD x 2 state
    |
    +-- NO-GO --> 最多候选 B：3 VDD x 2 state
    |                |
    |                +-- NO-GO --> STOP + report
    v
[3] 8 级短链：3 VDD x 9 code
    |
    +-- 非严格单调/调节比不足 --> STOP + report
    v
[4] 离线计算最小合法 N
    |   不运行 HSPICE
    |
    +-- 不存在合法 N --> STOP + report
    v
[5] 完整 N 级链三锚点局部验证
    |
    +-- NO-GO --> STOP + report
    v
[6] 真实 sensor + XOR + DFF：7 个 VDD 局部校准
    |
    +-- NO-GO --> STOP + report
    v
[7] 三 baseline，M=1/2 的最小静态跌落可行性
    |
    v
[8] 发布 summary.json + report
```

---

# 20. 必须增加的回归测试

新增：

```text
delay_chain/ftc/tests/test_fine_grained_controllable_delay.py
```

至少测试：

```text
1. 历史 runner 未被修改/调用；
2. formal range 固定 0.80--1.10 V；
3. sensor tap 固定 tap29；
4. DFF/XOR 固定为历史已验证单元；
5. Phase 1 最大候选数 = 2；
6. Phase 1 失败后不会调度短链；
7. 短链失败后不会搜索/运行完整链；
8. N sizing 阶段禁止 HSPICE；
9. 连续开启编码满足 C+1 只翻转一个 FAST->SLOW 单元；
10. calibration 只在预测边界附近调度，不全代码扫描；
11. 旧 3-bit mapping、4/5-bit 大 MUX、连续抽头方案不会被 runner 自动生成；
12. summary 中未执行阶段必须为 NOT_RUN。
```

测试可以使用纯 Python 合成数据，不允许为了测试重新运行历史 HSPICE。

---

# 21. 最终成功标准

本计划不是为了“尽量跑出 GO”，而是为了用最小新增仿真预算回答一个架构问题：

> **单位可控延时单元能否以足够低的 FAST 固定延时，提供严格为正且细粒度的 SLOW-FAST 延时增量，并在串联后同时满足 0.80--1.10 V 的宽范围自校准覆盖和 `M=1/2` 的真实物理裕量？**

成功时应得到：

```text
数字 code +1
      =
一个单位单元 FAST -> SLOW
      =
一个稳定、真实、可测量的物理延时增量
```

失败时则必须明确区分：

```text
单位增量不稳定
固定 FAST 开销过大
整体调节比不足
级联后非单调
长链边沿退化
真实 DFF 边界无法覆盖
C_lock + M 仍无有效跌落窗口
```

任何一种结构性失败都比继续对旧粗粒度 mapping 做调参更有研究价值，也应直接作为下一次架构决策的输入。
