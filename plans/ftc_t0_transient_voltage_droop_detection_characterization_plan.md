# FTC T0 瞬态电压跌落检测能力表征逐阶段推进计划

**仓库：** `Peiki0622/power_macro`  
**目标分支：** `main`  
**T0 原始输入基线：** `46ebf25e9bb15aba29be23f79e8aa3ed8b8ad474`  
**T0-2 纠偏完成提交：** `b3fe480c461b6b8a5d2f10a276d763ba9aae9526`  
**T0-4 纠偏闭合提交：** `bfe5ba69e68849f9c46db36ff6d0f43022769f2e`  
**当前阶段状态：** T0-2 已在本地电源归一化接口抽象下纠偏通过，T0-2E 已完成零 HSPICE 证据闭合，T0-3 相位敏感窗口已 GO，T0-4 六个正式检测配置的“跌落深度—最短可检测持续时间”边界已纠偏并 GO；下一步不是重跑 T0-4，而是先执行 **T0-4E：零 HSPICE 证据闭合、清理旧 T0-4 STOP 残留、建立跨 runner 修改的电气等价复用并解封 T0-5**，然后进入 T0-5A/T0-5B 时间覆盖率表征。  
**阶段定位：** H0 校准到检测所有权切换已通过，M0/M0-E 静态检测裕量与静态触发电压已闭合，M1 可编程检测配置已通过，M1-T 时序证据已闭合；T0 只研究当前冻结传感器面对真实瞬态电压跌落时的物理检测边界，并为后续 D0 运行时检测状态机给出必须满足的检测时序合同。

---

# 0. T0 的唯一宏观目标

T0 不再回答“静态电压下降多少会触发”，这个问题已经由 M0 完成；T0 也不负责写运行时检测状态机、报警、心跳或动态重校准，这些属于 D0。

T0 只回答以下几个物理问题：

1. 一个有限持续时间的电压跌落，至少要多深、持续多久，当前传感器才会被真实触发器检测到；
2. 同样的瞬态跌落出现在一次检测动作的不同时间位置时，哪些位置可检测、哪些位置属于盲区或恢复沿模糊区；
3. 不同检测裕量等级下，电压跌落深度与最短可检测持续时间之间是什么关系；
4. 为了覆盖目标攻击持续时间，未来 D0 最多允许多长的检测间隔；
5. 当前已经验证的一次性单 probe 时序与未来周期性运行时探测之间是否存在节拍矛盾；
6. 低于 0.80 V 的严重欠压应继续使用精确时序比较，还是应转入失效保护语义。

T0 的最终输出必须是一套可以直接约束 D0 的**瞬态威胁与检测时序合同**，而不是一批互不相干的 HSPICE 波形。

---

# 1. 冻结基线与已有证据

T0 必须把以下内容视为只读基线，非必要不得重跑。

## 1.1 冻结结构

- 当前冻结 `FTC_SENSOR`；
- medium 级 N=16；
- medium delay cell `BUF_X0P7M_A9TL40`；
- medium mux `MXT2_X0P5M_A9TL40`；
- fine driver `BUF_X0P8M_A9TL40`；
- fine load `NOR2_X4A_A9TL40`，信号 A；
- fine K=10；
- sensor tap 29；
- 初始 RVT 4 级、LVT 0 级；
- 30 个可观测级；
- XOR `XOR2_X0P5M_A9TL40`；
- DFF `DFFRPQ_X0P5M_A9TR40`；
- Q settle 200 ps；
- H0 所有权切换结构；
- M1 12 项精确检测配置表；
- 400 MHz / 2.5 ns 控制时钟合同。

## 1.2 已有静态检测证据

M0/M0-E 的静态触发深度只作为 T0 的参考锚点，不允许重新扫一遍来“复现”已有工作：

```text
0.95 V 正常工作点：
L1 -> 0.88 V，静态跌落深度约 70 mV
L2 -> 0.86 V，静态跌落深度约 90 mV
L3 -> 0.83 V，静态跌落深度约 120 mV

1.10 V 正常工作点：
L1 -> 1.01 V，静态跌落深度约 90 mV
L2 -> 0.96 V，静态跌落深度约 140 mV
L3 -> 0.93 V，静态跌落深度约 170 mV
```

对应 M1 精确检测配置：

```text
M4/F6 锚点：
L1 -> M4/F9
L2 -> M5/F6
L3 -> M5/F9

M2/F9 锚点：
L1 -> M2/F10
L2 -> M3/F8
L3 -> M3/F10
```

0.80 V 锚点只保留“配置合法、正常点已表征”的意义，不具有 `<0.80 V` 正式瞬态触发资格。

## 1.3 M1-T 风险记录

当前 M1-T 已确认：

```text
最差全局 setup +1.168 ps 是输入到寄存器路径，包含外部输入预算；
真正内部最差寄存器到寄存器 setup 约 +7.005 ps；
该路径属于一次性检测配置路径，不属于 T0 的实时传感路径。
```

因此 T0 **不修改 M1，也不因为 +7.005 ps 重新综合或重跑 M1**。该余量只作为未来 D0 集成/布局布线阶段的实现风险保留。

## 1.4 T0-2 纠偏后的权威证据【已完成】

提交 `b3fe480c461b6b8a5d2f10a276d763ba9aae9526` 已完成 T0-2 测试平台纠偏，后续 T0 必须以该提交及其后续明确取代证据作为物理基础，不得再使用原先固定高电平版本的结果作为正式结论。

纠偏后的正式事实为：

```text
PD_CTRL 内部保持稳定 0/1 逻辑语义；
PD_CTRL -> PD_SENSE 的 28 条验证跨域信号在 PD_SENSE 侧按瞬时 VDD_MONITORED 归一化；
S_CLK、复位、16 条 medium、10 条 fine 的本地高电平随 VDD_MONITORED；
XOR/CK 的时序测量阈值使用瞬时本地 VDD_MONITORED/2；
M0 0.87 V、M5/F6 与 T0 恒定低压兼容模式通过零 HSPICE 电气等价审计；
四个先行纠偏点全部恢复原 M0 的 Q0/Q1 方向；
六个正式检测配置的 12 个长脉冲场景全部通过；
T0-2 = CORRECTED PASS。
```

原 62 个使用固定 `VDD_VALUE` 作为跨域高电平的 T0 场景必须永久保留，但状态只能是：

```text
HISTORICAL_SUPERSEDED_NOT_DELETED
```

它们可以用于说明纠偏过程，不得用于后续 T0-3/T0-4/T0-5/T0-6 的物理结论，也不得再次被当成 T0-2 的正式失败证据。

## 1.5 T0-3 权威证据【已完成，GO】

T0-3 已在两个 L2 代表点上证明存在清楚、可重复的相位敏感窗口：

```text
0.95 V / L2 / M5-F6 / Vdroop=0.86 V / hold=3000 ps
稳定 Q1 采样窗口：当前已观测 -1000 ps .. +75 ps
其后进入稳定 Q0 区；转换边界细化到 25 ps。

1.10 V / L2 / M3-F8 / Vdroop=0.96 V / hold=3000 ps
稳定 Q1 采样窗口：当前已观测 -1000 ps .. +25 ps
其后进入稳定 Q0 区；转换边界细化到 25 ps。
```

当前两个 Q1 区的左端都停在已扫描范围的 `-1000 ps` 边界，因此这些结果证明了**存在时间敏感窗口**，但还不能把 `-1000 ps` 当作真实左边界。T0-5A 必须复用这些数据并仅向更早相位扩展，直到得到稳定 Q0，形成真正封闭的单 probe 可检测窗口。

## 1.6 T0-4 权威证据【已完成，GO】

提交 `bfe5ba69e68849f9c46db36ff6d0f43022769f2e` 已纠正 T0-4 原错误判门并完成两个异常的局部物理诊断。

正式事实：

```text
T0-4 = GO
正式 T0-4 历史场景 = 238 个，全部保留并复用，没有整体重跑；
6 个 last_q0_control 均在最长 3000 ps 测试下稳定 Q0；
last_q0_control 的 minimum_detectable_hold_ps=null 是正确负控制语义，不是失败；
18 个正式 Q1 检测点均已得到有效 clean-Q1 minimum duration；
invalid minimum duration = 0；
duration Q1 -> Q0 reversal = 0。
```

六个正式候选的持续时间边界以 `amplitude_duration/minimum_duration_boundary.csv` 为权威表，关键值包括：

```text
0.95 V / L1 / M4-F9：
70 mV -> 1360 ps
80 mV -> 1344 ps
90 mV -> 1296 ps

0.95 V / L2 / M5-F6：
90 mV  -> 1454 ps
100 mV -> 1438 ps
110 mV -> 1360 ps

0.95 V / L3 / M5-F9：
120 mV -> 2000 ps（1500 ps Q0 -> 1750 ps 恢复沿模糊 -> 2000 ps clean Q1）
130 mV -> 1562 ps
140 mV -> 1578 ps

1.10 V / L1 / M2-F10：
90 mV  -> 1500 ps（1000 ps Q0 -> 1250 ps 恢复沿模糊 -> 1500 ps clean Q1）
100 mV -> 1062 ps
110 mV -> 1031 ps

1.10 V / L2 / M3-F8：
140 mV -> 1188 ps
150 mV -> 1188 ps
160 mV -> 1172 ps

1.10 V / L3 / M3-F10：
170 mV -> 1234 ps
180 mV -> 1250 ps
190 mV -> 1250 ps
```

### 1.6.1 两个 T0-4 异常的最终定性

原异常点：

```text
0.95 V / L3 / Vdroop=0.83 V / phase=-450 ps / hold=1750 ps
1.10 V / L1 / Vdroop=1.01 V / phase=-500 ps / hold=1250 ps
```

两点在 1 ps 电源恢复沿下都曾出现第二次 `dff_ck` 相对本地 `VDD_MONITORED/2` 的交叉；但诊断确认：

```text
两次交叉之间 dff_ck/VDD_MONITORED 的最低局部值约为 0.5；
没有观察到一个稳定的逻辑低态；
两点 Q 双采样始终保持 stable_high；
恢复沿改为 10 ps 后，恢复窗口中的第二交叉都消失；
因此 real_second_clock_present = false；
根因 = fast_recovery_dynamic_local_rail_threshold_sensitivity。
```

正式结论：这是**1 ps 极快恢复沿下的本地动态门限敏感性**，不是一个已经证实的 `dff_ck` 低→高→低→高真实二次时钟。未来新的相位场景若出现类似现象，不得自动忽略，也不得自动判整个 T0 失败；应先保留为恢复沿模糊点，只在必要时做局部 10 ps 恢复沿敏感性检查。

---

# 2. 本阶段绝对禁止事项

除非后续某个明确停止门证明已有结构本身有错误，否则禁止：

```text
重跑 H0 / H0-E
重跑完整启动校准
重跑 M0 静态局部面 / trip sweep / M0-E
重跑 M1 RTL/SVA / 综合 / mapped+SDF / M1-T STA
重跑 RF6 / RF8 / RF9C / RF9D
重跑 XA 全流程
修改六个冻结校准 RTL
修改 H0 RTL
修改 M1 mapper / manager RTL
修改 FTC_SENSOR
修改 medium/fine/XOR/DFF 拓扑
修改 400 MHz 校准合同
设计 D0 检测状态机
设计报警逻辑
设计 heartbeat/timeout RTL
做动态重校准
做 PVT / Monte Carlo / post-layout
搜索或引入真实跨压 level shifter / isolation cell
```

额外禁止：

```text
因为修改 T0 runner 而自动重跑已经通过的 T0-2 正式 12 点；
因为 source_hash 改变而整体重跑 T0-3 或 T0-4；
重新运行旧的固定高电平 T0-2 流程；
把旧 long_pulse_consistency/summary.json 的 STOP 当成当前权威 Gate；
把旧 T0-4 STOP 的 phase_coverage/cadence/downstream 占位状态当作当前物理结论；
删除、覆盖或改写旧 62 个 T0-2 历史场景；
删除 T0-4 两个恢复沿异常或通过后处理强制单调化；
重新执行全部 238 个 T0-4 场景；
仅为了“保险”做六个 margin × 多深度 × 多持续时间 × 全相位暴力网格。
```

**核心原则：** T0 只新增“现有证据回答不了的瞬态物理问题”的仿真。能由已有 CSV/JSON/报告直接复用的内容一律不得通过重新跑仿真获得。

---

# 3. T0 的正式研究范围与判决语义

## 3.1 正式检测工作点

只把以下六个工作点定义为正式瞬态检测候选：

```text
0.95 V：L1 / L2 / L3
1.10 V：L1 / L2 / L3
```

L0 只作为正常/控制工作点，不用于宣称电压跌落触发能力。

0.80 V 的 L0-L3 只可用于必要的合法性或正常点控制，不允许在 T0 中升级为 `<0.80 V` 正式检测能力。

## 3.2 唯一权威判决

真实 DFF 的 Q 结果以及后续双采样可解释状态是唯一检测判据。

```text
R = W_xor - D_ref
```

只能作为机理解释量，不得替代真实 DFF 判决。

对 T0-3 及其后的动态相位场景，两个 Q 采样点必须分别按**各自采样时刻的本地 `VDD_MONITORED`**进行高低判决，不能把固定 `Vdroop` 作为两个采样点共同的判决电压。

至少需要记录：

```text
VDD_at_Q_sample_1
VDD_at_Q_sample_2
Q_sample_1 / VDD_at_Q_sample_1
Q_sample_2 / VDD_at_Q_sample_2
Q_final
```

## 3.3 T0-5 以后必须使用四状态解释

后续完整相位覆盖分析至少区分：

```text
CLEAN_Q1：两次 Q 采样稳定高，场景有效，无未解释多交叉；
STABLE_Q0：两次 Q 采样稳定低，场景有效；
RECOVERY_EDGE_AMBIGUOUS：恢复沿导致动态本地门限重新交叉或 Q 判决不能保证；
OTHER_INVALID_AMBIGUOUS：其它缺失 crossing、采样不稳定、恢复不安静等未解决异常。
```

其中只有 `CLEAN_Q1` 可以计入“保证检测”覆盖。恢复沿模糊点不得因为 Q 最终为高就自动计入 clean detection，也不得直接等价为物理失败。

---

# 4. T0-0 —— 冻结瞬态威胁与单次检测实验合同【已完成】

所有正式 T0 瞬态继续使用有限斜率梯形/PWL 电源波形：

```text
正常电压 Vbase
   ↓ t_fall
最低电压 Vdroop
   ↓ t_hold
恢复到 Vbase
   ↑ t_rise
```

统一参数：

```text
Vbase
DeltaV = Vbase - Vdroop
t_fall
t_hold
t_rise
phase
```

`phase` 冻结为：

> 电源下降开始时刻相对于本次真实检测 `S_CLK` 上升沿的时间偏移。

PWL 不允许同一时刻从 Vbase 直接跳到 Vdroop；必须有非零 `t_fall/t_rise`。

当前合同仍把 1 ps 下降/恢复作为主研究斜率，把 10 ps 作为敏感性检查。它们都是研究假设，不得写成真实芯片电源网络已经证明的斜率。

至少继续冻结：

```text
delay_chain/ftc/analysis/t0_transient_droop/contract/T0_TRANSIENT_THREAT_CONTRACT.json
delay_chain/ftc/controller/final_closure/freeze/POWER_DOMAIN_CONTRACT.json
S_CLK / reset / configuration 跨域合同
```

---

# 5. T0-1 —— 当前 FTC 专用瞬态单次检测 runner【已完成并纠偏】

后续不得重新建立另一套近似传感器模型。必须保持：

```text
当前 FTC_SENSOR
当前 medium/fine 拓扑
当前 XOR
当前真实 DFF
当前 M1 精确 M_det/F_det
当前单次 probe 时序
PD_CTRL 稳定逻辑语义
PD_SENSE 本地 VDD 归一化跨域抽象
```

唯一允许变化的物理研究变量仍然是 `VDD_MONITORED` 的瞬态波形参数。

后续 runner 可以扩展相位扫描、持续时间扫描、窗口后处理、覆盖率和 cadence 数学分析，但不得改变传感器拓扑、M/F 物理编码、DFF 连接、本地电源归一化方式和已冻结单 probe 事件时序。

---

# 6. T0-2 —— 长脉冲静态到瞬态一致性硬门【CORRECTED PASS】

T0-2 已完成，禁止再次执行旧 `phase_long_pulse()`、旧 `--phase long-pulse`、旧固定高电平 12 点或纠偏后正式 12 点，除非未来明确发现已保存的 deck/listing/measurement 损坏且无法复核。

旧 `long_pulse_consistency/summary.json` 的 STOP 只保留历史审计意义，当前权威入口是 `correction/` 和当前 `T0_GATE_STATUS.json`。

---

# 7. T0-2E —— 纠偏后证据闭合【已完成，0 HSPICE】

T0-2E 已完成以下工作：

```text
correction/four_point_summary.json 已远程闭合；
correction/formal_12_summary.json 已远程闭合；
旧 T0-2 STOP 已机器可读 superseded；
phase-window 已切断旧 phase_long_pulse 重跑路径；
动态 Q 判决已使用两个采样时刻各自本地 VDD；
T0-3 已被合法解封并完成。
```

后续不得重新把 T0-2E 当成待执行阶段。

---

# 8. T0-3 —— 中等裕量相位敏感窗口【已完成，GO】

T0-3 已完成两个 L2 代表点的粗扫和 25 ps 边界细化，证明当前冻结结构存在清楚、可重复的时间敏感窗口。

权威结果来自：

```text
delay_chain/ftc/analysis/t0_transient_droop/phase_window/phase_window.csv
delay_chain/ftc/analysis/t0_transient_droop/phase_window/summary.json
```

T0-3 的作用只是在物理上证明“存在 Q0/Q1 时间窗口并可重复定位边界”。由于两个可检测窗口的左端都被当前扫描下限 `-1000 ps` 截断，T0-3 不能直接承担最终完整相位覆盖率结论；该缺口交给 T0-5A 用最小新增仿真闭合。

---

# 9. T0-4 —— 六个正式工作点的“跌落深度—最短可检测持续时间”边界【已纠偏完成，GO】

## 9.1 当前权威判门

T0-4 的正确规则已经冻结：

```text
last_q0_control：
  这是略浅于静态 trip 的负控制；
  允许 minimum_detectable_hold_ps = null；
  最长已测 3000 ps 仍稳定 Q0、valid、无 anomaly、无 Q1 误触发 -> PASS。

first_q1_anchor 及更深点：
  必须存在 clean-Q1 minimum duration；
  ambiguous 点永久保留，不平滑、不删除、不强制单调；
  若局部结构为 Q0 -> ambiguous -> clean Q1，则 minimum 取第一个已有 clean Q1 点，并同时保留 bracket。
```

## 9.2 两个恢复沿特殊边界

当前两个特殊正式边界保留为：

```text
0.95 V / L3 / 120 mV：
1500 ps Q0 -> 1750 ps RECOVERY_EDGE_AMBIGUOUS -> 2000 ps CLEAN_Q1
正式 minimum clean-Q1 = 2000 ps

1.10 V / L1 / 90 mV：
1000 ps Q0 -> 1250 ps RECOVERY_EDGE_AMBIGUOUS -> 1500 ps CLEAN_Q1
正式 minimum clean-Q1 = 1500 ps
```

这两个点的模糊行为已经通过 1 ps/10 ps 局部诊断解释，不得再次作为阻塞 T0-5 的理由。

## 9.3 T0-4 当前 Gate

```text
T0-4 = GO
6 个负控制 PASS
18 个正式 clean-Q1 minimum duration 有效
Q1->Q0 reversal = 0
real second clock = false
```

除非未来新的独立证据直接推翻上述事实，否则禁止再次运行完整 `phase_amplitude_duration()` 或用旧的错误判门覆盖当前结果。

---

# 10. T0-4E —— T0-4→T0-5 零仿真证据闭合与执行解封【当前下一步，0 HSPICE】

这是当前唯一正确的下一阶段。**新增 HSPICE 必须严格为 0。**

## 10.1 目标一：冻结 T0-4 权威证据身份

建立机器可读 T0-4E 证据闭合记录，至少绑定以下文件及 SHA256：

```text
amplitude_duration/summary.json
amplitude_duration/minimum_duration_boundary.csv
amplitude_duration/anomaly_diagnostics.json
reports/T0_GATE_STATUS.json
reports/FTC_T0_TRANSIENT_DROOP_CHARACTERIZATION.md
controller/final_closure/freeze/POWER_DOMAIN_CONTRACT.json
```

必须明确：

```text
T0-4 = GO
T0-4 formal historical scenario count = 238
T0-4 diagnostic unique electrical cases = 4（两个异常 × 1 ps/10 ps）
诊断目录累计运行数可大于 4，但必须区分测量修订重跑与唯一电气场景数
T0-4E 本阶段 HSPICE = 0
```

## 10.2 目标二：清理旧 T0-4 STOP 残留，但不伪造 T0-5/T0-6 结果

当前仓库仍有历史占位文件写着 `BLOCKED_BY_T0_4_STOP`，至少包括：

```text
phase_coverage/phase_coverage.csv
cadence/cadence.csv
contract/T0_DOWNSTREAM_D0_TIMING_CONTRACT.json
```

T0-4E 必须把这些状态改成与当前 Gate 一致的**等待下游表征**状态，而不是物理阻塞：

```text
T0-4 = GO
T0-5 = ENABLED
T0-6 = WAITING_FOR_T0_5_GATE
runtime_probe_period.maximum_period_s = null
runtime_probe_period.status = PENDING_T0_5_T0_6
source_gate = T0-4 GO
```

不得在 T0-4E 提前填写覆盖率、最大 probe period 或 400 MHz 资格。

旧 `BLOCKED_BY_T0_4_STOP` 内容可以通过独立 supersession/audit 记录保留历史，不得继续作为当前程序的执行条件。

## 10.3 目标三：保护旧 STOP/旧 amplitude-duration 入口

当前 runner 中保留的历史入口不能再有能力覆盖已纠偏的权威 T0-4 结果。至少做到：

```text
旧 amplitude-duration 入口若发现当前 T0-4 已冻结为 GO，默认拒绝执行；
旧 finalize-stop / publish_t0_4_stop 只能用于真正新的未闭合 STOP，不得覆盖当前 corrected GO；
旧错误条件“所有 boundary 均要求 minimum != null”不得再成为任何当前 Gate；
任何历史终态报告函数不得把已纠偏的 T0-4 又写回 NO-GO。
```

优先采用显式阶段状态检查和机器可读权威证据哈希，不删除历史函数和历史结果。

## 10.4 目标四：建立跨 runner 修改的电气等价复用

这是 T0-5 前必须完成的关键基础设施。

当前 `source_hash()` 会包含整个 runner 源码；以后只要增加 T0-5/T0-6 后处理代码，就可能使场景身份变化。**源码哈希变化本身绝不能成为重跑旧 T0-3/T0-4 HSPICE 的理由。**

后续 `execute()`/复用逻辑至少应支持：

```text
第一优先：精确 scenario_id + parameters + deck hash 命中 -> 直接复用。

若仅因 source_hash 不同导致 scenario_id 不命中：
  1. 建立“电气参数投影”，忽略 source_hash 和纯编排/报告字段；
  2. 比较 baseline_vdd_v、margin、M/F、Vdroop、t_fall、t_hold、t_rise、phase、control_mode 等真正决定 deck 的物理参数；
  3. 用当前冻结 renderer 重新生成候选 deck；
  4. 若与已保存 deck 的有效电气内容/规范化 deck SHA 等价，则复用原 listing/measurement；
  5. 记录 reuse_reason = ELECTRICALLY_EQUIVALENT_SOURCE_HASH_DRIFT；
  6. 不运行 HSPICE。
```

如果当前 deck 内包含不影响电气行为的 source hash 注释，允许先做规范化 deck hash（只去除明确声明的非电气元数据行），但必须把规范化规则机器可读冻结，禁止通过宽松文本处理把真正的电路差异误判为等价。

只有真正电气参数或 deck 有差异时才允许建立新 T0-5 场景。

## 10.5 T0-4E Gate

只有全部满足才可解封 T0-5：

```text
T0-4 authority hash record 完整；
旧 BLOCKED_BY_T0_4_STOP 状态已被当前 T0-4 GO 取代；
T0_DOWNSTREAM_D0_TIMING_CONTRACT 不再声称 T0-4 STOP；
T0-5 = ENABLED；
T0-6 = WAITING_FOR_T0_5_GATE；
旧 amplitude-duration/STOP 入口不能覆盖 corrected T0-4；
电气等价复用测试覆盖 source_hash drift 且 HSPICE=0；
T0-4E 本阶段新增 HSPICE=0。
```

任何一项失败都只修证据/代码，不进入新的物理相位扫描。

---

# 11. T0-5 —— 将持续时间边界放回完整相位，量化时间覆盖率

T0-5 只在 T0-4E PASS 后执行。不得直接把 T0-4 的“代表相位最短持续时间”写成任意相位保证检测。

T0-5 分成 **T0-5A 主闭合** 和 **T0-5B 极小补充**，禁止一次性做六个 margin 的全维暴力扫描。

## 11.1 T0-5A —— 两个 L2 代表点的完整单 probe 时间窗口

优先继续使用 T0-3 的两个 L2 配置，以保证物理问题连续并最大化复用。

### 11.1.1 边界附近场景

固定使用 T0-4 已闭合的 first-Q1 深度和 minimum clean-Q1 持续时间：

```text
0.95 V / L2 / M5-F6
Vdroop = 0.86 V
DeltaV = 90 mV
hold = 1454 ps
总脉冲约 1456 ps（1 ps fall + hold + 1 ps rise）

1.10 V / L2 / M3-F8
Vdroop = 0.96 V
DeltaV = 140 mV
hold = 1188 ps
总脉冲约 1190 ps
```

这两个点回答“刚达到代表相位检测边界的脉冲，在完整时间位置上到底有多少覆盖”。

### 11.1.2 明显可检测长脉冲场景

同时保留：

```text
0.95 V / L2 / 0.86 V / hold=3000 ps
1.10 V / L2 / 0.96 V / hold=3000 ps
```

这两类场景必须优先复用 T0-3 已有 phase 点，禁止重跑相同电气参数。

T0-3 当前左边界被 `-1000 ps` 截断。T0-5A 对长脉冲只允许：

```text
从 -1000 ps 向更早相位按约 250 ps 粗步进扩展；
直到首次得到合法稳定 Q0；
然后只在最新 Q0/Q1 边界附近按 25 ps 细化；
已有 -1000 ps 及之后全部相位点直接复用。
```

如果右侧现有扫描端仍未回到稳定 Q0，也采用同样原则只向右扩；禁止重扫整个区间。

### 11.1.3 边界附近短脉冲的相位扫描

对 1454 ps / 1188 ps 两个边界脉冲，先使用 T0-3 已知时间窗口作为初始中心，只对未知区域做 250 ps 粗扫；出现任意状态变化后仅在边界附近做 25 ps 细化。

扫描范围的终止条件不是固定点数，而是两端都已经得到连续稳定 Q0，且所有 CLEAN_Q1/AMBIGUOUS 区间均被左右 Q0 闭合。

如果最左/最右仍为 Q1 或 ambiguous，只向该方向继续扩展，不回头重跑已覆盖区域。

## 11.2 T0-5A 每个场景必须记录

至少记录：

```text
phase
VDD_at_Q_sample_1
VDD_at_Q_sample_2
Q_sample_1
Q_sample_2
Q_sample_1/VDD_at_Q_sample_1
Q_sample_2/VDD_at_Q_sample_2
Q state
active CK crossing 信息
恢复沿开始/结束时刻
实际最小 VDD
R（仅诊断）
reuse/new/reparsed 证据来源
```

并按第 3.3 节四状态语义输出。

## 11.3 恢复沿模糊点的处理

如果 T0-5 新出现与 T0-4 相似的恢复沿二次动态交叉：

```text
先保留为 RECOVERY_EDGE_AMBIGUOUS；
不得计入 clean detection；
不得删除或强制改成 Q1；
只有当它改变窗口边界/覆盖率结论且已有 T0-4 诊断不能解释时，才允许对该新边界点增加一个 10 ps 恢复沿局部敏感性检查；
禁止做完整 10 ps 相位扫描。
```

如果局部 10 ps 行为与 T0-4 已知模式一致：1 ps 有动态交叉、10 ps 消失、Q 始终稳定高，则归类为“极快恢复沿敏感模糊区”，不是新物理二次时钟。

## 11.4 T0-5B —— 两个最有信息量的特殊裕量点

只有 T0-5A GO 后才执行，且只补两个 T0-4 特殊边界：

```text
0.95 V / L3 / M5-F9 / Vdroop=0.83 V / hold=2000 ps
1.10 V / L1 / M2-F10 / Vdroop=1.01 V / hold=1500 ps
```

理由：这两个点正好对应 T0-4 的 `Q0 -> recovery ambiguous -> clean Q1` 特殊边界，可以判断可编程 margin 与恢复沿敏感性如何共同改变完整时间覆盖。

T0-5B 同样只做自适应相位粗扫 + 边界细化；不得扩展成六个 margin 的全相位网格。

## 11.5 T0-5 核心输出

每个代表场景都必须输出所有连续区间，而不是一个全局最小/最大相位：

```text
所有 CLEAN_Q1 连续区间
所有 STABLE_Q0 连续盲区
所有 RECOVERY_EDGE_AMBIGUOUS 区间
所有 OTHER_INVALID_AMBIGUOUS 区间
每个区间宽度
最大连续非保证检测窗口
总采样相位点数
有效稳定相位点数
clean detection 相位点数
ambiguous 相位点数
clean phase coverage fraction
```

必须明确区分：

```text
最佳相位可检测
单 probe clean detection 时间覆盖率
恢复沿非保证区域
全相位保证检测
```

禁止把“某个相位可以检测”写成“任意相位保证检测”。

## 11.6 T0-5 Gate

T0-5A 两个基准电压都必须满足：

```text
边界脉冲和长脉冲均形成左右闭合的时间响应；
至少存在一个合法 CLEAN_Q1 区；
左右最终均回到 STABLE_Q0；
ambiguous 不主导整个相位响应；
没有大量不可解释的 Q1->Q0 物理反转；
所有新增恢复沿异常都可被现有模型解释或被单独保留；
没有因为 source_hash 变化而重跑已有 T0-3/T0-4 场景。
```

若 T0-5A 不满足，先停在 T0-5A 检查窗口定义/物理波形，不执行 T0-5B。

T0-5A GO 后执行 T0-5B；T0-5B 的特殊点允许出现明确记录的恢复沿模糊区，只要可重复、非主导且没有新真实二次时钟证据。

T0-5 完成后：

```text
T0-5 = GO
T0-6 = ENABLED
```

---

# 12. T0-6 —— 由单 probe 物理窗口反推未来运行时检测间隔

这一阶段不写 D0 RTL，也不默认需要新增 HSPICE。

## 12.1 优先做 0 HSPICE 数学窗口映射

把 T0-5 得到的每个单 probe CLEAN_Q1 区间表示成时间集合：

```text
W = W1 ∪ W2 ∪ ...
```

对于候选 probe period `P`，周期复制：

```text
W_P = ⋃(W + kP)
```

在一个周期模 `P` 的攻击相位域中计算：

```text
clean detection coverage
ambiguous coverage
stable blind coverage
最大连续非保证窗口
最坏攻击 phase
是否全相位保证检测
```

优先只消费 T0-5 已有窗口边界做数学/脚本级推导。不得为每个候选 `P` 跑一套 HSPICE。

只有当多个相邻 probe 的真实电源/复位/内部节点状态会发生重叠，导致“单 probe 窗口平移叠加”明显不再成立时，才允许增加极少量多 probe 晶体管级验证，并必须先写出为什么纯窗口叠加无法回答问题。

## 12.2 必须同时给出两个不同的时序限制

T0-6 不能只输出一个“400 MHz 是否足够”。必须分别输出：

### A. 物理覆盖要求

由攻击持续时间和相位窗口推导：

```text
Pmax_coverage = 满足目标 clean coverage / guaranteed detection 的最大 probe period
```

### B. 当前冻结单 probe 序列的非重叠实现下限

当前单 probe 关键时刻约为：

```text
S_CLK rise = 1.49 ns
Q1 sample = 3.79 ns
Q2 sample = 3.99 ns
reset assert = 4.19~4.20 ns
S_CLK fall = 4.49 ns
recovery end = 7.19 ns
```

若要求下一次 S_CLK rise 必须在本次 `recovery end` 之后，则当前冻结 one-shot 序列给出的 S_CLK-rise 到下一次 S_CLK-rise 非重叠下限约为：

```text
7.19 ns - 1.49 ns = 5.70 ns
```

这个 5.70 ns 是**当前已验证 one-shot 时序的实现参考下限**，不是未来 D0 永久不可缩短的物理极限。D0 若设计更紧凑的运行时 probe 序列，必须重新验证 reset/S_CLK/Q/recovery 时序。

## 12.3 400 MHz 必须这样判断

当前 400 MHz / 2.5 ns 是校准、所有权和配置控制时钟合同，不自动等于“每 2.5 ns 可以完成一次当前 one-shot probe”。

因此 T0-6 必须分别回答：

```text
1. 2.5 ns 周期从纯检测窗口覆盖角度是否满足目标攻击持续时间？
2. 当前 5.70 ns 级 one-shot 非重叠序列能否满足 Pmax_coverage？
3. 如果覆盖要求比当前 one-shot 可实现节拍更快，未来 D0 需要把运行时 probe 序列压缩到什么上限？
```

可能的结果：

```text
若 Pmax_coverage >= 当前可实现非重叠 probe period：
  当前序列原则上可实现，T0 可向 GO 收敛。

若 Pmax_coverage < 当前可实现非重叠 probe period，但传感器物理窗口本身清楚：
  T0 = CONDITIONAL_GO；
  条件：D0 必须实现 <= Pmax_coverage 的更紧凑运行时 probe 序列，并重新做时序验证。

若即使非常短的 P 也因窗口/ambiguous 结构无法形成目标覆盖：
  才考虑 T0 NO-GO。
```

T0 不得自行设计 DLL、高速时钟、分频器或完整检测 FSM。

## 12.4 T0-6 输出

至少生成：

```text
cadence/coverage_vs_probe_period.csv
cadence/cadence_summary.json
contract/T0_DOWNSTREAM_D0_TIMING_CONTRACT.json
```

下游合同至少明确：

```text
目标威胁持续时间
目标覆盖口径（clean coverage / guaranteed）
Pmax_coverage
400 MHz/2.5 ns 的覆盖资格
当前 one-shot 5.70 ns 参考实现约束
D0 是否需要更紧凑运行时 probe 序列
VDD<0.80 V fail-safe 需求
```

---

# 13. T0-7 —— `<0.80 V` 严重欠压的失效保护语义【需求已发布，保持冻结】

当前正式精确时序检测只在：

```text
VDD_MONITORED >= 0.80 V
```

范围内讨论。

低于 0.80 V 时：

- 传感路径标准单元可能进入未正式表征区；
- DFF 行为不能继续当作精确时间比较器；
- 不得通过少量深跌落波形宣称精确 Vtrip 能力。

D0 必须采用：

```text
heartbeat
stuck-Q
timeout
无有效检测结果
```

等失效保护语义，而不是继续依赖精细 timing trip 数值。

T0 只定义需求，不实现 RTL。

---

# 14. T0-8 —— 正式论文级证据、图和最终 Gate

T0-8 必须在 T0-5/T0-6 完成后重新生成当前正式图、报告和下游合同；此前因历史 T0-4 STOP 生成的 blocked 图/占位文件不得直接复用为最终结论。

## 14.1 必须形成的核心图

至少形成以下五类正式图：

### 图 T0-1：代表性瞬态波形

同一时间轴显示：

```text
VDD_MONITORED
XOR 有效脉冲/窗口
采样 CK
真实 Q
```

清楚标注下降、保持、恢复、相位以及恢复沿模糊点的解释。

### 图 T0-2：单 probe 时间敏感窗口

横轴为攻击相位，显示：

```text
CLEAN_Q1
STABLE_Q0
RECOVERY_EDGE_AMBIGUOUS
OTHER_INVALID_AMBIGUOUS
```

并标注所有连续区间和边界。

### 图 T0-3：跌落深度—持续时间二维检测边界

至少分别展示 0.95 V 和 1.10 V；负控制不得被画成“失败 minimum”。

### 图 T0-4：跌落深度—最短 clean-Q1 持续时间

同一基准电压下比较 L1/L2/L3，特殊恢复沿模糊 bracket 必须显式标记。

### 图 T0-5：probe period—时间覆盖率/保证检测关系

直接支撑未来 D0 的检测节拍选择，并同时标出 2.5 ns 控制时钟参考和当前约 5.70 ns one-shot 非重叠参考。

## 14.2 绘图环境

继续统一使用现有 Miniconda `DL` 环境和 matplotlib。

正式图：

```text
PDF
600 dpi PNG
```

并生成 manifest，至少记录：

```text
原始 CSV/JSON hash
绘图脚本 hash
Python 路径
matplotlib 版本
conda_env=DL
图尺寸/DPI
```

禁止手工编辑正式图片。

## 14.3 纠偏历史的论文处理

正式 T0 性能曲线只能消费纠偏后的本地 VDD 归一化场景和 T0-4 corrected GO 证据。

旧 62 个固定高电平 T0-2 场景、旧 T0-4 STOP 占位结果、被 supersede 的 blocked phase/cadence 文件只能作为方法学审计证据，不得进入正式性能曲线。

---

# 15. T0 最终判定标准

## 15.1 T0 = GO

至少满足：

1. T0-2 纠偏后的长脉冲 transient 与 M0 static Q0/Q1 ordering 一致；
2. T0-3/T0-5 证明 0.95 V 和 1.10 V 都存在完整、可解释、可重复的瞬态检测窗口；
3. 六个 trip-qualified margin 的 `DeltaV -> minimum clean-Q1 duration` 已提取；
4. T0-5 已量化 CLEAN_Q1、Q0 盲区和恢复沿模糊区；
5. 动态 Q 判决使用各采样时刻本地 `VDD_MONITORED`；
6. 不存在大量无法解释的“更深/更长反而稳定漏检”反转；
7. 至少针对一个明确瞬态威胁类别，可以推导出可实现的 `Pmax_coverage`；
8. 当前可实现 probe 序列能够满足该 `Pmax_coverage`，或者已有等价实现证据；
9. 已区分“最佳相位可检测”“clean coverage”“ambiguous 区”“全相位保证检测”；
10. `<0.80 V` 已明确转为失效保护语义；
11. 论文级图、机器可读合同和 provenance 完整；
12. 没有无意义重跑 H0/M0/M1/M1-T/T0-2/T0-3/T0-4 已完成物理证据。

## 15.2 T0 = CONDITIONAL_GO

如果：

```text
传感器物理瞬态检测机制成立；
T0-5 的单 probe 时间窗口清楚；
T0-6 可以给出明确 Pmax_coverage；
但当前已验证 one-shot probe 序列不能以该周期无重叠重复；
```

则允许：

```text
T0 = CONDITIONAL_GO
```

条件必须明确写为：

> 未来 D0 必须实现不慢于 T0-6 所要求 `Pmax_coverage` 的运行时 probe 序列，并重新验证其 reset/S_CLK/Q 双采样/恢复时序。

不得简单把“400 MHz 不够”写成模糊条件，也不得把当前 400 MHz 控制时钟直接等价为 runtime probe rate。

## 15.3 T0 = NO-GO / STOP

以下任一出现才允许真正停止进入 D0：

```text
纠偏后的 long-pulse 无法重现 M0 静态方向；
真实 DFF Q 与预期物理机制持续矛盾；
完整 phase 行为无法形成可重复边界；
动态相位场景主要由不可解释 ambiguous 状态构成；
amplitude-duration 出现大量不可解释反转；
即使最佳 phase + 足够长 pulse 也无法形成稳定 clean detection 区；
即使把 probe period 明显缩短仍无法得到目标覆盖；
发现新的、可重复的真实 dff_ck 二次时钟且会破坏检测语义。
```

NO-GO 后先检查瞬态物理感知机制、采样判决和 deck，不得用更复杂数字 FSM 掩盖物理问题。

---

# 16. 仿真预算与“非必要不重跑”规则

Codex 必须遵守以下优先级：

```text
已有 JSON/CSV/报告可回答 -> 直接复用，仿真数 0
已有 raw run 可重解析 -> 重解析，仿真数 0
仅 source_hash 变化且电气 deck 等价 -> 复用，仿真数 0
只缺后处理/摘要/证据取代标记 -> 只做后处理，仿真数 0
只有新的瞬态物理问题无法由已有证据回答 -> 才允许新增 HSPICE
```

禁止为了“保险”“回归”“顺便确认”重新执行：

```text
完整 startup calibration
M0 local surface / trip sweep / M0-E
M1 RTL/SDF / M1-T STA
RF 系列
XA 全链路
T0-2 纠偏四点 / 正式十二点
T0-3 已有相位点
T0-4 238 个正式历史场景
T0-4 已完成的四个唯一诊断电气场景
```

特别规定：

> **修改 `run_t0_transient_droop_characterization.py` 导致源码哈希变化，不构成重跑任何已完成 T0 电气场景的理由。应先做电气参数投影和 deck 等价复用。**

每一阶段报告必须明确记录：

```text
本阶段新增 HSPICE 场景数
复用旧场景数
电气等价复用场景数
仅重解析场景数
诊断测量修订重跑数（如有）
禁止流程新增运行数
```

如果某一步必须重跑旧实验，报告中必须写清楚**为什么现有原始证据不能回答当前问题**，否则视为流程违规。

---

# 17. 推荐任务目录

```text
delay_chain/ftc/analysis/t0_transient_droop/
├── baseline/
│   └── frozen_input_sha256.json
├── contract/
│   ├── T0_TRANSIENT_THREAT_CONTRACT.json
│   └── T0_DOWNSTREAM_D0_TIMING_CONTRACT.json
├── correction/
│   ├── constant_low_equivalence_audit.json
│   ├── correction_audit.json
│   ├── four_point_results.csv
│   ├── four_point_summary.json
│   ├── formal_12_results.csv
│   ├── formal_12_summary.json
│   └── legacy_62_scenarios_marker.json
├── long_pulse_consistency/
│   └── 历史纠偏前结果及 superseded 标记
├── phase_window/
│   ├── phase_window.csv
│   └── summary.json
├── amplitude_duration/
│   ├── amplitude_duration.csv
│   ├── minimum_duration_boundary.csv
│   ├── anomaly_diagnostics.json
│   └── summary.json
├── t0_4e_closure/
│   ├── authoritative_evidence_hashes.json
│   ├── stale_stop_supersession.json
│   └── electrical_reuse_contract.json
├── phase_coverage/
│   ├── phase_coverage.csv
│   └── phase_coverage_summary.json
├── cadence/
│   ├── coverage_vs_probe_period.csv
│   └── cadence_summary.json
├── figures/
├── scripts/
└── reports/
    ├── T0_GATE_STATUS.json
    └── FTC_T0_TRANSIENT_DROOP_CHARACTERIZATION.md
```

大体积 HSPICE deck/listing/waveform 放 task-owned run 目录并忽略；提交机器可读摘要、代表性证据、正式图和可重复脚本。

---

# 18. Codex 严格逐阶段执行顺序

当前正确执行序列更新为：

```text
T0-0   瞬态威胁 / 相位 / 波形合同                         已完成
  ↓
T0-1   当前 FTC 瞬态单次检测 runner                      已完成并纠偏
  ↓
T0-2   本地 VDD 归一化后的长脉冲静态→瞬态一致性          CORRECTED PASS
  ↓
T0-2E  纠偏证据闭合 + 旧 T0-2 STOP superseded             PASS，0 HSPICE
  ↓
T0-3   两个 L2 代表点相位敏感窗口                          GO
  ↓
T0-4   六个 margin 自适应 DeltaV→minimum clean-Q1 duration GO
  ↓
T0-4E  T0-4 authority + 旧 STOP 清理 + 电气等价复用        ← 当前下一步，0 HSPICE
  ├─ FAIL -> 只修证据/复用逻辑，不运行新物理扫描
  ↓ PASS
T0-5A  两个 L2：边界脉冲 + 3000 ps 长脉冲完整单 probe 窗口
  ├─ FAIL -> STOP 在 T0-5A，不执行 T0-5B
  ↓ GO
T0-5B  0.95/L3 与 1.10/L1 两个特殊恢复沿边界完整相位
  ↓
T0-6   用 T0-5 窗口数学反推 Pmax_coverage / cadence
  ↓
T0-7   保持 <0.80 V fail-safe 下游需求
  ↓
T0-8   重建论文级图 + 正式报告 + D0 合同 + 最终 Gate
```

任何后续入口都不得隐式重新调用 T0-2/T0-3/T0-4 已完成的 HSPICE。

---

# 19. 宏观防跑偏原则

Codex 在整个后续 T0 必须始终遵守以下方向：

> **T0-4 已经纠偏并通过，当前不再排查旧 T0-4，也不允许因为 runner 修改重新跑其 238 个正式场景。下一步先用零 HSPICE 的 T0-4E 把权威证据、旧 STOP 占位状态和跨源码哈希的电气等价复用彻底闭合，然后只用两个 L2 代表点完成真正左右封闭的单 probe 时间窗口；已有 T0-3 phase 点必须直接复用，只对未知左/右边界做自适应扩展。T0-5A 通过后才补 0.95/L3 和 1.10/L1 两个恢复沿特殊点。T0-6 优先完全基于 T0-5 窗口做周期数学映射，分别回答“物理覆盖允许的最大 probe period”和“当前 one-shot 序列可实现的非重叠节拍”，不能把 400 MHz 控制时钟直接等价为运行时 probe rate。只有现有证据无法回答的新物理问题才允许新增 HSPICE。**

---

# 20. T0 结束后的唯一正确下一步

只有 T0 最终给出 GO 或带明确 cadence 条件的 CONDITIONAL_GO，才允许进入：

```text
D0：运行时检测状态机
```

D0 才负责：

```text
运行时 reset/S_CLK 序列
probe cadence
Q 双采样判决
报警锁存/清除
状态寄存器
低于 0.80 V 的 heartbeat / stuck-Q / timeout 失效保护
```

总体路线冻结为：

```text
H0     校准→检测所有权切换                         PASS
 ↓
M0     静态检测裕量 / 静态触发电压                 CONDITIONAL_GO（仅范围边界）
 ↓
M1     精确检测配置 / 安全装载                      GO
 ↓
M1-T   检测配置时序证据闭合                         PASS
 ↓
T0-2   瞬态长脉冲静态一致性                         CORRECTED PASS
 ↓
T0-2E  纠偏证据闭合                                 PASS
 ↓
T0-3   相位敏感窗口                                 GO
 ↓
T0-4   深度×最短 clean-Q1 持续时间                  GO
 ↓
T0-4E  证据闭合 / 旧 STOP 清理 / 电气等价复用       当前下一步
 ↓
T0-5   完整单 probe 时间覆盖                         待执行
 ↓
T0-6   最大 probe period / cadence                  待执行
 ↓
T0-7   <0.80 V 失效保护需求                         已冻结
 ↓
T0-8   论文证据 / 最终 Gate / D0 合同               待执行
 ↓
D0     运行时检测状态机 / 判决 / 报警 / 失效保护
 ↓
V0/V1  完整控制器 + 混合信号 + 晶体管级瞬态闭环
```