# TCN 数据集与电压跌落检测实施计划

## 1. 目标与边界

本计划用于指导 Codex 在现有差分 Vernier 电压传感器基础上，构建可复现的 TCN 数据集、训练流程和检测评估流程。

本阶段的大方向是：

```text
人工直接驱动 chiplet-A 本地 VDD_A/VSS_A
        -> 标准单元 SPICE Vernier 传感器
        -> 真实 DFF 码元时间序列
        -> 严格分组的数据集
        -> 1D-TCN 风险检测
        -> Safe / Warning / Critical 输出
```

本阶段明确不做：

- 不把共享 PDN/RO-bank 联合仿真作为数据集生成的前置条件；
- 不把攻击源识别作为 TCN 任务；
- 不使用理想电压值作为 TCN 在线输入；
- 不使用 `sensor_code` 阈值直接生成监督标签；
- 不允许同一基础波形的变体跨训练/验证/测试集合；
- 不允许把同一条轨迹切出的窗口随机分散到不同数据划分；
- 不直接从一条 500 点轨迹大量滑窗后宣称得到独立样本。

共享 PDN 平台继续承担“跨芯粒攻击确实能造成 chiplet-A 压降和时序违例”的证明作用；本计划中的直接 VDD_A 平台承担“快速、可控、可重复地生成检测数据”的作用。

---

## 2. 文献方法中需要吸收的关键原则

本计划参考 Talukdar 等 2025 年电压跌落异常检测方法，但不照搬其卷积自编码器。

需要吸收的原则：

1. 电压跌落是时间序列问题，不能只用单点阈值；
2. 每条完整轨迹应包含连续采样点；
3. 滑动窗口应保持时间顺序；
4. 正常工作负载要区分 busy、bursty，并覆盖 mixed 场景；
5. 测试中的异常事件应随机出现在轨迹中，而不是固定位置；
6. 异常持续比例不能只固定为 25%，还应测试低占空比；
7. 需要连续多个异常窗口确认，以降低误报，但确认窗口会增加检测延迟；
8. 需要测试未见过的异常波形，类似文献中对非 RO 功耗攻击的泛化测试；
9. 低严重度压降会使正常与异常分布尾部重叠，必须单独建立困难测试集；
10. 评价不能只看 Accuracy，还要看误报、漏检、事件检测率和提前量。

本项目在此基础上的改进：

- 使用真实标准单元 Vernier 传感器码元，而不是理想电压值；
- 使用因果 1D-TCN，而不是卷积自编码器；
- 输出 Safe / Warning / Critical 风险等级；
- 标签依据未来时序风险，而不是“当前是否异常”；
- 使用严格的 `base_waveform_id` 分组防止数据泄漏；
- 增加 IID、OOD、低严重度、未见背景、低异常占空比等独立测试集合；
- 评价从“窗口分类”扩展到“事件提前检测”。

---

## 3. 现有硬件与仿真基线

复用 `delay_chain/phase2_vernier` 已完成结构：

```text
M_STAGES = 32
reference dummy load count = 1
CAL_SEL = 2
sense launch offset = 20 ps
nominal baseline code = 15
sample period = 4 ns
sample count per trace = 500
trace duration = 2 us
VDD_REF = 1.1 V
```

传感器输出至少包括：

```text
raw_code
corrected_code
sensor_code
bubble_count
code_valid
sample_done
```

新数据生成器应复用：

- 现有 HSPICE 路径；
- SMIC40LL CDL 模型；
- Vernier 网表生成器；
- DFF 测量与解码逻辑；
- 现有 CSV/JSON/manifest 输出风格；
- 现有 run-directory 不覆盖规则。

---

## 4. 检测任务定义

TCN 的在线输入只来自传感器可获得的数字信号。

TCN 任务：

```text
过去 L 个采样点
        -> 预测未来 H 个采样点内的风险状态
```

默认：

```text
L = 16 samples = 64 ns history
H = 8 samples  = 32 ns prediction horizon
```

输出类别：

```text
0 = Safe
1 = Warning
2 = Critical
```

输入特征初版：

```text
x0[k] = (sensor_code[k] - baseline_code) / (M - baseline_code)
x1[k] = (sensor_code[k] - sensor_code[k-1]) / M
x2[k] = 1 if sensor_code[k] == M else 0
x3[k] = bubble_count[k] / M
x4[k] = code_valid[k]
```

约束：

- `measured_vdd_a_v` 只用于标签和分析，不作为 TCN 输入；
- `configured_droop_mv` 只用于数据追踪，不作为 TCN 输入；
- `waveform_family` 不作为 TCN 输入；
- 每条轨迹应保存自己的 `baseline_code`；
- 不允许对每条完整轨迹单独做均值方差归一化；
- 所有统计归一化参数必须只由训练集计算。

---

## 5. 数据组织的四层 ID

所有数据必须显式记录：

```text
waveform_family_id
base_waveform_id
trace_id
window_id
```

定义：

- `waveform_family_id`：波形族，例如 trapezoid、triangle、exponential；
- `base_waveform_id`：不含随机背景噪声变体的基础事件参数组合；
- `trace_id`：某个基础波形在特定背景、随机种子、事件位置下的一次完整 HSPICE 轨迹；
- `window_id`：从完整轨迹中切出的一个因果窗口。

强制规则：

> 同一个 `base_waveform_id` 的所有变体必须进入同一个数据划分。

例如同一基础压降的不同：

- 起始时间；
- 背景噪声种子；
- 小幅参考电压扰动；
- 恢复尾部细节；

不能跨 train/validation/test。

---

## 6. 正常背景域设计

直接驱动 VDD_A 时，不能让正常轨迹始终保持平直电压。需要人工构造功能负载背景。

### 6.1 Busy 背景

特点：

- 连续存在中小幅波动；
- 相邻采样高度相关；
- 几乎没有长空闲段。

建议参数范围：

```text
amplitude = 0.5 to 5 mV
correlation duration = 8 to 40 ns
slow baseline drift = optional
```

波形组成：

- 小三角波；
- 小梯形波；
- 低通随机噪声；
- 短时负载突发；
- 多个微小事件叠加。

### 6.2 Bursty 背景

特点：

```text
idle segment -> active segment -> idle segment -> active segment
```

参数：

```text
burst_factor beta = 0.25, 0.5, 0.75
idle fluctuation = 0.2 to 1.5 mV
active fluctuation = 1 to 8 mV
active duration = 16 to 160 ns
```

### 6.3 Mixed 背景

- 将 busy 和 bursty 片段随机交错；
- 用于训练统一模型；
- 也用于测试跨工作模式泛化。

### 6.4 功耗随机化背景

用于模拟 CPA 防御 macro 的安全扰动：

```text
amplitude = 2 to 12 mV
irregular pulse clusters
random interval
non-periodic slope changes
must remain timing-safe
```

这些样本必须标为 Safe，是降低误报的关键困难负样本。

---

## 7. 压降事件域设计

每个事件由以下参数描述：

```text
amplitude_mv
fall_time_ns
hold_time_ns
recovery_time_ns
ringing_factor
secondary_drop
```

训练中出现的波形族：

1. trapezoid：线性下降、平台、线性恢复；
2. triangle：下降后立即恢复；
3. exponential：指数下降与指数恢复；
4. staircase：多级阶梯下降；
5. double_event：两个相邻压降事件；
6. plateau_with_jitter：平台叠加小扰动。

仅用于 OOD 测试的波形族：

1. RLC ringing；
2. glitch pulse cluster；
3. partial recovery then second collapse；
4. asymmetric double peak；
5. random-walk then sudden collapse。

每个事件至少扫描：

```text
amplitude: 4 to 80 mV
fall time: 4 to 100 ns
hold time: 0 to 300 ns
recovery time: 4 to 200 ns
```

参数采样应覆盖：

- 安全小扰动；
- Warning 区；
- 最后通过点附近；
- 首次违例点附近；
- 明显 Critical 区；
- 传感器饱和区。

---

## 8. 困难配对样本

必须专门生成 `hard_pair_id`，用于证明 TCN 利用历史趋势而不是简单阈值。

典型配对：

### 8.1 相同当前码元，不同未来趋势

```text
recovering: 15,17,19,20,18,16,15
worsening:  15,17,19,20,23,27,32
```

### 8.2 相同最低电压，不同下降速度

- 一条快速下降后恢复；
- 一条缓慢持续下降。

### 8.3 相同幅度，不同持续时间

- 短脉冲不造成故障；
- 长平台进入危险区。

### 8.4 相同当前斜率，不同未来结果

- 一个提前恢复；
- 一个继续恶化。

### 8.5 相同饱和码，不同持续风险

- 码元短时饱和后恢复；
- 码元持续饱和并进入 Critical。

测试报告中必须单独输出 hard-pair 准确率和事件检测率。

---

## 9. 标签生成

## 9.1 Slack 映射

优先建立：

```text
VDD_A -> worst_slack
```

映射表。

来源：已有 timing-droop 结果；边界附近不足时，补充有限数量电压点的时序分析。

建议边界附近至少包含：

```text
1.070, 1.065, 1.060, 1.055, 1.052,
1.050, 1.0475, 1.045, 1.040 V
```

插值要求：

- 保持单调；
- 不在已有数据范围外静默外推；
- 超出范围时明确标记；
- 保存映射版本和来源文件 SHA。

## 9.2 未来风险标签

对采样点 `k`：

```text
future_min_slack[k] = min(slack[k : k+H])
```

默认 `H=8`。

分类：

```text
Critical: future_min_slack <= 0
Warning:  0 < future_min_slack <= S_warn
Safe:     future_min_slack > S_warn
```

验证集扫描：

```text
S_warn = 5 ps, 10 ps, 20 ps
```

## 9.3 标签滞回

防止边界附近反复跳变。

扫描：

```text
K_recover = 2, 3, 4 samples
S_recover = 10, 15, 20 ps
```

状态恢复要求连续满足条件，不能单点恢复。

禁止：

```text
sensor_code >= threshold -> label
```

传感器码只能作为输入，不能作为标签真值。

---

## 10. 轨迹长度、事件位置与占空比

默认每条轨迹：

```text
sample_count = 500
sample_period = 4 ns
trace duration = 2 us
```

每条轨迹中的：

- 事件数量；
- 事件起始时间；
- 事件间隔；
- 持续时间；
- 波形参数；

都应由随机种子决定。

不要固定事件总在 200/600/1000/1400 ns 出现。

异常占空比应覆盖：

```text
1%, 5%, 10%, 25%
```

训练集可以以 10% 和 25% 为主；测试集必须包含 1% 和 5%。

---

## 11. 数据划分

推荐先构建 Pilot 数据集，再扩展正式数据集。

### 11.1 Pilot：96 条完整轨迹

训练集 48：

- 16 条纯正常背景；
- 32 条含压降事件；
- 只使用已知波形族。

验证集 16：

- 6 条正常；
- 10 条压降；
- 波形族与训练相同；
- 使用不同 `base_waveform_id` 和随机种子。

IID 测试集 16：

- 参数分布与训练相同；
- 完全不参与超参数调整。

OOD 测试集 16：

- 未见波形；
- 未见背景；
- 低严重度；
- 复合事件。

### 11.2 正式数据集

Pilot 通过后扩展到：

```text
192 to 240 independent traces
```

增加独立基础波形数量，而不是只增加同一轨迹的滑窗数量。

### 11.3 强制分组划分

使用 `GroupShuffleSplit` 或等效自定义方法，分组键：

```text
base_waveform_id
```

生成：

```text
splits/split_v1.json
```

并验证：

```text
intersection(train_base_ids, val_base_ids) == empty
intersection(train_base_ids, test_base_ids) == empty
intersection(val_base_ids, test_base_ids) == empty
```

---

## 12. 窗口化策略

默认：

```text
window length L = 16
```

消融：

```text
L = 8, 16, 32
```

训练阶段：

```text
stride = 2 preferred
```

或保持 stride=1，但必须进行事件均衡采样。

验证和测试：

```text
stride = 1
keep chronological order
```

训练 batch 的建议类别比例：

```text
Safe     40%
Warning  35%
Critical 25%
```

但测试集必须保持原始类别和事件占比，不得人为均衡。

每条轨迹对训练窗口数设置上限，防止一条长事件轨迹主导训练。

---

## 13. 模型与基线

必须实现以下四类方法：

1. 单点/短历史阈值基线；
2. 文献式卷积自编码器基线；
3. 普通 1D-CNN 分类器；
4. 提出的因果 1D-TCN。

### 13.1 TCN 初始结构

```text
input channels = 5
residual blocks = 2 or 3
kernel size = 3
dilations = [1, 2, 4]
hidden channels = 8 or 16
causal padding only
output classes = 3
```

训练：

- 使用 class-weighted cross entropy 或 focal loss；
- 不使用未来采样；
- 保存最佳 validation macro-F1 模型；
- 固定随机种子；
- 保存 config、git SHA、dataset manifest SHA。

### 13.2 连续窗口确认

参考文献的连续历史判决思想，但不能直接固定为 9 个窗口。

验证集扫描：

```text
K_confirm = 1, 3, 5, 9
```

报警规则：

```text
连续 K_confirm 个窗口预测 Warning/Critical 后触发
```

选择原则：

- 在满足正提前量的前提下；
- 选择误报率最低的 K；
- 必须计入确认造成的额外延迟。

---

## 14. 评价指标

### 14.1 窗口级

- macro-F1；
- per-class precision/recall/F1；
- Warning recall；
- Critical recall；
- PR-AUC；
- confusion matrix。

### 14.2 事件级

- event detection rate；
- critical event miss rate；
- false alarms per trace；
- false alarms per microsecond；
- attack/event start to alarm delay；
- alarm to first violation lead time；
- recovery persistence；
- hard-pair accuracy。

### 14.3 分布级

分别报告：

- IID；
- OOD waveform；
- low severity；
- unseen background；
- low event duty cycle；
- busy/bursty/mixed。

不能只报告整体 Accuracy。

---

## 15. 推荐目录结构

新增：

```text
tcn_detection/
├── README.md
├── config/
│   ├── dataset_v1.json
│   ├── label_v1.json
│   ├── model_tcn_v1.json
│   └── baselines.json
├── waveform/
│   ├── generate_background.py
│   ├── generate_event.py
│   ├── generate_hard_pairs.py
│   └── waveform_schema.py
├── spice/
│   ├── generate_dataset_deck.py
│   ├── run_dataset_trace.py
│   └── parse_sensor_trace.py
├── labels/
│   ├── build_slack_map.py
│   ├── assign_future_risk.py
│   └── apply_hysteresis.py
├── dataset/
│   ├── build_manifest.py
│   ├── split_groups.py
│   ├── build_windows.py
│   └── validate_dataset.py
├── models/
│   ├── threshold_baseline.py
│   ├── conv_autoencoder.py
│   ├── cnn1d.py
│   ├── tcn1d.py
│   └── causal_blocks.py
├── train/
│   ├── train_classifier.py
│   ├── train_autoencoder.py
│   └── sweep_confirm_windows.py
├── evaluate/
│   ├── evaluate_windows.py
│   ├── evaluate_events.py
│   ├── evaluate_ood.py
│   └── compare_models.py
├── tests/
└── runs/
```

数据文件建议：

```text
tcn_detection/data/
├── traces/
├── metadata/
├── splits/
├── windows/
└── reports/
```

大型 HSPICE 原始文件不提交 Git；保留 compact CSV、JSON、Markdown 和精选图。

---

## 16. Codex 逐步骤执行计划

## Step 0：复用传感器前端

1. 读取 `delay_chain/phase2_vernier/phase2_config.json`；
2. 复用 M=32/dummy=1/CAL_SEL=2/20 ps 配置；
3. 复用现有 direct-rail timeline 网表与真实 DFF 解码逻辑；
4. 不修改已完成的 Phase 2 结果；
5. 新建 `tcn_detection/`。

验收：

- 原有 Phase 1/2 测试仍通过；
- 新代码不复制硬编码的模型路径。

## Step 1：定义数据 schema 和配置

创建：

```text
config/dataset_v1.json
config/label_v1.json
waveform/waveform_schema.py
```

明确：

- trace schema；
- waveform family；
- ID 规则；
- seed 规则；
- event duty cycle；
- background mode；
- split group key。

验收：

- JSON schema 可验证；
- 同一 seed 可复现完全相同的波形参数。

## Step 2：实现正常背景生成器

实现 busy、bursty、mixed、randomizer-like 四类背景。

输出每条轨迹的基础 PWL 节点和 metadata。

验收：

- 无事件背景不跨入 Critical 电压区；
- 不同 seed 产生不同波形；
- 波形连续、时间严格递增。

## Step 3：实现压降事件生成器

实现训练波形族与 OOD 波形族。

生成：

```text
base_waveform_id
event_id
waveform_family_id
all event parameters
```

验收：

- 参数落在配置范围；
- 事件位置不固定；
- 占空比满足配置；
- 可生成恢复和恶化配对轨迹。

## Step 4：实现 hard-pair 生成器

为每组困难配对生成统一 `hard_pair_id`。

验收：

- 当前传感器码预计重叠；
- 未来风险不同；
- 配对成员强制进入同一测试集合。

## Step 5：生成 HSPICE 数据集轨迹

把背景与事件叠加成直接 `VDD_A` PWL，保持 `VDD_REF` 和 Vernier 电路配置不变。

每次 HSPICE run 生成一条完整轨迹。

输出：

```text
trace CSV
trace metadata JSON
manifest JSON
completion.rpt
```

验收：

- 500 个真实 DFF capture；
- 轨迹无缺失采样；
- code_valid 状态完整保留；
- 不用显示用随机抖动修改电气 CSV。

## Step 6：建立 VDD-to-slack 映射

读取已有 timing-droop 数据，构建单调映射。

不足时只补充必要边界电压点。

输出：

```text
labels/slack_map_v1.csv
labels/slack_map_v1.md
```

验收：

- 来源可追踪；
- 不静默外推；
- 最后通过点和首次违例点与现有结果一致。

## Step 7：生成未来风险标签

对每个采样计算：

```text
mapped_slack
future_min_slack
time_to_violation
raw_label
hysteresis_label
```

验收：

- 标签不读取 sensor_code；
- Critical 与 slack<=0 一致；
- 轨迹末尾不足 H 点的样本显式标记，不伪造未来数据。

## Step 8：严格分组划分

按 `base_waveform_id` 生成 train/validation/IID/OOD splits。

输出：

```text
splits/split_v1.json
reports/split_audit.md
```

验收：

- 各划分 base IDs 无交集；
- hard-pair 不被拆散；
- OOD 波形不进入训练集。

## Step 9：窗口化与采样

生成 L=8/16/32 三种窗口。

训练：stride=2 或事件均衡采样。

验证/测试：stride=1，保持顺序。

验收：

- 窗口只包含过去数据；
- 标签来自窗口末端之后的未来区间；
- 不跨轨迹边界；
- 每条轨迹贡献受限。

## Step 10：先跑简单基线

实现：

- sensor_code threshold；
- delta-code threshold；
- short-history rule。

目的：

- 检查数据集是否过于简单；
- 若阈值接近完美，增加困难样本后再训练 TCN。

验收：

- 输出 IID/OOD/low-severity 分项结果；
- 保存最佳阈值只由验证集决定。

## Step 11：实现文献式卷积自编码器

实现 window=16、stride=1 的正常数据训练基线。

要求：

- 只用正常训练窗口；
- 阈值来自训练/验证正常损失；
- 支持连续 K 窗口确认；
- 不把测试异常数据用于阈值选择。

## Step 12：实现 1D-CNN 和 1D-TCN

TCN 必须：

- causal convolution；
- dilated residual blocks；
- 无未来泄漏；
- 输出 3 类。

验收：

- 单元测试验证因果性；
- 修改未来输入不能改变当前输出；
- 保存参数量、MACs 和推理时延估计。

## Step 13：连续窗口确认扫描

扫描：

```text
K_confirm = 1, 3, 5, 9
```

评价误报与检测延迟折中。

验收：

- 报告额外确认延迟；
- 不只选择误报最低方案；
- 需要保留正的故障前提前量。

## Step 14：完整评估

输出：

- 窗口级指标；
- 事件级指标；
- IID/OOD/低严重度/未见背景/低占空比；
- hard-pair；
- threshold/CAE/CNN/TCN 对比。

## Step 15：生成论文级图表

至少包含：

1. 数据集整体流程图；
2. busy/bursty/mixed 背景示例；
3. 已知与 OOD 压降波形示例；
4. sensor code 时间序列；
5. 标签状态时间线；
6. class distribution；
7. split audit；
8. confusion matrix；
9. PR curves；
10. event detection timeline；
11. false alarm vs confirmation windows；
12. lead time distribution；
13. hard-pair 对比；
14. 四种模型综合对比。

---

## 17. Pilot 阶段停止条件

Pilot 数据集只有满足以下条件才进入正式扩展：

1. 至少 96 条独立完整轨迹；
2. train/validation/test 无 `base_waveform_id` 泄漏；
3. 所有波形与标签可复现；
4. Safe/Warning/Critical 均有多个独立基础波形；
5. 至少一种 OOD 波形完全未出现在训练中；
6. 至少包含 busy、bursty、mixed 和 randomizer-like 背景；
7. 至少包含 1%、5%、10%、25% 异常占空比测试；
8. 阈值基线不能轻易在所有测试集上接近完美；
9. hard-pair 样本足以区分时序模型与单点阈值；
10. TCN 在 OOD 或低严重度测试上相对 CNN/阈值有明确优势；
11. 连续窗口确认后的事件提前量仍为正；
12. 所有报告均可由 manifest 和配置复现。

---

## 18. 最终成果

本计划完成后，仓库应具备：

```text
可参数化的直接 VDD_A 波形生成器
可批量运行的标准单元 SPICE 数据生成器
严格无泄漏的数据集划分
未来时序风险标签
阈值/CAE/CNN/TCN 四类模型
窗口级与事件级评估
IID/OOD/低严重度/低占空比测试
可用于论文的图表和复现报告
```

最终论文中的方法描述应明确：

> 共享 PDN 平台用于验证跨芯粒攻击能够真实形成危险压降；直接局部压降平台用于高效、可控地生成电压风险检测数据；TCN 仅使用可硬件获得的 Vernier 传感器数字码，预测未来时间窗口内的时序风险等级。
