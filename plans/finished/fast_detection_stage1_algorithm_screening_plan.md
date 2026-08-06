# 阶段 1：快速电压跌落检测算法筛选计划

## 1. 总目标

本阶段目标不是设计预测器，而是在**相同检测任务、相同数据划分、相同输入信息约束下**，寻找可以替代当前 CNN 实时检测路径的低延迟检测算法。

核心问题：

> 当前 CNN 能否被更简单、更快、更适合芯粒电源 macro 的确定性检测器替代，同时保持足够的事件检测能力？

本阶段输出不是最终 RTL，而是确定：

1. 最佳快速检测算法；
2. 最小充分特征集合；
3. 与 CNN 的性能-延迟-硬件成本差距；
4. 下一阶段 RTL 实现候选。

---

## 2. 明确边界

### 本阶段做

- 复用现有 Formal V1 数据集；
- 复用冻结 CNN 评价口径；
- 建立统一 detector interface；
- 比较规则检测、统计检测和轻量学习检测；
- 进行事件级延迟评价；
- 输出 Pareto 前沿。

### 本阶段不做

- 不做未来预测任务；
- 不改变标签定义；
- 不训练 TCN；
- 不使用流式 TCN 替代 CNN；
- 不修改 CNN 模型结构；
- 不使用测试集调阈值；
- 不直接使用测量 VDD 作为输入。

原因：实时电压保护路径必须优先保证固定低延迟，神经网络只作为后续复核和复杂模式分析。

---

# 3. 输入与基准冻结

## Step 3.1 冻结数据合同

复用：

```
runs/formal_v1_20260727_r1/
```

必须读取：

- trace-level split；
- base_waveform_id 分组；
- causal window；
- sensor_code；
- bubble_count；
- code_valid；
- target label。

禁止：

- 随机重新切窗划分 train/test；
- 使用未来采样点；
- 使用 measured_vdd；
- 使用 configured_droop。

---

## Step 3.2 冻结 CNN baseline

CNN作为性能参考，不参与重新优化。

记录：

```
model config SHA
checkpoint SHA
window length
normalizer
threshold
```

CNN必须通过统一接口接入：

```
reset()
step(sensor_window)
output(alarm)
```

输出：

```
CNN_BASELINE_REPORT.json
```

---

# 4. 建立统一检测接口

新增：

```
fast_detection/
    detector_base.py
    dataset_adapter.py
    evaluate_detector.py
```

接口：

```python
state = detector.reset(metadata)
alarm = detector.step(sensor_code, valid)
```

所有算法必须支持：

- 单样本在线输入；
- 不访问未来数据；
- 保存内部状态；
- 输出首次告警时间。

---

# 5. 第一轮：无学习基线

目标：判断简单统计量是否已经足够。

## Step 5.1 单阈值

实现：

```
sensor_code >= threshold
```

搜索：

```
threshold = 1..32
```

输出：

- Recall
- FAR
- TTD

---

## Step 5.2 阈值+持续确认

实现：

```
if code > threshold:
    counter++
else:
    counter=0

alarm when counter >= K
```

搜索：

```
K={1,2,3,4,8}
```

---

## Step 5.3 幅值+斜率

特征：

```
e = code-baseline
d = code[k]-code[k-1]
```

规则：

```
e>T1 AND d>T2
```

搜索整数阈值。

---

# 6. 第二轮：统计检测算法

## Step 6.1 EWMA基线

实现：

```
b[k]=b[k-1]+(x[k]-b[k-1])/2^q
```

搜索：

```
q={3,4,5,6}
```

输出：

- baseline drift
- false alarm
- detection delay

---

## Step 6.2 CUSUM

实现：

```
S=max(0,S+e-v)
```

搜索：

```
v
H
```

要求：

- 纯整数实现；
- 无乘法器。

---

## Step 6.3 多统计量 FSM

最终重点候选。

输入：

```
residual
slope
acceleration
CUSUM
threshold_count
```

状态：

```
SAFE
SUSPECT
WARNING
CRITICAL
RECOVERY
```

要求：

- 明确状态转移表；
- 可直接转换 RTL；
- 固定周期响应。

---

# 7. 第三轮：轻量学习算法

目的：判断是否存在简单非线性关系。

## Step 7.1 整数评分卡

训练：

logistic regression

特征：

```
residual
slope
CUSUM
max residual
threshold count
```

限制：

- 权重 INT8；
- 优先使用移位加法；
- 不使用 sigmoid。

---

## Step 7.2 浅层决策树

限制：

```
depth <= 4
leaf <= 16
```

输出必须可以转换为：

```
comparator tree + FSM
```

---

# 8. 统一评价体系

## 8.1 窗口级

报告：

- Accuracy
- Balanced Accuracy
- Macro-F1
- MCC
- Critical Recall
- Safe FAR

---

## 8.2 事件级（主要指标）

报告：

### Event Recall

```
detected_events / total_events
```

### Detection Delay

```
first_alarm_time - event_start_time
```

报告：

- median
- p95
- maximum

### False Alarm

报告：

- false alarms / trace
- safe window FAR
- alarm occupancy

---

# 9. 阈值搜索规则

所有参数选择：

```
train
  |
validation
  |
freeze
  |
test once
```

禁止：

- 根据测试结果重新调阈值；
- 选择最佳单条波形结果；
- 选择最佳seed结果。

选择原则：

优先固定 FAR 下最大 Event Recall。

---

# 10. 硬件成本估计

每个候选记录：

```
add/sub count
compare count
multiplier count
state bits
memory bits
cycles/sample
```

重点比较：

```
CNN
vs
CUSUM
vs
FSM
vs
Scorecard
```

---

# 11. 阶段验收门槛

进入 RTL 阶段前必须完成：

## 算法门槛

- 至少完成 8 种 detector；
- 完成 CNN 对比；
- 完成事件级评价；
- 完成阈值冻结。

## 性能门槛

候选算法应满足：

```
Event Recall 接近 CNN
且
TTD 显著低于 CNN
```

允许存在小幅性能损失，但必须由：

- 延迟优势；
- 面积优势；
- 功耗优势

补偿。

## 工程门槛

最终选择：

```
Top-2 fast detector candidates
```

进入 RTL 微架构设计。

---

# 12. 最终产物

生成：

```
artifacts/
    detector_candidates.json
    detector_search_results.csv
    frozen_detector_config.json

reports/
    FAST_DETECTION_STAGE1_REPORT.md
    CNN_VS_FAST_DETECTOR_COMPARISON.md

plots/
    recall_vs_latency.png
    recall_vs_area.png
    far_vs_recall.png
```

完成后进入：

```
Stage 2:
Fast detector RTL microarchitecture
```
