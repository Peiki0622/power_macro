# FTC 最小可编程时间阈值 + 硬件脉宽比较器计划

## 0. 任务定位

最新结果已经关闭：

```text
Passive Sensitivity-Contrast Reference = NO-GO
```

因此本阶段不再要求 reference 被动抵消温度。reference 的职责收敛为：

```text
产生可编程时间阈值
```

本阶段只验证两个最基础的硬件事实：

1. 一个很小的标准单元可编程延迟结构能否产生随 code 单调变化的时间阈值；
2. tap29 真实 XOR 脉冲能否通过“延迟后的自身上升沿采样自身电平”得到 1-bit 脉宽比较结果。

比较关系为：

\[
Q(C)=
\begin{cases}
1,&W_{S,\mathrm{int}}>D(C)\\
0,&W_{S,\mathrm{int}}<D(C)
\end{cases}
\]

其中：

- \(Q(C)\)：控制码为 \(C\) 时真实 DFF 的比较输出；
- \(C\)：可编程时间阈值的数字控制码；
- \(W_{S,\mathrm{int}}\)：加入真实 comparator 负载以后，集成电路中的 tap29 XOR 高电平脉宽；
- \(D(C)\)：控制码为 \(C\) 时，从 tap29 XOR 上升沿到 DFF 时钟上升沿的实际传播延迟。

该公式表示：延迟后的 XOR 上升沿到达 DFF 时，如果原 XOR 脉冲还为高电平，输出应采到 1；如果原 XOR 脉冲已经结束，输出应采到 0。

本阶段**不实现**：

```text
self-calibration FSM
C_lock 搜索算法
programmable acceptance window
alarm margin
slow tracking
PVT campaign
DVFS
P&R
configuration skip
TDC
```

本阶段结束后只回答：

```text
Minimal programmable threshold + physical pulse-width comparator = GO / NO-GO ?
```

---

## 1. 冻结并复用已有证据，禁止重跑旧仿真

Codex 开始前读取：

```text
delay_chain/ftc/ftc_config.json
delay_chain/ftc/discovery/selected_cells.json
delay_chain/ftc/analysis/real_xor_pulse_width/fine.csv
delay_chain/ftc/analysis/reference_sensitivity_contrast/candidate_manifest.csv
delay_chain/ftc/analysis/reference_sensitivity_contrast/simple_candidate_screen.csv
delay_chain/ftc/reports/FTC_COMPOSITE_REFERENCE_SENSITIVITY_SHAPING.md
```

已有 cell 直接复用：

```text
sensor delay LVT = BUF_X0P7M_A9TL40
sensor delay RVT = BUF_X0P7M_A9TR40
sensor XOR       = XOR2_X0P5M_A9TR40
DFF              = DFFRPQ_X0P5M_A9TR40
```

DFF 已在 `selected_cells.json` 中确认：

```text
positive-edge triggered
active-high asynchronous clear
```

可编程延迟结构需要的 LVT MUX 不重新搜索整个 PDK，直接从上一阶段 `candidate_manifest.csv` 中读取已经 functionally verified 的 `mux_lvt` cell；若该 manifest 中的 cell 与 CDL/Verilog 文件不一致，停止并报告，不另找新 family。

### 禁止复跑

不要重新运行：

```text
36-point real-XOR VDD sweep
PVT baseline
simple reference campaign
composite reference prediction
phase-diverse / wavefront / old glitch experiments
```

本阶段允许的新 HSPICE 只有：

```text
frozen tap29 sensor + 新 programmable delay + 新 DFF comparator
```

这属于新的集成电路实验，不是旧 sensor 实验的重复运行。

---

## 2. Step 1 — 实现一个固定、很小的 3-bit tapped-delay threshold

不要先做通用 CDL generator。

第一版结构固定为：

```text
xor_29
  |
  +--> LVT BUF chain ------------------------------------+
  |                                                      |
  |      tap10 tap12 tap14 tap16 tap18 tap20 tap22 tap24 |
  |        |     |     |     |     |     |     |     |   |
  |        +-----+-----+-----+-----+-----+-----+-----+---+
  |                         |
  |                  balanced 8:1 LVT MUX tree
  |                         |
  |                         +----> CK of DFF
  |
  +--------------------------------> D of DFF
```

要求：

```text
BUF chain = 24 x BUF_X0P7M_A9TL40
selectable taps = 10,12,14,16,18,20,22,24 stages
MUX tree = balanced 8:1, three identical 2:1 LVT MUX levels
code C = 0..7 maps in increasing order to those eight taps
DFF = existing DFFRPQ_X0P5M_A9TR40
DFF reset = high initially, released well before xor_29 first rising edge
all cells use the same VDD_A / VSS_A as the sensor
```

不要加入独立 reference rail、Vref、额外 clock、counter 或 TDC。

这个 tap 范围不是重新优化出来的复杂参数。它只利用上一阶段已有的单元延迟量级，让 1.10 V 与 0.90 V 的正常 tap29 脉宽大概率都落入 8 个 code 的覆盖范围。若真实集成后其中一个工作点没有被 8 个 code bracket，本任务直接报告 range 不足，不在本任务里反复改 tap 数量。

### 时间阈值的真实定义

\[
D(C)=t_{\mathrm{CK},\uparrow}(C)-t_{\mathrm{XOR},\uparrow}
\]

其中：

- \(D(C)\)：控制码 \(C\) 对应的真实时间阈值；
- \(C\)：3-bit 控制码，取值为 0 到 7；
- \(t_{\mathrm{CK},\uparrow}(C)\)：控制码 \(C\) 时 DFF 时钟端第一次上升到 50% VDD 的时间；
- \(t_{\mathrm{XOR},\uparrow}\)：tap29 XOR 输出第一次上升到 50% VDD 的时间；
- 符号 \(\uparrow\)：表示上升沿。

该公式表示：真正用于比较的阈值不是“BUF 数量乘单元延迟”的估计值，而是从真实 XOR 上升沿到真实 DFF CK 上升沿的 HSPICE 测量值。

### 集成后的 sensor 脉宽定义

\[
W_{S,\mathrm{int}}=t_{\mathrm{XOR},\downarrow}-t_{\mathrm{XOR},\uparrow}
\]

其中：

- \(W_{S,\mathrm{int}}\)：加入 delay-line 与 DFF 负载以后真实 tap29 XOR 的高电平脉宽；
- \(t_{\mathrm{XOR},\downarrow}\)：tap29 XOR 输出第一次下降到 50% VDD 的时间；
- \(t_{\mathrm{XOR},\uparrow}\)：tap29 XOR 输出第一次上升到 50% VDD 的时间；
- 符号 \(\downarrow\)：表示下降沿；
- 符号 \(\uparrow\)：表示上升沿。

该公式用于确认 comparator 的真实负载是否改变了原先的脉宽，而不是假设 frozen `fine.csv` 在加负载以后完全不变。

---

## 3. Step 2 — 只在 TT / 25 C 跑两个工作点的完整 8-code sweep

只运行：

```text
corner = TT
temperature = 25 C
VDD = 1.10 V, 0.90 V
code = 0..7
```

总计：

```text
2 VDD x 8 code = 16 integrated HSPICE scenarios
```

不要增加 0.75 V、PVT 或 fine VDD sweep。

每个 scenario 至少测：

```text
t_xor_rise
t_xor_fall
W_S_int
t_ck_rise
D_code
Q_final
```

其中 `Q_final` 在 DFF 第一次采样边沿之后留出固定的短 settle interval 再读取逻辑电平即可；不要在本阶段设计 metastability monitor、双采样器或 synchronizer。

同时从已有 `fine.csv` 读取同 VDD 下 frozen `W_real`，只用于记录集成负载带来的脉宽变化：

\[
\Delta W_{\mathrm{load}}=W_{S,\mathrm{int}}-W_{S,\mathrm{frozen}}
\]

其中：

- \(\Delta W_{\mathrm{load}}\)：加入 programmable threshold 和 DFF 后 tap29 脉宽相对旧独立 sensor 结果的变化量；
- \(W_{S,\mathrm{int}}\)：当前集成 comparator 电路中重新测得的 tap29 XOR 脉宽；
- \(W_{S,\mathrm{frozen}}\)：已有 `fine.csv` 中相同 VDD、TT、25 C 条件下的 tap29 真实 XOR 脉宽。

该公式只用于量化新负载影响，不要求 \(\Delta W_{\mathrm{load}}\) 等于零。

输出：

```text
delay_chain/ftc/analysis/minimal_pulse_comparator/code_sweep.csv
```

---

## 4. Step 3 — 只检查两个核心物理性质

### 4.1 可编程阈值是否单调

对每个 VDD，要求：

\[
D(C+1)>D(C)
\]

其中：

- \(D(C+1)\)：下一个控制码对应的真实时间阈值；
- \(D(C)\)：当前控制码对应的真实时间阈值；
- \(C\)：当前 3-bit 控制码，且只在 0 到 6 的相邻 code 比较中使用。

该公式表示：code 增大时，DFF 采样时刻必须向后移动；否则后续自校准无法基于 code 顺序搜索。

### 4.2 DFF 是否真的实现脉宽比较

对每个 code，用真实测量的 \(W_{S,\mathrm{int}}\) 与 \(D(C)\) 预测比较结果，再与真实 DFF 输出比较：

\[
Q_{\mathrm{expected}}(C)=1\quad\text{when}\quad W_{S,\mathrm{int}}>D(C)
\]

其中：

- \(Q_{\mathrm{expected}}(C)\)：根据真实时间关系预测的 DFF 输出；
- \(C\)：当前 3-bit 控制码；
- \(W_{S,\mathrm{int}}\)：当前 integrated sensor 的真实 tap29 XOR 脉宽；
- \(D(C)\)：当前 code 对应的真实 DFF 采样延迟。

该公式表示：当采样边沿到达以前 XOR 脉冲还没有结束时，DFF 应采到逻辑 1。

\[
Q_{\mathrm{expected}}(C)=0\quad\text{when}\quad W_{S,\mathrm{int}}<D(C)
\]

其中：

- \(Q_{\mathrm{expected}}(C)\)：根据真实时间关系预测的 DFF 输出；
- \(C\)：当前 3-bit 控制码；
- \(W_{S,\mathrm{int}}\)：当前 integrated sensor 的真实 tap29 XOR 脉宽；
- \(D(C)\)：当前 code 对应的真实 DFF 采样延迟。

该公式表示：当采样边沿到达时 XOR 脉冲已经结束，DFF 应采到逻辑 0。

如果某一个 code 恰好非常靠近翻转边界，只记录它处于 comparator aperture 附近；不要因此增加复杂 metastability 电路。本阶段只需要相邻较早 code 与较晚 code 的物理判决方向正确。

---

## 5. 最终 Gate

### GO

必须同时满足：

```text
1. 1.10 V 下 D(code) 随 code 严格递增；
2. 0.90 V 下 D(code) 随 code 严格递增；
3. 1.10 V 下 8 个 code 中存在脉宽比较翻转边界；
4. 0.90 V 下 8 个 code 中存在脉宽比较翻转边界；
5. 除紧邻翻转边界的 comparator aperture 外，真实 DFF Q 与 W_S_int / D(code) 的时间关系一致。
```

则：

```text
Minimal Programmable Threshold + Pulse-Width Comparator = GO
```

下一阶段才进入：

```text
Static Self Calibration
```

即让数字控制逻辑自动寻找比较输出的翻转 code。

### NO-GO

如果出现以下任一核心问题：

```text
D(code) 明显非单调
8 个 code 在任一主要工作点完全无法 bracket W_S_int
真实 DFF 判决与物理时间关系大范围不一致
```

则本阶段 NO-GO。

不要在本任务中继续增加：

```text
更多 coarse/fine delay bank
第二条 delay line
TDC
多级 synchronizer
tracking FSM
复杂校准逻辑
```

先根据失败类型重新定义下一阶段。

---

## 6. 最小输出

新增一个任务专用 runner，建议：

```text
delay_chain/ftc/scripts/run_minimal_pulse_comparator.py
```

只提交 compact evidence：

```text
delay_chain/ftc/analysis/minimal_pulse_comparator/architecture.json
delay_chain/ftc/analysis/minimal_pulse_comparator/code_sweep.csv
delay_chain/ftc/analysis/minimal_pulse_comparator/summary.json
delay_chain/ftc/analysis/minimal_pulse_comparator/threshold_vs_pulse.svg
delay_chain/ftc/reports/FTC_MINIMAL_PROGRAMMABLE_THRESHOLD_PULSE_COMPARATOR.md
```

`architecture.json` 至少记录：

```text
BUF cell
MUX cell
DFF cell
tap list
code-to-tap mapping
same-rail VDD/VSS mapping
```

`threshold_vs_pulse.svg` 只需要画两个 VDD 下的：

```text
D(code)
W_S_int
Q(code)
```

不要额外生成大量图。

HSPICE `.lis/.tr0` 等 bulk 文件继续留在 ignored `runs/**` 下，不提交。

报告只回答三个问题：

1. 真实标准单元可编程 delay 是否产生单调 `D(code)`？
2. 真实 DFF 是否实现了 `W_S_int > D(code)` 的 1-bit 脉宽比较？
3. 这个硬件 primitive 是否足以进入下一阶段的 static self-calibration？
