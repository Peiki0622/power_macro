# FTC 标准单元负载细调级：验证合同重审与方向纠偏执行计划

## 0. 任务定位

本计划**取代上一版“继续通过驱动器尺寸联合优化来寻找 GO”**的方向。

当前最新完整联合设计提交：

```text
2c7944a28cc5b838eb4cfeb9c9b0c3f7a5bc3199
feat(ftc): evaluate fine driver co-design
```

最新正式结论仍然是：

```text
Fine Driver Co-Design = NO-GO
```

但现有证据已经显示，当前 NO-GO 的直接触发条件与“延时线输出在固定绝对时刻达到 0.90/0.10 VDD”强绑定，而不是已经证明延时线无法产生合法的全摆幅延迟波形。

本计划的目标不是再试新的标准单元，而是先回答一个更基础的问题：

> **我们现在的高/低电平 Gate（判定门槛），究竟是在验证“延时线电气完整性”，还是错误地把“设计所需的边沿后移”当成了逻辑电平失败？**

只有把这个问题回答清楚以后，才允许继续改硬件。

---

# 1. Codex 开始前必须读取并冻结的证据

开始执行前必须确认远程 `main`（主分支）最新提交。如果 `2c7944a` 之后已有更新，必须先读取新增代码和结果，不得直接按本计划的旧快照执行。

必须充分读取：

```text
delay_chain/ftc/reports/FTC_STANDARD_CELL_LOAD_FINE_STAGE_DRIVER_CODESIGN.md
delay_chain/ftc/analysis/standard_cell_load_fine_stage_driver_codesign/summary.json
delay_chain/ftc/analysis/standard_cell_load_fine_stage_driver_codesign/requirements.json
delay_chain/ftc/scripts/run_standard_cell_load_fine_stage_driver_codesign.py
delay_chain/ftc/scripts/run_standard_cell_load_fine_stage.py
delay_chain/ftc/ftc_config.json
```

并继续读取上游只读证据：

```text
delay_chain/ftc/analysis/path_selection_medium_stage/
delay_chain/ftc/analysis/standard_cell_load_size_sweep/fallback_1/
delay_chain/ftc/analysis/standard_cell_load_driver_strength_probe/
```

历史中调、负载尺寸扫描、驱动器探测和联合设计原始结果一律**只读**。

---

# 2. 必须冻结的当前事实

## 2.1 中调级

```text
Path-Selection Medium Stage = GO
medium_N = 16
medium buffer = BUF_X0P7M_A9TL40
medium mux    = MXT2_X0P5M_A9TL40
```

不得修改中调拓扑。

## 2.2 当前最值得保留的细调负载

继续冻结：

```text
fine load   = NOR2_X4A_A9TL40
signal pin  = A
control pin = B
high load   = control 0
low load    = control 1
```

本计划不得重新扫描 NAND/NOR、不得重新做 X0P5/X8/中间尺寸搜索。

## 2.3 四档驱动器联合设计已经完成

最新结果：

```text
Driver                 K       Deep 0.80 V high / low
BUF_X0P8M_A9TL40       10      0.6856528515 / 0.0241139336 V
BUF_X1M_A9TL40         13      0.6343493771 / 0.04968455244 V
BUF_X1P4M_A9TL40       21      0.5702537681 / 0.08329650319 V
BUF_X2M_A9TL40         30      0.5417883611 / 0.117377286 V
```

四档正式状态均为 NO-GO。

但是必须同时冻结另一个事实：

```text
驱动器越强 -> FineRange_8 越小 -> 为覆盖一个中调步长需要的 K 越大
```

因此本计划禁止继续自动扩大到 X3/X4/X6/X8。

## 2.4 当前正式逻辑电平合同

历史 runner（运行脚本）使用：

```text
output_logic_high >= 0.90 * VDD
output_logic_low  <= 0.10 * VDD
```

这两个电压比例本身先不否定。

**本计划要重新审查的是采样时刻，而不是先放宽 0.90/0.10。**

当前固定采样点来自：

```text
launch = 1.0 ns
period = 6.0 ns
high sample = launch + period/4 = 2.5 ns
low sample  = launch + 3*period/4 = 5.5 ns
```

符号说明：`launch` 是输入第一上升沿发射时间；`period` 是输入周期；`/` 表示除法；`+` 表示时间相加；`2.5 ns` 和 `5.5 ns` 是当前代码固定读取输出电压的绝对时刻。

---

# 3. 本计划必须采用的参考文献方向

本计划按 He、Su、Yang 2025 的可综合 FIA monitor（故障注入监测器）方法纠偏，但只吸收与本阶段直接相关的设计原则：

```text
1. 延时线本来就是为了把边沿向后移动；
2. 细调级使用标准单元输入端可变电容负载；
3. 细调范围需要覆盖粗一级/中一级的一个步长；
4. 逻辑正确性最终应与捕获边沿/锁定关系关联，而不是与任意固定绝对采样点关联；
5. bypass（旁路）用于处理较大的固定延时 offset（偏移）；
6. configuration skip（配置跳过）用于处理级间切换产生的非单调区间；
7. 延时单元类型、单元数量、实际分辨率是联合优化问题。
```

注意：本计划**暂不实现** bypass 和 configuration skip，只把它们保留为后续结构级任务。

---

# 4. 当前最重要的假设

本计划需要验证以下假设，而不是直接把它当成结论：

> 当前四档 driver（驱动缓冲器）的 NO-GO 中，至少 X0P8 的 0.80 V 深路径失败可能是“固定采样时刻早于真正 90%/10% 交叉点”导致的验证假阴性，而不是输出永远无法达到合法高/低电平。

当前报告已经给出只读审计结果：

```text
Driver     high sample - 90% crossing     low sample - 10% crossing
X0P8       -40.556 ps                     +56.009 ps
X1         -86.308 ps                     +26.776 ps
X1P4       -142.156 ps                    -2.607 ps
X2         -163.144 ps                    -22.479 ps
```

负值表示固定采样发生在相应阈值交叉之前。

因此下一阶段首先研究**验证合同**，而不是继续换 cell（标准单元）。

---

# 5. 新任务目录和代码边界

新增：

```text
delay_chain/ftc/scripts/run_fine_stage_validation_contract_audit.py
delay_chain/ftc/analysis/fine_stage_validation_contract_audit/
delay_chain/ftc/runs/fine_stage_validation_contract_audit/
delay_chain/ftc/reports/FTC_FINE_STAGE_VALIDATION_CONTRACT_AUDIT.md
delay_chain/ftc/tests/test_fine_stage_validation_contract_audit.py
```

不得覆盖或改写：

```text
standard_cell_load_fine_stage/
standard_cell_load_size_sweep/
standard_cell_load_driver_strength_probe/
standard_cell_load_fine_stage_driver_codesign/
```

不得为了让新判据通过而修改历史 `summary.json`、CSV、scenario manifest（场景清单）或报告。

---

# Phase 0 — 冻结旧 NO-GO 和新问题定义（0 个 HSPICE）

生成：

```text
delay_chain/ftc/analysis/fine_stage_validation_contract_audit/requirements.json
```

至少记录：

```text
upstream_driver_codesign_decision = NO-GO
upstream_commit = 2c7944a28cc5b838eb4cfeb9c9b0c3f7a5bc3199
fixed_load = NOR2_X4A_A9TL40__signal_A
primary_candidate_driver = BUF_X0P8M_A9TL40
primary_candidate_K = 10

legacy_high_ratio = 0.90
legacy_low_ratio = 0.10
legacy_high_sample_s = 2.5e-9
legacy_low_sample_s = 5.5e-9

new_hardware_search = forbidden
load_rescan = forbidden
driver_rescan = forbidden
medium_change = forbidden
bypass = future_work
config_skip = future_work
dff_integration = future_work
sensor = forbidden
droop_sweep = forbidden
pvt = forbidden
rtl = forbidden
layout = forbidden
```

并保存所有上游证据 SHA256。

---

# Phase 1 — 只读重解析已有 r2 原始结果（0 个 HSPICE）

这是本任务最重要的一步。

## Step 1.1：不要使用固定时刻电平作为新的硬 Gate

保留旧指标：

```text
V(2.5 ns)
V(5.5 ns)
```

但把它们改名为：

```text
legacy_fixed_sample_high
legacy_fixed_sample_low
```

只作为诊断数据，不允许直接触发新的 `delay_line_waveform_invalid`。

## Step 1.2：从原始测量中读取阈值交叉顺序

对已有最终 revision `r2` 的每个场景重新读取：

```text
t_out_rise_10
t_out_rise
t_out_rise_90
t_out_fall_90
t_out_fall
t_out_fall_10
t_out_rise_2
t_out_fall_2
```

其中 `t_out_rise`/`t_out_fall` 是 50% VDD 交叉时间。

新的第一层“延时线全摆幅波形存在”要求：

```text
t_rise10 < t_rise50 < t_rise90 < t_fall90 < t_fall50 < t_fall10
```

符号说明：`t_rise10`、`t_rise50`、`t_rise90` 分别表示第一次上升沿跨过 10%、50%、90% VDD 的时刻；`t_fall90`、`t_fall50`、`t_fall10` 分别表示随后下降沿跨过 90%、50%、10% VDD 的时刻；`<` 表示时间必须严格按顺序发生。该关系成立表示该输出脉冲确实完成了从低到高再回到低的完整阈值穿越。

必须同时要求：

```text
unexpected_transition_count = 0
```

如果某个场景连 90% 或 10% crossing（交叉）都不存在，才属于真正的全摆幅电气失败。

## Step 1.3：计算相对波形窗口，不再用绝对 2.5/5.5 ns 判断

定义 90% 高电平窗口：

```text
W_high90 = t_fall90 - t_rise90
```

符号说明：`W_high90` 表示输出处于至少 90% VDD 区域的时间窗口；`t_fall90` 是下降沿离开 90% VDD 的时间；`t_rise90` 是上升沿进入 90% VDD 的时间；`-` 表示时间差。

第一层要求只需要：

```text
W_high90 > 0
```

符号说明：`> 0` 表示高电平窗口必须真实存在。此阶段不人为规定最小窗口长度，因为未来实际最小窗口应由 DFF（触发器）建立/保持时间和捕获边沿合同决定。

同理记录 50% 脉宽：

```text
W_50 = t_fall50 - t_rise50
```

符号说明：`W_50` 是输出第一次上升到 50% VDD 到随后下降到 50% VDD 之间的脉冲宽度；`-` 表示时间差。

只记录，不以与输入 3 ns 完全相等作为硬 Gate。

## Step 1.4：重新计算 X0P8 + K=10 的中细调关系

优先只读重算：

```text
Driver = BUF_X0P8M_A9TL40
Load   = NOR2_X4A_A9TL40__signal_A
K      = 10
```

继续使用 50% crossing 的传播延时计算覆盖关系。

每个代表边界：

```text
M = 0 -> 1
M = 7 -> 8
M = 15 -> 16
VDD = 1.10 / 0.95 / 0.80 V
```

要求：

```text
D(M,K,V) >= D(M+1,0,V)
```

符号说明：`D(M,K,V)` 表示中调代码 `M`、最大细调代码 `K`、供电电压 `V` 下的 50% 上升传播延时；`D(M+1,0,V)` 表示下一中调代码配合最小细调代码时的传播延时；`>=` 表示本级细调上限必须达到或超过下一中调档位起点，从而没有延时空洞。

同时重新验证：

```text
delta_fine_max(V) < MediumStep_coupled_min(V)
```

符号说明：`delta_fine_max(V)` 是电压 `V` 下最大相邻细调步长；`MediumStep_coupled_min(V)` 是细调结构接入后浅/中/深代表位置中的最小中调步长；`<` 表示细调最大一步仍必须小于中调最小一步。

**关键要求：**如果某个场景旧 `valid=False` 仅由 2.5/5.5 ns 固定采样导致，但所有阈值 crossing 存在且顺序合法，则必须把它分类为：

```text
legacy_fixed_sample_miss
```

而不是：

```text
electrical_waveform_failure
```

Phase 1 输出：

```text
r2_reclassification.csv
x0p8_k10_recomputed_coverage.json
legacy_gate_false_negative_candidates.json
```

---

# Phase 2 — 先做最坏端点的两周期定向验证

只有 Phase 1 证明 X0P8/K10 的问题主要可能是固定采样时刻后，才允许进入本阶段。

不得重新跑 378 场景矩阵。

## Step 2.1：只跑 1 个最坏端点

固定：

```text
Driver = BUF_X0P8M_A9TL40
Load = NOR2_X4A_A9TL40__signal_A
K = 10
M = 15
F = 10
VDD = 0.80 V
```

物理网表必须与现有联合设计完全一致。

唯一允许改变的是**仿真观测时间长度和新增 measurement（测量语句）**。

将瞬态仿真扩展到足够观察：

```text
第一次 rise
第一次 fall
第二次 rise
```

新增测量：

```text
first rise : 10% / 50% / 90%
first fall : 90% / 50% / 10%
second rise: 10% / 50% / 90%
```

定义低电平窗口：

```text
W_low10 = t_rise10_2 - t_fall10_1
```

符号说明：`W_low10` 表示第一次下降沿进入 10% VDD 以下后，到第二次上升沿重新离开 10% VDD 之前的低电平时间窗口；`t_rise10_2` 是第二次上升沿跨过 10% VDD 的时刻；`t_fall10_1` 是第一次下降沿跨过 10% VDD 的时刻；`-` 表示时间差。

要求：

```text
W_high90 > 0
W_low10  > 0
```

两个窗口都必须存在，并且不得出现额外 50% crossing。

如果这个单场景连完整两周期全摆幅都做不到，则停止：

```text
Validation-Contract Audit = REAL_ELECTRICAL_NO-GO
```

此时才证明需要改硬件。

## Step 2.2：禁止通过移动一个任意采样点来“救”结果

不能采用：

```text
把 high sample 从 2.5 ns 改成 2.7/3.0 ns，看到 PASS 就结束
```

新的验证必须基于**阈值 crossing 和相对窗口**，而不是换一个新的任意绝对时间点。

---

# Phase 3 — X0P8/K10 有界最终波形验证

只有 Phase 2 最坏端点 GO 才继续。

不扫描 X1/X1P4/X2，不更换负载，不更换 K。

只对最终覆盖边界端点做两周期波形验证：

```text
(M=0,F=10)  与 (M=1,F=0)
(M=7,F=10)  与 (M=8,F=0)
(M=15,F=10) 与 (M=16,F=0)

VDD = 1.10 / 0.95 / 0.80 V
```

总计：

```text
3 boundaries * 2 endpoints * 3 voltages = 18 scenarios
```

符号说明：`3 boundaries` 是浅/中/深三个代表中调边界；`2 endpoints` 是每个边界的“当前中调最大细调”和“下一中调最小细调”两个端点；`3 voltages` 是 1.10、0.95、0.80 V 三个锚点；`*` 表示场景数量相乘；结果为 18 个新 HSPICE 场景。

每个场景必须：

```text
完整 10->50->90 上升 crossing
完整 90->50->10 下降 crossing
W_high90 > 0
W_low10 > 0
unexpected_transition_count = 0
```

同时继续用原有 50% propagation delay（传播延时）验证中细调覆盖。

---

# Phase 4 — 重新定义本阶段 GO / NO-GO

## 4.1 Fine-Stage Validation Contract = GO

必须同时满足：

```text
1. Phase 1 证明旧固定采样失败与真实阈值 crossing 可分离；
2. X0P8/K10 的 0.95 V 全细调单调性继续成立；
3. X0P8/K10 三电压范围覆盖继续成立；
4. 最大细调一步仍小于最小耦合中调步长；
5. Phase 2 最坏 0.80 V 深路径两周期波形完整；
6. Phase 3 的 18 个最终覆盖端点全部存在真实高/低窗口；
7. 无额外转换/毛刺；
8. 没有通过放宽 0.90/0.10 比例得到 GO；
9. 没有换 driver/load/medium topology；
10. 没有重跑历史 378 场景矩阵。
```

如果全部满足，发布：

```text
Fine-Stage Delay-Line Waveform Contract = GO
Selected provisional fine driver = BUF_X0P8M_A9TL40
Selected provisional fine load = NOR2_X4A_A9TL40__signal_A
Provisional K = 10
```

注意必须使用 `provisional`（暂定），因为未来 bypass、配置跳过和最终 DFF 捕获合同仍可能改变最终 K 和固定延时。

## 4.2 REAL_ELECTRICAL_NO-GO

只有出现以下情况之一，才允许说真实电路不工作：

```text
missing_90_percent_crossing
missing_10_percent_crossing
pulse_collapse
nonpositive_high_window
nonpositive_low_window
unexpected_transition
fine_code_non_monotonic
fine_range_insufficient
fine_resolution_not_below_medium
medium_fine_gap_remains
```

如果发生真实电气 NO-GO，本计划立即停止。

**不得在同一次执行里继续试 X3/X4/X6/X8、重新换负载或加入新缓冲树。**

必须先发布根因报告，再开独立硬件修复计划。

---

# 6. 固定绝对采样点以后应该放在哪里

本计划不是说固定采样永远无用。

它应该在未来**消费者时序已经明确以后**使用，例如：

```text
fine delay output
      |
      v
真实 DFF / 比较触发器
      |
      v
capture edge（捕获边沿）
```

届时真正需要验证的是：

```text
threshold crossing + setup margin < capture edge
```

符号说明：`threshold crossing` 是延时输出达到接收器有效逻辑阈值的时间；`setup margin` 是真实 DFF 要求的数据建立时间裕量；`capture edge` 是 DFF 实际采样边沿；`+` 表示需要把 crossing 时间与建立时间相加；`<` 表示数据必须在捕获边沿前准备完成。

而不是继续使用与消费者无关的：

```text
2.5 ns / 5.5 ns
```

因此本计划**不提前猜 DFF setup/hold 数值**，也不实现 DFF；只把接口要求记录到：

```text
future_capture_contract.json
```

其中至少写：

```text
capture_edge_not_yet_frozen = true
setup_hold_not_yet_frozen = true
fixed_absolute_sample_not_a_fine_stage_hard_gate = true
```

---

# 7. 参考论文对后续架构的约束提醒

如果本计划 GO，下一阶段方向才允许进入：

```text
medium + fine 两级完整编码
        |
        +-- fine bypass
        +-- configuration skip
        +-- 真实 DFF 捕获合同
        +-- 自校准
```

不要在本计划里直接实现这些功能。

特别注意：论文明确说明细调级具有较大的 code-0 固定延时，因此 bypass 是正常架构组成，而不是当前细调设计失败的补丁；论文也明确用 configuration skip 处理粗/中/细级切换时的延时下降，而不是要求物理延时单元天然做到全局配置完全连续。

---

# 8. 回归测试要求

新增：

```text
delay_chain/ftc/tests/test_fine_stage_validation_contract_audit.py
```

至少测试：

```text
1. Phase 1 不得调用 HSPICE；
2. Phase 1 必须只读 final revision r2；
3. 历史 valid 字段不得被覆盖；
4. 新分类必须区分 legacy_fixed_sample_miss 与 electrical_waveform_failure；
5. 新 waveform Gate 必须依赖 crossing 顺序，而不是 2.5/5.5 ns 电压值；
6. 0.90/0.10 比例不得被放宽；
7. primary candidate 必须严格为 X0P8 + NOR2_X4A + K10；
8. Phase 2 只允许 1 个新 HSPICE 最坏端点；
9. Phase 3 最多 18 个新场景；
10. 新网表器件实例必须与历史 X0P8/K10 物理拓扑一致；
11. 只允许扩展 tran 观察时间和 measurement 语句；
12. 不允许 X1/X1P4/X2 新联合设计场景；
13. 不允许新 driver/load 扫描；
14. 不允许 medium topology 变化；
15. 不允许 bypass/config skip/DFF/sensor/droop/PVT/RTL/layout 场景；
16. summary 必须记录 historical_driver_codesign_rerun=0；
17. summary 必须记录 new_hspice_scenarios <= 19；
18. REAL_ELECTRICAL_NO-GO 后必须早停，不得自动硬件救援。
```

执行：

```text
python3 -m unittest delay_chain.ftc.tests.test_fine_stage_validation_contract_audit
git diff --check
```

---

# 9. Codex 严格执行顺序

```text
Step 1  拉取远程 main 并确认最新提交。
Step 2  充分阅读最新 driver-codesign 报告、summary、requirements、runner 和 core runner。
Step 3  冻结 X0P8/X1/X1P4/X2 的现有 NO-GO 为历史事实，不改写历史结论。
Step 4  新建 validation_contract_audit 目录、runner、report、test。
Step 5  Phase 0 生成 requirements 和 provenance；0 HSPICE。
Step 6  Phase 1 重解析 r2 原始测量；0 HSPICE。
Step 7  明确列出所有 legacy_fixed_sample_miss 与真正 missing-crossing 场景。
Step 8  仅对 X0P8 + NOR2_X4A + K10 重算三电压覆盖、单调性和分辨率。
Step 9  若 X0P8/K10 在 crossing 层面已经失败，发布 REAL_ELECTRICAL_NO-GO 并停止。
Step 10 若只剩固定采样冲突，进入 Phase 2。
Step 11 只运行 0.80 V、M15、F10、K10 的一个两周期最坏端点。
Step 12 若最坏端点无法形成正的高/低窗口，发布 REAL_ELECTRICAL_NO-GO 并停止。
Step 13 若最坏端点通过，只运行 Phase 3 的 18 个覆盖端点。
Step 14 用动态 crossing 合同重新给出 Fine Stage GO/NO-GO。
Step 15 若 GO，发布 provisional X0P8/NOR2_X4A/K10 和 future_capture_contract.json。
Step 16 若 NO-GO，只发布明确物理根因，不继续搜索新 cell。
Step 17 本计划结束。不得顺手实现 bypass、配置跳过、DFF、自校准或跌落检测。
```

---

# 10. 最终报告必须回答的问题

生成：

```text
delay_chain/ftc/reports/FTC_FINE_STAGE_VALIDATION_CONTRACT_AUDIT.md
```

至少明确回答：

```text
1. 当前 2.5/5.5 ns 固定采样 Gate 的代码来源是什么？
2. 它最初验证的到底是稳态逻辑电平还是固定时间点电压？
3. 四档 driver 的 NO-GO 中，有多少场景其实存在完整 10/50/90 crossing？
4. X0P8/K10 最坏 0.80 V 深路径是否真的跨过 90% VDD？在什么时候？
5. 它是否真的回到 10% VDD？在什么时候？
6. 两周期扩展后 W_high90 和 W_low10 是否为正？
7. X0P8/K10 在三电压下是否仍覆盖三个代表中调边界？
8. 0.80 V 下最大细调步长是否仍小于最小耦合中调步长？
9. 旧 NO-GO 是真实电气失败、验证假阴性，还是两者混合？
10. 为什么继续增大 driver 会导致 K 增大？
11. 为什么本轮不允许继续扫 driver/load？
12. 哪些历史场景明确没有重跑？
13. 新增 HSPICE 场景总数是多少，是否 <=19？
14. 如果 GO，为什么只能称为 Fine-Stage Delay-Line Waveform Contract GO，而不是完整 FTC macro GO？
15. 下一阶段为什么应该转向 bypass/configuration skip/真实 capture contract，而不是继续无方向换标准单元？
```

---

# 11. 本计划最核心的方向纠偏

Codex 必须停止下面这种循环：

```text
固定采样失败
   -> 换大 driver
   -> 灵敏度下降
   -> K 增大
   -> 总负载增大
   -> 再次固定采样失败
   -> 再换 driver
```

本轮先把问题拆开：

```text
问题 A：延时线是否真的能产生完整、单调、可覆盖的延迟波形？
问题 B：未来真实捕获器在什么边沿、以什么 setup/hold 约束采样？
```

只有 A 失败才说明当前细调硬件本身需要重构。

A 通过而旧固定采样失败，说明之前的 NO-GO 至少部分来自验证合同与延时线用途不匹配。

在没有回答 A 之前，不允许继续更换标准单元。
