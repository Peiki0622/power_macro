# FTC 真实可达路径验收语义修复与一次性正式收敛计划

## 0. 任务定位

本计划承接当前远程最新电气基线：

```text
8fa8ac1fc433a0840bb20ce6e5b07d8206b97c9d
feat(ftc): diagnose DFF aperture and recovery guard
```

当前正式状态仍为：

```text
DFF 保持/捕获孔径协议修复 = NO-GO
动态启动校准协议 = NO-GO
```

当前已知的关键矛盾不是“真实选中校准路径已经失败”，而是当前第三版验收程序把大量为了单次 HSPICE 预渲染而存在、真实控制流程实际上不会执行的探测点和分支，也加入了最终通过/不通过判定。

当前 0.80 V 第三版结果已经测得：

```text
中调边界 = 9
两级回退后细调基础码 = 7
细调边界 = 5
保护细调码 = 6
保护探测 = PASS
锁定保持探测 = PASS
```

但第三版总体仍因 `recovery_tail_not_below_0p1_vdd` 被判 NO-GO。现有恢复审计进一步显示：

```text
中调探索失败 = 2
细调探索失败 = 17
选中细调分支失败 = 0
保护探测失败 = 0
锁定保持失败 = 0
```

其中大量失败来自：

```text
中调码 10
未被选择的中调码 8 / 9 细调分支
以及这些反事实分支中的高细调码
```

本计划只解决一个核心问题：

> 将“为了覆盖所有可能决策而预渲染的电气状态”和“真实控制器在当前测量结果下实际会执行的状态”严格分离，先用零 HSPICE 重放现有测量，证明当前 NO-GO 是否由验收语义错误造成；若零仿真证据允许，再一次性生成真正的可达路径专用电气场景，对 0.80 / 0.95 / 1.10 V 做最终正式验证。

本计划不是继续调恢复时间，也不是修改硬件。

---

# 1. 当前必须冻结的远程事实

Codex 开始时必须重新读取并计算 SHA256，至少包括：

```text
delay_chain/ftc/scripts/run_dff_reset_capture_repair.py

delay_chain/ftc/analysis/dff_reset_capture_repair/acceptance_results.json
delay_chain/ftc/analysis/dff_reset_capture_repair/acceptance_probe_results.csv
delay_chain/ftc/analysis/dff_reset_capture_repair/acceptance_transition_audit.csv
delay_chain/ftc/analysis/dff_reset_capture_repair/recovery_gate_audit.json
delay_chain/ftc/analysis/dff_reset_capture_repair/recovery_diagnostic_results.csv
delay_chain/ftc/analysis/dff_reset_capture_repair/recovery_diagnostic_summary.json
delay_chain/ftc/analysis/dff_reset_capture_repair/recovery_diagnostic_contract.json
delay_chain/ftc/analysis/dff_reset_capture_repair/guarded_lock_contract.json
delay_chain/ftc/analysis/dff_reset_capture_repair/classification.json

delay_chain/ftc/analysis/dynamic_m8_history_dependence_root_cause/classification.json
delay_chain/ftc/analysis/dynamic_m8_history_dependence_root_cause/repeatability_audit.csv
```

必须验证当前事实仍为：

```text
0.80 V：第三版状态 = NO-GO
0.95 V：第三版状态 = GO
1.10 V：第三版状态 = GO

0.80 V：
coarse_boundary = 9
primary_medium_base = 7
fine_boundary = 5
guard_code = 6
guard_probe_index = 36
lock_hold_probe_index = 37

0.80 V 当前总体失败原因只包含：
recovery_tail_not_below_0p1_vdd
```

还必须验证：

```text
M7/M8/M9 的动态延时升序单调性没有被否定
中调历史效应小于重复噪声门限
配置切换有效 CK 毛刺未被确认
```

若最新提交已经改变这些电气事实，则：

```text
真实可达路径验收修复 = 上游阻塞
```

0 个新 HSPICE，停止并报告差异。

---

# 2. 本计划首先修正的概念错误

当前第三版为了让一个预先写好的瞬态网表覆盖所有可能分支，预渲染了：

```text
所有候选中调码的双探测
+
多个候选细调基础码下的完整 F=0..K 扫描
+
大量重复探测
+
分支清理过程
```

这作为“证据采集”是允许的。

但正式验收必须区分两类状态：

```text
真实可达：
按照已经定义的校准决策规则，实际控制器会执行的探测/配置更新。

反事实仅诊断：
为了提前覆盖其他可能分支而放进网表，但在当前测量结果下真实控制器不会执行的探测/配置更新。
```

新判定器必须满足：

```text
只有真实可达状态可以决定正式通过/不通过。
反事实仅诊断状态可以保留全部电气结果，但不得把失败原因加入正式总体失败原因。
```

禁止通过删除反事实数据来“做出 GO”。所有反事实数据仍必须发布，只是语义从“正式验收”改成“诊断覆盖”。

---

# 3. 绝对禁止事项

本任务禁止：

```text
重跑上游 84 个静态场景
重跑旧 2.5 ns 动态场景
重跑旧 3.3 ns 恢复诊断场景
重跑第三版 0.80 / 0.95 / 1.10 预渲染验收场景
重跑第四版 5 ns 恢复诊断场景

修改传感器
修改异或门
修改中调 N=16
修改中调缓冲器/多路选择器
修改细调驱动/负载/K=10
修改 DFF 单元
加入配置跳过
加入旁路
加入时钟门控
加入控制状态机
加入可编程裕量
加入电压跌落/PVT/版图
```

特别禁止：

```text
先把 2.7 ns 改成 2.8 ns 再试一次
2.7 / 2.8 / 2.9 / 3.0 ns 扫描
用不可达的 M9/F10 直接决定功能恢复时间
```

---

# 4. 新任务目录

新建：

```text
delay_chain/ftc/scripts/run_reachable_path_acceptance.py

delay_chain/ftc/analysis/reachable_path_acceptance/
  frozen_evidence.json
  decision_semantics.json
  reachable_replay_0p80.json
  reachable_replay_0p95.json
  reachable_replay_1p10.json
  probe_reachability.csv
  transition_reachability.csv
  counterfactual_failures.csv
  reachable_failure_audit.json
  reachable_recovery_audit.json
  reachable_guard_derivation.json
  exact_path_contract.json
  exact_path_probe_results.csv
  exact_path_transition_audit.csv
  exact_path_results.json
  summary.json

delay_chain/ftc/runs/reachable_path_acceptance/

delay_chain/ftc/reports/FTC_REACHABLE_PATH_ACCEPTANCE.md

delay_chain/ftc/tests/test_reachable_path_acceptance.py
```

不得覆盖或修改现有：

```text
dff_reset_capture_repair
dynamic_m8_history_dependence_root_cause
dynamic_recovery_window_repair
dynamic_startup_calibration_protocol
```

旧 NO-GO 和全部历史证据永久保留。

---

# Phase 0 — 冻结基线并审计当前判定器（0 HSPICE）

先读取当前 `run_dff_reset_capture_repair.py`。

必须显式确认当前第三版判定器存在以下结构：

```text
先把全部探测的电气失败加入总体 reasons
先把全部配置切换失败加入总体 reasons
然后才选择 coarse boundary / fine base / fine boundary / guard / hold
```

将这一点发布到：

```text
frozen_evidence.json
```

并标记：

```text
legacy_acceptance_semantics = all_prerendered_rows_are_global_gates
```

如果源码已经修复为先判断可达性再聚合失败，则不得重复实现，先审查现有新逻辑。

---

# Phase 1 — 冻结“真实控制流程”的决策语义（0 HSPICE）

新任务必须先写 `decision_semantics.json`，之后所有重放和最终场景都只能使用这一个语义合同。

## 1.1 中调决策

从 M=0 开始逐级增加。

每一个中调码执行两个独立完整探测：

```text
中调扫描探测
中调重复探测
```

判定规则沿用第三版：

```text
两次均稳定高：继续到 M+1
两次均稳定低：确认该 M 为中调边界，立即停止继续上扫
模糊或两次不一致：不能确认边界，按照现有第三版规则继续记录并进入下一 M
```

一旦第一个“双稳定低”出现，所有更大的中调探测都标记为：

```text
counterfactual_after_coarse_stop
```

不得参与正式失败聚合。

## 1.2 两级中调回退

确认中调边界后：

```text
细调基础码 = 中调边界 - 2
```

“减 2”表示将中调温度计码逐位回退两级。

关键要求：

> 回退过程是配置更新，不是新的比较探测。

例如 0.80 V 若边界为 M9，则真实控制流程应执行：

```text
M9 -> M8 配置更新
M8 -> M7 配置更新
然后才在 M7/F0 做细调探测
```

不得为了单比特更新而人为在 M8 插入一个 S_CLK 比较脉冲。

每次配置更新仍必须满足：

```text
只改变一个温度计码位
DFF 处于复位状态
S_CLK 保持低
配置稳定时间合同满足
```

## 1.3 细调决策

在选定的中调基础码上，从 F=0 开始顺序扫描。

真实流程不是“每一个 F 都重复两次”。

规则冻结为：

```text
F0、F1、F2……逐个执行一次扫描探测；
第一个不是 stable_high（稳定高）的 F 定义为细调边界；
然后进入 F+1 作为保护细调码；
保护细调码执行一次正式保护探测；
同一个保护细调码再执行一次独立锁定保持探测；
只有保护探测和锁定保持探测都 stable_low（稳定低）才允许锁定。
```

因此，为了支持任意候选边界而在第三版网表中预渲染的其他 repeat（重复探测）必须标记为反事实，除非它恰好成为最终保护码的锁定保持探测。

## 1.4 细调回退分支

第三版允许最多一次中调基础码 +1 的回退分支，但只有当第一基础码直到 F=K-1 都没有形成合法细调边界时才允许进入。

若第一基础码已经形成合法边界并通过保护/保持：

```text
所有其他细调基础码分支 = counterfactual_unselected_fine_branch
```

不得参与正式失败聚合。

## 1.5 锁定以后

保护探测和锁定保持均稳定低后：

```text
状态 = LOCKED
```

之后所有预渲染探测标记：

```text
counterfactual_after_lock
```

不得参与正式失败聚合。

---

# Phase 2 — 用现有第三版测量离线重放真实控制流程（0 HSPICE）

这是本计划最重要的第一道门。

不得调用 HSPICE。

读取第三版三个电压已经存在的：

```text
acceptance_probe_results.csv
acceptance_transition_audit.csv
guarded_lock_contract.json
acceptance_results.json
```

按照 Phase 1 的决策语义逐电压重放。

输出：

```text
reachable_replay_0p80.json
reachable_replay_0p95.json
reachable_replay_1p10.json
probe_reachability.csv
transition_reachability.csv
```

每个预渲染探测至少标记：

```text
scenario
probe_index
medium_code
fine_code
protocol_phase
q_state
reachable
selected_path
counterfactual_only
counterfactual_reason
formal_gate
```

`counterfactual_reason` 至少支持：

```text
after_coarse_stop
coarse_backoff_probe_not_real_operation
fine_repeat_not_selected_as_lock_hold
unselected_fine_branch
after_fine_boundary
after_lock
branch_cleanup_not_real_probe
```

注意：

```text
配置更新本身仍可能是真实可达操作，
但“配置更新后人为插入的探测”可以是反事实。
```

因此 `transition_reachability.csv` 必须独立于 `probe_reachability.csv`，不能简单按 probe 索引继承。

---

# Phase 3 — 重新聚合失败，只允许真实可达状态进入正式 Gate（0 HSPICE）

生成：

```text
counterfactual_failures.csv
reachable_failure_audit.json
```

必须同时发布两套统计：

```text
全部预渲染电气失败数
真实可达电气失败数
```

正式判定只能使用第二个。

每个反事实失败必须保留原始：

```text
probe_index
M
F
失败原因
recovery ratio
原始第三版角色
新的不可达原因
```

这样可以证明不是删除失败，而是修正失败的控制语义。

### 0.80 V 当前基线的预期重放路径

Codex 必须由 CSV 自己重新推导，不能直接硬编码，但当前基线应得到：

```text
M0..M9：每个中调码两个探测
M9：首次双稳定低，停止中调扫描
M9 -> M8 -> M7：两次配置更新，不插入比较脉冲
M7/F0..F5：单次细调扫描
M7/F5：细调边界
M7/F6：保护探测
M7/F6：独立锁定保持探测
LOCK
```

在当前基线下，理论可达探测数量应为：

```text
20 个中调探测
+ 6 个 F0..F5 细调扫描
+ 1 个 F6 保护探测
+ 1 个 F6 锁定保持探测
= 28 个探测
```

其中“+”表示把各阶段实际执行的探测数量相加；结果 28 表示当前 0.80 V 测量对应的真实控制路径预计只需要 28 个比较探测，而不是第三版预渲染的 110 个。

如果离线重放得不到这一路径，必须停止并解释具体哪一个现有测量改变了决策。

---

# Phase 4 — 只对真实可达路径重新审计恢复时间（0 HSPICE）

不要直接采用第四版由全部 110 个预渲染探测得到的 2.8 ns。

先把第四版 5 ns 恢复诊断结果和 Phase 2 得到的真实可达路径做交集。

生成：

```text
reachable_recovery_audit.json
reachable_guard_derivation.json
```

对每一个真实可达探测，读取：

```text
xor_29 返回下降 10% 时间
medium_out 返回下降 10% 时间
dff_ck 返回下降 10% 时间
```

新的功能恢复时间只允许由“真实可达状态中的最坏返回完成时间”推导：

```text
功能恢复时间 = 向上取整到 0.1 ns（真实可达最坏返回完成时间 + 0.200 ns）
```

其中，“真实可达最坏返回完成时间”表示只在实际控制器会执行的探测中取 `dff_ck / medium_out / xor_29` 的最慢返回下降时间；`0.200 ns` 是冻结的安全尾窗；“+”表示返回完成后再增加 200 ps 安静时间；“向上取整到 0.1 ns”表示使用与当前协议一致的时间量化规则。

判定规则：

```text
如果真实可达最坏值推导结果 <= 2.7 ns：
    功能恢复时间继续冻结为 2.7 ns。

如果真实可达最坏值推导结果 > 2.7 ns：
    使用该实测结果冻结新的唯一候选值。

无论结果是多少：
    禁止 sweep（扫描尝试）。
```

特别要求：

```text
M9/F10 等反事实探测不得决定功能恢复时间。
```

---

# Phase 5 — 零仿真分流 Gate

完成 Phase 0~4 后，先得到一个纯证据结论：

## 情况 A：真实可达路径全部通过

要求：

```text
所有真实可达探测 Q 判决合法
所有真实可达活动窗口只有 1 个 CK 有效上升
所有真实可达配置更新无配置诱导 CK 边沿
所有真实可达探测的恢复尾窗通过
保护探测稳定低
锁定保持稳定低
不存在真实可达失败
```

则发布：

```text
旧第三版总体 NO-GO 的主要原因 = 反事实分支被错误纳入全局 Gate
```

然后允许进入 Phase 6。

## 情况 B：真实可达路径仍存在失败

则：

```text
真实可达路径验收修复 = NO-GO
```

停止。

不得通过修改可达性规则隐藏该失败，也不得进入新仿真。

报告必须给出第一个真实可达失败的：

```text
电压
操作序号
M/F
阶段
失败原因
恢复比值/CK/Q 原始证据
```

---

# Phase 6 — 构造“真正控制路径”的新调度器（0 HSPICE）

只有 Phase 5 情况 A 才允许执行。

新 runner 不得直接复用旧的“每次代码变化都绑定一个 probe”的假设。

必须支持三类独立操作：

```text
1. 配置更新操作
2. 比较探测操作
3. 锁定保持探测操作
```

尤其必须支持：

```text
M9 -> M8 配置更新
M8 -> M7 配置更新
```

中间不发 S_CLK 比较脉冲。

每一个配置更新仍需：

```text
单比特码变化
DFF 保持复位
S_CLK 为低
完成 10 ps 控制边沿
满足 1.5 ns 配置稳定合同
```

实际是否每次中间更新都完整等待 1.5 ns，必须在 `exact_path_contract.json` 中显式冻结；不得依赖旧 scheduler 的隐式行为。

建议保守合同：

```text
每一个单比特配置更新都独立满足完整 1.5 ns 稳定时间。
```

这样最终电气验证不会通过压缩两级回退时间获得人为优势。

---

# Phase 7 — 生成三个“真实可达路径专用”正式合同（0 HSPICE）

对：

```text
0.80 V
0.95 V
1.10 V
```

分别使用 Phase 2 的测量决策，生成一个不包含反事实探测的 exact-path（精确路径）网表合同。

当前基线预期：

```text
0.80 V：边界 9，基础码 7，细调边界 5，保护码 6
0.95 V：边界 6，基础码 4，细调边界 5，保护码 6
1.10 V：边界 4，基础码 2，细调边界 8，保护码 9
```

这些值必须由现有第三版测量重新推导后写入合同，不得直接硬编码。

正式路径不得包含：

```text
边界以上的中调探测
未选择细调基础码的探测
无必要的细调 repeat
分支清理 probe
锁定后的任何 probe
```

新场景不是旧第三版场景的重跑，因为：

```text
操作序列不同
时间轴不同
探测数量不同
网表哈希不同
场景身份不同
```

---

# Phase 8 — 一次性静态测试和防返工检查（0 HSPICE）

新增：

```text
delay_chain/ftc/tests/test_reachable_path_acceptance.py
```

至少覆盖：

```text
1. 基线提交和输入 SHA 正确；
2. 旧第三版 0.80/0.95/1.10 状态正确冻结；
3. 旧历史 HSPICE 入口全部不可调度；
4. 新判定器不能在 reachability 确定之前聚合全局 reasons；
5. counterfactual_only 行永远不能加入 formal reasons；
6. 中调在第一个双 stable_low 后停止；
7. 0.80 V M10 被标记 after_coarse_stop；
8. 两级回退是两次配置更新、零次比较探测；
9. 每次回退只改变一个中调温度计码位；
10. 细调 F0 到 boundary 只需要扫描探测；
11. 非 guard 的 fine repeat 被标记反事实；
12. 只有 guard 对应 repeat 成为 lock hold；
13. 第一细调基础码成功后其他细调基础码全部不可达；
14. 锁定以后全部不可达；
15. 0.80 V 当前基线离线重放为 28 个真实探测；
16. 0.95 / 1.10 的真实路径由测量自动推导；
17. reachable recovery 只从可达探测取最大值；
18. M9/F10 不得决定功能 guard，除非它在某个实际路径中真的可达；
19. guard 只能由实测可达 return-fall + 200 ps 推导；
20. 禁止 guard sweep；
21. exact-path 网表不包含未选择分支；
22. exact-path 回退中间没有 S_CLK probe；
23. 每个真实配置更新都有静态 quiet-window 审计；
24. 每个真实 probe 有两个 Q 采样且必须同轨；
25. active CK edge 必须恰好为 1；
26. 保护探测和锁定保持必须是两个独立 probe；
27. 新正式场景预算最多 3 个；
28. 不修改任何硬件单元；
29. 不出现 ConfigSkip/旁路/门控/状态机/裕量/PVT/电压跌落；
30. 所有旧 rerun counter 继续为 0。
```

执行：

```text
python3 -m unittest delay_chain.ftc.tests.test_reachable_path_acceptance
git diff --check
```

全部通过后才能进入 Phase 9。

---

# Phase 9 — 唯一一次正式三电压真实路径 HSPICE 验收

为了避免再次出现“只验证 0.80 V，下一轮又发现 0.95/1.10 时间轴合同不同”的返工，本计划在零仿真 Gate 全部通过后，一次性授权最多 3 个新场景：

```text
1 x exact_path_0p80
1 x exact_path_0p95
1 x exact_path_1p10
```

这 3 个场景必须一次性生成完合同后再运行，不允许看到前一个结果后修改后一个合同。

这不是旧场景重跑，而是第一次验证“真实可达控制路径”的精确时间轴。

每个场景必须验证：

```text
所有预期 Q 决策与离线重放一致
两个 Q 采样同轨
每个探测只有一个有效 CK 上升边沿
无 q_ambiguous（Q 模糊）
所有真实配置更新无 CK 毛刺
所有真实恢复尾窗通过
中调第一个双稳定低边界正确
两级回退正确
细调第一个非稳定高边界正确
保护码稳定低
锁定保持稳定低
最终锁点与 exact-path 合同一致
```

若任一电压失败：

```text
真实可达路径正式验收 = NO-GO
```

停止。

禁止在本计划内：

```text
增加第 4 个场景
改 guard 再跑
改 backoff 再跑
改 fine guard 再跑
改 DFF 再跑
```

失败必须作为新的真实协议证据进入下一份专门计划。

---

# 10. 关于 2.7 ns / 2.8 ns 的最终处理

本计划不得预设 2.8 ns 一定正确，也不得预设 2.7 ns 一定正确。

只允许按以下顺序：

```text
现有第三版可达路径恢复结果
+
现有第四版 5 ns 诊断中“可达探测子集”的真实 return-fall
↓
零 HSPICE 推导唯一功能 guard
↓
在 Phase 9 三个 exact-path 场景中使用同一个冻结 guard
```

如果可达子集证明 2.7 ns 足够，则保留 2.7 ns。

如果可达子集证明必须大于 2.7 ns，则冻结由实测值量化后的唯一结果。

当前全预渲染空间中的 2.8 ns 只能继续作为：

```text
全诊断覆盖空间最坏候选值
```

在完成可达子集审计之前，不得称为最终功能协议恢复时间。

---

# 11. 报告一致性修复

当前远程报告与 `recovery_gate_audit.json` 存在发布不一致：

```text
报告文字声称 19 个 0.80 V 恢复超限探测都有后续操作；
JSON 实际记录 operation_failure_count=18、terminal_failure_count=1。
```

本任务不得修改旧报告历史证据，但新报告必须显式指出并纠正这一发布差异。

所有新的：

```text
summary.json
正式报告
可达失败统计
反事实失败统计
```

必须从同一份结构化数据生成，禁止分别手写数字。

新增测试要求：

```text
报告中的计数必须与 JSON 完全一致。
```

---

# 12. 最终判定层级

必须分开发布两个结论。

## 12.1 判定器修复结论

如果零 HSPICE 离线重放证明：

```text
旧 NO-GO 只来自反事实探测，真实可达路径没有失败
```

则发布：

```text
Reachability-Aware Acceptance Semantics = GO
```

这只证明验收语义修复成立，不等于 F 阶段已经最终 GO。

## 12.2 正式协议结论

只有 Phase 9 三个真实路径场景全部通过，才允许发布：

```text
Exact Reachable-Path Dynamic Startup Calibration = GO
```

随后才允许把 F 阶段重新发布为：

```text
Dynamic Startup Calibration Protocol = GO
```

如果其中任一失败，则保留 F=NO-GO。

---

# 13. HSPICE 预算

本任务前半段：

```text
Phase 0~8 = 0 个 HSPICE
```

只有所有零仿真 Gate 通过后：

```text
Phase 9 最多 = 3 个新 HSPICE
```

严格计数：

```text
旧静态 84 场景重跑 = 0
旧 0.80 动态重跑 = 0
旧 0.95 动态重跑 = 0
旧 1.10 动态重跑 = 0
旧 3.3 ns 诊断重跑 = 0
旧第三版验收重跑 = 0
旧第四版 5 ns 诊断重跑 = 0
新 exact-path 场景 <= 3
```

任何 parser（解析器）、报告、可达性规则修改都必须复用已有新场景，不得重跑电气仿真。

---

# 14. 最终 `summary.json` 必须包含

```text
study
baseline_commit
legacy_decision
legacy_reason
reachability_semantics_decision
formal_exact_path_decision
old_prerendered_probe_count_by_vdd
reachable_probe_count_by_vdd
counterfactual_probe_count_by_vdd
legacy_failure_count_by_vdd
reachable_failure_count_by_vdd
counterfactual_failure_count_by_vdd
coarse_boundary_by_vdd
selected_medium_base_by_vdd
fine_boundary_by_vdd
guard_code_by_vdd
reachable_worst_return_probe
reachable_worst_return_node
reachable_worst_return_settle_s
full_diagnostic_space_guard_s
reachable_functional_guard_s
new_exact_path_hspice_scenarios
all_old_rerun_counters
final_dynamic_protocol_decision
```

---

# 15. 最终报告必须一次回答完的问题

`FTC_REACHABLE_PATH_ACCEPTANCE.md` 必须明确回答：

```text
1. 当前第三版为什么会把 0.80 V 判成 NO-GO？
2. 110 个预渲染探测中到底多少是真实可达？
3. 哪些失败属于真实路径，哪些只属于反事实诊断分支？
4. M10 为什么在本次 0.80 V 实际校准中不可达？
5. M8/M9 的未选择细调分支为什么不可达？
6. 两级 coarse backoff（中调回退）为什么是配置更新而不是比较探测？
7. fine repeat（细调重复探测）中哪些是真实锁定保持，哪些只是预渲染覆盖？
8. 0.80 V 真实路径是不是 28 个 probe（探测）？
9. 0.95 / 1.10 V 的真实路径分别是什么？
10. 2.7 ns 在真实可达路径中是否足够？
11. 2.8 ns 是由哪个状态推导出来的，该状态是否真实可达？
12. 最终功能 recovery guard（恢复保护时间）如何只从可达状态推导？
13. 新 exact-path（精确路径）场景是否完全去掉了反事实功能脉冲？
14. 新场景中所有配置切换是否仍然单比特且无 CK 毛刺？
15. 三个电压最终是否全部通过？
16. 是否修改任何物理硬件？
17. 是否重跑任何旧场景？
18. 本任务新跑了几个 HSPICE？
19. 旧报告 19/19 与 JSON 18+1 的发布矛盾如何处理？
20. F 阶段是否可以正式恢复为 GO？
```

---

# 16. Codex 严格执行顺序

```text
Step 1  拉取 main，确认最新电气基线仍为 8fa8ac1 或其后只有计划/文档提交。
Step 2  冻结第三版、第四版、M8 根因证据全部 SHA；0 HSPICE。
Step 3  审计旧 evaluator（判定器）是否先全局聚合失败、后做分支选择；0 HSPICE。
Step 4  写 decision_semantics.json，冻结真实控制规则；0 HSPICE。
Step 5  实现纯离线 reachability replay（可达性重放）；0 HSPICE。
Step 6  对 0.80 / 0.95 / 1.10 V 分别重放第三版已有测量；0 HSPICE。
Step 7  发布 probe_reachability / transition_reachability；0 HSPICE。
Step 8  分离 reachable failures（可达失败）与 counterfactual failures（反事实失败）；0 HSPICE。
Step 9  若任何真实可达失败存在，NO-GO 停止；不运行新仿真。
Step 10 从第四版 5 ns 结果中只提取真实可达探测子集；0 HSPICE。
Step 11 由真实可达最坏 return-fall + 200 ps 推导唯一功能 recovery guard；0 HSPICE。
Step 12 生成 exact-path 操作图，明确区分配置更新和比较探测；0 HSPICE。
Step 13 确认两级回退不插入比较脉冲；0 HSPICE。
Step 14 生成 0.80 / 0.95 / 1.10 三个 exact-path 合同；0 HSPICE。
Step 15 一次性完成全部 unittest 和 git diff --check；0 HSPICE。
Step 16 若任何静态 Gate 失败，停止。
Step 17 只在全部静态 Gate 通过后运行 3 个 exact-path HSPICE 场景。
Step 18 不根据第一个场景结果修改后两个场景合同。
Step 19 解析三个场景，重新检查 Q/CK/配置安静/恢复/保护/锁定全部 Gate。
Step 20 任一电压失败则 NO-GO，禁止本计划内继续调参。
Step 21 三个电压全部通过才发布 exact reachable-path GO。
Step 22 更新新 summary/report，不覆盖旧 NO-GO 历史证据。
Step 23 将本 plan 移入 plans/finished/。
Step 24 停止；不得自动进入 FSM/裕量/PVT/电压跌落。
```

---

# 17. 本计划最核心的防返工要求

本任务必须一次把下面三层语义分清：

```text
预渲染电气覆盖空间
        ↓
真实控制器可达状态
        ↓
最终正式验收路径
```

不得再出现：

```text
为了 HSPICE 方便预先仿真的状态
=
真实控制器一定会执行的状态
```

也不得走向另一个极端：不能仅靠离线重新贴标签就直接宣布 F 阶段 GO。

正确流程必须是：

```text
先用现有结果零仿真证明旧判定器是否误把反事实失败当正式失败
↓
冻结真实可达操作图和数据驱动 recovery guard
↓
再用一次三电压 exact-path 电气验证证明真正时间轴下仍然成立
↓
才允许恢复 F 阶段 GO
```

本计划的目标不是“让结果变成 GO”，而是保证最终 GO/NO-GO 只由真实控制协议实际会执行的电气操作决定。