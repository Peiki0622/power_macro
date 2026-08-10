# FTC tap29 真实 XOR 输出脉宽物理验证计划

## 0. 任务定位

本任务是 `XOR 脉宽—VDD` 路线在 proxy 分析得到 GO 之后的**第一项真实电路物理验证**。

当前已经证明：

```text
W_proxy_i(VDD) = |t_RVT_i(VDD) - t_LVT_i(VDD)|
```

在现有 36 点静态证据中对 30 个 tap 都具有稳定路径先后关系和严格单调的 VDD 映射，tap29 是当前最优候选。

但是 `W_proxy` 只是 RVT/LVT 两个 XOR 输入端的 crossing 时间差，**不是实际 XOR 标准单元输出的高电平脉宽**。

本计划只回答：

> **在当前真实 SMIC40LL RVT/LVT FTC 拓扑和真实 `XOR2_X0P5M_A9TR40` 单元下，tap29 的 XOR 输出高电平脉宽 `W_real(VDD)` 是否在 0.75--1.10 V 范围内保持完整、稳定、单调，并保留足够明显的 VDD 信息。**

只有这个问题得到 GO，后续才允许研究脉宽阈值判决器、PVT、自校准、双 tap、异步告警等架构创新。

---

# 1. 当前仓库事实必须直接复用

Codex 开始前先读取当前 HEAD 的：

```text
delay_chain/ftc/ftc_config.json
delay_chain/ftc/discovery/selected_cells.json
delay_chain/ftc/scripts/generate_ftc_deck.py
delay_chain/ftc/analysis/xor_pulse_width_vdd/summary.json
delay_chain/ftc/analysis/xor_pulse_width_vdd/tap_metrics.csv
delay_chain/ftc/reports/FTC_XOR_PULSE_WIDTH_VDD_MAPPING.md
```

当前正式工作点保持：

```text
technology                  = SMIC40LL
corner                      = TT
temperature                 = 25 C
RVT delay cell              = BUF_X0P7M_A9TR40
LVT delay cell              = BUF_X0P7M_A9TL40
real XOR cell               = XOR2_X0P5M_A9TR40
RVT initial stages          = 4
LVT initial stages          = 0
observable stages           = 30
formal VDD range            = 0.75--1.10 V
source launch time          = 1 ns
tran max step               = 1 ps
```

proxy 分析已经给出：

```text
best_tap = 29
shortlisted_taps = [29]
decision = GO
```

不要重新做 30-tap 排名。

不要因为 tap28/tap27 也很好而扩大本阶段范围。

---

# 2. 本任务明确不做什么

本阶段禁止：

```text
PVT sweep
Monte Carlo
voltage glitch campaign
falling-edge pulse study
multi-edge / rolling / pipelined-wavefront study
multi-tap fusion
TDC
counter-based pulse measurement
pulse-width threshold detector
DLL/PLL
reference voltage
Sticky Alarm
CUSUM
RTL architecture
area/power optimization
new Vt pair search
new delay-chain length search
new capture-phase search
```

也不要重新运行：

```text
FTC reproduction
phase-diverse experiments
wavefront experiments
原有 30-tap proxy analysis
```

本任务只有一个物理变量：

```text
VDD
```

只研究一个位置：

```text
tap29
```

只研究一次孤立上升沿产生的真实 XOR 高电平脉冲。

---

# 3. 关键实验原则：保持当前真实负载，不做“单 XOR 简化电路”

现有 `xor` mode 会实例化完整 30 路真实 XOR bank：

```text
RVT tap0..29
    +
LVT tap0..29
    -> 30 x XOR2_X0P5M_A9TR40
```

本任务必须继续使用这个完整 `xor` mode。

**不要为了只测 tap29 而删除其他 29 个 XOR。**

原因：proxy/static FTC 证据来自当前已验证 topology 和 loading。删除其他 XOR 会改变各 tap 的电容负载，从而让新的真实脉宽结果与旧证据失去可比性。

本阶段只是在完整 XOR bank 中新增对：

```text
xor_29
```

的时间域测量，不改变任何实体单元。

---

# 4. Step 1 — 给现有 deck 增加最小的真实脉宽测量接口

优先在：

```text
delay_chain/ftc/scripts/generate_ftc_deck.py
```

增加一个**可选、默认关闭**的 task-local pulse-width measurement 参数，例如：

```text
pulse_width_taps=[29]
```

或者等价的最小接口。

要求：

```text
pulse_width_taps is None
```

时，现有所有 deck 文本和旧流程行为保持不变。

只允许在：

```text
mode = xor
```

下用于本任务。

不要增加第四种复杂 FTC mode。

## 4.1 tap29 必须测量的节点

现有真实节点：

```text
rvt_tap_29
lvt_tap_29
xor_29
```

对一次孤立上升沿，保留已有输入 crossing：

```text
t_rvt29
t_lvt29
```

并新增真实 XOR 输出的：

```text
t_xor29_rise
t_xor29_fall
```

阈值统一使用：

```text
VDD_VALUE / 2
```

真实脉宽：

```text
W_real = t_xor29_fall - t_xor29_rise
```

proxy：

```text
W_proxy_same_run = abs(t_rvt29 - t_lvt29)
```

## 4.2 推荐 HSPICE measure 语义

使用真实 `xor_29` 输出的第一个高电平脉冲：

```text
TRIG xor_29 at VDD/2 RISE=1
TARG xor_29 at VDD/2 FALL=1
```

可直接 measure pulse width，也可以分别 measure rise/fall 后由 Python 计算。

优先保留 rise/fall 两个绝对 crossing，因为后续需要分析脉冲起点和终点分别被 XOR cell 移动多少。

## 4.3 同时测量 pulse peak

新增：

```text
xor29_peak_v
```

在首次 rising-edge pulse 所在时间窗口内测 MAX `v(xor_29,vss_a)`。

输出归一化：

```text
xor29_peak_ratio = xor29_peak_v / VDD
```

peak 只用于检查 pulse 是否明显衰减，不在本阶段人为设定复杂 VIH/VIL 判决。

真正最基本的有效性条件是：

```text
xor_29 必须存在可测的 VDD/2 rise 和 fall crossing
```

---

# 5. Step 2 — 用同一次物理 run 分解“proxy 与真实 XOR 脉宽的差异”

不要只输出：

```text
W_real
```

还要计算：

```text
lead_input_cross  = min(t_rvt29, t_lvt29)
lag_input_cross   = max(t_rvt29, t_lvt29)

start_shift_ps = (t_xor29_rise - lead_input_cross) * 1e12
end_shift_ps   = (t_xor29_fall - lag_input_cross) * 1e12

W_proxy_ps = (lag_input_cross - lead_input_cross) * 1e12
W_real_ps  = (t_xor29_fall - t_xor29_rise) * 1e12

width_error_ps = W_real_ps - W_proxy_ps
width_ratio    = W_real_ps / W_proxy_ps
```

这样可以直接验证：

```text
W_real = W_proxy + end_shift - start_shift
```

物理上回答：

> XOR cell 的 rise/fall propagation asymmetry 是近似系统偏移，还是会随 VDD 强烈改变并破坏原有映射。

本阶段不建立复杂模型拟合。

---

# 6. Step 3 — 第一轮只跑 5 个 VDD 锚点

先运行：

```text
1.10 V
1.00 V
0.90 V
0.80 V
0.75 V
```

不要第一步就跑 36 点。

每个 VDD 使用：

```text
selected 4-RVT / 0-LVT operating point
30-stage full delay lines
full 30-XOR bank
single normal rising launch
no glitch
TT / 25 C
tran max step = existing 1 ps
```

不要修改 `tran_max_step_s` 去追求额外精度。

如果 HSPICE measure 本身失败，先检查 measure window/occurrence 定义；不要通过重新优化电路解决。

---

# 7. Step 4 — 锚点阶段只看四个物理问题

对 5 个 VDD，逐点回答：

## Q1. 真实 XOR pulse 是否存在？

必须存在：

```text
t_xor29_rise finite
t_xor29_fall finite
t_xor29_fall > t_xor29_rise
W_real > 0
```

## Q2. pulse 是否保持可观察数字摆幅？

记录：

```text
xor29_peak_ratio
```

必须至少能跨过 VDD/2 形成完整 rise/fall pulse。

不要在这个阶段人为加入一个未经库规格支持的 0.8/0.9 VDD hard gate。

## Q3. `W_real(VDD)` 是否保持与 proxy 相同的宏观方向？

现有 proxy 随 VDD 从 1.10 V 降到 0.75 V 持续增大。

因此 5 个真实锚点应满足：

```text
W_real(1.10)
 < W_real(1.00)
 < W_real(0.90)
 < W_real(0.80)
 < W_real(0.75)
```

不做曲线拟合，不做平滑。

## Q4. XOR cell 是否把脉宽映射破坏成严重非一致失真？

观察：

```text
width_error_ps
width_ratio
start_shift_ps
end_shift_ps
```

只做描述和可视化。

不要预先假设 `W_real == W_proxy`。

真实 XOR 输出可以整体压缩或扩大 proxy，只要 VDD 映射仍然稳定可解释。

---

# 8. Step 5 — 锚点阶段的 gate

## ANCHOR-GO

满足：

```text
1. 五个 VDD 都存在完整 VDD/2 rise/fall crossing；
2. 五点 W_real 严格单调，方向与 W_proxy 一致；
3. 没有某个电压点发生 pulse disappearance / zero-width；
4. 输出 peak 没有低到失去 VDD/2 crossing。
```

则授权 Step 6 的 36 点 fine validation。

## ANCHOR-CONDITIONAL

如果：

```text
所有 pulse 都存在且总体 VDD movement 明显，
但出现 plateau 或一个局部顺序问题；
```

停止自动扩展。

报告为 CONDITIONAL，由人工决定是否值得做一个非常小的定点复核。

不要自动修改 XOR cell、drive strength 或 tap。

## ANCHOR-NO-GO

如果任一关键电压点出现：

```text
没有完整 pulse；
XOR pulse 无法跨 VDD/2；
明显非单调；
真实输出宽度与 VDD 的宏观趋势被 XOR filtering 破坏；
```

直接关闭当前 tap29 真实脉宽路线。

不要立刻改 tap28、换 XOR drive、加 pulse stretcher 来救结果。

---

# 9. Step 6 — 只有 ANCHOR-GO 后才跑 36 点真实脉宽 fine sweep

VDD：

```text
1.10, 1.09, ..., 0.75 V
```

共 36 点。

仍然只测 tap29。

每个 run 输出：

```text
vdd_v
t_rvt29_s
t_lvt29_s
t_xor29_rise_s
t_xor29_fall_s
W_proxy_ps
W_real_ps
start_shift_ps
end_shift_ps
width_error_ps
width_ratio
xor29_peak_v
xor29_peak_ratio
valid
```

不要测其余 29 个 XOR 的 pulse width。

---

# 10. Step 7 — 真实 `W_real(VDD)` 分析

对 36 点只计算简单直接指标。

## 10.1 单调性

分类：

```text
strict_increasing
nondecreasing_with_plateau
nonmonotonic
```

按 VDD 从 1.10 向 0.75 下降的顺序定义。

记录：

```text
plateau_count
monotonic_violation_count
```

## 10.2 动态范围

```text
real_span_ps = W_real(0.75) - W_real(1.10)
```

## 10.3 相邻 10 mV movement

```text
min_abs_step_ps
median_abs_step_ps
max_abs_step_ps
```

## 10.4 灵敏度

有限差分：

```text
|dW_real/dVDD|
```

单位：

```text
ps / 100 mV
```

输出：

```text
min
median
max
```

## 10.5 与 proxy 的失真

输出：

```text
min/median/max width_error_ps
min/median/max width_ratio
```

不要做高阶 polynomial fit。

不要把 proxy 与 real 的差异“校准掉”。

本阶段要先看真实物理结果本身是否足够好。

---

# 11. Step 8 — 只生成两张核心图

避免过度出图。

## 图 1：`W_real` 与 `W_proxy` 对 VDD

```text
x = VDD
y = pulse width (ps)
```

两条曲线：

```text
W_proxy_same_run
W_real
```

输出：

```text
delay_chain/ftc/analysis/real_xor_pulse_width/fig1_real_vs_proxy.svg
```

## 图 2：XOR cell 引入的 pulse distortion

横轴：

```text
VDD
```

优先画：

```text
width_error_ps
```

如需要再在报告表中给 `width_ratio`，不要做复杂多轴图。

输出：

```text
delay_chain/ftc/analysis/real_xor_pulse_width/fig2_width_error_vs_vdd.svg
```

---

# 12. Step 9 — 输出位置和证据管理

HSPICE 原始运行目录：

```text
delay_chain/ftc/runs/real_xor_pulse_width/
```

其中 deck、lis、measurement database 等保持 ignored/reproducible。

**紧凑结果不要放在 ignored runs 目录。**

提交：

```text
delay_chain/ftc/analysis/real_xor_pulse_width/anchor.csv
delay_chain/ftc/analysis/real_xor_pulse_width/anchor_summary.json
```

若 anchor GO，再提交：

```text
delay_chain/ftc/analysis/real_xor_pulse_width/fine.csv
delay_chain/ftc/analysis/real_xor_pulse_width/summary.json
fig1_real_vs_proxy.svg
fig2_width_error_vs_vdd.svg
```

这样不需要为本任务扩大 `.gitignore` 例外。

---

# 13. Step 10 — 最终报告

生成：

```text
delay_chain/ftc/reports/FTC_REAL_XOR_PULSE_WIDTH_VALIDATION.md
```

报告必须包含：

## A. Why this experiment

说明前一阶段 GO 只证明：

```text
|t_RVT - t_LVT|
```

是良好的 VDD feature，不等于真实 XOR output pulse。

## B. Exact physical topology

明确：

```text
4 RVT initial stages
0 LVT initial stages
30 observable stages
full 30 real XOR bank
XOR cell = XOR2_X0P5M_A9TR40
measured tap = 29
TT / 25 C
```

## C. Anchor result

表：

| VDD | W_proxy | W_real | Width error | Peak/VDD | Valid |
|---:|---:|---:|---:|---:|---:|

## D. Fine transfer（仅 anchor GO 时）

报告：

```text
monotonic class
real span
min/median 10 mV step
min/median/max sensitivity
width distortion range
```

## E. Physical interpretation

只回答：

```text
real XOR 是否保留 proxy 的 VDD 映射？
XOR cell 主要造成近似固定偏移还是 VDD-dependent distortion？
真实输出是否在全范围都产生完整 pulse？
```

不要讨论尚未验证的 threshold/TDC/PVT/glitch 架构性能。

## F. Final decision

必须明确：

```text
GO
CONDITIONAL
NO-GO
```

---

# 14. Step 11 — 最终 GO / CONDITIONAL / NO-GO 定义

## GO

36 点真实结果同时满足：

```text
1. 36/36 都有完整 VDD/2 rise/fall crossing；
2. W_real(VDD) strict monotonic；
3. 没有 pulse disappearance；
4. 相邻 VDD movement 始终非零；
5. tap29 真实 output 保留清晰的 VDD-dependent pulse-width transfer。
```

则下一阶段可以研究：

> **极简 pulse-width threshold/readout，而不是完整高分辨率 TDC。**

## CONDITIONAL

如果：

```text
36/36 pulse 都有效，
但出现 plateau，或少量局部非严格单调，
且宏观 VDD movement 仍然明显；
```

结论为 CONDITIONAL。

下一步只允许先研究攻击级 coarse threshold 是否仍可分，不直接设计完整 readout。

## NO-GO

如果：

```text
真实 XOR 在部分 VDD 丢失 pulse；
存在明显 output-pulse filtering；
W_real 与 VDD 出现不可解释的强非单调；
或真实脉宽变化被 XOR cell distortion 大幅抵消；
```

则关闭当前 tap29 pulse-width readout 路线。

不要立即通过换 XOR、加 pulse stretcher、多 tap fusion 来强行继续。

---

# 15. 最小代码组织建议

优先保持改动小。

建议只新增/修改：

```text
delay_chain/ftc/scripts/generate_ftc_deck.py
    - optional tap29 pulse-width .measure support

delay_chain/ftc/scripts/run_real_xor_pulse_width.py
    - task-owned 5-anchor -> gated 36-point runner
    - parse compact HSPICE measures
    - write analysis CSV/JSON/report/figures

delay_chain/ftc/tests/test_real_xor_pulse_width.py
```

不要为了这个任务继续扩张已经很大的 `run_ftc_characterization.py`，除非复用现有公共 helper 只需要极少改动。

新 runner 可以复用现有：

```text
HSPICE executable/config
selected_cells.json
measurement parser/helper
```

但不要复制一套 FTC topology generator。

---

# 16. 最小测试要求

只做与本任务直接相关的测试，不跑旧 HSPICE regression。

至少验证：

```text
1. pulse_width_taps=None 时旧 deck 不增加新 measure；
2. pulse_width_taps=[29] 时仍实例化完整 30-XOR bank；
3. deck 只新增 tap29 real XOR rise/fall/peak measures；
4. selected operating point 仍为 4 RVT / 0 LVT；
5. W_real / W_proxy / start_shift / end_shift 算术正确；
6. 5-anchor gate 正确阻止失败结果进入 36-point fine；
7. synthetic strict-monotonic result -> GO；
8. missing pulse / nonmonotonic result -> NO-GO 或 CONDITIONAL，按定义执行。
```

只运行：

```text
python unit test
py_compile
本任务新增的 HSPICE scenarios
```

不要重新跑：

```text
phase-diverse
pipelined-wavefront
完整 FTC VCS regression
旧 static HSPICE
```

---

# 17. Codex 最终最小提交物

若 anchor 阶段失败：

```text
modified minimal deck support
run_real_xor_pulse_width.py
anchor.csv
anchor_summary.json
FTC_REAL_XOR_PULSE_WIDTH_VALIDATION.md
task-specific test
```

若 anchor GO 且完成 fine：

```text
modified minimal deck support
run_real_xor_pulse_width.py
anchor.csv
anchor_summary.json
fine.csv
summary.json
fig1_real_vs_proxy.svg
fig2_width_error_vs_vdd.svg
FTC_REAL_XOR_PULSE_WIDTH_VALIDATION.md
test_real_xor_pulse_width.py
```

最终真正只回答一句：

> **tap29 上由真实 `XOR2_X0P5M_A9TR40` 产生的输出高电平脉宽，是否在现有 SMIC40LL FTC 的 0.75--1.10 V 工作范围内保留了 proxy 已证明的稳定 VDD 映射，从而值得进入下一阶段的极简脉宽判决器设计？**
