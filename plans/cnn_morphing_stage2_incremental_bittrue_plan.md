# 阶段 2：低周期 CNN 增量 bit-true 参考模型计划

## 目标

在 RTL 之前建立新的硬件调度唯一数值真值。

本阶段输出回答：

> 如果 CNN 不再每次完整计算 L32，而采用滚动更新，结果是否与原 W8/A8 reference 完全一致？

---

## 输入

使用：

- 阶段 0 冻结的 W8/A8 package；
- 阶段 1 选择的数据流方案；
- 原 bittrue.py 作为数学 baseline。

---

# 执行步骤

## Step 2.1 建立 rolling window reference

新增独立 Python reference。

功能：

1. 初始化完整 L32；
2. 执行一次 bootstrap inference；
3. 输入新的 sensor_code；
4. 更新循环 buffer；
5. 仅计算设计阶段确定的受影响位置；
6. 输出 Safe/Critical logits。

---

## Step 2.2 验证卷积状态更新

逐层比较：

```text
Conv1 full inference
vs
Conv1 rolling update

Conv2 full inference
vs
Conv2 rolling update

Conv3 full inference
vs
Conv3 rolling update
```

要求：

```text
bit exact
```

禁止使用误差阈值。

---

## Step 2.3 实现增量 pooling

保持三个统计分支：

```text
Average
Maximum
Endpoint
```

要求：

### Average

维护 rolling sum。

### Maximum

维护可验证的数据结构。

不能只保存最大值，因为最大值删除后无法恢复。

### Endpoint

始终对应最新窗口位置。

---

## Step 2.4 建立连续流测试

测试：

- 长随机 sensor_code 流；
- 长稳定 Safe 流；
- 长 Critical 流；
- Safe/Critical 边界变化；
- 0、15、32 极值；
- 连续窗口超过数千次更新。

每次比较：

```text
feature maps
pooling outputs
logits
decision
```

---

## Step 2.5 输出硬件参考合同

生成：

```text
artifacts/cnn_incremental_reference_contract.json
reports/CNN_INCREMENTAL_BITTRUE_REPORT.md
```

记录：

- 更新位置规则；
- 状态存储需求；
- 每步 MAC 数；
- latency 预算；
- golden vectors。

---

## 禁止事项

本阶段禁止：

- RTL 实现；
- PRNG；
- variant_id；
- 通道置换；
- lane 置换；
- 累加顺序随机化。

---

## 阶段门禁

进入阶段 3 前必须满足：

- rolling reference 与完整 reference 全部 bit-exact；
- pooling 三分支完全一致；
- 连续流测试通过；
- 输出硬件状态需求明确。

如果增量结果无法 bit-exact，停止进入 RTL，先修正数学模型。
