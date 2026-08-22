# FTC H0 校准到检测原子化控制权切换逐步骤推进计划

**仓库：** `Peiki0622/power_macro`  
**目标分支：** `main`  
**计划建立时远程基线：** `9eb61134e0cbfefd07ee52db0d73b11bee95eec5`  
**阶段定位：** P10 启动校准冻结之后、检测裕量表征之前。  
**阶段目标：** 在不修改冻结传感器、不修改启动校准算法、不修改 400 MHz 校准时序的前提下，新增一个可综合的控制权切换层，使 `FTC_SENSOR` 的 28 条控制信号能够从启动校准控制器安全、原子化地移交给未来检测控制器，并把启动校准结果作为后续检测阶段不可破坏的基准配置永久保存到下一次上电复位。

---

# 0. 本计划取代什么、又不做什么

## 0.1 不再推进 PD1 静态修订

本计划优先于 `plans/ftc_pd1_physical_power_domain_crossing_contract_plan.md` 中后续的 PD1-R0～PD1-R6 静态修订。

Codex **不要再执行**：

```text
PD1-R0
PD1-R1
PD1-R2
PD1-R3
PD1-R4
PD1-R5
PD1-R6
```

当前项目直接采用已经决定的工程假设：

> `PD_CTRL` 与 `PD_SENSE` 之间采用理想电源感知跨域接口抽象；真实跨压标准单元、电平转换、隔离、反向供电和物理电源意图实现不属于当前研究主线。

该假设只用于把研究重点放回传感器、校准和检测，不得被写成真实物理跨压接口已经签核。

## 0.2 H0 只解决“谁控制传感器”

H0 负责：

```text
启动校准阶段：CAL 拥有传感器
校准成功：锁存校准基准
安全静止：准备移交
检测侧预置完成：原子切换
切换以后：DET 拥有传感器
```

H0 **不负责**：

```text
检测阈值是多少
检测裕量是多少
F_det = F_cal + ?
M_det/F_det 如何编码
检测探测周期是多少
检测状态机如何工作
电压跌落最小幅度/持续时间
报警策略
重新校准策略
真实跨压接口实现
```

这些问题分别留给后续检测裕量、检测时序和检测控制器阶段。

---

# 1. 最高优先级原则

## 1.1 不重跑没有新信息量的上游仿真

本阶段新增的是 `PD_CTRL` 内部的控制权切换逻辑，不是传感器本体。

默认执行预算：

```text
重新跑 RF6 晶体管级三电压仿真      = 0
重新跑 RF8 原启动校准综合/STA       = 0
重新跑 RF9A/RF9B                    = 0
重新跑 RF9C 数模混合                = 0
重新跑 RF9D SDF+XA+晶体管           = 0
新的 HSPICE 传感器仿真               = 0
新的 XA 传感器仿真                   = 0
完整启动校准流程重放                 = 0
```

本阶段允许且有新信息量的工作：

```text
H0 新模块 RTL 单元仿真               = 允许
H0 新模块断言验证                     = 允许
H0 新模块一次必要的综合/STA           = 允许
H0 新模块映射后小型 SDF 单元验证      = 允许
静态复用 RF8/RF9D 既有时序证据       = 允许
```

**不得因为 H0 新增逻辑而把整个 RF6/RF9D 流程从头重跑。**

## 1.2 冻结上游 RTL 不得修改

以下文件是 P10 已冻结的启动校准实现，H0 默认必须保持 Git blob 不变：

```text
delay_chain/ftc/controller/rtl/ftc_cal_controller_top.sv
  blob = eab29ecae9a4ad93b7586f1c293c2ddd0dd5497c

delay_chain/ftc/controller/rtl/ftc_cal_fsm.sv
  blob = ae8cf850cfe35d5ae78518b2772a138d316c3b5a

delay_chain/ftc/controller/rtl/ftc_cal_pkg.sv
  blob = 504429b12a423ce57058e5ac301af40cd5f29db6

delay_chain/ftc/controller/rtl/ftc_cfg_therm_regs.sv
  blob = 02e1b7f44a6e67b4538d42d58b0b989a93d2fae2

delay_chain/ftc/controller/rtl/ftc_operation_sequencer.sv
  blob = b389c1f4ec8d86b1c3f27e8446b9e403333093bb

delay_chain/ftc/controller/rtl/ftc_q_sampler.sv
  blob = 3b5633020dd21ea0df4f21bbcc37dd3e07f00e81
```

不要为了修改过时注释而触碰这些文件。

如果发现上述文件与 P10 清单不一致，先停止 H0 并报告上游漂移，不得自行“顺便修复”。

## 1.3 冻结传感器和校准语义

以下继续不可修改：

- `FTC_SENSOR` 拓扑；
- 中调 16 级；
- 细调 10 级；
- 抽头 29；
- XOR 留在 `PD_SENSE`；
- capture DFF 留在 `PD_SENSE`；
- `Q_FINAL` 是锁存状态返回；
- 两次独立粗调探测；
- 首个双低粗调边界；
- 恰好回退两个中调配置步；
- 细调扫描规则；
- 保护档加一；
- 独立保持确认；
- Q 双采样；
- 400 MHz 校准时钟；
- 2.5 ns 周期；
- 1 周期配置稳定；
- 0/1/2/3/4/5/7 局部探测动作周期。

## 1.4 H0 不允许通过降低校准频率解决问题

如果 H0 新增的所有权选择逻辑无法满足当前 400 MHz 时序或物理事件顺序：

```text
禁止：400 MHz -> 更低频率
禁止：增加配置稳定周期
禁止：移动 XOR / capture DFF
禁止：修改探测动作周期
```

正确动作是：

1. 优化 H0 自身的选择结构；
2. 尽量减少 `sense_s_clk` 控制路径附加延迟；
3. 若仍无法满足，则 H0 报告不通过并停止。

---

# 2. 当前事实基础

Codex 执行 H0 前必须只读确认以下事实。

## 2.1 当前启动校准成功后已经天然进入安全静止状态

当前 `ftc_operation_sequencer.sv` 在空闲状态固定：

```text
sense_dff_reset = 1
sense_s_clk      = 0
```

探测结束前也已经先完成：

```text
RESET_ASSERT
S_CLK_FALL
RECOVERY_DONE
```

当前 `ftc_cal_fsm.sv` 在最终 HOLD probe 成功后进入 `ST_LOCKED`：

```text
cal_busy   = 0
cal_done   = 1
lock_valid = 1
seq_req    = 0
```

并且保持到下一次 POR。

因此 H0 **不需要修改 sequencer 来新增 probe_idle**。

H0 可以把以下同时成立作为“校准已经成功且传感器安全静止”的条件：

```text
cal_done == 1
lock_valid == 1
cal_fail == 0
cal_busy == 0
cal_sense_dff_reset == 1
cal_sense_s_clk == 0
```

## 2.2 当前配置寄存器已经永久锁定校准结果

`ftc_cfg_therm_regs.sv` 在 `lock_i` 被捕获后忽略所有配置步进请求直到 POR。

因此 H0 不需要修改原配置寄存器。

H0 要做的是额外锁存一份用于后续检测阶段的不可破坏基准：

```text
M_cal
F_cal
medium_therm_cal_snapshot[15:0]
fine_therm_cal_snapshot[9:0]
```

这份基准以后不得被检测阶段修改。

---

# 3. H0 冻结后的总体架构

本阶段新增逻辑全部位于 `PD_CTRL`。

```text
                           PD_CTRL

               冻结启动校准控制器
             ftc_cal_controller_top
                        │
       ┌────────────────┼─────────────────┐
       │                │                 │
  cal_medium       cal_fine       cal_reset/cal_sclk
       │                │                 │
       └────────────────┼─────────────────┘
                        │
                        ▼
              控制权原子切换模块
            ftc_sensor_owner_handoff
                        ▲
                        │
          未来检测控制器预留接口
       det_medium / det_fine / reset / sclk
                        │
                        ▼
                  实际传感器控制
                        │
             理想电源感知跨域接口
                        │
                        ▼
                         PD_SENSE
                    完整 FTC_SENSOR
                        │
                     Q_FINAL
                        │
                        ▼
                         PD_CTRL
```

注意：

> `Q_FINAL` 不经过 H0 所有权多路选择。

它仍是 `PD_SENSE -> PD_CTRL` 的共享锁存状态返回。启动校准在 `ST_LOCKED` 后不会再发采样请求；未来检测控制器将在后续阶段直接消费同一个 `Q_FINAL`。

---

# 4. H0 新增 RTL 文件

建议新增：

```text
delay_chain/ftc/controller/rtl/
  ftc_sensor_owner_handoff.sv
  ftc_cal_detect_handoff_top.sv
```

**只新增，不修改六个冻结校准 RTL。**

## 4.1 `ftc_sensor_owner_handoff.sv`

职责：

- 观察启动校准成功/失败状态；
- 在安全静止点锁存校准基准；
- 向未来检测侧发布“准备接管”请求和基准配置；
- 检查检测侧在接管前是否真的处于完全一致的安全状态；
- 经过安全保持状态后一次性切换所有权；
- 切换后永久保持检测侧所有权直到 POR；
- 对失败或非法接管请求采取安全阻塞。

建议接口至少包含：

```text
时钟/复位
  cal_clk_i
  ctrl_por_n_i

校准状态
  cal_busy_i
  cal_done_i
  cal_fail_i
  lock_valid_i

校准侧传感器控制
  cal_sense_dff_reset_i
  cal_sense_s_clk_i
  cal_medium_therm_i[15:0]
  cal_fine_therm_i[9:0]
  cal_medium_code_i[4:0]
  cal_fine_code_i[3:0]

未来检测侧控制
  det_takeover_ready_i
  det_sense_dff_reset_i
  det_sense_s_clk_i
  det_medium_therm_i[15:0]
  det_fine_therm_i[9:0]

实际传感器控制
  sense_dff_reset_o
  sense_s_clk_o
  medium_therm_o[15:0]
  fine_therm_o[9:0]

校准基准快照
  cal_cfg_valid_o
  cal_medium_code_snapshot_o[4:0]
  cal_fine_code_snapshot_o[3:0]
  cal_medium_therm_snapshot_o[15:0]
  cal_fine_therm_snapshot_o[9:0]

移交握手/状态
  det_prepare_o
  det_owner_valid_o
  handoff_blocked_o
  handoff_protocol_error_o
  handoff_state_o
```

如果实际实现需要略微调整命名可以，但语义不得改变。

## 4.2 `ftc_cal_detect_handoff_top.sv`

这是 H0 新的集成顶层。

它必须：

1. 原样实例化冻结的 `ftc_cal_controller_top`；
2. 把冻结校准顶层原来的 28 条 sensor control 输出先接到 `cal_*` 内部信号；
3. 再送入 `ftc_sensor_owner_handoff`；
4. 对外真正暴露给 `FTC_SENSOR` 的控制信号来自 handoff 模块；
5. 原有 `q_final` 仍直接送到冻结校准控制器；
6. 对外保留原有校准状态和 debug 输出；
7. 新增未来检测侧预留控制端口、校准快照和 ownership 状态端口。

不要把检测状态机塞进这个顶层。

---

# 5. H0 所有权状态机

建议使用以下五个状态，保持逻辑最小化：

```text
H_CAL_OWNED
H_WAIT_DET
H_SWITCH_SAFE
H_DET_OWNED
H_BLOCKED
```

## 5.1 `H_CAL_OWNED`

上电默认状态。

```text
实际 sensor control = 校准侧输出
DET 输入无论如何变化都不能影响 sensor
```

若：

```text
cal_fail == 1
```

进入：

```text
H_BLOCKED
```

若同时满足：

```text
cal_done == 1
lock_valid == 1
cal_fail == 0
cal_busy == 0
cal_sense_dff_reset == 1
cal_sense_s_clk == 0
```

则在该 `cal_clk` 上升沿：

1. 锁存 `medium_code` 为 `M_cal`；
2. 锁存 `fine_code` 为 `F_cal`；
3. 锁存两组温度计配置向量；
4. 置 `cal_cfg_valid=1`；
5. 进入 `H_WAIT_DET`。

这一步之后快照直到 POR 不再改变。

## 5.2 `H_WAIT_DET`

校准侧仍然保持所有权。

H0 向未来检测侧给出：

```text
det_prepare_o = 1
cal_cfg_valid_o = 1
```

未来检测侧必须先把自己的预留输出设置成：

```text
det_medium_therm = cal_medium_therm_snapshot
det_fine_therm   = cal_fine_therm_snapshot
det_reset        = 1
det_s_clk        = 0
```

然后才能拉高：

```text
det_takeover_ready = 1
```

H0 **必须自己重新检查**这些值，不得只相信 ready。

允许切换的完整条件：

```text
det_takeover_ready == 1
AND det_medium_therm == cal_medium_therm_snapshot
AND det_fine_therm == cal_fine_therm_snapshot
AND det_sense_dff_reset == 1
AND det_sense_s_clk == 0
```

若 `det_takeover_ready=1` 但任何一项不匹配：

```text
handoff_protocol_error = 1（保持到 POR）
进入 H_BLOCKED
不得转交所有权
```

## 5.3 `H_SWITCH_SAFE`

这是一个完整的安全保持周期。

该周期实际传感器控制必须固定为：

```text
medium_therm = cal_medium_therm_snapshot
fine_therm   = cal_fine_therm_snapshot
reset        = 1
s_clk        = 0
```

这一周期的目的不是等待模拟传感器重新稳定，而是给所有权选择提供明确的“断点”：

```text
CAL 已经停止产生有效探测动作
DET 已经预置完成
传感器保持 reset=1 / s_clk=0
配置完全不变
```

在该周期结束后进入：

```text
H_DET_OWNED
```

## 5.4 `H_DET_OWNED`

```text
实际 sensor control = 检测侧输出
```

并且：

```text
det_owner_valid = 1
```

启动校准侧之后即使内部信号变化，也不得再影响实际 sensor control。

H0 第一版禁止自动 `DET -> CAL` 返回。

只有：

```text
ctrl_por_n == 0
```

才能重新回到：

```text
H_CAL_OWNED
```

## 5.5 `H_BLOCKED`

进入原因：

```text
校准失败
或
检测侧在 ready=1 时违反安全预置契约
```

该状态下：

```text
det_owner_valid = 0
handoff_blocked = 1
sense_s_clk = 0
sense_dff_reset = 1
```

配置向量保持最后一个校准侧稳定值；禁止产生新的中调/细调切换。

只有 POR 可以离开。

---

# 6. 原子切换的硬性性质

Codex 必须把以下性质写成断言或等价机器检查。

## 6.1 所有权单调性

```text
POR 后初始 owner = CAL
CAL 可以转换到 DET
DET 不能转换回 CAL，除非 POR
```

## 6.2 锁定前检测侧完全无效

在：

```text
det_owner_valid == 0
且 state != H_SWITCH_SAFE/H_BLOCKED
```

检测侧所有输入即使随机跳变，实际 sensor control 也必须保持由校准侧决定。

## 6.3 切换后校准侧完全无效

在：

```text
det_owner_valid == 1
```

校准侧控制输入变化不得改变实际 sensor control。

## 6.4 校准快照永久保持

一旦：

```text
cal_cfg_valid == 1
```

直到 POR：

```text
M_cal                 stable
F_cal                 stable
medium snapshot       stable
fine snapshot         stable
```

## 6.5 失败校准永远不能进入检测所有权

必须证明：

```text
cal_fail -> !det_owner_valid
```

并且失败后没有任何路径可以不经 POR 进入 DET。

## 6.6 接管 ready 不能绕过配置一致性检查

必须证明：

```text
det_ready && mismatch -> BLOCKED
```

而不是：

```text
det_ready -> DET
```

## 6.7 切换窗口实际输出无功能跳变

在：

```text
H_WAIT_DET -> H_SWITCH_SAFE
H_SWITCH_SAFE -> H_DET_OWNED
```

必须证明：

```text
medium_therm 不变
fine_therm   不变
sense_dff_reset 始终为 1
sense_s_clk      始终为 0
```

特别禁止在 ownership 切换瞬间制造新的 `sense_s_clk` 脉冲。

---

# 7. 检测侧预留接口的边界

H0 只定义一次性接管握手，不冻结未来检测时钟频率。

## 7.1 `det_takeover_ready_i`

H0 把它定义为已经同步到 `cal_clk` 域的接管确认信号。

如果未来检测控制器工作在不同的时钟域，则由后续集成层负责产生同步后的 `det_takeover_ready_i`。

H0 不提前决定检测控制器最终时钟频率。

## 7.2 检测侧 sensor control

在接管以前，检测侧必须把：

```text
det_medium_therm
det_fine_therm
det_reset
det_s_clk
```

保持在安全预置值，并从 `det_takeover_ready` 拉高前一直稳定到 `det_owner_valid` 拉高。

在 `det_owner_valid=1` 以后，这些信号的动态时序由后续检测时序契约负责，H0 不定义检测 probe cadence。

---

# 8. 校准基准和检测配置必须从此分离

H0 输出的：

```text
M_cal
F_cal
medium_therm_cal_snapshot
fine_therm_cal_snapshot
```

具有“基准只读”语义。

未来必须采用：

```text
校准基准：M_cal / F_cal

检测配置：M_det / F_det
```

而不是继续共用同一组可修改寄存器。

H0 当前阶段只要求检测侧初始接管值：

```text
M_det_initial = M_cal
F_det_initial = F_cal
```

不要在 H0 中实现：

```text
F_det = F_cal + ΔF
M_det = M_cal + ΔM
```

因为检测裕量尚未表征。

---

# 9. H0 专属证据目录

Codex 创建：

```text
delay_chain/ftc/controller/h0_calibration_detection_handoff/
├── baseline/
│   ├── h0_baseline_manifest.json
│   └── frozen_input_sha256.json
├── contract/
│   ├── handoff_interface_contract.json
│   ├── ownership_state_contract.json
│   └── downstream_detection_handoff.json
├── verification/
│   ├── rtl/
│   │   ├── tb_ftc_sensor_owner_handoff.sv
│   │   ├── ftc_sensor_owner_handoff_sva.sv
│   │   └── H0_RTL_UNIT_RESULTS.json
│   └── gate_sdf/
│       ├── tb_ftc_sensor_owner_handoff_gate.sv
│       └── H0_GATE_SDF_RESULTS.json
├── synthesis/
│   ├── scripts/
│   ├── constraints/
│   ├── netlist/
│   └── reports/
├── timing/
│   ├── existing_timing_inputs.json
│   ├── handoff_incremental_delays.json
│   └── handoff_timing_composition.json
└── reports/
    ├── H0_GATE_STATUS.json
    ├── H0_FROZEN_HANDOFF_INTERFACE.json
    └── H0_FINAL_REPORT.md
```

上游 RF6/RF8/RF9 目录只读，不得覆盖。

---

# 10. H0-0 —— 基线回读和冻结哈希

## 执行步骤

1. 确认远程 `main` 当前提交。
2. 读取 P10：

```text
delay_chain/ftc/controller/final_closure/freeze/
  POWER_DOMAIN_CONTRACT.json
  STARTUP_CALIBRATION_FROZEN_FILES.json
  STARTUP_CALIBRATION_EVIDENCE_BOUNDARY.md
  FTC_AUTONOMOUS_STARTUP_CALIBRATION_FINAL_ACCEPTANCE.md
```

3. 读取六个冻结校准 RTL。
4. 核对 Git blob 与 P10 清单。
5. 读取当前有效 400 MHz：

```text
refrequency/handoff/phase1_timing_handoff_refrequency.json
refrequency/timing_contract/cycle_timing_contract_refrequency.json
refrequency/synthesis/phase_refrequency_synthesis_results.json
```

6. 读取当前 RF8 四类关键路径报告：

```text
sense_s_clk_path.rpt
sense_dff_reset_path.rpt
thermometer_paths.rpt
q_final_sampling_path.rpt
```

7. 记录全部哈希。

## 停止条件

任何冻结 RTL 或有效 400 MHz handoff 出现未经授权漂移，H0 立即停止。

## 新 EDA 预算

```text
0
```

---

# 11. H0-1 —— 写正式所有权接口契约

生成：

```text
contract/handoff_interface_contract.json
contract/ownership_state_contract.json
contract/downstream_detection_handoff.json
```

必须把第 4～8 节全部机器可读化。

特别记录：

```text
Q_FINAL 不经过 ownership mux
真实跨压接口不属于 H0
DET 时钟频率未冻结
DET 接管前配置必须等于校准快照
DET 接管前 reset=1 / s_clk=0
只有 POR 能让 DET ownership 返回 CAL
```

此阶段不写 RTL。

---

# 12. H0-2 —— 实现 `ftc_sensor_owner_handoff.sv`

只新增该文件，不改冻结校准 RTL。

## 实现要求

1. 所有 ownership 状态由 `cal_clk_i` 驱动；
2. `ctrl_por_n_i` 为唯一回到 CAL 的复位；
3. 快照寄存器在一次成功校准后只写一次；
4. `det_takeover_ready_i` 不能直接成为 mux select；
5. mux select 必须来自内部注册状态；
6. 必须有完整 `H_SWITCH_SAFE` 周期；
7. `H_BLOCKED` 强制：

```text
s_clk = 0
reset = 1
```

8. 配置在 blocked 时保持最后校准稳定值；
9. 不允许组合反馈；
10. 不允许门控 `cal_clk`；
11. 不得实现检测 margin 运算；
12. 不得修改 Q_FINAL。

---

# 13. H0-3 —— 实现新的集成顶层

新增：

```text
rtl/ftc_cal_detect_handoff_top.sv
```

## 要求

- 原样实例化 `ftc_cal_controller_top`；
- 不复制校准算法；
- 校准模块输出改名接入局部 `cal_*` 线；
- handoff 输出成为新顶层实际 `sense_*`/therm 输出；
- 保留原 calibration status/debug；
- 暴露 H0 快照和 ownership 状态；
- 暴露未来 detection 预留输入；
- `q_final` 继续直接进入冻结校准控制器。

Codex 必须做一次只读 diff，证明六个冻结校准 RTL 没有变化。

---

# 14. H0-4 —— RTL 单元验证，不运行完整校准

这一阶段只验证 handoff 模块本身。

## 14.1 三个冻结黄金校准结果回放

直接驱动 handoff 的校准侧输入，不启动真实校准状态机：

```text
0.80 V -> M7 / F6
0.95 V -> M4 / F6
1.10 V -> M2 / F9
```

温度计向量必须按照当前 `ftc_cfg_therm_regs.sv` 的真实编码生成，不能只比较 binary code。

每个黄金点执行：

```text
CAL owns
-> 驱动安全成功锁定状态
-> snapshot
-> WAIT_DET
-> DET 输入装载完全相同 therm + reset=1 + s_clk=0
-> det_ready
-> SWITCH_SAFE
-> DET owns
```

检查切换前后 28 条 sensor control 无功能变化。

## 14.2 必须覆盖的负向场景

至少覆盖：

1. `det_ready` 在 `lock_valid` 前乱跳；
2. DET 控制信号在 CAL ownership 期间随机跳变；
3. `lock_valid=1` 但 `cal_busy=1`；
4. `lock_valid=1` 但 `cal_reset=0`；
5. `lock_valid=1` 但 `cal_s_clk=1`；
6. `cal_fail=1`；
7. DET `medium` 与快照不一致却 ready；
8. DET `fine` 与快照不一致却 ready；
9. DET `reset=0` 却 ready；
10. DET `s_clk=1` 却 ready；
11. DET ownership 后 CAL 输入随机变化；
12. DET ownership 后尝试重新回 CAL；
13. POR 后重新回到 CAL 初始状态。

## 14.3 断言

实现第 6 节全部性质。

尤其必须有跨切换沿的：

```text
$sense_s_clk 不产生 0->1->0 或 1->0->1 异常脉冲
reset 不在切换窗口出现非预期释放
medium/fine 在切换窗口保持 stable
```

## 新仿真预算

```text
纯 RTL 单元验证 = 1 套
```

不得实例化 XA/晶体管传感器。

---

# 15. H0-5 —— 新逻辑综合和最小静态时序检查

H0 新增了真实 `PD_CTRL` 逻辑，因此允许对 **H0 新模块**进行一次必要综合/STA。

优先策略：

> 先独立综合 `ftc_sensor_owner_handoff`，复用现有 SMIC40LL 控制器标准单元库和当前 400 MHz 条件，提取 H0 自身状态逻辑以及 CAL->sensor ownership 选择路径的增量延迟。

不要第一步就重新综合整个启动校准控制器。

## 15.1 工艺和条件

复用 RF8 当前控制器库环境：

```text
sc9mc_logic0040ll_base_rvt_c40_ss_typical_max_0p99v_125c
```

时钟：

```text
400 MHz
2.5 ns
```

不做频率 sweep。

## 15.2 必须报告的新路径

至少报告：

```text
cal_sense_s_clk_i -> sense_s_clk_o
cal_sense_dff_reset_i -> sense_dff_reset_o
cal_medium_therm_i[*] -> medium_therm_o[*]
cal_fine_therm_i[*] -> fine_therm_o[*]

snapshot/status -> handoff state registers
det_takeover_ready -> ownership state register
```

对 mux 数据路径分别记录：

```text
rise delay
fall delay
最大位延迟
最小位延迟
medium/fine 位间最大差
```

## 15.3 H0 内部时序

所有 H0 状态寄存器必须：

```text
setup slack > 0
hold slack  > 0
```

在 2.5 ns 下闭合。

---

# 16. H0-6 —— 与当前 400 MHz 物理事件顺序做静态组合

这是 H0 最关键的时序门之一。

不得只看普通数字 STA slack；`sense_s_clk` 是传感器物理探测的起点，新 ownership 选择延迟会缩短从传感器真正看到 S_CLK 到控制器 Q_SAMPLE_1 的时间。

## 16.1 当前有效 400 MHz 名义事件间隔

从现有 `cycle_timing_contract_refrequency.json` 读取：

```text
RESET_RELEASE_COMPLETE -> S_CLK_RISE     约 2.49 ns
S_CLK_RISE -> Q_SAMPLE_1                 2.50 ns
Q_SAMPLE_1 -> Q_SAMPLE_2                 2.50 ns
Q_SAMPLE_2 -> RESET_ASSERT_START         2.50 ns
RESET_ASSERT_COMPLETE -> S_CLK_FALL      约 2.49 ns
S_CLK_FALL -> RECOVERY_DONE              5.00 ns
```

## 16.2 历史精确物理路径给出的最低事件间隔

这些只作为物理 minimum requirement：

```text
RESET_RELEASE_COMPLETE -> S_CLK_RISE     约 0.49 ns
S_CLK_RISE -> Q_SAMPLE_1                 约 2.30 ns
Q_SAMPLE_1 -> Q_SAMPLE_2                 约 0.20 ns
Q_SAMPLE_2 -> RESET_ASSERT_START         约 0.20 ns
RESET_ASSERT_COMPLETE -> S_CLK_FALL      约 0.29 ns
S_CLK_FALL -> RECOVERY_DONE              约 2.70 ns
```

因此 H0 之前 schedule 相对 minimum requirement 的主要静态余量：

```text
reset release -> sclk rise     约 2.00 ns
sclk rise -> q sample 1        约 0.20 ns   <- 最紧
q sample 1 -> q sample 2       约 2.30 ns
q sample 2 -> reset            约 2.30 ns
reset complete -> sclk fall    约 2.20 ns
sclk fall -> recovery          约 2.30 ns
```

## 16.3 新 ownership 逻辑的 S_CLK 门

设 H0 综合得到：

```text
d_h0_sclk_rise_max
```

由于 Q_SAMPLE_1 在校准控制器内的时刻不变，H0 后：

```text
S_CLK_RISE -> Q_SAMPLE_1 剩余裕量
≈ 0.20 ns - d_h0_sclk_rise_max
```

H0 必须要求：

```text
剩余裕量 > 0
```

如果不满足：

- 先优化 handoff 的 S_CLK 选择路径；
- 可以在同一普通控制器标准单元库中使用更直接的选择结构；
- 不得搜索跨压单元；
- 不得降低 400 MHz；
- 不得移动传感器结构。

## 16.4 reset 与 S_CLK 的相对偏差

分别使用 handoff 的 rise/fall delay 重新计算：

```text
RESET_RELEASE_COMPLETE < S_CLK_RISE
RESET_ASSERT_COMPLETE < S_CLK_FALL
```

必须保留正裕量。

重点检查最坏相对项：

```text
reset 路径比 sclk 路径更慢的差值
```

不得只比较两个绝对 delay。

## 16.5 配置稳定时间

H0 配置 mux 的位间差与 S_CLK mux delay 必须保持：

```text
配置到达并稳定
< 下一次实际 S_CLK 上升到达
```

原有 1 个校准周期配置稳定规则不变。

## 16.6 现有 RF8 数字裕量作为第二重检查

复用：

```text
sense_s_clk      +1.76 ns
sense_dff_reset  +1.77 ns
thermometer      +1.86 ns
q_final sampling +1.50 ns
```

其中 `q_final` 返回路径未经过 H0，因此不允许把 H0 当成理由重跑该路径。

将 H0 增量延迟与已有输出路径正裕量静态组合，必须仍然为正。

---

# 17. H0-7 —— 映射后小型 SDF 单元验证

这一步只验证新 handoff 逻辑，不运行完整 startup calibration，也不实例化晶体管传感器。

## 目的

验证综合映射以后 ownership 切换没有：

```text
S_CLK 毛刺
reset 瞬时错误释放
medium/fine 切换毛刺
```

## 场景

至少使用三个黄金校准快照中的：

```text
M7/F6
M4/F6
M2/F9
```

逐个执行安全切换。

必须监控切换附近高分辨率事件，确认：

```text
H_WAIT_DET -> H_SWITCH_SAFE
H_SWITCH_SAFE -> H_DET_OWNED
```

期间：

```text
sense_s_clk 恒 0
sense_dff_reset 恒 1
medium/fine 无位翻转
```

## 仿真预算

```text
H0 新模块 mapped + SDF 小型数字验证 = 1 套
```

不要跑 XA，不要跑 RF9D。

---

# 18. H0-8 —— 是否需要完整集成综合的条件门

默认：

```text
重新综合整个 ftc_cal_detect_handoff_top = 0
```

如果以下全部成立：

1. H0 独立综合内部 setup/hold 通过；
2. CAL->sensor mux 增量延迟已获得；
3. 第 16 节静态时序组合全部有正裕量；
4. H0 mapped+SDF 单元切换无毛刺；

则：

> **不要再重新综合整个启动校准控制器。**

只有当独立综合无法可靠回答“新 mux 接到冻结控制器输出后的真实负载/边沿是否仍闭合”时，才允许执行一次：

```text
ftc_cal_detect_handoff_top
完整数字综合 + STA
```

该执行属于 H0 新集成实现，不叫 RF8 重跑。

若触发，必须：

- 使用同一 400 MHz；
- 使用同一控制器工艺角；
- 不做频率 sweep；
- 不改六个冻结校准 RTL；
- 只做一次目标综合和必要时序报告；
- 不自动继续做数字 SDF 全启动校准；
- 不自动继续做 XA。

---

# 19. H0 不允许出现的“顺手扩展”

Codex 不得在本阶段顺手实现：

```text
margin_code
M_det/F_det 算法
检测 probe 状态机
检测报警
心跳/timeout
动态重新校准
DET -> CAL 切换
跨压 level shifter
UPF/CPF
传感器 PVT sweep
电压跌落幅度×持续时间 sweep
```

发现这些需求时只登记到下游 handoff，不进入 H0 RTL。

---

# 20. H0 最终通过条件

只有以下全部满足才能给出 GO。

## 20.1 上游冻结

```text
六个冻结校准 RTL blob 全部匹配
FTC_SENSOR 未修改
400 MHz timing handoff 未修改
启动校准算法未修改
```

## 20.2 功能

```text
POR 后 CAL 独占传感器
锁定前 DET 无法影响传感器
成功校准后只锁存一次 M_cal/F_cal 和 therm 快照
切换只发生在 cal_done && lock_valid && !cal_fail && !cal_busy
切换只发生在 reset=1 / s_clk=0
DET ready 前必须预置成和校准快照完全一致
错误 ready 被阻塞
H_SWITCH_SAFE 保持一个完整周期
切换期间 28 条控制输出无功能变化
DET 接管后 CAL 无法影响传感器
cal_fail 永远不能进入 DET
只有 POR 能恢复 CAL ownership
```

## 20.3 时序

```text
H0 内部 setup > 0
H0 内部 hold  > 0
S_CLK ownership 增量延迟后 S_CLK->Q_SAMPLE_1 物理余量 > 0
reset/S_CLK 两组相对事件顺序仍有正余量
配置稳定时间仍为正
已有 RF8 数字输出裕量扣除 H0 增量后仍为正
```

## 20.4 映射后切换安全

```text
mapped+SDF H0 单元切换无 S_CLK 毛刺
reset 无错误释放
medium/fine 无切换毛刺
```

## 20.5 仿真纪律

```text
RF6 rerun  = 0
RF9C rerun = 0
RF9D rerun = 0
HSPICE 新传感器仿真 = 0
XA 新传感器仿真 = 0
```

---

# 21. 最终报告和冻结 handoff

生成：

```text
reports/H0_GATE_STATUS.json
reports/H0_FROZEN_HANDOFF_INTERFACE.json
reports/H0_FINAL_REPORT.md
```

允许的最终状态只有：

```text
H0 校准到检测原子化控制权切换 = 通过
H0 校准到检测原子化控制权切换 = 不通过
H0 校准到检测原子化控制权切换 = 证据缺口停止
```

不得使用“基本通过”。

`H0_FROZEN_HANDOFF_INTERFACE.json` 必须冻结供后续阶段消费的：

```text
M_cal/F_cal snapshot 语义
therm snapshot 语义
cal_cfg_valid
 det_prepare
 det_takeover_ready
 det_owner_valid
实际 sensor control ownership
POR-only ownership reset
```

并记录新 H0 RTL 的 Git blob / SHA256。

---

# 22. H0 通过后立即交给下一阶段什么

H0 通过后，不继续扩展控制权逻辑。

下一阶段是：

> **检测裕量表征。**

它直接消费：

```text
M_cal
F_cal
medium_therm_cal_snapshot
fine_therm_cal_snapshot
cal_cfg_valid
det_owner_valid
```

后续检测裕量阶段才围绕三个冻结工作点：

```text
0.80 V -> M7/F6
0.95 V -> M4/F6
1.10 V -> M2/F9
```

研究局部 `M/F` 改变与传感器时序边界/等效电压阈值的关系。

H0 不提前定义任何 `ΔF` 或 `ΔM`。

---

# 23. Codex 执行顺序摘要

```text
H0-0  基线回读 / 冻结哈希
  │
  ▼
H0-1  所有权和下游接口契约
  │
  ▼
H0-2  新增 ftc_sensor_owner_handoff.sv
  │
  ▼
H0-3  新增 ftc_cal_detect_handoff_top.sv
  │
  ▼
H0-4  RTL 单元验证 + 三个黄金结果回放
  │
  ▼
H0-5  H0 新逻辑独立综合 / STA
  │
  ▼
H0-6  与已有 400 MHz 物理事件顺序静态组合
  │
  ▼
H0-7  H0 mapped + SDF 小型切换验证
  │
  ▼
H0-8  只有证据不足时才做一次完整集成综合/STA
  │
  ▼
最终 H0 门
```

执行核心原则：

> **新增逻辑只验证新增逻辑；旧传感器和旧启动校准证据能复用就复用。不要为了 H0 再跑一遍已经通过的 RF6/RF9D。**
