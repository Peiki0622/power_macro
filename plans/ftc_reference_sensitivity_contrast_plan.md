# FTC 灵敏度反差参考路径物理可行性计划

## 0. 任务定位与宏观方向

当前 `main` 已经完成两项前置证据：

1. `tap29` 的真实 XOR 高电平脉宽 `W_S = W_real(xor_29)` 对 VDD 具有稳定、单调的电压敏感性；
2. PVT 前置实验已经证明固定 `TT/25 C` Golden Model 的误差与 50--100 mV 级电压变化处于同量级甚至更大，因此后续必须转向**本地自校准 + 可编程时间参考**，而不能继续依赖固定 Golden Model。

本计划只执行下一阶段的第一个物理问题：

> **能否在 SMIC40LL 现有标准单元中找到一个参考延迟路径，使它在本地工作点附近对温度变化尽量跟随 tap29 脉宽，但对 VDD 变化的响应与 tap29 明显不同，从而在相减/比较后抑制温漂而保留 voltage-droop 信息？**

定义：

```text
Sensor timing quantity:
    W_S(V,T,P) = tap29 real-XOR pulse width

Reference timing quantity:
    D_R(V,T,P) = candidate reference-unit propagation delay
```

后续希望使用：

```text
E = W_S - D_R_scaled
```

形成局部差分判决。

### 本阶段不是做什么

本阶段**不是**：

```text
完整 CDL
self-calibration FSM
programmable acceptance window
tracking FSM
CUSUM
DVFS
P&R
configuration skip
最终 detector
```

本阶段只回答：

```text
Reference physical mechanism = GO / CONDITIONAL / NO-GO ?
```

如果这个物理条件不成立，后续 CDL 和自校准不应继续堆叠。

---

# 1. 必须复用已有传感器证据，禁止重跑旧 FTC 仿真

Codex 开始前先读取：

```text
delay_chain/ftc/ftc_config.json
delay_chain/ftc/discovery/selected_cells.json
delay_chain/ftc/scripts/discover_ftc_cells.py
delay_chain/ftc/scripts/run_real_xor_pvt_baseline.py
delay_chain/ftc/analysis/real_xor_pulse_width/fine.csv
delay_chain/ftc/analysis/real_xor_pvt_baseline/process_corners.json
delay_chain/ftc/analysis/real_xor_pvt_baseline/process_screen.csv
delay_chain/ftc/analysis/real_xor_pvt_baseline/temperature_screen.csv
delay_chain/ftc/analysis/real_xor_pvt_baseline/pvt_matrix.csv
delay_chain/ftc/analysis/real_xor_pvt_baseline/summary.json
delay_chain/ftc/reports/FTC_TAP29_PVT_BASELINE_CHARACTERIZATION.md
```

这些文件是本计划的**固定 sensor evidence**。

### 绝对不要重跑

不要重新运行：

```text
real-XOR 36-point VDD sweep
existing PVT sensor campaign
process screen
temperature screen
PVT matrix
phase-diverse
wavefront pipeline
旧 glitch campaign
```

本计划所有新的 HSPICE 只属于：

```text
reference candidate / reference macro-unit
```

不要为了“对齐数据”再次运行 tap29 sensor。

---

# 2. 参考路径的物理要求

未来 reference 必须和 sensor 位于同一电源域，因此本实验所有候选都使用：

```text
VDD = VDD_A
VSS = VSS_A
```

禁止新增：

```text
Vref
独立稳定电源轨
模拟偏置
外部精密时钟作为时间参考
```

参考路径最终要能够成为**可编程延迟线中的一个 delay quantum**。因此候选 `reference unit` 只需要满足：

```text
1 input / 1 output
combinational
无反馈
无状态
固定逻辑功能
整体输入输出同极性（rising input -> rising output）
可以重复级联
以后可以由一个 bypass MUX 整体插入/跳过
```

注意：

> **本阶段不实现 bypass MUX，也不实现完整 programmable line。**

只要候选结构未来可以作为一个被插入/旁路的整体 delay unit 即可。

---

# 3. 单标准单元和组合“大单元”的策略

不要把“reference unit”限制为一个标准单元。

执行顺序必须是：

```text
先筛简单单元
    ↓
若没有合适候选
    ↓
再利用已有单元测量结果构造少量组合 macro-unit
```

## 3.1 第一层：简单候选

从现有 RVT/LVT 标准单元库中发现并验证少量代表性组合逻辑 family，例如：

```text
BUF
INV
MUX
NAND
NOR
```

 exact cell name 必须来自实际 CDL/Verilog，不允许猜名字。

候选数量保持小规模：

- 每个 family / Vt class 优先选择最小驱动单元；
- 如果库命名明确，可额外保留一个相邻 drive strength 用于判断 drive/load 是否显著改变 sensitivity；
- 不遍历所有 drive strength。

其中：

- 单个 `BUF` 或固定数据路径的 `MUX` 可以直接成为 non-inverting reference-unit candidate；
- `INV`、配置成反相器的 `NAND/NOR` 先作为 primitive；若需要作为 reference unit，则使用偶数反相级组成整体 non-inverting macro-unit。

## 3.2 第二层：组合 macro-unit，仅在简单候选不够好时启用

如果没有单个 non-inverting candidate 达到本计划的 GO 条件，允许构造：

```text
2--4 个标准单元串联
```

形成一个整体 reference macro-unit。

允许：

```text
RVT + RVT
LVT + LVT
RVT + LVT
不同逻辑 family 的串联
```

前提仍然是：

```text
整体 1-in / 1-out
整体 non-inverting
无反馈
无状态
可重复级联
```

不要做：

```text
任意图结构搜索
穷举所有排列组合
机器学习搜索
遗传算法
环振荡器
锁相环
模拟 RC
```

组合 candidate 的产生必须**由单元测量数据指导**：

- 若 primitive A 的温度系数偏高、primitive B 偏低，可尝试 A+B；
- 若某 primitive 的 VDD sensitivity 太接近 sensor，则不要继续堆叠同类结构；
- 先用单元延迟相加做简单预测，只 HSPICE 验证少量最有希望的组合。

如果单标准单元已经满足 GO，不要为了追求“更优”自动扩展 composite search。

---

# 4. Step 1 — 新建任务专用 reference candidate discovery

建议新增一个任务专用脚本，例如：

```text
delay_chain/ftc/scripts/run_reference_sensitivity_contrast.py
```

可以复用 `discover_ftc_cells.py` 中的 CDL/Verilog parsing 思路，但不要修改已经完成的 FTC cell discovery 结果。

脚本首先读取：

```text
selected_cells.json
```

获得实际 RVT/LVT CDL 和 Verilog 路径，然后：

1. 解析实际 `.SUBCKT`；
2. 在 vendor functional Verilog 中验证逻辑功能和端口；
3. 生成小规模 primitive/candidate manifest；
4. 记录每个候选的：

```text
candidate_id
vt_class
cell_names
logic_family
stage_count
overall_polarity
cdl_ports
fixed_logic_ties (if any)
source_cdl
```

输出：

```text
delay_chain/ftc/analysis/reference_sensitivity_contrast/candidate_manifest.csv
```

如果 NAND/NOR/MUX 的逻辑 tie 无法从 functional view 明确确认，则直接不选该候选，不要自行猜 pin semantics。

---

# 5. Step 2 — 为 reference unit 建立独立、最小的 HSPICE testbench

不要把 reference candidate 塞进 `generate_ftc_deck.py`，也不要修改已有 sensor deck。

在任务专用 runner 中生成一个很小的 reference testbench。

为了避免“单独一个 cell 的输入 slew / 输出 load 不真实”，每个候选 unit 使用：

```text
unit0 -> unit1 -> unit2
```

三份完全相同的 unit 串联。

测量中间：

```text
unit1 input VDD/2 crossing
unit1 output VDD/2 crossing
```

定义：

```text
D_R = t_out(unit1) - t_in(unit1)
```

这样：

- `unit1` 的输入 slew 来自同类型前级；
- `unit1` 的输出负载是同类型后级；
- 不需要人为发明负载电容；
- 对未来重复级联的 programmable reference 更有代表性。

所有候选使用同一个：

```text
1 ps source slew
same VDD_A/VSS_A
same PDK model library
same process/temperature coordinates
```

本阶段只测**rising-input 到 overall rising-output 的传播延迟**。

不要同时设计 falling-path detector、pulse stretcher 或 TDC。

---

# 6. Step 3 — 第一轮 TT 简单候选筛选

第一轮只使用 `TT`，目的是快速判断是否存在 sensitivity-contrast 物理可能性。

## 6.1 两个主要合法工作基准

以：

```text
V0 = 1.10 V
V0 = 0.90 V
```

作为主要 quantitative gate。

原因：

- 已有 sensor 的 50/100 mV fine-curve 数据可直接复用；
- 已有 PVT sensor evidence 在这两个工作点是干净的；
- 不需要补跑任何 sensor HSPICE。

`0.75 V` 暂时只作为后面的 TT 温度 sanity point，不向更低电压扩展。

## 6.2 温度点

对每个候选，在：

```text
VDD = 1.10, 0.90 V
T   = -40, 25, 125 C
```

测 `D_R`。

第一轮不需要先跑 85 C；85 C 留给 shortlist confirmation。

## 6.3 VDD sensitivity 点

固定：

```text
T = 25 C
corner = TT
```

新增 reference-only HSPICE：

```text
1.10, 1.05, 1.00 V
0.90, 0.85, 0.80 V
```

这些只是 reference candidate 新数据；sensor 对应 `W_S` 全部从已有 `fine.csv` 读取。

输出：

```text
delay_chain/ftc/analysis/reference_sensitivity_contrast/simple_candidate_screen.csv
```

---

# 7. Step 4 — 用“校准后的残差”评价候选，不直接比较裸延迟

单个 reference unit 的绝对延迟通常远小于 tap29 脉宽，因此不要直接比较：

```text
D_R vs W_S
```

也不要因为一个 unit 只有几十 ps 就判失败。

对于每个候选和每个本地工作点 `V0`，定义仅用于物理筛选的 scale：

```text
k(V0) = W_S(V0,25C) / D_R(V0,25C)
```

这里 `k` 只是模拟未来“使用若干 reference units 匹配正常脉宽”的连续近似，**不是最终硬件 unit count，也不是本阶段的 CDL 设计**。

## 7.1 Temperature residual

对于同一 `V0`：

```text
E_T(T) = [W_S(V0,T) - W_S(V0,25C)]
         - k(V0) * [D_R(V0,T) - D_R(V0,25C)]
```

计算：

```text
E_T_max = max_T |E_T(T)|
```

含义：

> 如果 reference 在 nominal 点被校准到 sensor，随后只发生温度变化，sensor-reference residual 还剩多少。

## 7.2 Voltage-droop residual

使用已有 sensor `fine.csv`：

```text
E_V(DeltaV) = [W_S(V0-DeltaV,25C) - W_S(V0,25C)]
              - k(V0) * [D_R(V0-DeltaV,25C) - D_R(V0,25C)]
```

分别计算：

```text
DeltaV = 50 mV
DeltaV = 100 mV
```

## 7.3 直接 separability margin

定义：

```text
M_50  = |E_V(50mV)|  - E_T_max
M_100 = |E_V(100mV)| - E_T_max
```

解释：

```text
M > 0
```

表示在该本地工作点，至少从目前已测 temperature envelope 看，存在一个 timing threshold 可以位于 normal-temperature residual 与该 droop residual 之间。

这比人为定义一个复杂 score 更直接。

同时记录：

```text
sign(E_V)
equivalent_unit_count = k
raw sensor temperature span
residual temperature span
```

不要把 `k` 四舍五入成硬件数量，也不要在本阶段优化面积。

---

# 8. Step 5 — 简单候选 shortlist gate

对每个 candidate 分别检查：

```text
V0 = 1.10 V
V0 = 0.90 V
```

优先级：

1. `M_50 > 0`：很强；
2. `M_100 > 0`：物理机制可继续；
3. `M_100 <= 0`：该工作点下没有证明出足够的温度/VDD 可分性。

### 单候选 GO 条件

一个 simple candidate 可以直接进入 PVT confirmation，当且仅当：

```text
M_100 > 0 @ 1.10 V
AND
M_100 > 0 @ 0.90 V
```

并且：

```text
E_V(100mV) != 0
```

不要额外增加人为百分比门槛。

如果多个候选都满足，只保留最多 3 个用于下一步，按下面顺序排序：

```text
1. worst-case M_100 更大
2. 若接近，优先 M_50 更大
3. 若仍接近，优先更少 cell/stage 的结构
```

不需要做多目标优化器。

---

# 9. Step 6 — 如果 simple candidate 不够，才构造组合 reference macro-unit

只有在：

```text
没有任何 simple candidate 同时满足两个 V0 的 M_100 > 0
```

时才执行本步骤。

## 9.1 先用已测 primitive 数据预测组合

对于串联 primitive：

```text
D_AB ~= D_A + D_B
```

温度/VDD delay movement 也先按各级 delay movement 求和，得到简单预测。

利用这个预测，只构造少量可能改善：

```text
E_T_max
```

同时不显著削弱：

```text
|E_V|
```

的组合。

重点允许：

```text
RVT/LVT 混合
不同 family 混合
2-stage unit
必要时 4-stage unit
```

但整体必须 non-inverting。

## 9.2 HSPICE 重新验证整个组合 unit

组合最终必须作为一个真实 macro-unit 在三 unit cascade testbench 中重新 HSPICE：

```text
macro0 -> macro1 -> macro2
```

不能仅用单元 delay 相加结果作为最终 evidence。

输出：

```text
delay_chain/ftc/analysis/reference_sensitivity_contrast/composite_candidate_screen.csv
```

如果 composite candidate 已满足两个 V0 的 `M_100 > 0`，停止继续扩展组合空间。

---

# 10. Step 7 — 只对 1--3 个 finalist 做 PVT confirmation

PVT confirmation 的目的不是再次做大扫表，而是确认 sensitivity contrast 不是 TT-only 偶然现象。

## 10.1 复用已有 sensor PVT 数据

sensor 只从：

```text
pvt_matrix.csv
```

读取。

不重跑 sensor。

使用已有主要 envelope process：

```text
TT
FF
SS
```

以实际 `pvt_matrix.csv` 中存在的 corner 名称为准。

## 10.2 Reference-only 新仿真

对 finalist 在：

```text
VDD = 1.10, 0.90 V
T   = -40, 25, 85, 125 C
P   = selected envelope corners
```

运行 reference-only HSPICE。

对每个 `(P,V0)` 单独重新定义：

```text
k(P,V0) = W_S(P,V0,25C) / D_R(P,V0,25C)
```

这是为了模拟未来每颗芯片启动后各自 self-calibrate，因此静态 process offset 不要求 reference 天然等于 sensor。

然后重新计算：

```text
E_T(P,V0,T)
```

重点判断：

> process 固定以后，随着 temperature 改变，reference 是否仍能减少 sensor 的环境 residual。

## 10.3 只做一个已有数据可支持的 process-level VDD contrast sanity check

在每个 process corner 下，利用已有 sensor：

```text
1.10 V / 25 C
0.90 V / 25 C
```

和新 reference 数据，计算从 1.10 V 到 0.90 V 的 calibrated residual movement。

这里只检查：

```text
VDD contrast 没有在某个 process corner 下被完全抵消
```

不要因为缺少 FF/SS 的 50 mV fine sensor 数据而新增 sensor sweep。

`0.75 V / SS` 不作为本阶段的 process-level GO gate；当前阶段没有必要为它重跑或修复旧 sensor campaign。

输出：

```text
delay_chain/ftc/analysis/reference_sensitivity_contrast/finalist_pvt_confirmation.csv
```

---

# 11. Step 8 — 最终物理判定

最终判定针对的是：

```text
“灵敏度反差 reference 是否值得进入下一阶段最小 programmable delay line”
```

不是最终 detector GO/NO-GO。

## GO

至少存在一个 single-cell 或 composite reference unit，满足：

```text
1. TT 下：M_100 > 0 @ 1.10 V
2. TT 下：M_100 > 0 @ 0.90 V
3. PVT confirmation 中，per-process calibration 后的 temperature residual
   相比原始 sensor temperature movement 有实际收缩，而不是放大；
4. 1.10 -> 0.90 V 的 calibrated VDD residual 在 selected process corners
   中保持非零，不出现 reference 与 sensor 完全共模抵消。
```

若同时 `M_50 > 0`，作为额外亮点记录，但不是 GO 必需条件。

下一阶段才进入：

```text
Minimal Programmable Reference Delay Line
```

## CONDITIONAL

例如：

```text
只在一个主要 V0 有 M_100 > 0
或
只有部分 process corner 温度 residual 明显改善
或
需要 composite macro-unit 才能成立且 margin 很窄
```

报告明确指出有效范围，不在本计划中继续增加复杂结构救它。

## NO-GO

在 single-cell + 小规模 composite fallback 后，仍然：

```text
M_100 <= 0 @ 1.10 V
或
M_100 <= 0 @ 0.90 V
```

且没有 finalist 能在 PVT confirmation 中同时保留 VDD contrast 和降低温度 residual。

则关闭“同轨 sensitivity-contrast reference”路线。

不要继续尝试：

```text
更大组合搜索
复杂模拟补偿
第二电源轨
PLL/DLL
机器学习拟合
```

---

# 12. 结果文件与图

建议输出：

```text
delay_chain/ftc/analysis/reference_sensitivity_contrast/candidate_manifest.csv
delay_chain/ftc/analysis/reference_sensitivity_contrast/simple_candidate_screen.csv
delay_chain/ftc/analysis/reference_sensitivity_contrast/composite_candidate_screen.csv   # only if needed
delay_chain/ftc/analysis/reference_sensitivity_contrast/finalist_pvt_confirmation.csv
delay_chain/ftc/analysis/reference_sensitivity_contrast/summary.json
```

至少生成两张图：

```text
fig1_temperature_residual_vs_voltage_residual.svg
fig2_finalist_residual_across_pvt.svg
```

图 1 对候选直接展示：

```text
x-axis = worst temperature residual
 y-axis = 50/100 mV voltage residual
```

让 reviewer 一眼看到“温度小、VDD 大”的候选。

图 2 只画 finalist，不把所有候选塞进去。

最终报告：

```text
delay_chain/ftc/reports/FTC_REFERENCE_SENSITIVITY_CONTRAST_FEASIBILITY.md
```

---

# 13. 报告必须回答的 5 个问题

1. **是否存在单标准单元即可作为可编程 reference delay quantum？**
2. **若单单元不够，哪一种最小 composite macro-unit 能改善温度跟踪并保留 VDD contrast？**
3. **在 1.10 V 和 0.90 V 两个本地工作点，`M_50` / `M_100` 分别是多少？**
4. **per-process calibration 后，FF/TT/SS 下的 temperature residual 是否仍被压缩？**
5. **最终是否值得进入“最小可编程参考延迟线”阶段？为什么？**

报告中必须区分：

```text
measured HSPICE evidence
existing reused sensor evidence
analysis-only scaling k
future architecture inference
```

不得把 `k` 当作已经实现的 unit count，也不得宣称本阶段已经完成 self-calibration。

---

# 14. 测试与证据要求

只增加与本任务直接有关的小型测试，例如：

```text
candidate port/polarity parsing
3-unit testbench middle-delay measurement
existing sensor evidence lookup
E_T / E_V / M_50 / M_100 arithmetic
composite unit overall polarity
```

不要为本阶段建立大型 framework。

提交仓库的 compact evidence：

```text
CSV
summary.json
SVG
report
```

HSPICE 大体积输出继续留在 ignored `runs/**` 下，不提交 `.lis/.tr0/waveform` 等 bulk 文件。

---

# 15. 本阶段结束边界

一旦完成：

```text
reference candidate discovery
TT sensitivity-contrast screen
必要时的小规模 composite fallback
1--3 finalist PVT confirmation
GO / CONDITIONAL / NO-GO
```

本计划立即结束。

不要顺手实现：

```text
programmable bypass network
thermometer code
CDL range sizing
self-calibration search FSM
acceptance window
tracking
alarm latch
DVFS
P&R
```

这些属于后续阶段。

本计划的唯一成功标准是找到或否定下面这个物理关系：

```text
local temperature change:
    W_S and scaled D_R move similarly
    -> residual small

local VDD droop:
    W_S and scaled D_R move differently
    -> residual remains observable
```

若成立，下一步才将该 reference unit 做成最小可编程延迟线。