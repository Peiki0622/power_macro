# FTC Static Self Calibration + 0.75--1.10 V Code Headroom 计划

## 0. 任务定位

最新 `main` 已经完成 `Minimal Programmable Threshold + Pulse-Width Comparator`，结论为 `GO`。当前真实电路已经证明：

- tap29 真实 XOR 可以同时驱动 DFF 数据端和可编程延迟路径；
- 3-bit tapped delay 在 1.10 V 和 0.90 V 下都保持单调；
- 真实 DFF 输出存在唯一的 1 -> 0 硬件翻转；
- 新 comparator 对 tap29 脉宽只造成几 ps 级负载变化；
- 真实 DFF 翻转位置与单纯 50% crossing 的数学交点可以相差一个 code，因此后续校准必须以真实 DFF 输出为准。

当前结构的主要不足也已经明确：0.90 V 正常状态的真实 DFF 翻转已经接近最高 code，后续没有足够的 programmable security margin。

本阶段只做两件事：

1. 实现 **Static Self Calibration（静态自校准）**：可信启动阶段自动扫描真实 comparator，得到本芯片当前正常状态的硬件边界 code；
2. 在设计电压范围 **0.75 V--1.10 V** 内重新安排最小 delay range，使正常校准完成后仍保留至少两个更长延迟 code，供下一阶段 Programmable Acceptance Window 使用。

本阶段不检测 transient droop，不做 PVT，不做 slow tracking，不做最终 acceptance window。

---

## 1. 冻结上一阶段 GO，禁止重跑旧 16 个场景

Codex 开始前只读取并复用：

```text
delay_chain/ftc/analysis/minimal_pulse_comparator/architecture.json
delay_chain/ftc/analysis/minimal_pulse_comparator/code_sweep.csv
delay_chain/ftc/analysis/minimal_pulse_comparator/summary.json
delay_chain/ftc/reports/FTC_MINIMAL_PROGRAMMABLE_THRESHOLD_PULSE_COMPARATOR.md
delay_chain/ftc/analysis/real_xor_pulse_width/fine.csv
delay_chain/ftc/discovery/selected_cells.json
```

上一阶段 1.10 V / 0.90 V × 8 code 的 16 个 HSPICE 场景已经完成，不要为了本任务重新运行原来的 24-BUF / taps 10--24 结构。

继续固定使用：

```text
Threshold BUF = BUF_X0P7M_A9TL40
Threshold MUX = MXT2_X0P5M_A9TL40
Comparator DFF = DFFRPQ_X0P5M_A9TR40
Sensor XOR = XOR2_X0P5M_A9TR40
same VDD_A / VSS_A
```

不要重新搜索 cell family。

---

## 2. 自校准的唯一硬件判据

自校准结果定义为：

\[
C_{\mathrm{lock}}=\min\{C\mid Q(C)=0\}
\]

其中：

- \(C_{\mathrm{lock}}\)：静态自校准最终保存的正常状态控制码；
- \(C\)：当前被测试的可编程时间阈值控制码；
- \(Q(C)\)：控制码为 \(C\) 时真实 DFF 的采样输出；
- \(Q(C)=0\)：表示真实 DFF 已经在该 code 对应的采样时刻采到低电平；
- \(\min\)：从低 code 向高 code 扫描时，选择第一个满足条件的 code。

该公式表示：自校准直接寻找真实 DFF 的 1 -> 0 翻转，不再通过软件求 `W_S_int = D(code)` 的数学交点，也不恢复绝对 ps 脉宽。

后续安全裕量需要的上侧 code headroom 定义为：

\[
H_{\mathrm{up}}=C_{\max}-C_{\mathrm{lock}}
\]

其中：

- \(H_{\mathrm{up}}\)：自校准结束后，正常基准以上仍剩余的更长延迟 code 数量；
- \(C_{\max}\)：当前可编程时间阈值结构的最大合法控制码；
- \(C_{\mathrm{lock}}\)：当前工作电压下静态自校准得到的正常状态控制码。

该公式表示：自校准之后还剩多少 code 可以留给下一阶段的 programmable security margin。

本阶段固定最低要求：

\[
H_{\mathrm{up}}\ge 2
\]

其中：

- \(H_{\mathrm{up}}\)：正常校准 code 以上剩余的可用 code 数量；
- 数值 2：至少保留两个更长延迟档位，作为下一阶段可编程安全裕量的最低 prototype 要求。

该公式表示：0.75 V--1.10 V 范围内，任何被验证的正常工作点都不能再次出现“正常状态已经顶到最高 code”的情况。

---

## 3. Step 1 — 只做一次 0.75 V range sizing，然后冻结新的 8-code mapping

优先保持上一阶段最简单的结构：

```text
3-bit code
8 selectable taps
7-cell balanced 8:1 MUX tree
1 real DFF
```

不要立即扩展到 4-bit，也不要做 coarse/fine CDL。

### 3.1 新增一个 0.75 V sizing 场景

只在：

```text
TT / 25 C / VDD = 0.75 V
```

增加一个新的 sizing HSPICE 场景。

它继续使用真实 tap29 sensor 和同轨 LVT threshold chain，但只用于测量当前高端 tap 的传播趋势。至少记录：

```text
W_S_int
threshold arrival at tap 10,12,14,16,18,20,22,24
current code7 DFF result
```

这不是重跑上一阶段，因为 0.75 V 从未进入上一阶段的 integrated comparator 验证。

### 3.2 根据已有数据只延长 BUF chain，不改变基本拓扑

用：

- 已有 1.10 V / 0.90 V integrated `D(code)`；
- 新的 0.75 V sizing 数据；
- 已有 `fine.csv` 中 0.75--1.10 V 的冻结 sensor 脉宽曲线；

离线选择新的 8 个 tap。

设计原则：

```text
保留 3-bit / 8-code / balanced MUX
允许 tap 间距非均匀
优先保留原有低端 tap
只把高端 tap 延伸到满足 0.75 V 正常边界 + 2-code headroom 所需的最短位置
```

不要为了“更平滑”增加多余 BUF，也不要搜索不同标准单元。

新的 mapping 在进入下一步前必须冻结到一个小 JSON，例如：

```text
delay_chain/ftc/analysis/static_self_calibration/range_mapping.json
```

如果 8 个 code 无法同时覆盖 1.10 V 正常边界和 0.75 V 正常边界并留下两个上侧 code，本阶段报告：

```text
3-bit range = insufficient
```

然后停止；不要在同一任务中自动扩展 4-bit 架构。

---

## 4. Step 2 — 用新的固定 mapping 在 0.75--1.10 V 内执行真实静态自校准

只验证 TT / 25 C，不进入 PVT。

使用以下正常工作电压锚点：

```text
0.75 V
0.80 V
0.85 V
0.90 V
0.95 V
1.00 V
1.05 V
1.10 V
```

这些点覆盖本 macro 当前定义的合法检测电压范围。

### 每个 VDD 的校准流程

对每个正常工作电压：

```text
code = 0
  -> code stable
  -> reset DFF
  -> launch one isolated probe
  -> read real Q
  -> if Q=1: code += 1 and repeat
  -> first Q=0: save C_lock
```

找到 `C_lock` 后，只额外验证 `C_lock+1` 和 `C_lock+2` 两个 code 的真实 DFF 输出和延迟顺序，用来确认上侧 headroom；不要继续扫完整个 code 空间。

其中 code update 与 probe 必须时间分离：

```text
update code
wait fixed settle interval
reset DFF
launch probe
read Q
```

不要在 XOR pulse 正在传播时切换 MUX code。

### 每个工作点保存

```text
vdd_v
step_index
code
selected_tap
Q
D_code_ps
W_S_int_ps
is_lock
headroom_verified
```

输出：

```text
delay_chain/ftc/analysis/static_self_calibration/calibration_trace.csv
```

本阶段不要重复输出上一阶段的旧 code sweep。

---

## 5. Step 3 — 静态自校准 + full-range headroom Gate

每个 0.75--1.10 V 锚点都必须形成唯一的 1 -> 0 硬件边界，并满足：

\[
1\le C_{\mathrm{lock}}\le C_{\max}-2
\]

其中：

- \(C_{\mathrm{lock}}\)：该正常工作电压下真实 DFF 自校准得到的第一个 0 code；
- \(C_{\max}\)：3-bit 结构能够使用的最大控制码，当前为 7；
- 下界 1：正常边界以下至少存在一个更早的 code，使校准具有实际 bracket；
- 上界 \(C_{\max}-2\)：正常边界以上至少保留两个更长延迟 code。

该公式表示：每个被验证的合法工作电压都必须同时具备“可找到正常边界”和“边界以上仍有安全裕量空间”两个条件。

同时要求：

```text
1. 扫描过程中 Q 只允许从 1 变 0，不允许重新回到 1；
2. 新 mapping 的实际 D(code) 在被扫描到的 code 上保持严格递增；
3. C_lock+1 和 C_lock+2 两个 headroom code 都真实存在并且延迟继续增加；
4. comparator 加载后 W_S_int 仍然形成有效完整 pulse。
```

不要求 `C_lock` 随 VDD 呈严格线性，也不人为要求它每 50 mV 必须移动固定 code 数；自校准的意义正是允许每个工作点自行找到本地边界。

### GO

如果所有 0.75--1.10 V 锚点均通过，则：

```text
Static Self Calibration + Full-Range Code Headroom = GO
```

下一阶段才进入：

```text
Programmable Acceptance Window
```

### NO-GO

如果出现：

```text
某个工作点无法 bracket
某个工作点 C_lock 顶到最后两个 code
新 mapping 出现实际延迟非单调
真实 Q 出现多次 1/0 翻转
```

则本阶段 NO-GO。

只报告失败原因；不要在本任务中继续增加 bit-width、第二条 delay line 或复杂搜索逻辑。

---

## 6. Step 4 — 只在电气 Gate 通过后增加最小可综合校准控制逻辑

只有 Step 3 为 GO 时，再增加一个最小 controller。

功能只需要：

```text
START
SET_CODE
WAIT_SETTLE
PROBE
READ_Q
DONE
```

接口只需要能够表达：

```text
start
probe_req
probe_done / sample_valid
q_compare
code[2:0]
lock_code[2:0]
done
```

控制算法就是线性递增 code，直到第一次读取 `q_compare=0`，然后保存 `lock_code`。

不要实现：

```text
binary search
SAR
majority voting
runtime tracking
attack freeze
acceptance margin
DVFS state table
```

用 `calibration_trace.csv` 中真实 HSPICE 得到的 Q 序列做 RTL 单元测试，确认 controller 对八个 VDD 锚点都得到与物理实验一致的 `lock_code`。

本阶段不要求 gate-level synthesis 或 transistor-level FSM co-simulation；数字控制逻辑只需要证明是简单、可综合、与真实 comparator trace 一致的闭环算法。

---

## 7. 最小结果文件

只提交：

```text
delay_chain/ftc/analysis/static_self_calibration/range_mapping.json
delay_chain/ftc/analysis/static_self_calibration/calibration_trace.csv
delay_chain/ftc/analysis/static_self_calibration/summary.json
delay_chain/ftc/reports/FTC_STATIC_SELF_CALIBRATION_FULL_RANGE_HEADROOM.md
```

若电气 Gate 通过，再提交最小 controller 和对应测试。

报告只回答四个问题：

1. 新 3-bit tap mapping 是否覆盖 0.75--1.10 V 的正常工作范围？
2. 真实 DFF 驱动的静态自校准是否在每个 VDD 锚点自动找到唯一 `C_lock`？
3. 每个工作点校准后是否至少保留两个更长延迟 code？
4. 是否可以进入下一阶段 Programmable Acceptance Window？

不要在本任务中运行：

```text
旧 16-scenario comparator regression
PVT sweep
transient droop attack
slow tracking
baseline poisoning
DVFS
P&R
configuration skip
TDC
```

本阶段的宏观目标只有一个：

```text
让每个合法正常 VDD 自己找到真实硬件边界，
同时保证这个边界不会吃掉后续 security margin 的 code 空间。
```
