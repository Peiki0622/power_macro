# FTC PD1 物理电源域跨界接口契约逐步骤推进计划

**仓库：** `Peiki0622/power_macro`  
**目标分支：** `main`  
**计划建立时基线提交：** `179404d95522afcd93c5b824d7094e47c55c9aab`  
**阶段定位：** P10 之后、校准到检测所有权切换之前。  
**阶段目标：** 在不修改已冻结传感器、启动校准算法和 400 MHz 校准时序的前提下，把 `PD_CTRL` 与 `PD_SENSE` 之间 29 条跨电源域信号的物理电气要求、掉电行为、端到端时序预算和工艺可实现性定义成可审计契约。

---

# 0. 执行总原则

本计划由 Codex 逐步骤执行，但必须遵守以下最高优先级原则。

## 0.1 非必要不得重跑上一阶段仿真

P10 已经完成，RF6、RF8、RF9C、RF9D 已经形成有效证据。本阶段首先、并且尽可能完全依赖已有证据。

默认执行预算：

```text
晶体管级瞬态仿真      = 0
数字逻辑仿真          = 0
数模混合仿真          = 0
重新综合              = 0
重新静态时序分析      = 0
```

允许的工作：

- 回读既有报告、网表、时序交接文件和仿真结果；
- 对既有文件计算哈希；
- 静态解析网表、模型、库文件、延迟标注文件和约束文件；
- 编写只读审计脚本；
- 计算跨域时序预算；
- 调查工艺库中可能存在的跨电压接口单元；
- 形成表格、矩阵、契约和阶段结论。

禁止 Codex 因为“更方便”“想确认一下”“需要更完整波形”而自动重跑：

- RF6 三电压传感器晶体管仿真；
- RF8 综合与静态时序分析；
- RF9A/RF9B 数字验证；
- RF9C 数模混合无延迟标注验证；
- RF9D 数模混合完整延迟标注验证；
- 历史 1 GHz 失败路径；
- P10 之前任何已接受的校准仿真。

如果某个关键结论无法从已有证据和静态模型中得到，必须：

1. 明确写出缺失的具体物理量；
2. 说明为什么已有证据不能回答；
3. 说明该缺口是否阻塞阶段结论；
4. 生成“证据缺口停止报告”；
5. 停止在对应门点。

**不得自行启动新的瞬态仿真补缺口。**

只有后续得到单独明确授权，才允许针对已登记缺口设计最小化的新验证，而且不得演变成重新扫上一阶段全部场景。

## 0.2 上游冻结边界不可修改

以下内容已在 P10 冻结，本计划没有修改权限：

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

以下同样冻结：

- 中调级数 16；
- 细调级数 10；
- 直接寄存温度计码结构；
- 传感器抽头 29；
- 异或网络与传感器采样触发器的位置；
- 两次独立粗调探测；
- 首个双低粗调边界；
- 恰好回退两个中调配置步且中间不探测；
- 细调扫描规则；
- 细调边界后加一档保护码；
- 独立保持确认；
- Q 双采样；
- 0.80 V -> M7/F6；
- 0.95 V -> M4/F6；
- 1.10 V -> M2/F9；
- 校准时钟 400 MHz；
- 周期 2.5 ns；
- 配置稳定时间 1 个校准周期；
- 当前局部探测动作周期 0/1/2/3/4/5/7。

如果 PD1 发现接口无法满足这些冻结条件，正确动作是报告架构冲突并停止，而不是偷偷修改上游设计。

## 0.3 不得把现有数模接口抽象误写成真实物理实现

现有数模混合验证中的数字到模拟转换和模拟到数字转换只属于验证抽象。

本阶段不得声称：

- 已经实现真实电平转换单元；
- 已经完成真实跨域接口版图；
- 已经完成电源意图文件；
- 已经完成物理电网；
- 已经证明目标域掉电时不存在反向供电；
- 已经完成深度电压跌落下返回接口签核。

PD1 的任务是形成“物理接口必须满足什么”的契约，并证明工艺实现具有可行候选，而不是把验证抽象当成物理签核。

---

# 1. P10 冻结输入和权威证据

Codex 必须首先只读回读并记录以下文件。

## 1.1 P10 总状态和电源域冻结

```text
delay_chain/ftc/controller/reports/FTC_CONTROLLER_GATE_STATUS.json

delay_chain/ftc/controller/final_closure/freeze/
  POWER_DOMAIN_CONTRACT.json
  STARTUP_CALIBRATION_FROZEN_FILES.json
  STARTUP_CALIBRATION_EVIDENCE_BOUNDARY.md
  FTC_AUTONOMOUS_STARTUP_CALIBRATION_FINAL_ACCEPTANCE.md
```

其中 `POWER_DOMAIN_CONTRACT.json` 是本阶段电源域边界的首要权威来源。

## 1.2 当前有效 400 MHz 校准时序

```text
delay_chain/ftc/controller/refrequency/handoff/
  phase1_timing_handoff_refrequency.json
  rtl_timing_contract_audit.json
```

必须采用当前有效时序：

```text
校准时钟                 400 MHz
周期                     2.5 ns
配置稳定                  1 周期
RESET_RELEASE             0
S_CLK_RISE                1
Q_SAMPLE_1                2
Q_SAMPLE_2                3
RESET_ASSERT              4
S_CLK_FALL                5
RECOVERY_DONE             7
```

历史 1 GHz 时序只保留为历史证据，不得作为 PD1 当前接口预算的有效时序基线。

## 1.3 当前有效综合和时序证据

```text
delay_chain/ftc/controller/refrequency/synthesis/
  phase_refrequency_synthesis_results.json
  netlist/ftc_cal_controller_top_synth.v
  netlist/ftc_cal_controller_top_synth.sdc
  netlist/ftc_cal_controller_top_synth.sdf
```

重点复用现有已报告正裕量，不重新综合。

## 1.4 当前有效传感器和数模混合证据

```text
delay_chain/ftc/controller/analysis/phase9_autonomous_transistor_level/
  vcs_xa/inputs/ftc_sensor_frozen.sp

  vcs_xa_corrected/inputs/bridge_contract.json
  vcs_xa_corrected/src/ftc_sensor_ams_wrapper.sp
  vcs_xa_corrected/src/ftc_sensor_ams_stub.sv

delay_chain/ftc/controller/refrequency/verification/
  mixed_signal_no_sdf/
  mixed_signal_sdf/RF9D_TIMING_COMPOSED_MIXED_SIGNAL.json
```

还必须回读 RF6 三个当前有效晶体管场景证据，优先使用 `phase1_timing_handoff_refrequency.json` 中已经记录的 RF6 证据路径和哈希，不重复生成。

---

# 2. 本阶段专属工作目录

Codex 创建：

```text
delay_chain/ftc/controller/pd1_power_domain_interface/
├── baseline/
│   ├── pd1_baseline_manifest.json
│   └── immutable_input_sha256.json
├── power_states/
│   ├── supply_topology_contract.json
│   └── power_state_matrix.json
├── crossings/
│   ├── crossing_inventory.json
│   ├── configuration_crossing_contract.json
│   ├── reset_crossing_contract.json
│   ├── sclk_crossing_contract.json
│   └── qfinal_return_contract.json
├── timing_budget/
│   ├── existing_evidence_extraction.json
│   ├── configuration_timing_budget.json
│   ├── reset_to_sclk_timing_budget.json
│   ├── sclk_to_qsample_timing_budget.json
│   ├── qsample2_to_reset_timing_budget.json
│   └── end_to_end_timing_budget.json
├── library_audit/
│   ├── library_search_manifest.json
│   ├── candidate_interface_cells.json
│   ├── candidate_capability_matrix.json
│   └── library_evidence_limitations.md
├── power_safety/
│   ├── back_powering_risk_matrix.json
│   ├── unpowered_domain_behavior_contract.json
│   └── power_safety_evidence_gap.json
├── architecture/
│   ├── selected_interface_architecture.json
│   └── architecture_decision.md
└── reports/
    ├── PD1_GATE_STATUS.json
    ├── PD1_EVIDENCE_GAPS.md
    └── PD1_FINAL_REPORT.md
```

不得覆盖 P10、RF6、RF8、RF9C、RF9D 已有目录。

---

# 3. PD1-0 —— 基线冻结和一致性回读

## 目标

证明 Codex 执行 PD1 时读取的仍然是 P10 已冻结的启动校准和电源域基线。

## 执行步骤

1. 读取 P10 四个冻结文件和总门状态。
2. 读取 400 MHz 当前有效时序交接文件。
3. 读取当前有效综合网表、约束、延迟标注和综合结果。
4. 读取冻结传感器网表、数模混合封装、接口契约和 RF9D 结果。
5. 对所有被消费的权威输入计算哈希。
6. 与 P10 冻结清单中已有哈希能对应的项目进行比对。
7. 不存在对应哈希的文件允许作为“新增 PD1 只读输入”登记，但不得改写上游文件。

## 必须确认

```text
PD_SENSE = 完整冻结 FTC_SENSOR，包含异或网络和传感器采样触发器
PD_CTRL  = 独立稳定/可信数字域
跨域边界输出 = Q_FINAL
```

## 仿真预算

```text
全部新仿真 = 0
```

## 输出

```text
baseline/pd1_baseline_manifest.json
baseline/immutable_input_sha256.json
```

## 通过条件

```text
PD1 基线一致性 = 通过
```

若 P10 权威文件之间发生冲突，停止，不得自行修复 P10。

---

# 4. PD1-1 —— 29 条跨域信号逐条清点

## 目标

建立唯一、机器可审计的跨域信号清单。

## 权威期望

### `PD_CTRL -> PD_SENSE`

```text
sense_s_clk        1
sense_dff_reset    1
medium_therm      16
fine_therm        10
总计              28
```

### `PD_SENSE -> PD_CTRL`

```text
Q_FINAL             1
```

总跨域数量必须为：

```text
29
```

## 执行步骤

1. 从 P10 电源域契约读取预期清单。
2. 从数模混合封装和数字桩模块读取实际端口。
3. 从综合网表顶层和传感器接口读取实际连接。
4. 检查是否存在额外隐藏的电源、地或功能信号跨界。
5. 明确 VDD/VSS 不属于普通数字到模拟接口信号。
6. 为每一条跨域信号记录：方向、位宽、源域、目标域、功能类别、是否时序关键、是否需要掉电安全约束。

## 分类必须为

```text
第一类：26 条慢速配置线
第二类：1 条复位控制线
第三类：1 条传感器采样时钟线
第四类：1 条 Q_FINAL 状态返回线
```

## 输出

```text
crossings/crossing_inventory.json
```

## 停止条件

如果实际跨域数量不是 29，或存在 P10 未冻结的额外功能跨界，停止并报告。

---

# 5. PD1-2 —— 双电源和共地关系契约

## 目标

把“仿真域不同”正式转化为可供物理接口设计消费的供电关系。

## 当前工程目标

在没有目标芯粒集成规范与之冲突的前提下，PD1 采用：

```text
VDD_CTRL       = 独立稳定/可信数字电源
VDD_MONITORED  = 被监测电源，可发生电压跌落
VSS            = 两域共地
```

这里的“共地”是 PD1 当前接口设计前提，不等于已经完成物理地网签核。

## 执行步骤

1. 搜索仓库现有说明、约束、测试平台和电源定义，看是否存在与“共地双正电源”冲突的既有集成要求。
2. 如果无冲突，记录为 PD1 工作假设和后续宏接口要求。
3. 如果发现真实目标要求两个域地电位也独立，停止本计划；那将进入隔离接口问题，不能由普通跨电压接口计划继续处理。

## 输出

```text
power_states/supply_topology_contract.json
```

## 通过条件

```text
双电源共地接口前提 = 通过
```

---

# 6. PD1-3 —— 电源状态矩阵

## 目标

规定在 `PD_CTRL` 保持正常时，`PD_SENSE` 从正常到严重跌落甚至接近掉电的接口行为要求。

## 至少建立以下状态

```text
状态 0：PD_CTRL 正常，PD_SENSE 正常
状态 1：PD_CTRL 正常，PD_SENSE 正在上电
状态 2：PD_CTRL 正常，PD_SENSE 处于标称工作电压
状态 3：PD_CTRL 正常，PD_SENSE 中等电压跌落
状态 4：PD_CTRL 正常，PD_SENSE 严重电压跌落
状态 5：PD_CTRL 正常，PD_SENSE 接近掉电或掉电
```

本阶段不需要替后续检测阶段决定“多深的跌落一定可检测”，但必须规定接口最小安全语义。

## 每个状态必须审计

- `PD_CTRL -> PD_SENSE` 是否允许继续驱动；
- 是否存在反向供电风险；
- 目标域低电压时输入是否会产生大静态电流；
- `Q_FINAL` 是否仍可被视为有效逻辑；
- 无效 `Q_FINAL` 是否可能被错误解释为安全状态；
- 是否需要未来的隔离、保持、默认值或无响应检测。

## 输出

```text
power_states/power_state_matrix.json
```

---

# 7. PD1-4 —— 26 条配置线接口契约

## 目标

为：

```text
medium_therm[15:0]
fine_therm[9:0]
```

建立物理接口要求，但不改变直接温度计码结构。

## 功能特征

这些信号：

- 在配置更新时改变；
- 一次探测期间必须保持稳定；
- 不承担两个高速边沿之间的相对时间测量；
- 允许一定传播延迟；
- 不允许毛刺造成非法配置；
- 26 条之间的到达偏差必须被当前配置稳定窗口吸收。

## 执行步骤

1. 从现有控制器动作轨迹提取配置更新事件。
2. 确认探测开始前当前有效配置稳定窗口为一个 400 MHz 周期，即 2.5 ns。
3. 从已有网表、约束和数模接口资料中提取能够得到的现有转换延迟、边沿或稳定信息。
4. 计算 26 路接口允许占用的最大预算上限，必须扣除其他已知内部稳定需求，不能把整个 2.5 ns 无条件全部分给接口。
5. 定义目标接口必须满足的：
   - 最大传播延迟；
   - 最大位间到达偏差；
   - 单调转换要求；
   - 一次探测窗口内禁止变化要求；
   - 目标域低电压时的安全要求。
6. 不得把温度计码改成二进制后本地译码。

## 输出

```text
crossings/configuration_crossing_contract.json
timing_budget/configuration_timing_budget.json
```

## 硬停止条件

如果物理可实现接口所需的传播/稳定时间无法放入当前冻结的 2.5 ns 配置稳定窗口：

```text
PD1 配置接口时序 = 不通过
```

停止。本阶段不得自行把配置稳定时间从 1 周期改成 2 周期。

---

# 8. PD1-5 —— 复位接口契约

## 目标

为 `sense_dff_reset` 建立跨域后仍满足传感器采样触发器真实事件顺序的要求。

## 核心要求

跨域之后的真实物理顺序必须保持：

```text
复位释放完成
<
S_CLK 上升沿到达
```

以及：

```text
Q 第二次采样完成
<
复位重新拉高开始
<
复位重新拉高完成
<
S_CLK 下降沿到达
```

## 执行步骤

1. 回读历史精确物理事件顺序审计，只作为物理顺序参考，不把历史 1 GHz 周期数字重新激活为当前时序。
2. 回读 RF6 当前 400 MHz 传感器证据和 RF9D 当前端到端证据。
3. 提取能得到的复位释放、复位拉高与 S_CLK 的实际时间关系。
4. 建立复位接口允许的：
   - 最大传播延迟；
   - 最小单调性要求；
   - 禁止毛刺要求；
   - 上升/下降不对称容限；
   - 与 S_CLK 接口之间的相对延迟约束。
5. 复位接口与 S_CLK 接口必须联合预算，不能分别挑单元后再假设顺序自然成立。

## 输出

```text
crossings/reset_crossing_contract.json
timing_budget/reset_to_sclk_timing_budget.json
timing_budget/qsample2_to_reset_timing_budget.json
```

---

# 9. PD1-6 —— S_CLK 时序关键接口契约

## 目标

把 `sense_s_clk` 认定为 `PD_CTRL -> PD_SENSE` 中最高优先级时序关键跨域线，并给出可以直接用于后续单元选择的数值要求。

## 必须约束的项目

至少包括：

- 上升沿传播延迟；
- 下降沿传播延迟；
- 上升/下降传播延迟差；
- 输出上升时间；
- 输出下降时间；
- 高电平宽度变化；
- 低电平宽度变化；
- 输出逻辑高电平必须随 `VDD_MONITORED` 本地电源定义，而不能把 `VDD_CTRL` 电压直接灌入低压目标域；
- 目标域跌落时的安全行为。

## 执行步骤

1. 从 400 MHz 时序交接确定控制侧名义发出时刻。
2. 从 RF6/RF9C/RF9D 已有证据提取传感器侧实际 S_CLK 行为，能提取多少记录多少。
3. 不得凭“周期 2.5 ns”直接把 2.5 ns 当作接口传播预算。
4. 建立 `S_CLK` 到 `Q_SAMPLE_1` 的端到端链条：

```text
PD_CTRL 发出 S_CLK
-> 跨域接口
-> PD_SENSE 侧 S_CLK 到达
-> 冻结传感器传播
-> 传感器采样触发器形成 Q_FINAL
-> Q_FINAL 返回接口
-> PD_CTRL 输入稳定
-> Q_SAMPLE_1
```

5. 将总窗口扣除传感器已占时间、返回接口时间、数字采样建立裕量和必要安全余量后，得到 `S_CLK` 跨域接口可用预算。
6. 第二次采样也要做同样审计，不能只验证第一次。

## 输出

```text
crossings/sclk_crossing_contract.json
timing_budget/sclk_to_qsample_timing_budget.json
```

## 硬停止条件

如果现有 400 MHz 校准周期无法给出正的、工程上可实现的 `S_CLK` 接口预算，停止，不得修改校准时钟或传感器。

---

# 10. PD1-7 —— Q_FINAL 返回接口契约

## 目标

定义 `Q_FINAL` 从 `PD_SENSE` 返回 `PD_CTRL` 的可靠状态传输要求。

## 架构边界保持不变

必须保持：

```text
PD_SENSE
  延迟网络
    -> 异或网络
      -> 传感器采样触发器
        -> Q_FINAL
             │
             │ 跨电源域
             ▼
PD_CTRL
  Q 双采样
```

不得把异或窄脉冲或两条原始时序路径移出 `PD_SENSE`。

## 必须定义

1. 返回接口输入低电平判定范围；
2. 返回接口输入高电平判定范围；
3. 中间电压区域的处理要求；
4. 最大传播延迟；
5. 最小输出稳定时间；
6. 对两次 Q 采样的满足条件；
7. `PD_SENSE` 严重跌落/掉电时的安全行为；
8. 不得反向给 `PD_SENSE` 供电；
9. 传感器采样触发器已无法保证有效状态时，不得把“无效”默认为“安全”。

## 执行步骤

1. 回读现有数模接口契约中的当前模拟到数字判定抽象，仅作为已有验证方法记录，不能直接宣称为真实接口门限。
2. 回读 RF9D 中 Q 双采样、最终状态和当前模拟电源行为。
3. 从 400 MHz 端到端时间链计算返回接口最大允许传播预算。
4. 调查工艺库候选时，优先寻找能够把低电压源域状态可靠送入稳定控制域的接口结构。
5. 如果工艺库无法证明深度掉电下状态有效，则必须把此项标记为“后续检测工作区/无响应检测需要覆盖”，不能伪造结论。

## 输出

```text
crossings/qfinal_return_contract.json
```

---

# 11. PD1-8 —— 从已有证据提取端到端时序预算

## 目标

把前面四类接口的要求汇总成统一数值预算，并最大限度复用现有结果。

## 禁止做法

禁止使用以下简化推理：

```text
相邻控制周期是 2.5 ns
所以某个跨域接口最大延迟就是 2.5 ns
```

必须扣除窗口内其他真实过程。

## 必须形成四组预算

### 11.1 配置更新到允许探测

```text
配置更新完成
+ 26 路跨域最大传播
+ 最大位间偏差
+ PD_SENSE 内必要稳定时间
< 2.5 ns 配置稳定窗口
```

### 11.2 复位释放到 S_CLK 到达

```text
PD_SENSE 复位释放完成
<
PD_SENSE S_CLK 上升沿到达
```

预算必须包含两条接口各自的延迟和最坏偏差。

### 11.3 S_CLK 到 Q_SAMPLE_1 / Q_SAMPLE_2

必须覆盖完整链路：

```text
S_CLK 跨域
+ 冻结传感器响应
+ 传感器采样触发器响应
+ Q_FINAL 返回
+ PD_CTRL 输入建立要求
< 对应采样窗口
```

### 11.4 Q_SAMPLE_2 到复位重新拉高

必须保证控制域第二次采样已完成后，传感器域复位才真正开始重新拉高。

## 证据优先级

优先消费：

1. RF6 当前 400 MHz 三电压晶体管证据；
2. RF9D 当前 400 MHz 三电压端到端数模混合证据；
3. RF8 当前综合/时序结果；
4. 历史精确物理事件顺序，仅作为顺序和物理最小关系参考。

## 输出

```text
timing_budget/existing_evidence_extraction.json
timing_budget/end_to_end_timing_budget.json
```

每一个预算值必须同时记录：

- 数值；
- 单位；
- 数据来源；
- 来源文件；
- 是直接测得、静态推导还是保守上界；
- 是否存在证据缺口。

---

# 12. PD1-9 —— 工艺库跨电压接口静态调查

## 目标

在不做新瞬态仿真的前提下，确认当前工艺环境中是否存在能够满足四类接口契约的候选单元或明确可实现结构。

## 执行原则

先有契约预算，后查候选单元。禁止反过来先选某个单元，再修改契约去适配它。

## 调查范围

Codex 应静态搜索当前可用的：

- 标准单元库目录；
- 库说明文件；
- Liberty 或数据库可读信息；
- Verilog 功能/时序模型；
- 单元名称和描述中与跨电压、隔离、保持、掉电安全相关的候选；
- 已安装但本项目过去未使用的同工艺接口库，如果当前环境可读。

不得联网下载一个不属于当前工艺环境的任意接口单元来“证明可实现”。

## 候选分四类记录

```text
26 路配置线候选
1 路复位线候选
1 路 S_CLK 候选
1 路 Q_FINAL 返回候选
```

不要求四类必须使用相同单元。

## 每个候选至少记录

- 单元名称；
- 所属库；
- 可支持的源电压/目标电压范围；
- 转换方向；
- 传播延迟信息；
- 上升/下降边沿信息；
- 是否支持目标域低电压或掉电；
- 是否有隔离/保持能力；
- 是否有明确反向供电限制；
- 证据来源文件；
- 是否足以证明满足当前接口契约。

## 不允许过度推断

如果库文件只证明逻辑功能，没有掉电或反向供电资料，则只能写：

```text
掉电安全能力 = 未证明
```

不得凭单元名称推断已经满足。

## 输出

```text
library_audit/library_search_manifest.json
library_audit/candidate_interface_cells.json
library_audit/candidate_capability_matrix.json
library_audit/library_evidence_limitations.md
```

---

# 13. PD1-10 —— 反向供电和掉电安全静态审计

## 目标

防止跨域控制线在 `VDD_MONITORED` 下跌时通过接口或输入保护结构偷偷向 `PD_SENSE` 注入电流，从而污染真实电压跌落实验。

## 核心场景

至少检查：

```text
PD_CTRL 正常高电压
PD_SENSE 正常

PD_CTRL 正常高电压
PD_SENSE 中度跌落

PD_CTRL 正常高电压
PD_SENSE 严重跌落

PD_CTRL 正常高电压
PD_SENSE 接近 0 V
```

并分别考虑：

- 26 条配置线为高/低组合；
- 复位为高；
- S_CLK 高/低切换；
- Q_FINAL 返回端在源域掉电时的输入状态。

## 执行步骤

1. 优先从候选接口库资料、模型、端口结构和已有工艺文档静态判断。
2. 对能够明确证明无反向供电的候选记录证据。
3. 对无法证明的项目记录为证据缺口。
4. 不得为了这一项自动启动晶体管瞬态仿真。

## 输出

```text
power_safety/back_powering_risk_matrix.json
power_safety/unpowered_domain_behavior_contract.json
power_safety/power_safety_evidence_gap.json
```

## 硬停止条件

如果已知候选存在明确反向供电路径，且没有不修改冻结上游设计的替代接口方案：

```text
PD1 掉电安全 = 不通过
```

停止。

如果只是“现有资料不足以证明”，则进入“证据缺口停止”，不得冒充通过。

---

# 14. PD1-11 —— 物理接口架构选择

## 目标

基于前面形成的契约和候选能力，选出后续详细实现应该采用的接口类别，而不是直接改 RTL 或传感器。

## 目标结构

原则上形成：

```text
                   PD_CTRL
             稳定/可信数字电源
                     │
      ┌──────────────┼──────────────┐
      │              │              │
  26 路配置         复位           S_CLK
      │              │              │
      ▼              ▼              ▼
 配置型跨压接口   复位型跨压接口   时钟型跨压接口
      │              │              │
──────┼──────────────┼──────────────┼──── 电源域边界
      │              │              │
      ▼              ▼              ▼
                  PD_SENSE
                VDD_MONITORED
                     │
             ┌───────┴────────┐
             │ 完整冻结传感器 │
             │                │
             │ 延迟/调节网络  │
             │ 异或网络       │
             │ 采样触发器     │
             └───────┬────────┘
                     │
                  Q_FINAL
                     │
               状态返回接口
                     │
─────────────────────┼──────────────── 电源域边界
                     │
                     ▼
                   PD_CTRL
                     │
                  Q 双采样
```

## 必须说明

- 为什么 26 路配置线可以使用较慢接口；
- 为什么复位必须强调单调和相对顺序；
- 为什么 S_CLK 是最高时序优先级接口；
- 为什么 Q_FINAL 返回的是锁存状态而不是异或窄脉冲；
- 为什么异或网络和采样触发器继续留在 `PD_SENSE`；
- 哪些物理能力已经由库证据支持；
- 哪些能力仍未证明。

## 输出

```text
architecture/selected_interface_architecture.json
architecture/architecture_decision.md
```

本阶段仍然不得修改现有控制器 RTL 和冻结传感器。

---

# 15. PD1-12 —— 零新仿真闭合审核

## 目标

在启动任何新仿真之前，先判断 PD1 是否已经能够仅靠现有证据和静态库信息闭合。

## 审核维度

### 15.1 电源关系闭合

必须明确：

- 双电源；
- 共地前提；
- `PD_CTRL` 稳定；
- `PD_SENSE` 可跌落；
- 各电源状态下接口行为要求。

### 15.2 信号清单闭合

必须明确：

```text
28 条 CTRL -> SENSE
1 条 SENSE -> CTRL
共 29 条
```

没有漏项和隐藏功能跨界。

### 15.3 电气契约闭合

四类接口都必须有：

- 逻辑电压要求；
- 传播延迟要求；
- 边沿/单调性要求；
- 掉电安全要求；
- 反向供电要求。

### 15.4 时序闭合

至少确认：

- 26 路配置能在现有 2.5 ns 稳定窗口内达到合法稳定状态；
- 复位释放和 S_CLK 到达顺序有正裕量；
- S_CLK -> 传感器 -> Q_FINAL -> Q_SAMPLE_1/2 有正裕量；
- Q_SAMPLE_2 -> 复位重新拉高顺序有正裕量。

### 15.5 上游不变

必须机器检查或文件比对确认：

- 冻结传感器未改；
- 异或网络未搬；
- 传感器采样触发器未搬；
- 中调/细调结构未改；
- 启动校准算法未改；
- 400 MHz 校准时序未改；
- 直接温度计码结构未改。

## 结论类型

只允许三种：

```text
通过
不通过
证据缺口停止
```

不得使用含糊的“基本通过”掩盖关键物理量未知。

---

# 16. 新仿真授权门

PD1 默认不包含新的瞬态仿真。

如果 PD1-12 得到“证据缺口停止”，Codex 必须生成：

```text
reports/PD1_EVIDENCE_GAPS.md
```

每个缺口必须写成：

```text
缺口编号
物理量
为什么是阶段阻塞项
现有哪个证据不足
所需最小验证对象
所需最少场景数
为什么不能通过静态方法回答
是否需要改设计
```

然后停止。

**Codex 不得自行执行该最小验证。**

后续如果得到明确授权，只允许围绕缺口运行最小化定向验证，不得回到 RF6/RF9D 做全量重跑。

示例原则：

- 如果只缺 `Q_FINAL` 返回接口某一候选单元在低电压源域下的传播特性，只验证该候选接口和必要端点；
- 不允许因此把 0.80/0.95/1.10 V 全部 startup calibration 再跑一遍；
- 如果只缺反向供电静态电流，只针对接口掉电状态验证；
- 不允许因此重新执行完整数模闭环校准。

---

# 17. PD1 最终阶段门

只有同时满足以下条件，才能发布：

```text
PD1 物理电源域跨界接口契约 = 通过
```

## 必须全部成立

1. P10 冻结基线哈希一致；
2. 29 条跨域信号全部逐条登记；
3. 双电源共地工作前提无冲突；
4. 电源状态矩阵完整；
5. 26 条配置接口契约完整；
6. 复位接口契约完整；
7. S_CLK 接口契约完整；
8. Q_FINAL 返回接口契约完整；
9. 四组端到端时序预算具有正裕量；
10. 工艺库中存在与契约相容的可实现候选，或者有足够静态证据证明可构建等价接口；
11. 没有已知不可接受的反向供电风险；
12. 没有把未知掉电行为伪装成安全行为；
13. 冻结传感器未修改；
14. 启动校准算法未修改；
15. 400 MHz 校准时序未修改；
16. 本阶段未进行未经授权的上一阶段仿真重跑。

如果第 9、10、11、12 中任何一项不能由现有证据闭合，结论必须是：

```text
PD1 = 证据缺口停止
```

而不是强行给出通过。

---

# 18. 最终交付文件

PD1 完成时至少交付：

```text
delay_chain/ftc/controller/pd1_power_domain_interface/
  baseline/pd1_baseline_manifest.json
  baseline/immutable_input_sha256.json
  power_states/supply_topology_contract.json
  power_states/power_state_matrix.json
  crossings/crossing_inventory.json
  crossings/configuration_crossing_contract.json
  crossings/reset_crossing_contract.json
  crossings/sclk_crossing_contract.json
  crossings/qfinal_return_contract.json
  timing_budget/existing_evidence_extraction.json
  timing_budget/configuration_timing_budget.json
  timing_budget/reset_to_sclk_timing_budget.json
  timing_budget/sclk_to_qsample_timing_budget.json
  timing_budget/qsample2_to_reset_timing_budget.json
  timing_budget/end_to_end_timing_budget.json
  library_audit/library_search_manifest.json
  library_audit/candidate_interface_cells.json
  library_audit/candidate_capability_matrix.json
  library_audit/library_evidence_limitations.md
  power_safety/back_powering_risk_matrix.json
  power_safety/unpowered_domain_behavior_contract.json
  power_safety/power_safety_evidence_gap.json
  architecture/selected_interface_architecture.json
  architecture/architecture_decision.md
  reports/PD1_EVIDENCE_GAPS.md
  reports/PD1_GATE_STATUS.json
  reports/PD1_FINAL_REPORT.md
```

如果没有证据缺口，`PD1_EVIDENCE_GAPS.md` 仍应存在，并明确写“无阻塞性证据缺口”。

---

# 19. Codex 执行顺序

严格按照以下顺序推进，不得跳过门点：

```text
PD1-0  基线冻结和一致性回读
   ↓
PD1-1  29 条跨域信号逐条清点
   ↓
PD1-2  双电源和共地关系契约
   ↓
PD1-3  电源状态矩阵
   ↓
PD1-4  26 条配置线接口契约
   ↓
PD1-5  复位接口契约
   ↓
PD1-6  S_CLK 时序关键接口契约
   ↓
PD1-7  Q_FINAL 返回接口契约
   ↓
PD1-8  已有证据端到端时序预算
   ↓
PD1-9  工艺库跨电压接口静态调查
   ↓
PD1-10 反向供电和掉电安全静态审计
   ↓
PD1-11 物理接口架构选择
   ↓
PD1-12 零新仿真闭合审核
   ↓
通过 / 不通过 / 证据缺口停止
```

在 PD1 正式通过之前，不进入“校准到检测所有权切换”设计。

---

# 20. PD1 与下一阶段的明确边界

PD1 只回答：

> 两个已经冻结的电源域，在不破坏现有启动校准和传感器物理边界的情况下，29 条信号应该满足怎样的真实跨域电气、掉电和时序要求，并且当前工艺是否存在可实现路径。

PD1 不回答：

- 校准结束后检测逻辑何时接管传感器；
- 检测模式使用什么探测节拍；
- 检测裕量如何编码；
- 检测阈值对应多少毫伏；
- 电压跌落幅度/持续时间检测图；
- 极深电压跌落下最终报警策略；
- 检测状态机实现。

这些内容必须留到 PD1 通过后的独立阶段。

---

# 21. 本计划的最终硬规则摘要

Codex 执行时始终遵守：

```text
先读旧证据，后做新工作。
能静态证明，就不跑瞬态。
已有通过仿真，不为生成新报告而重跑。
遇到证据缺口，登记并停止，不自行扩展仿真。
遇到接口时序冲突，不修改 400 MHz 校准基线。
遇到接口结构冲突，不修改冻结传感器。
不把数模接口抽象冒充真实电平转换单元。
不把未知掉电行为冒充安全行为。
不进入下一阶段的检测功能设计。
```

本计划完成后的唯一允许结论之一必须明确写入 `PD1_GATE_STATUS.json`：

```text
PD1 物理电源域跨界接口契约 = 通过
```

或：

```text
PD1 物理电源域跨界接口契约 = 不通过
```

或：

```text
PD1 物理电源域跨界接口契约 = 证据缺口停止
```
