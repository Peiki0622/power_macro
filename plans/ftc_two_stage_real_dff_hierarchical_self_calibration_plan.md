# FTC 两级延时线真实 DFF 分层自校准：Codex 逐步骤执行计划

## 0. 任务定位

本计划承接最新已完成的：

```text
818ad2786d79dad3c66db9bf27e182427be10a28
feat(ftc): audit fine-stage waveform contract
```

最新已经证明：

```text
Fine-Stage Delay-Line Waveform Contract = GO
```

当前暂定细调物理合同：

```text
medium stage      = 已完成的 N=16 path-selection 中调级
fine driver       = BUF_X0P8M_A9TL40
fine load         = NOR2_X4A_A9TL40__signal_A
fine K            = 10
```

但是当前仓库仍明确写着：

```text
capture_edge_not_yet_frozen = true
setup_hold_not_yet_frozen   = true
```

因此下一阶段不再继续调整细调负载/驱动器，而是把已经 GO 的两级延时线真正接回历史已经验证过的 real DFF（真实 D 触发器）比较器，并验证：

> **能否通过“先扫中调 M、再扫细调 F”的分层搜索，在真实 DFF 输出 Q 上稳定找到唯一锁定边界。**

本计划只做到：

```text
两级延时线
+
真实 DFF
+
三个锚点电压的分层自校准可行性
```

本计划不做 bypass（旁路）、configuration skip（配置跳过）、报警 margin（裕量）、电压跌落扫描、PVT（工艺/电压/温度）或最终 RTL。

---

# 1. 最重要的执行原则：绝对禁止重跑历史仿真

Codex 必须把历史仿真当作只读证据。

禁止重新执行下列历史 campaign（实验批次）：

```text
path_selection_medium_stage
standard_cell_load_fine_stage
standard_cell_load_max_lvt_probe
standard_cell_load_max_lvt_probe_0p88
standard_cell_load_size_sweep
standard_cell_load_driver_strength_probe
standard_cell_load_fine_stage_driver_codesign
fine_stage_validation_contract_audit
minimal_pulse_comparator
static_self_calibration 的历史 r2
real_xor_pulse_width
```

特别禁止重跑：

```text
历史 path-selection 41 场景
历史 driver-codesign r2 378 场景
历史 validation-contract 19 场景
历史 minimal comparator 场景
历史 static self-calibration r2 场景
历史 real XOR pulse-width 扫描
```

所有上述结果只能读取：

```text
analysis/
runs/
reports/
```

里的既有 evidence（证据）。

**本计划允许的 HSPICE（晶体管级电路仿真器）只能是新拓扑：两级延时线 + real DFF 的新集成场景。**

如果 Codex 发现自己需要重新运行任何旧 runner 的 `main()` 才能获得数据，应立即停止并改为解析已有 evidence。

---

# 2. Codex 开始前必须读取并冻结的最新证据

## 2.1 最新细调 GO

必须读取：

```text
delay_chain/ftc/reports/FTC_FINE_STAGE_VALIDATION_CONTRACT_AUDIT.md
delay_chain/ftc/analysis/fine_stage_validation_contract_audit/summary.json
delay_chain/ftc/analysis/fine_stage_validation_contract_audit/future_capture_contract.json
delay_chain/ftc/analysis/fine_stage_validation_contract_audit/two_cycle_waveforms.csv
delay_chain/ftc/scripts/run_fine_stage_validation_contract_audit.py
```

冻结结论：

```text
Fine-Stage Delay-Line Waveform Contract = GO
selected provisional fine driver = BUF_X0P8M_A9TL40
selected provisional fine load   = NOR2_X4A_A9TL40__signal_A
provisional K                     = 10
```

必须继续冻结：

```text
fixed_absolute_sample_not_a_fine_stage_hard_gate = true
```

不得重新引入 2.5 ns / 5.5 ns 固定电压采样作为延时线有效性的硬 Gate。

## 2.2 中调级

必须读取但不得重跑：

```text
delay_chain/ftc/reports/FTC_PATH_SELECTION_MEDIUM_STAGE.md
delay_chain/ftc/analysis/path_selection_medium_stage/
delay_chain/ftc/scripts/run_path_selection_medium_stage.py
```

冻结：

```text
medium_N          = 16
medium_delay_cell = BUF_X0P7M_A9TL40
medium_mux_cell   = MXT2_X0P5M_A9TL40
```

不允许修改中调拓扑。

## 2.3 历史 real DFF 比较器

必须读取但不得重跑：

```text
delay_chain/ftc/analysis/minimal_pulse_comparator/architecture.json
delay_chain/ftc/analysis/minimal_pulse_comparator/summary.json
delay_chain/ftc/reports/FTC_MINIMAL_PROGRAMMABLE_THRESHOLD_PULSE_COMPARATOR.md
delay_chain/ftc/scripts/run_minimal_pulse_comparator.py
```

冻结 DFF：

```text
DFF cell = DFFRPQ_X0P5M_A9TR40
ports    = Q VDD VNW VPW VSS CK D R
```

历史证据已经证明真实 DFF 的 Q 可以随阈值延时单调形成唯一边界。

历史 `architecture.json` 记录：

```text
minimum_q_settle_s = 2e-10
```

即 200 ps 的 Q 稳定等待时间。

## 2.4 历史 sensor / XOR

必须读取但不得重跑：

```text
delay_chain/ftc/discovery/selected_cells.json
delay_chain/ftc/analysis/real_xor_pulse_width/fine.csv
delay_chain/ftc/scripts/run_real_xor_pulse_width.py
delay_chain/ftc/scripts/run_static_self_calibration.py
```

冻结：

```text
sensor initial RVT stages = 4
sensor initial LVT stages = 0
observable stages         = 30
sensor tap                = 29
XOR cell                  = XOR2_X0P5M_A9TR40
```

三个锚点的历史真实 XOR 脉宽只读参考：

```text
1.10 V : 242.236313 ps
0.95 V : 383.481361 ps
0.80 V : 789.004157 ps
```

这些数据只能用于前置范围判断，不得替代本计划中 real DFF 的新集成结果。

---

# 3. 新的完整物理拓扑

本计划的新 deck（网表）必须是：

```text
                         +------------------------------+
                         |      RVT sensor path         |
S_CLK -------------------+------------------------------+
                         |                              |
                         +------------------------------+
                         |      LVT sensor path         |
                         +------------------------------+
                                        |
                                  tap29 comparison
                                        |
                                        v
                              XOR2_X0P5M_A9TR40
                                        |
                                      xor_29
                         +--------------+----------------+
                         |                               |
                         |                               |
                         v                               v
                      DFF.D                    path-selection medium
                                                   M = 0..16
                                                       |
                                                       v
                                             BUF_X0P8M_A9TL40
                                                fine driver
                                                       |
                                                       v
                                       NOR2_X4A_A9TL40 load bank
                                                 F = 0..K
                                                       |
                                                       v
                                                    DFF.CK
                                                       |
                                                       v
                                                    DFF.Q
```

最关键的连接：

```text
DFF.D  = xor_29
DFF.CK = 延迟后的 xor_29
```

也就是说，新的两级延时线必须以 `xor_29` 为输入，而不是以原 fine-stage 独立测试中的普通 `in` 节点为输入。

中调网络中的 buffer（缓冲器）仍然全部固定为 `BUF_X0P7M_A9TL40`。

只在 medium output 后使用：

```text
BUF_X0P8M_A9TL40
```

作为细调驱动器。

细调负载仍然固定为：

```text
NOR2_X4A_A9TL40
signal=A
control=B
high_cap_control=0
low_cap_control=1
```

---

# 4. 新任务文件和目录

新增：

```text
delay_chain/ftc/scripts/run_two_stage_real_dff_hierarchical_calibration.py
delay_chain/ftc/analysis/two_stage_real_dff_hierarchical_calibration/
delay_chain/ftc/runs/two_stage_real_dff_hierarchical_calibration/
delay_chain/ftc/reports/FTC_TWO_STAGE_REAL_DFF_HIERARCHICAL_CALIBRATION.md
delay_chain/ftc/tests/test_two_stage_real_dff_hierarchical_calibration.py
```

不得覆盖任何历史目录。

推荐复用经过审查的纯 helper（辅助函数），但不得调用历史 runner 的 `main()`。

允许读取/复用的逻辑包括：

```text
历史 sensor/XOR 网表生成逻辑
path-selection medium 的拓扑 helper
fine load bank 的 thermometer（温度计码）helper
HSPICE listing/measurement parser
历史 real-DFF 的 reset/Q read 判定逻辑
```

但新 runner 必须拥有独立的 scenario identity（场景身份）和独立输出目录。

---

# Phase 0 — 冻结证据与新集成合同（0 个 HSPICE）

生成：

```text
delay_chain/ftc/analysis/two_stage_real_dff_hierarchical_calibration/requirements.json
```

至少记录：

```text
upstream_fine_waveform_decision = GO
upstream_commit = 818ad2786d79dad3c66db9bf27e182427be10a28

medium_N = 16
medium_delay_cell = BUF_X0P7M_A9TL40
medium_mux_cell = MXT2_X0P5M_A9TL40

fine_driver = BUF_X0P8M_A9TL40
fine_load = NOR2_X4A_A9TL40__signal_A
initial_K = 10

sensor_tap = 29
sensor_initial_rvt_stages = 4
sensor_initial_lvt_stages = 0
xor_cell = XOR2_X0P5M_A9TR40
dff_cell = DFFRPQ_X0P5M_A9TR40
minimum_q_settle_s = 2e-10

anchor_vdd_v = [1.10, 0.95, 0.80]

historical_hspice_rerun = 0
load_rescan = forbidden
driver_rescan = forbidden
medium_redesign = forbidden
bypass = future_work
config_skip = future_work
programmable_margin = future_work
droop = forbidden
pvt = forbidden
rtl = forbidden
layout = forbidden
```

还必须保存所有读取证据的 SHA256。

---

# Phase 1 — 静态集成审计（0 个 HSPICE）

这一阶段只生成 deck skeleton（网表骨架）和 contract，不执行仿真。

必须静态证明：

```text
1. sensor 路径与历史 real-XOR 拓扑一致；
2. XOR cell 和 tap29 不变；
3. xor_29 同时连接到 DFF.D 和 medium-stage input；
4. DFF.CK 只连接新两级延时线输出；
5. DFF cell 与历史 comparator 相同；
6. medium stage 完全保持 N=16 及原 BUF/MUX；
7. fine driver 只为 X0P8；
8. fine load 只为 NOR2_X4A signal=A；
9. K 初始为 10；
10. 没有历史 3-bit MUX threshold tree；
11. 没有 bypass；
12. 没有 configuration skip；
13. 没有理想 delay 元件；
14. 没有理想 capacitor（电容）替代标准单元负载。
```

生成：

```text
integration_contract.json
```

若任何静态合同失败：

```text
Two-Stage Real-DFF Integration = ARCHITECTURE_BLOCKED
```

0 HSPICE 停止。

---

# Phase 2 — 只读估算 Q 读取时刻（0 个 HSPICE）

不能机械沿用历史 `Q_READ_TIME_S = 3 ns`。

原因：当前新延时线在 0.80 V 深路径的传播延时已经超过 1 ns，而 `xor_29` 本身的上升时间也明显晚于 S_CLK launch（发射边沿）。

本阶段只读取：

```text
real_xor_pulse_width/fine.csv
fine_stage_validation_contract_audit/two_cycle_waveforms.csv
```

估算三个锚点中最大的：

```text
t_CK_projected_max = t_xor29_rise + D_delay_max
```

符号说明：`t_CK_projected_max` 表示新 DFF.CK 最晚可能出现的预测上升时刻；`t_xor29_rise` 是历史真实 `xor_29` 上升时刻；`D_delay_max` 是当前两级延时线在相同电压下已测的最大代表传播延时；`+` 表示两个时间量相加。

新的固定 Q 读取时刻必须满足：

```text
q_read_time >= t_CK_projected_max + 200 ps
```

符号说明：`q_read_time` 是仿真读取 DFF 输出 Q 的时刻；`t_CK_projected_max` 是预测最晚 CK 上升时刻；`200 ps` 是历史真实 DFF 已冻结的最小 Q settle（稳定）时间；`+` 表示在捕获边沿后增加稳定等待时间；`>=` 表示读取必须不早于该安全时刻。

同时 `q_read_time` 必须位于下一次 sensor/XOR 功能事件到来前的安静窗口中。

如果现有输入周期无法提供安全读取窗口，只允许增加 testbench（测试平台）周期/停止时间；不得改变电路器件或延时线。

生成：

```text
q_read_contract.json
```

---

# Phase 3 — 0.95 V 首先验证分层搜索算法

先只做典型电压：

```text
VDD = 0.95 V
```

如果典型点失败，不继续 1.10/0.80 V。

## Step 3.1：中调扫描

固定：

```text
F = 0
K = 10
M = 0..16
```

共 17 个新 HSPICE 场景。

每个场景至少测量：

```text
t_xor_rise
t_xor_fall
t_ck_rise
q_final_v
D_code_ps
W_xor_ps
```

其中：

```text
D_code_ps = t_ck_rise - t_xor_rise
```

符号说明：`D_code_ps` 表示当前中调/细调配置下两级阈值延时；`t_ck_rise` 是真实 DFF.CK 第一次上升跨过 50% VDD 的时刻；`t_xor_rise` 是真实 `xor_29` 第一次上升跨过 50% VDD 的时刻；`-` 表示两者时间差。

```text
W_xor_ps = t_xor_fall - t_xor_rise
```

符号说明：`W_xor_ps` 表示当前新集成网表里真实 XOR 脉宽；`t_xor_fall` 是第一次下降跨过 50% VDD 的时刻；`t_xor_rise` 是第一次上升跨过 50% VDD 的时刻；`-` 表示脉宽时间差。

Q 仍按历史 comparator 的真实 DFF 方式读取：

```text
Q = 1 if q_final_v >= VDD/2 else 0
```

符号说明：`Q` 是数字化后的 DFF 输出；`q_final_v` 是安全读取时刻测得的 DFF.Q 电压；`VDD/2` 是供电电压的一半；`>=` 表示 Q 电压高于等于半电源时记为 1，否则记为 0。

必须同时要求：

```text
t_ck_rise <= q_read_time - 200 ps
```

符号说明：`t_ck_rise` 是 DFF 捕获时钟边沿；`q_read_time` 是 Q 读取时间；`200 ps` 是稳定等待时间；`-` 表示从读取时刻往前留出稳定时间；`<=` 表示 CK 必须足够早。

### 中调 GO 条件

按 M 递增后：

```text
D_code_ps 严格增加
```

且 Q 序列必须只有一次：

```text
1 -> 0
```

允许：

```text
11111100000000000
```

不允许：

```text
全 1
全 0
1->0->1
0->1
多次翻转
```

定义：

```text
M_transition = 第一个 Q=0 的中调代码
M_fine       = M_transition - 1
```

符号说明：`M_transition` 是第一次出现 Q=0 的中调代码；`M_fine` 是后续细调扫描固定使用的中调代码；`- 1` 表示回退一个中调档，让 fine stage（细调级）覆盖剩余距离。

必须满足：

```text
1 <= M_transition <= 16
```

符号说明：`M_transition` 必须位于中调代码 1 到 16 之间；`<=` 表示包含边界。这样既存在一个更短的前一中调档，也存在一个真实 Q 翻转。

若不满足，停止典型点并分类：

```text
coarse_range_too_long_at_M0
coarse_range_too_short_at_M16
coarse_q_non_monotonic
coarse_delay_non_monotonic
dff_capture_invalid
```

不得在本任务中通过换 driver/load 来救援。

## Step 3.2：细调扫描

固定：

```text
M = M_fine
F = 0..10
K = 10
VDD = 0.95 V
```

共 11 个新 HSPICE 场景。

要求：

```text
D_code_ps 随 F 严格增加
```

Q 序列只能有一次：

```text
1 -> 0
```

定义：

```text
F_lock = 第一个 Q=0 的细调代码
```

符号说明：`F_lock` 表示当前固定中调档下第一次使真实 DFF 输出变为 0 的细调代码。

必须满足：

```text
1 <= F_lock <= 10
```

符号说明：`F_lock` 必须位于 1 到 10 的合法细调范围内；`<=` 表示包含两端。

如果 `F=0` 已经 Q=0，则说明回退一个中调档仍然太慢，应分类：

```text
fine_entry_already_late
```

如果 `F=10` 仍然 Q=1，则说明真实 DFF 接入以后当前 K 范围不足，应分类：

```text
fine_range_insufficient_after_dff_load
```

本任务不自动重新搜索负载。

---

# Phase 4 — 扩展到 1.10 V 和 0.80 V

只有 0.95 V 完整通过 Phase 3 才执行。

分别对：

```text
1.10 V
0.80 V
```

严格重复同样的分层流程：

```text
F=0 扫 M=0..16
      ↓
找到唯一 M_transition
      ↓
M=M_transition-1
      ↓
扫 F=0..10
      ↓
找到唯一 F_lock
```

每个电压最多：

```text
17 + 11 = 28 个新 HSPICE 场景
```

符号说明：`17` 是 17 个中调代码；`11` 是 11 个细调代码；`+` 表示场景数相加；结果是每个电压最多 28 个新场景。

三个锚点完整上限：

```text
3 * 28 = 84 个新 HSPICE 场景
```

符号说明：`3` 表示 1.10、0.95、0.80 V 三个锚点；`28` 是每个电压最多的新场景数；`*` 表示乘法；结果为最多 84 个新 HSPICE 场景。

这是**新集成拓扑**的场景，不属于历史仿真重跑。

---

# Phase 5 — 真实 DFF 分层自校准 GO / NO-GO 判定

## 5.1 GO 条件

三个锚点都必须同时满足：

```text
1. 中调 D_code_ps 严格单调；
2. 中调 Q 只有一次 1->0；
3. M_transition 位于 1..16；
4. 细调 D_code_ps 严格单调；
5. 细调 Q 只有一次 1->0；
6. F_lock 位于 1..10；
7. 所有 CK 捕获边沿都留足 200 ps Q settle；
8. q_final_v 可被明确数字化，不出现无法稳定判断的 Q；
9. 新集成的 XOR pulse（脉冲）真实存在且 W_xor_ps > 0；
10. 无 HSPICE incomplete/fatal/convergence failure；
11. 历史仿真重跑数为 0；
12. 没有新增 driver/load/medium 搜索。
```

若全部成立：

```text
Two-Stage Real-DFF Hierarchical Self-Calibration = GO
```

并输出三个锚点的：

```text
M_transition
M_fine
F_lock
D_lock_ps
W_xor_ps
D_minus_W_ps
q_read_time_s
```

其中：

```text
D_minus_W_ps = D_lock_ps - W_xor_ps
```

符号说明：`D_minus_W_ps` 是锁定配置的阈值延时相对真实 XOR 脉宽的时间差；`D_lock_ps` 是 `(M_fine,F_lock)` 配置的真实 DFF.CK 延时；`W_xor_ps` 是同一新集成网表里的真实 XOR 脉宽；`-` 表示两者时间差。该量只用于分析，不替代真实 DFF.Q 作为锁定判据。

## 5.2 NO-GO 必须明确分类

允许的根因分类：

```text
coarse_range_too_long_at_M0
coarse_range_too_short_at_M16
coarse_delay_non_monotonic
coarse_q_non_monotonic
fine_entry_already_late
fine_range_insufficient_after_dff_load
fine_delay_non_monotonic
fine_q_non_monotonic
q_settle_window_insufficient
q_ambiguous
xor_pulse_invalid
dff_capture_invalid
hspice_execution_failure
```

NO-GO 后必须停止。

不得顺手执行：

```text
换 X1/X1P4/X2 driver
换 NOR 单元尺寸
重新扫描 NAND/NOR
修改 medium buffer/mux
加入 bypass
加入 config skip
```

这些必须根据具体 NO-GO 原因另开新计划。

---

# 6. 当前阶段不要实现 bypass 和 configuration skip

这两个模块只在测出真实需求后引入。

## 6.1 什么时候才需要 bypass

如果 real DFF 新集成结果出现：

```text
M=0,F=0 已经 Q=0
```

并且确认不是 Q read/捕获合同错误，则说明当前两级延时线最小固定延时已经太大，真正存在：

```text
coarse_range_too_long_at_M0
```

下一计划才引入 bypass。

## 6.2 什么时候才需要 configuration skip

如果：

```text
D_code_ps 单调
```

但是跨 M/F 层级时 Q 出现多次翻转，或未来完整二维配置出现级间延时下降，则下一计划再研究 configuration skip。

如果三个锚点都能通过：

```text
先 M 后 F
```

找到唯一锁定点，则当前启动自校准不要求先实现全局二维线性代码。

---

# 7. 防止历史仿真被误触发的实现要求

新 runner 中禁止：

```text
subprocess 调用任何历史 runner
import 历史 runner 后触发 main
清空任何历史 runs 目录
修改任何历史 scenario_manifest.json
修改任何历史 summary/report/CSV
```

建议：

```text
只 import 无副作用 helper
或者把必要纯函数复制为新任务局部 helper 并注明来源
```

新 scenario identity 至少包含：

```text
study
phase
vdd_v
medium_code
fine_code
medium_N
medium_delay_cell
medium_mux_cell
fine_driver_cell
fine_load_cell
fine_K
sensor_tap
sensor_rvt_initial_stages
sensor_lvt_initial_stages
xor_cell
dff_cell
q_read_time_s
q_settle_s
input_period_s
```

所有新场景独立写入：

```text
delay_chain/ftc/runs/two_stage_real_dff_hierarchical_calibration/
```

---

# 8. 新实验的早停和仿真预算

Codex 必须早停，不能无意义跑满 84 个场景。

顺序固定：

```text
0.95 V 中调 17 场景
   |
   +-- FAIL -> 立即停止
   |
   +-- GO
        |
        v
0.95 V 细调 11 场景
   |
   +-- FAIL -> 立即停止
   |
   +-- GO
        |
        v
1.10 V 中调 + 细调
   |
   +-- FAIL -> 立即停止
   |
   +-- GO
        |
        v
0.80 V 中调 + 细调
   |
   +-- FAIL -> 立即停止
   |
   +-- GO -> 最终 GO
```

同一个场景只允许运行一次；如果任务中断，必须根据 scenario manifest 和完整 HSPICE listing 判断是否可以复用，不得无条件重跑。

最终 `summary.json` 必须记录：

```text
new_hspice_scenarios
reused_new_task_scenarios
historical_hspice_rerun
historical_medium_rerun
historical_driver_codesign_rerun
historical_validation_audit_rerun
historical_static_calibration_rerun
historical_xor_rerun
```

所有 `historical_*_rerun` 必须为 0。

---

# 9. 回归测试要求

新增：

```text
delay_chain/ftc/tests/test_two_stage_real_dff_hierarchical_calibration.py
```

至少测试：

```text
1. 最新 upstream fine waveform decision 必须是 GO；
2. primary fine driver 必须为 BUF_X0P8M_A9TL40；
3. primary fine load 必须为 NOR2_X4A_A9TL40__signal_A；
4. initial K 必须为 10；
5. medium N/BUF/MUX 不得变化；
6. sensor tap29 / XOR / DFF 不得变化；
7. DFF.D 必须来自 xor_29；
8. medium input 必须来自 xor_29；
9. DFF.CK 必须来自两级延时线输出；
10. 新 deck 不得出现历史 3-bit threshold MUX tree；
11. 新 deck 不得出现 bypass/config-skip；
12. 新 deck 不得出现理想 delay/capacitor；
13. q_read_time 必须满足 projected max CK + 200 ps；
14. q_read_time 必须在下一功能事件之前；
15. 中调 schedule 必须严格为 M=0..16, F=0；
16. 细调 schedule 只能在 M_transition-1 上运行 F=0..10；
17. 一个电压中调失败后不得继续细调；
18. 0.95 V 失败后不得继续 1.10/0.80 V；
19. 总新 HSPICE 不得超过 84；
20. 任何历史 runner main 不得被调用；
21. historical_*_rerun 必须全部为 0；
22. GO 必须要求三个锚点均得到唯一 M 和 F 边界。
```

至少执行：

```text
python3 -m unittest delay_chain.ftc.tests.test_two_stage_real_dff_hierarchical_calibration
git diff --check
```

测试本身不得启动 HSPICE。

---

# 10. Codex 严格执行顺序

```text
Step 1  拉取远程 main，确认 818ad278 之后是否有新提交。
Step 2  充分读取最新 fine waveform GO evidence；0 HSPICE。
Step 3  读取 path-selection medium GO；0 HSPICE，不重跑 41 场景。
Step 4  读取 real XOR / minimal comparator / static calibration 历史证据；0 HSPICE。
Step 5  冻结 X0P8 + NOR2_X4A + K10；不做任何 load/driver 搜索。
Step 6  新建 two_stage_real_dff_hierarchical_calibration 任务目录。
Step 7  生成 requirements.json 和 source SHA256；0 HSPICE。
Step 8  静态生成并审计新集成 topology；0 HSPICE。
Step 9  用历史 evidence 估算 q_read_time；0 HSPICE。
Step 10 先运行 0.95 V、F=0、M=0..16 的 17 个新集成场景。
Step 11 检查 D_code 单调性和唯一 Q 1->0；失败立即停止。
Step 12 计算 M_transition 和 M_fine=M_transition-1。
Step 13 只在 M_fine 扫 F=0..10，共 11 个新集成场景。
Step 14 检查 fine delay 单调性和唯一 Q 1->0；失败立即停止。
Step 15 记录 0.95 V 的 F_lock。
Step 16 若 0.95 V GO，再重复 1.10 V 的 17+11 分层扫描。
Step 17 若 1.10 V GO，再重复 0.80 V 的 17+11 分层扫描。
Step 18 三个锚点全部 GO 后生成 lock_table.json。
Step 19 发布 Two-Stage Real-DFF Hierarchical Self-Calibration = GO。
Step 20 若任一步 NO-GO，只发布明确根因，不继续添加 bypass/config skip 或换标准单元。
Step 21 本任务结束；不得继续做 margin、droop、PVT、RTL 或 layout。
```

---

# 11. 输出文件

必须生成：

```text
delay_chain/ftc/analysis/two_stage_real_dff_hierarchical_calibration/requirements.json
delay_chain/ftc/analysis/two_stage_real_dff_hierarchical_calibration/integration_contract.json
delay_chain/ftc/analysis/two_stage_real_dff_hierarchical_calibration/q_read_contract.json
delay_chain/ftc/analysis/two_stage_real_dff_hierarchical_calibration/coarse_scan.csv
delay_chain/ftc/analysis/two_stage_real_dff_hierarchical_calibration/fine_scan.csv
delay_chain/ftc/analysis/two_stage_real_dff_hierarchical_calibration/lock_table.json
delay_chain/ftc/analysis/two_stage_real_dff_hierarchical_calibration/summary.json
delay_chain/ftc/reports/FTC_TWO_STAGE_REAL_DFF_HIERARCHICAL_CALIBRATION.md
```

若任务早停，尚未运行阶段对应的输出可不存在，但 `summary.json` 和报告必须存在并明确写 `NOT_RUN`。

---

# 12. 最终报告必须回答的问题

最终报告至少回答：

```text
1. 本任务读取了哪些历史证据，哪些历史 HSPICE 明确没有重跑？
2. 新集成 topology 是否严格保持 sensor/XOR/DFF 和已 GO 的 medium/fine 单元？
3. 为什么 q_read_time 不能继续机械使用 3 ns？
4. 实际选择的 q_read_time 是多少，为什么满足 200 ps Q settle？
5. 0.95 V 的中调 Q 序列是什么，唯一 M_transition 在哪里？
6. 0.95 V 的细调 Q 序列是什么，F_lock 在哪里？
7. 1.10 V 和 0.80 V 的 M_transition / F_lock 分别是多少？
8. 三个电压的 D_code 是否在中调和细调两阶段均单调？
9. 是否存在 Q 多次翻转或模糊电平？
10. real DFF 接入后 K=10 是否仍然足够？
11. 若 GO，为什么现在仍不能称为完整 FTC droop macro GO？
12. 若 NO-GO，根因是否真正指向 bypass、config skip、K 范围或捕获窗口中的某一项？
13. 本任务新增多少 HSPICE，复用了多少本任务新场景？
14. 所有 historical_*_rerun 是否均为 0？
```

---

# 13. 下一阶段的分叉条件

如果本计划 GO：

```text
Fine waveform GO
      +
Real-DFF hierarchical calibration GO
      |
      v
下一阶段：扩展 0.80~1.10 V 启动自校准轨迹
      |
      v
再加入 programmable margin
      |
      v
最后进入 droop detection
```

如果本计划 NO-GO，则只根据实测根因进入对应分支：

```text
M0/F0 已经过慢        -> bypass 计划
跨级/二维切换非单调  -> configuration-skip 计划
K10 不足              -> 只做 bounded K re-sizing 计划
Q settle 不足         -> capture/readout contract 计划
DFF Q 非单调          -> comparator/capture root-cause 计划
```

禁止再次回到“盲目换 driver / 盲目换负载”的循环。

---

# 14. 本计划的核心目标

这一阶段唯一要回答的是：

> **已经 GO 的两级延时线，接入真实 sensor/XOR/DFF 后，能不能通过“先中调、后细调”的有限搜索稳定找到唯一真实 DFF 锁定点？**

如果答案是 GO，我们就拥有了一个真正可以继续发展为启动自校准阈值 macro（宏单元）的物理核心。

如果答案是 NO-GO，也必须第一次把根因落到明确的系统接口上，而不是再次通过随机改变标准单元来试错。
