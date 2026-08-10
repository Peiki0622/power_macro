# FTC XOR 脉宽—VDD 映射分析计划

## 0. 任务目标

本任务只回答一个物理机制问题：

> **利用已经完成的 SMIC40LL FTC 仿真中保存的 RVT/LVT 每级 transition/crossing 时间，判断 30 个对应 tap 上由两条路径到达时间差形成的“等效 XOR 高电平脉宽”是否与 VDD 存在稳定、单调、足够明显的映射关系。**

本阶段是纯数据分析，不重新运行 HSPICE，不修改 FTC 硬件，不设计新的 pulse-width detector，不做 CUSUM，不做 PVT，不做 glitch coverage。

如果映射成立，下一阶段才允许选择少量 tap，直接在真实 XOR 输出端物理测量高电平脉宽，并验证门级脉冲失真和可实现的读出方式。

---

# 1. 必须正确理解本阶段测量量

对于第 `i` 个对应 tap，已有数据包含：

```text
t_RVT_i(VDD)
t_LVT_i(VDD)
```

定义有符号路径差：

```text
Delta_i(VDD) = t_RVT_i(VDD) - t_LVT_i(VDD)
```

定义本阶段的等效 XOR 输入高电平窗口：

```text
W_proxy_i(VDD) = abs(Delta_i(VDD))
```

单位统一转换为 ps。

其物理意义是：

```text
当 RVT_i 和 LVT_i 的逻辑状态不同，理想 XOR 应为 1；
因此两条路径 VDD/2 crossing 的时间差近似给出 XOR=1 的理想时间窗口。
```

## 1.1 不得过度声称

`W_proxy_i` 不是最终真实 XOR 单元输出脉宽。

真实 XOR 输出还可能受到：

```text
XOR cell propagation delay
rise/fall asymmetry
inertial filtering
very-short-pulse attenuation
loading
```

影响。

因此本阶段只能得出：

```text
RVT/LVT path-difference pulse-width proxy 是否值得继续研究
```

不能直接宣称：

```text
真实 XOR pulse detector 已经可用
```

下一阶段若 GO，才对少量候选 tap 直接做真实 XOR 输出脉宽 HSPICE 验证。

---

# 2. 已完成结果作为固定前提，不重新运行

保持当前正式 FTC 工作点：

```text
technology                = SMIC40LL
RVT initial stages        = 4
LVT initial stages        = 0
observable stages         = 30
formal VDD range          = 0.75--1.10 V
selected capture phase    = 300 ps
```

本任务只使用已经存在的 transition/crossing evidence。

## 2.1 禁止重新运行

不要重新运行：

```text
FTC reproduction
mechanism search
capture phase search
0.75--1.10 V static HSPICE sweep
phase-voltage 2-D analysis
phase-diverse sampling
pipelined-wavefront experiments
任何新的 glitch HSPICE
任何新的 PVT/Monte Carlo
```

不要因为某个输入文件在 Git 中被忽略，就自动重新跑 HSPICE。

---

# 3. 数据源优先级

Codex 必须先检查现有 workspace 中的紧凑证据，然后按以下优先级选择输入。

## 3.1 首选：已有 10 mV static fine 数据

如果存在：

```text
delay_chain/ftc/runs/static_fine/static_transfer.csv
```

并且包含：

```text
vdd_v
rvt_crossings_s
lvt_crossings_s
```

则直接使用它作为主数据源。

预期 VDD：

```text
1.10, 1.09, ..., 0.75 V
```

共 36 点。

不要重新生成这个文件。

## 3.2 远程仓库已提交的后备数据

如果本地 fine 数据不存在，使用已提交：

```text
delay_chain/ftc/runs/phase_diverse_screen/phase_candidate_coarse.csv
```

该文件已经保存：

```text
vdd_v
rvt_crossings_s
lvt_crossings_s
phase_id
phase_multiplier
```

并覆盖正式范围的 coarse VDD：

```text
1.10
1.05
1.00
0.95
0.90
0.85
0.80
0.75 V
```

由于同一 VDD 在多个 capture phase 下被重复物理运行，主映射分析只取：

```text
phase_id = phi_p00
```

即当前 300 ps nominal capture 对应的数据，避免把不同重复 run 混成一条 VDD 曲线。

如果字段命名变化，则使用：

```text
phase_multiplier = 0
```

作为等价选择条件。

## 3.3 重复 phase 数据只用于一致性检查

其他 phase_id 的 crossing 数据不要用于扩充 VDD 点数。

它们只可以用来检查：

> 同一个 VDD、同一个 tap 的 `W_proxy` 在独立 phase-diverse run 中是否基本一致。

这个检查用于识别：

```text
输入数据混乱
仿真重复性异常
capture-control switching 对路径 crossing 的异常影响
```

不要把这种重复 run spread 当成完整 PVT/noise 模型。

## 3.4 数据不足时的规则

如果 fine 数据不存在，coarse committed 数据仍足以完成本阶段的初始 GO/CONDITIONAL/NO-GO 判断。

不要为了获得 10 mV 分辨率重新跑 HSPICE。

报告必须明确说明最终判断基于：

```text
36-point fine evidence
```

还是：

```text
8-point committed coarse evidence
```

---

# 4. Step 1 — 新建纯数据分析脚本

新增：

```text
delay_chain/ftc/scripts/analyze_xor_pulse_width_vdd.py
```

该脚本必须是纯 CSV 后处理工具。

禁止：

```text
import generate_ftc_deck
调用 HSPICE
修改 ftc_config.json
修改 selected_operating_point
自动生成缺失的物理数据
```

建议默认输出目录：

```text
delay_chain/ftc/analysis/xor_pulse_width_vdd/
```

最终报告：

```text
delay_chain/ftc/reports/FTC_XOR_PULSE_WIDTH_VDD_MAPPING.md
```

---

# 5. Step 2 — 严格验证输入数据

对主数据源的每一行检查：

```text
0.75 <= vdd_v <= 1.10
len(rvt_crossings_s) == 30
len(lvt_crossings_s) == 30
所有 crossing 都是 finite positive values
initial_rvt_stages == 4（若字段存在）
initial_lvt_stages == 0（若字段存在）
```

禁止：

```text
插值缺失 tap
插值缺失 VDD
把不同 operating point 混在一起
```

对每个 VDD 只能产生一组主分析数据。

如果使用 coarse phase-diverse 输入，必须明确过滤到 `phi_p00` / `phase_multiplier=0` 后再分析。

---

# 6. Step 3 — 计算 30 个 tap 的等效 XOR 脉宽

对每一个：

```text
VDD = V_k
tap = i, i in [0,29]
```

计算：

```text
delta_signed_ps = (t_RVT_i - t_LVT_i) * 1e12
xor_width_proxy_ps = abs(delta_signed_ps)
```

生成长表：

```text
delay_chain/ftc/analysis/xor_pulse_width_vdd/xor_pulse_width_matrix.csv
```

每一行至少包含：

```text
vdd_v
tap_index
rvt_cross_s
lvt_cross_s
delta_signed_ps
xor_width_proxy_ps
lead_path
```

其中：

```text
lead_path = LVT  if delta_signed_ps > 0
lead_path = RVT  if delta_signed_ps < 0
lead_path = tie  if exactly zero
```

不要只保存最终 width，必须保留 signed delta，因为路径先后关系是否发生翻转是一个重要判据。

---

# 7. Step 4 — 先检查每个 tap 的物理方向是否稳定

对于每个 tap，检查整个正式 VDD 范围内：

```text
sign(delta_signed_ps)
```

是否保持一致。

输出：

```text
lead_sign_stable
lead_path
sign_flip_count
```

## 7.1 为什么这个检查重要

如果某个 tap 随 VDD 变化出现：

```text
LVT leads -> tie -> RVT leads
```

则：

```text
W_proxy = abs(Delta)
```

会出现 V 型/折返点，单个脉宽可能无法唯一映射到 VDD。

这类 tap 不应作为首选单 tap sensor。

不要为了保留这种 tap 而立即设计复杂双特征解码。

---

# 8. Step 5 — 分析 `W_proxy_i(VDD)` 的单调性和灵敏度

对 30 个 tap 分别计算以下简单指标。

## 8.1 端点动态范围

```text
span_ps = max(W_proxy) - min(W_proxy)
endpoint_delta_ps = W_proxy(0.75 V) - W_proxy(1.10 V)
```

同时记录绝对值：

```text
abs_endpoint_delta_ps
```

## 8.2 相邻 VDD 步进变化

按 VDD 从 1.10 V 降到 0.75 V 排序，计算：

```text
step_delta_ps[k] = W_proxy(V_{k+1}) - W_proxy(V_k)
```

输出：

```text
min_abs_step_ps
median_abs_step_ps
max_abs_step_ps
```

如果主数据源是 10 mV fine 数据，同时额外生成 50 mV 抽样视图用于和 committed coarse evidence 一致比较。

## 8.3 单调性

不要使用复杂机器学习指标。

直接分类：

```text
strict_increasing
strict_decreasing
nondecreasing_with_plateau
nonincreasing_with_plateau
nonmonotonic
```

同时记录：

```text
monotonic_violation_count
plateau_count
```

这里的目标不是强迫线性，而是判断：

> 一个脉宽值能否较可靠地对应到一个 VDD 区域。

## 8.4 灵敏度

计算有限差分：

```text
S_i(V) = dW_proxy_i / dVDD
```

统一以：

```text
ps / 100 mV
```

报告。

每个 tap 输出：

```text
median_abs_sensitivity_ps_per_100mV
min_abs_sensitivity_ps_per_100mV
max_abs_sensitivity_ps_per_100mV
```

不要假设 sensitivity 在全范围恒定。

---

# 9. Step 6 — 利用已有重复 phase run 做轻量一致性检查

仅当使用或能够读取：

```text
phase_candidate_coarse.csv
```

时执行。

对每个：

```text
VDD
tap
```

利用不同 `phase_id` 的重复 crossing，计算：

```text
repeat_min_ps
repeat_max_ps
repeat_range_ps
```

针对 `W_proxy` 而不是 start/end。

这个结果只回答：

> 相同 VDD 下，现有重复物理 runs 算出的 path-difference width 是否一致。

然后对每个 tap 给出：

```text
max_repeat_range_ps
```

并与 50 mV VDD step 的 width movement 比较。

定义一个简单可审查的 margin：

```text
step_margin_ps = min_abs_50mV_step_ps - max_repeat_range_ps
```

如果：

```text
step_margin_ps > 0
```

说明现有数据中最小 50 mV VDD movement 仍大于相同 VDD 重复 run spread。

如果：

```text
step_margin_ps <= 0
```

则该 tap 的映射至少在现有证据下不够干净，应标记为弱候选。

不要把这个量称为 silicon SNR，也不要声称它包含 PVT/jitter/noise。

---

# 10. Step 7 — 30 tap 全局可视化

至少生成四类图。

## 图 1：30 tap × VDD 的脉宽热图

横轴：

```text
VDD
```

纵轴：

```text
tap index 0..29
```

颜色/数值：

```text
W_proxy_ps
```

目的：直观看到差分延迟如何沿链累积，以及哪个 tap 区域对 VDD 最敏感。

建议文件：

```text
fig1_pulse_width_heatmap.svg
```

## 图 2：30 个 tap 的 endpoint span / sensitivity vs tap index

横轴：

```text
tap index
```

至少绘制：

```text
abs_endpoint_delta_ps
median_abs_sensitivity_ps_per_100mV
```

如果量纲差异明显，做两张独立图，不要用难读的双 Y 轴。

建议：

```text
fig2_span_vs_tap.svg
fig3_sensitivity_vs_tap.svg
```

## 图 3：候选 tap 的 `W_proxy-VDD` 曲线

只画最终 shortlist，不要把 30 条线全部堆在一张图中。

建议：

```text
fig4_candidate_width_vs_vdd.svg
```

## 图 4：signed delta / lead-path consistency

对所有 tap 给出一个紧凑图或表，明确是否发生：

```text
Delta_i = 0 crossing
lead-path reversal
```

建议：

```text
fig5_signed_delta_map.svg
```

---

# 11. Step 8 — 给 30 个 tap 排名，但不要提前设计多 tap 架构

生成：

```text
delay_chain/ftc/analysis/xor_pulse_width_vdd/tap_metrics.csv
```

每个 tap 一行，至少包含：

```text
tap_index
lead_sign_stable
lead_path
sign_flip_count
monotonic_class
monotonic_violation_count
plateau_count
span_ps
endpoint_delta_ps
abs_endpoint_delta_ps
min_abs_step_ps
median_abs_step_ps
median_abs_sensitivity_ps_per_100mV
min_abs_sensitivity_ps_per_100mV
max_repeat_range_ps（若可用）
step_margin_ps（若可用）
```

## 11.1 排名优先级

不要用复杂加权 score。

按以下逻辑顺序筛选：

```text
1. lead_sign_stable = true
2. monotonic_class 不是 nonmonotonic
3. 优先 plateau 少的 tap
4. 优先 50 mV step_margin_ps > 0（若重复证据可用）
5. 再比较 span_ps 和 median sensitivity
```

这个顺序体现：

```text
先保证映射可解释
再追求灵敏度
```

不要为了获得最大的 span 选择一个明显非单调 tap。

## 11.2 shortlist 数量

最终 shortlist：

```text
最多 3 个 tap
```

如果只有一个明显最优 tap，就只选择一个。

不要机械地强行选 3 个。

本阶段只 shortlist，不修改 RTL/HSPICE 拓扑。

---

# 12. Step 9 — 明确 GO / CONDITIONAL / NO-GO

这里的判决只针对：

> **是否值得进入“真实 XOR 输出脉宽物理验证”下一阶段。**

不是最终架构判决。

## GO

至少存在一个 tap 满足：

```text
1. RVT/LVT lead sign 在 0.75--1.10 V 全范围稳定；
2. W_proxy(VDD) 在已有 VDD 网格上单调；
3. 不存在大面积平台导致明显多 VDD 对一 width；
4. VDD-induced width movement 明显存在；
5. 若重复 phase evidence 可用，则 50 mV 最小 step movement 大于 same-VDD repeat range。
```

结论：

```text
GO — 对 shortlist tap 直接测真实 XOR output pulse width
```

## CONDITIONAL

例如：

```text
映射总体单调但存在平台；
只有部分 VDD 区间灵敏；
或 50 mV movement 与 repeat spread 接近；
或只有 late taps 有足够 sensitivity。
```

结论：

```text
CONDITIONAL — 保留候选，但下一阶段先做少量真实 XOR pulse 验证，不做架构设计
```

## NO-GO

如果全部 30 个 tap 都出现：

```text
明显非单调/路径先后翻转；
或者 width 对 VDD 变化太弱；
或者现有重复 run spread 与 VDD movement 同量级；
```

则：

```text
NO-GO — 关闭 XOR pulse-width readout 路线
```

不要通过增加复杂多 tap 算法去强行得到 GO。

---

# 13. Step 10 — 生成最终研究报告

生成：

```text
delay_chain/ftc/reports/FTC_XOR_PULSE_WIDTH_VDD_MAPPING.md
```

报告按以下结构组织。

## A. Motivation

说明：

```text
fixed-time spatial snapshot 已暴露 phase dependence 和 temporal blind-window 问题；
本分析不再改变 capture phase/launch cadence，而是重新检查 RVT/LVT 差分延迟本身能否直接作为时间域特征。
```

不要重新复述全部 phase-diverse/wavefront 实验过程。

## B. Input Evidence

明确写：

```text
使用了哪个现有 CSV
VDD 点数
是否 36-point fine 或 8-point coarse
是否使用重复 phase run 做 consistency check
没有运行新的 HSPICE
```

## C. Definition

明确：

```text
Delta_i = t_RVT_i - t_LVT_i
W_proxy_i = |Delta_i|
```

并强调：

```text
W_proxy 是由路径 crossing 得到的等效 XOR 输入窗口，不是最终真实 XOR cell output pulse width。
```

## D. 30-tap Mapping

给出：

```text
heatmap
span-vs-tap
sensitivity-vs-tap
signed-delta consistency
```

## E. Candidate Taps

用表格列出 shortlist：

| Tap | Lead path | Monotonicity | Span | Sensitivity | Repeat margin | Reason |
|---|---|---|---:|---:|---:|---|

## F. Physical Interpretation

回答：

```text
差分延迟是否随 tap 累积？
哪个 tap 区域最有 VDD 信息？
是否存在 path-order reversal？
灵敏度是否只在低压区增强？
```

只根据数据回答，不做未经验证的晶体管级推断。

## G. Final Decision

必须明确：

```text
GO
CONDITIONAL
NO-GO
```

并明确下一阶段是否被授权。

---

# 14. Step 11 — 最小测试要求

新增：

```text
delay_chain/ftc/tests/test_xor_pulse_width_vdd.py
```

只测试纯分析逻辑，不调用 HSPICE。

至少覆盖：

```text
30-element crossing arrays 正确解析
ps 单位换算正确
signed delta / abs width 正确
lead-path sign 判断正确
monotonic classification 正确
sign-flip tap 能被拒绝为首选
coarse phase input 正确过滤 phi_p00 / multiplier=0
结果 CSV 列稳定
```

可以使用 synthetic data 验证算法。

只运行：

```text
该任务相关 Python unit test
必要的 py_compile
```

不要重新运行 Phase-3 regression、完整 FTC HSPICE 或此前已完成的 phase/wavefront regression。

---

# 15. 本任务明确禁止的过度设计

本阶段不要实现：

```text
真实 XOR pulse-width detector
TDC
counter
DLL/PLL
multi-tap fusion logic
new latch/FF bank
asynchronous sticky alarm
CUSUM
new glitch campaign
PVT/Monte Carlo
new delay-chain topology
new Vt pair search
new initial-delay search
```

也不要：

```text
修改 4-RVT / 0-LVT 基线
修改 30-stage observable line
扩展最低工作电压到 0.70 V
重新寻找 300 ps capture phase
```

本阶段必须保持为：

```text
existing physical transition data
        -> pure post-processing
        -> 30-tap W_proxy(VDD) mapping
        -> shortlist / decision
```

---

# 16. Codex 最终应提交的最小成果

至少提交：

```text
delay_chain/ftc/scripts/analyze_xor_pulse_width_vdd.py
delay_chain/ftc/analysis/xor_pulse_width_vdd/xor_pulse_width_matrix.csv
delay_chain/ftc/analysis/xor_pulse_width_vdd/tap_metrics.csv
delay_chain/ftc/analysis/xor_pulse_width_vdd/summary.json
delay_chain/ftc/analysis/xor_pulse_width_vdd/fig1_pulse_width_heatmap.svg
delay_chain/ftc/analysis/xor_pulse_width_vdd/fig2_span_vs_tap.svg
delay_chain/ftc/analysis/xor_pulse_width_vdd/fig3_sensitivity_vs_tap.svg
delay_chain/ftc/analysis/xor_pulse_width_vdd/fig4_candidate_width_vs_vdd.svg
delay_chain/ftc/analysis/xor_pulse_width_vdd/fig5_signed_delta_map.svg
delay_chain/ftc/reports/FTC_XOR_PULSE_WIDTH_VDD_MAPPING.md
delay_chain/ftc/tests/test_xor_pulse_width_vdd.py
```

`summary.json` 至少包含：

```text
input_source
vdd_point_count
used_new_hspice = false
best_tap
shortlisted_taps
decision
decision_reason
```

最终真正需要回答的只有一句：

> **在 0.75--1.10 V 范围内，是否存在至少一个 RVT/LVT 对应 tap，使 `|t_RVT - t_LVT|` 随 VDD 呈稳定、可解释且足够明显的变化，从而值得继续验证真实 XOR 输出脉宽作为新的 FTC 读出量？**
