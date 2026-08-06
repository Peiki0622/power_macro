# CNN 计算活动码本任务三补全实施计划

## 1. 计划目的

本计划用于指导 Codex 补全 `plans/cnn_compute_reuse_phase1_plan.md` 中任务三尚未完成的部分。

当前仓库已经完成：

- `multistat_w18_k5` W8/A8 定点参考模型；
- 16-lane CNN RTL、固定周期模型和真实窗口回归；
- 36 个固定 L32 窗口、108 次 RTL 仿真；
- RTL 信号翻转统计和 low/medium/high 活动分档；
- 初步 VCD/SAIF/DC 功耗尝试。

当前只证明了：

> 不同合法窗口能够在固定 12,892-cycle CNN 路径上产生可重复、可调的 RTL 翻转活动。

当前尚未证明：

- 各窗口具有可信、可复现的标准单元与 ROM 动态功耗；
- 存在可信的平均功耗、峰值功耗和窗口能量档位；
- SAIF 对综合网表的注释覆盖率达到可接受门槛；
- ROM 仿真 `Q_` 与物理 public `Q` 路径在功耗流程中一致；
- 任务三配置中的分档间隔和重复 CV 门槛真正被执行；
- 完整“窗口写入 + CNN 计算”能量已被测量；
- 系统真实推理间隔能够容纳完整 dummy inference slot。

本计划的最终目标是形成两个严格区分的产物：

```text
RTL activity codebook
    用于解释内部信号翻转和模块活动来源

Gate-level power codebook
    用于比较固定工艺/时钟条件下的平均动态功耗和窗口能量
```

只有 gate-level power codebook 和 idle-slot 预算同时通过，才能提出后续 real/dummy 固定时隙复用计划。

---

## 2. 冻结基线

执行本计划时必须以以下仓库状态为基线：

```text
baseline commit:
25366d29c970436f9addc5faddad86500bb338dc
```

关键冻结对象：

```text
模型：multistat_w18_k5
定点：W8/A8，沿用任务一认证包
MAC lanes：16
CNN compute latency：12,892 cycles
CNN initiation interval：12,893 cycles
窗口长度：L32
sensor_code 范围：[0,32]
ROM：CNNW384X128，384 x 128，mux=8
目标工艺基线：SMIC40LL TT / 1.10 V / 25 C
综合目标：2.000 ns
已验证 ROM 功能仿真周期：4.000 ns
```

不得在本计划中修改：

- CNN 浮点模型结构；
- 定点位宽、scale、舍入和饱和规则；
- 已认证权重；
- CNN 固定计算 schedule；
- Conv/Average/Max/Endpoint/Classifier 完整路径；
- 现有 36 个窗口的输入内容和 `pattern_id`；
- Safe/Critical 标签或输出定义；
- 已冻结 IID/OOD 数据和结果。

如果为了门级仿真必须增加 compatibility model、testbench force/bind 或名称映射，这些内容必须仅存在于仿真/分析路径，不能改变综合网表的功能逻辑和物理 ROM 接口。

---

## 3. 当前缺陷与本计划对应关系

| 当前缺陷 | 本计划处理阶段 |
| --- | --- |
| `PWR-415`：顺序单元输出未充分注释 | 阶段 2、3、4 |
| `PWR-428`：hard macro 输出未充分注释 | 阶段 2、3、4 |
| ROM compiler model 使用内部 `Q_`，综合使用 public `Q` | 阶段 2 |
| low/medium/high 由排序等分产生 | 阶段 1、6 |
| `activity_separation_fraction` 未执行 | 阶段 1、6 |
| `max_repeat_cv_fraction` 未作为失败门禁 | 阶段 1、6 |
| 当前只测 compute，不测窗口写入 | 阶段 5 |
| 自动测试没有覆盖任务三验收门禁 | 阶段 1、7 |
| 未证明完整 dummy slot 可被调度 | 阶段 8 |

阶段必须顺序执行。前一阶段未通过时，不得用后续阶段绕过缺陷。

---

## 4. 全局执行约束

### 4.1 禁止跨步

本计划完成前禁止实现：

- real/dummy window arbiter；
- dummy FIFO；
- dummy scheduler；
- PRNG/TRNG；
- 随机窗口生成器；
- 分段电容；
- PRECHARGE/ISOLATE/ASSIST；
- 计算与电荷联合调度；
- TVLA、CPA 或防护效果结论。

### 4.2 不得把代理量伪装成物理功耗

以下概念必须分别命名和存储：

```text
total_toggle_count          RTL 或 gate-level 翻转数量
peak_cycle_activity         单周期翻转峰值
average_dynamic_power_mw    工艺库和活动注释下的动态功耗
energy_window_nj            指定测量区间积分能量
peak_power_mw               工具确实支持并有可信时间分辨率时才填写
```

不得用 `total_toggle_count` 线性换算后填写 `average_dynamic_power_mw`。
不得把 `peak_cycle_activity` 填入 `peak_power_mw`。
不得把 vectorless DC power 当作窗口相关功耗。

### 4.3 run 目录和覆盖规则

所有生成物必须位于：

```text
rtl/cnn_monitor/runs/<new_task3_tag>/
```

建议 run tag：

```text
activity_power_codebook_20260802_r1
```

若目录已存在必须拒绝覆盖。不得删除或重写：

```text
runs/activity_codebook_20260802_r1/
runs/stage89_20260801_r1/
```

### 4.4 计划读取记录

每个阶段开始前，Codex 必须向新 run 的：

```text
evidence/plan_reads.log
```

追加：

```text
阶段号
UTC 时间
当前 Git commit
本计划 SHA256
执行命令
```

如果计划文件在执行过程中发生变化，必须停止并重新确认基线。

---

# 阶段 0：建立不可变输入清单

## Step 0.1：生成基线 manifest

### 要做什么

新增脚本或扩展现有 provenance 工具，生成：

```text
inputs/baseline_manifest.json
```

至少记录以下文件的路径、大小和 SHA256：

```text
rtl/cnn_monitor/rtl/cnn_monitor.sv
rtl/cnn_monitor/rtl/cnn_convolution_engine.sv
rtl/cnn_monitor/rtl/cnn_pool_classifier.sv
rtl/cnn_monitor/rtl/cnn_weight_rom.sv
rtl/cnn_monitor/rtl/cnn_window_buffer.sv
rtl/cnn_monitor/config/cnn_rtl_config_v1.json
rtl/cnn_monitor/config/cnn_activity_config_v1.json
任务一 parameter package manifest
ROM RCF
ROM Verilog model
ROM Liberty DB
16-lane mapped DDC
16-lane mapped Verilog netlist
16-lane SDF
16-lane SDC
36-window manifest
```

### 验证措施

- 缺少任一文件时失败；
- 文件摘要变化时失败；
- mapped DDC/netlist 必须对应 16 lanes；
- ROM RCF 摘要必须与任务二认证记录一致；
- 36-window manifest 必须仍为 36 条；
- 任务一权重摘要必须保持不变。

### 交付物

```text
inputs/baseline_manifest.json
evidence/baseline_manifest_check.log
```

### 停止条件

基线摘要不一致时停止，不允许自动重新综合、重新生成权重或替换 checkpoint 来“修复”。

---

# 阶段 1：修复活动分析器和验收门禁

本阶段先修复现有 RTL activity codebook 的逻辑缺陷，不涉及门级功耗。

## Step 1.1：新增任务三 v2 配置

### 要做什么

新增：

```text
rtl/cnn_monitor/config/cnn_activity_power_config_v2.json
```

必须显式包含：

```text
schema_version
config_id
baseline_commit
window_length = 32
sensor_code_min = 0
sensor_code_max = 32
mac_lanes = 16
repeat_count = 3
compute_latency_cycles = 12892
initiation_interval_cycles = 12893
activity_separation_fraction = 0.05
max_repeat_cv_fraction = 0.001
minimum_patterns_per_tier = 3
required_tier_count = 3
required_valid_pattern_count = 36
required_candidate_pattern_count = 31
```

增加功耗覆盖门槛：

```text
primary_input_annotation_fraction_min = 1.0
sequential_output_annotation_fraction_min = 0.95
rom_output_annotation_fraction_min = 1.0
overall_state_element_annotation_fraction_min = 0.95
reject_power_warning_ids = [PWR-415, PWR-428]
```

这些阈值在首次正式功耗运行前冻结。不得根据功耗结果降低。

### 验证措施

增加 schema 测试，缺少字段、字段类型错误、阈值越界均失败。

### 交付物

```text
config/cnn_activity_power_config_v2.json
tests/test_activity_power_config.py
```

## Step 1.2：禁止排序后强制三等分

### 要做什么

修改或新增分析器。建议保留现有：

```text
scripts/analyze_activity_vcd.py
```

作为 v1 历史证据，新增：

```text
scripts/analyze_activity_codebook_v2.py
```

v2 分档不得使用：

```python
按排序索引直接 low/medium/high 三等分
```

Codex 可以选择确定性的 1D 聚类或基于间隔的连续分段，但必须满足：

1. 无随机初始化，重复运行结果完全相同；
2. 使用实际测得指标，而不是 `pattern family`；
3. 每档至少 `minimum_patterns_per_tier` 条；
4. 相邻档中心差满足：

```text
(center_high - center_low) / center_low >= activity_separation_fraction
```

5. 所有模式的重复 CV 满足配置门槛；
6. 不能得到三档时，任务状态必须为 FAIL，不能退回强制等分；
7. control 窗口不参与候选聚类，但保留在报告中。

### 验证措施

构造合成单元测试数据：

- 清晰三档，应 PASS；
- 只有两档，应 FAIL；
- 三档中心间隔小于 5%，应 FAIL；
- 任一模式 CV 大于 0.1%，应 FAIL；
- 每档少于 3 条，应 FAIL；
- 输入顺序变化，结果不得变化。

### 交付物

```text
scripts/analyze_activity_codebook_v2.py
tests/test_activity_tiering.py
```

## Step 1.3：增加码本完整性门禁

### 要做什么

新增 validator：

```text
scripts/validate_activity_codebook.py
```

检查：

- 36 条记录存在；
- 31 条非 control 候选存在；
- 每条有 3 次重复；
- 每次 latency = 12,892；
- 无 overflow/protocol error；
- logits/decision 与 cycle model 一致；
- input SHA256 与窗口 manifest 一致；
- module toggle vector 组名完整；
- power 字段若未达到功耗门禁必须为 `null`；
- 不允许部分模式有功耗值、部分模式没有而仍报告 PASS。

### 验证措施

对缺记录、重复 pattern、错误 SHA、错误 latency、非空伪功耗字段逐项建立失败测试。

### 阶段 1 验收

运行现有 108 次 RTL 活动数据，通过 v2 分析器重新分析。

阶段 1 通过只表示：

> RTL activity tier 的分档和验收逻辑可信。

不得把阶段 1 结果描述为物理功耗档位。

---

# 阶段 2：解决 ROM `Q_` 与 public `Q` 的功耗可观测一致性

## Step 2.1：建立 ROM 路径审计

### 要做什么

新增脚本：

```text
scripts/audit_rom_observability.py
```

它必须分别解析并记录：

- RTL adapter 中的 ROM 实例名；
- mapped netlist 中的 ROM 实例路径；
- compiler model 的 public `Q`；
- compiler model 的 internal `Q_`；
- mapped netlist 中从 ROM `Q` 到 CNN consumer 的网络路径；
- SAIF 中对应 ROM output net 的层级名。

输出：

```text
analysis/rom_observability_audit.json
```

### 验证措施

- mapped netlist 必须恰有一个 `CNNW384X128`；
- ROM 地址和控制引脚保持冻结合同；
- consumer 数据路径在综合网表中必须源自 public `Q`；
- 仿真活动路径必须能映射到同一物理 Q net；
- 不能仅证明 internal `Q_` 有活动而 public Q 无活动。

## Step 2.2：实现仿真专用 ROM compatibility 层

### 要做什么

当前 delivered compiler model 在 VCS 中 public `Q` 为 X，而 internal `Q_` 正确。Codex 必须实现一种**仅用于门级活动仿真**的兼容方法，使综合网表可观察的物理 `Q` 网络获得与 internal `Q_` 完全一致的数据。

允许的实现方式，按优先级：

1. 仿真 library compatibility wrapper；
2. `bind` 到 ROM 实例的仿真适配器；
3. testbench 中受严格层级检查保护的 `force/release`；
4. 其他不会修改综合网表和综合 RTL的仿真方法。

禁止：

- 修改 RCF；
- 修改 ROM Liberty；
- 修改 mapped netlist 的逻辑连接；
- 在综合 RTL 中继续增加 `Q_` 分支；
- 使用与认证 ROM 内容无关的新行为 ROM；
- 跳过 ROM 读访问、直接给 CNN weight_word 注入权重。

### 验证措施

对全部 384 地址执行 exhaustive readback：

```text
public-Q-compatible output
== compiler internal Q_
== RCF expected word
```

每个地址均需检查：

- 请求地址；
- 一拍同步延迟；
- 128-bit 数据；
- q_valid；
- read disable 行为；
- 370..383 零填充；
- 未使用 lane 为零。

输出 384/384 PASS 才能进入阶段 3。

### 交付物

建议新增：

```text
tb/cnn_rom_activity_compat.sv
scripts/run_rom_public_q_activity_check.sh
analysis/rom_public_q_check.json
```

具体文件名可以调整，但必须与综合路径隔离。

## Step 2.3：证明兼容层不改变功能 RTL

### 要做什么

重新计算并比较以下 RTL 源文件 SHA256，必须与阶段 0 manifest 一致：

```text
cnn_monitor.sv
cnn_convolution_engine.sv
cnn_pool_classifier.sv
cnn_window_buffer.sv
cnn_weight_rom.sv
```

如果 `cnn_weight_rom.sv` 必须修改，只允许删除历史仿真 workaround 并把 workaround 移到纯仿真文件；修改后必须重新执行任务二完整 bit-true 回归和综合，且功能、周期、宏实例数、权重摘要完全不变。

### 阶段 2 停止条件

只要 public Q 仍为 X、SAIF 中 ROM output 无可映射活动，或必须修改物理 ROM 接口，阶段 2 判定 FAIL。

---

# 阶段 3：建立门级活动仿真流程

## Step 3.1：建立 gate-level 仿真入口

### 要做什么

新增：

```text
scripts/run_gate_activity_characterization.py
```

或等价 shell/Python driver。输入必须来自阶段 0 manifest：

```text
mapped netlist
mapped SDF
standard-cell simulation library
ROM compiler model
ROM compatibility layer
36-window manifest
```

禁止重新综合作为 driver 的隐式步骤。若 mapped netlist 不存在，应失败并提示先执行任务二综合。

### 仿真分两级

#### Level A：gate functional

- mapped netlist；
- standard-cell model；
- ROM compatibility；
- 不回标 SDF；
- 用于先证明功能、层级和活动可观测性。

#### Level B：gate SDF TT

- 同一 mapped netlist；
- 回标当前 mapped SDF；
- 使用与 ROM 模型兼容的已验证时钟周期；
- 用于生成最终功耗 SAIF。

若 2 ns 下 legacy ROM timing checker 仍不可用，正式 activity codebook 可以在 4 ns 下生成，但必须：

- 将结果明确标注为 250 MHz TT gate-level baseline；
- 不直接声称是 500 MHz 测量；
- 500 MHz 只能作为单独的频率缩放 projection 字段；
- projection 不得替代 4 ns 原始值。

### 验证措施

每个窗口在 Level A 和 Level B 均需检查：

```text
latency = 12892 cycles
safe_logit exact match
critical_logit exact match
decision exact match
numeric_overflow = 0
protocol_error = 0
result_valid one cycle
```

任一窗口失败即停止，不生成功耗码本。

## Step 3.2：生成层级稳定的 VCD/SAIF

### 要做什么

活动文件必须从 mapped gate-level DUT 生成，而不是 RTL DUT。

需要分别生成三个测量区间：

```text
compute_only
acquisition_only
end_to_end_slot
```

其中：

- `compute_only`：从 inference request 接受至 result commit；
- `acquisition_only`：32 个 sensor_code 写入周期；
- `end_to_end_slot`：32 个写入周期 + 固定 preamble + compute + result commit；
- reset 和非固定初始化不得计入；
- 每种模式使用相同边界。

活动文件路径建议：

```text
gate_functional/vcd/
gate_sdf/vcd/
gate_sdf/saif/
```

### 验证措施

- 每个 pattern/repeat/measurement_scope 均有唯一文件；
- 文件中顶层实例名与功耗 Tcl 完全一致；
- SAIF duration 与期望周期数一致；
- 不得混入 reset；
- 不得把 acquisition 和 compute 合并后再反推两部分。

## Step 3.3：重复性检查

### 要做什么

仍使用每窗口 3 次重复。对 gate-level：

- compute_only energy/activity；
- acquisition_only energy/activity；
- end_to_end_slot energy/activity；

分别计算 CV。

### 验收门槛

每个指标的 CV 必须小于配置中的 `max_repeat_cv_fraction`。超过即 FAIL，不允许取中位数后忽略不稳定性。

---

# 阶段 4：建立 SAIF 注释覆盖率审计和功耗门禁

## Step 4.1：新增 coverage-aware DC Tcl

### 要做什么

保留历史：

```text
synthesis/dc_activity_power.tcl
```

新增：

```text
synthesis/dc_gate_activity_power_v2.tcl
```

v2 Tcl 必须：

1. 读取阶段 0 的同一 mapped DDC；
2. link 同一 TT standard-cell DB 和 ROM DB；
3. 读取单个 gate-level SAIF；
4. 显式设置 SAIF instance path；
5. 输出 `report_power -hierarchy`；
6. 输出 switching-activity annotation 报告；
7. 列出未注释对象；
8. 单独列出 primary inputs、sequential outputs、ROM outputs；
9. 不使用 vectorless activity 填补缺失对象后冒充完全注释；
10. 保留所有 PWR warning ID。

Codex 可以使用 `report_switching_activity` 或当前 DC 版本的等价命令，但必须形成可解析的对象级证据。

## Step 4.2：新增 coverage parser

### 要做什么

新增：

```text
scripts/audit_saif_coverage.py
```

输出：

```text
coverage/coverage_<pattern>_<repeat>_<scope>.json
```

至少包含：

```text
total_primary_inputs
annotated_primary_inputs
primary_input_fraction
total_sequential_outputs
annotated_sequential_outputs
sequential_output_fraction
total_rom_outputs
annotated_rom_outputs
rom_output_fraction
total_state_elements
annotated_state_elements
overall_state_element_fraction
warning_ids
unannotated_object_examples
status
```

### 门禁

以下条件必须全部满足：

```text
primary_input_fraction == 1.0
sequential_output_fraction >= 0.95
rom_output_fraction == 1.0
overall_state_element_fraction >= 0.95
PWR-415 absent
PWR-428 absent
```

若 DC 版本即使覆盖充分仍固定发出某 warning，Codex 必须提供对象计数和最小复现证据，单独申请调整计划；不得直接在脚本中忽略 warning。

## Step 4.3：先运行一个 control preflight

### 要做什么

只对：

```text
control_all_15_r0
```

执行完整 gate SDF -> SAIF -> DC -> coverage audit。

### 通过条件

- 功能自检通过；
- ROM public Q 已注释；
- coverage 门槛全部通过；
- 无 PWR-415/PWR-428；
- report_power 有 internal、switching、leakage 和 total；
- 同一输入重复运行结果稳定。

### 停止条件

control preflight 未通过时，禁止批量运行 36 个模式。

---

# 阶段 5：生成完整窗口功耗指标

## Step 5.1：批量执行全部模式

### 要做什么

仅在阶段 4 preflight PASS 后，对：

```text
36 patterns x 3 repeats x 3 scopes
```

运行功耗分析。

总计应有：

```text
324 个 scope-level power reports
324 个 coverage JSON
```

如工具成本过高，可以每个 pattern 用一份同时包含三个固定 time scope 的活动文件，但最终仍必须输出三组独立指标，且每组可追溯到明确时间区间。

## Step 5.2：提取可信功耗

### 要做什么

新增：

```text
scripts/extract_gate_power_metrics.py
```

提取：

```text
internal_power_mw
switching_power_mw
leakage_power_mw
total_power_mw
dynamic_power_mw = internal + switching
measurement_duration_ns
energy_window_nj = dynamic_power_mw * duration_ns / 1000
```

对 end-to-end scope 同样计算。

若工具只给平均功耗，`peak_power_mw` 必须保持 `null`。只有得到时间分辨率功耗工具证据时才能填写 peak power。

## Step 5.3：保持 250 MHz 原始值与 500 MHz projection 分离

### 要做什么

如果正式 gate-level SAIF 基于 4 ns：

```text
measured_clock_period_ns = 4.0
measured_frequency_mhz = 250
```

可增加：

```text
projected_dynamic_power_500mhz_mw
```

projection 只能按明确公式生成，并标注：

- 假设每周期活动分布不变；
- 只缩放 dynamic，不缩放 leakage；
- 不包含 500 MHz 额外 glitch、IR drop 和热效应；
- 不能作为 signoff。

不得把 projection 写回 `average_dynamic_power_mw`。

## Step 5.4：对账三个 scope

### 要做什么

对每个窗口报告：

```text
acquisition_energy_nj
compute_energy_nj
end_to_end_energy_nj
```

检查：

```text
end_to_end_energy
```

应与 acquisition + compute + 固定 preamble/result overhead 在合理误差内一致。

误差门槛由 Codex 在第一次正式运行前写入配置，建议不超过 2%。不得看到结果后放宽。

### 阶段 5 交付物

```text
analysis/raw_gate_power_metrics.jsonl
analysis/gate_power_metrics_by_pattern.jsonl
analysis/power_scope_reconciliation.json
```

---

# 阶段 6：建立真实功耗/能量档位

## Step 6.1：选择主分档指标

### 要做什么

主分档必须使用：

```text
compute_energy_nj
```

并额外报告：

```text
end_to_end_energy_nj
average_dynamic_power_mw
acquisition_energy_nj
```

不得以 total toggle 作为功耗分档主指标。RTL activity tier 保留为独立字段。

## Step 6.2：执行确定性三档聚类

### 要做什么

复用阶段 1 的确定性聚类/分段机制，对 31 个非 control 模式按 `compute_energy_nj` 分档。

必须满足：

- 3 档；
- 每档至少 3 条；
- 相邻中心差至少 5%；
- 每条模式 3 次重复 CV <= 0.1%；
- coverage 全部 PASS；
- 功耗字段全部非 null；
- 无 overflow/protocol error；
- 真实 control 不参与聚类。

如果只有两档满足门槛，结果必须为 FAIL 或明确记录为 two-tier evidence；不得强行命名 low/medium/high。

## Step 6.3：比较 RTL activity tier 与 power tier

### 要做什么

输出混淆/对应表：

```text
RTL activity tier
vs
compute energy tier
```

计算至少：

- Spearman rank correlation；
- Pearson correlation，仅作为辅助；
- tier agreement；
- 最大偏离模式；
- 模块 toggle vector 与功耗的关系。

目的不是证明线性，而是识别：

- 哪些模式 RTL 翻转高但功耗不高；
- 哪些模式被 ROM/时钟底噪主导；
- 哪些模式适合作为低、中、高功耗执行候选。

## Step 6.4：筛选 dummy 候选

### 要做什么

每个候选增加：

```text
candidate_status = accepted / rejected / conditional
rejection_reason
```

至少拒绝：

- 功耗覆盖不合格；
- 重复 CV 超限；
- peak-cycle activity 异常；
- end-to-end 能量过高；
- 任何功能错误；
- 只靠 acquisition 差异而 compute 差异不足；
- 与 control 真实窗口无法区分研究用途时需标记 conditional，而非强行接受。

### 阶段 6 交付物

```text
analysis/cnn_gate_power_codebook_v2.jsonl
analysis/power_tiering_summary.json
analysis/activity_power_correlation.json
```

---

# 阶段 7：补齐自动测试和回归

## Step 7.1：增加分析门禁测试

### 要做什么

新增测试至少覆盖：

```text
test_activity_power_config.py
test_activity_tiering.py
test_activity_codebook_validation.py
test_saif_coverage_parser.py
test_gate_power_extraction.py
test_power_scope_reconciliation.py
test_idle_slot_budget.py
```

### 必测失败场景

- coverage 94.9%，失败；
- ROM output 127/128 annotated，失败；
- 出现 PWR-415，失败；
- 出现 PWR-428，失败；
- 功耗字段 null，失败；
- 重复 CV 超限，失败；
- 三档中心差不足，失败；
- 强制等分代码重新出现，静态检查失败；
- end-to-end 能量对账超限，失败；
- gate logit 与 bit-true 不一致，失败；
- pattern 数不为 36，失败。

## Step 7.2：增加静态防跑偏检查

### 要做什么

新增脚本检查：

- 新功耗流程读取 mapped netlist，不读取 RTL 作为 DUT；
- 不使用 vectorless power 作为 codebook 输入；
- 不出现 `power = toggle * constant`；
- 不修改任务一量化配置；
- 不修改 36-window 输入；
- 不引入 PRNG/TRNG；
- 不新增 dummy scheduler RTL；
- 不新增电容控制 RTL。

### 阶段 7 验收

- Python 单元测试全部通过；
- ROM exhaustive test 通过；
- gate functional 36x3 通过；
- gate SDF 36x3 通过；
- coverage 324/324 通过，或等价三 scope 全覆盖通过；
- 功耗码本 validator PASS。

---

# 阶段 8：证明真实推理周期是否允许完整 dummy slot

任务三的功耗码本完成并不自动代表可以调度 dummy inference。

## Step 8.1：冻结真实推理 cadence 输入合同

### 要做什么

新增配置：

```text
config/cnn_real_inference_cadence_v1.json
```

它必须由系统集成需求明确给出：

```text
cnn_clock_period_ns
sensor_sample_period_ns
real_inference_stride_samples
real_request_interval_cycles
real_deadline_cycles
maximum_request_jitter_cycles
```

不得由 Codex自行假设一个较慢 cadence 来制造空闲时间。

如果项目尚未决定 CNN 每多少个采样运行一次，阶段 8 必须输出：

```text
status = BLOCKED_MISSING_REAL_CADENCE_CONTRACT
```

## Step 8.2：计算非抢占 fixed-slot 预算

### 要做什么

当前一条完整 inference 占用：

```text
II = 12893 cycles
```

对真实请求间隔 `R`：

```text
idle_cycles_after_real = max(0, R - II)
max_full_dummy_slots = floor(idle_cycles_after_real / II)
```

由于当前 CNN 不支持安全抢占：

- 少于 12,893 个空闲周期不能启动一个 dummy；
- 不允许启动后被真实请求中断；
- 不允许延迟真实请求；
- 不允许丢弃真实窗口；
- 不允许把零散 idle cycles 累计跨真实 deadline 拼成一个 dummy slot。

## Step 8.3：生成 cadence 表

### 要做什么

输出：

```text
analysis/idle_slot_budget.csv
```

至少包含：

```text
real stride samples
request interval cycles
real utilization
idle cycles
max full dummy slots
deadline margin
status
```

可以输出假设性 sweep 供研究，但只有被配置文件标为 approved 的 cadence 才能授权下一阶段。

## Step 8.4：idle-slot 验收

允许进入下一阶段的最低条件：

```text
approved cadence exists
AND max_full_dummy_slots >= 1
AND real deadline margin >= configured safety margin
AND no request jitter can overlap dummy slot
```

否则结论必须是：

```text
任务三功耗码本完成，但当前架构没有可证明的 dummy 调度空间。
```

此时下一步应优化 CNN latency/II 或降低经过系统论证的真实推理频率，而不是直接实现 scheduler。

---

# 阶段 9：形成最终报告和阶段门决定

## Step 9.1：新增最终报告

### 要做什么

新增：

```text
rtl/cnn_monitor/CNN_ACTIVITY_POWER_CODEBOOK_V2_REPORT.md
```

原 `CNN_ACTIVITY_CODEBOOK_REPORT.md` 保留为历史 RTL activity 报告，不覆盖、不删除。

新报告必须包含：

1. 基线 commit 和所有输入 SHA256；
2. gate-level 仿真环境；
3. ROM public-Q compatibility 方法；
4. exhaustive ROM readback 结果；
5. 功能回归结果；
6. SAIF coverage 数值；
7. PWR warning 审计；
8. compute/acquisition/end-to-end 功耗和能量；
9. 三档聚类门禁；
10. RTL activity 与 gate power 相关性；
11. accepted/rejected dummy 候选；
12. cadence 和 idle-slot 预算；
13. 未解决风险；
14. 是否允许进入 real/dummy scheduler。

## Step 9.2：生成机器可读阶段结论

输出：

```text
analysis/task3_final_gate.json
```

格式至少包括：

```text
baseline_manifest_pass
rom_public_q_pass
gate_functional_pass
gate_sdf_pass
coverage_pass
power_codebook_complete
power_tier_count
repeatability_pass
end_to_end_energy_pass
approved_cadence_present
full_dummy_slot_available
next_stage_authorized
failures
```

`next_stage_authorized` 只能由所有门禁自动计算，不允许在报告中手工修改。

## Step 9.3：最终授权条件

只有以下全部满足时，才可写：

```text
TASK3_COMPLETE
NEXT_STAGE_AUTHORIZED_FOR_FIXED_REAL_DUMMY_SLOT_PROTOTYPE
```

条件：

- baseline manifest PASS；
- ROM public-Q 384/384 PASS；
- 36x3 gate functional PASS；
- 36x3 gate SDF PASS；
- coverage 全部通过；
- 无 PWR-415/PWR-428；
- 31 个候选均有可信 compute/end-to-end energy；
- 三个真实能量档位通过；
- repeat CV 通过；
- 功耗码本 validator PASS；
- approved real cadence 存在；
- 至少有一个完整 dummy slot；
- 真实 deadline 不受影响。

如果功耗码本通过但 idle-slot 不通过，只能写：

```text
TASK3_POWER_CODEBOOK_COMPLETE
NEXT_STAGE_BLOCKED_NO_SAFE_IDLE_SLOT
```

---

## 5. 建议文件变更清单

Codex 开始前应重新检查仓库结构。推荐新增，不强制完全同名：

```text
rtl/cnn_monitor/config/cnn_activity_power_config_v2.json
rtl/cnn_monitor/config/cnn_real_inference_cadence_v1.json
rtl/cnn_monitor/scripts/audit_rom_observability.py
rtl/cnn_monitor/scripts/run_rom_public_q_activity_check.sh
rtl/cnn_monitor/scripts/run_gate_activity_characterization.py
rtl/cnn_monitor/scripts/analyze_activity_codebook_v2.py
rtl/cnn_monitor/scripts/audit_saif_coverage.py
rtl/cnn_monitor/scripts/extract_gate_power_metrics.py
rtl/cnn_monitor/scripts/validate_activity_codebook.py
rtl/cnn_monitor/synthesis/dc_gate_activity_power_v2.tcl
rtl/cnn_monitor/tb/cnn_rom_activity_compat.sv
rtl/cnn_monitor/tests/test_activity_power_config.py
rtl/cnn_monitor/tests/test_activity_tiering.py
rtl/cnn_monitor/tests/test_activity_codebook_validation.py
rtl/cnn_monitor/tests/test_saif_coverage_parser.py
rtl/cnn_monitor/tests/test_gate_power_extraction.py
rtl/cnn_monitor/tests/test_power_scope_reconciliation.py
rtl/cnn_monitor/tests/test_idle_slot_budget.py
rtl/cnn_monitor/CNN_ACTIVITY_POWER_CODEBOOK_V2_REPORT.md
```

不得删除：

```text
scripts/analyze_activity_vcd.py
CNN_ACTIVITY_CODEBOOK_REPORT.md
runs/activity_codebook_20260802_r1/
```

它们是任务三第一次实施的历史证据。

---

## 6. 建议提交顺序

每个提交必须独立可审查：

```text
commit 1:
Add task-three v2 configuration and acceptance-gate tests

commit 2:
Add deterministic activity tiering and codebook validator

commit 3:
Add ROM public-Q observability audit and compatibility regression

commit 4:
Add gate-level functional and SDF activity flow

commit 5:
Add SAIF coverage audit and control-pattern power preflight

commit 6:
Add full 36-pattern gate power characterization

commit 7:
Add acquisition/compute/end-to-end energy reconciliation

commit 8:
Add power tiering, activity-power correlation, and candidate screening

commit 9:
Add real-cadence idle-slot budget and final task-three gate report
```

禁止把所有内容压成一个无法审查的大提交。

---

## 7. 每个阶段的汇报格式

Codex 每完成一个阶段，应更新 run 内：

```text
evidence/progress.md
```

固定格式：

```text
阶段：
状态：PASS / FAIL / BLOCKED
完成的文件：
执行的命令：
输入 SHA256：
输出 SHA256：
关键指标：
失败日志：
是否允许进入下一阶段：yes/no
```

不得只写“测试通过”。必须给出测试数量、仿真数量、coverage 数值和失败门禁。

---

## 8. 允许 Codex 自主决定的细节

Codex 可以自主决定：

- Python 类和函数的拆分；
- gate-level driver 使用 Python 还是 shell；
- VCD 转 SAIF 的具体工具；
- 确定性 1D 聚类的具体算法；
- report parser 的实现；
- run tag 的小版本号；
- 单元测试 fixture 的组织；
- compatibility 使用 wrapper、bind 或受控 force。

但不得改变：

- 阶段顺序；
- 功耗与 activity 的概念边界；
- coverage 门槛；
- 三档最小分离门槛；
- 3 次重复；
- 36 个冻结窗口；
- 任务一权重和定点合同；
- 12,892/12,893 固定 schedule；
- 必须测 acquisition、compute 和 end-to-end 三个 scope；
- 必须先 control preflight 再全量运行；
- 无完整 idle slot 不得实现 scheduler；
- 本计划完成前不得进入随机扰动或电荷整形。

---

## 9. 最终期望结论

本计划不是为了强行得到“任务三通过”，而是为了得到可审计的二选一结论。

### 结论 A：任务三完整通过

```text
门级活动覆盖可信
ROM public Q 可审计
36 模式具有可信功耗/能量
存在三个可重复能量档位
完整窗口写入和计算能量已测
approved cadence 可容纳至少一个完整 dummy slot
```

随后才能规划：

```text
固定 real/dummy slot 原型
真实请求最高优先级
不抢占的 dummy inference
快速硬保护
```

### 结论 B：任务三仍阻塞

任何以下情况均应阻塞：

- ROM public Q 无法形成可信活动；
- SAIF coverage 不达标；
- PWR-415/PWR-428 未消除；
- 功耗档位不满足 5% 分离；
- 重复性超限；
- end-to-end 能量不可对账；
- 无 approved cadence；
- 无完整 dummy slot。

阻塞时必须保留失败证据，并回到对应阶段修复，不得跨步实现 PRNG、dummy scheduler 或电荷整形。
