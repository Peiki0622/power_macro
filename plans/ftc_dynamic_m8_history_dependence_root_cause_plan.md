# FTC 0.80 V M8 动态异常：一次性根因定位与后续修复分流计划

## 0. 任务定位

本计划承接当前远程最新电气提交：

```text
25b2fba0c61d1192584d37155c5fe3b677846e62
feat(ftc): add dynamic recovery window diagnostic
```

当前正式状态：

```text
Dynamic Recovery Window Repair = NO-GO
Dynamic Startup Calibration Protocol = NO-GO
```

当前唯一发布的诊断停止原因：

```text
diagnostic_q_sequence_changed
```

本计划的目标不是再做一次“试一个 recovery guard（恢复保护时间）看看能不能过”的调参，而是尽量通过：

1. 对已经存在的 2.5 ns 原始动态场景和 3.3 ns 诊断场景进行零仿真深挖；
2. 只新增 **1 个 0.80 V 晶体管级 root-cause matrix（根因矩阵）HSPICE 场景**；
3. 在这 1 个场景中一次性覆盖 predecessor（前序代码）、recovery guard、code-settle（配置稳定时间）、有无前序功能脉冲、reset release（复位释放）以及重复性控制实验；
4. 对 `xor_29 -> medium_out -> dff_ck -> DFF.Q` 分级测量；

来区分下面这些候选根因：

```text
A. 3.3 ns diagnostic schedule（诊断调度）累积拉长导致的协议时间轴耦合；
B. M7 -> M8 / M9 -> M8 的 medium path-selection（中调路径选择）历史依赖；
C. 动态 code-to-delay（代码到延时）非单调/滞回；
D. 2.7 ns 左右 recovery 后仍存在前一 probe 的模拟状态残留；
E. 1.5 ns code-settle guard 不足；
F. fine driver/load 虽然 F=0 但仍对历史状态敏感；
G. DFF reset/capture（复位/捕获）历史依赖；
H. 现有 .measure 事件索引或结果发布错误；
I. HSPICE 长时间轴/累计状态导致的重复性问题。
```

本计划优先回答：

> 同一个 `(M=8,F=0)` 为什么在原始动态场景中可以得到 Q=1，在 3.3 ns diagnostic 的 probe 8 得到 Q=0，而同一个 diagnostic 后面的 probe 10 `(M=8,F=0)` 又恢复为 Q=1？

在这个问题没有被定位之前：

```text
禁止继续实现 FSM
禁止引入 ConfigSkip
禁止引入 bypass
禁止重选 medium/fine 单元
禁止进入 programmable margin
```

---

# 1. 当前已经确定的事实：全部冻结，不允许重新证明

## 1.1 静态真实 DFF 黄金结果

上游 `two_stage_real_dff_hierarchical_calibration` 已经 GO，并且 0.80 V 静态黄金关系为：

```text
M_transition = 9
M_fine       = 8
F_lock       = 1
```

静态 coarse（中调）结果中：

```text
M7 -> Q=1
M8 -> Q=1
M9 -> Q=0
```

所以 M8 是当前 0.80 V 静态边界附近的最后一个 early（偏早）代码。

不得重跑上游 84 个静态场景。

## 1.2 原始 2.5 ns 动态结果

冻结：

```text
recovery_guard = 2.5 ns
13-probe Q      = 1111111110100
coarse Q        = 1111111110
fine Q          = 10
hold Q          = 0
final            = (8,1)
```

原始场景的唯一 failure（失败）来自 recovery quiet tail（恢复安静尾窗），不是 Q、锁点、动态 delay 单调性或 configuration-induced CK edge（配置诱导 CK 边沿）。

## 1.3 3.3 ns recovery diagnostic 结果

冻结：

```text
diagnostic_bound = 3.3 ns
13-probe Q        = 1111111100100
first Q mismatch  = probe 8
probe 8           = (M=8,F=0), Q=0
probe 9           = (M=9,F=0), Q=0
probe 10          = (M=8,F=0), Q=1
```

因此，当前最关键的现象不是简单“配置码 8 永远失败”，而是：

```text
M7 -> M8 : probe 8 发生 Q=0
M9 -> M8 : probe 10 发生 Q=1
```

这构成 transition-history dependence（切换历史依赖）的强候选证据，但尚不能直接定性为硬件历史依赖，因为现有 3.3 ns diagnostic 同时改变了整个累计 schedule（调度时间轴）。

## 1.4 recovery 根因本身已经获得强证据

当前 diagnostic 已经得到 39/39 个有效 return measurement（返回测量），没有 second rise（第二次返回上升）。

0.80 V 最坏：

```text
worst probe = 9
M           = 9
F           = 0
worst node  = dff_ck
return settle after S_CLK fall = 2.474756780 ns
```

因此按已有 repair 合同，候选真实功能 guard 应为：

```text
2.474756780 ns + 0.200 ns = 2.674756780 ns
向上取整到 0.1 ns -> 2.7 ns
```

这里 `2.474756780 ns` 是已经实测的最坏 `dff_ck` 返回下降到 10% VDD 以下的时间；`0.200 ns` 是冻结的安全尾窗；`+` 表示在真实恢复完成后加入保护时间；`2.7 ns` 是按当前 0.1 ns 量化规则得到的候选功能 recovery guard。

**3.3 ns 只是 diagnostic observation bound（诊断观察上界），不得继续作为最终功能 recovery guard。**

---

# 2. 文献启发：只作为待验证假设，不作为结论

He et al. 的可综合 FIA monitor（故障注入监测器）在 Fig. 11 中明确讨论：多级 configurable delay line（可配置延时线）的整体数字代码与真实物理延时不保证天然全局单调。fine/medium/coarse 级的调节范围重叠和 mismatch（失配）可能使“数字配置增加”时真实延时反而下降，因此论文使用 programmable configuration skips（可编程配置跳过）恢复全局单调。

本项目当前现象与该问题有相关性，但存在一个重要区别：

```text
论文典型问题：跨级切换时的全局 code-delay 非单调
当前异常：F=0 固定，medium 内部 M7 -> M8 与 M9 -> M8 可能得到不同 M8 判决
```

因此本计划必须同时区分：

```text
static non-monotonicity（静态非单调）
dynamic non-monotonicity（动态非单调）
hysteresis/history dependence（滞回/历史依赖）
DFF capture dependence（DFF 捕获依赖）
```

在完成根因定位前，禁止直接照搬论文的 ConfigSkip。

---

# 3. 绝对禁止事项

## 3.1 禁止重跑现有电气证据

本任务禁止重新执行：

```text
上游 84 个 two-stage static HSPICE
原始 dynamic_0p95
原始 dynamic_1p10
原始 dynamic_0p80 / 2.5 ns
recovery_diagnostic_0p80 / 3.3 ns
```

这些全部只读。

最终 summary 必须包含：

```text
upstream_static_84_scenarios_rerun = 0
old_dynamic_0p95_rerun             = 0
old_dynamic_1p10_rerun             = 0
old_dynamic_0p80_rerun             = 0
old_recovery_diagnostic_0p80_rerun = 0
```

全部必须为 0。

## 3.2 禁止在定位阶段修硬件

禁止：

```text
改 sensor
改 tap29
改 XOR
改 medium N=16
改 BUF_X0P7M
改 MXT2
改 fine X0P8
改 NOR2_X4A
改 K=10
改 DFF
加 bypass
加 ConfigSkip
加 clock gating
加 update isolation
加理想延时/理想电容
```

## 3.3 禁止盲目 guard sweep

不得：

```text
2.6 ns 跑一次
2.7 ns 跑一次
2.8 ns 跑一次
3.0 ns 再跑一次
```

本任务不允许“试到成功”。

候选功能 guard 固定为已经由 retained diagnostic（保留诊断）推导出来的 2.7 ns；3.3 ns 只作为对照因素和隔离窗口。

---

# 4. 新任务文件

新建：

```text
delay_chain/ftc/scripts/run_dynamic_m8_history_root_cause.py

delay_chain/ftc/analysis/dynamic_m8_history_root_cause/
  requirements.json
  frozen_evidence.json
  retained_2p5_vs_3p3_probe_comparison.csv
  retained_transition_comparison.csv
  root_cause_matrix_contract.json
  root_cause_results.csv
  stage_delay_results.csv
  transition_internal_node_audit.csv
  repeatability_audit.csv
  classification.json
  summary.json

delay_chain/ftc/runs/dynamic_m8_history_root_cause/

delay_chain/ftc/reports/FTC_DYNAMIC_M8_HISTORY_ROOT_CAUSE.md

delay_chain/ftc/tests/test_dynamic_m8_history_root_cause.py
```

不得覆盖旧：

```text
dynamic_startup_calibration_protocol
dynamic_recovery_window_repair
```

旧 NO-GO 必须永久保留。

---

# Phase 0 — 冻结最新基线（0 HSPICE）

Codex 必须确认远程最新 FTC 电气提交仍是：

```text
25b2fba0c61d1192584d37155c5fe3b677846e62
```

如果该提交以后已经出现新的 FTC 电气代码，先审查差异，不得直接执行本计划。

读取并计算 SHA256：

```text
delay_chain/ftc/analysis/dynamic_recovery_window_repair/summary.json
delay_chain/ftc/analysis/dynamic_recovery_window_repair/diagnostic_results.csv
delay_chain/ftc/analysis/dynamic_recovery_window_repair/measured_return_settle.json
delay_chain/ftc/analysis/dynamic_recovery_window_repair/old_failure_map.json
delay_chain/ftc/analysis/dynamic_recovery_window_repair/diagnostic_timing_contract.json
delay_chain/ftc/reports/FTC_DYNAMIC_RECOVERY_WINDOW_REPAIR.md
delay_chain/ftc/scripts/run_dynamic_recovery_window_repair.py

delay_chain/ftc/analysis/dynamic_startup_calibration_protocol/summary.json
delay_chain/ftc/analysis/dynamic_startup_calibration_protocol/probe_results.csv
delay_chain/ftc/analysis/dynamic_startup_calibration_protocol/transition_audit.csv
delay_chain/ftc/analysis/dynamic_startup_calibration_protocol/trajectory_contract.json
delay_chain/ftc/analysis/dynamic_startup_calibration_protocol/timing_contract.json
```

同时找到两个 retained scenario（保留场景）的原始：

```text
2.5 ns old dynamic_0p80 measurement/listing/deck/manifest
3.3 ns recovery_diagnostic_0p80 measurement/listing/deck/manifest
```

全部只读。

生成：

```text
frozen_evidence.json
requirements.json
```

若任何核心 handoff（交接条件）变化：

```text
Dynamic M8 History Root Cause = UPSTREAM_BLOCKED
```

0 HSPICE 停止。

---

# Phase 1 — 先把现有 2.5 ns 与 3.3 ns raw measurement 挖干净（0 HSPICE）

这是防止返工的第一道门。

当前 3.3 ns runner 已经在内存里得到 `probe_result` 和 `transition_result`，但没有完整发布这些结果，只发布了 return measurements（返回测量）。Codex 必须从 retained 3.3 ns scenario 的 measurement 文件重新解析，不重新跑 HSPICE。

对 13 个 probe 全部恢复：

```text
probe_index
M
F
protocol_phase
launch_time
q_read_time
xor_rise
xor_fall
ck_rise
Q_voltage
Q_logic
W_xor_ps
D_total_ps = ck_rise - xor_rise
extra_ck_edge
```

其中：

```text
D_total_ps = t_ck_rise - t_xor_rise
```

`D_total_ps` 表示 `xor_29` 到 `dff_ck` 的真实总传播延时；`t_ck_rise` 是 DFF.CK 的有效上升时间；`t_xor_rise` 是同一 probe 的 XOR 有效上升时间；`-` 表示传播时间差。

然后和原始 2.5 ns 的相同 probe 逐行配对，输出：

```text
retained_2p5_vs_3p3_probe_comparison.csv
```

至少包含：

```text
probe_index
M
F
Q_2p5
Q_3p3
Q_changed
D_total_2p5_ps
D_total_3p3_ps
delta_D_total_ps
W_xor_2p5_ps
W_xor_3p3_ps
delta_W_xor_ps
launch_shift_ns
```

重点必须单独发布：

```text
probe 7 : M7,F0
probe 8 : M8,F0 / M7->M8
probe 9 : M9,F0
probe10 : M8,F0 / M9->M8
probe11 : M8,F1
probe12 : M8,F1 hold
```

同时恢复两套 transition audit（切换审计）并输出：

```text
retained_transition_comparison.csv
```

必须回答：

```text
1. probe 8 Q 翻转时，D_total 是否也发生可重复方向变化？
2. probe 8 的 XOR 脉宽是否变化，还是只有 delay path / DFF 变化？
3. probe 10 同为 M8,F0 为什么仍是 Q=1？
4. 3.3 ns 下是否出现新的 configuration glitch？
5. 2.5/3.3 的 M8 差异能否仅用绝对 launch 时间解释？
```

若 retained raw measurement 已经足以证明 parser（解析器）发布错误，例如 `Q_logic` 与原始电压不一致，则：

```text
root cause = measurement_publication_or_parser_error
```

直接修 parser/report，不运行新的 HSPICE。

除非数据真实显示物理差异，否则不得进入 Phase 4。

---

# Phase 2 — 构造一次性 root-cause matrix（根因矩阵）（0 HSPICE）

如果 retained evidence 仍不能唯一定位，就生成一个新的 0.80 V 长场景，内部包含多个彼此隔离的 micro-episode（微实验片段）。

**整个 root-cause matrix 只算 1 个 HSPICE scenario（场景）。**

所有 episode 共用冻结的真实：

```text
sensor
XOR
N=16 medium
X0P8/NOR2 K10 fine
real DFF
VDD=0.80 V
```

F 始终固定为 0，除非某个 control episode 明确用于排除 fine driver/load；本计划不重新做完整 fine search。

## 2.1 Episode 之间的强制隔离

每个 episode 结束后：

```text
DFF reset = 1
S_CLK     = 0
M         -> 0（逐 bit thermometer 回退，不允许多 bit 同时切）
F         = 0
```

之后保持一个 `episode_isolation_guard`。

该 guard 固定为：

```text
episode_isolation_guard = 3.5 ns
```

来源：当前 diagnostic observation bound 是 3.3 ns，再增加冻结 200 ps quiet tail（安静尾窗）；该 3.5 ns **只用于实验片段相互隔离**，不是功能 recovery guard。

禁止把该值带回最终协议。

## 2.2 功能 recovery guard 对照值

矩阵只允许使用：

```text
2.5 ns : 原始失败合同对照
2.7 ns : retained return-fall 实测推导出的候选功能 guard
3.3 ns : 旧 diagnostic bound 对照
```

不得增加第四个 guard 值。

## 2.3 code-settle 对照值

只允许：

```text
1.5 ns : 当前功能合同
3.3 ns : 长稳定时间 control（控制实验）
```

3.3 ns code-settle 仅用于判断 M 控制切换后内部 medium 节点是否需要比 1.5 ns 更长的稳定，不是预设修复方案。

## 2.4 reset-release 对照值

只允许：

```text
0.49 ns : 当前历史合同
1.00 ns : DFF reset sensitivity control（复位敏感性控制）
```

1.00 ns 只用于定位 DFF reset/capture 历史，不得自动写回功能协议。

---

# Phase 3 — 必须放进同一个 HSPICE 场景的实验矩阵

为了尽量一次性定位，不允许 Codex 看到一个结果后再回来申请“再跑一个小实验”。以下 episode 必须第一次就全部包含。

## Group A — isolated static-like anchors（隔离静态式锚点）

目的：在同一长 deck 中建立 M7/M8/M9 的局部基线，并排除绝对时间/全局模型差异。

```text
A1: isolated M7,F0 single probe
A2: isolated M8,F0 single probe
A3: isolated M9,F0 single probe
A4: isolated M8,F0 single probe repeat #2（放在整个 deck 后半段）
```

M7/M8/M9 均通过从 M0 安静地逐 bit 配到目标代码，然后等待 3.3 ns code-settle control，再进行 probe；不允许直接多 bit 跳码。

如果 A2 与 A4 不可重复，则首先分类为：

```text
long_timeline_or_simulation_state_nonrepeatability
```

在这种情况下，不允许讨论 ConfigSkip。

## Group B — predecessor direction（前序方向）

功能 guard=2.7 ns，code-settle=1.5 ns，reset separation=0.49 ns。

```text
B1: M7 probe -> recover 2.7 ns -> M7->M8 -> M8 probe
B2: M9 probe -> recover 2.7 ns -> M9->M8 -> M8 probe
B3: M8 probe -> recover 2.7 ns -> M8(no code change) -> M8 probe
```

目的：比较完全相同最终 `(M8,F0)` 在三种 predecessor 下的：

```text
XOR
medium_out
dff_ck
DFF.Q
```

若 B1/B2 的 M8 delay 明显不同，而 B3 和 isolated M8 稳定，则 transition-history dependence 成立。

## Group C — recovery duration sensitivity（恢复时间敏感性）

保持 predecessor 和 code-settle 相同，只改变前一 probe 返回后到代码更新的 guard：

```text
C1: M7 -> M8 with 2.5 ns recovery
C2: M7 -> M8 with 2.7 ns recovery
C3: M7 -> M8 with 3.3 ns recovery

C4: M9 -> M8 with 2.5 ns recovery
C5: M9 -> M8 with 2.7 ns recovery
C6: M9 -> M8 with 3.3 ns recovery
```

目的：判断当前 Q flip 是否是“前一功能脉冲恢复时间”的局部效应，还是 3.3 ns 全局累计 schedule 才出现的效应。

如果同一个 predecessor 下 M8 只随 recovery 时间改变，则分类为：

```text
residual_return_state_dependence
```

如果局部 C2/C3 都不翻转，而 retained 13-probe 3.3 ns 的 probe 8 翻转，则优先分类为：

```text
cumulative_schedule_history_dependence
```

## Group D — active-pulse vs config-only history（功能脉冲历史 vs 纯配置历史）

```text
D1: 配到 M7，但不发 S_CLK probe -> M7->M8 -> M8 probe
D2: M7 发一个完整 probe -> recover 2.7 -> M7->M8 -> M8 probe
D3: 配到 M9，但不发 S_CLK probe -> M9->M8 -> M8 probe
D4: M9 发一个完整 probe -> recover 2.7 -> M9->M8 -> M8 probe
```

所有其他时间相同。

如果 D1≈D3，但 D2 与 D4 分裂：

```text
root cause = functional_pulse_history / recovery-memory
```

如果 D1 与 D3 在没有前序 S_CLK 脉冲时仍分裂：

```text
root cause = configuration_transition_history in medium path
```

## Group E — code-settle sensitivity（配置稳定时间）

```text
E1: M7 probe -> recover 2.7 -> M7->M8 -> settle 1.5 ns -> probe
E2: M7 probe -> recover 2.7 -> M7->M8 -> settle 3.3 ns -> probe

E3: M9 probe -> recover 2.7 -> M9->M8 -> settle 1.5 ns -> probe
E4: M9 probe -> recover 2.7 -> M9->M8 -> settle 3.3 ns -> probe
```

如果只延长 code-settle 就消除方向差异：

```text
root cause = code_settle_guard_insufficient
```

而不是 ConfigSkip。

## Group F — reset/capture sensitivity（DFF 复位/捕获敏感性）

使用相同 2.7 ns recovery 和 1.5 ns code-settle：

```text
F1: M7->M8, reset fully-low -> launch separation = 0.49 ns
F2: M7->M8, reset fully-low -> launch separation = 1.00 ns

F3: M9->M8, reset fully-low -> launch separation = 0.49 ns
F4: M9->M8, reset fully-low -> launch separation = 1.00 ns
```

如果 `xor_29/medium_out/dff_ck` timing（时序）一致，但 Q 随 reset separation 改变：

```text
root cause = real_dff_reset_or_capture_history
```

## Group G — ascending / descending local monotonicity（局部升/降方向单调性）

```text
G1 ascending:
M7 probe -> M8 probe -> M9 probe
每步 recovery=2.7 ns, settle=1.5 ns

G2 descending:
M9 probe -> M8 probe -> M7 probe
每步 recovery=2.7 ns, settle=1.5 ns
```

目的：直接回答参考文献启发的 code-delay monotonicity（代码-延时单调性）问题。

对 G1 要求检查：

```text
D(M7) < D(M8) < D(M9)
```

这里 `D(M7)`、`D(M8)`、`D(M9)` 分别表示相同动态序列中 M7/M8/M9 的总 DCDL 延时；`<` 表示更大的 medium code 应产生更大的传播延时。

对 G2 不要求“时间方向上的数值递增”，而是将相同 code 的 delay 与 G1 配对，检查是否存在 hysteresis（滞回）。

如果 G1 本身出现：

```text
D(M8) <= D(M7)
或
D(M9) <= D(M8)
```

这里 `<=` 表示代码增加时真实延时没有增加，则分类为：

```text
dynamic_code_delay_non_monotonicity
```

这才是最接近参考文献 Fig. 11 的问题类别。

如果 G1/G2 各自都保持 M7<M8<M9，但相同 M8 在升/降方向的 delay 不同，则分类为：

```text
dynamic_delay_hysteresis_without_order_break
```

---

# Phase 4 — 每个 episode 必须测到哪一级：一次性完成 stage localization（级定位）

不能再只测 `xor_29` 和 `dff_ck` 两端。

每个最终 M8 probe 至少测：

```text
t_xor_rise10
t_xor_rise50
t_xor_fall10
t_xor_fall50

t_medium_rise10
t_medium_rise50
t_medium_fall10
t_medium_fall50

t_ck_rise10
t_ck_rise50
t_ck_fall10
t_ck_fall50

q_read_v
Q_logic
```

并计算：

```text
D_medium_ps = t_medium_rise50 - t_xor_rise50
```

`D_medium_ps` 是 medium stage 的动态上升传播延时；`t_medium_rise50` 是 `medium_out` 上升穿过 50% VDD 的时刻；`t_xor_rise50` 是 `xor_29` 上升穿过 50% VDD 的时刻；`-` 表示传播时间差。

```text
D_fine_driver_ps = t_ck_rise50 - t_medium_rise50
```

`D_fine_driver_ps` 是 `medium_out -> dff_ck` 的 fine driver/load 等效传播延时；`t_ck_rise50` 是 `dff_ck` 上升穿过 50% VDD 的时刻；`t_medium_rise50` 是 medium 输出 50% 上升时刻；`-` 表示该后级传播延时。

```text
D_total_ps = t_ck_rise50 - t_xor_rise50
```

`D_total_ps` 是完整两级延时；`t_ck_rise50` 和 `t_xor_rise50` 分别是 CK 与 XOR 的 50% 上升时刻；`-` 表示总传播时间差。

还要测三个 pulse width（脉宽）：

```text
W_xor
W_medium
W_ck
```

这样可以区分“上升沿延时变化”和“脉冲形状/下降沿历史变化”。

---

# Phase 5 — medium 内部节点必须被观测，避免根因只定位到“medium 某处”

M7/M8/M9 只改变 thermometer code 中相邻一个 bit。

因此 root-cause deck 必须额外测 medium path-selection 网络中围绕边界的内部节点：

```text
x7
x8
x9
x10
my6
my7
my8
my9
medium_out
```

如果实际 netlist 命名与此略有不同，以新 runner 生成的 frozen topology 命名为准，但至少覆盖：

```text
M7/M8 切换 bit 对应 MUX 的输入/输出
M8/M9 切换 bit 对应 MUX 的输入/输出
向最终 medium_out 传播的上游两级节点
```

每个关键 episode 对这些节点测：

```text
rise10
rise50
fall10
fall50
quiet-window max
```

输出：

```text
transition_internal_node_audit.csv
```

如果 `xor_29` 完全一致，而差异第一次出现在某个 `myN`：

```text
root cause stage = medium_path_selection
first_divergent_node = myN
```

这样下一步不需要再做一次“medium 内部到底哪一级”的仿真。

---

# Phase 6 — 事件完整性和 .measure 防误判合同

为避免又因为 measure indexing（测量事件索引）返工，每个 episode 必须：

```text
1. 用明确 FROM/TO 或 TD 限定本 episode 的有效窗口；
2. 不能只依赖全局 RISE=n；
3. 对 xor_29 / medium_out / dff_ck 分别测第 1 个和第 2 个 >50% VDD 上升；
4. 第二个边沿只在同一 probe active window 内才算 extra edge；
5. recovery return pulse 与下一 episode 的新 probe 必须通过时间窗完全隔离；
6. 每个 Q read 都必须记录原始电压，不只写 0/1；
7. Q 高要求 >=0.9 VDD，Q 低要求 <=0.1 VDD；
8. 10%~90% VDD 之间必须分类为 q_ambiguous；
9. 所有 HSPICE failed measure 都必须是显式 failure，不能被解析成 0；
10. measurement file / listing / deck / manifest 全部 hash 后保留。
```

---

# Phase 7 — 重复性阈值必须数据驱动，不准拍脑袋定义 5 ps/10 ps

同一 episode 至少对：

```text
isolated M8
M7->M8 @2.7 ns
M9->M8 @2.7 ns
```

各安排 2 次重复，其中一组在 deck 前半段、一组在后半段。

定义：

```text
repeat_spread_ps = 同一条件重复测量的最大 D_total 差值
```

`repeat_spread_ps` 表示相同电气条件在同一个长仿真中的重复误差；“最大差值”用于形成该次任务自己的数值噪声基线。

定义：

```text
history_effect_ps = |mean(D_M7toM8) - mean(D_M9toM8)|
```

`history_effect_ps` 表示 M7->M8 与 M9->M8 两种前序方向下最终 M8 的平均总延时差；`mean` 表示相同条件重复结果的平均值；`| |` 表示取绝对差。

只有当：

```text
history_effect_ps > 2 * repeat_spread_ps
```

并且方向性结果重复出现时，才将其作为明确 history-dependent delay（历史依赖延时）证据。

这里 `history_effect_ps` 是两种 history 的延时差；`repeat_spread_ps` 是相同条件的重复波动；`2 *` 表示要求 history 差至少超过重复波动的两倍，以避免把数值抖动误判成物理历史效应；`>` 表示超过该数据驱动噪声界。

同时，无论差值是否很小，只要 Q 在重复可复现条件下发生稳定分裂，都必须记录为 comparator-boundary-sensitive（比较器边界敏感），不能因为 ps 差值小就忽略。

输出：

```text
repeatability_audit.csv
```

---

# Phase 8 — 新 HSPICE 预算

根因定位阶段只允许：

```text
1 x history_root_cause_matrix_0p80
```

这是本计划的核心要求。

所有 Group A~G 都必须在这一个场景中完成。

禁止拆成：

```text
一个 predecessor 场景
一个 recovery sweep 场景
一个 reset 场景
一个 monotonicity 场景
```

避免再次多轮返工。

scenario identity 至少包含：

```text
study
git_baseline_sha
frozen_evidence_sha
vdd=0.80
cells/topology
matrix_contract_sha
2.5/2.7/3.3 recovery factors
1.5/3.3 code-settle factors
0.49/1.00 reset-separation factors
episode list hash
measurement contract version
internal-node list hash
```

如果场景完整 PASS，后续 parser/report 修改只能复用，不得重跑。

---

# Phase 9 — 自动根因分类决策树

新 runner 必须自动生成：

```text
classification.json
```

分类不能由报告作者主观选择，必须由测量结果触发。

## 9.1 measurement/parser error

如果 retained raw voltage 与已发布 Q 不一致，或新场景事件计数不一致：

```text
measurement_publication_or_event_indexing_error
```

## 9.2 sensor/XOR history

如果最终 M8 的 `t_xor_rise50` / `W_xor` 随 history 显著变化，而 medium 相对 XOR 的延时基本稳定：

```text
sensor_xor_pulse_history_dependence
```

## 9.3 medium transition history

如果 XOR 基本稳定，而 `D_medium` 在 M7->M8 与 M9->M8 间出现超过重复噪声界的可重复差异：

```text
medium_path_transition_history_dependence
```

同时必须给：

```text
first_divergent_internal_node
```

## 9.4 dynamic code-delay non-monotonicity

如果 G1 ascending 中 M7/M8/M9 真实延时排序被破坏：

```text
dynamic_code_delay_non_monotonicity
```

这是与参考文献 Fig.11 最直接对应的类别。

## 9.5 hysteresis without order break

如果升序/降序各自都满足 M7<M8<M9，但相同 code 的延时依赖方向：

```text
dynamic_delay_hysteresis_without_order_break
```

## 9.6 recovery-memory

如果同一 predecessor 下 2.5/2.7/3.3 的 M8 结果随 recovery guard 改变，同时 config-only history 不改变：

```text
residual_return_state_dependence
```

## 9.7 code-settle insufficient

如果 1.5 ns 与 3.3 ns code-settle 显著改变 M8 medium delay/Q，而 recovery 固定：

```text
code_settle_guard_insufficient
```

## 9.8 fine driver/load history

如果 `D_medium` 稳定，但 `D_fine_driver` 随 history 改变：

```text
fine_driver_or_load_history_dependence
```

## 9.9 DFF reset/capture

如果 XOR、medium、CK timing 在 Q=0 与 Q=1 情况基本一致，而 reset separation 改变 Q：

```text
real_dff_reset_or_capture_history_dependence
```

## 9.10 cumulative schedule only

如果：

```text
isolated M8 可重复
B/C/D/E/F 均不显示局部 history
2.7 与 3.3 isolated transition 均保持正确 Q
但 retained 全 13-probe / 3.3 ns diagnostic 的 probe 8 独有 Q=0
```

则分类：

```text
cumulative_schedule_history_dependence
```

并进一步由 stage measurements 判断累计影响最先出现在 sensor / medium / CK / DFF 中哪一级。

## 9.11 simulation long-timeline non-repeatability

如果相同 isolated M8 在 deck 前后重复本身不一致：

```text
long_timeline_or_simulation_state_nonrepeatability
```

此时先解决仿真合同，禁止修改电路。

---

# Phase 10 — 分类必须输出“证据链”，不能只给字符串

`classification.json` 至少：

```text
primary_classification
secondary_classifications
confidence = conclusive / strong / ambiguous
first_divergent_stage
first_divergent_node
q_flip_conditions
non_q_flip_control_conditions
D_total_history_effect_ps
D_medium_history_effect_ps
D_fine_history_effect_ps
repeat_spread_ps
recovery_sensitive
code_settle_sensitive
reset_sensitive
active_pulse_history_sensitive
ascending_monotonic
descending_consistent
retained_2p5_vs_3p3_consistent_with_classification
recommended_next_action
forbidden_next_actions
```

`confidence=conclusive` 只能在至少一个正向触发实验和一个对应 negative control（阴性控制）共同支持时使用。

若多个因素同时显著，必须报告组合根因，不准强行只选一个。

---

# Phase 11 — 是否允许直接进入 2.7 ns repaired validation

为了避免再多开一轮 plan，本计划预先授权一个**严格条件式**后续动作，但只有根因矩阵明确证明没有硬件历史问题时才允许执行。

## 11.1 可以直接进入 repaired validation 的唯一条件

只有 classification 同时满足：

```text
primary_classification = cumulative_schedule_history_dependence
或 measurement_publication_or_event_indexing_error 已经通过重解析消除

AND

ascending_monotonic = true
medium history effect <= repeat noise gate
fine history effect <= repeat noise gate
reset_sensitive = false
code_settle_sensitive = false
active_pulse_history_sensitive = false
2.7 ns isolated M7->M8 gives Q=1
2.7 ns isolated M9->M8 gives Q=1
configuration glitches = 0
```

才允许使用已有 return measurement 冻结：

```text
functional_recovery_guard = 2.7 ns
```

并最多新增：

```text
1 x repaired_full_trajectory_0p80_2p7ns
```

这个第二场景必须完整运行原 13-probe 搜索轨迹，验证：

```text
coarse = 1111111110
fine   = 10
hold   = 0
lock   = (8,1)
recovery tail PASS
```

若失败，立即停止，不允许 2.8/2.9/3.0 ns 调参。

## 11.2 以下任一根因出现时禁止 repaired full trajectory

```text
medium_path_transition_history_dependence
dynamic_code_delay_non_monotonicity
dynamic_delay_hysteresis_without_order_break
residual_return_state_dependence
code_settle_guard_insufficient
fine_driver_or_load_history_dependence
real_dff_reset_or_capture_history_dependence
long_timeline_or_simulation_state_nonrepeatability
```

这些情况必须先根据根因进入对应修复计划。

---

# 12. 对参考文献 ConfigSkip 的使用门槛

只有出现：

```text
dynamic_code_delay_non_monotonicity
```

或者经过完整 evidence 证明某些 medium/fine code 区间在稳定后也存在重复的 delay drop，才允许下一阶段研究 ConfigSkip。

如果只是：

```text
recovery-memory
code-settle insufficient
DFF reset/capture history
```

则 ConfigSkip 不是直接修复手段，禁止引入。

如果是：

```text
medium_path_transition_history_dependence
```

但静态/长 settle 后恢复唯一延时，则下一步优先研究 update protocol（更新协议）、settle contract 或控制隔离，而不是直接跳码。

---

# 13. 新静态测试要求（0 HSPICE）

新增：

```text
delay_chain/ftc/tests/test_dynamic_m8_history_root_cause.py
```

至少测试：

```text
1. 最新基线 commit 与 25b2fba 一致；
2. retained repair decision = NO-GO；
3. reason = diagnostic_q_sequence_changed；
4. old 2.5 Q = 1111111110100；
5. diagnostic 3.3 Q = 1111111100100；
6. first mismatch = probe 8 / M8,F0；
7. diagnostic probe10 M8,F0 = Q1；
8. worst return settle = 2.474756780 ns；
9. candidate functional guard = 2.7 ns；
10. 3.3 ns 只被标记为 diagnostic bound；
11. root-cause matrix scenario count = 1；
12. Group A~G 全部存在；
13. predecessor 7/8/9 control 全部存在；
14. 2.5/2.7/3.3 三个 recovery factor 全部存在且只有这三个；
15. 1.5/3.3 两个 code-settle factor 全部存在且只有这两个；
16. 0.49/1.00 两个 reset factor 全部存在且只有这两个；
17. episode 之间 M/F 逐 bit 回到已知状态；
18. episode isolation guard = 3.5 ns 且不能写回功能协议；
19. F 在所有 medium 根因 episode 中固定为 0；
20. active vs config-only paired controls 存在；
21. isolated M8 至少重复两次并分布在 deck 前/后；
22. medium internal nodes 被测；
23. active probe window 的第 2 CK edge 被显式审计；
24. Q rail validity 被检查；
25. parser missing measure 不能变成 0；
26. 新 runner 不 import/dispatch 旧动态 runner；
27. 新 runner 不 dispatch 上游 84 static；
28. 0.95/1.10 不进入 HSPICE scheduler；
29. 不出现 bypass/ConfigSkip/gating/FSM/margin/droop/PVT；
30. phase0 / retained-analysis 模式绝不能执行 HSPICE；
31. 只有 root-cause classification 通过 schedule-only gate 时才允许第二个 repaired scenario；
32. 总新 HSPICE 成功上限：root-cause=1，条件式 repaired=1。
```

执行：

```text
python3 -m unittest delay_chain.ftc.tests.test_dynamic_m8_history_root_cause
git diff --check
```

---

# 14. 报告必须一次回答完的问题

最终报告：

```text
delay_chain/ftc/reports/FTC_DYNAMIC_M8_HISTORY_ROOT_CAUSE.md
```

必须明确回答：

```text
1. 2.5 ns 与 3.3 ns retained raw measurement 的 probe 8 D_total 差多少？
2. probe 8 Q flip 时 XOR pulse width 是否也改变？
3. probe 10 同为 M8,F0 为什么仍是 Q1？
4. isolated M8 在 deck 前后是否可重复？
5. M7->M8 与 M9->M8 在相同 2.7 ns guard 下 D_medium 是否不同？
6. 差异第一次出现在哪个 medium internal node？
7. active predecessor pulse 是否是必要条件？
8. 2.5/2.7/3.3 recovery 对同一个局部 transition 有何影响？
9. 1.5/3.3 code-settle 是否改变结果？
10. 0.49/1.00 reset separation 是否改变 Q 而不改变 CK？
11. ascending M7->M8->M9 的真实 delay 是否严格单调？
12. descending M9->M8->M7 是否出现相同 code 的 hysteresis？
13. 当前现象是否真正属于参考文献 Fig.11 类型的 dynamic code-delay non-monotonicity？
14. 如果不是，最准确的根因类别是什么？
15. 2.7 ns 是否仍可作为 recovery 功能 guard？
16. 是否有任何证据支持 ConfigSkip？
17. 是否有任何证据支持修改 medium/fine 单元？
18. 是否有任何证据支持修改 DFF/reset 合同？
19. 本任务新增了几个 HSPICE scenario？
20. 所有旧仿真是否保持 0 rerun？
21. 下一步唯一推荐动作是什么？
```

---

# 15. Codex 严格执行顺序

```text
Step 1  拉取 main，确认最新 FTC 电气提交仍为 25b2fba 或其后只有计划/文档提交。
Step 2  冻结 old 2.5 ns + diagnostic 3.3 ns + static golden 全部 SHA；0 HSPICE。
Step 3  从 retained 3.3 raw measurement 恢复未发布的 probe_result / transition_result；0 HSPICE。
Step 4  生成 retained_2p5_vs_3p3_probe_comparison.csv；0 HSPICE。
Step 5  检查 parser/publication error；若存在，只重解析，不跑 HSPICE。
Step 6  固定 candidate functional recovery guard=2.7 ns；不得 sweep。
Step 7  构造 Group A~G 一次性 root-cause matrix contract；0 HSPICE。
Step 8  构造 episode isolation/reset-to-known-state 流程；0 HSPICE。
Step 9  加入 active-stage xor/medium/ck 10%/50% rise/fall 测量；0 HSPICE。
Step 10 加入 M7/M8/M9 medium internal-node 测量；0 HSPICE。
Step 11 加入 repeatability controls；0 HSPICE。
Step 12 运行全部 unittest 与 git diff --check；0 HSPICE。
Step 13 只运行 1 个 history_root_cause_matrix_0p80 HSPICE 场景。
Step 14 解析所有 episode，不允许缺一个 Group 后补跑。
Step 15 自动生成 repeatability_audit / stage_delay / internal_node / classification。
Step 16 按决策树发布 primary/secondary root cause 和 first divergent node。
Step 17 若 root cause 是任何真实 history/non-monotonic/reset/settle 问题，停止，不运行 full repaired trajectory。
Step 18 只有满足 schedule-only gate 时，才冻结 2.7 ns 并允许 1 个 repaired_full_trajectory_0p80_2p7ns。
Step 19 repaired full trajectory 若失败，停止，不调 guard。
Step 20 生成最终报告，明确是否属于文献 Fig.11 类型问题以及下一步修复路线。
Step 21 不实现 ConfigSkip/FSM/margin/droop/PVT。
```

---

# 16. 成功标准

本计划不是以“F 阶段必须 GO”为成功标准，而是以**根因必须被一次性收敛**为成功标准。

允许的成功结论之一：

```text
Dynamic M8 History Root Cause = CONCLUSIVE
```

且 `classification.json` 必须给出明确 primary classification（主分类）和 first divergent stage/node（首个分歧级/节点）。

如果 classification 仍是 `ambiguous`，则只有在下列情况下可接受：

```text
HSPICE/measurement 本身不具备足够可重复性
或
两个以上物理因素确实同时显著
```

不允许因为“当初少测了 medium internal node / 少做了 reset control / 少做了 config-only control”而把结果写成 ambiguous；这些控制实验已经被本计划要求第一次全部放入同一个场景。

---

# 17. 本计划的核心原则

> 不再围绕 2.5/2.7/3.3 ns 反复试错，而是利用已经存在的两套完整动态证据，加上一个包含 predecessor、recovery、code-settle、active/config-only、reset、ascending/descending 和重复性控制的单一 0.80 V 晶体管级场景，把异常第一次出现的位置从 `xor_29 -> medium internal nodes -> medium_out -> fine driver -> dff_ck -> real DFF.Q` 逐级定位。只有在确认不存在真正的 code-delay/history 问题时，才允许用已实测推导的 2.7 ns 做一次最终 repaired validation；否则直接进入与根因对应的修复分支，避免再次返工。
