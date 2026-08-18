# FTC 标准单元负载细调级：负载固定、驱动器可选的逐步骤执行计划

## 0. 本次重构为什么必要

本计划已经不再处于“寻找标准单元负载”的阶段。远程仓库现有证据已经把问题收敛到一个更具体的物理矛盾：

```text
已完成路径选择中调级
        |
        +-- GO
        |
        v
标准单元输入负载细调
        |
        +-- X0P5 太小：调节量不足，需要 K≈116        -> NO-GO
        |
        +-- X8 太大：范围足够，但分辨率/波形受损       -> NO-GO
        |
        +-- 中间尺寸扫描
               |
               +-- 最终保留负载：NOR2_X4A_A9TL40，signal=A
               |
               +-- K=8 时分辨率和范围处于合理区间
               |
               +-- 唯一关键失败集中在
                   VDD=0.80 V, M=15, F=8
                   使用 BUF_X0P7M 驱动时高电平仅 0.717393 V
                   低于原始 0.90*VDD = 0.72 V 门限
                       |
                       v
               有界驱动器强度实验
                       |
                       +-- BUF_X0P8M : high/VDD=0.94947, PASS
                       +-- BUF_X1M   : high/VDD=0.98382, PASS
                       +-- BUF_X1P4M : high/VDD=0.99937, PASS
                       +-- BUF_X2M   : high/VDD=0.99999, PASS
```

因此，原计划中把细调固定驱动器写死为：

```text
BUF_X0P7M_A9TL40
```

已经与最新电气证据冲突。

**本次重构的核心决策是：**

> 细调负载单元固定为已经筛选出的 `NOR2_X4A_A9TL40` 的 A 输入方向；细调驱动缓冲器不再固定为 `BUF_X0P7M_A9TL40`，而是作为一个有界、可验证的标准单元设计变量。Codex 必须从已完成的真实 LVT 缓冲器序列中，寻找能够通过完整细调级验收的最小驱动器。

本计划仍只做到：

```text
标准单元负载细调级
+
覆盖一个中调步长
+
确定最小可接受细调驱动器
```

本计划仍然**不实现**旁路、配置跳过、最终两级编码、自校准或跌落检测。

---

# 1. Codex 开始前必须充分读取并冻结的最新证据

## 1.1 最新提交

开始执行前必须确认远程 `main`（主分支）至少包含：

```text
e8fd08b718716d5a2de6a093afa8fb53c9b8d0df
feat(ftc): compare remaining fine-driver sizes
```

如果远程 `main` 已经有更新提交，必须先读取更新内容；不得假定本计划编写时的提交仍是最新状态。

## 1.2 路径选择中调级：继续冻结为只读 GO 证据

必须读取但不得重跑：

```text
delay_chain/ftc/analysis/path_selection_medium_stage/
delay_chain/ftc/reports/FTC_PATH_SELECTION_MEDIUM_STAGE.md
delay_chain/ftc/scripts/run_path_selection_medium_stage.py
```

冻结：

```text
Path-Selection Medium Stage = GO
N_characterize = 16
Anchor VDD = 1.10, 0.95, 0.80 V

已测最大中调步长：
1.10 V : 33.703762 ps
0.95 V : 44.069195 ps
0.80 V : 66.862606 ps

已测最小中调步长：
1.10 V : 10.232424 ps
0.95 V : 13.209050 ps
0.80 V : 20.958529 ps
```

历史中调的 41 个 HSPICE（晶体管级电路仿真器）场景不得重新运行。

## 1.3 小尺寸、最大尺寸和中间尺寸负载实验全部转为历史证据

必须读取：

```text
delay_chain/ftc/analysis/standard_cell_load_fine_stage/
delay_chain/ftc/analysis/standard_cell_load_max_lvt_probe/
delay_chain/ftc/analysis/standard_cell_load_max_lvt_probe_0p88/
delay_chain/ftc/analysis/standard_cell_load_size_sweep/

delay_chain/ftc/reports/FTC_STANDARD_CELL_LOAD_FINE_STAGE.md
delay_chain/ftc/reports/FTC_STANDARD_CELL_LOAD_MAX_LVT_PROBE.md
delay_chain/ftc/reports/FTC_STANDARD_CELL_LOAD_MAX_LVT_PROBE_0P88.md
delay_chain/ftc/reports/FTC_STANDARD_CELL_LOAD_SIZE_SWEEP.md
```

这些已有电气场景全部只读，不得重新跑。

## 1.4 本阶段固定负载合同

本阶段不再重新选择 NAND/NOR，也不重新进行 28 候选尺寸扫描。

固定：

```text
candidate_id           = NOR2_X4A_A9TL40__signal_A
cell                   = NOR2_X4A_A9TL40
signal_pin             = A
control_pin            = B
high_cap_control_value = 0
low_cap_control_value  = 1
historical_K_candidate = 8
```

来源必须读取：

```text
delay_chain/ftc/analysis/standard_cell_load_size_sweep/fallback_1/selected_size_contract.json
```

历史单负载调节量：

```text
1.10 V : 4.242129 ps
0.95 V : 4.184472 ps
0.80 V : 4.457042 ps
```

注意：这些数值只属于历史 `BUF_X0P7M_A9TL40` 驱动条件。驱动器尺寸改变以后，细调步长和总范围必须重新实测，不能直接复用数值。

## 1.5 必须正确解释 NOR2_X4A 的历史 NO-GO

不得把中间尺寸扫描的总 `NO-GO` 误解成 `NOR2_X4A` 负载本身已经证明不可用。

对 `NOR2_X4A_A9TL40__signal_A` 的完整 fallback（后备候选）结果：

```text
K = 8

最大相邻细调步长：
1.10 V : 8.308268 ps
0.95 V : 9.924159 ps
0.80 V : 11.572565 ps

最小耦合中调步长：
1.10 V : 10.203422 ps
0.95 V : 13.825847 ps
0.80 V : 20.432596 ps
```

因此该候选在三个锚点下都满足：

```text
最大细调步长 < 最小耦合中调步长
```

其 `fallback_result.coupled_reasons` 只有：

```text
0.80 V M15->16 coverage failed
```

对应失败端点：

```text
VDD         = 0.80 V
medium code = 15
fine code   = 8
K           = 8
fine driver = BUF_X0P7M_A9TL40

output high = 0.717393004 V
output low  = 0.0118503303 V
rise time   = 396.472655 ps
```

原始高电平门限是：

```text
0.90 * 0.80 V = 0.72 V
```

符号说明：`0.90` 表示必须达到供电电压的 90%；`0.80 V` 是该场景供电电压；`*` 表示乘法；结果 `0.72 V` 是原始高电平有效门限。

因此该候选的关键失败是**固定细调驱动器过弱造成的波形建立失败**，而不是负载调节范围不足。

## 1.6 有界驱动器强度实验必须冻结为新的架构证据

必须读取：

```text
delay_chain/ftc/analysis/standard_cell_load_driver_strength_probe/
delay_chain/ftc/reports/FTC_STANDARD_CELL_LOAD_DRIVER_STRENGTH.md
delay_chain/ftc/scripts/run_standard_cell_load_driver_strength_probe.py
delay_chain/ftc/tests/test_standard_cell_load_driver_strength_probe.py
```

固定端点不变：

```text
load         = NOR2_X4A_A9TL40__signal_A
M            = 15
F            = 8
K            = 8
VDD          = 0.80 V
logic high   >= 0.90 * VDD
logic low    <= 0.10 * VDD
```

已有真实结果：

```text
BUF_X0P7M : high/VDD = 0.8967413, rise = 396.473 ps, FAIL
BUF_X0P8M : high/VDD = 0.9494658, rise = 344.226 ps, PASS
BUF_X1M   : high/VDD = 0.9838224, rise = 295.632 ps, PASS
BUF_X1P4M : high/VDD = 0.9993679, rise = 205.763 ps, PASS
BUF_X2M   : high/VDD = 0.9999906, rise = 153.470 ps, PASS
```

这组结果已经证明：

```text
“细调驱动器固定为 X0P7”不是必要架构约束。
```

而且从 X0P7 仅略增到 X0P8，就已经把最坏已知端点从失败提升到 `high/VDD=0.9495`。

这些驱动器端点场景不得重跑。

---

# 2. 重构后的细调物理结构

结构仍保持：

```text
路径选择中调级
      |
      v
 MEDIUM_OUT
      |
      v
+--------------------------------+
| 可选择的细调驱动缓冲器           |
| BUF_X0P8M / X1M / X1P4M / X2M |
+---------------+----------------+
                |
                +----------------------> FINE_OUT
                |
                +-- NOR2_X4A load V0
                +-- NOR2_X4A load V1
                +-- NOR2_X4A load V2
                |        ...
                +-- NOR2_X4A load V(K-1)
```

这里：

```text
中调网络             = 冻结，不允许修改
细调负载单元         = 冻结为 NOR2_X4A_A9TL40 signal=A
细调驱动器           = 本计划唯一允许重新选择的电路单元
K                    = 必须随驱动器重新推导，不得永久固定为 8
```

中调级仍然使用其历史 `BUF_X0P7M_A9TL40` 延时缓冲器。**只允许修改 `XFINE_DRIVER`，绝不能因为细调驱动器变化而修改中调网络中的 buffer（缓冲器）。**

---

# 3. 细调驱动器不再写死，但搜索必须有界

## 3.1 驱动器候选序列

历史 `BUF_X0P7M_A9TL40` 只作为失败基线，不再进入新仿真。

本轮允许：

```text
优先级 1 : BUF_X0P8M_A9TL40
优先级 2 : BUF_X1M_A9TL40
优先级 3 : BUF_X1P4M_A9TL40
优先级 4 : BUF_X2M_A9TL40
```

这些单元已经由现有驱动器探测脚本从真实 LVT Verilog/CDL 中确认，并且 CDL 总晶体管宽度严格递增。

不得自动扩展到 X3/X4/X6/X8 或其他 buffer 家族。如果四档完整验收都失败，再另开计划，不在本轮无限扩大驱动器。

## 3.2 驱动器选择目标

目标不是选输出边沿最快的最大驱动器，而是：

> **选择通过完整细调级所有电气 Gate（判定门槛）的最小驱动器。**

原因：更强驱动器虽然改善建立时间和高电平，但也可能降低相同负载切换带来的延时灵敏度，从而增大所需 K。

因此执行顺序固定：

```text
X0P8 -> 完整验收
   |
   +-- GO -> 立即停止，X0P8 为 selected_fine_driver
   |
   +-- NO-GO -> X1 完整验收
                    |
                    +-- GO -> 停止
                    |
                    +-- NO-GO -> X1P4
                                      |
                                      +-- ... -> 最多到 X2
```

## 3.3 恢复原始逻辑门限

本计划不使用 X8 实验中曾授权的 `0.88*VDD` 例外。

统一恢复：

```text
output_logic_high >= 0.90 * VDD
output_logic_low  <= 0.10 * VDD
```

因为 X0P8 及以上驱动器已经在历史最坏端点上证明能够满足原始 0.90 门限，没有必要再通过放宽门限救援。

---

# 4. 代码重构要求

## 4.1 不要破坏历史 runner（运行脚本）

现有：

```text
delay_chain/ftc/scripts/run_standard_cell_load_fine_stage.py
```

已经在底层函数中支持：

```text
render_deck(..., fine_driver_cell=...)
scenario_parameters(..., fine_driver_cell=...)
```

而且 `fine_driver_cell` 已进入场景参数和缓存身份，因此不同驱动器不会错误复用同一个 HSPICE 场景。

但是该脚本顶层仍保留：

```text
FINE_DRIVER_CELL = BUF_X0P7M_A9TL40
```

以及旧的固定驱动流程。

本计划**不要删除历史默认值，也不要改写历史分析目录的语义**。

建议新增：

```text
delay_chain/ftc/scripts/run_standard_cell_load_fine_stage_driver_codesign.py
```

该 runner 复用已经审查过的网表生成、HSPICE 完整性、分类和场景缓存 helper（辅助函数），但由它负责：

```text
固定 NOR2_X4A 负载合同
有界驱动器序列
每个驱动器重新推导 K
完整中调/细调耦合 Gate
选择最小通过驱动器
```

## 4.2 新分析目录

使用独立目录：

```text
delay_chain/ftc/analysis/standard_cell_load_fine_stage_driver_codesign/
delay_chain/ftc/runs/standard_cell_load_fine_stage_driver_codesign/
delay_chain/ftc/reports/FTC_STANDARD_CELL_LOAD_FINE_STAGE_DRIVER_CODESIGN.md
delay_chain/ftc/tests/test_standard_cell_load_fine_stage_driver_codesign.py
```

不得覆盖：

```text
standard_cell_load_fine_stage/
standard_cell_load_max_lvt_probe/
standard_cell_load_size_sweep/
standard_cell_load_driver_strength_probe/
```

---

# 5. 防重复仿真规则

每个新场景的身份必须至少包含：

```text
phase
medium_N
medium_code
medium_mux_cell
medium_delay_cell
fine_driver_cell
fine_load_cell
signal_pin
control_pin
low_cap_control_value
high_cap_control_value
K
fine_code
vdd_v
logic_high_min_ratio
logic_low_max_ratio
input_slew_contract
output_load_contract
```

特别是：

```text
fine_driver_cell
```

必须参与哈希和 `scenario_manifest.json`。X0P8、X1、X1P4、X2 之间禁止共享电气结果。

已有 driver-strength probe（驱动器强度探测）端点可以作为只读架构证据，但只有当新场景参数、runner/requirements/contract 哈希完全一致时才允许正式场景缓存复用；否则不得伪装成同一场景。

禁止调用以下历史主执行流程：

```text
run_path_selection_medium_stage.py
run_standard_cell_load_fine_stage.py 的 main 流程
run_standard_cell_load_size_sweep.py 的 main 流程
run_standard_cell_load_size_fallback.py 的 main 流程
run_standard_cell_load_driver_strength_probe.py 的 main 流程
run_fine_grained_controllable_delay.py
run_delay_code_refinement.py
run_programmable_acceptance_window.py
run_static_self_calibration.py
```

允许导入经过审查的纯 helper 函数，但不得通过 import 副作用或 subprocess 重跑历史实验。

---

# Phase 0 — 冻结负载与驱动器证据（0 个新 HSPICE）

生成：

```text
delay_chain/ftc/analysis/standard_cell_load_fine_stage_driver_codesign/requirements.json
```

至少记录：

```text
medium_stage_decision = GO
fixed_load_candidate  = NOR2_X4A_A9TL40__signal_A
signal_pin            = A
control_pin           = B
high_cap_control      = 0
low_cap_control       = 1
historical_K          = 8

historical_driver_baseline = BUF_X0P7M_A9TL40
historical_driver_baseline_result = FAIL_AT_0P80_M15_F8

driver_candidates = [
  BUF_X0P8M_A9TL40,
  BUF_X1M_A9TL40,
  BUF_X1P4M_A9TL40,
  BUF_X2M_A9TL40
]

driver_selection_policy = smallest_full_acceptance_GO
logic_high_min_ratio = 0.90
logic_low_max_ratio  = 0.10

bypass = future_work
config_skip = future_work
sensor = forbidden
xor = forbidden
dff = forbidden
calibration = forbidden
droop = forbidden
pvt = forbidden
rtl = forbidden
power = forbidden
area = forbidden
layout = forbidden

final_medium_N_frozen = false
final_fine_K_frozen   = false
```

还要保存所有关键历史证据的 SHA256。

---

# Phase 1 — 静态驱动器合同验证（0 个新 HSPICE）

对 4 个候选逐个从真实 LVT Verilog/CDL 检查：

```text
1. 单元确实存在；
2. 端口必须为同极性 BUF 类型；
3. CDL 端口必须匹配 Y VDD VNW VPW VSS A；
4. 逻辑必须是 Y=A；
5. 4 个候选 CDL 总晶体管宽度严格递增；
6. 不允许替换 medium stage 中的 BUF_X0P7M；
7. 只允许替换 XFINE_DRIVER。
```

输出：

```text
driver_contract.json
```

如果静态合同不成立：

```text
Fine Driver Co-Design = ARCHITECTURE_BLOCKED
```

0 HSPICE 结束。

---

# Phase 2 — 对当前最小可行驱动器重新表征 8 单元细调阵列

从：

```text
BUF_X0P8M_A9TL40
```

开始。

注意：历史驱动器端点已经证明 X0P8 能把最坏已知高电平从 `0.717393 V` 提升到 `0.759573 V`，但这只证明一个端点，不代表完整细调级 GO。因此必须重新测细调范围和分辨率。

## Step 2.1：0.95 V 全细调代码

固定：

```text
load = NOR2_X4A_A9TL40__signal_A
driver = 当前候选
medium_N = 16
medium_code = 8
K_test = 8
VDD = 0.95 V
F = 0..8
```

共 9 个场景。

定义：

```text
delta_F(F,V) = D(F+1,V) - D(F,V)
```

符号说明：`F` 是细调代码；`V` 是供电电压；`D(F,V)` 是固定中调代码和驱动器条件下的实际上升沿传播延时；`F+1` 表示只再切换一个负载到高电容状态；`-` 表示两个相邻代码传播延时相减；`delta_F` 是真实相邻细调步长。

所有相邻步长必须：

```text
delta_F > 0
```

## Step 2.2：1.10 V / 0.80 V 有界抽样

运行：

```text
VDD = 1.10, 0.80 V
F = 0,1,4,7,8
```

共 10 个场景。

要求抽样延时严格递增，并且全部满足原始 0.90/0.10 逻辑电平合同。

## Step 2.3：浅/深位置灵敏度

在 0.95 V 补：

```text
medium_code = 0,15
F = 0,1,8
```

共 6 个场景。

Phase 2 每个驱动器最多：

```text
9 + 10 + 6 = 25 个新 HSPICE 场景
```

符号说明：`9` 是 0.95 V 的完整 9 个代码；`10` 是两个边界电压各 5 个抽样代码；`6` 是浅、深两个中调位置各 3 个代码；`+` 表示场景数相加。

若任何代码出现：

```text
逻辑高电平不足
逻辑低电平超限
负延时
非单调
额外转换/毛刺
边沿测量失败
```

则当前驱动器 Phase 2 NO-GO，并进入下一更强驱动器。

---

# Phase 3 — 对每个驱动器重新推导 K

驱动器改变以后，禁止沿用历史 `K=8` 作为最终值。

对每个锚点计算 8 单元范围：

```text
FineRange_8(V) = D(F=8,V) - D(F=0,V)
```

符号说明：`FineRange_8(V)` 表示供电电压 `V` 下 8 个固定 NOR2_X4A 负载从全部低负载状态到全部高负载状态形成的真实延时范围；`D(F=8,V)` 是最大细调代码传播延时；`D(F=0,V)` 是最小细调代码传播延时；`-` 表示两端延时相减。

初步推导：

```text
K_pred(V) = ceil(8 * MediumStep_max(V) / FineRange_8(V))
```

符号说明：`K_pred(V)` 是供电电压 `V` 下预计覆盖一个最大中调步长所需的细调负载数量；`8` 是实测小阵列的负载个数；`MediumStep_max(V)` 是冻结中调接口在相同电压下的最大步长；`FineRange_8(V)` 是当前驱动器条件下实测的 8 单元细调范围；`*` 表示乘法；`/` 表示除法；`ceil` 表示向上取整。

取：

```text
K_candidate = max(K_pred(1.10), K_pred(0.95), K_pred(0.80))
```

符号说明：`K_candidate` 是当前驱动器的保守候选负载数量；`max` 表示取三个锚点预测值中的最大值。

硬限制继续保持：

```text
K_candidate <= 64
```

若某驱动器得到 `K_candidate > 64`，该驱动器不能 GO。

输出每个驱动器独立的：

```text
driver_<size>/fine_bank_sizing.json
```

---

# Phase 4 — 当前驱动器的完整 K 覆盖和单调性验收

只有当前驱动器通过 Phase 2/3 才进入。

## Step 4.1：先验证 M=7 -> 8

三个锚点分别运行：

```text
M=7, F=0
M=7, F=K
M=8, F=0
```

定义真实覆盖条件：

```text
D(M,K,V) >= D(M+1,0,V)
```

符号说明：`D(M,K,V)` 表示中调代码为 `M`、细调代码达到最大 `K`、供电电压为 `V` 时的传播延时；`D(M+1,0,V)` 表示下一中调代码配合最小细调代码时的传播延时；`>=` 表示当前中调档位的细调上限必须达到或超过下一中调档位的起点，从而不存在延时空洞。

若只有范围稍不足且波形全部有效，只允许对当前驱动器进行一次 K 重估；禁止逐个 K 暴力扫描。

## Step 4.2：0.95 V 完整 K 全码单调性

固定：

```text
M = 7
VDD = 0.95 V
F = 0..K
```

所有相邻步长必须严格为正。

## Step 4.3：1.10 V / 0.80 V 有界代码抽样

仅运行：

```text
F = 0
F = 1
F ~= K/4
F ~= K/2
F ~= 3K/4
F = K-1
F = K
```

`~=` 表示取最接近目标比例的合法整数细调代码。

不得在高低电压无理由做完整 K 暴力扫描。

---

# Phase 5 — 浅/中/深耦合覆盖与最终分辨率 Gate

对当前驱动器、当前最终候选 K 验证：

```text
M = 0 -> 1
M = 7 -> 8
M = 15 -> 16

VDD = 1.10, 0.95, 0.80 V
```

每个组合都必须满足：

```text
D(M,K,V) >= D(M+1,0,V)
```

同时测量 `M` 和 `M+1` 在 `F=0` 下的真实传播延时，得到当前驱动器条件下的耦合中调步长。

定义：

```text
MediumStep_coupled(M,V) = D(M+1,0,V) - D(M,0,V)
```

符号说明：`MediumStep_coupled(M,V)` 表示细调驱动器和完整负载阵列都已经物理接入时，相邻两个中调代码之间的真实延时差；`M+1` 是下一中调代码；`0` 是最低细调代码；`-` 表示传播延时相减。

然后验证：

```text
delta_fine_max(V) < MediumStep_coupled_min(V)
```

符号说明：`delta_fine_max(V)` 是当前驱动器在供电电压 `V` 下测得的最大相邻细调步长；`MediumStep_coupled_min(V)` 是浅/中/深三个代表中调位置中最小的耦合中调步长；`<` 表示最大的细调一步仍必须小于最小的中调一步。

三个锚点全部通过才算当前驱动器完整 GO。

---

# 6. 驱动器级状态机

每个驱动器独立输出：

```text
driver_<size>/summary.json
```

状态：

```text
GO
NO-GO
ARCHITECTURE_BLOCKED
NOT_RUN
```

总流程：

```text
BUF_X0P8M
  |
  +-- full acceptance GO
  |       -> selected_fine_driver = BUF_X0P8M
  |       -> STOP
  |
  +-- NO-GO
          -> BUF_X1M
                 |
                 +-- GO -> STOP
                 +-- NO-GO -> BUF_X1P4M
                                    |
                                    +-- GO -> STOP
                                    +-- NO-GO -> BUF_X2M
                                                       |
                                                       +-- GO -> STOP
                                                       +-- NO-GO -> overall NO-GO
```

只要某一档 GO，后面更大的驱动器全部 `NOT_RUN`。

最终选择原则只有：

```text
最小的完整 GO 驱动器
```

而不是：

```text
最大驱动器
最快边沿驱动器
最高 Vhigh 驱动器
```

---

# 7. 当前驱动器的完整 GO 条件

某一驱动器只有同时满足以下条件才能 GO：

```text
1. 真实 LVT Verilog/CDL 合同合法；
2. 只改变 XFINE_DRIVER，不改变中调网络；
3. NOR2_X4A 负载合同完全保持；
4. 0.95 V 的 K_test=8 全代码严格单调；
5. 1.10/0.80 V 的 K_test=8 抽样代码严格单调；
6. 所有测量满足 output_high >= 0.90*VDD；
7. 所有测量满足 output_low <= 0.10*VDD；
8. 无额外转换，rise/fall delay 与 10%-90% 边沿均可测；
9. 重新推导的 K <= 64；
10. 最终 K 在 0.95 V 下全代码严格单调；
11. M=0->1、7->8、15->16 × 三个电压共 9 个边界全部无空洞；
12. 三个电压下 delta_fine_max < MediumStep_coupled_min；
13. 没有重跑历史中调、历史负载尺寸扫描和历史 driver probe；
14. 没有实现旁路、自校准、DFF、跌落扫描或 PVT。
```

若失败，根因必须明确分类，例如：

```text
driver_waveform_high_fail
driver_waveform_low_fail
driver_settling_fail
fine_code_non_monotonic
fine_range_insufficient
K_exceeds_bounded_limit
medium_fine_gap_remains
fine_resolution_not_below_medium
edge_integrity_failure
library_driver_contract_blocked
```

---

# 8. 未来旁路接口仍然保留，但必须等驱动器选定以后再发布

只有选出 `selected_fine_driver` 后，才能计算新的：

```text
fine_driver_offset_ps_by_vdd
fine_bank_code0_offset_ps_by_vdd
fine_range_by_vdd
coverage_margin_by_vdd
selected_fine_driver
selected_fine_load
K_candidate_tt25
```

并写入：

```text
future_bypass_interface.json
```

必须继续：

```text
bypass_not_implemented = true
final_K_frozen = false
final_medium_N_frozen = false
```

因为后续加入旁路多路选择器以后固定开销还会改变。

---

# 9. 本计划明确禁止的范围

禁止：

```text
重新扫描 28 个负载候选
重新选择 NAND/NOR 逻辑族
重跑 X0P5/X8/中间尺寸历史扫描
重跑 X0P7 失败端点
重跑已经完成的 X0P8/X1/X1P4/X2 driver-strength probe
无限扩大驱动器尺寸
放宽 0.90*VDD 高电平门限
改变中调级 BUF/MUX 单元
加入 bypass
加入配置跳过
加入二维最终编码器
加入 tap29/XOR/DFF
加入启动自校准
加入 C_lock 和报警裕量
加入跌落攻击扫描
加入 PVT
加入 RTL
加入功耗/面积/版图
```

本阶段唯一新的架构自由度是：

```text
fine_driver_cell
```

---

# 10. 回归测试要求

新增：

```text
delay_chain/ftc/tests/test_standard_cell_load_fine_stage_driver_codesign.py
```

至少测试：

```text
1. fixed load 必须严格等于 NOR2_X4A_A9TL40__signal_A；
2. signal=A/control=B/high=0/low=1 不得变化；
3. driver candidates 必须严格等于 X0P8M/X1M/X1P4M/X2M；
4. 四档 CDL 总晶体管宽度严格递增；
5. medium network 中的 BUF_X0P7M 数量和单元类型不得因 driver 变化而改变；
6. 只有 XFINE_DRIVER 的 cell 可以变化；
7. scenario identity 必须包含 fine_driver_cell；
8. 不同 driver 不允许命中同一缓存；
9. 历史 runner main 不得 import/subprocess 执行；
10. 0.88 高电平例外不得进入本计划；
11. 一个 driver GO 后后续 driver 必须 NOT_RUN；
12. K>64 必须早停当前 driver；
13. 当前 driver 只允许一次 K rescale；
14. 高低电压不得无界 full-code sweep；
15. summary 必须证明 historical_medium_scenarios_rerun=0；
16. summary 必须证明 historical_load_sweep_scenarios_rerun=0；
17. summary 必须证明 historical_driver_probe_scenarios_rerun=0；
18. sensor/dff/droop/bypass scenario 数必须为 0；
19. final_fine_K_frozen=false；
20. final_medium_N_frozen=false。
```

至少执行：

```text
python3 -m unittest delay_chain.ftc.tests.test_standard_cell_load_fine_stage_driver_codesign
git diff --check
```

不得因为测试入口触发 HSPICE 历史主流程。

---

# 11. Codex 严格执行顺序

```text
Step 1  拉取并确认远程 main 最新提交，读取 e8fd08b 之后是否还有新证据。
Step 2  冻结路径选择中调 GO 证据；0 HSPICE。
Step 3  冻结 X0P5、X8、中间尺寸负载扫描及 fallback 证据；0 HSPICE。
Step 4  冻结 NOR2_X4A_A9TL40__signal_A 为唯一负载；不再 rerank load。
Step 5  冻结 X0P7 失败端点以及 X0P8/X1/X1P4/X2 驱动器探测结果；0 HSPICE。
Step 6  新建 driver-codesign analysis/run/report/test，不覆盖历史目录。
Step 7  静态验证 4 个 LVT driver 合同和严格递增物理宽度；0 HSPICE。
Step 8  从 BUF_X0P8M 开始，对 K_test=8 重新做 25 场景细调表征。
Step 9  重新计算当前 driver 的 FineRange_8 和 K_candidate。
Step 10 K>64 则当前 driver NO-GO；进入下一 driver。
Step 11 K 合法则运行 M=7->8 三电压真实覆盖。
Step 12 若只存在范围不足，只允许当前 driver 一次 K rescale。
Step 13 在 0.95 V 完整验证 F=0..K 单调性。
Step 14 在 1.10/0.80 V 只做有界代码抽样。
Step 15 验证 M=0->1、7->8、15->16 × 三电压耦合覆盖和逻辑完整性。
Step 16 重新计算 delta_fine_max 和 MediumStep_coupled_min。
Step 17 当前 driver 全部 Gate GO，则立即选择它并停止后续更大 driver。
Step 18 当前 driver NO-GO，则按 X0P8 -> X1 -> X1P4 -> X2 顺序进入下一档。
Step 19 若四档都 NO-GO，发布 Fine Driver Co-Design = NO-GO，不再自动扩大尺寸。
Step 20 若某档 GO，生成 future_bypass_interface.json，并发布完整 Fine Stage + One-Medium-Step Coverage = GO。
Step 21 无论 GO/NO-GO，本计划到此停止；不得实现 bypass、配置跳过、自校准或跌落检测。
```

---

# 12. 最终报告必须回答的问题

生成：

```text
delay_chain/ftc/reports/FTC_STANDARD_CELL_LOAD_FINE_STAGE_DRIVER_CODESIGN.md
```

至少明确回答：

```text
1. 为什么 NOR2_X4A 被固定为本轮唯一负载？
2. 为什么 X0P7 的历史失败应归因于细调驱动强度不足，而不是范围不足？
3. X0P8/X1/X1P4/X2 在历史最坏端点分别改善了多少高电平和 rise time？
4. 最终选择哪个 fine driver，为什么是最小通过者？
5. 驱动器变强后 8 单元细调范围发生了怎样的变化？
6. 每个 driver 重新推导出的 K 是多少？
7. 最终 K 是否 <=64？
8. 0.95 V 最终 K 是否全代码严格单调？
9. 1.10/0.95/0.80 V 是否全部满足原始 0.90/0.10 逻辑门限？
10. M=0->1、7->8、15->16 是否全部无延时空洞？
11. 最大细调步长是否仍小于最小耦合中调步长？
12. 新 driver 引入多少固定延时开销？
13. 未来 bypass 至少需要覆盖哪些固定开销？
14. 新增多少 HSPICE，复用多少新任务场景？
15. 哪些历史场景明确没有重跑？
16. 为什么本轮 GO 仍不等于完整 FTC 电压跌落检测宏 GO？
```

---

# 13. 最核心的架构判断

现在不应继续把：

```text
BUF_X0P7M_A9TL40
```

当作细调架构的一部分永久冻结。

现有数据已经证明：

```text
负载选择
与
驱动器强度
```

是耦合设计变量。

当前最合理的架构是：

```text
冻结中调级
+
冻结 NOR2_X4A 细调负载
+
在有限真实 LVT buffer 集合中选择最小可接受细调驱动器
+
对每个驱动器重新推导 K 和完整耦合行为
```

只有这样，才能把当前“负载本身合适，但 X0P7 驱动不足”的实验结果真正转化为可继续推进的细调级架构，而不是继续被旧计划的人为固定约束卡住。
