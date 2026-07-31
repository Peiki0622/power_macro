# 普通 1D-CNN 模型报告（Seed 20260725）

## 1. 报告结论

本报告将随机种子 `20260725` 对应的 `multistat_w18_k5` 普通 1D-CNN
作为当前代表模型。这里的“普通 CNN”指不使用 TCN 残差膨胀卷积结构的
一维卷积分类器；模型仍使用多统计量池化，以保留窗口的均值、最大值和
末端状态信息。

该模型在固定 validation 集的 22,512 个窗口上取得 `0.987962` Accuracy、
`0.953100` Macro-F1 和 `0.900489` Critical PR-AUC。Critical Recall 达到
`0.974535`，即 1,453 个 Critical 窗口中检出 1,416 个；Safe FAR 为
`0.011112`，即 21,059 个 Safe 窗口中有 234 个被误报为 Critical。

本报告只描述 validation 窗口级结果，不读取、不重跑、也不重新解释 IID
结果。报告中的分类结果来自原始二分类输出，未施加滑动滤波、迟滞阈值或
事件级后处理，因此不能直接当作部署状态监测指标。

## 2. 任务与数据口径

| 项目 | 当前口径 |
| --- | --- |
| 任务 | Safe / Critical 二分类状态监测 |
| 标签 0 | Safe，包括原三分类任务中的 Safe 和 Warning |
| 标签 1 | Critical |
| 输入特征 | 单通道归一化原始 sensor code |
| 窗口长度 | 32 个采样点（L32） |
| 评价数据 | 固定 validation split |
| Validation trace 数 | 48 |
| Validation 窗口数 | 22,512 |
| Safe 窗口数 | 21,059 |
| Critical 窗口数 | 1,453 |
| 随机种子 | 20260725 |
| 决策口径 | 原始窗口级 argmax 分类，无后处理 |

训练集观测到 31,656 个 Safe 窗口和 2,184 个 Critical 窗口，类别比例约为
`14.50:1`。本次训练采用自然采样和无权重交叉熵，没有通过过采样或类别
权重改变训练分布。

## 3. 模型结构

| 组件 | 配置 |
| --- | --- |
| Architecture ID | `multistat_w18_k5` |
| 输入通道 | 1 |
| 卷积通道 | `[18, 18, 18]` |
| 卷积核尺寸 | 5 |
| 卷积层数 | 3 |
| 局部感受野 | 13 个采样点 |
| Dropout | 0.1 |
| 池化 | 全局平均 + 全局最大 + 最后位置特征拼接 |
| 分类头 | 两类别线性分类头 |
| 参数量 | 3,494 |
| 估算 MAC/window | 106,668 |

多统计量池化同时保留窗口整体水平、局部峰值和最新采样位置的状态。该结构
比只使用全局平均池化的普通 CNN 更适合区分短时 Critical 峰值，但它仍是
固定窗口分类器，不具有 TCN 的残差块和长程膨胀卷积路径。

## 4. 训练配置

| 参数 | 值 |
| --- | ---: |
| Optimizer | AdamW |
| Learning rate | 0.004 |
| Weight decay | 0.00001 |
| Batch size | 256 |
| 最大 Epoch | 120 |
| Early-stopping patience | 25 |
| LR scheduler | 无 |
| Loss | 无类别权重的 Cross Entropy |
| Sampling | Natural |
| Checkpoint 选择指标 | Validation Critical PR-AUC |
| 最佳 Epoch | 66 |
| 实际完成 Epoch | 91 |
| 训练耗时 | 137.956 秒 |
| CPU 推理延迟 | 0.331486 ms/window |

最佳 checkpoint 出现在第 66 个 epoch；其后继续训练 25 个 epoch 未再改善
Critical PR-AUC，因此在第 91 个 epoch 按预定 patience 正常早停。这说明
120-epoch 上限没有截断该种子的训练过程。

## 5. Validation 总体指标

| 指标 | 数值 |
| --- | ---: |
| Accuracy | 0.987962 |
| Balanced Accuracy | 0.981712 |
| Macro-F1 | 0.953100 |
| Critical PR-AUC | 0.900489 |
| Critical ROC-AUC | 0.995949 |
| Critical Precision | 0.858182 |
| Critical Recall | 0.974535 |
| Critical F1 | 0.912665 |
| Safe Precision | 0.998226 |
| Safe Recall | 0.988888 |
| Safe F1 | 0.993535 |
| Safe FAR | 0.011112 |
| Log-loss | 0.032469 |

Accuracy 很高，但 validation 中 Safe 占 `93.55%`，因此不能只依赖 Accuracy
判断效果。Balanced Accuracy、Macro-F1、Critical PR-AUC 和 Critical Recall
共同表明模型并非仅通过预测多数类获得高分。

## 6. 混淆矩阵

| 真实类别 / 预测类别 | Safe | Critical | 合计 |
| --- | ---: | ---: | ---: |
| Safe | 20,825 | 234 | 21,059 |
| Critical | 37 | 1,416 | 1,453 |
| 合计 | 20,862 | 1,650 | 22,512 |

按 Critical 为正类，混淆矩阵对应：

| 统计项 | 数量 |
| --- | ---: |
| True Positive（TP） | 1,416 |
| False Positive（FP） | 234 |
| False Negative（FN） | 37 |
| True Negative（TN） | 20,825 |

当前错误以误报为主：FP 是 FN 的约 `6.32` 倍。换言之，当前模型优先保证
Critical 检出率，代价是部分 Safe 窗口被报警。若后续部署更关注报警数量，
应在独立 validation 流程中评估因果滑动滤波或迟滞机制，而不能依据 IID
结果继续调节阈值。

## 7. 与参考结果的关系

| 指标 | 同结构调参前 Seed 20260725 | 当前 Seed 20260725 | 三种子 TCN 中位数 |
| --- | ---: | ---: | ---: |
| Accuracy | 0.986763 | **0.987962** | 0.978101 |
| Balanced Accuracy | 0.976265 | **0.981712** | 0.984853 |
| Macro-F1 | 0.948381 | **0.953100** | 0.920481 |
| Critical PR-AUC | 0.894981 | **0.900489** | 0.861863 |
| Critical Precision | 0.850638 | **0.858182** | 未记录 |
| Critical Recall | 0.964212 | **0.974535** | 最差种子 0.982794 |
| Safe FAR | 0.011681 | **0.011112** | 0.022223 |

与同结构、同种子的调参前结果相比，当前参数同时改善了 Accuracy、Balanced
Accuracy、Macro-F1、Critical PR-AUC、Precision、Recall 和 Safe FAR。与
TCN 的三种子中位数相比，当前 CNN 的 Accuracy、Macro-F1、PR-AUC 和 FAR
更好，但这种单种子对三种子聚合的比较仅用于定位量级，不构成严格的
同口径优劣证明。

## 8. 产物与可追溯性

| 产物 | SHA256 |
| --- | --- |
| `best_checkpoint.pt` | `b64abdea5b6c856ca63a7b25ffec5d7781a8f238888809c3c88b87a207f4f9b2` |
| `training_summary.json` | `7b5f7cdb1d0b3bb9e0ef635d19d2833832503fc0cd3e7d9df142ca789cc2db6b` |
| `validation_predictions.csv` | `c88436e176f6ad2147b36d19bd184e977be18e4c17772ffe0d887eb91fb6ce94` |

运行目录：

`runs/formal_v1_20260727_r1/models/state_code_binary_multistat_training_v1_20260731_r1/stage2/lr4em3_b256_seed20260725`

## 9. 最终判断

Seed `20260725` 可以作为当前普通 CNN 的代表结果。它在 validation 上已经
达到较高的窗口分类质量，并且在 3,494 个参数和 106,668 MAC/window 的
计算预算内超过了调参前的同结构模型。当前剩余主要问题不是漏检，而是
234 个 Safe 窗口误报；后续若需要继续优化，应优先评估只基于 validation
冻结的因果后处理，同时保留原始窗口指标作为对照。

该结论不等同于新的 IID 泛化结论，也不表示已通过部署级事件检测和延迟
要求。既有 IID 产物继续保持冻结，不应为该报告重新运行。
