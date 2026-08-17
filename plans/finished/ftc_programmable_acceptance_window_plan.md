# FTC Programmable Acceptance Window 计划

## 0. 任务定位

最新 `main` 已经完成 `Static Self Calibration + Full-Range Code Headroom`，并把正式合法工作范围收敛为 **0.80 V--1.10 V**。当前已经证明：

- 真实 XOR 脉宽在 TT/25 C、0.80--1.10 V 内完整且随 VDD 降低单调增大；
- 真实 DFF comparator 可以作为 1-bit 脉宽比较器；
- 静态自校准在七个正常 VDD 锚点得到唯一 `C_lock`；
- 当前 3-bit mapping 为 `[10,12,14,16,18,36,37,38]`；
- `C_lock` 在 0.80--1.00 V 为 5，在 1.05--1.10 V 为 4；
- 每个正常工作点至少已经验证两个上侧 code 可用。

本阶段只回答下一件事：

> **以真实 `C_lock` 为本地正常基准，增加可编程 margin 后，真实 comparator 在多大的静态 voltage droop 下会报警；当前 3-bit mapping 的安全分辨率是否足以继续进入 PVT detector verification。**

本阶段是 **静态 droop acceptance-window characterization**，不是 transient glitch 实验。

不要在本任务中做 PVT、slow tracking、baseline poisoning、DVFS、P&R、TDC 或新的 delay-line 自动生成。

---

## 1. 冻结上一阶段结论，禁止复跑 Static Self Calibration

Codex 开始前只读取：

```text
delay_chain/ftc/analysis/static_self_calibration/range_mapping.json
delay_chain/ftc/analysis/static_self_calibration/calibration_trace.csv
delay_chain/ftc/analysis/static_self_calibration/summary.json
delay_chain/ftc/reports/FTC_STATIC_SELF_CALIBRATION_FULL_RANGE_HEADROOM.md
delay_chain/ftc/analysis/minimal_pulse_comparator/architecture.json
delay_chain/ftc/discovery/selected_cells.json
```

固定复用当前 mapping：

```text
code 0 -> tap10
code 1 -> tap12
code 2 -> tap14
code 3 -> tap16
code 4 -> tap18
code 5 -> tap36
code 6 -> tap37
code 7 -> tap38
```

固定复用已有 `C_lock`：

```text
0.80 V -> 5
0.85 V -> 5
0.90 V -> 5
0.95 V -> 5
1.00 V -> 5
1.05 V -> 4
1.10 V -> 4
```

不要重新运行这 54 个 calibration probe，也不要重新搜索 `C_lock`。

继续使用同一套真实 cell：

```text
Threshold BUF = BUF_X0P7M_A9TL40
Threshold MUX = MXT2_X0P5M_A9TL40
Comparator DFF = DFFRPQ_X0P5M_A9TR40
Sensor XOR = XOR2_X0P5M_A9TR40
same VDD_A / VSS_A
```

---

## 2. Acceptance Window 的最小定义

本阶段只使用两个全范围都合法的 programmable margin：

```text
M = 1
M = 2
```

告警 code 定义为：

\[
C_{\mathrm{alarm}}=C_{\mathrm{lock}}+M
\]

其中：

- \(C_{\mathrm{alarm}}\)：monitor 模式下真正送入 3-bit threshold MUX 的告警控制码；
- \(C_{\mathrm{lock}}\)：上一阶段真实 DFF 静态自校准得到的正常状态边界 code；
- \(M\)：可编程安全裕量，本阶段只取 1 或 2 个 code。

该公式表示：告警阈值不使用固定 Golden Model，而是在本芯片当前正常硬件边界之上增加一档或两档时间裕量。

运行时静态告警定义为：

\[
Alarm=Q(C_{\mathrm{alarm}})
\]

其中：

- \(Alarm\)：当前 probe 的 voltage-droop 告警位；
- \(Q(C_{\mathrm{alarm}})\)：真实 DFF 在告警 code 对应延迟边沿到来时采到的实际逻辑值；
- \(C_{\mathrm{alarm}}\)：由本地正常 `C_lock` 与可编程 margin 共同确定的阈值 code。

该公式表示：正常状态下告警 code 已在脉冲结束之后，真实 DFF 应为 0；当 VDD 降低使 XOR 脉冲相对同轨 threshold 延迟扩展到越过该边界时，真实 DFF 变为 1，直接产生告警。

### 重要范围边界

0.80 V 是当前传感器正式最低合法工作点。

因此：

- 0.80 V 只复用已有正常 `Q=0` headroom 证据；
- 不在本任务中把 VDD 降到 0.80 V 以下；
- 不声称从 0.80 V baseline 向下的 droop detection 能力。

---

## 3. Step 1 — 用当前 mapping 做真实 static-droop trip map

新增一个任务专用 runner，建议：

```text
delay_chain/ftc/scripts/run_programmable_acceptance_window.py
```

它必须复用当前真实 sensor + threshold + DFF 电路结构，但使用**冻结的 baseline `C_lock`**选择 `C_alarm`。

不要调用 Static Self Calibration FSM 去重新搜索 code。

### 正常 baseline

使用：

```text
V0 = 0.85, 0.90, 0.95, 1.00, 1.05, 1.10 V
M  = 1, 2
```

其中：

- `V0`：可信校准完成时的正常工作电压；
- `M`：可编程安全裕量 code 数。

0.80 V baseline 不新增 attack HSPICE；其正常 headroom 直接复用上一阶段。

### 每组 `(V0, M)` 的最小 sweep

1. 从 `V0 - 0.05 V` 开始，每次降低 50 mV；
2. 最低只到 0.80 V；
3. 一旦真实 `Q` 第一次变成 1，停止继续向更低电压粗扫；
4. 只在最后一个 `Q=0` 与第一个 `Q=1` 之间补 10 mV 点，找到 10 mV 分辨率的 trip boundary；
5. 如果一直到 0.80 V 仍然 `Q=0`，记录 `NO_IN_RANGE_TRIP`，不要向 0.80 V 以下扩展。

不要做完整二维矩形 sweep，也不要重复已经存在的 normal calibration scenarios。

### 每个新 HSPICE scenario 至少记录

```text
baseline_vdd_v
attack_vdd_v
margin_code
lock_code
alarm_code
selected_tap
W_S_int_ps
D_alarm_ps
Q
alarm
```

这里的 `baseline_vdd_v` 只用于选择冻结的 `C_lock`；物理 HSPICE scenario 的供电使用 `attack_vdd_v`，从而真实包含 sensor 与同轨 threshold 在 droop 下同时变化的效应。

输出：

```text
delay_chain/ftc/analysis/programmable_acceptance_window/attack_sweep.csv
```

---

## 4. Step 2 — 提取每个 margin 的最小可检测静态 droop

对于每个 `(V0, M)`，定义：

\[
\Delta V_{\mathrm{trip}}=V_0-V_{\mathrm{trip}}
\]

其中：

- \(\Delta V_{\mathrm{trip}}\)：当前 margin 下使真实 DFF 首次稳定产生告警的最小静态电压跌落幅度；
- \(V_0\)：该组实验对应的正常 baseline 电压；
- \(V_{\mathrm{trip}}\)：10 mV refinement 后仍使真实 `Q=1` 的最高 attack VDD，也就是最靠近正常状态的实际 trip 电压。

该公式表示：安全 margin 最终必须映射到实际可检测的 voltage-droop 深度，而不能只说“多了一个 code”。

生成：

```text
delay_chain/ftc/analysis/programmable_acceptance_window/trip_map.csv
```

至少包含：

```text
baseline_vdd_v
lock_code
margin_code
alarm_code
trip_status
trip_vdd_v
trip_depth_mv
```

### 必须检查 programmable ordering

当 `M=1` 和 `M=2` 都存在 in-range trip 时，要求更大的 margin 不能比更小的 margin 更早报警。

也就是结果应满足：

```text
trip_depth(M=2) >= trip_depth(M=1)
```

这里：

- `trip_depth(M=2)`：安全裕量为两个 code 时测得的最小静态 droop 深度；
- `trip_depth(M=1)`：安全裕量为一个 code 时测得的最小静态 droop 深度。

该关系表示：增加安全裕量应该降低检测灵敏度，而不能出现 margin 越大反而越敏感的异常排序。

---

## 5. Step 3 — 判断“机制成立”与“当前 mapping 分辨率足够”

不要把这两个结论混成一个。

### A. Acceptance mechanism GO

满足以下条件即可说明可编程接受窗口机制本身成立：

```text
1. 上一阶段已有 normal evidence 中，C_alarm 对应 Q=0，不产生正常误报；
2. 对每个 V0 > 0.80 V，M=1 在不低于 0.80 V 的范围内至少存在一个真实 Q=1 trip；
3. M=2 不得出现比 M=1 更浅的 trip；
4. attack sweep 中 Q 随 VDD 降低不能出现 0 -> 1 -> 0 的反复翻转。
```

若这些条件失败：

```text
Programmable Acceptance Window mechanism = NO-GO
```

停止，不增加复杂硬件。

### B. Current 3-bit mapping 是否足以进入 PVT detector verification

在机制 GO 的前提下，再检查当前 `[10,12,14,16,18,36,37,38]` mapping 是否过粗。

使用一个简单、与既有实验一致的灵敏度门限：

```text
V0 = 0.90--1.10 V:
M=1 必须在 <= 100 mV droop 内产生 trip

V0 = 0.85 V:
M=1 必须在 <= 50 mV droop 内产生 trip
```

原因是 0.85 V 到正式最低 0.80 V 只有 50 mV 合法空间，而 0.90 V 及以上至少有 100 mV 的合法向下空间。

同时要求 `M=1` 与 `M=2` 的 trip boundary 在至少一个工作点上能够被 10 mV grid 区分；否则虽然数字 code 不同，但当前安全灵敏度等级没有显示出可测的可编程差异。

### 最终分类

如果机制成立且当前 mapping 通过上述灵敏度/区分度检查：

```text
Programmable Acceptance Window = GO
Current 3-bit Mapping = READY_FOR_PVT_DETECTOR_VERIFICATION
```

如果机制成立但当前 mapping 过粗：

```text
Programmable Acceptance Window = GO
Current 3-bit Mapping = REFINEMENT_REQUIRED
```

这种情况下本任务到此停止。不要在同一个任务里自动扩成 4-bit、coarse/fine CDL 或重新搜索 topology；下一步单独制定一个很窄的 delay-code refinement plan。

---

## 6. Step 4 — 只有 mapping READY 时增加最小 monitor RTL

只有 Step 3 判定为 `READY_FOR_PVT_DETECTOR_VERIFICATION` 时，才增加最小 acceptance-window 控制逻辑。

它只需要：

```text
input  lock_code[2:0]
input  margin_sel        // 0 -> M=1, 1 -> M=2
input  q_compare
output alarm_code[2:0]
output alarm
```

功能仅为：

```text
margin_sel=0 -> alarm_code = lock_code + 1
margin_sel=1 -> alarm_code = lock_code + 2
alarm = q_compare during completed monitor probe
```

用 `attack_sweep.csv` 中真实 HSPICE Q trace 做 RTL replay 测试即可。

不要在本阶段加入：

```text
slow tracking
majority voting
baseline update
attack freeze
DVFS table
PVT compensation
```

---

## 7. 最小交付物

只需要：

```text
delay_chain/ftc/analysis/programmable_acceptance_window/attack_sweep.csv
delay_chain/ftc/analysis/programmable_acceptance_window/trip_map.csv
delay_chain/ftc/analysis/programmable_acceptance_window/summary.json
delay_chain/ftc/reports/FTC_PROGRAMMABLE_ACCEPTANCE_WINDOW.md
```

若且仅若 mapping READY，再提交最小 monitor RTL 和 trace-driven test。

报告只回答四个问题：

1. `C_lock + M` 的真实 DFF acceptance-window 机制是否成立？
2. `M=1` 和 `M=2` 分别对应多大的静态 droop trip depth？
3. 当前 `[10,12,14,16,18,36,37,38]` mapping 的安全分辨率是否足够？
4. 下一阶段是进入 PVT detector verification，还是先做一次窄的 delay-code refinement？

本任务不要重跑上一阶段 Static Self Calibration，也不要把 0.80 V 以下重新纳入正式工作范围。
