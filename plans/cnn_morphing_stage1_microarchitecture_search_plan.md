# 阶段 1：压缩 CNN 低周期微架构搜索计划

## 目标

在不修改模型、不修改 W8/A8 数值合同的前提下，确定新的 CNN 硬件数据流结构。

本阶段只回答：

> `[18,8,18]` CNN 应该采用多少 MAC 并行、多少权重 bank、多少位置并行，才能满足周期目标？

不实现 RTL，不实现功能等价变体，不加入 PRNG。

---

## 当前输入

固定使用阶段 0 输出：

```text
channels = [18,8,18]
kernel = [5,5,5]
window = 32
W8/A8
pooling = average + maximum + endpoint
```

当前旧 RTL 周期不能直接继承。旧实现面向 `[18,18,18]`，采用固定 16-lane 调度，12892 cycles latency 和 12893 cycles II。该数据只作为 baseline，不作为新设计约束。

---

# 执行步骤

## Step 1.1 建立周期模型

新增软件周期估算器。

输入：

```text
MAC 数量
输出通道并行度
位置并行度
fan-in并行度
weight bank数量
ROM latency
requant pipeline
writeback bandwidth
```

输出：

```text
Conv1 cycles
Conv2 cycles
Conv3 cycles
pool cycles
classifier cycles
total latency
II
MAC utilization
memory bandwidth
```

周期模型必须与后续 RTL 调度一一对应。

---

## Step 1.2 分析增量计算可行性

比较两种模式：

### 模式 A：完整窗口计算

每次重新计算完整 L32。

### 模式 B：滑动窗口增量计算

新 sensor_code 到来后，只更新受影响位置。

Codex 需要建立 bit-true 位置依赖分析，确认：

- Conv1 受影响位置；
- Conv2 受影响位置；
- Conv3 受影响位置；
- pooling 更新成本。

不能直接假设增量一定正确。

---

## Step 1.3 搜索 MAC 配置

至少评估：

```text
16 MAC
32 MAC
64 MAC
128 MAC
```

每种配置评估：

```text
output channel parallel
position parallel
fan-in parallel
```

目标不是最大并行，而是在面积、功耗和周期之间取得平衡。

---

## Step 1.4 重新规划权重存储

旧 ROM 结构不能直接复用。

设计新的：

```text
weight bank
bias storage
requant parameter storage
classifier weight storage
```

评估：

- 单 bank；
- 多 bank；
- 并行读取宽度。

---

## Step 1.5 选择正式微架构

生成：

```text
artifacts/cnn_microarchitecture_candidates.json
artifacts/cnn_microarchitecture_selected.json
reports/CNN_MICROARCHITECTURE_SEARCH.md
```

报告必须说明：

- 为什么选择该 MAC 数；
- latency；
- II；
- 预计面积；
- 预计存储需求。

---

## 禁止事项

本阶段禁止：

- 写新的 CNN RTL；
- 加入 channel permutation；
- 加入 lane permutation；
- 加入 PRNG；
- 修改模型结构；
- 删除 pooling 分支；
- 修改量化。

---

## 阶段门禁

进入阶段 2 前必须完成：

- 周期模型可运行；
- 至少比较两种数据流；
- 选定 MAC 并行度；
- 选定权重存储方案；
- latency 和 II 有明确目标；
- 所有选择均来自模型合同，而不是手工猜测。
