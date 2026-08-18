# FTC 动态启动校准协议：Codex 逐步骤执行计划

## 0. 任务定位

本计划对应总体路线中的：

```text
F. 动态启动校准协议
```

它严格承接已经完成并正式 GO 的上一步：

```text
b1f511f57812b07c7d243413af456930ae197f8b
feat(ftc): validate two-stage real-DFF calibration
```

上一步已经证明：

```text
Two-Stage Real-DFF Hierarchical Self-Calibration = GO
```

并得到三个锚点的静态真实 DFF（真实 D 触发器）锁定参考：

```text
1.10 V : M_transition=4, M_fine=3, F_lock=4
0.95 V : M_transition=6, M_fine=5, F_lock=1
0.80 V : M_transition=9, M_fine=8, F_lock=1
```

本阶段不再证明“某个静态 M/F 配置是否可工作”，而是证明：

> 在同一个晶体管级电路、同一次连续 HSPICE 仿真中，按照“中调递增 -> 发现边界 -> 回退一级 -> 细调递增 -> 锁定”的启动校准协议动态改变 M/F 时，真实 sensor/XOR/two-stage delay/DFF 是否仍然稳定工作，代码切换是否会制造额外 DFF.CK 事件，最终 Q 序列和锁点是否与上一步静态黄金参考一致。

本阶段仍由 testbench（测试平台）根据上一步已经知道的黄金轨迹驱动 M/F；本阶段**不实现真实 FSM（有限状态机）/计数器/寄存器控制器**。真实控制电路属于下一阶段 G。

若本阶段通过，只允许发布：

```text
Dynamic Startup Calibration Protocol = GO
```

不得发布完整 macro GO，也不得进入可编程检测裕量。后续顺序必须是：

```text
F. 动态启动校准协议
        ↓
G. 真实启动校准控制电路实现
        ↓
H. 完整真实电路级启动校准验证
        ↓
I. 可编程检测裕量
```

---

# 1. 绝对约束：禁止重跑上一步 84 个静态仿真

Codex 必须把上一步 `two_stage_real_dff_hierarchical_calibration` 的全部结果当作只读黄金证据。

禁止重新执行：

```text
delay_chain/ftc/scripts/run_two_stage_real_dff_hierarchical_calibration.py
```

禁止重新运行其 84 个静态场景，禁止清空、覆盖或修改：

```text
delay_chain/ftc/runs/two_stage_real_dff_hierarchical_calibration/
delay_chain/ftc/analysis/two_stage_real_dff_hierarchical_calibration/
delay_chain/ftc/reports/FTC_TWO_STAGE_REAL_DFF_HIERARCHICAL_CALIBRATION.md
```

尤其禁止为了生成动态 deck 而调用上一步 runner（运行脚本）的 `main()`、`run_voltage()`、`run_one()` 或 `execute_scenario()`。

本阶段只能读取上一步的结果和源码作为 evidence（证据）。

最终 `summary.json` 必须显式记录：

```text
upstream_static_hspice_rerun = 0
upstream_static_84_scenarios_rerun = 0
historical_medium_rerun = 0
historical_fine_rerun = 0
historical_xor_rerun = 0
historical_dff_rerun = 0
```

全部必须为 0。

---

# 2. Codex 开始前必须读取并冻结的远程证据

必须读取：

```text
delay_chain/ftc/analysis/two_stage_real_dff_hierarchical_calibration/summary.json
delay_chain/ftc/analysis/two_stage_real_dff_hierarchical_calibration/lock_table.json
delay_chain/ftc/analysis/two_stage_real_dff_hierarchical_calibration/coarse_scan.csv
delay_chain/ftc/analysis/two_stage_real_dff_hierarchical_calibration/fine_scan.csv
delay_chain/ftc/analysis/two_stage_real_dff_hierarchical_calibration/integration_contract.json
delay_chain/ftc/analysis/two_stage_real_dff_hierarchical_calibration/q_read_contract.json
delay_chain/ftc/analysis/two_stage_real_dff_hierarchical_calibration/requirements.json
delay_chain/ftc/reports/FTC_TWO_STAGE_REAL_DFF_HIERARCHICAL_CALIBRATION.md
delay_chain/ftc/scripts/run_two_stage_real_dff_hierarchical_calibration.py
```

必须确认：

```text
decision = Two-Stage Real-DFF Hierarchical Self-Calibration = GO
new_hspice_scenarios = 84
```

并确认上一步静态集成合同中的以下检查全部为 true：

```text
sensor_matches_historical_real_xor
xor_cell_and_tap29_frozen
xor29_drives_dff_data
xor29_drives_medium_input
dff_clock_only_from_two_stage_output
frozen_n16_medium
only_approved_fine_driver
only_approved_nor_load
initial_K_is_ten
no_historical_three_bit_threshold_tree
no_bypass
no_config_skip
no_ideal_delay
no_ideal_capacitor
```

如果上一步不是 GO，或者任何冻结合同已经变化：

```text
Dynamic Startup Calibration Protocol = UPSTREAM_BLOCKED
```

0 个新 HSPICE，立即停止。

所有上述文件必须计算 SHA256 并写入本任务 `requirements.json`，用于证明没有偷偷重算或替换黄金证据。

---

# 3. 冻结物理电路，不允许重新选单元

本阶段固定：

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
fine high-cap control     = 0
fine low-cap control      = 1
fine K                    = 10

DFF                       = DFFRPQ_X0P5M_A9TR40
DFF minimum Q settle      = 200 ps
```

连接仍然必须是：

```text
                         +-----------------------> DFF.D
                         |
S_CLK -> sensor -> xor_29
                         |
                         v
                   N=16 medium stage
                         |
                         v
                 BUF_X0P8M_A9TL40
                         |
                         v
               NOR2_X4A load bank K=10
                         |
                         v
                       DFF.CK
                         |
                         v
                       DFF.Q
```

禁止：

```text
driver/load/MUX/DFF 重新搜索
改变 N 或 K
加入 bypass（旁路）
加入 configuration skip（配置跳过）
恢复旧 3-bit threshold tree
加入理想 delay
加入理想 capacitor
修改 sensor tap
修改 XOR/DFF
加入 programmable margin
加入 droop
加入 PVT
加入 RTL/FSM/真实控制器
```

如果动态协议失败，本任务只定位原因，不允许现场改硬件救援。

---

# 4. 动态控制码的物理定义必须与上一步完全一致

## 4.1 中调 thermometer code（温度计码）

M 从 0 增加到 16 时：

```text
M=0 : m[0..15] 全 0
M=1 : m0=1
M=2 : m0,m1=1
...
```

因此中调每次 `M -> M+1` 只允许一个控制节点从 0 跳到 VDD。

当检测到静态黄金边界后执行 `M_transition -> M_fine`，因为：

```text
M_fine = M_transition - 1
```

这里 `M_transition` 表示第一个静态 Q=0 的中调代码；`M_fine` 表示进入细调前回退一级的中调代码；`-1` 表示只撤销最后一个 thermometer bit（温度计码位）。

所以 backoff（回退）也只允许一个 medium control（中调控制）节点从 VDD 回到 0。

## 4.2 细调 thermometer code

F=0 时全部 NOR2 的 B 控制端为 VDD，对应低电容状态。

F 每增加一级，只允许一个新的 `f_i` 从 VDD 变为 0，使对应 NOR2 输入进入高电容状态。

因此整个动态黄金轨迹不存在多位同时变化的必要性。

Codex 必须生成单控制位切换的 PWL（分段线性）控制源，不得一次切换多个 M/F 控制位。

本阶段控制源仍属于 testbench，不代表下一阶段真实控制器的输出 slew（转换速度）。

---

# 5. 黄金动态轨迹：不得重新搜索完整范围

上一步已经给出静态边界，因此本阶段不能再动态扫满 `M=0..16` 和 `F=0..10`。

只运行达到已知边界所必需的连续轨迹。

## 5.1 0.95 V 首先执行

连续同一仿真中的 coarse（中调）probe（探测）顺序：

```text
(M,F) =
(0,0)
(1,0)
(2,0)
(3,0)
(4,0)
(5,0)
(6,0)
```

黄金 Q：

```text
1111110
```

到 `(6,0)` 后执行一次 backoff：

```text
(6,0) -> (5,0)
```

然后 fine（细调）probe：

```text
(5,0)
(5,1)
```

黄金 Q：

```text
10
```

最后保持 `(5,1)` 不再改码，再额外 probe 一次作为 LOCK_HOLD（锁定保持）检查，黄金 Q 必须仍为 0。

总 probe 数：10。

## 5.2 1.10 V

只有 0.95 V 完整 GO 后执行。

coarse：

```text
(0,0) -> (1,0) -> (2,0) -> (3,0) -> (4,0)
```

黄金 Q：

```text
11110
```

backoff：

```text
(4,0) -> (3,0)
```

fine：

```text
(3,0) -> (3,1) -> (3,2) -> (3,3) -> (3,4)
```

黄金 Q：

```text
11110
```

最后保持 `(3,4)` 再 probe 一次，Q 必须保持 0。

总 probe 数：11。

## 5.3 0.80 V

只有 0.95 V 和 1.10 V 均 GO 后执行。

coarse：

```text
(0,0) -> (1,0) -> ... -> (8,0) -> (9,0)
```

黄金 Q：

```text
1111111110
```

backoff：

```text
(9,0) -> (8,0)
```

fine：

```text
(8,0) -> (8,1)
```

黄金 Q：

```text
10
```

最后保持 `(8,1)` 再 probe 一次，Q 必须保持 0。

总 probe 数：13。

三个电压总共只有 34 次 probe，但必须封装为**最多 3 个连续动态 HSPICE 场景**：每个 VDD 一个场景，不是 34 个静态场景。

---

# 6. 动态 probe 时序合同：先用历史证据推导，0 HSPICE

本阶段不得直接沿用上一步“每个配置独立仿真”的时间轴，而要构造可连续重复的 probe slot（探测时隙）。

必须从上一步只读证据中推导并写入：

```text
delay_chain/ftc/analysis/dynamic_startup_calibration_protocol/timing_contract.json
```

当前证据已经给出：

```text
historical launch time     = 1.0 ns
historical Q read time     = 3.3 ns
Q read offset from launch  = 2.3 ns
DFF Q settle               = 0.2 ns
historical S_CLK high time = 3.0 ns
historical reset fully low -> launch separation = 0.49 ns
```

本阶段每个动态 probe 必须保持：

```text
Q read = 当前 probe 的 S_CLK 上升 launch 之后 2.3 ns
```

也就是说，不能把动态仿真的绝对 3.3 ns 当作所有 probe 的读取时刻，而是把上一步验证过的 `2.3 ns launch-to-read offset` 平移到每个 probe。

每个 probe 中，真实 DFF.CK 的有效上升边沿必须至少早于 Q read 200 ps。

## 6.1 代码稳定等待时间

从上一步 `q_read_contract.json` 读取最大的历史两级延时参考：

```text
D_delay_max = 1.269042997 ns
```

代码更新后，在解除 reset 前的 code-settle guard（代码稳定保护时间）不得小于“历史最大两级延时 + 200 ps”。按当前数据向上取整到 0.1 ns 后，预期固定为：

```text
code_settle_guard = 1.5 ns
```

其中 `code_settle_guard` 是一次 M/F 物理控制变化后保持 S_CLK 低、DFF reset 高的等待时间；`1.5 ns` 来自现有最坏延时证据加 200 ps 保护量，不是新仿真结果。

不得为了缩短仿真时间而扫描或缩小该 guard。

## 6.2 输入返回低电平后的 recovery guard

S_CLK 下降会再次在 sensor/XOR 中产生返回活动，所以不能在 S_CLK 刚下降后立即改 M/F。

必须用保留证据中的最大 sensor-to-XOR 延迟参考、最大两级延时参考和 200 ps 保护量推导 recovery guard（恢复保护时间）。按当前证据向上取整到 0.1 ns 后，预期至少为：

```text
recovery_guard = 2.3 ns
```

这里 `recovery_guard` 表示 S_CLK 返回低电平后，到允许修改 M/F 之前保持电路安静的时间。

如果 Codex 根据远程只读数据重算得到更大的值，只允许取更大的值；不得取比证据推导值更小的值。

## 6.3 每个 probe 的固定事件顺序

每个 probe 必须严格执行：

```text
A. S_CLK=0，DFF reset=1
B. 若需要，更新一个 M 或 F 控制位
C. 等待 code_settle_guard
D. DFF reset 用与历史相同量级的 10 ps PWL 边沿释放
E. reset 完全释放后等待 0.49 ns
F. S_CLK 用历史相同的 1 ps 边沿上升，开始本次 probe
G. launch + 2.3 ns：读取 Q
H. Q read 后再等待 0.2 ns，重新断言 DFF reset
I. launch + 3.0 ns：S_CLK 返回低电平
J. 等待 recovery_guard
K. 只有到此时才允许下一次 M/F 更新
```

在 D 到 H 的有效比较窗口中，M/F 必须完全静态。

本阶段 M/F testbench PWL 控制边沿统一固定为 10 ps，只作为协议验证的测试平台参数，不做 slew sweep（转换速度扫描）。真实控制器输出 slew 在 G/H 阶段验证。

---

# 7. 为什么 DFF reset 必须按 probe 周期参与协议

上一步静态仿真只观测 S_CLK 上升触发的第一组 XOR/DFF 比较，然后在 S_CLK 的后续下降事件之前读取 Q。

连续动态仿真中，S_CLK 下降同样会使 sensor/XOR 和延时线产生活动。为了避免返回事件污染下一次校准判定，本阶段协议必须：

```text
先读取本 probe 的 Q
      ↓
重新断言 DFF reset
      ↓
再让 S_CLK 返回低电平
      ↓
等待全部返回活动结束
      ↓
再修改 M/F
```

因此返回低电平造成的 CK 活动本阶段不是“配置毛刺”，但它必须发生在 reset 已经重新断言之后，并且必须在下一次代码更新之前完全结束。

若返回活动一直延伸到 code-update window（代码更新窗口），应分类为：

```text
recovery_window_insufficient
```

而不是直接归因于 configuration skip。

---

# 8. 新任务目录和文件

新增且只写入：

```text
delay_chain/ftc/scripts/run_dynamic_startup_calibration_protocol.py

delay_chain/ftc/analysis/dynamic_startup_calibration_protocol/
  requirements.json
  golden_reference.json
  timing_contract.json
  trajectory_contract.json
  integration_contract.json
  probe_results.csv
  transition_audit.csv
  dynamic_lock_table.json
  summary.json

delay_chain/ftc/runs/dynamic_startup_calibration_protocol/

delay_chain/ftc/reports/FTC_DYNAMIC_STARTUP_CALIBRATION_PROTOCOL.md

delay_chain/ftc/tests/test_dynamic_startup_calibration_protocol.py
```

不得覆盖任何旧 analysis/runs/reports。

新 runner 可以读取旧 runner 源码作为 SHA 证据，但不得 import 或 dispatch（调度）旧 runner。

允许继续复用无副作用的通用 HSPICE listing/MEAS parser（日志/测量解析器），例如已有 phase1 的公共 parser；不得通过公共 helper 间接执行旧 campaign。

---

# Phase 0 — 冻结黄金参考（0 HSPICE）

生成 `requirements.json` 和 `golden_reference.json`。

`golden_reference.json` 至少包含三个电压的：

```text
M_transition
M_fine
F_lock
coarse full static Q sequence
fine full static Q sequence
D_lock_ps
W_xor_ps
q_read_time_s
```

同时生成本阶段实际使用的黄金 prefix（前缀）：

```text
0.95 : coarse 1111110, fine 10, hold 0
1.10 : coarse 11110,   fine 11110, hold 0
0.80 : coarse 1111111110, fine 10, hold 0
```

必须验证这些 prefix 是直接从上一步 `coarse_scan.csv` / `fine_scan.csv` 截取，而不是手工重新推导。

如果手工常量与文件内容不一致，以只读文件为准并停止，不能自动修补黄金结果。

---

# Phase 1 — 动态 topology 与 trajectory 静态审计（0 HSPICE）

新 runner 先生成一个不执行的 0.95 V 动态 deck skeleton（网表骨架），静态检查：

```text
1. sensor/XOR/DFF 与上一步完全相同；
2. medium N=16、BUF、MUX 完全相同；
3. fine X0P8/NOR2_X4A/K10 完全相同；
4. xor_29 同时驱动 DFF.D 与 medium input；
5. dff_ck 只来自 fine driver 输出；
6. M 控制从 DC 源变为本任务 PWL 源，但拓扑不变；
7. F 控制从 DC 源变为本任务 PWL 源，但负载拓扑不变；
8. 任一 M 更新只切换一个 m_i；
9. 任一 F 更新只切换一个 f_i；
10. backoff 只撤销一个 m_i；
11. 有效比较窗口内没有任何 M/F 变化；
12. M/F 只在 S_CLK=0 且 DFF reset=1 时变化；
13. 代码更新前已经完成 recovery guard；
14. 代码更新后满足 code-settle guard；
15. reset 完全释放后到 launch 至少保持历史 0.49 ns；
16. 没有旧 3-bit threshold tree；
17. 没有 bypass；
18. 没有 configuration skip；
19. 没有理想 delay/capacitor；
20. 没有真实 FSM/计数器/寄存器。
```

生成：

```text
integration_contract.json
trajectory_contract.json
```

若任一检查失败：

```text
Dynamic Startup Calibration Protocol = ARCHITECTURE_BLOCKED
```

0 HSPICE 停止。

---

# Phase 2 — 动态测量合同（0 HSPICE）

每个 probe 必须输出至少：

```text
vdd_v
probe_index
protocol_phase
medium_code
fine_code
launch_time_s
q_read_time_s
t_xor_rise_s
t_xor_fall_s
t_ck_rise_s
q_read_v
q_logic
D_code_ps
W_xor_ps
xor_peak_v
ck_peak_v
valid
reason
```

其中：

```text
D_code_ps = t_ck_rise_s - t_xor_rise_s
```

`D_code_ps` 表示本 probe 中两级延时线送到真实 DFF.CK 的传播延时；`t_ck_rise_s` 是本 probe 的有效 CK 上升时刻；`t_xor_rise_s` 是同一 probe 的 xor_29 上升时刻；`-` 表示两时刻之差。

```text
W_xor_ps = t_xor_fall_s - t_xor_rise_s
```

`W_xor_ps` 表示本 probe 的真实 XOR 脉宽；`t_xor_fall_s` 是对应下降时刻；`t_xor_rise_s` 是对应上升时刻；`-` 表示脉宽时间差。

Q 数字化仍采用真实 DFF 输出，但除 `VDD/2` 判定外还必须检查 rail validity（电平有效性）：

```text
Q=1 时 q_read_v >= 0.9*VDD
Q=0 时 q_read_v <= 0.1*VDD
```

`q_read_v` 是本 probe 的 Q 读取电压；`VDD` 是当前供电；`0.9*VDD` 和 `0.1*VDD` 分别表示 90% 与 10% 电源轨；`>=` 和 `<=` 分别表示高电平至少到达 90% VDD、低电平至多为 10% VDD。

若 Q 落在 10%~90% VDD 中间区域，分类：

```text
q_ambiguous
```

---

# Phase 3 — 必须审计的三类动态窗口

## 3.1 有效 probe 窗口

从 S_CLK launch 到 reset 重新断言之间：

```text
xor_29 必须出现且只出现一个有效 >50% VDD 上升事件
DFF.CK 必须出现且只出现一个有效 >50% VDD 上升事件
xor_peak >= 0.9 VDD
ck_peak  >= 0.9 VDD
W_xor_ps > 0
D_code_ps > 0
CK 必须在 Q read 前至少 200 ps 到达
```

如果同一个有效比较窗口出现第二个 CK 上升跨越 50% VDD，分类：

```text
extra_ck_edge_during_probe
```

## 3.2 返回/恢复窗口

reset 已重新断言后，S_CLK 返回低电平。该阶段允许 sensor/XOR/CK 因输入下降产生功能性返回活动。

但是在进入下一次代码更新前必须证明：

```text
xor_29 已回到低电平
medium_out 已回到低电平
dff_ck 已回到低电平
```

且 recovery guard 末尾连续静默。

否则：

```text
recovery_window_insufficient
```

## 3.3 code-update quiet window

M/F 更新发生时 S_CLK 必须为 0、reset 必须为 1。

从控制位开始切换到下一次 reset release 之前，要求：

```text
xor_29 不得出现 >10% VDD 的异常活动
medium_out 不得出现 >10% VDD 的配置毛刺
dff_ck 不得出现 >10% VDD 的配置毛刺
```

特别是任何 dff_ck 上升跨越 50% VDD 都必须单独记录为：

```text
configuration_induced_ck_edge
```

backoff 和 fine load 控制切换必须分别标记，使最终报告能判断问题来自：

```text
coarse_increment
coarse_backoff
fine_increment
```

本阶段不允许看到毛刺后立刻加入 configuration skip；只记录证据并 NO-GO。

---

# Phase 4 — 0.95 V 单连续场景（最多 1 个新 HSPICE）

首先只运行：

```text
VDD = 0.95 V
```

一个连续 deck 必须完整包含 10 个 probe 和其中全部 M/F 更新。

必须验证：

```text
coarse dynamic Q = 1111110
backoff 后 (5,0) 的 fine 第一个 Q = 1
fine dynamic Q   = 10
LOCK_HOLD Q      = 0
最终 code         = (5,1)
```

另外必须验证：

```text
coarse 动态 D_code_ps 随 M 严格增加
fine 动态 D_code_ps 随 F 严格增加
所有有效 probe 均只有一个 CK 有效上升边沿
所有 code-update quiet window 无 dff_ck 配置毛刺
backoff 无配置诱导 CK 边沿
返回活动均在下一次代码更新前结束
```

如果 0.95 V 任一硬 Gate 失败：

```text
立即停止
1.10 V NOT_RUN
0.80 V NOT_RUN
```

不得为了“看看其他电压”继续运行。

---

# Phase 5 — 1.10 V 单连续场景（最多 1 个新 HSPICE）

只有 0.95 V GO 后执行。

必须验证：

```text
coarse dynamic Q = 11110
fine dynamic Q   = 11110
LOCK_HOLD Q      = 0
最终 code         = (3,4)
```

并执行与 0.95 V 完全相同的波形、单调性、CK 边沿、quiet-window、backoff、recovery 检查。

失败后立即停止，0.80 V NOT_RUN。

---

# Phase 6 — 0.80 V 单连续场景（最多 1 个新 HSPICE）

只有前两个电压均 GO 后执行。

必须验证：

```text
coarse dynamic Q = 1111111110
fine dynamic Q   = 10
LOCK_HOLD Q      = 0
最终 code         = (8,1)
```

0.80 V 是当前三个锚点中延时最慢、动态轨迹最长的场景，因此必须额外报告：

```text
最晚有效 CK 到达时间
最小 Q-settle margin
最长返回活动结束时间
最小 code-update quiet margin
```

如果全部满足合同，才能进入最终 GO 判定。

---

# 9. 动态结果与静态黄金证据的比较方式

动态 GO 的主判据是：

```text
真实 Q 序列
动态 D_code 单调性
无配置诱导 CK 毛刺
满足 reset/recovery/code-settle 时序
最终锁点一致
```

必须同时把每个动态 probe 与上一步相同 `(VDD,M,F)` 的静态记录配对，输出：

```text
static_D_code_ps
dynamic_D_code_ps
delta_D_ps
static_W_xor_ps
dynamic_W_xor_ps
delta_W_ps
static_Q
dynamic_Q
```

但是 `delta_D_ps` / `delta_W_ps` 在本阶段首先作为 diagnostic（诊断量），不能凭空设置一个未经证据支持的 1 ps、5 ps 或百分比硬阈值。

如果动态与静态 Q 完全一致、动态单调且协议波形干净，即可按本计划判定；若延时差异常大，报告必须指出，但不能自行创造容差标准。

---

# 10. 新 HSPICE 预算与复用合同

本阶段最多允许：

```text
3 个新 HSPICE 场景
```

分别为：

```text
dynamic_0p95
dynamic_1p10
dynamic_0p80
```

每个场景内部包含多个 probe，不得拆成大量静态场景。

严格早停顺序：

```text
0.95 V
  |
  +-- NO-GO -> STOP
  |
  +-- GO -> 1.10 V
                |
                +-- NO-GO -> STOP
                |
                +-- GO -> 0.80 V
                              |
                              +-- GO -> FINAL GO
```

新任务自己的场景也必须一场只执行一次。

scenario identity（场景身份）至少包含：

```text
study
vdd_v
trajectory_sha256
timing_contract_sha256
integration_contract_sha256
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
```

若任务中断，只允许复用：

```text
manifest = PASS
参数完全一致
deck SHA256 完全一致
HSPICE listing 完整
measurement 完整
```

不得因为 runner 注释、报告格式变化或 parser 修正而重跑已经完整 PASS 的动态电气场景。

部分/失败目录不得自动覆盖重跑，先报告 retained scenario invalid/failed，等待人工决定。

---

# 11. GO 判据

只有三个电压全部满足以下条件才允许：

```text
Dynamic Startup Calibration Protocol = GO
```

硬 Gate：

```text
1. 上一步静态 84 场景重跑数为 0；
2. 冻结的 sensor/XOR/medium/fine/DFF 物理拓扑未改变；
3. 0.95/1.10/0.80 V 的动态 coarse Q 与黄金 prefix 完全一致；
4. 三个电压的动态 fine Q 与黄金 prefix 完全一致；
5. 三个 LOCK_HOLD probe 均保持 Q=0；
6. 最终锁点分别为 (5,1)、(3,4)、(8,1)；
7. 每个 coarse 动态 D_code_ps 严格递增；
8. 每个 fine 动态 D_code_ps 严格递增；
9. 每个有效 probe 只有一个有效 DFF.CK 上升边沿；
10. 每个 CK 都满足 Q read 前至少 200 ps 的 settle 要求；
11. Q 每次读取都在有效 rail 区域，不出现 10%~90% VDD 模糊电平；
12. 每次 code update 前返回活动已经结束；
13. 每次 M/F 更新期间 dff_ck 无配置诱导有效边沿；
14. backoff 不产生配置诱导 CK 边沿；
15. fine load 切换不产生配置诱导 CK 边沿；
16. 每次更新后满足 code-settle guard；
17. 无 HSPICE fatal/incomplete/convergence failure；
18. 新 HSPICE 场景总数不超过 3；
19. 未加入 bypass/config skip/FSM/margin/droop/PVT。
```

---

# 12. NO-GO 根因分类

NO-GO 必须落入明确分类，至少包括：

```text
upstream_reference_mismatch
architecture_contract_violation
trajectory_contract_violation
probe_waveform_invalid
extra_ck_edge_during_probe
q_settle_window_insufficient
q_ambiguous
dynamic_coarse_q_mismatch
dynamic_fine_q_mismatch
dynamic_lock_hold_mismatch
dynamic_coarse_delay_non_monotonic
dynamic_fine_delay_non_monotonic
recovery_window_insufficient
configuration_induced_ck_edge
coarse_increment_glitch
coarse_backoff_glitch
fine_increment_glitch
final_lock_mismatch
hspice_execution_failure
```

NO-GO 后只写报告和证据，不进行硬件修复。

下一步分支由根因决定，例如：

```text
只有 recovery 不足
    -> 后续重新定义协议 guard，不先改延时线

代码更新导致 CK 毛刺
    -> 下一计划研究 control gating / update isolation / configuration handling

backoff 特有毛刺
    -> 下一计划专门研究 M 回退切换接口

fine increment 特有毛刺
    -> 下一计划研究 fine control 驱动/隔离

动态 Q 与静态 Q 不一致但无毛刺
    -> 下一计划研究重复周期 history/capture 行为
```

不得自动回到 driver/load 搜索。

---

# 13. 回归测试要求

新增：

```text
delay_chain/ftc/tests/test_dynamic_startup_calibration_protocol.py
```

测试必须完全静态，不允许启动 HSPICE。

至少覆盖：

```text
1. 上一步 decision 必须是 GO；
2. 上一步静态场景数必须是 84；
3. 上一步所有 historical rerun counter 必须为 0；
4. 三个黄金 lock 必须与远程 lock_table 一致；
5. 0.95 黄金 prefix 必须由 CSV 截取得到；
6. 1.10 黄金 prefix 必须由 CSV 截取得到；
7. 0.80 黄金 prefix 必须由 CSV 截取得到；
8. 动态 topology 保持 tap29/XOR/DFF；
9. medium N16/BUF/MUX 不变；
10. fine X0P8/NOR/K10 不变；
11. xor_29 同时驱动 DFF.D 与 medium input；
12. M increment 每次只切换一个控制位；
13. M backoff 只切换一个控制位；
14. F increment 每次只切换一个控制位；
15. M/F 不得在有效 probe 窗口变化；
16. code update 必须发生在 S_CLK=0、reset=1；
17. q_read offset 必须是 2.3 ns；
18. q_settle 必须是 200 ps；
19. code-settle guard 不得小于只读证据推导值；
20. recovery guard 不得小于只读证据推导值；
21. reset fully-low 到 launch 不得小于 0.49 ns；
22. 0.95 动态轨迹 probe 数严格为 10；
23. 1.10 动态轨迹 probe 数严格为 11；
24. 0.80 动态轨迹 probe 数严格为 13；
25. 三个 VDD 最多只有 3 个 HSPICE scenario identity；
26. 0.95 失败后调度器不能继续 1.10/0.80；
27. 1.10 失败后不能继续 0.80；
28. 新 runner 不得 import/调用上一步 runner；
29. 新 runner 不得写入上一步 analysis/runs/report；
30. 不得出现 bypass/config skip/FSM/margin/droop/PVT；
31. phase0-only 模式绝不能调用 subprocess HSPICE；
32. 最终 GO 必须要求三个动态场景全部 GO。
```

至少执行：

```text
python3 -m unittest delay_chain.ftc.tests.test_dynamic_startup_calibration_protocol
git diff --check
```

---

# 14. 输出结果格式

`probe_results.csv` 每行对应一个有效 probe。

`transition_audit.csv` 每行对应一次动态控制变化，至少记录：

```text
vdd_v
transition_index
transition_type
old_M
new_M
old_F
new_F
update_time_s
next_reset_release_s
next_launch_s
medium_out_quiet_peak_v
dff_ck_quiet_peak_v
xor_quiet_peak_v
configuration_ck_edge_count
status
reason
```

`dynamic_lock_table.json` 至少输出：

```text
VDD
expected_M_fine
expected_F_lock
dynamic_M_final
dynamic_F_final
coarse_q_dynamic
fine_q_dynamic
lock_hold_q
status
```

`summary.json` 至少输出：

```text
decision
reasons
new_dynamic_hspice_scenarios
reused_dynamic_scenarios
upstream_static_hspice_rerun
upstream_static_84_scenarios_rerun
per_voltage
minimum_q_settle_margin_ps
maximum_configuration_quiet_peak_ratio
maximum_recovery_end_time_s
```

---

# 15. 最终报告必须回答的问题

报告：

```text
delay_chain/ftc/reports/FTC_DYNAMIC_STARTUP_CALIBRATION_PROTOCOL.md
```

必须回答：

```text
1. 上一步 84 个静态场景是否全部只读、重跑数是否为 0？
2. 本阶段一共新跑了几个 HSPICE 连续动态场景？
3. 动态 topology 与上一步静态 topology 有哪些唯一允许的差异？
4. 为什么 M/F 从 DC 配置改成 PWL 后仍属于同一物理延时线？
5. 动态 probe slot 的 q-read offset、reset 时序、code-settle guard、recovery guard 分别如何从旧证据得到？
6. 为什么 S_CLK 下降后的返回 XOR/CK 活动必须与配置毛刺区分？
7. 0.95 V 的完整动态 M/F/Q 时间轨迹是什么？
8. 1.10 V 的完整动态 M/F/Q 时间轨迹是什么？
9. 0.80 V 的完整动态 M/F/Q 时间轨迹是什么？
10. 每次中调 increment 是否只改变一个 thermometer bit？
11. backoff 是否只撤销一个 bit，是否产生 CK 毛刺？
12. 每次 fine increment 是否只改变一个 load-control bit，是否产生 CK 毛刺？
13. 三个电压的动态 coarse/fine D_code 是否保持严格单调？
14. 每个有效 probe 是否都只有一个有效 CK 上升边沿？
15. 是否存在 q_ambiguous？
16. 最小 Q-settle margin 是多少？
17. code-update quiet window 中 dff_ck 的最大峰值是多少？
18. 最终动态锁点是否与静态黄金锁点完全一致？
19. 如果 GO，为什么仍不能称为真实启动校准电路 GO？
20. 为什么下一阶段必须先做真实控制电路实现，而不是直接 programmable margin？
```

---

# 16. Codex 严格执行顺序

```text
Step 1  拉取远程 main，确认 b1f511f 之后是否只有计划类提交；若已有新的电气实现，先重新审查再继续。
Step 2  读取上一步 summary/lock/coarse/fine/integration/q-read/requirements/report/runner；0 HSPICE。
Step 3  验证上一步 GO、84 场景和所有冻结单元；0 HSPICE。
Step 4  为上述只读证据生成 SHA256；0 HSPICE。
Step 5  生成本任务 requirements.json 和 golden_reference.json；0 HSPICE。
Step 6  从旧证据计算 q-read offset、code-settle guard、recovery guard；0 HSPICE。
Step 7  生成 timing_contract.json；0 HSPICE。
Step 8  生成三个黄金动态 trajectory；0 HSPICE，不重新搜索完整 M/F 空间。
Step 9  实现新的 dynamic runner，局部重建冻结 topology；不得 import 上一步 runner。
Step 10 把 M/F DC rail 改成单 bit PWL rail，只改变 testbench 控制方式。
Step 11 生成 0.95 V deck skeleton 并执行 integration/trajectory 静态审计；0 HSPICE。
Step 12 执行全部 unittest 与 git diff --check；0 HSPICE。
Step 13 只运行 0.95 V 一个连续动态 HSPICE 场景。
Step 14 解析 10 个 probe、全部 transition quiet window、recovery window 和 CK 边沿。
Step 15 若 0.95 V 任一硬 Gate 失败，写 summary/report 并停止。
Step 16 若 0.95 V GO，只运行 1.10 V 一个连续动态场景。
Step 17 若 1.10 V 失败，写 summary/report 并停止。
Step 18 若前两点 GO，只运行 0.80 V 一个连续动态场景。
Step 19 解析 0.80 V 最坏 Q-settle/recovery/quiet-window 指标。
Step 20 三个电压全部 GO 后生成 dynamic_lock_table.json。
Step 21 发布 Dynamic Startup Calibration Protocol = GO。
Step 22 本任务结束；不得继续实现 FSM、计数器、寄存器、margin、droop、PVT、RTL 或 layout。
```

---

# 17. 本阶段完成后的下一步唯一主线

如果本计划 GO，已经证明：

```text
静态真实 DFF 分层搜索可行
        +
连续动态 M/F 更新协议可行
        +
代码切换没有破坏真实 CK/Q 比较
```

然后进入 G：

```text
真实启动校准控制电路实现
```

G 阶段才把 testbench 当前完成的：

```text
reset sequencing
coarse increment
Q decision
coarse backoff
fine increment
lock hold
```

变成真实标准单元控制逻辑。

G 完成后还必须进入 H：完整真实电路级启动校准验证。只有 H 也 GO，才能进入 I：可编程检测裕量。

如果本计划 NO-GO，则根据本计划记录的具体动态波形根因另开修复计划，禁止绕过 F 直接进入真实 FSM 或可编程裕量。

---

# 18. 本计划唯一要回答的核心问题

> 已经在 84 个静态真实 DFF 场景中证明可行的“先中调、回退一级、再细调”搜索关系，在不重新运行那 84 个场景的前提下，能否在同一真实晶体管级电路中通过连续的 M/F 动态更新稳定复现，并且全过程不产生配置诱导的 DFF.CK 毛刺、错误 Q、时序污染或错误锁点？

只有这个问题得到 GO，本项目才具备进入“真实启动校准控制电路实现”的依据。