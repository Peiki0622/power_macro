# CNN 活动码本任务 3 执行复盘

## 1. 结论与范围

本报告复盘 `power_macro/plans/cnn_compute_reuse_phase1_plan.md` 的任务三。
任务三要验证的是：在**不加入随机调度、电荷整形或任何综合 RTL 改动**的情况下，输入不同但数值合法的 L32 窗口，现有 16-lane W8/A8 CNN 是否产生稳定且可调的内部开关活动。它不是侧信道防护实现，也不是物理签核功耗报告。

本次结论分成两个不能混淆的层次：

1. **RTL 开关活动结论成立。** 31 个合成 dummy 窗口形成了 low、medium、high 三档；每个窗口重复三次的总翻转计数完全相同，所有 36 个窗口都按固定 12,892-cycle 完整 CNN 路径结束，且无数值溢出或协议错误。
2. **逐窗口物理功耗结论不成立。** VCD 转 SAIF 后的 DC 预检报告 `PWR-415` 和 `PWR-428`。当前流程没有可量化、可证明达到门槛的活动注释覆盖率，因此 DC 输出的毫瓦数字不能作为平均动态功耗、峰值功耗或窗口能量写入码本。相应字段明确为 `null`，而非以 RTL 翻转量代替功耗。

因此，本任务只完成“CNN 可作为可控 **RTL 开关活动** 执行器”的证据收集；它不足以授权进入 real/dummy 时隙调度、PRNG、PDN/电荷整形或侧信道效果宣称。当前监测器在饱和真实请求率下也没有已证明的安全空闲 slot。

## 2. 冻结对象与不变量

测量对象是既有 `cnn_monitor #(.MAC_LANES(16))`。此次没有修改以下综合 RTL：

| 文件 | SHA256 |
| --- | --- |
| `rtl/cnn_convolution_engine.sv` | `3d9f4c786aa5d7fa4eb2ce2406b00778868c646e7fc60f94955d3647cb89b5eb` |
| `rtl/cnn_monitor.sv` | `b04ca0c4b837d7d1209b92dbe242e62ac9161c7ba5371fb0977d6d0aa7920f7f` |
| `rtl/cnn_pool_classifier.sv` | `a6aa545b5d653fe4f5c5e5d4a99485bf25dd0eafdfef79e9edcbfbcfd109b6d9` |

这些摘要与活动测量前记录的基线相同。测量固定使用同一套已认证权重、16 MAC lane、同一 ROM compiler model、4 ns 仿真时钟、相同 reset/preamble/postamble，且每次 inference 均为 12,892 个周期。已有全 RTL 基线回归也保留在 `runs/activity_codebook_20260802_r1/baseline_vcs/`，其中 `simulation.log` 给出 `CNN_MONITOR_REGRESSION_PASS vectors=15 trace_cycles=12892`。

## 3. 任务书到实施的逐项映射

### 3.1 Step 3.1：活动测量接口

新增的测量基础设施均在综合设计之外：

- `tb/cnn_activity_tb.sv` 是仿真专用 testbench。它仅实例化未修改的 DUT；没有向 DUT 添加 counter、debug port 或条件逻辑。
- `scripts/run_activity_characterization.py` 在一个任务专属目录中编译一次 VCS，再独立运行每个 pattern/repeat，产出 `vcd/`、`results/` 与 `logs/`。
- `scripts/analyze_activity_vcd.py` 只统计已知 `0 <-> 1` bit transition，按 VCD identifier 去重，避免同一个信号因层次 alias 被重复计数；X/Z 不被伪装成翻转。

解析器把可见信号划入互不重叠的组：`convolution_mac`、`weight_intermediate_storage`、`average_accumulator`、`maximum_tracker`、`endpoint_registers`、`classifier`、`control_address`。这满足任务书要求的模块归因，但它是 RTL 信号层的归因，**不是**标准单元或晶体管功耗分解。

### 3.2 Step 3.2：固定测量协议

testbench 的执行协议如下，所有 108 次运行相同：

1. reset 保持两个上升沿，释放后固定空闲四个上升沿；该阶段关闭 VCD。
2. 连续 32 个周期加载一个 L32 窗口，并在每个样本处检查 `sample_ready`；加载结束时检查 `inference_ready`。该阶段同样关闭 VCD，避免 acquisition 接口翻转混入计算活动。
3. 固定四周期 preamble 后，在下降沿打开 VCD 并拉高一次 `inference_request`。下一上升沿接收请求并进入 CNN 固定 schedule。
4. `busy` 期间强制 `sample_valid=0`、`inference_request=0`；VCD 从请求接受覆盖到 result 提交，测量对象仅是该次 CNN 计算。
5. result 后关闭 VCD；额外固定四周期 postamble 用于确认 `result_valid` 只有一个周期，但 postamble 自身不进入活动窗口。

这一边界很重要：不同 dummy 的输入加载开关没有被计入总翻转，避免把接口写入差异误判为 CNN 内部计算差异；同时没有跳过任何卷积、Average、Max、Endpoint 或分类路径。

### 3.3 Step 3.3：窗口库和真值来源

配置 `config/cnn_activity_config_v1.json` 冻结以下参数：L32、sensor code `[0,32]`、16 lanes、三次重复、12,892-cycle latency、两条真实对照，以及 5% 预期档位分离/0.1% CV 的判据。

`scripts/generate_activity_windows.py` 没有 PRNG。它产生 36 条固定记录，并对每条记录计算 SHA256 和 task-one bit-true cycle model 的期望 logits/decision：

| 家族 | 数量 | 构造意图 |
| --- | ---: | --- |
| `mean_dominant` | 7 | 常数 low/mid/high、上下 ramp、宽 plateau，覆盖整体水平和平均路径 |
| `peak_dominant` | 10 | 单峰、双峰、短 burst、峰位置扫描，覆盖最大值路径和转移位置 |
| `endpoint_dominant` | 6 | 最后一点升/降、末四点 ramp、相同前缀不同 endpoint |
| `mixed_statistic` | 8 | 固定步长 walk、ramp+peak+recovery、双平台、窄/宽交替 |
| `control` | 5 | 全 0、全 15、全 32，以及任务一 golden 的真实 Safe/real Critical |

最终 manifest 位于 `runs/activity_codebook_20260802_r1/rtl_characterization/inputs/windows/manifest.json`：共 36 条记录，窗口 JSONL SHA256 为 `41cc0eafbfa6d815f3d4fc4f10f339c82a72c339534b21434fa5896d17a85b24`，绑定的 task-one manifest SHA256 为 `cae8e6fc012603c65c0be6a7b627c49632e6e45a8b41917e193b5902c57f5c72`。

### 3.4 Step 3.4：功能自检与重复测量

每次仿真不是 smoke：`cnn_activity_tb.sv` 在 result 周期检查以下合同，任一不符即 `$fatal`：

- 固定 latency 恰为 12,892；
- `numeric_overflow==0` 且 `protocol_error==0`；
- safe logit、critical logit、decision 与该窗口的 cycle-model 期望值逐值相等；
- postamble 后 `result_valid` 恰为单周期脉冲。

执行集为 `36 patterns x 3 repeats = 108` 次完整仿真。run 目录下实际有 108 个 VCD、108 个 result 文件和 108 条带 `CNN_ACTIVITY_PASS ... cycles=12892` 的日志；未发现 `ACTIVITY_TB_ERROR`、`Fatal` 或 `Error-`。原始逐重复数据有 108 行，最终码本有 36 行。

额外的 Python contract test `tests/test_activity_windows.py` 验证两次独立生成的 `windows.jsonl` 字节完全一致、36 条 pattern id 无重复、每条长度均为 32、码值都在 `[0,32]`、cycle model latency 固定且无溢出。整个任务一至任务三相关单元测试累计 37 项通过；这与 108 次 RTL 仿真是互补验证，而非替代关系。

### 3.5 Step 3.5：指标、分档和原始数据

最终机器可读码本为 `runs/activity_codebook_20260802_r1/rtl_characterization/analysis/cnn_activity_codebook_v1.jsonl`，每行保存 pattern/family/parameters/input SHA256、总翻转、各模块向量、峰值 cycle/activity、前 32 个非 DC bin 的频谱摘要、latency、logits、decision、重复值/CV 和 validity。

逐 repeat 的完整 cycle waveform 未塞入最终码本以避免重复膨胀，而保留在 `raw_activity_metrics.jsonl`（108 行，约 6.26 MB）。VCD 原文件也保留在同一 task-scoped run 的 `vcd/` 目录。所有中间产物集中在 `runs/activity_codebook_20260802_r1/`，没有向 RTL 源目录或工作区根目录散落。

对 31 条非 control、有效模式，按**测得的总翻转计数升序**等分为三档，而不是根据输入外观预先贴标签：

| 指标 | 结果 |
| --- | --- |
| low / medium / high | 11 / 10 / 10 条 |
| 全 36 条的总翻转范围 | 1,528,082 至 2,073,437 bit transitions |
| 任一模式三次 repeat CV | 0.0 |
| 有效记录 | 36/36 |
| overflow / protocol error | 0/108 / 0/108 |

例如 `mean_constant_high` 为 1,529,205 次，`mean_constant_low` 为 1,928,560 次；差异主要体现在 `convolution_mac`，而 `weight_intermediate_storage` 在这两个例子中均为 850,931。这说明输入数据相关翻转在 MAC 数据通路中可见，而固定权重/存储访问形成了显著的共同底噪。它不表示任何一个 family 必然只激活某一统计分支，也不意味着总翻转与物理功耗线性对应。

## 4. 功耗预检：做了什么、为什么拒绝其数值

为避免把 VCD 计数包装成工艺功耗，实施了一个最小 DC preflight：`synthesis/dc_activity_power.tcl` 读取冻结的 16-lane DDC、TT standard-cell library 与 ROM `.db`，设置 4 ns 时钟，并以

```tcl
read_saif -input <saif> -instance_name cnn_activity_tb/dut -auto_map_names -verbose
```

导入 `control_all_15_r0` 的 SAIF，再运行 `report_power -hierarchy`。选择 4 ns 是为了与已认证 ROM compiler model 的功能仿真周期一致；这不是把该次 VCD 冒充成 500 MHz 实测。

结果保留在 `analysis_attempt1_x_observation/control_all_15_r0_power.rpt`。DC 确实产生过 `20.510 mW` 的 total 行，但该行**被拒绝**，不进入任何结果字段，理由不是数字“看起来不合理”，而是报告开头明确给出：

1. `PWR-415: Design has unannotated sequential cell outputs`。RTL VCD 的层次和信号名无法完整对应综合优化后的触发器输出；一部分活动只能由 DC 的低努力零延迟传播推导，而不是来自实测 SAIF。
2. `PWR-428: Design has unannotated black box outputs`。ROM 是 hard macro，macro 输出没有完整、可信的 SAIF 注释。
3. ROM 模型有已知的仿真/物理引脚可见性不一致：`rtl/cnn_weight_rom.sv` 在 `CNN_ROM_COMPILER_MODEL` 条件下读取 compiler model 内部同步 `Q_`，因为 VCS 下 public `Q` (`macro_q`) 为 X；综合时则连接物理 macro 的 public `Q`。功能回归因此成立，但该 VCD 的可观察功能路径与 DDC/Liberty 的物理 macro 输出不是一一对应。
4. 当前脚本没有生成 per-object 或 per-class（primary input、sequential output、macro output）的数值 annotation coverage 报告。因此不能诚实地声称“已测得覆盖率低于 90%”；准确说法是：有 PWR-415/PWR-428，且尚不能证明达到可信功耗所需的覆盖门，故拒绝使用该数值。

由此，`average_dynamic_power_mw`、`energy_window_nj`、`peak_power_proxy_mw` 全部保持 `null`。`peak_cycle_activity` 只是每周期 RTL bit transition 的峰，不是峰值毫瓦，也不能据其判定供电安全、电迁移、IR drop 或热风险。

## 5. 任务三七项验收复盘

| 任务书问题 | 证据与回答 | 状态 |
| --- | --- | --- |
| 至少三个可重复活动/能量档位？ | RTL 活动有三档（11/10/10），三次 repeat CV=0；物理能量档位没有可信证据。 | 活动通过；能量未通过 |
| 不同窗口族主要激活哪些模块？ | 每条记录有 module toggle vector；示例和整体数据表明卷积 MAC 随输入变化显著，存储访问有固定基线。 | 通过，限 RTL 层 |
| 峰值活动是否集中在固定周期？ | 每条记录保存 `peak_cycle`/waveform，峰周期可审计；尚未把它们归纳为统一固定物理峰。 | 数据已交付，物理结论未作 |
| 哪些窗口有不安全峰/过高能量？ | 无可信 mW/nJ 和无 PDN/热模型，不能判定。 | 不可判定，不伪造结论 |
| 哪些窗口可作后续 dummy 候选？ | 三档中的有效合成模式是研究候选；control 不作 dummy 候选。具体投放仍依赖 slot/物理功耗证据。 | 条件成立 |
| 真实与 dummy 是否走同一完整路径？ | 同一 DUT、权重、16 lanes、请求协议和 12,892-cycle self-check；五个 control 同样执行。 | 通过 |
| 是否足以支持后续时隙复用研究？ | 支持后续“受控计算活动”的研究，不支持实施调度或防护效果宣称。 | 仅研究前置通过 |

任务书的建议继续条件要求“至少三档、每档多个输入、重复方差远小于档间差异、无溢出、不改变真实窗口结果”。前五项在 RTL 活动层已满足：每档至少 10 条、CV=0、最大最小差为 545,355 transitions（约为低端值的 35.7%）、108 次无错误且真实 control 完整自检。缺口是**没有可信物理功耗/能量注释**，以及**没有安全 idle slot 的系统级证明**；这两个缺口使后续调度保持禁止状态。

## 6. 已知限制与下一阶段的最小前置条件

本次没有做、也不应由任务三擅自做：dummy scheduler、PRNG/TRNG、额外综合计数器、权重重训/重量化、PDN/IR-drop、侧信道攻击/防护评估，或基于不完整 DC 注释的峰值安全宣称。

若后续目标是让物理功耗字段达到可用门槛，最小的下一步不是扩大码本，而是单独建立可审计的 gate-level 活动流程：

1. 从该 DDC 对应的 mapped netlist 运行门级仿真，或提供正式 RTL-to-gate 名称映射，消除 `PWR-415` 的主要来源。
2. 在不改变 PDK、ROM 地址/时序合同和综合网表的前提下，使仿真可观测的 ROM 输出与物理 public `Q` 路径可审计地一致，处理 `Q_`/`Q` 差异和 `PWR-428`。
3. 输出明确的 annotation coverage 统计及门禁；仅在 coverage 达标后，才对全 36 条模式批量生成平均功耗、能量和峰值功耗。

在这些前置条件完成前，码本应被使用为“RTL activity codebook”，不得称为“silicon power codebook”。

## 7. 可复查产物

所有任务三运行产物都在 `rtl/cnn_monitor/runs/activity_codebook_20260802_r1/`：

- `rtl_characterization/inputs/windows/`：固定窗口、manifest、task-one 绑定摘要；
- `rtl_characterization/logs/`、`results/`、`vcd/`：108 次仿真的直接证据；
- `rtl_characterization/analysis/`：最终 raw metrics、码本、summary；
- `rtl_characterization/analysis_attempt1_x_observation/`：SAIF、DC preflight report 和第一次 X 观测结果；
- `rtl_characterization/analysis_attempt2_unknown_audit/`：unknown-state 审计后的历史解析结果；
- `baseline_vcs/`：任务三前的完整 RTL 基线回归证据。

历史分析目录被保留用于审计，不作为最终码本数据源。最终结果只以 `rtl_characterization/analysis/` 为准。
