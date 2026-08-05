# 当前最终实现报告：多统计量 CNN `[18,8,18]`

## 1. 结论与状态

根据当前工程取舍，选择卷积通道配置 `[18,8,18]` 作为现阶段最终浮点实现。该选择优先保留约 98.54% 的 validation Accuracy，同时将 MAC/window 降低约 54%，达到原压缩计划的 Level 1 复杂度要求。

该模型的准确描述是：

```text
user-selected current floating-point implementation
validation-selected compressed CNN candidate
```

需要明确区分以下事实：

- `[18,8,18]` 已达到至少 50% 的 MAC 压缩要求；
- validation Accuracy 仅比代表 Teacher 低 0.182 个百分点；
- Safe FAR 没有恶化，反而略有降低；
- Critical PR-AUC、Critical Recall、Macro-F1 和 Balanced Accuracy 未通过原计划的严格质量门槛；
- 当前结果来自代表 seed `20260727`，尚未完成三随机种子正式复核；
- 尚未针对该模型执行 W8/A8 量化、bit-true 导出或新 RTL 实现；
- 未读取、推理或评估 IID/OOD 数据，因此不作 IID/OOD 泛化声明。

本报告不会改写此前 `CNN_COMPRESSION_V1_NO_FEASIBLE_CANDIDATE` 的严格门禁结论。当前选择表示接受已量化披露的 Critical 类质量损失，以换取显著的 MAC 和参数压缩。

## 2. 模型身份与产物

| 项目 | 值 |
| --- | --- |
| Architecture ID | `sensitivity_conv2_w8` |
| 通道数 | `[18,8,18]` |
| Kernel | `[5,5,5]` |
| 输入 | 归一化 `sensor_code`，形状 `[N,1,32]` |
| 输出 | Safe/Critical 两类 logits，形状 `[N,2]` |
| 池化 | Average + Maximum + Endpoint |
| 分类头输入维度 | `3 * 18 = 54` |
| 训练 seed | `20260727` |
| 最佳 epoch | `4 / 5` |
| Checkpoint | `sensitivity_scan/conv2_w8/best_checkpoint.pt` |
| Checkpoint SHA256 | `2ee30cdac4ee114c1b2a50d34289ecc84a2c885409b9a386032f56a03cca8c4d` |
| 来源 Teacher SHA256 | `b6741281203fc4593b6434df584ace44cffa5daed23ece8745d1b14215a64814` |
| Window CSV SHA256 | `ccb8787a0766e46e79a56b6b78846aa0e0a4842d420c8a7bbd3000977b50d065` |
| 执行计划 SHA256 | `5727557709d413ff458fa4b46916651e5d22b85f5b5ed81473ab1ac88cabc10b` |
| 源码 Git commit | `7a84f153643e6b5408edeb7c9472876ca51f0958` |

实际 checkpoint 路径：

```text
tcn_detection/runs/formal_v1_20260727_r1/models/
  state_code_binary_cnn_compression_v1_20260805_r1/
    sensitivity_scan/conv2_w8/best_checkpoint.pt
```

## 3. 冻结任务合同

当前实现继续遵守原二分类任务定义：

| 合同项 | 当前实现 |
| --- | --- |
| 任务 | 当前状态 Safe/Critical 二分类 |
| 输入特征 | 仅 `sensor_code` |
| 窗口长度 | L32 |
| 标签 | Warning 合并到 Safe |
| 类别映射 | `0=Safe`，`1=Critical` |
| 池化顺序 | Average、Maximum、Endpoint |
| 训练采样 | Natural sampling |
| 监督损失 | Unweighted cross entropy |
| 后处理 | 未修改 |
| 禁止数据 | `iid_test`、`ood_test` |

Checkpoint 中的冻结 train-only normalizer 为：

```text
mean = 0.12906921462987161
std  = 0.29408967344229564
source_split = train
window_length = 32
```

## 4. 结构化剪枝实现

该候选仅压缩 Conv2，Conv1 和 Conv3 仍保留 18 个输出通道：

```text
Input [1 x 32]
  -> Conv1: 1  -> 18, k=5
  -> Conv2: 18 ->  8, k=5
  -> Conv3: 8  -> 18, k=5
  -> Average/Maximum/Endpoint: 18 + 18 + 18
  -> Linear: 54 -> 2
```

Conv2 使用 Critical-aware Taylor 排名进行物理通道删除，保留的原始通道索引为：

```text
[1, 3, 5, 6, 9, 11, 14, 15]
```

迁移后的物理权重形状为：

| 张量 | 形状 |
| --- | --- |
| `features.0.weight` | `[18,1,5]` |
| `features.3.weight` | `[8,18,5]` |
| `features.6.weight` | `[18,8,5]` |
| `classifier.weight` | `[2,54]` |

删除通道不依赖运行时 mask。Conv2 输出 filter、Conv3 对应输入列均被物理切片；Conv3 仍为 18 通道，因此 Average/Maximum/Endpoint 分类头保持原 54 列顺序。

## 5. 训练与模型选择

该候选从冻结 Teacher 继承保留权重，随后执行 5 个完整恢复 epoch：

```text
optimizer    = AdamW
learning rate = 4e-4
weight decay  = 1e-5
batch size    = 256
sampling      = natural
loss          = unweighted cross entropy
scheduler     = none
```

Validation 只用于选择 checkpoint，不参与梯度。选择键依次为 Critical PR-AUC、Macro-F1、Balanced Accuracy、Critical Recall 和负 Safe FAR。最终选择 epoch 4，而不是 Accuracy 更高但 Critical PR-AUC 更低的 epoch 5。

| Epoch | Train loss | Accuracy | Balanced Acc. | Macro-F1 | Critical PR-AUC | Critical Recall | Safe FAR |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 0.033496 | 0.985252 | 0.969371 | 0.942423 | 0.873394 | 0.951136 | 0.012394 |
| 2 | 0.030007 | 0.985075 | 0.968635 | 0.941730 | 0.876259 | 0.949759 | 0.012489 |
| 3 | 0.029123 | 0.985386 | 0.970403 | 0.942995 | 0.878473 | 0.953200 | 0.012394 |
| 4 | 0.028461 | 0.985430 | 0.970747 | 0.943185 | 0.885063 | 0.953889 | 0.012394 |
| 5 | 0.027729 | 0.986007 | 0.977463 | 0.945873 | 0.881348 | 0.967653 | 0.012726 |

## 6. Validation 数据与复核结果

本次复核覆盖全部 22,512 个 validation 窗口：

| 类别 | 窗口数 |
| --- | ---: |
| Safe | 21,059 |
| Critical | 1,453 |
| 合计 | 22,512 |

混淆矩阵为：

| Truth / Prediction | Safe | Critical |
| --- | ---: | ---: |
| Safe | 20,798 | 261 |
| Critical | 67 | 1,386 |

完整 validation 指标：

| 指标 | `[18,8,18]` |
| --- | ---: |
| Accuracy | 0.985429993 |
| Balanced Accuracy | 0.970747378 |
| Macro-F1 | 0.943184934 |
| Weighted-F1 | 0.985852182 |
| Critical PR-AUC | 0.885062786 |
| Critical ROC-AUC | 0.995048111 |
| Critical Precision | 0.841530055 |
| Critical Recall | 0.953888507 |
| Critical F1 | 0.894193548 |
| Critical false-negative rate | 0.046111493 |
| Safe FAR | 0.012393751 |
| Negative predictive value | 0.996788881 |
| Log loss | 0.038184073 |
| Brier score | 0.011588650 |
| ECE, 15 bins | 0.005519922 |

## 7. 相对 Teacher 的质量变化

下表使用代表 Teacher seed `20260727` 作为同 seed 对照。绝对变化为“候选减 Teacher”；百分点变化等于绝对变化乘 100。

| 指标 | Teacher | `[18,8,18]` | 绝对变化 | 百分点变化 | 相对变化 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Accuracy | 0.987251 | 0.985430 | -0.001821 | -0.1821 pp | -0.184% |
| Balanced Accuracy | 0.986778 | 0.970747 | -0.016031 | -1.6031 pp | -1.625% |
| Macro-F1 | 0.951061 | 0.943185 | -0.007876 | -0.7876 pp | -0.828% |
| Critical PR-AUC | 0.900391 | 0.885063 | -0.015328 | -1.5328 pp | -1.702% |
| Critical Recall | 0.986235 | 0.953889 | -0.032347 | -3.2347 pp | -3.280% |
| Safe FAR | 0.012679 | 0.012394 | -0.000285 | -0.0285 pp | 改善 2.247% |

Accuracy 降幅较小不能掩盖 Critical Recall 的下降。Validation 中 Safe 占 93.55%，因此总体 Accuracy 对 Critical 漏检不够敏感；Balanced Accuracy、Critical PR-AUC 和 Critical Recall 是更直接的安全类质量指标。

## 8. 参数量、MAC 与存储

### 8.1 分层复杂度

| 层 | 参数量 | MAC/window |
| --- | ---: | ---: |
| Conv1 `1->18, k5` | 108 | 2,880 |
| Conv2 `18->8, k5` | 728 | 23,040 |
| Conv3 `8->18, k5` | 738 | 23,040 |
| Linear `54->2` | 110 | 108 |
| **合计** | **1,684** | **49,068** |

### 8.2 相对 Teacher 的压缩

| 复杂度 | Teacher | `[18,8,18]` | 减少量 | 降低比例 |
| --- | ---: | ---: | ---: | ---: |
| 参数量 | 3,494 | 1,684 | 1,810 | 51.803% |
| MAC/window | 106,668 | 49,068 | 57,600 | 53.999% |
| FP32 参数字节 | 13,976 | 6,736 | 7,240 | 51.803% |

该模型满足原计划的 Level 1 门槛：

```text
MAC/window = 49,068 <= 53,334
```

由于 Conv1 和 Conv3 仍为 18 通道，单层最大激活张量仍为 `18 * 32 = 576` 个元素；主要收益来自 Conv2/Conv3 的输入输出乘加减少，而不是峰值激活存储降低。

## 9. 原计划门槛审计

### 9.1 单层敏感度门槛

| 门槛 | 实际变化 | 结果 |
| --- | ---: | --- |
| Critical PR-AUC drop <= 0.010 | 0.015328 | 失败 |
| Critical Recall drop <= 0.010 | 0.032347 | 失败 |
| Safe FAR increase <= 0.005 | -0.000285 | 通过 |
| Macro-F1 drop <= 0.010 | 0.007876 | 通过 |

### 9.2 原三种子发布阈值的单 seed 预检查

| 指标 | 发布阈值 | 当前单 seed | 预检查 |
| --- | ---: | ---: | --- |
| Critical PR-AUC | >= 0.895391 | 0.885063 | 失败 |
| Critical Recall | >= 0.954212 | 0.953889 | 失败，差 0.000323 |
| Macro-F1 | >= 0.947356 | 0.943185 | 失败 |
| Balanced Accuracy | >= 0.971712 | 0.970747 | 失败 |
| Safe FAR | <= 0.014112 | 0.012394 | 通过 |
| MAC/window | <= 53,334 | 49,068 | 通过 |

该表只是单 seed 预检查，不能替代计划要求的三种子 median/worst-seed 聚合。选择该模型作为当前实现，是在明确接受上述质量偏差后的工程决策，而不是原严格质量门槛已经通过。

## 10. 验证状态

已经完成：

- Teacher checkpoint、窗口和计划 SHA256 复核；
- 旧 Teacher 模型严格加载和 logits 等价测试；
- 物理 channel surgery 和分类头三分支索引测试；
- Critical-aware Taylor 确定性和数据顺序不变性测试；
- 完整 5 epoch 恢复训练；
- 全部 22,512 个 validation 窗口复核；
- 仓库 `tcn_detection/tests` 完整 discovery，共 101 项测试通过；
- `iid_features_loaded=false`；
- `iid_metrics_computed=false`；
- `parameters_tuned_on_test=false`。

尚未完成：

- seed `20260725/20260726/20260727` 的正式三种子复训和聚合；
- `[18,8,18]` 专属 W8/A8 量化、bit-true reference 和 golden vectors；
- 新权重 ROM、RTL 数据通路、latency/II 和周期模型；
- 新任务三功耗码本；
- IID/OOD 一次性冻结评估。

## 11. 硬件实现含义

`[18,8,18]` 在保持输入、输出和三统计量分类头不变的情况下，将中间卷积瓶颈缩小到 8 通道。相比 Teacher：

- Conv2 MAC 从 51,840 降至 23,040；
- Conv3 MAC 从 51,840 降至 23,040；
- Conv1 和分类头复杂度不变；
- 总 MAC 降低约 54%，具备重新设计低延迟 CNN 数据通路的价值；
- 旧 `[18,18,18]` ROM、12892-cycle 周期模型和功耗码本不能直接复用。

当前报告不指定新的 MAC 并行度、ROM 排布、latency 或 II。上述硬件参数必须在新的 RTL 计划中依据 `[18,8,18]` 权重张量重新设计和验证。

## 12. 当前采用决策

现阶段采用：

```text
channels       = [18,8,18]
kernel_sizes   = [5,5,5]
window_length  = 32
pooling        = Average + Maximum + Endpoint
checkpoint     = conv2_w8/best_checkpoint.pt
checkpoint_sha = 2ee30cdac4ee114c1b2a50d34289ecc84a2c885409b9a386032f56a03cca8c4d
```

采用理由是该候选在所有单层扫描结构中提供最大的 MAC/参数压缩，并保持较高总体 Accuracy 和不恶化的 Safe FAR。主要风险是 Critical Recall、Critical PR-AUC、Balanced Accuracy 和 Macro-F1 的可测下降；在完成三种子验证和 W8/A8 bit-true 验收前，不应将其描述为部署就绪模型。
