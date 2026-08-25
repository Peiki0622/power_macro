# FTC D0-BR：合法捕获事件、共享传感路径重装载与最小交错架构闭合计划

## 0. 计划定位

本计划替代本文件上一版“直接从双 capture bank 开始评审”的推进方式，但保留其历史提交作为证据。最新权威入口提交为：

```text
3c8cf2861b0f4ad7bb83135fc860d8ff0d36bfdf
```

D0-A 已发布：

```text
ARCHITECTURE_ESCALATION_REQUIRED
```

并确认两个正式 T0 L2/3002 ps target 点中：

```text
0.95 V / L2 / Vdroop=0.86 V：真实 dff_ck high = 519.665 ps
1.10 V / L2 / Vdroop=0.96 V：真实 dff_ck high = 301.263 ps
```

当前正式 capture cell `DFFRPQ_X0P5M_A9TR40` 的已审计时序模型要求：

```text
CK high     >= 1000 ps
CK low      >= 1000 ps
reset width >= 1000 ps
recovery    >= 1000 ps
removal     >=  500 ps
```

因此 D0-BR 的宏观任务不是“写更快的 D0 FSM”，也不是“直接复制两个 DFF”，而是依次回答三个更基础的物理问题：

1. **同一个冻结 sensing path 能否真的每 <=2075 ps 接受一次新的 probe launch，并重新产生一组干净、唯一的 sensing/capture event？**
2. **若共享 sensing path 可以达到该 cadence，怎样在尽量保持原 raw `dff_ck` 上升沿判决语义的前提下，把 301~520 ps 的非法窄 CK event 转换成满足正式 DFF timing check 的合法 capture pulse？**
3. **在合法 capture event 已经成立以后，一个 capture context 是否仍因 Q 观察、reset width、recovery 等无法每 2075 ps 自身复用；若不能，最少需要几个交错 capture context，且修改后的架构还能否重新证明 T0 要求的 100% full-phase coverage？**

只有这三个问题全部闭合后，才允许进入后续 D0-C runtime controller/alarm/heartbeat/timeout 实现。

---

# 1. 必须保持的正确物理理解

当前冻结比较器的本质是：

```text
xor_29 ---------------------------------------> capture D
   |
   +-> medium delay -> fine load -> raw dff_ck -> capture CK
```

因此真正的检测时间阈值由以下相对时间决定：

```text
D_ref = t(raw_dff_ck rise) - t(xor_29 rise)
```

这意味着任何新的 capture-event 电路都不能只关心“把脉冲变宽”，还必须量化它对有效 capture 上升沿位置造成的偏移。若新的合法时钟上升沿比 raw `dff_ck` 明显后移，则实际检测阈值、M/F->trip 关系和 T0 phase window 都可能改变。

同时必须保持以下结论：

```text
400 MHz / 2.5 ns 是已经闭合的 CAL/H0/M1 控制时钟合同
它不是 D0 runtime probe cadence
T0 runtime coverage 要求仍为 successive probe launches <=2075 ps
```

不得通过修改 400 MHz 校准时钟、降低 T0 100% full-phase 要求或把 2.075 ns 改回 2.5 ns 来“解决”D0-BR。

---

# 2. 冻结边界

除本计划明确授权的 detection-only 新结构外，以下输入全部只读：

```text
FTC_SENSOR 的 4-RVT/0-LVT sensing topology
sensor tap29
medium N=16
medium delay/mux
fine driver/load, K=10
现有 M/F codebook
原 XOR2_X0P5M_A9TR40 sensing node
原 DFFRPQ_X0P5M_A9TR40 cell 类型
H0 ownership handoff
M1 static margin configuration
T0 threat/phase/cadence contract
D0-A physical timing evidence
PD1 power-domain contracts
RF sequential-cell timing audit
```

尤其禁止 Codex 因为仓库中存在其它 30-bit capture、latch、Vernier 或历史结构就自动替换当前正式 transistor sensor。

允许研究：

```text
PD_SENSE 内 detection-only capture event legalizer
PD_SENSE 内 detection-only capture bank
Q 侧本地结果保持/观察接口
只为验证新结构而增加的最小 isolation/buffer/gating
```

但这些都必须经过本计划 Gate，不能一步直接落成完整 runtime RTL。

---

# 3. 全阶段禁止事项

D0-BR 结束前禁止：

```text
重跑完整 startup calibration
重跑 M0/M0-E 全 surface/trip sweep
重跑 T0-2/T0-3/T0-4/T0-5/T0-6 全 campaign
重跑 H0/M1/RF/XA 完整流程
实现最终 D0 FSM/alarm/heartbeat/timeout/status
修改 H0 或 M1 已冻结子模块
修改 medium/fine/XOR sensing topology
换 capture DFF cell family
直接复制完整 sensor lane
直接上 DLL/PLL/复杂 clock generator
把两个同样的 301~520 ps raw dff_ck 简单接到两个 DFF
忽略正式 $width/$recrem timing check，只看功能波形
用 R_ps/XOR pulse 代替真实 DFF Q decision
用一个 Q 样本复制两份伪装“两次独立观察”
把 T0 100% full-phase 改成平均覆盖率
```

若任何阶段发现必须突破这些边界，立即停止并发布独立 `ARCHITECTURE_ESCALATION_REQUIRED`，不得自行扩题。

---

# 4. 证据复用与 HSPICE 纪律

严格按以下顺序取证：

```text
已有 JSON/CSV/report 能回答
    -> 直接消费，0 HSPICE
已有 retained listing/measure 能回答
    -> 只重解析，0 HSPICE
新结构尚未加入但可由 Liberty/CDL/capacitance 静态判断
    -> 先做静态筛选，0 HSPICE
只有新结构或新的 repeated-probe 问题无法由历史证据回答
    -> 才允许最小 task-owned HSPICE
```

每个阶段必须发布：

```text
new_hspice_scenarios
reused_hspice_scenarios
reparsed_hspice_scenarios
electrically_equivalent_reuse_scenarios
forbidden_flow_runs
```

源码 hash 漂移不构成重跑电气仿真的理由。历史场景只有在电气拓扑、激励或必须观测的量真正发生变化且旧 listing 无法回答时才可重跑。

---

# 5. D0-BR0：冻结 D0-A/T0/M0/M1/PD1/RF 输入【0 HSPICE】

## 5.1 目标

重新 hash 并绑定至少：

```text
delay_chain/ftc/analysis/d0_runtime_fastpath/a1_physical_budget/physical_timing_budget.json
delay_chain/ftc/analysis/d0_runtime_fastpath/a2_single_path_candidate/candidate_timing_contract.json
delay_chain/ftc/analysis/d0_runtime_fastpath/a5_interleave_review/lane_count_analysis.json
delay_chain/ftc/analysis/d0_runtime_fastpath/reports/D0_A_GATE_STATUS.json
delay_chain/ftc/analysis/t0_transient_droop/contract/T0_DOWNSTREAM_D0_TIMING_CONTRACT.json
delay_chain/ftc/analysis/m0_detection_margin_characterization/probe_contract/single_probe_contract.json
delay_chain/ftc/controller/refrequency/library_audit/sequential_cell_timing_capability.json
delay_chain/ftc/controller/pd1_power_domain_interface/crossings/*.json
delay_chain/ftc/controller/m1_detection_margin/contract/M1_DOWNSTREAM_T0_D0_HANDOFF.json
```

必须确认：

```text
D0-A decision = ARCHITECTURE_ESCALATION_REQUIRED
T0 Pmax_coverage = 2075 ps
P_lane_verified = null
current blocking root cause includes illegal raw dff_ck high width
DFFRPQ_X0P5M_A9TR40 has 1 ns CK high/low and reset-width checks
```

## 5.2 Gate

```text
D0_BR_BASELINE_READY
```

否则停止。

---

# 6. D0-BR1：共享 sensing path 的 2.075 ns 重装载能力先行判门【优先 0 HSPICE】

这是本计划新增的最前置硬门。**如果共享 sensor 自己不能每 <=2075 ps 接受下一次 S_CLK rise，则 capture bank 再多也没有意义。**

## 6.1 必须区分的两种恢复

不要把 capture DFF reset/recovery 与 sensing path re-arm 混在一起：

```text
A. capture-context recovery
   Q observation -> reset -> recovery -> next capture for the same DFF

B. sensing-path recovery
   S_CLK rise -> XOR/medium/raw_dff_ck event -> S_CLK fall -> RVT/LVT/XOR/medium/fine 回到可生成下一次 rising-event 的初态
```

D0-BR1 只回答 B。

## 6.2 先重解析已有证据

从 M0/T0/D0-A retained listing/measure 中尽可能得到：

```text
S_CLK rise -> xor_29 rise/fall
S_CLK rise -> medium_out rise/fall
S_CLK rise -> raw dff_ck rise/fall
S_CLK fall 后是否产生 falling-edge induced second raw CK event
第二事件何时结束
recovery endpoint/tail 的已有低电平证据
```

必须回答：现有证据是否已经能够证明：

```text
下一次 S_CLK rise 距上一次 S_CLK rise <=2075 ps
```

时，所有会参与下一次比较的 sensitive nodes 已经回到合法初态，并且下一次 rising probe 不与上一 probe 的 falling wavefront 混叠。

D0-A 已看到 post-reset second CK edge，不能把它忽略。

## 6.3 只有证据不足时允许两个新 sensor-only 连续边沿诊断

若历史 listing 无法闭合 shared-path re-arm，最多允许 **2 个** task-owned HSPICE diagnostics：

```text
0.95 V / 正式 L2 M/F / target electrical condition
1.10 V / 正式 L2 M/F / target electrical condition
```

目标不是重新做 T0 detection sweep，而是只验证共享 sensing path 能否在 `P_probe=2075 ps` 下生成两个相互独立、无混叠的 rising-probe raw events。

诊断中原 capture DFF 可以保持 reset，使测试只聚焦 sensing path。必须测：

```text
S_CLK rise0/fall0/rise1
xor_29 rise/fall sequence
medium_out rise/fall sequence
raw dff_ck rise/fall sequence
每个 probe 对应的 raw event edge count
falling-edge induced event
每个 sensitive node 上前一波前是否在后一波前到达该节点前结束
rise1 后第二个 rising probe 的每波前 D_ref 是否仍定义清晰
```

S_CLK fall 时刻必须由已有物理事件完成时间构造，不允许做 broad duty-cycle sweep。若只有靠极窄、相互重叠的 rising/falling wavefront 才能勉强工作，则分类为 `TIMING_FRAGILE`，不要继续 capture-bank 实现。

## 6.4 固定占空比 Gate

只允许以下结果：

```text
SHARED_SENSOR_CADENCE_FIXED_FALL_GO
    同一个 sensing path 可以在 <=2075 ps successive launches 下可靠 re-arm。

SHARED_SENSOR_CADENCE_FIXED_FALL_FAIL
    已绑定的固定 ``S_CLK fall offset`` 不能使连续 launch 分离；这只是否定该占空比，
    不是对全部合法 fall timing 的物理否定。

SHARED_SENSOR_TIMING_FRAGILE
    功能上勉强存在，但依赖极小 re-arm/wavefront margin；同样只是否定该固定占空比，
    必须进入 D0-BR1R，不得进入 capture-bank。

SHARED_SENSOR_CADENCE_PHYSICALLY_BLOCKED
    仅当 D0-BR1R 的有限、物理导出的 fall retiming 搜索以同节点 E0/EF/E1 波前分离判据
    证明两个正式 target 均无法在 2075 ps 周期内独立传播时成立；capture-bank-only 路线才终止。
```

`SHARED_SENSOR_CADENCE_FIXED_FALL_FAIL` 或固定占空比的 `SHARED_SENSOR_TIMING_FRAGILE`
必须先进入 D0-BR1R；不得仅凭固定占空比结果进入 multi-sensor-lane 或 capture bank。
只有 `SHARED_SENSOR_CADENCE_PHYSICALLY_BLOCKED` 才进入独立 **multi-sensor-lane interleave**
计划，并根据实际 `P_sensor_verified` 计算：

```text
N_sensor_min = ceil(P_sensor_verified / 2075 ps)
```

禁止在本计划中直接复制 sensor。

---

## 6.5 D0-BR1R：固定拓扑的有限 S_CLK falling-edge retiming【优先复用；最多 6 个新 HSPICE】

### 6.5.1 目的与冻结边界

BR1 的 `1687.575705 ps` fall offset 是由已测 primary raw-CK fall 加 25 ps 得出的单一
保守占空比。旧的 source-completion-window 判门曾将其标为 collision；修正后该 retained
endpoint 因只观测到两个 node-fall 而是**部分观测**，既不能证明该固定 fall 通过，也不能证明
collision，更不能说明共享 sensing path 在所有合法 source 高/低时间分配下都不能满足 2075 ps。

BR1R 唯一允许改变的是第一笔 source 的 falling edge：

```text
S_CLK rise0  = 冻结 T0 launch
S_CLK rise1  = rise0 + 2075 ps（严格不变）
S_CLK fall0  = rise0 + one approved retiming offset
M/F、4-RVT/0-LVT/tap29/XOR/medium N=16/fine K=10/DFF input load 均不变
```

capture DFF 继续保持 reset asserted，只保留真实 D/CK 负载；不得加入 pulse legalizer、
capture bank、runtime FSM、sensor copy 或任何理想 delay。不得重跑 M0/T0/H0/M1/RF/XA。

### 6.5.2 先复用既有 BR1 证据【0 HSPICE】

对两个 retained `1687.575705 ps` deck/listing 重新解析。禁止把全局 `rise1/rise2/rise3`
序号直接当作 source-time window 的 probe 标签，也禁止要求一个 source 事件必须在
`[rise0,fall0)`、`[fall0,rise1)` 或 `[rise1,stop)` 内走完整条链。应按真实波前和已冻结
拓扑重建：

```text
E0 = S_CLK rise0 引起的 probe0
EF = S_CLK fall0 引起的 falling-wave
E1 = S_CLK rise1 引起的 probe1

每条波前：xor_29 -> medium_out -> raw_dff_ck
```

同一节点上的连续脉冲序列（而不是 source rise1 时该节点的瞬时电平）是判门对象：E0/EF/E1
必须按 rise/fall 交替、不可合并或重叠，且前一脉冲 fall 到后一脉冲 rise 必须为正并保有明确
低电平裕量。EF 可在 E1 的 source rise 后仍处于 medium/raw 阶，只要 EF 在 E1 到达**同一节点**
之前结束。分别报告每条波前的 `D_ref=t(raw_dff_ck rise)-t(xor_29 rise)`；其变化只能在同节点
分离和拓扑顺序通过后归为 transient-supply 物理延迟变化，不得把 T0 的 25 ps phase 搜索精度
当作 repeated-probe D_ref 漂移阈值。

### 6.5.3 有限 retiming 集合【最多 6 个新 HSPICE】

只使用已有 BR1 两个正式 target，并对两个 target 使用同一组三个 source high-width：

```text
750 ps   = 已有两个 target 中最慢 probe0 XOR rise 后 100 ps 的 25 ps 网格点
1000 ps  = 750 ps 与 1250 ps 的唯一中点
1250 ps  = 已有两个 target 中最慢 probe0 raw_dff_ck rise 后 100 ps 的 25 ps 网格点
```

这不是 duty-cycle sweep：三个点分别检查 probe0 XOR 已建立、两条波前之间的中间释放、以及
probe0 raw CK 已建立后的释放。BR1 已有的 `1687.575705 ps` retained deck 是“primary raw CK
fall 后释放”端点证据，只重解析、不重跑。BR1R 因此最多新增 `3 offsets × 2 targets = 6`
个 task-owned HSPICE scenarios；不得添加第三个电压、M/F code、phase、hold 或拓扑变体。

每个新 deck 必须观测至少六个 rise 和六个 fall crossing，避免隐藏第四个边沿。输出只能保留
在 `delay_chain/ftc/runs/d0_interleaved_capture/br1r_fall_retiming/`。

### 6.5.4 同节点波前 Gate（0-HSPICE 重新判门）

单个 target/offset 只有同时满足以下条件才是 `WAVEFRONT_SEPARATION_PASS`：

1. E0/EF/E1 在 XOR、medium、raw_dff_ck 中均有完整 rise/fall crossing，且每条波前保持
   `xor -> medium -> raw_dff_ck` 的传播顺序；
2. 每个节点内 E0→EF→E1 的 rise/fall 顺序正确，脉冲不合并、不重叠；
3. 对每个节点的 E0→EF 与 EF→E1，`later rise - earlier fall` 为正，且至少保留 25 ps 的独立
   low-level separation margin；这个 25 ps 是显式的同节点分离 guard，不是 phase-search 精度；
4. 每条波前的 raw `D_ref` 定义且为正。报告 E0/EF/E1 间的 D_ref 变化，但不设以 T0 25 ps 为
   依据的漂移拒绝阈值；在条件 1--3 通过时，变化分类为 transient-supply physical-delay variation，
   不分类为 wavefront collision；
5. `S_CLK rise1` 前的单点节点电压快照只保留为诊断，不得作为失败条件。唯一相关条件是 EF 必须
   在 E1 到达该**同一节点**之前结束。

`1687.575705 ps` retained endpoint 只有两个 node-fall measure 时必须标为观测不完整，不能把
未测的 E1 fall 伪称为 pass，也不能把 EF 晚于 source rise1 伪称为 collision。

若同一个 retiming offset 在两个正式 target 都 `WAVEFRONT_SEPARATION_PASS`，发布：

```text
SHARED_SENSOR_CADENCE_RETIMING_GO
```

此时只授权进入 D0-BR2 的合法 capture event/pulse legalizer 研究，仍不授权 bank 或 runtime
FSM。若三个 retiming 点在修正后的同节点判据下仍证明两个 target 均不能独立传播，才发布：

```text
SHARED_SENSOR_CADENCE_PHYSICALLY_BLOCKED
```

并另立 multi-sensor-lane 计划；`P_sensor_verified` 未经更长周期证据不得填写，
`N_sensor_min` 不得伪造为数字。

---

# 7. D0-BR2：合法 capture event 形成结构筛选【仅 BR1R=RETIMING_GO，0 HSPICE】

## 7.1 目标

在共享 sensor cadence 已经成立的前提下，研究最小 detection-only 结构，把：

```text
raw dff_ck high = 301~520 ps
```

转换为满足：

```text
capture CK high >= 1000 ps
capture CK low  >= 1000 ps
```

的合法 DFF capture event，同时尽可能保持 raw `dff_ck` 上升沿的比较语义。

## 7.2 首选方向：只延后 falling edge，不主动等待新的 rising edge

优先筛选标准单元可实现的“直接支路 + 延迟支路合并”型 pulse extension，例如概念上：

```text
                     +----------------------+
raw_dff_ck ----------|-------------------+  |
                     |                   |  |
                     +-> delay chain ----+-> OR-like merge -> legal_ck
```

目标是：

```text
legal_ck rise ≈ raw_dff_ck rise + 一个最小组合门延迟
legal_ck fall = 延迟支路决定，从而把 high pulse 拉长
```

这只是架构模板，不允许 Codex 未审计库单元就直接固定 OR2/门数。

优先级：

```text
1. 已有/已验证标准单元组合式 pulse extension
2. 已有 library 中明确有 timing model 的专用 clock/event cell
3. 最小状态型 event hold（仅当前两类无法成立时）
```

任何状态型候选若自身又要求输入 pulse width >= raw 301~520 ps 以上，则直接淘汰，不能把同一个问题转移到另一个 sequential cell。

## 7.3 禁止的“修复”

```text
换一个更快 DFF 后忽略正式 timing check
用理想行为 one-shot
自定义模拟延时器/电容单稳态
PLL/DLL
把 PD_CTRL clock 直接替代 raw dff_ck 判决
等到 XOR pulse 结束后再重新采样
```

这些都会破坏全数字标准单元宏的可集成性或改变原比较语义。

## 7.4 bounded library audit

只允许围绕已知 library family 对以下角色做定向审计：

```text
BUF/INV delay element
OR/NOR/AND/AOI/OAI 等可形成单调 pulse extension 的组合单元
已有 clock-gating/event 单元（若现成存在）
```

不得重新扫描整个 PDK 进行大规模 cell discovery。

对每个候选列出：

```text
raw_ck input capacitance
first-edge propagation path
falling-edge extension mechanism
是否有 sequential min-pulse dependency
VDD_MONITORED 下工作语义
是否可能产生额外 edge/glitch
是否可保持在 PD_SENSE
```

最多保留 **1 个 primary candidate** 进入下一阶段；若没有明确 primary，停止，不允许“多个方案都跑 HSPICE 看看”。

## 7.5 Gate

```text
CAPTURE_EVENT_LEGALIZER_CANDIDATE
或
CAPTURE_EVENT_ARCHITECTURE_BLOCKED
```

---

# 8. D0-BR3：交错 capture context 与负载/时序合同【0 HSPICE】

只有 BR2 有唯一候选时执行。

## 8.1 先证明为什么 single capture context 是否足够

必须用正式 timing check 和 D0-A 实测 Q 响应建立单 context reuse budget，至少包含：

```text
capture CK rise -> Q stable
两次独立 Q stable observation aperture
result secured
reset high >=1000 ps
reset release -> next CK recovery >=1000 ps
removal >=500 ps
```

D0-A 最大实测 `CK rise -> Q90` 约 292 ps，可以作为已有物理输入，但旧 200 ps Q1/Q2 spacing 仍只能作为历史 protocol value，不能冒充硬物理下限。

如果仅：

```text
Q stable + reset width + recovery
```

就已经超过 2075 ps，应明确记录 single-context runtime reuse 不可能，而不是继续压缩 FSM。

## 8.2 计算最少 capture context 数量

定义：

```text
P_context_required = 一个 context 从本次 capture 到能够再次合法 capture 的最小有证据周期
N_capture_min = ceil(P_context_required / 2075 ps)
```

若 `P_context_required` 仍不能由 0-HSPICE 合同闭合，则先给出 guarded model lower bound，并在后续 multi-probe 中物理闭合；不能把模型值写成 verified。

优先研究 `N=2`，但只有数学/物理预算支持时才进入两 bank，不能因为 D0-A 曾给出 `ceil(2500/2075)=2` 就默认最终一定是 2。

## 8.3 CAL 兼容性不能只写“逻辑旁路”

新增 capture bank 即使在 CAL 时保持 reset，也会对 sensitive nodes 产生输入电容。因此必须分别估计：

```text
xor_29 新增 D input load
raw_dff_ck/legalizer 新增 CK load
bank select/gating load
pulse-former input load
```

逻辑上必须保持 H0/M1 CAL controls 完全旁路；物理上则必须承认新增负载可能改变 calibration/trip。

必须比较至少两种 D-side 连接思想，最终只选一种：

```text
A. xor_29 直接扇出到多个同型 DFF D
B. 一个最小 isolation buffer 后对称驱动各 bank D
```

若选 B，必须明确 buffer data delay 会改变 comparator relative timing；不能声称它“只是隔离负载”。若选 A，也必须量化额外 input capacitance。

## 8.4 bank clock 分配

必须比较：

```text
A. raw event -> global legalizer -> glitch-free/static bank gate
B. raw event + static bank enable -> per-bank legalizer
```

bank enable/selection 必须在 event 到来前稳定，并只在对应 clock low/idle 区域切换；禁止用普通组合 mux 在活跃 pulse 中切换。

## 8.5 power-domain 位置

优先：

```text
raw sensing / legalizer / capture bank -> PD_SENSE / VDD_MONITORED
Q result hold -> PD_SENSE 或 boundary-local
PD_CTRL 只接收已经保持住的结果
```

这样 runtime cadence 不依赖当前尚未物理闭合的 Q_FINAL return receiver。

仍然使用项目已冻结的理想电源感知跨域验证抽象；不得声称真实 level shifter/isolation 已完成。

## 8.6 输出与 Gate

输出：

```text
b3_capture_context_budget.json
b3_load_budget.json
b3_selected_architecture.json
```

Gate：

```text
INTERLEAVED_CAPTURE_STATIC_CANDIDATE
或
ARCHITECTURE_ESCALATION_REQUIRED
```

静态合同不能闭合时禁止“先仿真看看”。

---

# 9. D0-BR4：最终候选的最小晶体管级单-probe预检【仅 BR3 通过】

这一阶段只验证**一个已经静态选定的完整候选**，不做方案赛马。

## 9.1 两个正式 target 点

默认只新增：

```text
0.95 V / L2 / Vdroop=0.86 V / 3002 ps / 既有 worst-side phase
1.10 V / L2 / Vdroop=0.96 V / 3002 ps / 既有 worst-side phase
```

必须测：

```text
raw_dff_ck rise/fall
legal_ck rise/fall
Delta_t_rise = t(legal_ck rise) - t(raw_dff_ck rise)
legal CK high/low
edge count
glitch count
xor_29 pulse width before/after new load
medium_out timing shift
raw_dff_ck timing shift
capture Q 10/90
reset clear
bank-specific clock isolation
M/F static
```

其中 `Delta_t_rise` 是核心指标，必须同时报告两个电压点，不能只说“pulse width 过了”。

## 9.2 三个 calibration-anchor smoke checks【只有新增负载触及原 sensing nodes 时执行】

若新候选对 `xor_29`、medium/fine output 或原 capture input 增加了不可忽略物理负载，则额外只允许三点：

```text
0.80 V：冻结最终 calibration code 的 lock-hold probe
0.95 V：冻结最终 calibration code 的 lock-hold probe
1.10 V：冻结最终 calibration code 的 lock-hold probe
```

只验证已有 golden final code 在新物理负载下仍保持预期 stable-low lock state。

**不运行完整 coarse/fine calibration search。**

如果三点中任一点翻转，立即停止，发布 `CALIBRATION_COMPATIBILITY_FAIL`；下一阶段必须是 load isolation 或针对受影响 calibration path 的独立最小 requalification plan，不能在本计划里把 calibration code 悄悄改掉。

## 9.3 HSPICE 上限

```text
正式 target = 2
必要 calibration smoke = 最多 3
本阶段总上限 = 5
```

没有参数 sweep。

## 9.4 Gate

```text
SINGLE_PROBE_INTEGRATION_GO
TIMING_FRAGILE
CALIBRATION_COMPATIBILITY_FAIL
CAPTURE_EVENT_FAIL
```

只有第一种进入 BR5。

---

# 10. D0-BR5：连续交错 probe 最小物理验证【仅 BR4=GO】

## 10.1 核心场景仅 4 个

```text
1. 0.95 V / no-droop / >=3 aggregate probes
2. 1.10 V / no-droop / >=3 aggregate probes
3. 0.95 V / L2 / 0.86 V / 3002 ps / target phase / >=3 aggregate probes
4. 1.10 V / L2 / 0.96 V / 3002 ps / target phase / >=3 aggregate probes
```

若 N_capture=2，至少必须出现：

```text
probe0 -> bank A
probe1 -> bank B
probe2 -> bank A
```

从而真实证明 bank A 在两个 aggregate intervals 后可重用。

## 10.2 必须记录

对每个 aggregate probe 和每个 bank：

```text
S_CLK launch/fall
raw sensor event
legal bank CK rise/fall/high/low
edge count
bank selection state
Q response
两次真实稳定 Q observation timepoints
result hold
reset assert/release/width
recovery/removal relation
下一次同-bank capture
M/F static
```

同时再次确认 shared sensing path 在真实 repeated waveform 下没有 rising/falling wavefront collision。

## 10.3 不能把本阶段变成 coverage sweep

BR5 只回答：

> “候选架构能否以目标 aggregate cadence 连续运行，并在两个代表性 target/no-droop 场景下正确工作？”

它还不能回答最终 100% phase coverage，因此 BR5 通过后仍必须执行 BR6。

## 10.4 Gate

```text
MULTI_PROBE_FUNCTIONAL_GO
TIMING_FRAGILE
MULTI_PROBE_FAIL
```

只有第一种进入 BR6。

---

# 11. D0-BR6：修改后架构的 T0 全相位覆盖最小再资格化【必须执行】

这是本计划相对上一版 D0-B 新增的第二个关键 Gate。

原因：T0 的 `Pmax_coverage=2075 ps` 来自**旧 capture/sensing loading 和旧 timing relation**。现在只要加入：

```text
pulse legalizer
bank clock gating
额外 D input load
新的 legal_ck rise delay
```

旧 CLEAN_Q1 phase interval 就不能未经验证直接继承。

## 11.1 不重跑整个 T0

只允许两个正式 cadence target：

```text
0.95 V / L2 / 0.86 V / total pulse=3002 ps
1.10 V / L2 / 0.96 V / total pulse=3002 ps
```

复用原 T0 threat waveform、phase 定义、crossing 判据和 old clean-window bracket。

不重新运行：

```text
T0-2 全矩阵
T0-3 全扫描
T0-4 duration map
T0-5 全 candidate set
L1/L3 recovery special cases
```

## 11.2 只重新闭合新的 CLEAN_Q1 边界

以旧 T0 clean interval 为起点，对新架构做局部 adaptive boundary closure：

```text
先测试旧 left/right boundary 附近
若仍 bracket，则局部二分/细化
精度不得低于原 T0 已发布边界精度
```

如果新边界大幅漂移到旧局部 bracket 之外，不允许扩成无界 phase sweep；停止并发布 `PHASE_WINDOW_REQUALIFICATION_ESCALATION_REQUIRED`。

建议 HSPICE 总预算：

```text
每个 baseline 只围绕 left/right 两个边界
全 BR6 新场景建议 <=16
硬上限 <=24
```

超过上限必须停止并解释为何原 T0 evidence 已无法局部继承。

## 11.3 bank-specific phase window

若 bank A/B 的实际 capture path 不完全等价，必须分别得到：

```text
W_clean_A
W_clean_B
```

不能用一个 bank 的窗口替另一个 bank。

只有在 netlist、load、legalizer、CK path 和 transistor evidence 均证明 A/B 电气等价时，才允许只表征一个 bank并用等价性合同复制窗口。

## 11.4 重新计算 aggregate cadence coverage

对于实际 bank launch sequence，重新执行 periodic interval union。

若 aggregate launch 间隔为 `P_runtime`，必须用新架构真实各 bank 的 clean interval 和实际 launch offset，计算：

```text
full-phase CLEAN_Q1 coverage
maximum non-guarantee interval
Pmax_coverage_new
```

最终硬条件仍为：

```text
Pmax_coverage_new >= 2075 ps
```

若新窗口导致 `<2075 ps`，禁止把结果写成 GO，也禁止降低 T0 requirement；只能：

```text
更快 aggregate cadence + 重新计算所需 bank 数
或
architecture escalation
```

---

# 12. D0-BR7：最终架构 Gate 与 D0-C 交接【0 HSPICE】

只有以下全部成立才能发布：

```text
D0_INTERLEAVED_CAPTURE_GO
```

必须同时满足：

1. BR1R 已在同一 fall timing 下证明两个正式 target 的 shared sensing path 在 successive launch <=2075 ps 下物理可 re-arm；
2. raw 301~520 ps capture event 已转换为正式 timing-check 合法的 bank CK；
3. legal CK high/low 均满足 1 ns，且有报告的真实 margin；
4. `Delta_t_rise` 已量化，未被隐藏；
5. bank count 有 timing budget 与 multi-probe physical evidence，而不是模型猜测；
6. 每个 bank reset width >=1 ns；
7. recovery/removal 合法；
8. 两次真实 Q stable observations 成立；
9. no-droop repeated probes 无误报；
10. 两个正式 L2/3002 ps target repeated probes PASS；
11. CAL golden final-code smoke 在新增负载下未被破坏，或已有独立证据证明新结构不加载 CAL-sensitive nodes；
12. 新架构 CLEAN_Q1 phase interval 已局部重新闭合；
13. `Pmax_coverage_new >=2075 ps`；
14. H0/M1 状态机本体未修改；
15. T0 历史 `CONDITIONAL_GO`、D0-A `ARCHITECTURE_ESCALATION_REQUIRED` 都作为历史证据保留，没有被回写。

发布至少：

```text
delay_chain/ftc/analysis/d0_interleaved_capture/contract/D0_INTERLEAVED_CAPTURE_CONTRACT.json
delay_chain/ftc/analysis/d0_interleaved_capture/reports/D0_BR_GATE_STATUS.json
delay_chain/ftc/reports/FTC_D0_INTERLEAVED_CAPTURE_ARCHITECTURE_CLOSURE.md
```

若任何一项失败，最终状态按根因只能是：

```text
SHARED_SENSOR_CADENCE_PHYSICALLY_BLOCKED
CAPTURE_EVENT_ARCHITECTURE_BLOCKED
TIMING_FRAGILE
CALIBRATION_COMPATIBILITY_FAIL
MULTI_PROBE_FAIL
PHASE_WINDOW_REQUALIFICATION_ESCALATION_REQUIRED
ARCHITECTURE_ESCALATION_REQUIRED
```

不得继续写完整 D0 runtime controller。

---

# 13. 若 BR1R 证明 shared sensor 物理阻塞，正确的下一层架构是什么

只有 BR1R 已在其有限且物理导出的共同 fall timing 集合内，以 topology-ordered、same-node
E0/EF/E1 separation 证明两个正式 target 都无法在 2075 ps 独立传播，才认为同一个 sensing
path 物理阻塞并结束本计划。

此时必须承认：

```text
capture-bank interleave 只能隐藏 DFF reset/recovery
不能隐藏 sensor RVT/LVT/XOR/medium/fine 自身的 re-arm 时间
```

下一份计划应研究完整 sensor-lane interleave：

```text
Lane A: sensor + M/F-equivalent path + capture
Lane B: sensor + M/F-equivalent path + capture
...
```

并先计算：

```text
N_sensor_min = ceil(P_sensor_verified / 2075 ps)
```

但 multi-sensor lane 会引入：

```text
lane mismatch
每 lane calibration/trim 需求
面积/功耗
M/F code sharing 合法性
T0 evidence inheritance 边界
```

所以不能在 D0-BR 中直接实现。

---

# 14. 推荐目录

```text
delay_chain/ftc/analysis/d0_interleaved_capture/
├── baseline/
│   └── frozen_input_sha256.json
├── br1_shared_sensor_cadence/
│   ├── retained_timing_inventory.json
│   ├── shared_sensor_cadence_contract.json
│   └── diagnostic_manifest.json
├── br1r_fall_retiming/
│   ├── retained_fixed_fall_causal_reanalysis.json  # legacy filename; topology-wavefront content
│   ├── retiming_search_contract.json
│   └── diagnostic_manifest.json
├── br2_capture_event_legalizer/
│   ├── candidate_screen.json
│   └── selected_candidate.json
├── br3_capture_context/
│   ├── capture_context_budget.json
│   ├── load_budget.json
│   └── selected_architecture.json
├── br4_single_probe/
│   ├── scenario_manifest.json
│   ├── results.csv
│   └── calibration_smoke.json
├── br5_multi_probe/
│   ├── scenario_manifest.json
│   └── results.csv
├── br6_phase_requalification/
│   ├── phase_boundary_results.csv
│   ├── clean_windows.json
│   └── cadence_coverage.json
├── contract/
│   └── D0_INTERLEAVED_CAPTURE_CONTRACT.json
└── reports/
    └── D0_BR_GATE_STATUS.json
```

run/deck/listing 放：

```text
delay_chain/ftc/runs/d0_interleaved_capture/
```

大体积波形不提交，只保留必要 manifest/measure/CSV/JSON/report。

---

# 15. 严格执行顺序

```text
D0-A
ARCHITECTURE_ESCALATION_REQUIRED
        |
        v
D0-BR0  冻结权威输入                              0 HSPICE
        |
        v
D0-BR1  共享 sensing path 能否 <=2075 ps re-arm    先 0 HSPICE；必要时最多2点
        |
        +-- FIXED_FALL_FAIL --> D0-BR1R（固定拓扑 fall retiming，最多3 offsets×2 targets）
        |                           |
        |                           +-- same-node PHYSICALLY_BLOCKED --> 停止，另立 multi-sensor-lane plan
        |
        v
D0-BR2  合法 capture event/pulse legalizer 筛选     仅 BR1R=RETIMING_GO，0 HSPICE
        |
        +-- BLOCKED --> 停止
        |
        v
D0-BR3  capture context 数量 + load + 时序合同      0 HSPICE
        |
        +-- BLOCKED --> 停止
        |
        v
D0-BR4  最终单一候选 2 个 target 单-probe
        |       + 必要时3个 calibration lock smoke
        |
        +-- FAIL --> 停止
        |
        v
D0-BR5  4个核心连续 aggregate-probe 场景
        |
        +-- FAIL/FRAGILE --> 停止
        |
        v
D0-BR6  仅两个正式 target 的 phase boundary 局部再闭合
        |       + 重新计算 Pmax_coverage_new
        |
        +-- Pmax_new < 2075 ps --> 架构升级，不放宽T0
        |
        v
D0-BR7  D0_INTERLEAVED_CAPTURE_GO
        |
        v
下一阶段 D0-C
才允许 runtime FSM / alarm / heartbeat / stuck-Q / timeout
```

---

# 16. 给 Codex 的最高优先级防跑偏原则

> **不要把“DFF 的 raw CK 太窄”直接等价为“加两个 DFF 就解决”，也不要把一个固定 S_CLK 占空比失败直接等价为共享 sensor 物理失败。先按 E0/EF/E1 波前身份和 XOR→medium→raw_dff_ck 拓扑重新解释既有 BR1 evidence：允许不同波前同时位于不同延迟级，只检查同一节点上前一脉冲是否在后一波前到达前结束。只有 BR1R 在冻结 topology、M/F 与 2075 ps 周期下以该同节点无碰撞判据找不到共同 fall timing，才停止 capture-bank 路线并升级到 sensor-lane interleave。D_ref 的逐波前变化必须报告；T0 的 25 ps phase 搜索精度不是其漂移阈值。共享 sensing path 通过后，才研究最小标准单元 pulse legalizer，并优先保持 raw dff_ck 的上升沿语义、只延后 falling edge；任何新增 legalizer/bank 都必须量化对 xor_29、raw dff_ck 和有效 capture rise 的负载与延迟偏移。再用正式 CK/reset/recovery timing check 计算 capture context 数量，不允许用复杂 FSM 压缩物理恢复。最后必须对修改后的最终架构重新闭合两个正式 L2/3002 ps target 的 CLEAN_Q1 phase boundary 并重新计算 Pmax；旧 T0 的 2075 ps 不能未经重新资格化直接继承。整个过程中优先复用历史 listing/JSON，只有新的 topology 或连续 probe 物理问题才运行最小 HSPICE，绝不重跑已有完整 campaign。**
