# 二分类多统计量 CNN 结构化剪枝、微调与蒸馏执行计划

## 0. 本计划的目的

本计划用于指导 Codex 在**不改变任务定义、不触碰冻结测试边界、不提前修改 RTL**的前提下，压缩当前高精度二分类 1D-CNN 的卷积主干，并形成一个可量化、可重新硬件化的轻量模型。

本计划的主路线固定为：

```text
冻结当前高精度 Teacher
        ↓
建立可变通道模型与结构化通道迁移工具
        ↓
Critical-aware 通道重要性分析
        ↓
逐层敏感度扫描
        ↓
迭代结构化通道剪枝
        ↓
小学习率恢复微调
        ↓
固定 Teacher 的 logit 蒸馏
        ↓
必要时加入 Average/Maximum/Endpoint 统计特征蒸馏
        ↓
可选：Conv2/Conv3 的 k=5→k=3 结构化卷积核裁剪
        ↓
三随机种子 validation-only 正式比较
        ↓
冻结浮点轻量模型
        ↓
重新执行 W8/A8 定点量化与 bit-true 导出
        ↓
停止；另立计划重新设计 RTL 和任务三功耗码本
```

本计划不是 NAS，不允许 Codex 同时更换任务、窗口、标签、输入特征、池化合同和后处理方式。压缩过程中必须保持可解释的单变量推进，保证每一项精度变化都能够归因。

---

# 1. 当前权威基线与冻结合同

## 1.1 Teacher 模型

压缩 Teacher 必须绑定到当前三种子训练报告中选出的代表 checkpoint：

```text
architecture_id: multistat_w18_k5
input_channels: 1
window_length: 32
channels: [18, 18, 18]
kernel_size: [5, 5, 5]
pooling: average + maximum + endpoint
classifier_features: 54
classes: Safe / Critical
representative_seed: 20260727
teacher_checkpoint_sha256:
  b6741281203fc4593b6434df584ace44cffa5daed23ece8745d1b14215a64814
```

Codex 必须从现有最终训练报告和 fixed-point 配置中交叉验证上述 SHA256。若本地 checkpoint 摘要不一致，立即停止，不得自行选择 seed `20260725`、其他 checkpoint 或重新训练 Teacher 来替代。

## 1.2 Teacher validation 基线

必须区分以下两种基线，禁止混用。

### 三种子聚合基线：用于最终发布比较

```text
Median Accuracy                 0.987873
Median Balanced Accuracy        0.981712
Median Macro-F1                 0.952356
Median Critical PR-AUC          0.900391
Worst-seed Critical Recall      0.964212
Median Safe FAR                 0.011112
Parameters                      3494
Estimated MAC/window            106668
```

### 代表 Teacher seed 20260727：用于蒸馏和逐模型对照

```text
Accuracy                        0.987251
Balanced Accuracy               0.986778
Macro-F1                        0.951061
Critical PR-AUC                 0.900391
Critical Recall                 0.986235
Safe FAR                        0.012679
```

最终模型选择必须使用三种子聚合指标；单种子扫描阶段只允许用于缩小候选范围，不能作为正式结论。

## 1.3 冻结数据与任务合同

压缩期间必须保持：

```text
任务：当前状态 Safe / Critical 二分类
输入：仅归一化 sensor_code
归一化：(sensor_code - 15) / 17
窗口：L32
标签：Warning 合并到 Safe
池化：Average + Maximum + Endpoint
训练数据：现有 train split
选择数据：现有 validation split
禁止数据：iid_test、ood_test
采样：natural sampling
基础监督损失：unweighted cross entropy
```

不得创建新的随机 window split，不得按窗口重新打乱 trace 归属，不得修改标签阈值，不得引入 `delta_code`、`bubble_count`、`code_valid`、测量 VDD、slack 或未来样本作为输入。

---

# 2. 本计划明确禁止的事项

在本计划全部完成前，Codex 不得：

1. 读取、推理、评估或调参使用 IID/OOD 特征、预测或指标；
2. 重跑既有冻结 IID/OOD；
3. 修改标签、窗口长度、输入通道或 Safe/Critical 定义；
4. 修改 Average/Maximum/Endpoint 池化合同；
5. 修改后处理阈值、迟滞或事件状态机；
6. 将非结构化稀疏率当作硬件压缩收益；
7. 直接把权重置零而不物理删除通道；
8. 同时修改通道数、kernel、量化位宽和网络类型；
9. 将普通卷积替换为 depthwise、TCN、FCN、Transformer、RNN；
10. 修改 `rtl/cnn_monitor`、ROM、周期模型或任务三功耗码本；
11. 删除、覆盖或改写旧模型、旧报告和旧 run；
12. 用 best single seed 替代三种子聚合结果；
13. 因为 Accuracy 较高而忽略 Critical Recall、Critical PR-AUC 和 Safe FAR；
14. 为了满足门槛伪造或手工编辑机器可读指标。

Depthwise-separable CNN 和因果流式 CNN 属于后续独立研究分支，不在本计划 v1 范围内。只有本计划结束后确认结构化剪枝仍无法达到目标复杂度，才能另立计划讨论。

---

# 3. Codex 执行纪律

## 3.1 每次执行前

Codex 每进入一个 Step，必须：

1. 重新读取本计划；
2. 记录本计划 SHA256、当前 Git commit、UTC 时间和 Step 编号；
3. 检查工作树，禁止覆盖无关改动；
4. 创建全新的 run 目录，默认拒绝覆盖非空目录；
5. 验证所有输入文件 SHA256；
6. 仅在当前 Step 验收通过后进入下一 Step。

建议日志位置：

```text
tcn_detection/runs/formal_v1_20260727_r1/
  models/state_code_binary_cnn_compression_v1_<run_tag>/
    evidence/plan_reads.log
    evidence/input_manifest.json
    evidence/commands.log
```

生成型 checkpoint、prediction、TensorBoard 和中间缓存继续遵守仓库现有 ignore policy。小型配置、脚本、测试和最终 Markdown/JSON 报告必须进入版本控制。

## 3.2 不确定路径的处理

Codex 应先定位当前 CNN 模型类、训练入口、数据加载器、指标实现和复杂度估计器，并复用现有实现。禁止在未检查现有代码前复制一套新的数据加载或指标代码。

若现有文件名与本计划建议路径不同，允许按仓库既有风格放置，但必须在最终报告中列出实际文件映射。

---

# 4. 建议新增的版本化源码与配置

建议新增：

```text
tcn_detection/config/state_code_binary_cnn_compression_v1.json

tcn_detection/compression/
  __init__.py
  teacher_contract.py
  channel_importance.py
  channel_surgery.py
  distillation.py
  complexity.py
  run_sensitivity_scan.py
  run_iterative_pruning.py
  run_distillation.py
  finalize_compression.py

tcn_detection/tests/
  test_compression_teacher_contract.py
  test_channel_surgery.py
  test_channel_importance.py
  test_distillation_contract.py
  test_compression_data_boundary.py
  test_compression_complexity.py
```

若仓库已有同类模块，应扩展现有模块，而不是机械创建重复文件。

最终报告建议放置：

```text
tcn_detection/runs/formal_v1_20260727_r1/reports/
  state_code_binary_cnn_compression_v1_<run_tag>/
    BASELINE_AUDIT.md
    LAYER_SENSITIVITY.md
    PRUNING_PATHS.md
    DISTILLATION_ABLATION.md
    FINAL_COMPRESSION.md
    final_compression.json
    selected_candidate_manifest.json
```

---

# 5. Step 0：冻结输入、Teacher 和边界

## 要做什么

1. 读取：
   - 当前模型配置；
   - 最终三种子训练报告；
   - fixed-point 配置；
   - 当前训练入口；
   - 当前 validation 指标实现；
   - 当前 split/window manifest。
2. 建立 `teacher_contract.json`，至少记录：
   - architecture ID；
   - checkpoint 路径和 SHA256；
   - channels、kernel、pooling、输入和标签合同；
   - train/validation window 文件路径和 SHA256；
   - forbidden split 列表；
   - Teacher 单种子和三种子聚合基线；
   - Python/PyTorch 版本；
   - 当前 Git commit。
3. 使用现有 evaluator 对代表 Teacher 只运行一次 validation 复核；不得读取 IID/OOD。
4. 验证复核指标与现有报告一致，误差仅允许来自确定性浮点打印精度。
5. 输出 `BASELINE_AUDIT.md`。

## 验收条件

- checkpoint SHA256 精确等于 `b674...a64814`；
- 模型结构精确为 `[18,18,18]`、k=5、多统计量池化；
- validation 数量、类别数和指标与冻结报告一致；
- evaluator 明确记录 `iid_features_loaded=false`、`iid_metrics_computed=false`；
- 未产生新的 IID/OOD 文件；
- 所有输入摘要已写入 manifest。

任一项失败时，状态写为：

```text
BLOCKED_TEACHER_OR_DATA_PROVENANCE_MISMATCH
```

并停止。

---

# 6. Step 1：把现有 CNN 改造成可配置通道结构

## 要做什么

在不改变默认行为的前提下，让当前 CNN 支持：

```text
cnn_channels: [c1, c2, c3]
kernel_sizes: [k1, k2, k3]
pooling_contract: multistat_average_max_endpoint
classifier_features: 3 * c3
```

默认配置仍必须实例化原模型：

```text
[18,18,18], [5,5,5]
```

模型 forward 应可选返回：

```text
logits
conv1_activation
conv2_activation
conv3_activation
average_feature
maximum_feature
endpoint_feature
```

训练默认只返回 logits；蒸馏时才启用中间特征返回。不得让调试输出进入部署接口。

## 必须实现的测试

1. 旧配置构建的新模型参数名和张量形状与 Teacher checkpoint 完全兼容；
2. 加载 Teacher 后，所有 validation logits 与旧模型逐元素相等；
3. `[16,16,16]`、`[12,12,12]`、`[8,12,12]` 可正常 forward；
4. 分类头输入维度始终为 `3*c3`；
5. Average、Maximum、Endpoint 的拼接顺序不变；
6. 不允许数据相关 early exit；
7. 参数量和 MAC 估计根据配置自动计算，禁止硬编码 3494/106668。

## 验收条件

旧配置输出必须 bitwise 或在既有确定性容差内完全一致。若旧配置行为变化，不得进入剪枝。

---

# 7. Step 2：实现结构化通道迁移工具

## 7.1 通道删除必须物理生效

实现 `channel_surgery.py`，输入：

```text
teacher/student checkpoint
原 channels
目标 channels
每层保留通道索引
```

输出物理压缩后的新模型和 checkpoint。不得只使用 mask 保留原维度。

## 7.2 权重迁移规则

### 剪 Conv1 输出通道

- 保留 Conv1 指定输出 filter 和 bias；
- 同步保留 Conv2 对应输入通道；
- 保持通道相对顺序稳定。

### 剪 Conv2 输出通道

- 保留 Conv2 指定输出 filter 和 bias；
- 同步保留 Conv3 对应输入通道。

### 剪 Conv3 输出通道

- 保留 Conv3 指定输出 filter 和 bias；
- 重建多统计量分类头；
- 对每个保留通道 `c`，同步保留分类头中三段对应列：

```text
average slice
maximum slice
endpoint slice
```

分类头的最终输入排列必须仍为：

```text
[average all kept channels,
 maximum all kept channels,
 endpoint all kept channels]
```

## 7.3 测试

1. 不剪通道时，surgery 前后参数和 logits 完全一致；
2. 对随机 keep-index，compact 模型输出必须与“原模型被删除通道显式置零且下游对应列同步置零”的参考实现一致；
3. 每个层的输入/输出维度和 classifier 三段映射正确；
4. 保留权重来自原 checkpoint，不得随机初始化；
5. 所有导出 checkpoint 包含原始 Teacher SHA、keep-index 和目标结构；
6. 非法索引、重复索引、越界索引、非递增映射必须失败。

---

# 8. Step 3：建立 Critical-aware 通道重要性分析

## 8.1 主重要性方法

主方法使用一阶 Taylor 通道重要性：

```text
score_c = mean(abs(activation_c * gradient_c))
```

分别在 Safe 和 Critical 样本上累计：

```text
score_safe[layer][channel]
score_critical[layer][channel]
```

每层、每类别独立归一化后，最终主分数固定为：

```text
score_final = max(score_safe_normalized,
                  score_critical_normalized)
```

该规则用于防止一个通道虽然对多数 Safe 样本贡献小，但对 Critical 样本关键时被错误删除。

## 8.2 重要性校准数据

- 只允许来自 train split；
- 使用固定种子生成确定性 calibration subset；
- Safe/Critical 可等量抽样用于**重要性估计**，但不得改变正式训练的 natural sampling；
- 记录 trace ID、window ID 和摘要；
- 不允许使用 validation 计算通道重要性；
- 不允许读取 IID/OOD。

## 8.3 对照方法

同时实现仅用于消融的：

```text
filter L1 norm
filter L2 norm
```

但正式剪枝默认必须使用 Critical-aware Taylor。只有报告证明其他方法在相同预算上更优，才可作为候选，不能静默切换。

## 8.4 统计分支审计

对 Conv3 通道额外报告其在：

```text
Average
Maximum
Endpoint
```

三个分支上的激活量和梯度贡献。该结果用于审计，不直接替代主 Taylor 排名。

## 验收条件

- 相同输入、种子和 checkpoint 重复运行得到相同排名；
- 每层通道数完整；
- Safe/Critical 分数均非全零、非 NaN；
- 报告每层 top/bottom 通道；
- 更换 calibration 样本顺序不得改变累计结果；
- 明确证明没有访问 validation 之外的选择信息或任何 test 信息。

---

# 9. Step 4：逐层敏感度扫描

此阶段只使用代表 Teacher seed `20260727`，用于缩小候选范围，不形成正式模型结论。

## 9.1 扫描结构

一次只剪一层，其他层保持 18：

```text
Conv1 scan:
[16,18,18]
[14,18,18]
[12,18,18]
[10,18,18]
[ 8,18,18]

Conv2 scan:
[18,16,18]
[18,14,18]
[18,12,18]
[18,10,18]
[18, 8,18]

Conv3 scan:
[18,18,16]
[18,18,14]
[18,18,12]
[18,18,10]
[18,18, 8]
```

每个候选：

1. 按 Taylor 排名做物理通道裁剪；
2. 继承保留权重；
3. 用 train split 小学习率恢复 5 个 epoch；
4. validation 只评价，不参与梯度；
5. 输出全部核心指标和复杂度。

## 9.2 恢复训练默认参数

初始固定为：

```text
optimizer: AdamW
learning_rate: 4e-4
weight_decay: 1e-5
batch_size: 256
max_epochs: 5
sampling: natural
supervised_loss: unweighted CE
scheduler: none
```

此阶段不做 KD 超参数搜索。

## 9.3 敏感度报告

对每层给出：

- 通道数与 MAC；
- Accuracy；
- Balanced Accuracy；
- Macro-F1；
- Critical PR-AUC；
- Critical Recall；
- Safe FAR；
- 相对 Teacher 的指标变化；
- 是否出现突然失稳。

## 9.4 结束规则

为每层定义最小“安全宽度”：在短恢复训练后满足：

```text
Critical PR-AUC drop <= 0.010
Critical Recall drop <= 0.010
Safe FAR increase <= 0.005
Macro-F1 drop <= 0.010
```

若某层从 12 降到 10 时发生明显崩溃，应将该层最小宽度冻结在 12，不得为了达到预设 MAC 强行继续。

---

# 10. Step 5：建立固定的迭代剪枝路径

敏感度扫描完成后，必须运行以下主路径。每次只减少 2 个通道，剪枝后立即恢复，不允许一步从 18 跳到 8。

## 10.1 Path A：均衡压缩

```text
[18,18,18]
→ [16,16,16]
→ [14,14,14]
→ [12,12,12]
```

## 10.2 Path B：前端优先压缩

仅在 Conv1 敏感度允许时运行：

```text
[18,18,18]
→ [16,16,16]
→ [12,14,14]
→ [10,12,12]
→ [ 8,12,12]
```

## 10.3 Path C：末端优先压缩

仅在 Conv3 敏感度允许时运行：

```text
[18,18,18]
→ [16,16,16]
→ [14,14,12]
→ [12,12,10]
→ [12,12, 8]
```

## 10.4 Path D：激进压缩

只有 A/B/C 中至少一个模型在约 50% MAC 以下仍通过严格质量门槛时，才允许运行：

```text
[12,12,12]
→ [10,10,10]
→ [8,8,8]
```

## 10.5 每个剪枝步要做什么

1. 从上一步最佳 checkpoint 出发；
2. 重新计算当前模型 Taylor 重要性，不得一直沿用 Teacher 排名；
3. 物理删除最低分通道；
4. 验证 surgery 等价性；
5. 运行 10 至 20 epoch 恢复微调；
6. 保存 best validation Critical PR-AUC checkpoint；
7. 输出训练历史、validation predictions、复杂度和摘要；
8. 只有当前步通过宽松门槛，才继续下一步。

## 10.6 逐步停止门槛

任一剪枝步若满足以下任一条件，当前路径停止：

```text
Critical PR-AUC drop > 0.015
Critical Recall drop > 0.020
Safe FAR increase > 0.010
Macro-F1 drop > 0.020
出现 NaN/训练不稳定
```

停止路径不等于删除失败证据；必须保留报告并注明失败位置。

---

# 11. Step 6：实现固定 Teacher 的 logit 蒸馏

## 11.1 Teacher 行为

- Teacher 为 seed `20260727`、SHA256 `b674...a64814`；
- 全程 `eval()`；
- 参数 `requires_grad=false`；
- 不得更新 BatchNorm/Dropout 状态；
- Teacher 输出可在线计算，也可在严格绑定 window ID 和输入摘要的前提下缓存；
- 缓存必须记录 checkpoint SHA、window manifest SHA 和 logits SHA。

## 11.2 蒸馏损失

基础损失：

```text
L_total = alpha_ce * CE(student_logits, label)
        + (1 - alpha_ce) * T^2 * KL(
              softmax(teacher_logits / T),
              softmax(student_logits / T))
```

第一轮固定：

```text
T = 4
alpha_ce = 0.5
```

只对 Step 5 中 Pareto 最好的 3 个学生进行正式蒸馏，禁止对所有失败结构做无界搜索。

## 11.3 小型 validation-only 蒸馏搜索

若固定配置未恢复质量，仅允许搜索：

```text
T ∈ {2, 4}
alpha_ce ∈ {0.5, 0.7}
```

共最多 4 个组合。选择指标顺序：

1. Critical PR-AUC；
2. Critical Recall；
3. Macro-F1；
4. Safe FAR；
5. 更低 MAC。

## 11.4 训练参数

建议起点：

```text
learning_rate: 4e-4
weight_decay: 1e-5
batch_size: 256
max_epochs: 60
early_stopping_patience: 15
scheduler: none
sampling: natural
```

可在配置中调整，但不得根据 IID/OOD 调参。

## 验收条件

- 关闭 KD 时退化为普通 CE 微调；
- Teacher 无梯度、无权重变化；
- 相同 batch 的离线缓存与在线 Teacher logits 一致；
- 温度和 `T^2` 缩放正确；
- CE 与 KD 分量分别记录；
- 不允许只报告总 loss 而无法审计各分量。

---

# 12. Step 7：可选的多统计量特征蒸馏

只有满足以下条件时才允许进入：

```text
logit KD 后模型已明显恢复，
但 Critical PR-AUC 或 Critical Recall 仍未达到最终严格门槛。
```

## 12.1 蒸馏目标

分别对齐：

```text
Teacher average feature: 18 dims
Teacher maximum feature: 18 dims
Teacher endpoint feature: 18 dims
```

Student 通道数可能小于 18，因此使用训练期投影：

```text
student_feature (c3)
→ train-only projection (c3→18)
→ teacher_feature (18)
```

三个分支使用独立投影。投影层只用于训练，最终部署模型必须删除。

## 12.2 损失

```text
L_stat = SmoothL1(P_avg(student_avg), teacher_avg)
       + SmoothL1(P_max(student_max), teacher_max)
       + SmoothL1(P_end(student_endpoint), teacher_endpoint)

L_total = L_CE + lambda_kd * L_KD + lambda_stat * L_stat
```

第一轮固定：

```text
lambda_stat = 0.1
```

最多再测试：

```text
lambda_stat ∈ {0.1, 0.2, 0.3}
```

## 12.3 验收条件

- 投影层不进入最终 checkpoint 的部署 state dict，或明确存放在 train-only namespace；
- 导出的 student 仅包含 CNN 主干、三统计量池化和分类头；
- 三个统计分支损失分别报告；
- 不允许只蒸馏 average 而省略 maximum/endpoint 后仍宣称保持原多统计合同。

若特征蒸馏没有改善 validation 门槛，应保留消融结果并回退到 logit KD，不得强制采用。

---

# 13. Step 8：可选的结构化卷积核裁剪

此阶段不是默认步骤。只有通道剪枝后的最佳模型仍超过目标 MAC，且其严格质量门槛有足够余量时才允许运行。

## 13.1 允许的 kernel 候选

从最佳通道模型出发：

```text
K0: [5,5,5]  基线
K1: [5,5,3]
K2: [5,3,3]
```

第一层保持 k=5，禁止本轮直接改为 `[3,3,3]`，避免同时削弱输入局部波形提取。

## 13.2 权重继承

k=5→k=3 时，只保留中心三个 tap：

```text
原 tap indices: [0,1,2,3,4]
保留 indices:   [1,2,3]
```

必须物理生成 k=3 权重张量，不允许通过 mask 保持 k=5 循环。

## 13.3 训练

- 先运行无 KD 的短恢复；
- 再使用 Step 6 选定的 KD 配置；
- 不允许同时改变 channels；
- 报告感受野变化与 MAC 变化。

## 验收门槛

kernel 裁剪后仍必须通过最终严格质量门槛，否则回退到 `[5,5,5]`。

---

# 14. Step 9：正式三随机种子验证

## 14.1 候选数量

只允许选择最多 3 个 Pareto 候选进入正式三种子阶段：

1. 最稳健候选：通常为 `[12,12,12]`；
2. 最低 MAC 且通过单种子严格门槛的候选；
3. 一个不同压缩形态候选，例如 `[8,12,12]` 或 kernel-cropped 模型。

## 14.2 随机种子

固定：

```text
20260725
20260726
20260727
```

Teacher checkpoint仍固定为 seed `20260727` 的 `b674...a64814`。Student 初始化和训练随机性按上述三 seed 变化。

## 14.3 最终严格质量门槛

相对于三种子聚合 Teacher：

```text
Median Critical PR-AUC >= 0.895391
  即下降不超过 0.005

Worst-seed Critical Recall >= 0.954212
  即下降不超过 0.010

Median Macro-F1 >= 0.947356
  即下降不超过 0.005

Median Balanced Accuracy >= 0.971712
  即下降不超过 0.010

Median Safe FAR <= 0.014112
  即增加不超过 0.003

Median Accuracy 只报告，不作为首要筛选指标
```

## 14.4 压缩门槛

至少满足：

```text
MAC/window reduction >= 50%
```

目标等级：

```text
Level 1: MAC <= 53334   （至少减半）
Level 2: MAC <= 40000
Level 3: MAC <= 30000
```

最终选择规则固定为：

1. 先过滤全部质量门槛；
2. 在可行模型中选 MAC 最低者；
3. MAC 相同则参数量更低者优先；
4. 再比较 worst-seed Critical Recall；
5. 再比较 Critical PR-AUC；
6. 再比较 Safe FAR；
7. 最后按 architecture ID 字典序确定性打破平局。

不得因为单个 seed 表现最好而跳过上述规则。

## 14.5 代表 checkpoint

从最终三种子中选取最接近 median Critical PR-AUC 的真实 seed，平局依次使用：

```text
更高 Macro-F1
更高 Critical Recall
更低 Safe FAR
更小 seed
```

记录 checkpoint SHA256。

---

# 15. Step 10：Teacher Assistant 可选分支

只有当直接从 18 通道 Teacher 蒸馏到激进模型（如 `[8,8,8]`）失败，而 `[12,12,12]` 已通过严格门槛时，才允许运行 Teacher Assistant：

```text
Teacher: [18,18,18]
        ↓
Assistant: [12,12,12]
        ↓
Final Student: [8,8,8] 或其他激进候选
```

要求：

- Assistant 必须先按 Step 9 正式通过；
- 第二阶段蒸馏使用 Assistant logits；
- 最终报告同时比较 direct KD 与 assistant KD；
- 不得因为 assistant KD 复杂而跳过直接 KD 对照；
- Teacher Assistant 仍仅使用 train/validation。

若激进模型仍不通过严格门槛，则保留 Level 1/2 模型作为最终候选，不得强求 `[8,8,8]`。

---

# 16. Step 11：冻结浮点轻量模型

最终浮点候选选定后，生成：

```text
selected_candidate_manifest.json
model_config.json
training_config.json
teacher_contract.json
checkpoint.pt
checkpoint.sha256
validation_predictions.csv
training_summary.json
complexity.json
FINAL_COMPRESSION.md
```

manifest 必须记录：

- 来源 Teacher SHA；
- 剪枝路径和每一步 keep-index；
- 最终 channels/kernel；
- KD 配置；
- 是否使用统计特征蒸馏；
- 是否使用 Teacher Assistant；
- 三种子指标；
- 代表 checkpoint；
- 参数量、MAC、权重字节和最大激活量；
- 数据 manifest SHA；
- `iid_features_loaded=false`；
- `iid_metrics_computed=false`；
- 当前 Git commit；
- 全部关键产物 SHA256。

最终浮点模型仍只能描述为：

```text
validation-selected compressed CNN candidate
```

不得描述为部署就绪，也不得声称新的 IID/OOD 泛化结论。

---

# 17. Step 12：重新执行定点量化

只有浮点候选冻结后，才允许重新量化。

## 17.1 第一优先候选

```text
W8/A8
```

保持现有定点合同：

- signed symmetric；
- zero point 0；
- per-output-channel weight scale；
- per-layer activation scale；
- ties-to-even；
- 饱和规则不变；
- average pool 的 32 点累加和除法规则不变；
- tie decision 为 Safe。

## 17.2 不允许的行为

- 不得直接复用旧 `[18,18,18]` 权重包；
- 不得在浮点搜索阶段混入 QAT；
- 不得为了量化指标重新访问 IID/OOD；
- 不得修改标签或后处理补偿量化损失。

## 17.3 量化验收

相对冻结轻量浮点模型：

```text
Accuracy drop <= 0.005
Balanced Accuracy drop <= 0.010
Macro-F1 drop <= 0.010
Critical PR-AUC drop <= 0.020
Critical Recall drop <= 0.010
Safe FAR increase <= 0.010
```

并生成：

```text
new fixed-point config
quantized weight package
bit-true reference
new golden vectors
fixed-point report
artifact SHA256 manifest
```

此 Step 结束后仍不得修改 RTL。新的 RTL、ROM、周期模型和功耗码本必须由后续独立计划处理。

---

# 18. Step 13：最终报告、测试和停止门禁

## 18.1 必须完成的测试

至少包括：

1. Teacher provenance；
2. 数据边界；
3. 可变通道旧模型等价；
4. channel surgery；
5. classifier 三分支索引映射；
6. Taylor 重要性确定性；
7. Critical-aware score 合成；
8. KD loss 数学正确性；
9. Teacher 冻结；
10. train-only 投影层不会进入部署模型；
11. MAC/参数量自动计算；
12. kernel 中心裁剪；
13. 三种子聚合和确定性排名；
14. forbidden split 不可加载；
15. W8/A8 bit-true 回归。

## 18.2 最终报告必须回答

1. 哪一层最敏感；
2. 哪一层冗余最多；
3. Taylor 与 L1/L2 排名的差异；
4. 普通微调、logit KD、统计特征 KD 分别恢复了多少精度；
5. 最终模型相对 Teacher 减少多少参数和 MAC；
6. 最终最差 seed 的 Critical Recall；
7. Safe FAR 是否恶化；
8. kernel 裁剪是否值得；
9. W8/A8 是否保持浮点轻量模型质量；
10. 为什么最终模型适合进入新的 RTL 设计。

## 18.3 最终状态码

### 全部通过

```text
CNN_COMPRESSION_V1_COMPLETE
FLOAT_CANDIDATE_FROZEN
W8A8_HANDOFF_READY
NEXT_STAGE_REQUIRES_NEW_RTL_PLAN
```

### 浮点压缩通过，但量化未通过

```text
CNN_COMPRESSION_V1_FLOAT_COMPLETE
BLOCKED_FIXED_POINT_QUALITY_GATE
```

### 无模型同时满足质量和至少 50% MAC 压缩

```text
CNN_COMPRESSION_V1_NO_FEASIBLE_CANDIDATE
RECOMMEND_SEPARATE_DEPTHWISE_OR_STREAMING_PLAN
```

不得通过放宽 test 边界、改标签或手工修改指标解除失败状态。

---

# 19. 推荐的最小执行顺序

Codex 必须按以下顺序推进：

```text
0. 基线和 Teacher SHA 审计
1. 可配置模型和旧模型等价测试
2. 结构化 channel surgery
3. Critical-aware Taylor 重要性
4. 单层敏感度扫描
5. Path A/B/C 迭代剪枝
6. 普通恢复微调对照
7. logit KD
8. 必要时统计特征 KD
9. 必要时 k=5→k=3 结构化裁剪
10. 最多三个候选的三种子正式验证
11. 冻结浮点轻量模型
12. W8/A8 定点量化与 bit-true 导出
13. 最终报告和停止门禁
```

不得跳过 Step 0、Step 1、Step 2 或直接从 Teacher 训练一个随机初始化的小模型。不得在选出浮点轻量模型前开始新的 RTL。

---

# 20. 与当前硬件和任务三的关系

现有 `[18,18,18]`、k=5、12892-cycle RTL 和任务三活动码本保留为：

```text
legacy_multistat_w18_k5_hardware_baseline
```

本计划不删除、不修补、不继续扩展该功耗码本。原因是通道、kernel、权重、ROM 和 MAC 数据流一旦改变，旧功耗档位不再代表最终硬件。

完成本计划后，下一份计划应重新定义：

```text
轻量模型 RTL
新的 MAC 并行度
新的权重 ROM
新的 latency / II
新的 task-three power codebook
计算复用 idle-slot 预算
```

只有新的轻量 RTL 冻结后，才能继续“计算复用＋电荷整形＋随机扰动”。

---

# 21. 宏观研究方向

本压缩工作的研究结论应围绕：

> 当前高精度多统计量 CNN 中存在可被结构化删除的通道冗余。通过 Critical-aware Taylor 剪枝保护危险类判别通道，使用固定高精度 Teacher 的 logit 与 Average/Maximum/Endpoint 特征蒸馏恢复边界识别能力，可以在不改变 Safe/Critical 任务和单通道 L32 输入合同的前提下，获得显著降低 MAC 的轻量 CNN，为后续低时延硬件和计算复用释放资源。

论文消融至少应包含：

```text
原始 Teacher
随机通道剪枝
L1/L2 通道剪枝
Critical-aware Taylor 剪枝
Taylor + 普通微调
Taylor + logit KD
Taylor + logit KD + multistat feature KD
可选 kernel 裁剪
最终 W8/A8 模型
```

任何最终结论必须同时报告质量、安全类指标和硬件复杂度，不能只报告 Accuracy 或参数压缩率。