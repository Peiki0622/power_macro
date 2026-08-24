# FTC D0-A 运行时快路径重定时与架构闭合逐阶段推进计划

**仓库：** `Peiki0622/power_macro`  
**目标分支：** `main`  
**计划输入基线：** `de9046bdff5bd425f6124d39bf5c2037bdc66712`  
**D0-0 当前结论：** `ARCHITECTURE_REVIEW`  
**T0 下游硬要求：** 对两个正式基准电压下的 L2 / 3002 ps 目标瞬态，要求 `100% CLEAN_Q1` 全攻击相位保证，连续 probe 的 `P_runtime <= 2075 ps`。  
**本计划唯一宏观目标：** 在最大限度保留已冻结传感核心、H0、M1 和 T0 物理证据的前提下，先找出真实的单通道物理节拍下限，再选择最小必要架构改动，使运行时探测具备可验证、可重复、可实现的 `P_runtime <= 2075 ps` 能力；不得用更复杂数字 FSM、降低威胁要求或无意义重跑已有仿真来掩盖物理时序矛盾。

---

# 0. 当前事实与本计划的正确解读

D0-0 已经证明：若严格保持原冻结 one-shot 调度关系，则单一 capture DFF 路径无法满足 T0 的 2.075 ns 连续 probe 要求。以一次 `S_CLK rise` 为 0：

```text
Q sample 1                 +2300 ps
Q sample 2                 +2500 ps
reset assert start         +2700 ps
reset assert end           +2710 ps
S_CLK fall                 +3000 ps
recovery end               +5700 ps
```

即使完全忽略完整 recovery，只按 `Q2 -> reset -> 下一次 reset release -> 下一次 S_CLK rise` 串行计算，乐观下界仍为 3200 ps，因此当前 one-shot 协议不能直接缩成 2075 ps。

但必须同时冻结以下正确认识：

1. `Q_SAMPLE_1=+2300 ps`、`Q_SAMPLE_2=+2500 ps` 是已验证 one-shot 协议中的观察时刻，不自动等价于真实 DFF 的最早物理可读时刻；
2. 490 ps reset-arm、3000 ps S_CLK 高电平和 5700 ps recovery 中同时包含协议调度、观察等待和物理恢复成分，必须先拆分，不能全部当作永久物理下限；
3. 400 MHz / 2.5 ns 是校准、所有权和配置控制时钟合同，不是 runtime probe cadence；
4. T0 的 2.075 ns 只对应已冻结的目标威胁：`0.95 V / L2 / 0.86 V / 3002 ps` 与 `1.10 V / L2 / 0.96 V / 3002 ps` 的 100% 全相位 CLEAN_Q1 保证，不能外推成所有瞬态的统一要求；
5. `<0.80 V` 仍然只允许 fail-safe 语义，不得在 D0-A 中重新宣称精确 timing trip；
6. D0-0 的 `ARCHITECTURE_REVIEW` 必须永久保留为“冻结 one-shot 调度不可满足 2.075 ns”的历史证据，不允许通过改写旧报告把它变成 GO。

---

# 1. 冻结边界

除非本计划某个明确 Gate 授权，以下内容全部只读：

```text
FTC_SENSOR 的 medium/fine/XOR/capture 感知机理
medium N=16
fine K=10
sensor tap29
现有 M/F 检测码映射和 M1 12 项 codebook
DFFRPQ_X0P5M_A9TR40 作为当前正式 capture DFF
H0 calibration->DET ownership handoff
M1 安全配置装载和静态 M/F 输出语义
T0-2/T0-3/T0-4/T0-5/T0-6 全部正式物理证据
T0 Pmax_coverage = 2075 ps
T0 <0.80 V fail-safe 要求
PD_CTRL / PD_SENSE 现有理想电源感知跨域验证抽象
```

特别规定：仓库中存在其它历史 sensor RTL、Vernier、30-bit capture、latch/capture 等结构，它们只能作为历史设计资料，**不得被 Codex 自动替换成当前 T0 权威 transistor sensor**，也不得因为名字相似就被拿来“修复”D0-A。

---

# 2. 全阶段绝对禁止事项

在 D0-A 结束前禁止：

```text
修改 H0 或 M1 已冻结 RTL
重新运行完整 startup calibration
重新运行 M0/M0-E surface/trip sweep
重新运行 M1/M1-T 全流程
重新运行 RF/XA 完整流程
重新扫描 T0-2/T0-3/T0-4/T0-5 已完成电气场景
修改 T0 威胁模型以放宽 2.075 ns 要求
把 100% full-phase 要求偷偷改成平均覆盖率或“多数相位”
用 R_ps、XOR 脉宽或纯数字推断替代真实 DFF Q 判决
直接实现完整 D0 FSM、alarm、heartbeat、timeout、status 寄存器
直接加入 DLL/PLL/复杂时钟发生器
直接换 DFF cell 或修改 medium/fine/XOR 拓扑
直接复制多套完整 sensor 而没有先完成单通道物理下限分析
为了“保险”批量重跑旧 HSPICE
PVT/Monte Carlo/post-layout 扩展
```

若某一步发现需要突破以上边界，必须在当前 Gate 停止并发布 `ARCHITECTURE_ESCALATION_REQUIRED` 或独立后续计划，禁止 Codex 自行越级。

---

# 3. 证据复用优先级与仿真纪律

每个阶段严格按以下顺序取证：

```text
已有 JSON/CSV/报告能回答
    -> 直接消费，HSPICE=0
已有 retained raw listing/waveform 能回答
    -> 只重解析/新增 measure 后处理，HSPICE=0
仅 source_hash 变化但电气参数/deck 等价
    -> 电气等价复用，HSPICE=0
缺少的只是脚本、摘要、hash、Gate
    -> 只做后处理，HSPICE=0
只有新的连续 probe 物理问题确实无法由已有单 probe 证据回答
    -> 才允许任务自有的极少量新 HSPICE
```

所有阶段报告必须列出：

```text
new_hspice_scenarios
reused_hspice_scenarios
reparsed_hspice_scenarios
electrically_equivalent_reuse_scenarios
forbidden_flow_runs
```

如果必须重新仿真一个已有电气点，仅允许因为“旧原始数据没有保留当前必须的物理观测量且无法从 listing 重解析”，并且必须在 manifest 中明确记录原因；源码 hash 变化本身绝不是重跑理由。

---

# 4. D0-A0 —— 基线冻结与权威输入绑定【0 HSPICE】

## 4.1 目标

建立 D0-A 独立 baseline，绑定至少以下权威输入及 SHA256：

```text
analysis/d0_runtime_timing/contract/D0_0_RUNTIME_TIMING_BUDGET.json
reports/FTC_D0_RUNTIME_TIMING_FEASIBILITY.md
analysis/t0_transient_droop/contract/T0_DOWNSTREAM_D0_TIMING_CONTRACT.json
analysis/t0_transient_droop/cadence/cadence_summary.json
analysis/m0_detection_margin_characterization/probe_contract/single_probe_contract.json
controller/m1_detection_margin/contract/M1_DOWNSTREAM_T0_D0_HANDOFF.json
controller/pd1_power_domain_interface/crossings/sclk_crossing_contract.json
controller/pd1_power_domain_interface/crossings/reset_crossing_contract.json
controller/pd1_power_domain_interface/crossings/qfinal_return_contract.json
controller/refrequency/reports/REFREQUENCY_FINAL_REPORT.md
```

同时发布机器可读 scope，明确：

```text
D0-0 ARCHITECTURE_REVIEW 保留
T0 Pmax=2075 ps 保留
H0/M1/T0 不重跑
本阶段不实现 D0 runtime RTL
本计划允许研究 detection-only 快路径，但不自动授权改传感核心
```

## 4.2 Gate

只有输入 hash 完整、当前 T0/D0-0 状态一致、旧证据未被改写，才进入 D0-A1。

---

# 5. D0-A1 —— 将“协议等待时间”拆成“真实物理硬下限”【优先 0 HSPICE】

这是本计划最关键的第一步。**不得直接拿 2.30/2.50/3.00/5.70 ns 当作新的 runtime 时序。**

## 5.1 必须提取的真实物理量

优先从已保留的 M0/T0/RF HSPICE listing、measure、raw 波形中重解析：

```text
S_CLK rise -> 本地 sensor 关键内部边沿
S_CLK rise -> dff_ck 第一次真实有效 rise
真实 dff_ck high width / low width
真实 dff_ck 是否存在额外 edge
有效 dff_ck rise -> Q 开始响应
有效 dff_ck rise -> Q 到达稳定 low/high 判决带
Q 第一次稳定 -> 第二次独立稳定观察所需最小间隔
reset assert -> Q 被可靠清零
reset release -> 下一有效 dff_ck 的 recovery/re-arm 下限
S_CLK fall -> 延迟/XOR/CK 路径恢复到可重复下一 probe 所需时间
目标 droop 条件下上述量相对正常点是否恶化
```

必须把每一项分类为：

```text
PHYSICAL_MEASURED       已由现有晶体管证据直接量到
MODEL_TIMING_CHECK      由正式 cell timing check 给出
PROTOCOL_SCHEDULED      只是旧协议安排，不可当物理下限
UNKNOWN                 现有证据无法回答
```

生成至少：

```text
analysis/d0_runtime_fastpath/a1_physical_budget/physical_timing_inventory.csv
analysis/d0_runtime_fastpath/a1_physical_budget/physical_timing_budget.json
analysis/d0_runtime_fastpath/a1_physical_budget/evidence_reuse_manifest.json
```

## 5.2 对 Q 观察的特别要求

T0/M0 的权威检测仍是“真实 DFF Q 两次独立稳定观察”。允许重新确定两次观察的最早合法位置，但不允许把两次观察减少为一次，也不允许用数字复制同一个采样值伪装“两次独立观察”。

若旧 raw/listing 已经能证明 Q 在原 `Q_SAMPLE_1` 前很早就稳定，必须记录真实最早已证实时间；若只能知道旧采样点 PASS，而没有更早连续波形证据，就标为 `UNKNOWN`，不能自动提前。

## 5.3 HSPICE 例外预算

默认新增 HSPICE = 0。只有当一个决定架构方向的硬物理量为 `UNKNOWN`，且 retained raw/listing 不存在或无法重解析时，才允许最多 **2 个**任务自有单-probe诊断重测：优先选择 `0.95 V / L2 / 0.86 V` 与 `1.10 V / L2 / 0.96 V` 的已正式电气点，只新增必要 measure，不做 sweep，不改变 M/F、droop 或 sensor 拓扑。

## 5.4 Gate

输出：

```text
SINGLE_LANE_PHYSICAL_BUDGET_READY
或
INSUFFICIENT_EVIDENCE
```

若 `INSUFFICIENT_EVIDENCE`，停止，禁止进入架构实现。

---

# 6. D0-A2 —— 单通道 detection-only 快速重定时候选【0 HSPICE】

## 6.1 目标

只基于 D0-A1 得到的真实硬下限，构造一个 detection-only 候选微时序，判断**不修改 medium/fine/XOR/capture DFF 本体**时，单通道是否理论上可能满足：

```text
successive S_CLK rise <= 2075 ps
两次真实 Q 稳定观察完成
随后 reset 原 capture DFF
下一 probe 前 reset release/recovery 合法
每个 probe 只有一个真实有效 capture CK edge
M/F 全程静态
```

这里可以提出独立 `det_clk` / runtime timing source 的接口合同，但**不得在本阶段实现 PLL/DLL/复杂时钟发生器**；只定义需要什么边沿，不猜系统如何生成。

## 6.2 必须同时检查的三类瓶颈

### A. capture/Q 判决瓶颈

两次真实 Q 观察能否在 2075 ps 内完成，并给 reset 留出合法时间。

### B. reset/re-arm 瓶颈

当前 probe 清零后，下一 probe 的 capture DFF 是否满足真实 removal/recovery/re-arm，而不是沿用旧 490 ps 常数。

### C. S_CLK / dff_ck 脉宽与重复性瓶颈

必须消费正式 cell timing check。现有 RF 审计已记录 sequential cell 约 1.0 ns CK high/low 最小宽度；2.075 ns 周期距离 2.0 ns 硬理论周期非常近，因此必须显式计算真实 dff_ck high/low margin。不能因为功能波形“看起来能跑”就忽略 timing check。

原 RF 采用了 2.5 ns 以获得约 0.25 ns 半周期宽度余量。D0-A 不要求自动继承 2.5 ns，但如果候选只勉强满足硬 1.0 ns width、明显无法维持既有 guard，应标记为 `TIMING_FRAGILE`，不能直接写成稳健 GO。

## 6.3 单通道候选分类

必须得到以下之一：

```text
SINGLE_PATH_CANDIDATE
    单通道在硬物理约束上存在 <=2075 ps 合法序列，可进入 D0-A3。

Q_OBSERVATION_OR_RETURN_LIMITED
    capture 本体和 S_CLK/CK 可重复，但 Q 双观察、Q_FINAL 回传或 reset 等待阻塞；进入 D0-A4 的 Q 侧本地保持分支。

SENSOR_CLOCK_OR_RECOVERY_LIMITED
    单通道的 S_CLK/dff_ck width、内部恢复或真实 re-arm 本身不能安全达到 2075 ps；禁止仅靠 Q shadow 修补，进入 D0-A5 的交错架构评审。

TIMING_FRAGILE
    数学上能满足硬检查，但 margin 仅处于极窄区、无法得到可实现 guard；不得进入完整 D0 FSM，优先评估 D0-A4 或 D0-A5。
```

生成候选 timing contract 和完整不等式证明；本阶段 HSPICE 必须为 0。

---

# 7. D0-A3 —— 单通道候选的最小连续 multi-probe 物理验证【仅在 A2 有候选时执行】

只有 `SINGLE_PATH_CANDIDATE` 才允许执行。若 A2 已判定 clock/recovery limited，禁止为了“试试看”跑这一阶段。

## 7.1 场景预算

新增 HSPICE 默认只允许 **4 个核心场景**，最多 **2 个**额外边界诊断，总上限 6；不得 sweep。

核心场景：

```text
1) 0.95 V / L2 / 无 droop / 连续 >=3 probes
2) 1.10 V / L2 / 无 droop / 连续 >=3 probes
3) 0.95 V / L2 / Vdroop=0.86 V / total pulse=3002 ps / T0 最坏相位附近
4) 1.10 V / L2 / Vdroop=0.96 V / total pulse=3002 ps / T0 最坏相位附近
```

只有核心场景出现单一明确边界问题时，才允许新增不超过 2 个局部诊断；不得演变成相位/时长大扫描。

## 7.2 测量与判据

每个场景必须记录每一个 probe 的：

```text
S_CLK rise/fall
真实 dff_ck rise/fall 和 edge count
CK high/low width
reset release/assert crossing
Q 第一次/第二次观察值和稳定性
reset 后 Q 清零
下一次 probe 重新 capture
M/F 是否全程不变
是否出现 extra CK edge
是否出现 reset/S_CLK 顺序反转
```

仍使用当前本地 `VDD_MONITORED` 归一化 crossing 语义，不得退回旧固定高电平测试平台。

## 7.3 Gate

```text
SINGLE_PATH_GO
    P<=2075 ps，两个基准无误报，两个目标 droop 可重复检测，双 Q 观察、reset/re-arm、CK timing check 均成立。

TIMING_FRAGILE
    功能通过但 pulse-width/interface/recovery margin 不能形成可信实现余量；转 D0-A4/A5，不进入完整 D0。

SINGLE_PATH_FAIL
    真实连续 probe 破坏 capture、reset 或目标检测；根据根因转 D0-A4 或 D0-A5。
```

禁止为了让单通道过门而修改 T0 coverage requirement。

---

# 8. D0-A4 —— Q 侧本地双观察 / 结果保持最小结构【仅当根因确实在 Q 观察/回传/复位等待】

如果 A2/A3 证明 S_CLK/dff_ck/capture 本体可以在目标 cadence 工作，而阻塞来自 PD_CTRL 等待 Q_FINAL、两次观察完成后才能清零等问题，则优先研究这一最小结构；如果根因是 sensor clock/recovery，**跳过本阶段**。

## 8.1 架构原则

优先从**现有 capture DFF 的 Q 输出**分支 detection-only 观察结构，而不是给 XOR、D、CK 再加负载：

```text
原有 XOR/medium/fine -> 原 capture DFF -> Q
                                      |-> local observation 1
                                      |-> local observation 2
                                      |-> stable/sticky result hold
                                                   |
                                                   +-> 较慢返回 PD_CTRL
```

目的：在本地完成两次独立 Q 稳定观察并把结果保持住，之后原 capture DFF 可以尽早 reset/re-arm，而不是等待较慢的跨域回传或 PD_CTRL 采样。

## 8.2 先做 0 HSPICE 架构合同

必须先回答：

```text
observer 放在 PD_SENSE、本地边界还是可信供电侧的理由
两个 observation 是否真的是独立时刻，而不是复制同一位
observer 时钟/采样来源
sticky result 的 reset/clear 语义
原 Q 增加的输入负载
掉电/严重 droop 时的 fail-safe 行为
如何不破坏 H0 校准时的 Q_FINAL 既有语义
如何保证新增逻辑仅在 DET ownership 后参与
```

H0/M1 本体仍不修改。可以新增 detection-only wrapper/sidecar，但必须保持 CAL 路径完全旁路。

## 8.3 负载与时序验证

先用已有 Liberty/CDL/静态信息做 Q 驱动负载预算。只有确认结构合理后才允许极少量任务自有电气验证：默认 4 个以内，优先比较“原 Q 负载”和“新增 observer Q 负载”在两个正式基准/目标 L2 点上的 tCQ、Q 稳定、capture 判决和连续 reset/re-arm。不得重新扫 M0/T0 trip map。

如果新增 Q 负载导致原 capture 判决、trip ordering 或 T0 目标窗口发生不可接受漂移，必须停止；不能直接继承旧 T0 结论。

## 8.4 Gate

```text
Q_LOCAL_HOLD_GO
    不改 XOR/D/CK/medium/fine，本地双观察+保持成立，原 capture 可按 <=2075 ps cadence 重置并重复，旧 CAL 语义不受影响。

Q_LOCAL_HOLD_FAIL
    Q 负载、供电、采样或 reset 问题仍阻塞；进入 D0-A5。
```

本阶段仍不实现完整 alarm/heartbeat/FSM。

---

# 9. D0-A5 —— 单通道无法安全满足时的交错架构评审【默认 0 HSPICE】

只有 A2/A3 证明 `SENSOR_CLOCK_OR_RECOVERY_LIMITED`，或 A4 已失败，才允许进入。

## 9.1 先算最少交错通道数，不要直接复制三套 sensor

从已经验证/提取的单通道最小安全周期 `P_lane_verified` 计算：

```text
N_min = ceil(P_lane_verified / 2075 ps)
```

例如：只有当最终确认必须保留当前 5700 ps one-shot 非重叠周期时，才有：

```text
N_min = ceil(5700 / 2075) = 3
```

这个 `3` 只是由当前 one-shot 参考得到的示例，**不是预设最终架构**。如果 A1/A3 证明单 lane 可以安全做到 3.5~4.0 ns，则可能只需要 2 lane；如果单 lane 已能做到 <=2075 ps，则根本不需要 interleave。

## 9.2 必须比较的候选层级

按改动从小到大比较：

```text
A) 交错 capture/结果保持结构，尽量共享现有 sensing path
B) 双/多 capture bank，单独 reset/re-arm，各 lane 交错使用
C) 独立 sensor lane time-interleave
```

必须逐项说明：

```text
是否给 XOR/D/CK 增加负载
是否改变原 sensor 物理 trip
每 lane 是否需要独立校准
M/F code 能否共享
各 lane 是否共享同一 VDD_MONITORED
aggregate probe phase 如何定义
面积/功耗开销
对 H0/M1 ownership 的影响
T0 单-probe evidence 能否继承、需要哪些最小新增验证
```

## 9.3 本阶段默认只做架构选择

D0-A5 默认 HSPICE=0，只输出推荐结构和后续独立实现计划。禁止在同一轮里未经新计划直接改 medium/fine/XOR 或复制整套 sensor 并跑大量仿真。

若需要真正实现 interleave，发布 `ARCHITECTURE_ESCALATION_REQUIRED` 并单独建立下一份 plan。

---

# 10. D0-A6 —— 最终 Gate、合同与 D0 正式实现交接

如果 A3 `SINGLE_PATH_GO` 或 A4 `Q_LOCAL_HOLD_GO`，发布：

```text
analysis/d0_runtime_fastpath/contract/D0_RUNTIME_FASTPATH_CONTRACT.json
analysis/d0_runtime_fastpath/reports/D0_A_GATE_STATUS.json
reports/FTC_D0_RUNTIME_FASTPATH_ARCHITECTURE_CLOSURE.md
```

合同至少包含：

```text
最终 runtime probe period 及其上限关系
probe reference event
S_CLK / dff_ck high-low width
两次 Q observation 时刻及物理依据
reset assert/release/re-arm 时序
连续 probe 的最坏时序余量
目标威胁范围
无 droop false-positive 结果
目标 droop detection 结果
使用的 power-domain crossing 抽象
新增/复用/重解析 HSPICE 账本
冻结的 sensor/H0/M1/T0 SHA256
```

**不要改写 T0 原始结论。** 新合同应写成“D0-A 满足 T0 下游条件”，而不是把 T0 的 `CONDITIONAL_GO` 历史重新改成另一种过去状态。

如果没有任何最小结构满足要求，则最终状态只能是：

```text
ARCHITECTURE_ESCALATION_REQUIRED
```

并保留清楚的失败根因，不得继续写完整 D0 FSM。

---

# 11. D0-A 最终判门标准

## 11.1 GO

至少全部满足：

1. `P_runtime <= 2075 ps`；
2. 两个正式基准电压下均有真实连续 probe 证据；
3. 目标 L2 / 3002 ps droop 的 100% full-phase cadence 合同未被放宽；
4. 每次 probe 只有预期 capture edge，无新二次 CK；
5. 两次真实 Q 独立稳定观察成立；
6. reset/re-arm 对下一次 capture 合法；
7. CK high/low timing check 合法并报告真实 margin；
8. 无 droop 连续运行无误报；
9. M/F 在 DET runtime 全程静态；
10. H0/M1 CAL 路径未被新逻辑影响；
11. 没有无意义重跑既有 HSPICE；
12. 所有物理接口仍明确区分“理想验证抽象”和“未来真实跨电源域实现”。

## 11.2 TIMING_FRAGILE

若功能上能达到 2075 ps，但只能依赖极窄 CK width/recovery/interface margin，或尚缺真实跨域接收器时序闭合，则不得把结果称为正式 GO；保持 `TIMING_FRAGILE`，继续最小架构改进。

## 11.3 ARCHITECTURE_ESCALATION_REQUIRED

以下任一成立：

```text
单通道物理 S_CLK/CK/recovery 无法达到目标
Q-side local hold 也无法解决根因
新增负载破坏既有 sensing/trip 语义
需要修改 medium/fine/XOR/capture 拓扑
需要多 lane/interleave 才能满足
```

则必须停止本计划并建立独立 interleave/sensor architecture plan。

---

# 12. 推荐目录

```text
delay_chain/ftc/analysis/d0_runtime_fastpath/
├── baseline/
│   └── frozen_input_sha256.json
├── a1_physical_budget/
│   ├── physical_timing_inventory.csv
│   ├── physical_timing_budget.json
│   └── evidence_reuse_manifest.json
├── a2_single_path_candidate/
│   ├── candidate_timing_contract.json
│   └── feasibility_summary.json
├── a3_multi_probe_validation/
│   ├── scenario_manifest.json
│   ├── results.csv
│   └── summary.json
├── a4_q_local_hold/
│   ├── architecture_contract.json
│   ├── load_budget.json
│   └── validation_summary.json
├── a5_interleave_review/
│   ├── lane_count_analysis.json
│   └── architecture_comparison.md
├── contract/
│   └── D0_RUNTIME_FASTPATH_CONTRACT.json
└── reports/
    └── D0_A_GATE_STATUS.json
```

大体积 HSPICE deck/listing/waveform 继续放 task-owned run 目录并忽略，只提交必要 manifest、紧凑 CSV/JSON、报告和可重复脚本。

---

# 13. 严格逐阶段执行顺序

```text
D0-0   冻结 one-shot timing feasibility                  ARCHITECTURE_REVIEW，已完成
  ↓
D0-A0  冻结 D0-0/T0/M0/M1/PD1/RF 权威输入                0 HSPICE
  ↓
D0-A1  拆分真实物理下限 vs 协议等待                       优先 0 HSPICE
  ↓
D0-A2  构造单通道 fastpath 微时序并分类根因               0 HSPICE
  ↓
  ├─ SINGLE_PATH_CANDIDATE
  │      ↓
  │   D0-A3  极小 multi-probe 物理验证                    <=4 核心，最多6
  │      ├─ SINGLE_PATH_GO -> D0-A6
  │      ├─ Q/return/reset limited -> D0-A4
  │      └─ clock/recovery limited -> D0-A5
  │
  ├─ Q_OBSERVATION_OR_RETURN_LIMITED / TIMING_FRAGILE
  │      ↓
  │   D0-A4  Q侧本地双观察 + result hold 最小结构
  │      ├─ Q_LOCAL_HOLD_GO -> D0-A6
  │      └─ FAIL -> D0-A5
  │
  └─ SENSOR_CLOCK_OR_RECOVERY_LIMITED
         ↓
      D0-A5  计算 N_min 并做 interleave 架构评审
         ↓
      ARCHITECTURE_ESCALATION_REQUIRED，另立计划

D0-A6  发布 runtime fastpath 合同和最终 Gate
  ↓
后续 D0-B 才允许实现 runtime FSM / alarm / heartbeat / timeout
```

---

# 14. 宏观防跑偏原则

Codex 在整个 D0-A 中必须始终遵守：

> **不要把“当前 one-shot 调度失败”误写成“传感器物理机制失败”，也不要把“旧采样时刻”误写成“不可缩短的物理下限”。先从已有晶体管证据中抽取真实 CK/Q/reset/recovery 物理边界，再决定单通道是否可重定时。若只卡 Q 观察/回传，优先在原 capture DFF 的 Q 侧做 detection-only 本地双观察与结果保持，避免加载 XOR/D/CK；若真正卡在单通道 S_CLK/CK 脉宽或恢复，则按 `N_min=ceil(P_lane_verified/2075 ps)` 计算最少交错通道数，禁止继续用复杂 FSM 硬压物理时序。任何时候都不得通过降低 T0 的 100% full-phase 目标、重跑大量旧场景、修改 H0/M1、替换真实 DFF Q 判决或未经授权改 sensor 核心来获得表面 GO。**

本计划结束前不实现完整 D0。只有 fastpath 物理/时序架构真正闭合后，下一阶段才是 D0-B：运行时状态机、报警锁存/清除、heartbeat、stuck-Q、timeout 和系统状态接口。
