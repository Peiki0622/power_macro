# FTC 动态启动校准 Recovery Window 修复：Codex 逐步骤执行计划

## 0. 任务定位

本计划是对已经完成但最终判定为 NO-GO 的动态启动校准协议进行**单点修复**。

当前远程基线提交：

```text
568f8ace2b7fa813a2bb082302c182b51288dd53
feat(ftc): document dynamic recovery window failure
```

当前正式结论：

```text
Dynamic Startup Calibration Protocol = NO-GO
```

唯一终止原因：

```text
recovery_window_insufficient
```

本任务只回答一个问题：

> 0.80 V 下 S_CLK 下降后产生的功能性返回波没有在当前 2.5 ns recovery window（恢复窗口）结束前完全返回低电平，是否能够通过重新定义“真实返回活动结束时间”并延长 recovery guard（恢复保护时间）来修复，而不修改 sensor、XOR、中调、细调、DFF 或校准搜索轨迹？

如果本任务修复成功，允许将 F 阶段重新发布为：

```text
Dynamic Startup Calibration Protocol = GO
```

然后下一阶段仍然必须是：

```text
G. 真实启动校准控制电路实现
        ↓
H. 完整真实电路级启动校准验证
        ↓
I. 可编程检测裕量
```

本任务不得进入 G/H/I。

---

# 1. 当前已知事实：必须原样冻结

Codex 开始前必须读取当前远程结果，并验证以下事实没有变化。

## 1.1 0.95 V 已经动态 GO

```text
coarse Q = 1111110
fine Q   = 10
hold Q   = 0
final    = (M=5, F=1)
```

## 1.2 1.10 V 已经动态 GO

```text
coarse Q = 11110
fine Q   = 11110
hold Q   = 0
final    = (M=3, F=4)
```

## 1.3 0.80 V 除 recovery 外全部通过

```text
coarse Q = 1111111110
fine Q   = 10
hold Q   = 0
final    = (M=8, F=1)
```

0.80 V 当前还已经满足：

```text
动态 coarse D_code 严格单调
动态 fine D_code 严格单调
全部 probe 的 Q 均有效
没有 q_ambiguous
没有 extra_ck_edge_during_probe
所有 configuration_ck_edge_count = 0
coarse_backoff transition = PASS
fine_increment transition = PASS
最终动态锁点与静态黄金锁点一致
```

当前全局最小 Q-settle margin（Q 稳定裕量）约：

```text
481.42946 ps
```

当前 0.80 V 最大配置更新安静峰值比仍小于 10% VDD Gate（判定门槛），当前结果给出的最大值约：

```text
maximum_configuration_quiet_peak_ratio = 0.04538
```

因此本计划**不允许**把当前问题解释成 DFF 比较失败、动态搜索失败或配置切换产生 CK 毛刺。

## 1.4 当前 recovery failure 的性质

当前 0.80 V：

```text
recovery_guard = 2.5 ns
maximum_recovery_signal_ratio ≈ 1.0034 x VDD
```

这说明当前固定 recovery endpoint/tail（恢复终点/尾部窗口）落在仍然接近完整高电平的返回活动上，而不是只有很小的残余振铃。

当前报告已经明确：

```text
The sole terminal reason is recovery_window_insufficient.
```

Codex 必须把这条结论作为当前任务的冻结 handoff（交接条件）。

---

# 2. 绝对禁止事项

## 2.1 禁止重跑上一步 84 个静态 HSPICE 场景

以下全部只读：

```text
delay_chain/ftc/runs/two_stage_real_dff_hierarchical_calibration/
delay_chain/ftc/analysis/two_stage_real_dff_hierarchical_calibration/
delay_chain/ftc/reports/FTC_TWO_STAGE_REAL_DFF_HIERARCHICAL_CALIBRATION.md
```

并且：

```text
upstream_static_hspice_rerun = 0
upstream_static_84_scenarios_rerun = 0
```

必须继续保持为 0。

## 2.2 禁止重跑已经 GO 的 0.95 V 和 1.10 V 动态场景

当前 `dynamic_startup_calibration_protocol` 中：

```text
0.95 V = retained GO evidence（保留的 GO 证据）
1.10 V = retained GO evidence
```

本任务只能读取，不能重新执行。

## 2.3 禁止原样重跑当前失败的旧 0.80 V 场景

旧场景的目的已经完成：它证明 2.5 ns recovery guard 不足。

不得生成一个完全相同的 2.5 ns deck（网表）再次运行。

本任务新运行的 0.80 V 场景必须具有新的诊断或修复合同，例如新增真实 return-fall（返回下降沿）测量或使用由新证据得到的 recovery guard。

## 2.4 禁止改硬件

保持：

```text
sensor initial RVT stages = 4
sensor initial LVT stages = 0
observable stages         = 30
sensor tap                = 29
XOR                       = XOR2_X0P5M_A9TR40

medium N                  = 16
medium delay cell         = BUF_X0P7M_A9TL40
medium MUX                = MXT2_X0P5M_A9TL40

fine driver               = BUF_X0P8M_A9TL40
fine load                 = NOR2_X4A_A9TL40
fine signal pin           = A
fine control pin          = B
fine K                    = 10

DFF                       = DFFRPQ_X0P5M_A9TR40
DFF minimum Q settle      = 200 ps
```

禁止：

```text
重新搜索 driver/load/MUX/DFF
改变 N
改变 K
加入 bypass（旁路）
加入 configuration skip（配置跳过）
加入 clock gating（时钟门控）
加入 update isolation（更新隔离）
加入理想 delay
加入理想 capacitor
改变 sensor tap
改变 XOR
改变 DFF
实现 FSM（有限状态机）
实现 counter/register（计数器/寄存器）
加入 programmable margin（可编程裕量）
加入 droop（电压跌落）
加入 PVT（工艺/电压/温度）
加入 RTL（寄存器传输级设计）
进入 layout（版图）
```

如果修复失败，只允许记录根因和 NO-GO，不允许现场改硬件救援。

---

# 3. 根因假设：只能作为待验证假设，不能先写成结论

当前 runner（运行脚本）使用：

```text
recovery_guard = ceil_0.1ns(
    max_sensor_to_xor
  + D_delay_max
  + Q_SETTLE
)
```

其中：

- `max_sensor_to_xor`：历史输入 launch（发射）到 `xor_29` 上升沿的最大传播时间；
- `D_delay_max`：历史两级延时线的最大上升传播延时；
- `Q_SETTLE`：200 ps 保护量；
- `+`：把各时间项相加；
- `ceil_0.1ns`：向上取整到 0.1 ns。

当前得到：

```text
max_sensor_to_xor = 0.95105046 ns
D_delay_max       = 1.269042997 ns
Q_SETTLE          = 0.200 ns
recovery_guard    = 2.500 ns
```

本任务的工作假设是：

> 该公式主要覆盖“返回活动前沿到达”的时间，但没有直接测量 S_CLK 下降后，由 sensor/XOR 返回脉冲经过两级延时线后，`dff_ck` 真正下降并稳定到 10% VDD 以下的时间。

0.80 V 的历史真实 XOR 脉宽约 789 ps，比 0.95/1.10 V 更宽，因此该遗漏最可能首先在 0.80 V 暴露。

这只是 hypothesis（假设）。必须通过本任务新增的 return-event measurement（返回事件测量）验证。

---

# 4. 本任务新增目录和文件

新建：

```text
delay_chain/ftc/scripts/run_dynamic_recovery_window_repair.py

delay_chain/ftc/analysis/dynamic_recovery_window_repair/
  requirements.json
  frozen_baseline.json
  old_failure_map.json
  diagnostic_timing_contract.json
  diagnostic_results.csv
  measured_return_settle.json
  repaired_timing_contract.json
  repaired_probe_results.csv
  repaired_transition_audit.csv
  repaired_lock_table.json
  summary.json

delay_chain/ftc/runs/dynamic_recovery_window_repair/

delay_chain/ftc/reports/FTC_DYNAMIC_RECOVERY_WINDOW_REPAIR.md

delay_chain/ftc/tests/test_dynamic_recovery_window_repair.py
```

不得覆盖：

```text
delay_chain/ftc/analysis/dynamic_startup_calibration_protocol/
delay_chain/ftc/runs/dynamic_startup_calibration_protocol/
delay_chain/ftc/reports/FTC_DYNAMIC_STARTUP_CALIBRATION_PROTOCOL.md
```

原始 NO-GO 必须永久保留，作为修复前证据。

新 runner 不得 import 或 dispatch：

```text
run_two_stage_real_dff_hierarchical_calibration.py
run_dynamic_startup_calibration_protocol.py
```

允许读取它们作为只读源码证据并计算 SHA256。

允许继续使用无副作用的公共 HSPICE listing/MEAS parser（日志/测量解析器）。

---

# Phase 0 — 冻结当前 NO-GO handoff（0 HSPICE）

读取并 SHA256：

```text
delay_chain/ftc/analysis/dynamic_startup_calibration_protocol/summary.json
delay_chain/ftc/analysis/dynamic_startup_calibration_protocol/dynamic_lock_table.json
delay_chain/ftc/analysis/dynamic_startup_calibration_protocol/timing_contract.json
delay_chain/ftc/analysis/dynamic_startup_calibration_protocol/probe_results.csv
delay_chain/ftc/analysis/dynamic_startup_calibration_protocol/transition_audit.csv
delay_chain/ftc/analysis/dynamic_startup_calibration_protocol/integration_contract.json
delay_chain/ftc/analysis/dynamic_startup_calibration_protocol/trajectory_contract.json
delay_chain/ftc/reports/FTC_DYNAMIC_STARTUP_CALIBRATION_PROTOCOL.md
delay_chain/ftc/scripts/run_dynamic_startup_calibration_protocol.py
```

如果 `trajectory_contract.json` 实际按 VDD 分文件，则读取当前实现中的全部对应文件；不得因为文件名与计划不同就重新生成旧结果。

必须验证：

```text
current decision = Dynamic Startup Calibration Protocol = NO-GO
reasons          = [recovery_window_insufficient]
0.95 status      = GO
1.10 status      = GO
0.80 status      = NO-GO
0.80 final code  = (8,1)
0.80 coarse Q    = 1111111110
0.80 fine Q      = 10
0.80 hold Q      = 0
```

还必须验证所有上游/历史 rerun counter 仍为 0。

生成：

```text
requirements.json
frozen_baseline.json
```

若任何冻结事实不一致：

```text
Dynamic Recovery Window Repair = UPSTREAM_BLOCKED
```

0 个新 HSPICE，停止。

---

# Phase 1 — 先定位旧 failure map（0 HSPICE）

当前旧 runner 已经有 recovery endpoint/tail 判定逻辑。

Codex 必须从保留的旧 measurement/summary 中解析并发布：

```text
old_failure_map.json
```

每个旧失败项至少包含：

```text
vdd_v
probe_index
protocol_phase
medium_code
fine_code
node
recovery_end_s
endpoint_v
endpoint_ratio
tail_v
tail_ratio
```

节点至少区分：

```text
xor_29
medium_out
dff_ck
```

要求回答：

```text
到底是哪些 probe 在 2.5 ns endpoint/tail 失败？
最坏节点是谁？
是 xor_29 仍高、medium_out 仍高、还是 dff_ck 仍高？
是否多个节点顺序一致地显示返回脉冲仍在传播？
```

此 Phase 不允许 HSPICE。

如果旧 raw measurement 文件能够完整恢复 failure map，直接使用旧数据。

如果旧 summary 没有发布全部 `recovery_failures`，这是 publication gap（证据发布缺口），但不能因此重跑旧场景；先从 retained scenario（保留场景）的 measurement 文件解析。

---

# Phase 2 — 重新定义 recovery 的测量合同（0 HSPICE）

当前的错误判定方式是：

```text
在固定 recovery_end 点检查一次电压
+
检查 recovery_end 前 200 ps 的 MAX
```

修复任务必须增加真正的返回时序测量。

对每一个 0.80 V probe，在 `sclk_fall` 之后测：

```text
t_return_xor_rise10
t_return_xor_fall10
t_return_xor_rise10_2

t_return_medium_rise10
t_return_medium_fall10
t_return_medium_rise10_2

t_return_ck_rise10
t_return_ck_fall10
t_return_ck_rise10_2
```

其中 `rise10` / `fall10` 表示节点上升/下降穿过 10% VDD 的时刻；`rise10_2` 表示在 S_CLK fall（下降）之后第二次上升穿过 10% VDD，用于检测返回后是否又出现新的超阈值活动。

定义：

```text
T_return_settle(node, probe) = t_return_node_fall10 - t_sclk_fall
```

其中：

- `T_return_settle`：该节点从 S_CLK 下降开始，到返回下降穿过 10% VDD 所需时间；
- `t_return_node_fall10`：该节点返回下降穿过 10% VDD 的时刻；
- `t_sclk_fall`：对应 probe 的 S_CLK 下降时刻；
- `-`：两个绝对时刻相减得到恢复延时。

新的 recovery guard 必须由实测最坏值推导：

```text
recovery_guard_new = ceil_0.1ns(
    max(T_return_settle)
  + 0.200 ns
)
```

其中：

- `recovery_guard_new`：修复后的固定恢复保护时间；
- `max(T_return_settle)`：0.80 V 全部需要进入下一次更新的 probe/节点中的最慢返回时间；
- `0.200 ns`：沿用当前 DFF/Q 合同中的保守保护量，不新增未经证明的随机裕量；
- `+`：在实测最坏恢复时间之后再留 200 ps；
- `ceil_0.1ns`：向上取整到 0.1 ns。

最终 guard 不允许手工写死为 3.3 ns、3.5 ns 或 5 ns 后再宣布成功。

3.3 ns 只允许作为当前证据下的 first diagnostic bound（第一诊断观察上界）候选，不是最终答案。

---

# Phase 3 — 生成 0.80 V diagnostic bound（0 HSPICE）

在真正运行诊断场景前，用保留的旧证据得到一个保守但有来源的观察窗口。

优先使用 0.80–1.10 V 正式工作范围内的：

```text
historical real-XOR end time
historical two-stage maximum delay
200 ps protection
```

建议 preflight（预检查）估算使用：

```text
T_diag_bound = ceil_0.1ns(
    max(t_xor29_fall - launch) over 0.80..1.10 V
  + retained D_delay_max
  + 2 * Q_SETTLE
)
```

其中：

- `T_diag_bound`：只用于第一次诊断场景的长观察窗口；
- `t_xor29_fall - launch`：真实 XOR 脉冲结束相对输入 launch 的时间；
- `retained D_delay_max`：保留证据中的最大两级延时；
- `Q_SETTLE`：200 ps；
- `2 * Q_SETTLE`：额外给诊断窗口 400 ps 观测余量，而不是最终协议裕量；
- `+`：时间累加；
- `ceil_0.1ns`：向上取整到 0.1 ns。

必须把每个输入数据值、来源文件和 SHA256 写入：

```text
diagnostic_timing_contract.json
```

若按当前证据计算结果在 3.x ns，这是合理量级；不得因为“想一次通过”而擅自改成特别大的任意窗口。

---

# Phase 4 — 唯一一次 0.80 V recovery diagnostic HSPICE

本 Phase 最多允许 1 个新 HSPICE 场景：

```text
recovery_diagnostic_0p80
```

它不是旧 2.5 ns 场景的原样重跑。

必须保持：

```text
完全相同的 sensor/XOR/medium/fine/DFF
完全相同的 0.80 V M/F/Q 黄金轨迹
完全相同的 single-bit PWL（单比特分段线性）更新原则
完全相同的 q-read offset
完全相同的 reset 比较流程
```

唯一允许的协议差异：

```text
1. recovery window 临时延长到 T_diag_bound；
2. 增加 Phase 2 定义的 return 10% crossing measurements（返回 10% 交叉测量）。
```

诊断场景必须输出：

```text
diagnostic_results.csv
measured_return_settle.json
```

每个 probe / node 至少记录：

```text
probe_index
M
F
node
sclk_fall_s
return_rise10_s
return_fall10_s
return_settle_ps
second_rise10_s
second_rise_present
valid
reason
```

诊断 Gate：

```text
1. 每个需要恢复的 probe 都找到 return_fall10；
2. return_fall10 发生在下一次 code update 前；
3. return_fall10 后不存在 second_rise10；
4. 诊断延长窗口本身不改变 Q 序列；
5. coarse/fine/hold Q 必须仍是 1111111110 / 10 / 0；
6. 最终锁点仍是 (8,1)；
7. 不产生新的 configuration-induced CK edge（配置诱导 CK 边沿）；
8. 不产生 extra CK edge during probe（比较窗口额外 CK 边沿）。
```

如果诊断窗口结束仍有节点没有 `return_fall10`：

```text
recovery_return_did_not_settle_within_diagnostic_bound
```

立即 NO-GO，停止。不得自动继续扩大窗口试到成功。

---

# Phase 5 — 从诊断结果冻结新的 recovery guard（0 HSPICE）

只有 Phase 4 诊断完整有效后执行。

从 `measured_return_settle.json` 中寻找：

```text
worst_probe_index
worst_M
worst_F
worst_node
worst_return_settle_ps
```

然后严格按 Phase 2 公式得到：

```text
recovery_guard_new
```

生成：

```text
repaired_timing_contract.json
```

必须同时保留：

```text
old_recovery_guard_s = 2.5e-9
new_recovery_guard_s
added_guard_s
worst_return_settle_s
safety_tail_s = 0.2e-9
derivation = measured_return_fall10_plus_200ps
```

不得通过观察 repaired validation（修复验证）结果后再调 guard。

也就是说：

> Phase 5 一旦冻结 `recovery_guard_new`，Phase 6 只有一次验证机会；如果失败，本任务 NO-GO，不做 iterative tuning（迭代调参）。

---

# Phase 6 — 静态审计和回归测试（0 HSPICE）

在运行修复场景前必须证明：

```text
1. 新旧物理 topology 完全一致；
2. M/F 动态黄金轨迹完全一致；
3. q-read offset = 2.3 ns 不变；
4. Q settle = 200 ps 不变；
5. code-settle guard = 1.5 ns 不变；
6. 只有 recovery_guard 发生变化；
7. 只有新增 return-event measure，不增加任何功能硬件；
8. reset 时序逻辑不变；
9. M/F 每次仍只变一个 thermometer bit（温度计码位）；
10. 不导入旧 runner；
11. 不写入旧 analysis/runs/report；
12. 0.95/1.10 不进入调度器；
13. upstream 84 静态场景不进入调度器。
```

新增静态测试：

```text
delay_chain/ftc/tests/test_dynamic_recovery_window_repair.py
```

至少覆盖：

```text
- latest frozen baseline hash/decision checks
- only recovery reason is accepted as repair entry
- 0.95/1.10 retained GO are mandatory
- 0.80 Q/lock old results must already match golden
- old guard = 2.5 ns
- diagnostic bound comes only from retained evidence
- new guard comes only from measured_return_settle + 200 ps
- new guard must be > old guard
- new guard cannot exceed diagnostic bound
- 0.80 trajectory still has 13 probes
- all dynamic code updates remain single-bit
- no old runner import/dispatch
- no static 84 scheduler path
- no 0.95/1.10 HSPICE scheduler path
- repaired scenario budget = 1
- diagnostic scenario budget = 1
- forbidden hardware tokens absent
```

执行：

```text
python3 -m unittest delay_chain.ftc.tests.test_dynamic_recovery_window_repair
git diff --check
```

全部 PASS 才能进入 Phase 7。

---

# Phase 7 — 唯一一次 0.80 V repaired validation HSPICE

本 Phase 最多允许 1 个新 HSPICE 场景：

```text
recovery_repaired_0p80
```

使用 Phase 5 已冻结的：

```text
recovery_guard_new
```

运行完整 13-probe 0.80 V 动态轨迹。

必须重新验证本电压自己的全部 Gate，因为改变 probe 间隔后，不能只检查 recovery：

```text
coarse Q = 1111111110
fine Q   = 10
hold Q   = 0
final    = (8,1)
```

还必须：

```text
coarse D_code 严格单调
fine D_code 严格单调
每个有效 probe 只有一个有效 CK 上升边沿
没有 q_ambiguous
Q rail validity 通过
Q-settle >= 200 ps
所有 code-update quiet window < 10% VDD
所有 configuration_ck_edge_count = 0
coarse backoff PASS
fine increment PASS
所有 return_fall10 在 recovery_guard_new - 200 ps 之前完成
return_fall10 后没有 second_rise10
recovery 最后 200 ps 所有 xor_29/medium_out/dff_ck < 10% VDD
```

若任何一项失败：

```text
Dynamic Recovery Window Repair = NO-GO
```

停止。不得再次扩大 recovery guard。

---

# 5. HSPICE 预算

整个修复任务最多：

```text
2 个新 HSPICE 场景
```

严格为：

```text
1 x recovery_diagnostic_0p80
1 x recovery_repaired_0p80
```

明确禁止：

```text
0.95 V 新仿真 = 0
1.10 V 新仿真 = 0
旧 0.80 V 2.5 ns 原样重跑 = 0
上游静态 84 场景重跑 = 0
历史 medium/fine/XOR/DFF campaign 重跑 = 0
```

最终 summary 必须显式给出所有这些计数。

---

# 6. 新场景复用合同

scenario identity（场景身份）必须绑定：

```text
study
phase = diagnostic / repaired_validation
vdd_v = 0.80
frozen_baseline_sha256
trajectory_sha256
timing_contract_sha256
medium_N
medium_delay_cell
medium_mux_cell
fine_driver
fine_load
fine_K
sensor_tap
xor_cell
dff_cell
q_read_offset_s
q_settle_s
code_settle_guard_s
recovery_guard_s
control_edge_s
measurement_contract_version
```

每个新场景一旦完整 PASS，只允许复用，不允许因为：

```text
报告文字变化
注释变化
CSV 列排序变化
parser 注释修复
```

而重新跑电气场景。

如果 retained scenario 参数、deck SHA、measurement 不一致，报告冲突，不覆盖原目录。

---

# 7. repaired GO 的总判据

只有以下全部成立才允许：

```text
Dynamic Recovery Window Repair = GO
```

并重新发布：

```text
Dynamic Startup Calibration Protocol = GO
```

硬 Gate：

```text
1. 原始 NO-GO 证据完整保留；
2. 上游静态 84 个场景重跑为 0；
3. 0.95/1.10 动态重跑为 0；
4. 原始 0.80/2.5 ns 场景原样重跑为 0；
5. 新场景数 <= 2；
6. 诊断实测证明旧 2.5 ns failure 是返回活动尚未结束；
7. 新 guard 由实测 return_fall10 + 200 ps 得到，不是手工调参；
8. 物理 topology 完全不变；
9. 0.80 coarse Q = 1111111110；
10. 0.80 fine Q = 10；
11. hold Q = 0；
12. 最终 code = (8,1)；
13. coarse/fine D_code 严格单调；
14. 没有额外 probe CK edge；
15. 没有 q_ambiguous；
16. Q-settle 合同通过；
17. code-update quiet window 通过；
18. configuration CK edge = 0；
19. backoff/fine increment 继续 PASS；
20. 所有返回节点在新 guard 的安全尾部之前进入 <10% VDD；
21. 返回完成后没有第二次 >10% VDD 活动；
22. 没有 bypass/config skip/gating/FSM/margin/droop/PVT/RTL/layout。
```

最终 F 阶段 GO 必须由：

```text
retained 0.95 GO
+
retained 1.10 GO
+
new repaired 0.80 GO
```

组合得到，而不是重新跑三个电压。

---

# 8. NO-GO 分类

至少支持：

```text
upstream_baseline_mismatch
old_failure_not_recovery_only
old_failure_map_incomplete
diagnostic_contract_invalid
recovery_return_did_not_settle_within_diagnostic_bound
return_fall_measurement_missing
return_second_rise_detected
diagnostic_q_sequence_changed
diagnostic_lock_changed
measured_guard_not_greater_than_old_guard
measured_guard_exceeds_diagnostic_bound
repaired_coarse_q_mismatch
repaired_fine_q_mismatch
repaired_lock_hold_mismatch
repaired_final_lock_mismatch
repaired_delay_non_monotonic
repaired_extra_ck_edge
repaired_q_ambiguous
repaired_q_settle_insufficient
repaired_configuration_glitch
repaired_recovery_window_insufficient
hspice_execution_failure
```

任何 NO-GO 都只发布证据，不进入自动硬件改造。

---

# 9. 最终输出

## 9.1 `measured_return_settle.json`

至少：

```text
old_guard_ns
worst_probe_index
worst_protocol_phase
worst_M
worst_F
worst_node
worst_return_rise10_ns
worst_return_fall10_ns
worst_return_settle_ns
second_rise_present
```

## 9.2 `repaired_timing_contract.json`

至少：

```text
old_recovery_guard_s
new_recovery_guard_s
added_guard_s
worst_return_settle_s
safety_tail_s
rounding_quantum_s
derivation
```

## 9.3 `summary.json`

至少：

```text
decision
reasons
baseline_commit
new_diagnostic_hspice_scenarios
new_repaired_hspice_scenarios
reused_new_task_scenarios
upstream_static_84_scenarios_rerun
upstream_static_hspice_rerun
old_dynamic_0p95_rerun
old_dynamic_1p10_rerun
old_dynamic_0p80_rerun
old_recovery_guard_s
new_recovery_guard_s
worst_return_settle_s
retained_0p95_status
retained_1p10_status
repaired_0p80_status
final_dynamic_protocol_decision
```

## 9.4 最终报告

```text
delay_chain/ftc/reports/FTC_DYNAMIC_RECOVERY_WINDOW_REPAIR.md
```

必须明确回答：

```text
1. 原始 0.80 V 到底是哪几个 probe/node 在 2.5 ns 失败？
2. 旧失败终点的峰值为何接近完整 VDD？
3. 实测 S_CLK fall -> xor_29 return fall10 多久？
4. 实测 S_CLK fall -> medium_out return fall10 多久？
5. 实测 S_CLK fall -> dff_ck return fall10 多久？
6. 最坏恢复节点和 probe 是谁？
7. 是否存在 second rise >10% VDD？
8. 新 recovery guard 如何从实测结果计算？
9. 新 guard 比 2.5 ns 增加多少？
10. 是否修改任何硬件单元或拓扑？
11. 0.80 V 修复后 Q 序列是否仍完全匹配黄金参考？
12. 最终 lock 是否仍是 (8,1)？
13. 配置更新是否仍无 CK 毛刺？
14. 0.95/1.10 是否完全没有重跑？
15. 上游 84 个静态场景是否完全没有重跑？
16. 本任务总共新跑几个 HSPICE？
17. 为什么该修复可以解释为 protocol timing repair（协议时序修复），而不是 hardware redesign（硬件重设计）？
18. 修复 GO 后为什么下一阶段仍然是 G 真实控制电路实现，而不是可编程裕量？
```

---

# 10. Codex 严格执行顺序

```text
Step 1  拉取远程 main，确认最新电气基线是否仍为 568f8ace 或其后仅有计划/文档类提交。
Step 2  若 568f8ace 之后已有新的 FTC 电气实现，先重新审查差异；不要盲目执行本计划。
Step 3  读取旧 dynamic summary/lock/timing/probe/transition/report/runner；0 HSPICE。
Step 4  验证 NO-GO 唯一 reason 为 recovery_window_insufficient；0 HSPICE。
Step 5  验证 0.95/1.10 retained GO；0 HSPICE。
Step 6  验证 0.80 Q/lock/monotonic/config transitions 除 recovery 外全部通过；0 HSPICE。
Step 7  SHA256 冻结所有输入证据；0 HSPICE。
Step 8  从 retained measurement 文件恢复 old_failure_map；0 HSPICE。
Step 9  确认具体 failing probes/nodes；0 HSPICE。
Step 10 定义 return rise10/fall10/second-rise measurement contract；0 HSPICE。
Step 11 从 0.80–1.10 V 保留证据推导 T_diag_bound；0 HSPICE。
Step 12 实现新 runner 和 diagnostic deck；不得 import 旧 runner。
Step 13 执行 integration audit、unittest、git diff --check；0 HSPICE。
Step 14 只运行一个 recovery_diagnostic_0p80 新场景。
Step 15 发布 diagnostic_results.csv 和 measured_return_settle.json。
Step 16 若诊断窗口内仍不 settle 或出现 second rise，NO-GO 停止。
Step 17 根据实测最坏 return_fall10 + 200 ps 冻结 recovery_guard_new；0 HSPICE。
Step 18 生成 repaired_timing_contract.json；此后禁止继续调 guard。
Step 19 静态证明只有 recovery guard/measurement contract 改变；0 HSPICE。
Step 20 再次执行全部 unittest 和 git diff --check；0 HSPICE。
Step 21 只运行一个 recovery_repaired_0p80 新场景。
Step 22 重新检查 0.80 V 全部 Q/D/CK/quiet/recovery Gate。
Step 23 若任何 Gate 失败，NO-GO 停止，不进行第二次 guard tuning。
Step 24 若 0.80 GO，组合 retained 0.95 GO + retained 1.10 GO + repaired 0.80 GO。
Step 25 发布 Dynamic Recovery Window Repair = GO。
Step 26 更新最终结论为 Dynamic Startup Calibration Protocol = GO，但保留原始 NO-GO 报告不覆盖。
Step 27 将本 plan 移入 plans/finished/。
Step 28 本任务结束；不得继续实现 G/H/I。
```

---

# 11. 本任务成功后允许推进的唯一下一阶段

如果本计划 GO：

```text
F. 动态启动校准协议 = GO
```

此时已经证明：

```text
静态真实 DFF 分层校准可行
+
动态 M/F 搜索轨迹可行
+
配置切换无有效 CK 毛刺
+
0.80 V 返回恢复窗口可以通过协议时序正确覆盖
```

下一步只能进入：

```text
G. 真实启动校准控制电路实现
```

G 阶段再把当前 testbench（测试平台）完成的 reset sequencing（复位时序）、coarse increment（中调递增）、Q decision（Q 判决）、backoff（回退）、fine increment（细调递增）、lock hold（锁定保持）实现成真实标准单元控制逻辑。

G 完成后仍必须经过 H 完整真实电路验证，之后才能进入 I 可编程检测裕量。

---

# 12. 本计划最终核心判断

> 当前 0.80 V NO-GO 是否只是 recovery guard 对“返回活动结束时间”的定义不足；在不重跑历史静态/已通过动态场景、不修改任何硬件拓扑的前提下，能否通过一次有界返回时序诊断，测得真实最坏 return-fall settle time（返回下降稳定时间），据此冻结新的 recovery guard，并仅用一次新的 0.80 V 连续动态场景证明整个校准协议重新达到 GO？
