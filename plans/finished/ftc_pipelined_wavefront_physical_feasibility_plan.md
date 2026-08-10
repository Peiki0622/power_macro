# FTC 波前流水化物理可行性验证计划

## 0. 目标

本计划只验证一个物理问题：

> **同一套 RVT/LVT 双延迟链中，能否在前一个探测波前尚未完全离开延迟链时继续注入新的边沿，并且在每个探测时刻仍得到稳定、可解释的 XOR 窗口。**

如果答案为 YES，后续才有资格设计“波前流水化 FTC（Pipelined-Wavefront FTC）”的捕获、控制和告警逻辑。

本计划不是完整新架构实现计划，不做短时故障覆盖率、PVT、面积功耗或最终 RTL。

核心推进原则：

```text
先验证单边沿
    -> 再验证两个边沿共存
    -> 再验证连续多个边沿
    -> 最后判断是否存在真正的稳定流水区间
```

不要一开始设计复杂控制器，也不要同时引入新的传感结构。

---

## 1. 已完成证据直接复用，不重复实验

当前 HEAD 已经完成 FTC 基线复现和多相位失败分析。以下内容视为已有事实，Codex 不得为了本任务例行重跑：

```text
FTC 工艺                     = SMIC40LL
高 Vt 路径映射               = RVT
低 Vt 路径映射               = LVT
RVT initial stages           = 4
LVT initial stages           = 0
observable stages            = 30
正式 VDD 范围                = 0.75--1.10 V
已选捕获相对时间             = 300 ps
当前基线采样周期             = 6 ns
```

已有多相位结果已经证明：

```text
改变 capture phase 不能消除共同的 post-capture blind interval；
最佳单相位、双相位和三相位的最长共同盲区没有实质缩短；
因此 phase-diverse sampling 路线关闭。
```

本任务直接从这个结论继续。

### 禁止重跑

不要重新运行：

```text
FTC cell discovery
FTC nominal mechanism search
XOR loading study
capture-phase search
0.75--1.10 V 原始 coarse/fine static sweep
phase-voltage 2-D separability
phase-diverse candidate screen
phase-diverse glitch map
原有 FTC 全量 regression
```

只有当本计划新增的“连续边沿激励”真正改变了物理边界时，才运行对应的新 HSPICE 场景。

---

## 2. 本阶段严格范围

本阶段只回答三个递进问题：

### Q1. 下降沿本身是否能够在现有 RVT/LVT 延迟链上形成可解释的 XOR 窗口？

### Q2. 当第二个边沿在第一个波前尚未完全离开延迟链时进入，两个波前是否可以物理共存而不破坏可解码性？

### Q3. 连续多个边沿进入后，系统是否能够进入稳定、重复的周期状态？

本阶段不回答：

```text
短时 voltage glitch 最终覆盖率是多少
最终 blind window 能缩短多少
实际时序发生器怎么做
是否加入 Sticky Alarm
最终 capture bank 怎么流水化
最终 area/power 是多少
PVT/Monte Carlo 表现如何
```

这些问题只有物理可行性通过以后再规划。

---

## 3. 目录与实现边界

继续使用独立 FTC 工程：

```text
delay_chain/ftc/
```

新增任务目录建议为：

```text
delay_chain/ftc/runs/pipelined_wavefront_physical/
delay_chain/ftc/analysis/pipelined_wavefront/
delay_chain/ftc/reports/FTC_PIPELINED_WAVEFRONT_PHYSICAL_FEASIBILITY.md
```

大型 HSPICE deck、listing、波形文件继续忽略，只提交紧凑 CSV/JSON、必要图和 Markdown 报告。

### 最小代码改动原则

优先复用：

```text
delay_chain/ftc/scripts/generate_ftc_deck.py
delay_chain/ftc/scripts/run_ftc_characterization.py
delay_chain/ftc/scripts/ftc_analysis.py
```

只增加一个任务专用的连续边沿/脉冲列激励模式和对应结果汇总。

不要复制一套新的 FTC 仿真框架。

不要修改 `ftc_config.json` 中当前已经选择的正式工作点。

新增参数必须放在任务本地配置或命令行参数中。

---

# Step 1 — 为物理可行性实验增加最小连续边沿激励能力

## 1.1 目标

让现有 HSPICE deck 能够描述：

```text
edge_0
edge_1
edge_2
...
```

而不是只支持单次 launch。

第一版只需要支持规则方波/脉冲列，不做可编程复杂 pattern generator。

至少允许设置：

```text
first_edge_time_s
edge_spacing_s
edge_count
initial_logic_level
```

其中：

```text
edge_count = 1, 2, 8
```

已经足够覆盖本计划。

## 1.2 观测方式

物理可行性阶段**优先观测 raw XOR**，不要先设计新的多次 latch/FF 捕获结构。

对第 i 个边沿定义虚拟观测时刻：

```text
sample_i = edge_i + 300 ps
```

300 ps 继续使用当前已验证的相对捕获关系，不重新做 phase search。

在每个 `sample_i` 读取 30 个对应 tap 的 XOR 电平，并生成：

```text
raw_xor_word
start_index
end_index
one_run_length
run_count
largest_run_length
second_largest_run_length
valid
```

这里 `run_count` 很重要，因为多个波前共存后可能出现多个 `1` 区间。

## 1.3 必须保留的物理波形信息

每个场景至少保留紧凑形式的：

```text
edge times
sample times
RVT tap crossing/transition evidence
LVT tap crossing/transition evidence
每个 sample 的 raw XOR word
```

不要求提交完整波形文件。

## Step 1 完成条件

能够使用现有 FTC 双延迟链，在一次 HSPICE 场景中产生 1/2/8 个连续边沿，并在每个边沿后 300 ps 得到独立的 raw XOR 观测结果。

此时不要实现新的 RTL capture bank。

---

# Step 2 — 单独验证下降沿物理感知能力

## 2.1 为什么先做这一步

真正的连续波前序列天然是：

```text
rise -> fall -> rise -> fall -> ...
```

因此在研究波前重叠前，必须先知道下降沿经过同一套 RVT/LVT 延迟链时的基本行为。

## 2.2 实验

保持现有 FTC 拓扑完全不变。

分别运行：

```text
A. 孤立上升沿：直接复用已有基线证据，不重新跑
B. 新增孤立下降沿：本计划新增 HSPICE
```

下降沿只测三个电压锚点：

```text
1.10 V
0.90 V
0.75 V
```

不要做 10 mV fine sweep。

对下降沿记录：

```text
raw_xor_word
start_index
end_index
one_run_length
run_count
valid
RVT/LVT 各代表 tap 的 transition time
```

## 2.3 判断

下降沿不要求与上升沿得到相同 `(start,end)`。

只判断它属于以下哪一类：

```text
A. 可感知边沿：
   三个电压点都形成稳定、可解释的 XOR 窗口。

B. 仅恢复边沿：
   下降沿自身不适合作为传感输出，但能干净传播并恢复延迟链状态。

C. 破坏性边沿：
   下降沿导致明显不可解释/不可重复状态，连下一次上升沿也无法干净建立。
```

### 分支规则

```text
A -> 后续同时评估 rise/fall 双边沿流水
B -> 后续只把 rise 作为有效 probe，fall 仅作为恢复边沿
C -> 直接标记双边沿流水高风险，不做复杂补救设计
```

不要为了让下降沿“看起来能工作”而修改延迟链、XOR tap 或 initial stage。

## Step 2 输出

```text
isolated_falling_edge.csv
isolated_falling_edge_summary.json
```

---

# Step 3 — 两个边沿共存：先在 1.10 V 找到物理边界

这是整个计划最重要的实验。

## 3.1 激励

产生：

```text
edge_0 = rise
edge_1 = fall
```

相邻边沿间隔为：

```text
T_edge
```

观测：

```text
sample_0 = edge_0 + 300 ps
sample_1 = edge_1 + 300 ps
```

## 3.2 间隔选择

不要盲目做超密扫描。

先读取现有已提交 crossing evidence，确定 1.10 V 和 0.75 V 下 30 级路径的大致传播时间。

据此构造一个**由安全非重叠区逐步进入重叠区**的小型候选集合，约 5--7 个点即可，例如量级上可覆盖：

```text
~2 ns
~1.5 ns
~1.0 ns
~0.75 ns
~0.5 ns
~0.3--0.4 ns
```

具体数值以现有 crossing 数据为依据，不要求机械使用上述示例值。

重点是集合中必须同时包含：

```text
明显非重叠点
接近波前排空边界的点
明确存在波前重叠的点
```

## 3.3 第一轮只跑 1.10 V

对每个 `T_edge` 记录两个 sample 的：

```text
raw_xor_word
start/end
run_count
largest/second-largest run
valid
```

并标记：

```text
overlap_expected
```

判断第二个边沿进入时，第一个边沿是否理论上仍位于 30 级可观察链中。

## 3.4 不要把“出现两个 1-run”立即定义为失败

按下列等级分类：

### Level 0 — 正常单窗口

```text
0000011111100000
```

最理想。

### Level 1 — 有额外小窗口，但主窗口稳定占优

```text
0011111000100000
```

如果最大窗口位置稳定、第二窗口显著更小，仍保留为可研究状态。

### Level 2 — 多个相近窗口，边界归属不清

```text
0011100011110000
```

标记为不可安全解码。

### Level 3 — 输出不稳定/全零/无合法窗口

直接失败。

这里不要设计复杂多窗口解码器；只做物理分类。

## Step 3 完成条件

至少找到一个满足：

```text
第二边沿进入时第一波前仍未完全离开链
并且 sample_0/sample_1 均保持 Level 0 或稳定 Level 1
```

的 `T_edge`。

如果所有明确重叠点都是 Level 2/3，则波前流水核心假设直接 NO-GO，不继续做连续 8 边沿实验。

## Step 3 输出

```text
two_edge_nominal.csv
two_edge_nominal_summary.json
```

---

# Step 4 — 只把少量候选间隔扩展到 0.90 V 和 0.75 V

Step 3 通过后，从结果中只保留：

```text
1 个保守间隔
1 个较激进但已通过的重叠间隔
必要时再加 1 个边界间隔
```

不要把所有 `T_edge` 重新跑一遍。

对这 2--3 个候选，在：

```text
1.10 V
0.90 V
0.75 V
```

验证双边沿行为。

重点检查低压下：

```text
波前传播时间变长后是否出现新的多窗口冲突
第二边沿是否吞噬/压缩第一边沿脉冲
两个 sample 是否仍能得到稳定主窗口
```

### Step 4 通过条件

至少一个**真实重叠间隔**在三个电压锚点都保持可解释输出。

如果只能在 1.10 V 重叠、到 0.75 V 就不可解释，则不要宣称 0.75--1.10 V 全范围波前流水成立。

## Step 4 输出

```text
two_edge_anchor.csv
two_edge_anchor_summary.json
```

---

# Step 5 — 连续 8 边沿验证是否形成稳定流水状态

只有 Step 4 通过以后执行。

## 5.1 激励

使用选出的 1--2 个 `T_edge`，产生：

```text
rise, fall, rise, fall, rise, fall, rise, fall
```

共 8 个边沿。

每个边沿仍然在：

```text
edge_i + 300 ps
```

观测 raw XOR。

## 5.2 电压点

先只跑：

```text
1.10 V
0.75 V
```

如果两端都成立，再补：

```text
0.90 V
```

不要直接做全范围细扫。

## 5.3 需要证明的不是“8 次完全相同”

双边沿模式允许形成两个周期基线：

```text
rise : R
fall : F
rise : R
fall : F
...
```

因此重点观察：

```text
同极性边沿的 start/end 是否收敛到重复状态
run_count 是否稳定
最大窗口是否稳定
是否随边沿序号持续漂移
```

允许前 1--2 个边沿是启动过渡。

后续边沿应进入稳定周期。

定义一个简单的 `steady_state` 判据即可：

```text
最后两个 rise 的窗口分类和主要边界一致
最后两个 fall 的窗口分类和主要边界一致
不存在 Level 2/3 输出
```

不需要复杂统计模型。

## Step 5 通过条件

存在一个 `T_edge`，在三个电压锚点下连续 8 边沿能够进入稳定的 rise/fall 周期状态，并且该间隔明确处于波前重叠区。

## Step 5 输出

```text
eight_edge_pipeline.csv
eight_edge_pipeline_summary.json
```

---

# Step 6 — 确定物理可行区间，而不是追求极限频率

根据 Step 3--5 结果给出：

```text
T_edge_nonoverlap
T_edge_overlap_begin
T_edge_min_tested_stable
T_edge_first_unstable
```

不要为了找到绝对极限再做大规模二分搜索。

本阶段只需要确定一个清晰工程区间：

```text
稳定非重叠区
稳定重叠区
不稳定区
```

并从稳定重叠区选择一个保守代表点：

```text
T_edge_recommended_for_next_stage
```

选择原则：

```text
优先三个 VDD 锚点都稳定
优先 Level 0，必要时接受稳定 Level 1
不要选择紧贴首次失效边界的点
```

这一代表点只是下一阶段研究输入，不是最终硬件参数。

---

# Step 7 — 最终物理可行性判决

最终报告只能给以下三种结论之一。

## GO — 波前流水物理成立

同时满足：

```text
1. 至少一个重叠 T_edge 在 1.10/0.90/0.75 V 都稳定；
2. 连续 8 边沿能够进入可重复的周期状态；
3. 每次观测都有稳定主 XOR 窗口；
4. 下一边沿确实在上一波前尚未完全离开 observable line 时进入。
```

此时才允许下一阶段研究：

```text
真实流水 capture 架构
rolling probe 的 glitch coverage
sticky alarm
实际 timing generator
```

## CONDITIONAL — 只能更快重复，但未证明真正流水

例如：

```text
只有非重叠间隔稳定；
或 falling edge 只能作为 reset，不适合独立 probe；
或重叠只在部分 VDD 成立。
```

这时必须准确表述成：

```text
faster repeated probing / rise-only pulsed probing
```

不能称为全范围 pipelined wavefront FTC。

## NO-GO — 波前重叠破坏 FTC 可解释性

如果：

```text
所有重叠间隔都产生不可稳定解码的多窗口；
或连续边沿出现不可重复漂移；
或 0.75--1.10 V 无共同稳定重叠区。
```

则关闭波前流水路线，不增加复杂解码器补救。

后续另行考虑异步事件捕获，而不是继续堆叠流水控制逻辑。

---

# Step 8 — 报告必须阐述的结果

生成：

```text
delay_chain/ftc/reports/FTC_PIPELINED_WAVEFRONT_PHYSICAL_FEASIBILITY.md
```

报告必须围绕“物理可行性”组织，而不是堆实验日志。

至少包含以下内容。

## 8.1 为什么从 phase diversity 转向 wavefront pipelining

简明引用已完成结果：

```text
不同 capture phase 共享 post-capture blind interval；
因此需要移动新的 launch/edge aperture，而不是继续移动同一 wavefront 的 capture phase。
```

不要重新分析 phase-diverse 数据。

## 8.2 Falling-edge 基本行为

给出：

```text
1.10/0.90/0.75 V
raw XOR
start/end
window length
分类：可感知 / reset-only / destructive
```

## 8.3 两波前共存边界

给出一张核心表：

| T_edge | 是否重叠 | 1.10 V | 0.90 V | 0.75 V | 窗口等级 | 结论 |
|---|---|---|---|---|---|---|

必须明确指出：

```text
从哪个间隔开始真正出现 wavefront overlap；
从哪个间隔开始输出失稳。
```

## 8.4 连续 8 边沿结果

建议画一张简单的 edge-index 图或矩阵：

```text
edge index -> start/end 或 window class
```

显示：

```text
是否存在启动过渡
是否进入 rise/fall 周期状态
是否持续漂移
```

## 8.5 物理工作区间

明确给出：

```text
稳定非重叠区
稳定重叠区
不稳定区
推荐下一阶段 T_edge
```

## 8.6 最终结论

必须明确写：

```text
GO
CONDITIONAL
NO-GO
```

并用测量事实说明原因。

不要使用“看起来可行”“大概有效”之类模糊结论。

---

# Step 9 — 本任务的最小测试要求

只增加与本任务直接相关的测试。

至少检查：

```text
连续边沿参数能正确进入 deck
每个 sample_i 都能提取 30-bit XOR word
run_count / largest-run 计算正确
结果 CSV/JSON 字段稳定
任务不会修改正式 selected_operating_point
```

只运行任务相关测试和必要的 Python 语法检查。

**不要为了本计划重新运行此前完整 FTC regression 或 Phase-3 regression。**

---

# 10. 明确禁止的过度设计

在本计划完成 GO 之前，不要实现：

```text
第二套 RVT/LVT 延迟链
第二套 XOR bank
多 bank capture
复杂多窗口匹配器
FIFO
pipeline controller RTL
Sticky Alarm
CUSUM
随机 probe scheduler
PLL/DLL
可编程真实延迟发生器
PVT adaptive calibration
Monte Carlo
全 glitch 矩阵
面积功耗优化
```

也不要：

```text
把最低工作电压重新扩展到 0.70 V
修改现有 30-stage observable length
重新选择 RVT/LVT initial stage
重新优化 300 ps baseline phase
```

物理可行性没有证明之前，这些都没有意义。

---

# 11. Codex 最终应提交的最小成果

如果实验能够完成，提交内容应聚焦：

```text
1. 最小连续边沿 HSPICE 支持
2. falling-edge compact evidence
3. two-edge compact evidence
4. eight-edge compact evidence
5. 物理区间 summary JSON
6. FTC_PIPELINED_WAVEFRONT_PHYSICAL_FEASIBILITY.md
7. 少量任务专用测试
```

最终真正需要回答的问题只有一句：

> **在 SMIC40LL RVT/LVT FTC 的 0.75--1.10 V 已验证范围内，是否存在一个非空的波前重叠时间区间，使多个连续边沿可以共享同一套延迟链并保持稳定、可解释的 XOR 观测？**

只有这个问题得到肯定答案，才进入下一阶段的“流水捕获与瞬态覆盖率”设计。
