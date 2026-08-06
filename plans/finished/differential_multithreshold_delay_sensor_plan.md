# 差分多阈值延迟传感器实施计划

## 1. 目的与范围

本计划用于在现有 `power_macro` 仓库中，将 Phase 1 的单延迟链固定时刻采样方案升级为一个可由 SMIC40LL 标准单元实现的差分多阈值延迟传感器。

当前已知条件：

- 工艺库：SMIC40LL `sc9mc_base_rvt_c40`；
- 当前感知单元：`INV_X0P5M_A9TR40`；
- 反相器 CDL 端口顺序：`Y VDD VNW VPW VSS A`；
- 标称电压：`1.1 V`；
- 770 MHz 下首次违例电压：`1.092826204042 V`；
- 需要分辨的电压差约为 `7.17 mV`；
- Phase 1 的 16/32/64 级单链固定采样没有产生足够大的码元变化。

本阶段目标不是设计晶体管级模拟灵敏放大器，而是利用两条标准单元延迟链和一组标准单元 DFF/边沿比较器，将微小供电电压变化转换成多位温度计码。

最终希望得到：

```text
VDD_A - VSS_A
      -> 感知链相对参考链的边沿位置变化
      -> 16/32 bit 差分温度计码
      -> 纠错后的 sensor_code
      -> 后续 1D-TCN 输入
```

---

## 2. 电路总体结构

### 2.1 顶层框图

```text
                         VDD_REF / VSS_REF
                                |
                                v
START_REF ----------------> Reference launch
                                |
                                v
                   R0 -> R1 -> R2 -> ... -> R(M-1)
                    |     |     |              |
                    |     |     |              |
                    |     |     |              +------ CLK of DFF[M-1]
                    |     |     +--------------------- CLK of DFF[2]
                    |     +--------------------------- CLK of DFF[1]
                    +--------------------------------- CLK of DFF[0]

START_REF
   |
   v
Programmable launch-offset network, powered by VDD_REF/VSS_REF
   |
   v
Sense launch buffer
   |
   v
                   S0 -> S1 -> S2 -> ... -> S(M-1)
                   powered by VDD_A / VSS_A
                    |     |     |              |
                    |     |     |              +------ D of DFF[M-1]
                    |     |     +--------------------- D of DFF[2]
                    |     +--------------------------- D of DFF[1]
                    +--------------------------------- D of DFF[0]

DFF bank, powered by VDD_REF / VSS_REF
   |
   +--> raw_code[M-1:0]
   |
   +--> bubble correction
   |
   +--> transition-point encoder
   |
   +--> sensor_code + code_quality
```

### 2.2 核心判决关系

第 `i` 级 DFF 连接为：

```text
D   = S_i
CLK = R_i
RST = sensor_reset
Q   = raw_code[i]
```

当参考边沿 `R_i` 到达时：

- 若感知边沿 `S_i` 已到达，则 `Q=1`；
- 若感知边沿 `S_i` 尚未到达，则 `Q=0`。

理想码型：

```text
0000011111111111
```

定义：

```text
sensor_code = leading-zero count
```

即前导零的数量。

电压下降时感知链变慢，因此：

```text
VDD_A decrease -> sense edge becomes later -> leading-zero count increases
```

---

## 3. 两条延迟链的具体结构

## 3.1 感知延迟单元 `sense_stage`

每一级由两个反相器组成一个非反相延迟单元：

```text
A_in
  |
  v
INV_X0P5M_A9TR40
  |
  v
INV_X0P5M_A9TR40
  |
  v
Y_out
```

每个实例的连接必须显式写为：

```text
Y   = output node
VDD = VDD_A
VNW = VDD_A
VPW = VSS_A
VSS = VSS_A
A   = input node
```

要求：

- 所有感知级都连接芯粒 A 的本地 `VDD_A/VSS_A`；
- 不连接理想源端；
- 不使用固定 `#delay`；
- 不自行搭建 NMOS/PMOS；
- 第一版不添加额外 dummy load。

## 3.2 参考延迟单元 `reference_stage`

基本结构与感知级相同：

```text
A_in
  |
  v
INV_X0P5M_A9TR40
  |
  v
INV_X0P5M_A9TR40 ----> Y_out
                          |
                          +--> 0/1/2/3 个 dummy INV input loads
```

所有参考链单元和 dummy load 连接：

```text
VDD = VDD_REF
VNW = VDD_REF
VPW = VSS_REF
VSS = VSS_REF
```

dummy load 实现：

- dummy inverter 的 `A` 端连接当前参考级输出；
- dummy inverter 的 `Y` 端连接独立的未使用命名节点；
- dummy inverter 仍需完整连接 `VDD/VNW/VPW/VSS`；
- 不得把 dummy 输出短接到地或电源；
- 不得在分析脚本中用理想电容替代，除非单独作为对照实验。

参考级的目标是：

```text
t_ref = t_sense(Vnom) + delta_0
```

即参考级在标称电压下比感知级略慢。

---

## 4. Vernier 工作条件

两条链满足：

```text
T_S,i = T_S,0 + i * t_sense(VDD_A)
T_R,i = T_R,0 + i * t_ref
```

定义启动偏移：

```text
Delta_T_launch = T_S,0 - T_R,0 > 0
```

标称电压下要求：

```text
t_sense(Vnom) < t_ref
```

因此感知边沿初始落后，但每级传播略快，会逐渐追上参考边沿。

理想转折级数：

```text
i_star = Delta_T_launch / (t_ref - t_sense)
```

当 `VDD_A` 下降时：

```text
t_sense increases
(t_ref - t_sense) decreases
i_star increases
```

因此温度计码转折点向右移动。

---

## 5. 默认参数与扫描范围

第一版默认：

```text
comparator_stages M = 16
nominal transition target C0 = 8
sense stage = 2 x INV_X0P5M_A9TR40
reference stage = 2 x INV_X0P5M_A9TR40 + programmable dummy loads
reference dummy load count = 0, 1, 2, 3
launch offset choices = 0..7 standard-cell delay taps
VDD_A fine sweep = 1.085 V to 1.100 V
fine sweep step = 0.0005 V
VDD_REF initial value = 1.100 V ideal
corner = TT
initial temperature = 25 C
```

第二轮可扩展：

```text
M = 8, 16, 32
corners = TT, SS, FF
temperatures = 25 C, 85 C
VDD_A extended range = 0.95 V to 1.10 V
```

---

## 6. 可编程启动偏移网络

## 6.1 第一阶段：理想偏移

在没有实现标准单元可编程延迟之前，先在 SPICE testbench 中使用独立 PULSE 延迟参数：

```text
START_REF   = pulse at T0
START_SENSE = pulse at T0 + Delta_T_launch
```

扫描 `Delta_T_launch`，找到标称电压下转折码接近 `C0=8` 的范围。

此阶段只用于确定目标偏移，不作为最终电路。

## 6.2 第二阶段：标准单元偏移网络

建立参考域供电的非反相延迟 tap 链：

```text
START
  +--> tap0: direct
  +--> tap1: 1 non-inverting delay unit
  +--> tap2: 2 non-inverting delay units
  ...
  +--> tap7: 7 non-inverting delay units
```

通过标准单元 MUX 选择一个 tap：

```text
CAL_SEL[2:0] -> tap-select MUX -> START_SENSE
```

要求：

- 偏移链由 `VDD_REF/VSS_REF` 供电；
- 第一版如果尚未发现合适的标准单元 MUX，可在 SPICE 中使用受控开关或逐场景生成不同固定连接；
- 不得猜测 MUX 单元名；必须从 SMIC40LL CDL/Verilog 库中搜索并记录真实单元名和端口；
- 若库中没有合适 MUX，Phase 2 可先为每个 `CAL_SEL` 生成独立网表。

---

## 7. DFF 比较器阵列

## 7.1 DFF 单元发现

Codex 必须先搜索 SMIC40LL 标准单元 CDL 和 Verilog 模型，找到：

- 正边沿触发 DFF；
- 优先选择带异步清零的 DFF；
- 记录真实 cell name；
- 记录 CDL 端口顺序；
- 记录电源、well、reset、clock、D、Q 端口。

禁止直接假设单元名为 `DFFRX1` 或其他常见名称。

生成文件：

```text
delay_chain/phase2_vernier/discovery/dff_candidates.md
```

内容至少包括：

```text
cell name
CDL port order
clock polarity
reset polarity
power pins
selected/not selected
selection reason
```

## 7.2 DFF 供电

比较器 DFF bank 由：

```text
VDD_REF / VSS_REF
```

供电。

感知 tap 的高电平来自 `VDD_A`。必须在真实 DFF SPICE 仿真中验证跨小电压差输入：

```text
VDD_A = 0.95..1.10 V
VDD_REF = 1.10 V
```

需要检查：

- 是否能正确识别高电平；
- 是否出现明显静态短路电流；
- 是否需要接收缓冲或 level shifter；
- Warning 区间 `1.085..1.10 V` 是否可靠。

如果库中存在 level shifter，记录候选；第一版不得无依据添加自定义模拟电平转换器。

---

## 8. 参考电源结构

## 8.1 初始可行性验证

第一阶段使用理想参考电源：

```text
VDD_REF = 1.1 V
VSS_REF = 0 V
```

目的：仅验证差分编码和码元灵敏度。

## 8.2 接入共享 RLC 时的参考岛

后续建立 RC 隔离参考岛：

```text
upstream VDD ---- R_ISO ---- VDD_REF
                              |
                             C_REF
                              |
                           VSS_REF
```

要求：

```text
tau_ref = R_ISO * C_REF >= 5 to 10 times sensor decision time
```

扫描：

```text
R_ISO: 1, 2, 5, 10 ohm
C_REF: 1, 2, 5, 10 pF
```

注意：具体量级必须根据共享 RLC 模型和检测时间重新筛选，不得直接把上述候选作为最终物理值。

---

## 9. 码元定义与数字处理

## 9.1 原始码

```text
raw_code[M-1:0]
```

理想形式：

```text
0000011111111111
```

## 9.2 气泡纠错

第一版使用三位多数滤波：

```text
corrected[i] = majority(raw[i-1], raw[i], raw[i+1])
```

边界位保持原值或使用两位一致性规则。

## 9.3 传感码

使用前导零计数：

```text
sensor_code = leading_zero_count(corrected_code)
```

同时计算：

```text
ones_count = sum(corrected_code)
transition_count = number of 0<->1 transitions
bubble_count = number of non-monotonic bits
```

输出字段：

```text
sensor_code
raw_code
corrected_code
bubble_count
code_valid
```

`code_valid` 条件：

```text
transition_count <= 1
```

TCN 后续输入建议：

```text
x0[k] = sensor_code[k]
x1[k] = sensor_code[k] - sensor_code[k-1]
x2[k] = bubble_count[k]
x3[k] = code_valid[k]
```

---

## 10. 仿真状态时序

一次测量周期必须包含以下状态：

### RESET

```text
START = 0
DFF reset asserted
both chains return to 0
```

### ARM

```text
release DFF reset
hold CAL_SEL constant
wait for reference island stable
```

### LAUNCH

```text
START_REF rising edge
START_SENSE rising edge after selected launch offset
```

### PROPAGATE / COMPARE

参考边沿依次到达 `R_i`，对应 DFF 采样 `S_i`。

### CAPTURE

等待最后一级参考边沿完成后锁存 `raw_code`。

### ENCODE

进行纠错、转折点编码和 CSV 导出。

### RECOVER

START 回到 0，等待所有链节点复位后进入下一周期。

测量周期的所有时间参数必须写入配置文件，不允许散落硬编码在多个脚本中。

---

## 11. 仓库目录与文件要求

新增：

```text
delay_chain/
└── phase2_vernier/
    ├── README.md
    ├── phase2_config.json
    ├── discovery/
    │   ├── dff_candidates.md
    │   ├── mux_candidates.md
    │   └── selected_cells.json
    ├── scripts/
    │   ├── extract_phase1_delay_delta.py
    │   ├── discover_standard_cells.py
    │   ├── generate_vernier_deck.py
    │   ├── run_ideal_arrival_sweep.py
    │   ├── analyze_ideal_arrivals.py
    │   ├── run_dff_sweep.py
    │   ├── decode_vernier_code.py
    │   ├── run_reference_island_sweep.py
    │   └── run_shared_pdn_vernier.py
    ├── spice/
    │   ├── sense_stage.inc
    │   ├── reference_stage.inc
    │   ├── launch_offset.inc
    │   ├── comparator_bank.inc
    │   └── vernier_sensor_top.inc
    ├── tests/
    │   ├── test_cell_discovery.py
    │   ├── test_deck_generation.py
    │   ├── test_arrival_decoder.py
    │   ├── test_thermometer_decoder.py
    │   └── test_config_validation.py
    └── runs/
        └── generated run directories
```

不要提交：

- HSPICE `.tr0/.lis/.mt0`；
- 大型中间波形；
- 临时 solver 文件。

可以提交：

- 配置；
- 脚本；
- 测试；
- 汇总 CSV；
- Markdown 报告；
- 精选图像。

---

## 12. 配置文件建议

`phase2_config.json` 至少包含：

```json
{
  "schema_version": 1,
  "technology": "SMIC40LL sc9mc_base_rvt_c40",
  "corner": "tt",
  "temperature_c": 25.0,
  "vnom_v": 1.1,
  "first_violation_voltage_v": 1.092826204042,
  "sense_inverter_cell": "INV_X0P5M_A9TR40",
  "sense_inverter_ports": ["Y", "VDD", "VNW", "VPW", "VSS", "A"],
  "comparator_stages": [8, 16, 32],
  "default_comparator_stages": 16,
  "reference_dummy_load_counts": [0, 1, 2, 3],
  "launch_offset_taps": [0, 1, 2, 3, 4, 5, 6, 7],
  "fine_vdd_start_v": 1.085,
  "fine_vdd_stop_v": 1.1,
  "fine_vdd_step_v": 0.0005,
  "nominal_target_code_fraction": 0.5,
  "target_fail_code_delta": 3
}
```

实际模型路径、HSPICE路径、CDL路径应复用 Phase 1 的配置，不要复制硬编码到多个文件。

---

# 13. 逐步骤执行计划

## Step 0：读取和复用 Phase 1 基础设施

任务：

1. 读取 `delay_chain/phase1/phase1_config.json`；
2. 读取 Phase 1 网表生成器和分析脚本；
3. 复用：
   - model library 路径；
   - cell CDL 路径；
   - HSPICE 路径；
   - inverter 端口顺序；
   - run-directory 规则；
   - raw result parser；
4. 不修改 Phase 1 已有结果。

验收：

- Phase 1 单元测试继续通过；
- Phase 2 配置能继承 Phase 1 的公共路径。

## Step 1：提取现有单级延迟增量

编写：

```text
extract_phase1_delay_delta.py
```

输入：Phase 1 的 raw/summary 数据。

输出：

```text
t_sense_nominal
t_sense_first_violation
epsilon = t_fail - t_nominal
relative_delay_change_percent
```

生成：

```text
delay_chain/phase2_vernier/reports/phase1_delay_delta.md
```

禁止：

- 从图像估算；
- 缺失数据时伪造结果；
- 用理论模型替代已有 HSPICE 数据。

若 Phase 1 数据不包含足够的单级延迟信息，则重新运行最小必要的 1.1 V 和 1.092826204042 V 两个场景。

验收：

- 报告给出实测 `epsilon`；
- 后续参考级延迟差以该值为依据。

## Step 2：标准单元发现

编写：

```text
discover_standard_cells.py
```

搜索：

- 正边沿 DFF；
- 带异步清零 DFF；
- 2:1 MUX；
- 可选 level shifter；
- 可选 buffer。

输出：

```text
dff_candidates.md
mux_candidates.md
selected_cells.json
```

验收：

- 所有选用单元都有真实 CDL 名称和端口顺序；
- 没有猜测单元名；
- 发现失败时明确停止，不自动编造替代名称。

## Step 3：建立理想到达时间 Vernier 模型

先不实例化 DFF。

`generate_vernier_deck.py` 生成：

- M 级感知链；
- M 级参考链；
- 可扫描 dummy load；
- 理想启动偏移；
- 每一级 `S_i` 和 `R_i` crossing measure。

扫描：

```text
M = 8,16,32
dummy_load = 0,1,2,3
VDD_A = 1.085..1.100 V, step 0.5 mV
Delta_T_launch = around target range
```

分析脚本根据 crossing time 计算：

```text
ideal_bit[i] = 1 if T_S,i < T_R,i else 0
ideal_sensor_code
```

先使用 `0 ps` guard，再额外输出 `+/- setup_guard` 的敏感性对照。

验收：

- 标称码可调到 M/2 附近；
- 首次违例电压与标称码差至少 3；
- 1.085..1.1 V 区间整体单调；
- 选择至少一个候选 `(M, dummy_load, Delta_T_launch)`。

若没有候选：

- 不进入 DFF 阶段；
- 输出 `NO_FEASIBLE_IDEAL_CANDIDATE`；
- 扩展参考级结构或链长后再测试。

## Step 4：确定参考级和启动偏移候选

对理想模型候选进行排序：

优先级：

1. `abs(C_fail - C_nominal) >= 3`；
2. 标称码距两端至少 25% 量程；
3. 电压-码元单调；
4. dummy load 数量更少；
5. M 更小；
6. 平均功耗和峰值电流更低。

输出：

```text
selection_ideal.json
selection_ideal.md
```

至少保留 3 个候选进入真实 DFF 阶段。

## Step 5：加入真实 DFF 比较器阵列

使用 Step 2 选定的真实 DFF CDL 子电路。

连接：

```text
D = S_i
CLK = R_i
RESET = global sensor reset
Q = raw_code[i]
```

加入完整 RESET/ARM/LAUNCH/RECOVER 时序。

验证场景：

- 标称电压；
- 首次违例电压；
- 1.085 V；
- 1.100 V；
- 至少 3 组 launch offset；
- 至少 2 组 dummy load。

输出：

- raw DFF bits；
- crossing times；
- DFF Q settle time；
- comparator bank power；
- 错误/亚稳态标志。

验收：

- 真实 DFF 码元趋势与理想 arrival 比较一致；
- 首次违例码差至少 2，目标为 3；
- 码元可通过纠错恢复；
- 没有大面积随机翻转。

## Step 6：实现码元纠错和编码器参考模型

编写：

```text
decode_vernier_code.py
```

功能：

1. 读取 raw bits；
2. 三位多数滤波；
3. 计算 leading-zero code；
4. 计算 bubble count；
5. 计算 code validity；
6. 导出标准 CSV。

CSV 至少包括：

```text
scenario_id
vdd_a_v
vdd_ref_v
m_stages
dummy_load_count
launch_offset
raw_code
corrected_code
sensor_code
bubble_count
code_valid
```

验收：

- 单元测试覆盖理想码、单气泡、双气泡、全 0、全 1；
- 无效码不得被静默当作有效码。

## Step 7：启动偏移校准算法

实现离线校准参考算法：

1. 在无攻击、已知正常工作状态下采样 16 或 32 次；
2. 对每个 `CAL_SEL` 求 `sensor_code` 中位数；
3. 选择最接近 `M/2` 的 `CAL_SEL`；
4. 若并列，选择 bubble count 更小者；
5. 若仍并列，选择偏移较小者。

输出：

```text
selected_cal_sel
baseline_code
baseline_variation
calibration_status
```

验收：

- TT 条件下可将标称码置于 M/2 +/- 1；
- 无可行 tap 时输出明确失败状态。

## Step 8：跨电压域输入验证

固定 DFF 供电为 `VDD_REF=1.1 V`，扫描感知 tap 高电平供电：

```text
VDD_A = 0.95..1.10 V
```

对真实 DFF 做：

- D=0/1 静态采样；
- setup/hold 附近采样；
- 输入高电平 DC current；
- Q correctness；
- DFF supply current。

输出：

```text
cross_domain_validation.md
```

若 Warning 区间不可靠：

- 搜索并加入标准单元接收 buffer 或 level shifter；
- 重新执行 Step 5；
- 禁止直接跳过该问题。

## Step 9：参考 RC 岛仿真

建立 `VDD_REF` RC 隔离支路。

输入使用人工 PWL droop 和共享 RLC droop 两类波形。

比较：

```text
VDD_A(t)
VDD_REF(t)
Delta_V(t)
sensor_code(t)
```

筛选条件：

- 检测窗口内 `VDD_REF` 变化远小于 `VDD_A`；
- 参考岛恢复时间可接受；
- 参考岛充放电电流不会明显扰动上游电源。

输出：

```text
reference_island_selection.json
reference_island_report.md
```

## Step 10：接入双芯粒共享 RLC 模型

将传感器连接到：

```text
Sense chain -> chiplet A local VDD_A/VSS_A
Reference chain + DFF bank -> RC reference island
Chiplet B -> existing RO-bank attack load
```

保留现有贡献一模型，不改变芯粒 A/B 主体负载定义。

测试：

- RO-bank 数量接近首次违例阈值；
- 随机攻击启动时刻；
- 不同持续时间；
- 芯粒 A 正常、busy、bursty 负载；
- 功耗随机化 macro 关闭/开启。

输出：

```text
time
ro_enable
ro_bank_count
vdd_a
vss_a
vdd_ref
vss_ref
raw_code
sensor_code
bubble_count
min_slack
violated_path_count
```

核心指标：

```text
T_warning = first time sensor_code crosses warning threshold
T_failure = first timing violation
T_lead = T_failure - T_warning
```

要求：

```text
T_lead > 0
```

## Step 11：PVT 与鲁棒性

在选定结构上执行：

```text
corners = TT, SS, FF
temperature = 25 C, 85 C
```

每个条件先运行启动校准，再评估：

- nominal code；
- warning code；
- first-violation code；
- code delta；
- bubble rate；
- sensor power。

只有在校准后仍满足码元分离，才进入后续 TCN 数据生成。

## Step 12：传感器自扰动评估

比较传感器关闭和开启：

```text
VDD_A minimum
A-side droop
sensor average power
sensor peak current
minimum slack
violated path count
```

要求：

- 传感器额外跌落显著小于目标检测跌落；
- 传感器不能改变贡献一的主要攻击结论；
- 若 DFF bank 同时翻转造成明显尖峰，需要错峰复位或降低采样率。

## Step 13：确定最终输出接口

最终安全宏前端接口建议：

```text
input  sensor_start
input  sensor_reset
input  cal_sel[2:0]
output raw_code[M-1:0]
output sensor_code[ceil(log2(M+1))-1:0]
output bubble_count
output code_valid
output sample_done
```

生成 Verilog 行为参考模型，用于 TCN 和控制器开发。

行为模型参数必须来自 SPICE 标定结果，不得使用任意固定延迟。

---

## 14. 必须生成的图表

至少生成：

1. `sense_ref_arrival_vs_stage.png`
   - 标称电压与首次违例电压下，两条边沿到达时间随级数变化；
2. `raw_code_vs_voltage.png`
   - 不同电压下原始温度计码；
3. `sensor_code_vs_voltage.png`
   - 细粒度 1.085..1.100 V 扫描；
4. `code_delta_at_failure.png`
   - 不同 M、dummy load、launch offset 的首次违例码差；
5. `bubble_rate.png`；
6. `reference_island_waveform.png`；
7. `shared_pdn_detection_timeline.png`
   - RO enable、VDD_A、VDD_REF、sensor code、warning、first violation；
8. `sensor_power_overhead.png`。

---

## 15. 最终验收标准

Phase 2 只有在以下条件全部满足后才算完成：

1. 使用真实 SMIC40LL 标准单元 CDL；
2. DFF、MUX、buffer/level shifter 单元名均来自库发现结果；
3. 标称状态经校准后：

```text
C0 in [M/2 - 1, M/2 + 1]
```

4. 首次违例电压处：

```text
abs(C_fail - C0) >= 3 preferred
abs(C_fail - C0) >= 2 minimum
```

5. Warning 点至少变化 1~2 码；
6. `1.085..1.100 V` 区间总体单调；
7. 气泡可检测，不得静默修正全部异常码；
8. 跨电压域输入在 Warning 区间可靠；
9. 共享 RLC 场景中 `T_lead > 0`；
10. 传感器自扰动和功耗有量化报告；
11. 所有脚本可复现；
12. 所有测试通过；
13. 若无可行候选，输出明确的 `NO_FEASIBLE_*` 状态而不是伪造成功。

---

## 16. Codex 执行顺序摘要

Codex 应严格按以下顺序执行：

```text
1. 复用 Phase 1 配置和工具
2. 提取 epsilon
3. 发现真实 DFF/MUX/level-shifter 单元
4. 生成无 DFF 的理想到达时间 Vernier 网表
5. 扫描 M、dummy load、launch offset、细粒度 VDD
6. 选择 3 个理想候选
7. 加入真实 DFF 比较器阵列
8. 实现码元纠错和编码器
9. 实现启动偏移校准
10. 验证跨电压域输入
11. 加入 RC 参考岛
12. 接入共享 RLC 双芯粒平台
13. 做 PVT、自扰动、提前量实验
14. 输出最终 SPICE 标定数据和 Verilog 行为接口
```

在 Step 5 之前不要直接实现完整 RTL；在 Step 7 之前不要假设 DFF 单元；在 Step 10 之前不要开始 TCN 训练。