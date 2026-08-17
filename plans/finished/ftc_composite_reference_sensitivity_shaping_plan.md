# FTC Composite Reference Sensitivity-Shaping 窄实验计划

## 0. 任务目标

上一阶段 `Sensitivity Contrast Reference Path` 的结论是 `CONDITIONAL`：

- simple reference 在 TT 下保留了明显的 VDD contrast；
- 但 `buf_lvt / inv_lvt / nand2_lvt` 等 finalist 在 FF/TT/SS 下不能稳定降低 tap29 的 temperature residual；
- 上一阶段因为 TT 已经存在 simple finalist，代码没有真正执行 composite reference，因此“多个标准单元组成一个整体 reference unit”仍未被物理验证。

本任务只补这一件事：

> **尝试用极小规模 RVT/LVT 组合 reference macro-unit 做灵敏度塑形，看能否同时降低温度 residual 并保留 VDD residual。**

本任务结束后必须把“被动 sensitivity-contrast reference”路线收口为：

```text
GO
或
NO-GO
```

不要再次输出一个需要继续扩大搜索的 CONDITIONAL。

---

## 1. 只读已有证据，禁止复跑旧结果

先读取：

```text
delay_chain/ftc/analysis/reference_sensitivity_contrast/simple_candidate_screen.csv
delay_chain/ftc/analysis/reference_sensitivity_contrast/finalist_pvt_confirmation.csv
delay_chain/ftc/analysis/reference_sensitivity_contrast/summary.json
delay_chain/ftc/reports/FTC_REFERENCE_SENSITIVITY_CONTRAST_FEASIBILITY.md
delay_chain/ftc/analysis/real_xor_pulse_width/fine.csv
delay_chain/ftc/analysis/real_xor_pvt_baseline/temperature_screen.csv
delay_chain/ftc/analysis/real_xor_pvt_baseline/pvt_matrix.csv
```

不要重新运行：

```text
tap29 sensor
real-XOR VDD sweep
PVT baseline
10 个 simple reference candidate
上一阶段 finalist PVT confirmation
任何旧 FTC / phase / wavefront / glitch 实验
```

本任务的新 HSPICE 只能用于**最终选中的 composite macro-unit**。

---

## 2. Step 1 — 用已有数据做一次正确的 composite 预测

不要沿用上一版脚本里“把两个 parent residual 直接相加”的预测方式。

对 simple candidate A/B，先从现有 `simple_candidate_screen.csv` 和已有 sensor 数据恢复各自相对 nominal 的 reference delay movement：

```text
DeltaD_A = (DeltaW_S - E_A) / k_A
DeltaD_B = (DeltaW_S - E_B) / k_B
```

其中已有 row 已提供：

```text
D_R(25C)
k
E_T(-40C)
E_T(125C)
E_V(50mV)
E_V(100mV)
```

然后对一个 composite：

```text
D_C = nA * D_A + nB * D_B
```

必须重新计算 composite 自己的：

```text
k_C(V0) = W_S(V0,25C) / D_C(V0,25C)
```

再计算：

```text
E_T,C = DeltaW_S - k_C * DeltaD_C
E_V,C = DeltaW_S - k_C * DeltaD_C

M_50,C  = |E_V,C(50mV)|  - max|E_T,C|
M_100,C = |E_V,C(100mV)| - max|E_T,C|
```

### 搜索空间保持很小

只考虑：

```text
1 个 RVT simple unit + 1 个 LVT simple unit
```

以及三个小整数比例：

```text
1:1
1:2
2:1
```

但最终 composite 的实际标准单元总数必须 `<= 4`；超过直接丢弃。

不考虑：

```text
三个以上不同 family
任意长链
全排列搜索
机器学习/优化器
模拟器内参数扫权重
```

### TT 预测 shortlist 条件

在：

```text
V0 = 1.10 V
V0 = 0.90 V
```

都必须满足：

```text
max|E_T,C| < raw sensor temperature movement
M_100,C > 0
```

优先选择同时：

```text
M_50,C > 0
```

的组合。

最多保留 **3 个** composite candidate。

如果一个都没有：

```text
Passive composite sensitivity shaping = NO-GO
```

直接结束，不运行新 HSPICE。

输出：

```text
delay_chain/ftc/analysis/composite_reference_shaping/predicted_candidates.csv
```

---

## 3. Step 2 — 只对 shortlist 做真实 composite HSPICE

为最多 3 个 candidate 建立真实 macro-unit，例如：

```text
macro = [RVT unit] + [LVT unit]
```

或对应 1:2 / 2:1 的合法小组合。

整体必须保持：

```text
1 input / 1 output
combinational
non-inverting
无反馈
可重复级联
```

仍使用三份 macro-unit 串联：

```text
macro0 -> macro1 -> macro2
```

测中间 `macro1` 的整体传播延迟。

### 先只跑 TT 验证点

```text
VDD = 1.10, 1.05, 1.00, 0.90, 0.85, 0.80 V
T   = -40, 25, 125 C
```

只运行实际计算 `E_T / E_V` 所需的组合，不做矩形过扫。

用真实 composite delay 重新计算：

```text
k_C
E_T,C
E_V,C
M_50,C
M_100,C
```

如果真实 HSPICE 后 candidate 不再满足：

```text
温度 residual 在 1.10/0.90 V 都低于 raw sensor
AND
M_100 > 0 @ 1.10/0.90 V
```

则淘汰。

如果没有 candidate 留下：

```text
Passive composite sensitivity shaping = NO-GO
```

结束，不继续扩大组合。

输出：

```text
delay_chain/ftc/analysis/composite_reference_shaping/measured_tt.csv
```

---

## 4. Step 3 — 对最终 1--2 个 candidate 做最小 PVT confirmation

最多保留 2 个 TT 通过者。

Sensor 全部复用已有 `pvt_matrix.csv`，不重跑。

Reference-only 新 HSPICE：

```text
P = TT, FF, SS
V = 1.10, 0.90 V
T = -40, 25, 85, 125 C
```

对每个 `(P,V0)` 单独做本地校准等效分析：

```text
k_C(P,V0) = W_S(P,V0,25C) / D_C(P,V0,25C)
```

然后比较：

```text
composite temperature residual
vs
raw sensor temperature movement
```

同时利用 25 C 的 `1.10 -> 0.90 V` 数据确认 calibrated VDD residual 仍非零。

输出：

```text
delay_chain/ftc/analysis/composite_reference_shaping/pvt_confirmation.csv
```

---

## 5. 最终判定并结束

### GO

至少一个 composite 在：

```text
P = TT, FF, SS
V0 = 1.10, 0.90 V
```

全部满足：

```text
1. per-process calibration 后的 temperature residual
   < 同条件 raw sensor temperature movement

2. 1.10 -> 0.90 V calibrated residual != 0
```

并且 TT 下：

```text
M_100 > 0 @ 1.10 V
M_100 > 0 @ 0.90 V
```

则：

```text
Composite Sensitivity Contrast Reference = GO
```

下一阶段才进入最小可编程参考延迟线。

### NO-GO

如果上述条件不能同时满足：

```text
Passive Sensitivity-Contrast Reference = NO-GO
```

不要继续增加 cell 数量或搜索复杂结构。

后续 architecture 改为：

```text
reference 只负责 programmable timing threshold
+
self-calibration
+
security-aware slow tracking 负责 temperature/aging
```

本任务到此结束。

---

## 6. 最小结果文件

只需要提交：

```text
delay_chain/ftc/analysis/composite_reference_shaping/predicted_candidates.csv
delay_chain/ftc/analysis/composite_reference_shaping/measured_tt.csv          # 若进入 HSPICE
delay_chain/ftc/analysis/composite_reference_shaping/pvt_confirmation.csv     # 若进入 PVT confirmation
delay_chain/ftc/analysis/composite_reference_shaping/summary.json
delay_chain/ftc/reports/FTC_COMPOSITE_REFERENCE_SENSITIVITY_SHAPING.md
```

报告只回答三个问题：

1. 正确的 composite scaling 后，是否存在预测可行组合？
2. 真实 composite HSPICE 是否保留这种温度/VDD 可分性？
3. 这条 passive reference 路线最终是 GO 还是 NO-GO，下一阶段进入哪里？

不要在本任务中实现：

```text
CDL
bypass MUX
thermometer code
self-calibration FSM
acceptance window
tracking FSM
P&R
DVFS
CUSUM
```
