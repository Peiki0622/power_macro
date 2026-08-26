# FTC PD1 理想跨电源域接口契约与收口逐步骤推进计划

**仓库：** `Peiki0622/power_macro`  
**目标分支：** `main`  
**P10 冻结基线：** `179404d95522afcd93c5b824d7094e47c55c9aab`  
**PD1 首轮静态执行提交：** `c9818f7a0fe11b76d02d814d971dda253cffd324`  
**本计划状态：** 对原 PD1 计划的直接修订；Codex 必须从首轮 `PD1 = 证据缺口停止` 结果继续收口，不得从头重跑。  
**阶段定位：** P10 之后、校准到检测所有权切换之前。  

---

# 0. 本次修订的核心决定

本项目不再把“寻找、选择、验证真实跨压标准单元”作为 PD1 的目标，也不再要求使用当前 SMIC40LL 工艺库证明真实电平转换、隔离、掉电保护和反向供电能力。

从本修订开始，PD1 的正式研究对象改为：

> **冻结一个理想的、电源感知的跨电源域接口抽象，使后续研究专注于 FTC_SENSOR、启动校准、检测裕量和电压跌落检测本身。**

真实物理跨压接口实现属于后续芯片物理集成问题，不属于本项目当前主线。

因此：

```text
PD1 研究范围内
--------------------------------
PD_CTRL / PD_SENSE 电源域划分
29 条跨域信号及方向
理想跨域接口逻辑语义
理想接口的电源感知高/低电平语义
现有 XA D2A/A2D 抽象参数
400 MHz 启动校准在该抽象下的时序与功能证据
深度跌落时“无效不能自动等于安全”的体系结构约束

PD1 研究范围外
--------------------------------
真实电平转换标准单元选择
真实隔离单元选择
真实跨压单元晶体管实现
跨压单元版图和寄生
真实掉电反向供电电流签核
真实接收器低压门限签核
UPF/CPF 电源意图实现
真实电源网和地网签核
```

首轮提交 `c9818f7...` 中的三个阻塞性证据缺口从本修订开始不再作为 PD1 的阻塞门，而是重新分类为“范围外物理集成限制”。

---

# 1. 最高优先级执行原则

## 1.1 非必要不得重跑上一阶段仿真

P10、RF6、RF8、RF9C、RF9D 已经形成有效证据。本次 PD1 修订只做静态收口。

默认预算必须保持：

```text
新晶体管级瞬态仿真    = 0
新数字逻辑仿真        = 0
新数模混合仿真        = 0
重新综合              = 0
重新静态时序分析      = 0
重新跑 RF6            = 0
重新跑 RF8            = 0
重新跑 RF9C           = 0
重新跑 RF9D           = 0
```

Codex 不得因为：

- 需要重新生成报告；
- 想得到更完整波形；
- 想确认旧结果；
- 想验证真实跨压接口；
- 想寻找更多 PMK 单元；

而重跑任何上一阶段 EDA 流程。

## 1.2 停止继续搜索真实跨压单元

从本修订开始，Codex 必须停止：

- 搜索更多电平转换单元；
- 搜索更多隔离单元；
- 遍历更多 PMK 电压组合；
- 试图证明 0.80 V 下真实跨压标准单元可用；
- 试图用单元名称推断掉电安全；
- 为跨压单元建立新的晶体管仿真。

首轮 PD1 已经得到的库调查结果只保留为历史审计证据，不再决定 PD1 最终门状态。

## 1.3 上游冻结边界继续不可修改

以下内容保持 P10 冻结：

```text
PD_SENSE
    完整冻结 FTC_SENSOR
    ├── 延迟/调节网络
    ├── 中调路径选择网络
    ├── 细调驱动/负载网络
    ├── 异或时序比较网络
    └── 传感器采样触发器
          │
        Q_FINAL

PD_CTRL
    ├── 中调/细调配置状态寄存器
    ├── 操作时序控制
    ├── Q 双采样与分类逻辑
    ├── 启动校准状态机
    └── 后续检测、裕量、报警逻辑
```

以下仍然冻结：

- 中调级数 16；
- 细调级数 10；
- 直接寄存温度计码结构；
- 传感器抽头 29；
- 异或网络留在 `PD_SENSE`；
- 传感器采样触发器留在 `PD_SENSE`；
- `Q_FINAL` 为唯一 SENSE→CTRL 返回状态；
- 启动校准算法；
- Q 双采样；
- 0.80 V -> M7/F6；
- 0.95 V -> M4/F6；
- 1.10 V -> M2/F9；
- 校准时钟 400 MHz；
- 周期 2.5 ns；
- 配置稳定时间 1 个校准周期；
- 当前局部探测动作周期 0/1/2/3/4/5/7。

本修订不得为了“让真实跨压单元容易实现”而修改上述任何内容。

---

# 2. 理想跨域接口的正式定义

本项目后续统一采用“理想电源感知接口抽象”。

## 2.1 `PD_CTRL -> PD_SENSE` 理想接口

适用于：

```text
medium_therm[15:0]
fine_therm[9:0]
sense_dff_reset
sense_s_clk
```

理想接口语义：

1. 控制域逻辑 `0` 在传感域映射到 `VSS_LOCAL`；
2. 控制域逻辑 `1` 在传感域映射到当前 `VDD_MONITORED / VDD_LOCAL`；
3. 不允许把 `VDD_CTRL` 的模拟高电平直接灌入 `PD_SENSE`；
4. 不增加新的、需要单独签核的真实跨压单元传播延迟；
5. 不增加新的、需要单独签核的跨压单元抖动和偏差；
6. 不产生额外反向供电；
7. 接口不会改变冻结的温度计码、复位和 `sense_s_clk` 功能语义；
8. 具体电压转换波形参数以现有 `bridge_contract.json` 和 RF9C/RF9D 已验证接口抽象为权威来源，不得另行虚构一套参数。

这里的“理想”含义是：

> **不再引入一个新的物理跨压标准单元作为研究变量。**

它不等于数学上的零上升时间，也不允许 Codex随意改变现有 XA 接口抽象参数。

## 2.2 `PD_SENSE -> PD_CTRL` 的 `Q_FINAL` 理想返回接口

`Q_FINAL` 是 `PD_SENSE` 内传感器采样触发器已经锁存的状态，而不是异或窄脉冲。

返回接口语义：

1. 使用现有 XA A2D 归一化门限作为本项目验证抽象；
2. 当前已有门限定义应从 `bridge_contract.json` 原样提取并冻结，不得自行更改；
3. 已知当前抽象使用相对于 `VDD_LOCAL` 的低/高门限比例时，应明确注明这是验证抽象而不是特定物理接收器规格；
4. 不增加新的真实接收器传播延迟；
5. 不引入反向供电；
6. 当 `PD_SENSE` 已低到传感器本身无法保证 `Q_FINAL` 有效时，`Q_FINAL` 不得被体系结构自动解释为“安全”。

第 6 项保留为后续检测控制器设计约束，但真实接收器的低压失效行为不再阻塞 PD1。

---

# 3. 首轮三个证据缺口的重新分类

Codex 必须更新首轮 `PD1_EVIDENCE_GAPS.md`，不得继续把以下三项作为 PD1 阻塞项。

## 3.1 原 `PD1-GAP-001`

原问题：真实跨压接口的多电源延迟、边沿、摆幅和相对偏差未表征。

新分类：

```text
范围外物理集成限制
非 PD1 阻塞项
```

理由：本项目采用现有理想电源感知接口抽象，不引入真实跨压单元延迟作为研究变量。

## 3.2 原 `PD1-GAP-002`

原问题：严重跌落/掉电时真实接口的反向供电和输入静态电流未证明。

新分类：

```text
范围外物理集成限制
非 PD1 阻塞项
```

本项目模型假设：

```text
理想接口不向 PD_SENSE 注入额外供电电流
不存在由跨域接口导致的反向供电
```

报告必须明确这是模型假设，不得写成“真实工艺已经完成反向供电签核”。

## 3.3 原 `PD1-GAP-003`

原问题：低压/掉电时真实 `Q_FINAL` 接收器门限和无响应行为未证明。

新分类：

```text
真实物理接收器门限 = 范围外
验证接口门限 = 使用现有 XA 抽象
深度跌落无响应语义 = 后续检测控制器约束
非 PD1 阻塞项
```

---

# 4. 当前 29 条跨域信号继续冻结

Codex 不得重新发明跨域边界。

正式清单仍为：

```text
PD_CTRL -> PD_SENSE

sense_s_clk        1
sense_dff_reset    1
medium_therm      16
fine_therm        10
--------------------
总计              28

PD_SENSE -> PD_CTRL

Q_FINAL             1
--------------------
总计               1
```

全部跨域：

```text
29
```

四类接口保持：

```text
第一类：26 条慢速配置线
第二类：1 条复位控制线
第三类：1 条传感器采样时钟线
第四类：1 条 Q_FINAL 锁存状态返回线
```

首轮 `crossing_inventory.json` 如果已正确，无需重新生成数据；只需确保最终报告引用它。

---

# 5. 修正首轮时序报告中的概念性表述

这是本次继续执行中必须完成的修正。

首轮脚本把历史：

```text
0.49 ns
2.30 ns
0.20 ns
...
```

写成当前 400 MHz 的 `observed margin` 或当前窗口，这是不准确的。

这些数值来自：

```text
analysis/cycle_protocol_event_order_v2/exact_path_event_order_audit.json
```

其正确语义是：

> **从历史精确物理路径提取、被 400 MHz 重量化时继续保留的物理最小事件间隔要求。**

不得再把它们称为当前 400 MHz 的实际事件间隔或当前 observed margin。

## 5.1 当前有效 400 MHz 名义事件时刻

Codex 必须从：

```text
refrequency/timing_contract/cycle_timing_contract_refrequency.json
```

读取当前 active schedule：

```text
RESET_RELEASE_COMPLETE 约 0.01 ns
S_CLK_RISE              2.50 ns
Q_SAMPLE_1              5.00 ns
Q_SAMPLE_2              7.50 ns
RESET_ASSERT_START     10.00 ns
RESET_ASSERT_COMPLETE  10.01 ns
S_CLK_FALL             12.50 ns
RECOVERY_DONE          17.50 ns
```

不得重新跑任何仿真获取这些值。

## 5.2 当前 400 MHz 名义事件间隔

静态计算：

```text
RESET_RELEASE_COMPLETE -> S_CLK_RISE     约 2.49 ns
S_CLK_RISE -> Q_SAMPLE_1                 2.50 ns
Q_SAMPLE_1 -> Q_SAMPLE_2                 2.50 ns
Q_SAMPLE_2 -> RESET_ASSERT_START         2.50 ns
RESET_ASSERT_COMPLETE -> S_CLK_FALL      约 2.49 ns
S_CLK_FALL -> RECOVERY_DONE              5.00 ns
```

## 5.3 物理最低事件间隔要求

从历史精确物理事件顺序证据读取：

```text
RESET_RELEASE_COMPLETE -> S_CLK_RISE     约 0.49 ns
S_CLK_RISE -> Q_SAMPLE_1                 约 2.30 ns
Q_SAMPLE_1 -> Q_SAMPLE_2                 约 0.20 ns
Q_SAMPLE_2 -> RESET_ASSERT_START         约 0.20 ns
RESET_ASSERT_START -> RESET_ASSERT_COMPLETE 约 0.01 ns
RESET_ASSERT_COMPLETE -> S_CLK_FALL      约 0.29 ns
S_CLK_FALL -> RECOVERY_DONE              约 2.70 ns
```

这些是“物理最小需求”，不是新接口延迟预算。

## 5.4 400 MHz schedule 相对物理最低需求的静态裕量

Codex 必须静态生成并明确标注：

```text
复位释放 -> S_CLK 上升        约 +2.00 ns
S_CLK 上升 -> Q_SAMPLE_1      约 +0.20 ns
Q_SAMPLE_1 -> Q_SAMPLE_2      约 +2.30 ns
Q_SAMPLE_2 -> RESET_ASSERT    约 +2.30 ns
RESET_COMPLETE -> S_CLK_FALL  约 +2.20 ns
S_CLK_FALL -> RECOVERY_DONE   约 +2.30 ns
```

`RESET_ASSERT_START -> RESET_ASSERT_COMPLETE` 的 0.01 ns 属于已有事件完成定义，不要把它误写成“可供真实电平转换器使用的裕量”。

必须特别注明：

> `S_CLK_RISE -> Q_SAMPLE_1` 的约 +0.20 ns 是当前 schedule 相对既有物理最小事件间隔最紧的一项；但在本修订采用理想接口抽象后，不再要求从这 0.20 ns 中为一个新的真实跨压单元分配延迟。

## 5.5 当前控制器输入路径证据继续保留

必须引用现有 RF8 `q_final_sampling_path.rpt`：

```text
数据到达约 0.89 ns
要求时间约 2.39 ns
建立裕量约 +1.50 ns
```

该证据只证明当前抽象接口下 `q_final` 到控制器采样路径成立，不得外推成真实跨压接收器签核。

---

# 6. 不再执行真实工艺库接口审计

首轮生成的：

```text
library_audit/candidate_interface_cells.json
library_audit/candidate_capability_matrix.json
library_audit/library_evidence_limitations.md
```

全部保留作为历史探索记录，不删除。

但是从本修订开始：

- 它们不参与 PD1 最终 GO/STOP；
- 不要求补搜更多库；
- 不要求补齐真实跨压候选；
- 不要求证明 0.80 V 真实单元；
- 不要求生成新的候选能力矩阵。

Codex 应在 `library_evidence_limitations.md` 或一个新的范围说明中增加明确声明：

> 工艺跨压标准单元的完整可实现性不属于本阶段研究范围；现有库搜索只保留为历史探索，不再阻塞理想接口抽象下的 PD1 收口。

原计划要求的 `library_search_manifest.json` 不再是 PD1 最终 GO 的必要交付项。如果已有文件可静态保留则保留；不存在时不需要为了它重新搜索库。

---

# 7. 掉电和反向供电改为“模型假设 + 集成限制”

首轮 `power_safety` 结果不能删除，但必须修订语义。

## 7.1 本项目理想接口模型

必须明确记录：

```text
理想 CTRL->SENSE 接口：
不向 PD_SENSE 注入额外供电电流

理想 Q_FINAL 返回接口：
不反向给 PD_SENSE 供电

PD_SENSE 电压：
仅由 VDD_MONITORED / VDD_LOCAL 定义
```

因此后续 droop 仿真中，接口不会人为抬高被监测电源。

## 7.2 不允许过度声称

报告同时必须写：

```text
真实工艺反向供电安全 = 未签核 / 范围外
真实掉电静态电流     = 未签核 / 范围外
```

这两个“未签核”不再等于 PD1 失败。

---

# 8. Codex 本轮只需执行的继续步骤

Codex 不得重新执行整个旧 PD1-0～PD1-12。只执行下面的修订收口步骤。

## PD1-R0 —— 回读当前状态，不做新 EDA

只读回读：

```text
P10 freeze
c9818f7 首轮 PD1 结果
400 MHz active timing contract
RF8 q_final sampling report
RF9C/RF9D final summary
bridge_contract.json
```

确认上游未改变。

如果冻结 RTL、传感器、400 MHz handoff 已发生未经授权修改，停止。

## PD1-R1 —— 建立理想接口总契约

新增建议文件：

```text
delay_chain/ftc/controller/pd1_power_domain_interface/
  architecture/ideal_power_aware_interface_contract.json
```

至少记录：

- 29 条 crossing；
- CTRL→SENSE 高电平跟随 `VDD_LOCAL`；
- CTRL→SENSE 低电平跟随 `VSS_LOCAL`；
- 无额外真实跨压单元延迟；
- 无额外跨压单元抖动/偏差；
- 无反向供电；
- Q_FINAL 使用现有 XA A2D 抽象；
- 真实物理跨压实现明确标记为范围外。

## PD1-R2 —— 修正四类 crossing contract

更新：

```text
crossings/configuration_crossing_contract.json
crossings/reset_crossing_contract.json
crossings/sclk_crossing_contract.json
crossings/qfinal_return_contract.json
```

将原来“必须找到/验证真实 power-safe cell”改成：

```text
本项目采用冻结的理想电源感知接口抽象
真实物理单元要求为芯片集成限制
```

不得改变 29 条 crossing，也不得改变传感器边界。

## PD1-R3 —— 修正时序预算报告

更新：

```text
timing_budget/existing_evidence_extraction.json
timing_budget/configuration_timing_budget.json
timing_budget/reset_to_sclk_timing_budget.json
timing_budget/sclk_to_qsample_timing_budget.json
timing_budget/qsample2_to_reset_timing_budget.json
timing_budget/end_to_end_timing_budget.json
```

必须完成第 5 节规定的语义修正：

```text
历史 0.49/2.30/0.20... = 物理最低事件间隔要求
400 MHz 当前 schedule    = 当前名义事件时刻
两者之差                 = schedule 相对最低要求的静态裕量
```

不得再把历史最小间隔写成当前 400 MHz observed margin。

本轮仍然不跑 RF6/RF9D。

## PD1-R4 —— 重分类原三个证据缺口

更新：

```text
reports/PD1_EVIDENCE_GAPS.md
power_safety/power_safety_evidence_gap.json
power_safety/back_powering_risk_matrix.json
```

原 `PD1-GAP-001/002/003` 全部保留编号以便历史追踪，但状态改为：

```text
NON_BLOCKING_OUT_OF_SCOPE_PHYSICAL_INTEGRATION_LIMITATION
```

并说明为什么不再阻塞 PD1。

## PD1-R5 —— 修订接口架构决定

更新：

```text
architecture/selected_interface_architecture.json
architecture/architecture_decision.md
```

最终架构必须表达为：

```text
                   PD_CTRL
              稳定/可信数字域
                     │
       28 路理想电源感知接口
                     │
                     ▼
                  PD_SENSE
                VDD_MONITORED
                     │
             完整冻结 FTC_SENSOR
                     │
                   Q_FINAL
                     │
          1 路理想状态返回接口
                     │
                     ▼
                   PD_CTRL
                  Q 双采样
```

必须继续明确：

```text
XOR ∈ PD_SENSE
capture DFF ∈ PD_SENSE
Q_FINAL 是唯一返回状态
```

## PD1-R6 —— 发布新的最终门状态

更新：

```text
reports/PD1_GATE_STATUS.json
reports/PD1_FINAL_REPORT.md
```

建议最终机器可读结论：

```text
PD1 = GO_WITH_IDEAL_POWER_AWARE_INTERFACE_ABSTRACTION
```

中文结论：

```text
PD1 理想跨电源域接口契约 = 通过
```

同时必须并列写出：

```text
真实物理跨压接口实现签核 = 范围外
```

不得把“范围外”写成“已通过物理签核”。

---

# 9. 新的 PD1 最终门条件

在本修订后的研究范围内，只有以下项目是 PD1 GO 的必要条件。

## 必须通过

1. P10 冻结边界未改变；
2. 29 条跨域信号清单未改变；
3. `PD_SENSE` 和 `PD_CTRL` 双电源域定义清楚；
4. 两域采用共地工作假设；
5. 理想 CTRL→SENSE 接口高电平随 `VDD_LOCAL`；
6. 理想接口不向 `PD_SENSE` 注入额外供电；
7. `Q_FINAL` 继续作为锁存状态返回；
8. A2D 门限继续采用现有验证抽象，并明确不等于真实工艺门限；
9. 当前 400 MHz active schedule 与物理最低事件顺序要求静态一致；
10. RF8 当前 `q_final` 数字采样路径保持正裕量；
11. RF9C/RF9D 当前理想/抽象接口下三电压启动校准继续为已有 GO 证据；
12. 冻结传感器未修改；
13. 启动校准算法未修改；
14. 400 MHz 校准时序未修改；
15. 未进行未经授权的上一阶段仿真重跑；
16. 最终报告明确真实跨压物理实现是范围外限制。

## 不再是阻塞条件

以下内容从本修订开始不再决定 PD1 GO：

```text
是否找到 0.80 V 合格真实跨压标准单元
是否有真实跨压单元的延迟表
是否有真实掉电注入电流规格
是否完成真实反向供电签核
是否完成真实 Q_FINAL 接收器低压门限签核
```

---

# 10. 最终报告必须使用的结论边界

允许写：

> 本项目已完成 `PD_CTRL` 与 `PD_SENSE` 的双电源域架构定义，并在现有数模混合验证中采用理想电源感知跨域接口。控制域逻辑高电平在传感域侧映射至本地 `VDD_MONITORED`，返回状态通过现有归一化 A2D 门限送回可信控制域。在该接口抽象下，冻结的 400 MHz 启动校准闭环证据保持有效。

允许写：

> 真实电平转换、隔离、掉电保护和反向供电控制属于芯片物理集成实现范围，本项目当前不对特定 SMIC40LL 跨压单元做签核。

禁止写：

```text
真实 level shifter 已 signoff
真实 power-off safety 已证明
真实 back-powering 为零
真实 0.80 V receiver 已验证
```

除非未来另开独立物理集成阶段并获得真实证据。

---

# 11. 本轮结束后允许进入的下一阶段

一旦：

```text
PD1 理想跨电源域接口契约 = 通过
```

就允许进入下一阶段：

> **校准到检测的原子化控制权切换设计。**

该阶段再定义：

- 启动校准何时释放传感器控制权；
- 检测逻辑何时接管；
- 中调/细调校准码如何冻结；
- 传感器控制多路选择如何避免双驱动；
- 校准状态和检测状态之间如何安全切换。

PD1 不提前实现这些功能。

---

# 12. Codex 最终执行顺序摘要

```text
已有 c9818f7 首轮 PD1 证据缺口停止
                │
                ▼
PD1-R0
只读回读，不重跑 EDA
                │
                ▼
PD1-R1
冻结理想电源感知接口契约
                │
                ▼
PD1-R2
修正四类 crossing contract
                │
                ▼
PD1-R3
修正 400 MHz 时序预算语义
                │
                ▼
PD1-R4
三个旧 GAP 重分类为非阻塞范围外限制
                │
                ▼
PD1-R5
冻结理想接口架构决定
                │
                ▼
PD1-R6
发布新的 PD1 最终门
                │
                ▼
PD1 = GO_WITH_IDEAL_POWER_AWARE_INTERFACE_ABSTRACTION
```

本轮严禁：

```text
重跑 RF6
重跑 RF8
重跑 RF9C
重跑 RF9D
重新综合
重新 STA
重新搜索跨压工艺单元
新增跨压晶体管仿真
修改 FTC_SENSOR
修改启动校准算法
修改 400 MHz timing contract
```

本计划的目标是**收口 PD1，而不是把项目变成跨压标准单元开发项目**。
