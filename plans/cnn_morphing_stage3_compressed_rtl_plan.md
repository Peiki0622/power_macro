# 阶段 3：压缩 CNN RTL 原型实现计划

## 目标

实现基于 `[18,8,18]` W8/A8 模型的新 CNN RTL 原型。

本阶段只实现：

```text
compressed CNN inference
```

不实现：

- 功能等价变体；
- 通道置换；
- lane 置换；
- PRNG；
- 侧信道防护。

原因：必须先得到一个正确、低周期、可综合的基础 CNN。

---

# 执行步骤

## Step 3.1 创建新的 RTL 边界

不要直接修改旧：

```text
rtl/cnn_monitor/
```

建议建立：

```text
rtl/cnn_monitor_compressed/
```

包含：

```text
rtl/
tb/
scripts/
config/
```

旧 RTL 仅作为接口和测试参考。

---

## Step 3.2 生成新的权重和参数存储

根据阶段 0 W8/A8 package 重新生成：

```text
Conv1 weights
Conv2 weights
Conv3 weights
bias
requant parameters
classifier weights
```

禁止直接使用旧 18/18/18 ROM。

所有存储必须有：

- shape；
- flatten order；
- bit width；
- SHA256。

---

## Step 3.3 实现卷积计算核心

根据阶段 1 选择的微架构实现：

包括：

```text
MAC array
activation buffer
weight access
accumulator
requantize
ReLU
```

要求：

- 固定调度；
- 无数据相关状态跳转；
- 无 early exit；
- 无动态 latency。

---

## Step 3.4 实现 feature storage

实现：

```text
Conv1 feature storage
Conv2 feature storage
Conv3 feature storage
```

要求：

- 地址规则明确；
- 不产生 bank conflict；
- 与 bittrue reference 地址对应。

---

## Step 3.5 实现多统计量池化

保持：

```text
Average
Maximum
Endpoint
```

禁止删除任意分支。

输出顺序固定：

```text
average[0:18]
maximum[18:36]
endpoint[36:54]
```

---

## Step 3.6 实现分类头

实现：

```text
54 feature
-> binary classifier
-> Safe/Critical logits
```

要求：

- 与整数 reference 一致；
- tie = Safe；
- 输出格式固定。

---

## Step 3.7 建立 RTL 验证环境

必须包含：

### 单窗口测试

比较：

```text
RTL
vs
bittrue reference
```

### 连续流测试

模拟：

```text
sensor_code stream
window update
inference request
result
```

### 边界测试

包括：

- 全 0；
- 全 32；
- 随机窗口；
- Safe；
- Critical。

---

## Step 3.8 周期和综合报告

输出：

```text
reports/CNN_COMPRESSED_RTL_REPORT.md
artifacts/cnn_compressed_rtl_manifest.json
```

包含：

- latency；
- II；
- MAC utilization；
- area；
- timing；
- power estimate；
- RTL SHA256。

---

# 禁止事项

本阶段禁止：

- PRNG；
- variant descriptor；
- channel permutation；
- accumulation permutation；
- lane permutation；
- dummy workload；
- 电荷整形。

---

# 阶段门禁

进入下一阶段前必须满足：

1. RTL 输出与 bittrue reference 完全一致；
2. latency 固定；
3. II 固定；
4. synthesis 可以通过；
5. 新 ROM 和新权重包完整；
6. 不依赖旧 `[18,18,18]` RTL；
7. 无数据相关控制路径。

完成后，才允许进入“功能等价 CNN 执行变体”。
