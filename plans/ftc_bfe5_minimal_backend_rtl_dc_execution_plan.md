# B-FE5 Minimal Backend RTL + DC Execution Plan

> 目标：从当前已经冻结的 `B-FE5-ARCH0` 出发，**逐步、最小化**实现安全域后处理电路，并在每一步使用 Synopsys Design Compiler 做真实 SMIC40LL 映射。所有 RTL 逻辑、模块、寄存器、端口和控制状态都必须只实现当前 Gate 所需的最小集合；禁止为了“未来可能会用”而预留接口、参数、状态机、调试端口或复杂数据通路。
>
> `B-FE5-ARCH1-CANDIDATE` 仅作为未来研究架构保存，**本计划不实现 ARCH1**。

---

# 0. 当前权威边界

工作分支：`bfe-multitap-latched-frontend`

当前权威架构：

- `delay_chain/ftc/analysis/b_fe_frontend/bfe5_arch0_contract/BFE5_ARCH0_CONTRACT.md`
- `delay_chain/ftc/analysis/b_fe_frontend/bfe5_arch1_candidate/BFE5_ARCH1_CANDIDATE.md` 仅为 future candidate，不得进入当前 RTL。

冻结的安全域主链：

```text
safe_d[29:0]
     |
30 x LATQ_X0P5M_A9TR40
     |
30 x DFFRPQ_X0P5M_A9TR40
     |
 q_ff[29:0]
     |
 M_FF = sum(i*q_ff[i]), i=0..29
     |
 startup calibration
     |
 M_REF_RISE / M_REF_FALL
     |
 abs(M_FF-M_REF)
     |
 programmable margin
     |
 DROOP_ALARM / DROOP_ALARM_STICKY
```

当前仓库已经存在单 bit 的真实捕获结构 `delay_chain/ftc/rtl/ftc_capture_struct.sv`，其中使用：

```text
LATQ_X0P5M_A9TR40
DFFRPQ_X0P5M_A9TR40
```

`delay_chain/ftc/discovery/selected_cells.json` 记录的 Verilog 逻辑/电源端口为：

```text
LATQ: Q, VDD, VSS, D, G
DFF : Q, VDD, VSS, CK, D, R
```

但 **DC 的实际 Liberty logical pin view 必须在实现前重新查询确认**，不得仅根据 Verilog/CDL 端口猜测综合接口。

---

# 1. 永久最小化规则

以下规则适用于本计划全部阶段，违反任一条即不得宣称 Gate PASS。

## 1.1 RTL 逻辑必须最小

- 固定 30 taps，不为了“通用性”增加 `N_TAPS` 等可配置泛型，除非代码必须因此显著更简单。
- 固定 `M_FF` 为 9 bit，不使用更宽的“保险”数据通路。
- 不建立 package、CSR block、register file、APB/AHB/AXI、interrupt controller、scan wrapper、debug controller。
- 不增加 pipeline，除非 DC 真实 timing evidence 证明当前最小结构无法满足后续明确要求，并经人工授权。
- 不增加冗余 valid/ready/busy/done/enable 信号；同一语义只保留一个信号。
- 不添加测试专用 RTL 端口。测试应通过 testbench、hierarchical observation 或综合报告完成。
- 不实现 LUT、ML、多特征融合、bubble repair、raw-code repair、ARCH1 tracking、DVFS/OPP bank、temperature compensation。
- 不从旧 FTC controller 复制复杂 FSM 或旧 1 GHz 控制逻辑；当前 backend 是新的、独立的最小实现。
- 除显式 foundry `LATQ` 外，不允许 RTL 推断任何额外 latch。
- 不使用乘法器、除法器。

## 1.2 端口必须最小

模块/顶层只暴露当前功能真正需要的端口。特别禁止为了“以后调试方便”暴露 `q_ff`、`M_REF`、内部 counter、sum、FSM state 等顶层输出。

最终 ARCH0 backend 顶层候选端口上限为：

```text
input  [29:0] safe_d
input         latch_gate
input         clk_probe
input         reset
input         event_valid
input         edge_pol
input         cal_mode
input  [8:0]  m_margin_rise
input  [8:0]  m_margin_fall
output        cal_lock
output        droop_alarm
output        droop_alarm_sticky
```

电源端口 `VDD/VSS` 只有在 **DC/库视图确实要求 RTL 显式连接**时才允许加入；若 Liberty logical view 不需要，则不得为了模拟习惯把电源端口扩散到 backend 顶层。

`event_valid` 定义为 **backend consume strobe**：当其为 1 时，与其配对的 `edge_pol` 和已经由 DFF bank 捕获完成的 `M_FF` 必须稳定可用。当前计划不实现 `event_valid/edge_pol` 生成器，也不额外增加一拍 pipeline 去猜测其时序。

## 1.3 每阶段严格停止

- 每个阶段独立 Gate、独立报告、独立 commit。
- 一次执行只允许完成一个阶段。
- 当前阶段 PASS 后立即停止，等待人工确认是否进入下一阶段。
- 当前阶段 FAIL/INCONCLUSIVE 后禁止自动加逻辑“修复到 PASS”。

---

# 2. Stage P0：DC Library / Capture Preservation Preflight

## 2.1 唯一目标

在写新的 backend RTL 之前，只回答：

> 当前 SMIC40LL `.db` 是否能让 DC 正确 link `LATQ_X0P5M_A9TR40` 和 `DFFRPQ_X0P5M_A9TR40`，它们在 DC 里的 logical pins/ref_name 是什么，以及什么最小 preservation constraints 能确保这两类实例不会被删除、替换、合并或跨边界优化？

## 2.2 必做

使用仓库已有 SMIC40LL RVT DC library flow，查询并记录：

```text
get_lib_cells *LATQ_X0P5M_A9TR40*
get_lib_cells *DFFRPQ_X0P5M_A9TR40*
get_lib_pins  <LATQ cell>/*
get_lib_pins  <DFF cell>/*
```

确认：

- 两个 cell 在目标 `.db` 中真实存在；
- latch 的 D/Q/G 属性正确；
- DFF 的 D/Q/CK/R 属性正确；
- reset 极性与现有 selected-cell contract 一致；
- DC 是否要求在 RTL 中显式处理 power pins。

然后做一个最小 1-bit link probe，只含一颗 LATQ + 一颗 DFF，不添加 feature logic。

## 2.3 Preservation 最小原则

优先使用：

```tcl
set latq_cells [get_cells -hierarchical -filter "ref_name == LATQ_X0P5M_A9TR40"]
set dff_cells  [get_cells -hierarchical -filter "ref_name == DFFRPQ_X0P5M_A9TR40"]
set_dont_touch $latq_cells
set_dont_touch $dff_cells
```

capture-bank 层级后续应禁止 ungroup/boundary optimization，但只约束 capture bank；feature/backend 仍允许 DC 自由优化。

禁止一开始使用大范围 `set_dont_touch_network [all_clocks]`、全设计 `dont_touch`、全库 `dont_use` 等粗暴约束。

综合使用普通 `compile`，不使用 `compile_ultra`、retiming 或 sequential boundary optimization。

## 2.4 Gate

`BFE5_P0_DC_CAPTURE_CELL_PREFLIGHT_PASS`

PASS 要求：

- 两种目标 cell 均能真实 link；
- 1-bit probe 映射后仍恰好 1 LATQ + 1 DFF；
- cell ref_name 不变；
- LATQ.Q 直接连接 DFF.D；
- 无 unresolved reference；
- 输出最小可复现 DC query/link report。

P0 不写 30-bit backend，不实现 M，不实现 calibration。

---

# 3. Stage RTL0：30-bit Capture Bank + M Feature

只有 P0 PASS 后才允许执行。

## 3.1 目标架构

```text
                    PD_SAFE synthesis boundary

safe_d[29:0]
     |
     v
+-------------------------+
| bfe_capture_bank        |
|                         |
| 30 x REAL LATQ          | <- latch_gate
|       |                 |
| 30 x REAL DFF           | <- clk_probe / reset
+-----------+-------------+
            |
        q_ff[29:0]
            |
            v
+-------------------------+
| bfe_m_feature           |
| M=sum(i*q_ff[i])        |
+-----------+-------------+
            |
         M_FF[8:0]
```

## 3.2 RTL 文件数量最小化

优先只新增：

```text
delay_chain/ftc/rtl/bfe_capture_bank.sv
delay_chain/ftc/rtl/bfe_m_feature.sv
delay_chain/ftc/rtl/bfe_backend_top.sv
```

如果当前 `ftc_capture_struct.sv` 可直接被 DC 正确 link，则 `bfe_capture_bank` 应直接实例化它 30 次，禁止复制一份等价的 LATQ/DFF wrapper；只有 P0 证明它与 DC logical view 不兼容时，才允许建立最小 DC-compatible wrapper。

不创建 package。

## 3.3 Capture bank 最小实现

固定 30 路，同一个 `latch_gate`、同一个 `clk_probe`、同一个 `reset`。

内部 `q_ff[29:0]` 必须保留，但不作为 `bfe_backend_top` 顶层输出。

所有 60 个真实 sequential cells 必须在 link 后施加 `dont_touch`。

DC 必须自动断言：

```text
LATQ_X0P5M_A9TR40 count   == 30
DFFRPQ_X0P5M_A9TR40 count == 30
```

并验证每个 i：

```text
safe_d[i] -> LATQ[i].D
LATQ[i].Q -> DFF[i].D
DFF[i].Q  -> q_ff[i]
```

其中 `LATQ.Q -> DFF.D` 之间不允许出现 combinational cell、mux、inverter 或逻辑 replacement。

## 3.4 M feature 最小实现

数学定义严格固定：

```text
M_FF = sum(i*q_ff[i]), i=0..29
range = 0..435
width = 9 bit
```

第一版使用**最简单可综合组合 RTL**表达 constant-weight sum，让 DC 自己优化；禁止为了“可能更快”手工设计复杂 CSA/tree/prefix network。

`q_ff[0]` 的权重为 0，算术中可以自然忽略，但对应 LATQ/DFF 仍必须物理保留。

`report_resources` 不得出现 multiplier/divider。

## 3.5 RTL0 验证

至少包含：

```text
all zero      -> M=0
only q[1]=1   -> M=1
only q[29]=1  -> M=29
all one       -> M=435
random q      -> 与软件 golden sum 完全一致
```

再从仓库已有 CLK2/VD0/VD1 已验证结果中直接读取 representative `q_ff`，确认新的 RTL `M_FF` 与历史已记录 M 一致。不得手工“修正”历史 q code。

## 3.6 DC 输出

至少保存：

```text
check_design_precompile.rpt
check_design_postcompile.rpt
report_reference.rpt
report_cell.rpt
report_resources.rpt
report_area.rpt
report_qor.rpt
report_timing.rpt
mapped.v
mapped.ddc
mapped.sdc
```

并生成一个结构检查摘要，明确列出：

```text
LATQ count
DFF count
每个 ref_name
LATQ.Q->DFF.D direct-connect check
multiplier count
M width
```

## 3.7 RTL0 Gate

`BFE5_RTL0_CAPTURE_M_BACKEND_PASS`

必须同时满足：

- 30 LATQ 保留；
- 30 DFF 保留；
- ref_name 均正确；
- 30 路 LATQ.Q→DFF.D 直接连接；
- 无 sequential cell 被删除/替换/合并；
- M 数学回归全 PASS；
- known frontend vectors 全 PASS；
- `M_FF` 9 bit；
- 无 multiplier/divider；
- DC link/check_design 无 fatal/unresolved；
- 没有新增 calibration/detector/ARCH1 逻辑。

RTL0 PASS 后立即停止。

---

# 4. Stage RTL1：最小 Startup Calibration

只有 RTL0 PASS 且人工授权后执行。

## 4.1 唯一新增功能

在 `M_FF` 后加入 ARCH0 已冻结的 startup calibration：

```text
4 valid RISE samples -> M_REF_RISE
4 valid FALL samples -> M_REF_FALL
both done            -> CAL_LOCK=1
```

不实现 detector。

## 4.2 最小控制

使用现有 `clk_probe` 作为 backend sequential clock，不新增 backend clock。

只允许新增必要输入：

```text
event_valid
edge_pol
cal_mode
```

`reset` 复用 RTL0 reset。

实现只需要：

- `SUM_RISE[10:0]`
- `SUM_FALL[10:0]`
- 每个 polarity 最小 sample count/done state
- `M_REF_RISE[8:0]`
- `M_REF_FALL[8:0]`
- `CAL_LOCK`

均值第一版直接使用 4-sample sum 右移 2 bit；不实现 divider，不做统计方差、min/max、median、EWMA。

不建立多状态 calibration FSM；若 counter + done bit 足够，不允许用 FSM。

第一版只支持 **reset 后的一次 startup calibration epoch**。`CAL_LOCK` 后 reference 永久冻结到下次 reset；不为了未来 service recalibration 增加额外 handshake。

## 4.3 RTL1 Gate

`BFE5_RTL1_STARTUP_CALIBRATION_PASS`

要求：

- invalid event 不计数；
- rise/fall 分开累计；
- 各 4 个 valid sample 后得到正确均值；
- 两边完成前 `CAL_LOCK=0`；
- 两边完成后 `CAL_LOCK=1`；
- `CAL_LOCK` 后 reference 不再变化；
- 无 divider/multiplier；
- 无额外 FSM/无多余端口；
- RTL0 的 30 LATQ + 30 DFF preservation Gate 继续 PASS；
- DC mapped netlist 成功。

RTL1 PASS 后立即停止。

---

# 5. Stage RTL2：最小 Detection Datapath

只有 RTL1 PASS 且人工授权后执行。

## 5.1 唯一新增功能

```text
edge_pol
   |
select M_REF_RISE/FALL
   |
D_M = abs(M_FF - M_REF)
   |
select M_MARGIN_RISE/FALL
   |
D_M > M_MARGIN ?
   |
DROOP_ALARM
   |
DROOP_ALARM_STICKY
```

## 5.2 最小端口增量

只新增：

```text
input [8:0] m_margin_rise
input [8:0] m_margin_fall
output      droop_alarm
output      droop_alarm_sticky
```

`cal_lock` 保持唯一 calibration status 输出。

禁止暴露 `M_FF`、`D_M`、`M_REF_*`、counter、sum、内部 compare result 为顶层调试端口。

## 5.3 最小检测语义

```text
detect_valid = event_valid && cal_lock && !cal_mode
```

只有 `detect_valid` 时报警比较有意义。

绝对差使用普通 9-bit compare + subtract：

```text
if M_FF >= M_REF: D_M = M_FF - M_REF
else              D_M = M_REF - M_FF
```

禁止引入 signed-wide arithmetic、DSP、LUT。

`droop_alarm` 为当前 valid event 的报警结果；`droop_alarm_sticky` 一旦置位保持到 `reset`，第一版不增加单独 clear 端口。

不实现 debounce、hysteresis、K-of-N、ARCH1 tracking。

## 5.4 RTL2 Gate

`BFE5_RTL2_MINIMAL_DETECTOR_PASS`

要求：

- rise/fall reference/margin 选择正确；
- absolute difference 边界正确；
- `event_valid=0` / `cal_lock=0` / `cal_mode=1` 时不报警；
- threshold 采用严格 `>`，等于 margin 不报警；
- sticky alarm 行为正确；
- 无额外 clear/ready/busy/debug port；
- RTL0/RTL1 preservation 与功能回归继续 PASS；
- DC mapped netlist 成功。

RTL2 PASS 后立即停止。

---

# 6. Stage RTL3：ARCH0 Backend Integration / DC Closure

只有 RTL2 PASS 且人工授权后执行。

## 6.1 目标

形成当前 ARCH0 的最小可综合 backend top，不新增功能。

最终结构：

```text
safe_d[29:0]
     |
30 x LATQ (protected)
     |
30 x DFF  (protected)
     |
M_FF 9b
     |
4+4 sample startup calibration
     |
M_REF_RISE/FALL
     |
abs difference + programmable margin
     |
ALARM + STICKY
```

## 6.2 最终顶层端口审计

最终只允许保留第 1.2 节列出的最小端口集合；任何额外 top-level port 必须在 report 中逐项给出“不可删除”的功能理由，否则删除。

内部 module boundary 可以有 `q_ff`、`M_FF`、`M_REF` 等必要连接，但不得把它们扩展成宏外部接口。

## 6.3 DC 约束边界

- capture bank：结构保护；
- M feature/calibration/detection：允许普通 DC logic optimization；
- 不使用 `compile_ultra`；
- 不 retime；
- 不跨 capture boundary 优化；
- 不把 `LATQ`/`DFF` 替换为其他 sequential cells；
- 不对全设计施加无必要 `dont_touch`。

`clk_probe` 作为唯一 backend sequential clock。实际 timing constraint 必须依据当前冻结 400 MHz safe-domain probe 条件，不继承旧 controller 的 1 GHz constraint。

本阶段的 timing report 用于确认最小 backend 是否存在明显关键路径问题；若 timing FAIL，不得在同一阶段自动加入 pipeline/复杂 adder tree，必须输出原因并停止，由人工决定是否开启专门 timing optimization stage。

## 6.4 RTL3 Gate

`BFE5_RTL3_ARCH0_BACKEND_DC_PASS`

PASS 至少要求：

- 全部 RTL0/RTL1/RTL2 功能回归 PASS；
- 30 LATQ + 30 DFF structural preservation PASS；
- 顶层无多余端口；
- 无额外 inferred latch；
- 无 multiplier/divider；
- 无 unresolved reference；
- DC mapped netlist、DDC、SDC、area/reference/resources/timing reports 完整；
- 报告实际 cell count/area/timing，而不是预估；
- ARCH1 candidate 未被实现。

---

# 7. 推荐最小文件组织

除非仓库现有结构要求不同，不要创建更多目录层次：

```text
delay_chain/ftc/rtl/
  bfe_capture_bank.sv
  bfe_m_feature.sv
  bfe_backend_ctrl.sv        # RTL1/RTL2 逐步扩展；不要拆出多个小 FSM
  bfe_backend_top.sv

delay_chain/ftc/backend/synthesis/
  run_dc.tcl
  run_dc.sh                  # 仅在确实需要环境封装时创建

delay_chain/ftc/backend/reports/
delay_chain/ftc/backend/netlist/
```

测试优先复用现有 `delay_chain/ftc/tests/`，不要为每个 20 行 RTL 创建独立 test framework。

`bfe_backend_ctrl.sv` 在 RTL1 先只实现 calibration；RTL2 在同一文件中增加最小 detector。不要为了“模块化美观”拆成 calibration FSM、reference manager、margin manager、alarm manager 等多个模块。

---

# 8. Codex 防过度设计检查清单

每个 commit 前必须回答以下问题；任意答案为“是”都要先删除/简化，除非当前 Gate 明确要求：

```text
是否新增了当前阶段未使用的端口？
是否新增了 future-proof parameter？
是否新增了 debug/status 输出？
是否新增了 CSR/bus/register file？
是否新增了额外 pipeline？
是否新增了复杂 FSM，而 counter/flag 已足够？
是否新增了 multiplier/divider/LUT？
是否实现了 ARCH1 tracking？
是否实现了 DVFS/OPP/temperature/PVT policy？
是否为了 timing 猜测提前重构 adder tree？
是否修改了已冻结 LATQ/DFF capture mechanism？
是否把一个当前 Gate 的失败通过增加功能“修”成 PASS？
```

核心原则：

> **先证明最小硬件能够正确综合和工作，再由真实面积/时序/鲁棒性证据决定是否增加下一块逻辑。没有实验或 DC 报告证明需要的复杂度，一律不实现。**

当前首先执行 `Stage P0`；P0 PASS 后停止。