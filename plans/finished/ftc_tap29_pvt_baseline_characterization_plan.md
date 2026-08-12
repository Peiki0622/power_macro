# FTC tap29 真实 XOR 脉宽 PVT 前置表征计划

## 0. 任务定位

本任务是后续“自校准可编程脉宽窗 FTC”之前的**共同前置实验**。

当前仓库已经完成并确认：

```text
SMIC40LL
4 RVT initial stages / 0 LVT initial stages
30 observable stages
full 30-real-XOR bank
measured tap = 29
XOR = XOR2_X0P5M_A9TR40
TT / 25 C
VDD = 0.75--1.10 V, 10 mV step
```

当前真实 XOR 输出脉宽 `W_real` 在 36 个 VDD 点上全部有效并严格单调，已经判定 GO。

本阶段**不再验证 VDD 映射本身**，也不设计新的 detector。

唯一目标是建立：

```text
W_real(VDD, Temperature, Process)
```

的最小、可审查物理证据，从而定量回答：

> **当前 tap29 脉宽在正常工艺/温度变化下会漂移多少，这种漂移与 50 mV、100 mV 等 VDD 变化引起的脉宽变化相比处于什么量级；固定 TT/25 C Golden Model 是否会产生不可忽略的基线误差。**

该结果只为下一阶段的 self-calibration / programmable timing reference 提供输入。

不要在本任务中实现 self-calibration、CDL、FSM 或任何补偿电路。

---

# 1. 必须复用已有结果，禁止重复仿真

Codex 开始前先读取：

```text
delay_chain/ftc/ftc_config.json
delay_chain/ftc/discovery/selected_cells.json
delay_chain/ftc/scripts/generate_ftc_deck.py
delay_chain/ftc/scripts/run_real_xor_pulse_width.py
delay_chain/ftc/analysis/real_xor_pulse_width/fine.csv
delay_chain/ftc/analysis/real_xor_pulse_width/summary.json
delay_chain/ftc/reports/FTC_REAL_XOR_PULSE_WIDTH_VALIDATION.md
```

已有 TT / 25 C 的 36 点 `fine.csv` 是本任务的正式 nominal baseline。

### 绝对禁止重跑

以下任何 `(corner=tt, temperature=25 C, VDD=0.75--1.10 V)` 已存在点都不得重新运行 HSPICE：

```text
1.10, 1.09, ..., 0.75 V
```

特别是本计划后面用到的：

```text
TT / 25 C / 1.10 V
TT / 25 C / 0.90 V
TT / 25 C / 0.75 V
```

必须直接从已有 `fine.csv` 读取。

不要重新运行：

```text
FTC reproduction
30-tap proxy analysis
real-XOR 5-anchor validation
real-XOR 36-point fine validation
phase-diverse experiments
pipelined-wavefront experiments
旧 glitch experiments
```

---

# 2. 冻结物理拓扑

整个 PVT 前置实验必须保持当前真实 XOR 验证的物理结构：

```text
RVT delay cell      = BUF_X0P7M_A9TR40
LVT delay cell      = BUF_X0P7M_A9TL40
XOR cell            = XOR2_X0P5M_A9TR40
RVT initial stages  = 4
LVT initial stages  = 0
observable stages   = 30
measured output     = xor_29
source              = existing isolated rising launch
tran max step       = 1 ps
full XOR bank       = retained
```

不要：

```text
改 tap
改 cell
改 drive strength
改 chain length
删掉其他 29 个 XOR
改 launch/capture operating point
加 reference rail
```

本阶段的新变量只有：

```text
process corner
temperature
VDD anchor
```

---

# 3. Step 1 — 先发现 PDK 真实 process corner，不猜名字

当前 `ftc_config.json` 已给出实际 model library 路径，并使用：

```text
.lib <model_library> tt
```

Codex 首先在仿真主机上**只读取 model library 文本**，列出其中供当前 core MOS/model 使用的实际 process `.lib` section。

不得直接假设一定存在：

```text
ff
ss
fs
sf
```

必须以 PDK 文件实际 section 为准。

生成：

```text
delay_chain/ftc/analysis/real_xor_pvt_baseline/process_corners.json
```

至少记录：

```text
model_library
nominal_corner
available_process_corners
selected_process_corners_for_screen
```

### 选择原则

第一轮 process screen 使用：

```text
所有明确属于 core process variation 的可用 corner
```

数量通常很小，不需要人为再构造 synthetic corner。

不要加入：

```text
Monte Carlo
local mismatch
statistical section
IO-only corner
memory-only corner
```

如果 PDK 文件本身没有可用的非 TT process corner，不要编造 corner；报告这一事实，继续完成 temperature 部分即可。

这一步不运行 HSPICE。

---

# 4. Step 2 — 新建任务专用最小 PVT runner

新增建议：

```text
delay_chain/ftc/scripts/run_real_xor_pvt_baseline.py
```

不要修改 `run_real_xor_pulse_width.py` 中已经完成并冻结的 TT/25 C 验证逻辑。

新 runner 只负责：

```text
1. 读取现有 config/cells；
2. 读取已有 TT/25 C fine.csv；
3. 在内存中的 scenario config 覆盖 corner / temperature；
4. 复用现有 generate_ftc_deck.py 和 HSPICE helper；
5. 使用现有 pulse_width_taps=[29] 真实 XOR measure；
6. 对新 PVT 点运行 HSPICE；
7. 写 compact CSV/JSON 和报告。
```

不得修改正式：

```text
ftc_config.json
selected_operating_point
```

每次 scenario 只在内存副本中改变：

```text
corner
temperature_c
vdd_v
```

---

# 5. Step 3 — 建立 scenario manifest，先防止重复运行

在真正运行前先生成：

```text
delay_chain/ftc/analysis/real_xor_pvt_baseline/scenario_manifest.csv
```

字段至少包括：

```text
scenario_id
vdd_v
corner
temperature_c
source
needs_hspice
```

其中：

```text
source = reused_tt25_fine
```

或：

```text
source = new_pvt_hspice
```

### 必须 deduplicate

任何：

```text
corner=tt
temperature=25 C
```

的 VDD 点都必须：

```text
needs_hspice = 0
```

并从已有 `fine.csv` 导入。

不要因为 runner 使用了不同输出目录而重跑 nominal evidence。

---

# 6. Step 4 — Process-only screen：只在 25 C 测三个 VDD anchor

目的不是做完整 PVT，而是先找出哪些真实 process corner 构成 tap29 脉宽的上下包络。

VDD 只取：

```text
1.10 V
0.90 V
0.75 V
```

Temperature 固定：

```text
25 C
```

对于每个实际 process corner，测：

```text
W_real_ps
W_proxy_ps
width_ratio
xor29_peak_ratio
valid
```

TT 三个点直接复用旧数据，不运行 HSPICE。

输出：

```text
delay_chain/ftc/analysis/real_xor_pvt_baseline/process_screen.csv
```

## 6.1 只做简单 envelope 筛选

对每个 VDD anchor 找：

```text
corner_min_width
corner_max_width
```

最终下一阶段的 process 集合定义为：

```text
TT
+
三个 VDD anchor 上实际出现过的 min/max width corner 的并集
```

不要使用复杂 score。

不要为了“覆盖更多”把所有 corner 自动带入后续完整温度矩阵；只有实际形成上下包络的 corner 才继续。

如果不同 VDD 下 envelope corner 不同，保留它们即可，不强行假定一个 universal fast/slow corner。

---

# 7. Step 5 — Temperature-only screen：TT 下观察温度行为

固定：

```text
corner = TT
```

VDD：

```text
1.10 V
0.90 V
0.75 V
```

Temperature：

```text
-40 C
25 C
85 C
125 C
```

其中 25 C 三点复用旧数据。

新 HSPICE 只跑：

```text
3 VDD x 3 new temperatures = 9 scenarios
```

输出：

```text
delay_chain/ftc/analysis/real_xor_pvt_baseline/temperature_screen.csv
```

重点只回答：

```text
W_real 随温度改变多少？
温度方向是否在不同 VDD 下相同？
是否出现明显 non-monotonic / temperature inversion 行为？
所有真实 XOR pulse 是否仍完整？
```

不要在本阶段建立温度补偿公式。

---

# 8. Step 6 — 只对包络 process corner 做最小 PVT matrix

只有 Step 4/5 数据有效后执行。

Process：

```text
TT + Step 4 实际 envelope corners
```

VDD：

```text
1.10 V
0.90 V
0.75 V
```

Temperature：

```text
-40 C
25 C
85 C
125 C
```

再次强调：已经存在于 process screen、temperature screen、TT/25 C fine 数据中的 scenario **全部复用**。

runner 只执行缺失组合。

输出总表：

```text
delay_chain/ftc/analysis/real_xor_pvt_baseline/pvt_matrix.csv
```

每一行至少包含：

```text
vdd_v
corner
temperature_c
W_real_ps
W_proxy_ps
width_ratio
xor29_peak_ratio
valid
source
```

本阶段不做：

```text
36 VDD points x PVT
```

三个电压 anchor 已足够回答前置问题。

---

# 9. Step 7 — 定量拆分 process、temperature、combined PVT 偏移

以已有：

```text
TT / 25 C
```

作为**分析参考**，不是新的 detector Golden Model。

对每个 VDD anchor 计算：

```text
W_nominal_ps
```

## 9.1 process-only offset

25 C 下：

```text
process_offset_ps = W_real(corner,25C) - W_real(TT,25C)
```

输出：

```text
min_process_offset_ps
max_process_offset_ps
process_span_ps
```

## 9.2 temperature-only offset

TT 下：

```text
temperature_offset_ps = W_real(TT,T) - W_real(TT,25C)
```

输出：

```text
min_temperature_offset_ps
max_temperature_offset_ps
temperature_span_ps
```

## 9.3 combined PVT envelope

对选定 P/T matrix：

```text
pvt_min_width_ps
pvt_max_width_ps
pvt_span_ps
```

不要做方差模型，不要假设 process 与 temperature 独立，也不要做 RSS 合成。

直接使用真实仿真 envelope。

---

# 10. Step 8 — 与已有 VDD sensitivity 做量级比较，不新增 voltage sweep

这个步骤必须**完全使用现有 TT/25 C 36-point fine.csv**。

不要为 50 mV / 100 mV comparison 重新跑任何 HSPICE。

对于 `VDD0=1.10 V`，从已有 fine 数据读取：

```text
DeltaW_50mV  = W(1.05) - W(1.10)
DeltaW_100mV = W(1.00) - W(1.10)
DeltaW_200mV = W(0.90) - W(1.10)
```

对于 `VDD0=0.90 V`：

```text
DeltaW_50mV  = W(0.85) - W(0.90)
DeltaW_100mV = W(0.80) - W(0.90)
DeltaW_150mV = W(0.75) - W(0.90)
```

`0.75 V` 是当前正式下限，只用于 PVT pulse validity 和 spread，不向下扩展攻击电压。

计算简单比值：

```text
pvt_span_to_50mV_shift
pvt_span_to_100mV_shift
```

这些比值只用于回答：

> **正常 PVT 漂移与目标 VDD-induced width movement 是否处于相同量级。**

不要把它称为最终 detection SNR，也不要据此宣称最终 50 mV attack coverage。

---

# 11. Step 9 — 计算“固定 TT/25 C Golden Model 等效 VDD 误差”

为了把 Golden Model 问题表达得更直接，可以利用已有严格单调的 36-point：

```text
TT/25 C W_real(VDD)
```

作为一条只用于分析的 monotonic lookup curve。

对于每个 PVT scenario 的：

```text
W_real(Vactual,P,T)
```

在 TT/25 C fine curve 中做简单 piecewise-linear inverse mapping，得到：

```text
V_equiv_golden
```

并计算：

```text
golden_equivalent_error_mV
    = (V_equiv_golden - Vactual) * 1000
```

如果 PVT width 超出 TT/25 C curve 范围，直接标记：

```text
out_of_nominal_curve
```

不要外推。

这个量的物理意义是：

> **如果错误地把一颗处于不同 P/T 条件的芯片强行套入 TT/25 C Golden Model，它会被误认为偏移了多少 mV。**

这不是最终校准算法，只是量化 Golden Model 的偏差。

---

# 12. Step 10 — 只生成三类核心结果图

不要大量出图。

## 图 1：TT/25 C fine curve + PVT envelope

```text
x = VDD
y = W_real_ps
```

画：

```text
已有 TT/25 C 36-point curve
三个 VDD anchor 的 PVT min/max envelope
```

输出：

```text
fig1_pvt_envelope_vs_nominal.svg
```

## 图 2：P/T spread 与 VDD-induced movement 比较

对 1.10 V、0.90 V 分别比较：

```text
process span
temperature span
combined PVT span
50 mV shift
100 mV shift
```

输出：

```text
fig2_pvt_spread_vs_vdd_shift.svg
```

## 图 3：Golden-equivalent VDD error

按：

```text
corner / temperature / VDD anchor
```

展示：

```text
golden_equivalent_error_mV
```

输出：

```text
fig3_golden_equivalent_error.svg
```

不要加入复杂统计分布拟合。

---

# 13. Step 11 — 最终报告只回答四个问题

生成：

```text
delay_chain/ftc/reports/FTC_TAP29_PVT_BASELINE_CHARACTERIZATION.md
```

报告必须围绕以下四个问题组织。

## Q1. Process variation 有多大？

给：

```text
process corner
W_real at 1.10/0.90/0.75 V
process span
```

## Q2. Temperature variation 有多大？

给：

```text
-40 / 25 / 85 / 125 C
三个 VDD anchor 的 W_real
是否有 temperature inversion / non-monotonic behavior
```

## Q3. PVT spread 与 voltage sensitivity 相比是什么量级？

必须直接比较：

```text
PVT span
vs
50 mV VDD-induced width movement
vs
100 mV VDD-induced width movement
```

## Q4. 固定 TT/25 C Golden Model 会产生多大等效 VDD 偏差？

报告：

```text
max |golden_equivalent_error_mV|
median |golden_equivalent_error_mV|
worst scenario
```

结论必须基于测量数据，不提前给 self-calibration 算法性能。

---

# 14. 本任务的结论格式

本阶段不对“最终 FTC sensor”做 GO/NO-GO。

只给一个面向下一阶段的研究结论：

```text
PVT_IMPACT = SMALL / NON_NEGLIGIBLE / DOMINANT
```

但不要使用拍脑袋百分比阈值来分类。

分类依据必须在报告中写成**实际量级关系**，例如：

```text
combined PVT span < 50 mV width shift
```

或：

```text
combined PVT span is between 50 mV and 100 mV width shifts
```

或：

```text
combined PVT span > 100 mV width shift
```

再据此解释：

```text
固定 Golden Model 是否足够稳健；
self-calibration / programmable reference 是否有明确必要性。
```

不要在本任务中声称自校准已经解决了 PVT。

---

# 15. 最小代码与文件组织

建议新增：

```text
delay_chain/ftc/scripts/run_real_xor_pvt_baseline.py

delay_chain/ftc/analysis/real_xor_pvt_baseline/process_corners.json
delay_chain/ftc/analysis/real_xor_pvt_baseline/scenario_manifest.csv
delay_chain/ftc/analysis/real_xor_pvt_baseline/process_screen.csv
delay_chain/ftc/analysis/real_xor_pvt_baseline/temperature_screen.csv
delay_chain/ftc/analysis/real_xor_pvt_baseline/pvt_matrix.csv
delay_chain/ftc/analysis/real_xor_pvt_baseline/summary.json
delay_chain/ftc/analysis/real_xor_pvt_baseline/fig1_pvt_envelope_vs_nominal.svg
delay_chain/ftc/analysis/real_xor_pvt_baseline/fig2_pvt_spread_vs_vdd_shift.svg
delay_chain/ftc/analysis/real_xor_pvt_baseline/fig3_golden_equivalent_error.svg

delay_chain/ftc/reports/FTC_TAP29_PVT_BASELINE_CHARACTERIZATION.md

delay_chain/ftc/tests/test_real_xor_pvt_baseline.py
```

原始 HSPICE deck/listing/database 放：

```text
delay_chain/ftc/runs/real_xor_pvt_baseline/
```

保持 ignored。

compact analysis evidence 放 `analysis/` 并提交。

---

# 16. 最小测试要求

只做本任务相关测试。

至少检查：

```text
1. TT/25 C existing fine rows 被标记为 reused，不进入 HSPICE queue；
2. process corner 名称来自真实 model library，不是 hard-code ff/ss；
3. scenario dedup 正确；
4. tap29/full-XOR topology 没有改变；
5. PVT offset/span 算术正确；
6. 50/100 mV comparison 从已有 fine.csv 读取，不触发新 HSPICE；
7. golden inverse mapping 对 synthetic monotonic curve 正确；
8. 超出 nominal curve 时标记 out_of_nominal_curve，不外推。
```

只运行：

```text
本任务 unit test
py_compile
本任务确实缺失的新 PVT HSPICE scenarios
```

不要运行完整旧 regression。

---

# 17. 明确禁止的过度设计

本阶段不要实现或探索：

```text
Configurable Delay Line (CDL)
coarse/medium/fine delay architecture
RO / counter
self-calibration FSM
programmable acceptance window
reference cell screening
sensitivity-contrast reference
Temporal Majority Voting
security-aware tracking
Configuration Skip
DVFS integration
Sticky Alarm
CUSUM
TDC
P&R
post-layout extraction
Monte Carlo
30-tap PVT sweep
36-point VDD x PVT full grid
voltage glitch transient campaign
dynamic temperature ramp
```

也不要修改当前 sensor topology 来“改善 PVT”。

这个阶段只负责把问题测清楚。

---

# 18. Codex 最终必须回答的一句话

> **在当前已验证的 tap29 真实 XOR 脉宽传感前端中，正常 process/temperature variation 会造成多大的 `W_real` 基线漂移；这个漂移相对于 50 mV、100 mV VDD 变化的脉宽特征是否足以使固定 TT/25 C Golden Model 失去可靠性，从而为下一阶段自校准可编程时间参考提供定量设计依据？**
