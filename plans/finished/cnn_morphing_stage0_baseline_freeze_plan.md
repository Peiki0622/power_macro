# 阶段 0：压缩 CNN 基线冻结与开发边界计划

## 1. 目的

本计划只完成一件事：为后续“低周期 CNN + 功能等价执行变体”建立唯一、可审计的开发基线。

Codex 在本阶段不得实现新 RTL、执行置换、PRNG、dummy 计算或功耗实验。所有工作都应围绕以下问题展开：

> 后续设计究竟以哪个模型、哪个 checkpoint、哪套 W8/A8 数值规则、哪些输入输出接口和哪些数据边界为准？

本阶段完成后，后续阶段不得再自行更换模型或量化规则。

---

## 2. 当前仓库事实

开始执行前，Codex 必须先核对远程仓库 HEAD，并将实际 SHA 写入报告。编写本计划时的参考提交为：

```text
739257b0c5174c8912a54f3162742b35e0f2fb5d
```

当前压缩模型合同为：

```text
architecture_id = sensitivity_conv2_w8
channels        = [18, 8, 18]
kernel_sizes    = [5, 5, 5]
input           = sensor_code, [N,1,32]
classes         = Safe / Critical
pooling         = Average + Maximum + Endpoint
classifier      = 54 -> 2
quantization    = W8/A8
```

必须以以下仓库文件为主要依据：

```text
tcn_detection/models/cnn1d.py
tcn_detection/config/fixed_point_cnn_multistat_w18_8_18_k5_v1.json
tcn_detection/fixed_point/bittrue.py
tcn_detection/fixed_point/export_package.py
tcn_detection/fixed_point/provenance.py
tcn_detection/tests/test_fixed_point_compressed_contract.py

tcn_detection/runs/formal_v1_20260727_r1/reports/
  state_code_binary_cnn_compression_v1_20260805_r1/
    CURRENT_FINAL_IMPLEMENTATION_W18_8_18.md
    FIXED_POINT_QUANTIZATION_W18_8_18.md

tcn_detection/runs/formal_v1_20260727_r1/models/
  state_code_binary_cnn_compression_v1_20260805_r1/
    final_w18_8_18_20260805_r1/
```

旧 RTL 目录 `rtl/cnn_monitor/` 仍对应 `[18,18,18]` 模型和旧 12892-cycle 调度，只能作为接口、测试方式和综合脚本参考，不能作为新模型数值真值。

---

## 3. 本阶段禁止事项

Codex 不得在本阶段：

- 修改 `[18,8,18]` 模型通道数或卷积核；
- 重新训练模型；
- 重新选择 checkpoint；
- 修改 Safe/Critical 标签定义；
- 修改 W8/A8 舍入、饱和、ReLU、池化或判决规则；
- 读取 IID/OOD 数据用于设计选择；
- 修改旧 `rtl/cnn_monitor/` 使其“临时兼容”新模型；
- 实现 rolling update、MAC tile、channel/lane permutation 或 PRNG；
- 声称当前模型已经 deployment-ready。

发现源文件、产物或 SHA 不一致时，应停止并生成阻塞报告，不能静默修复或替换。

---

## 4. 逐步执行计划

### Step 0.1：核对仓库 HEAD 和工作区

执行内容：

1. 记录当前 Git HEAD、分支和工作区状态；
2. 确认本阶段所需文件全部存在；
3. 确认没有未提交修改覆盖模型、量化或固定点导出文件；
4. 将检查结果写入机器可读 JSON。

建议产物：

```text
artifacts/cnn_morphing_stage0/source_state.json
```

至少记录：

```text
git_commit
branch
required_files
missing_files
dirty_files
execution_time
```

若关键文件缺失或被未提交修改覆盖，本阶段立即失败。

### Step 0.2：核对模型身份

执行内容：

1. 从 `model_config.json` 和固定点配置中解析模型结构；
2. 使用 `provenance.build_validated_model` 严格加载 checkpoint；
3. 检查卷积权重形状：

```text
Conv1 = [18,1,5]
Conv2 = [8,18,5]
Conv3 = [18,8,5]
Classifier = [2,54]
```

4. 检查 pooling feature 顺序固定为：

```text
average[0:18]
maximum[18:36]
endpoint[36:54]
```

5. 检查 checkpoint SHA256：

```text
2ee30cdac4ee114c1b2a50d34289ecc84a2c885409b9a386032f56a03cca8c4d
```

任何 shape、顺序或 SHA 不匹配均停止。

### Step 0.3：核对 W8/A8 数值合同

执行内容：

1. 读取 `fixed_point_cnn_multistat_w18_8_18_k5_v1.json`；
2. 核对以下规则：

```text
weight = signed int8, per-output-channel scale
activation = signed int8, per-layer scale
rounding = round-to-nearest, ties-to-even
convolution = 完整累加后 requantize
ReLU = 负数归零，再限制到激活范围
average = 32 点求和后 ties-to-even 除以 32
maximum = 直接取 32 点最大值
endpoint = 逻辑位置 31
logits = signed int32
exact tie = Safe
```

3. 核对分析位宽：

```text
Conv1 accumulator = 14 bit
Conv2 accumulator = 20 bit
Conv3 accumulator = 19 bit
Classifier accumulator = 19 bit
```

4. 运行现有固定点压缩合同测试；
5. 运行现有 golden replay 或导出包自检，确认权重 `.mem` round-trip 和整数中间层结果仍然 bit-exact。

本步骤只验证既有合同，不重新搜索位宽。

### Step 0.4：建立不可变基线清单

新增一个小型脚本，例如：

```text
scripts/freeze_cnn_morphing_baseline.py
```

脚本只读取现有文件并输出 SHA256 清单，不复制大型 checkpoint，不改写已有 run 目录。

清单至少包含：

```text
Git commit
model config
checkpoint
fixed-point config
quantization config
weight .mem files
golden windows
golden expected outputs
relevant source files
```

建议产物：

```text
artifacts/cnn_morphing_stage0/baseline_manifest.json
```

脚本必须默认拒绝覆盖已有清单；需要重跑时使用新的 run tag。

### Step 0.5：冻结后续阶段的接口边界

新增：

```text
config/cnn_morphing_development_contract_v1.json
```

该配置只描述后续开发边界，不指定尚未完成的微架构。

至少包含：

```text
model_channels = [18,8,18]
kernel_sizes = [5,5,5]
window_length = 32
sensor_code_range = [0,32]
weight_bits = 8
activation_bits = 8
pooling_order = [average, maximum, endpoint]
class_order = [Safe, Critical]
sample_period_ns = 4.0
preferred_compute_period_ns = 2.0
```

推理步长在本阶段不要凭空固定。只给阶段 1 一个有限搜索集合：

```text
inference_stride_candidates = [1,2,4,8,16,32]
```

阶段 1 必须根据周期和硬件代价给出推荐值。

### Step 0.6：明确科学与数据边界

在报告中明确：

- 当前 `[18,8,18]` 是 user-selected validation candidate；
- W8/A8 只完成 validation 范围内的 bit-true handoff；
- 不重新读取 IID/OOD；
- 后续 RTL 工作不得修改模型指标；
- 后续功能等价变体必须逐 bit 保持当前固定点输出；
- 侧信道有效性不属于阶段 0 到阶段 3 的结论。

### Step 0.7：发布阶段 0 报告

生成：

```text
reports/CNN_MORPHING_STAGE0_BASELINE_FREEZE.md
```

报告必须包含：

1. 实际 Git HEAD；
2. 模型和 checkpoint 身份；
3. W8/A8 数值合同；
4. 所有关键 SHA256；
5. 已运行测试和结果；
6. 明确的禁止事项；
7. 阶段状态。

状态只能是：

```text
STAGE0_BASELINE_FROZEN
```

或：

```text
STAGE0_BLOCKED_<原因>
```

---

## 5. 建议提交顺序

```text
commit 1: add stage-0 audit script and development contract
commit 2: add manifest tests and baseline freeze report
```

不要在同一提交中加入低周期模型或 RTL。

---

## 6. 阶段验收门禁

只有全部满足以下条件，才能进入阶段 1：

- 当前 HEAD 和所用源文件已记录；
- checkpoint SHA 匹配；
- `[18,8,18]` 权重和 classifier shape 匹配；
- pooling 顺序匹配；
- W8/A8 合同测试通过；
- golden replay bit-exact；
- baseline manifest 可重复生成且 SHA 稳定；
- 未读取 IID/OOD；
- 未修改旧 RTL；
- 报告状态为 `STAGE0_BASELINE_FROZEN`。

阶段 0 的完成标准不是“写了配置”，而是后续任何开发者都能仅凭清单和报告准确定位同一模型、同一数值合同和同一 golden 基线。