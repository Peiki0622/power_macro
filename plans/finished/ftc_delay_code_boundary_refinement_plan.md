# FTC Delay-Code Boundary Refinement 计划

## 0. 任务定位

当前最新 `main` 提交 `6ab33b96b60b275e532ac10931b90bb3a6addd68` 已经明确证明：

```text
Programmable Acceptance Window = NO-GO
```

但这个 NO-GO 不应解释为 RVT/LVT sensor、real XOR、real DFF comparator 或 3-bit/7-MUX 架构失败。

当前根因已经收敛到 threshold tap mapping：

```text
[10,12,14,16,18,36,37,38]
                  ^
                  |
        tap18 -> tap36 物理间隔过大
```

上一阶段保证了“C_lock 之后还有两个数字 code”，但没有保证这些 code 在真实时间上仍靠近 pulse boundary。因此 code4/tap18 到 code5/tap36 一次跨过真正的 comparator boundary，后续 `C_lock+1`、`C_lock+2` 都落在过晚的 threshold 区域。

本任务只修复这一件事：

> **保持现有 sensor、real DFF、3-bit、7-MUX 和 0.80--1.10 V 正式范围不变，重新布置 8 个 threshold taps，使真实 calibration boundary 附近具有足够的物理时间分辨率，并用最小 droop 实验确认新 mapping 有资格重新进入完整 Programmable Acceptance Window characterization。**

本任务不实现最终 monitor RTL，也不进入 PVT。

---

## 1. 冻结已有证据，禁止重跑上一阶段实验

Codex 开始前读取并复用：

```text
delay_chain/ftc/reports/FTC_PROGRAMMABLE_ACCEPTANCE_WINDOW_ROOT_CAUSE.md
delay_chain/ftc/analysis/programmable_acceptance_window/attack_sweep.csv
delay_chain/ftc/analysis/programmable_acceptance_window/trip_map.csv
delay_chain/ftc/analysis/programmable_acceptance_window/summary.json
delay_chain/ftc/analysis/static_self_calibration/calibration_trace.csv
delay_chain/ftc/analysis/static_self_calibration/range_mapping.json
delay_chain/ftc/analysis/minimal_pulse_comparator/architecture.json
delay_chain/ftc/discovery/selected_cells.json
```

以下结论全部冻结，不重新证明：

```text
1. 0.80--1.10 V 是当前正式工作范围；
2. tap29 real-XOR pulse 在 TT/25 C 的正式范围内有效且随 VDD 降低单调变宽；
3. real DFF comparator 可以产生真实 Q=1 和 Q=0；
4. 3-bit balanced 8:1 MUX tree 本身工作；
5. static self-calibration 的 first-Q=0 算法工作；
6. 当前 [10,12,14,16,18,36,37,38] mapping 的 acceptance window 已经 NO-GO；
7. 旧 42 个 acceptance-window HSPICE scenarios 不得重跑。
```

也不要重新运行旧 54 个 static-self-calibration probes。

历史 runner 保持不变：

```text
delay_chain/ftc/scripts/run_static_self_calibration.py
delay_chain/ftc/scripts/run_programmable_acceptance_window.py
```

它们继续负责复现历史 GO/NO-GO，不要为了新 mapping 修改其 frozen constants。

---

## 2. 保持不变的硬件边界

本任务不得修改：

```text
Sensor tap             = tap29
Sensor initial path    = 4 RVT / 0 LVT
Threshold BUF          = BUF_X0P7M_A9TL40
Threshold MUX          = MXT2_X0P5M_A9TL40
Comparator DFF         = DFFRPQ_X0P5M_A9TR40
Sensor XOR             = XOR2_X0P5M_A9TR40
Code width             = 3 bit
Selectable taps        = 8
MUX count              = 7, balanced 8:1 tree
Supply                 = same VDD_A / VSS_A
Formal VDD range       = 0.80--1.10 V
```

不要扩展为：

```text
4-bit
coarse/fine CDL
第二条 threshold chain
第二个 sensor
TDC
PVT compensation
slow tracking
```

如果 3-bit refinement 最终失败，再单独决定是否需要扩大架构；本任务不自动救援。

---

## 3. Step 1 — 用 3 个新的 HSPICE 场景定位真实 boundary corridor

新增一个独立 runner，建议：

```text
delay_chain/ftc/scripts/run_delay_code_refinement.py
```

第一步不要测试大量 candidate mapping。

只运行：

```text
TT / 25 C
VDD = 1.10 V, 0.95 V, 0.80 V
```

总计 3 个新的 sizing HSPICE scenarios。

这三个场景继续实例化冻结的 tap29 sensor 和一条 LVT threshold chain，并把 threshold chain 至少保留到当前 tap38；但 sizing 场景不需要为每个 tap 单独运行 DFF probe。

在一个场景中同时测量：

```text
t_xor_rise
t_xor_fall
W_S_int
threshold tap 14..38 的每一级 rising arrival
```

原始 tap arrival 只用于筛选 candidate，不作为最终 comparator 结论。

定义筛选用的原始 tap 延迟：

\[
D_{\mathrm{raw}}(t,V)=t_{\mathrm{tap}}(t,V)-t_{\mathrm{xor,rise}}(V)
\]

其中：

- \(D_{\mathrm{raw}}(t,V)\)：供电电压为 \(V\) 时，threshold 物理 tap \(t\) 相对 xor_29 上升沿的原始传播延迟；
- \(t\)：threshold chain 的物理 BUF tap 编号；
- \(V\)：当前 HSPICE 供电电压；
- \(t_{\mathrm{tap}}(t,V)\)：threshold tap \(t\) 在电压 \(V\) 下第一次上升到 50% VDD 的时间；
- \(t_{\mathrm{xor,rise}}(V)\)：xor_29 在电压 \(V\) 下第一次上升到 50% VDD 的时间。

该公式只用于确定“哪些物理 taps 靠近 pulse boundary”，不能替代真实 MUX + DFF 验证。

### 利用旧数据估计 MUX 固定路径贡献

从上一阶段已有的真实 `D_code_ps` 中选择同一 VDD 下已测量的旧 tap18 路径，并与本轮 `D_raw(tap18,V)` 比较，得到一个 screening-only 的 MUX/path offset。

定义：

\[
D_{\mathrm{est}}(t,V)=D_{\mathrm{raw}}(t,V)+D_{\mathrm{mux,est}}(V)
\]

其中：

- \(D_{\mathrm{est}}(t,V)\)：候选 tap \(t\) 经现有三层 balanced MUX 后的预估总 threshold delay；
- \(D_{\mathrm{raw}}(t,V)\)：本轮 sizing HSPICE 测得的物理 tap 原始延迟；
- \(D_{\mathrm{mux,est}}(V)\)：由旧 tap18 real-DFF threshold measurement 与本轮 tap18 raw arrival 差值估计出的三层 MUX/path 延迟；
- \(t\)：候选 threshold tap 编号；
- \(V\)：当前供电电压。

该公式只用于离线筛选 8-tap candidate。最终任何 GO/NO-GO 都必须来自真实 balanced MUX + real DFF HSPICE。

输出：

```text
delay_chain/ftc/analysis/delay_code_refinement/tap_screen.csv
```

至少记录每个 VDD 下 tap14..38 的 `D_raw`、估算的 `D_est` 和真实 `W_S_int`。

---

## 4. Step 2 — 只生成 1 个 primary mapping，最多 1 个 fallback mapping

不要做大规模组合优化，也不要搜索 cell family。

根据 Step 1 的三个电压锚点，只从真实 boundary corridor 附近选 8 个严格递增 taps。

### candidate mapping 的原则

```text
1. 不再固定 code0..4 = [10,12,14,16,18]；
2. 不再使用旧 0.75 V sizing 作为新 mapping 的目标；
3. 优先让 8 个 code 覆盖 1.10 V boundary 到 0.80 V boundary 的移动区间；
4. boundary 附近优先使用相邻或少量 BUF 间隔，禁止再次出现类似 18-stage 的大洞；
5. 必须为最低 0.80 V 的正常 boundary 保留两个更长 code；
6. 必须为最高 1.10 V 的正常 boundary 保留至少一个更短 code；
7. 不追求数学等间隔，也不追求面积最优；先保证 boundary-centered physical resolution。
```

Codex 只生成：

```text
primary mapping
```

如果 primary 后面的真实 Gate 失败，才允许再生成：

```text
1 个 fallback mapping
```

最多两次 candidate，不允许无限调参。

把 candidate 写到：

```text
delay_chain/ftc/analysis/delay_code_refinement/candidate_mapping.json
```

此文件只是 candidate，不覆盖历史：

```text
delay_chain/ftc/analysis/static_self_calibration/range_mapping.json
```

---

## 5. Step 3 — 对 candidate 做最小真实 DFF calibration Gate

candidate 必须使用真实：

```text
threshold BUF chain
balanced 7-MUX tree
real DFF
real XOR29 sensor
```

验证电压：

```text
0.80, 0.85, 0.90, 0.95, 1.00, 1.05, 1.10 V
```

不要对每个 VDD 重新扫完整 0..7。

先利用 Step 1 的 estimated boundary 预测每个 VDD 的 first-zero code `k`，然后每个 VDD 只运行：

```text
code k-1
code k
code k+1
code k+2
```

如果预测 `k` 不在 1..5，candidate 直接失败。

每个 VDD 的物理 Gate 必须满足：

```text
Q(k-1) = 1
Q(k)   = 0
Q(k+1) = 0
Q(k+2) = 0

D(k-1) < D(k) < D(k+1) < D(k+2)
```

这里：

- `k`：当前 VDD 下 candidate mapping 的真实 first-zero code；
- `Q(k-1)`：first-zero 前一个 code 的真实 DFF 输出；
- `Q(k)`：first-zero code 的真实 DFF 输出；
- `Q(k+1)`：第一个上侧 margin code 的真实 DFF 输出；
- `Q(k+2)`：第二个上侧 margin code 的真实 DFF 输出；
- `D(...)`：相应 code 通过真实 balanced MUX 到达 DFF CK 的实际 HSPICE delay。

这些条件表示：真实正常边界被相邻 code bracket，并且 boundary 上方确实还有两个更长、正常时不误报的物理 threshold。

若 primary mapping 在任一 VDD 失败，允许使用 Step 2 唯一一次 fallback mapping；不要修改 sensor 或增加 bit-width。

输出：

```text
delay_chain/ftc/analysis/delay_code_refinement/calibration_gate.csv
```

---

## 6. Step 4 — 在冻结新 mapping 前先做最小 acceptance feasibility

上一阶段最大的流程错误，是 mapping 在只验证“两个 code headroom”以后就被直接冻结。

本次必须在 freeze 前增加一个很小的 static-droop feasibility Gate。

只选择三个 baseline：

```text
0.85 V   -> 低压端
0.95 V   -> 中间点
1.10 V   -> 高压端
```

对每个 baseline 只检查：

```text
M = 1
M = 2
```

告警 code 定义仍保持：

\[
C_{\mathrm{alarm}}=C_{\mathrm{lock}}+M
\]

其中：

- \(C_{\mathrm{alarm}}\)：当前 candidate mapping 下 monitor probe 实际使用的 threshold code；
- \(C_{\mathrm{lock}}\)：Step 3 真实 DFF calibration 得到的 first-zero code；
- \(M\)：可编程安全裕量，本任务只取 1 或 2。

该公式本身不修改；本次修复的是相邻 code 的物理 tap 位置，使 `+1`、`+2` 真正对应 boundary 附近的时间裕量，而不是再次跨越巨大 delay gap。

### droop probe 调度

继续使用同轨静态 droop 模式，但只对这三个 baseline 做 adaptive sweep：

```text
从 baseline - 50 mV 开始
每次降低 50 mV
最低到 0.80 V
首次 Q=1 后停止 coarse sweep
只在最后 Q=0 / 首次 Q=1 之间补 10 mV refinement
```

不要重跑旧 mapping 的 42 个 acceptance-window scenarios。

新 HSPICE 只属于新 candidate mapping。

### 最小 feasibility Gate

必须满足：

```text
1. 三个 baseline 的 M=1 都在各自合法 0.80--V0 范围内出现真实 Q=1；
2. M=2 不能比 M=1 更浅触发；
3. Q 随 attack VDD 降低不能出现 0 -> 1 -> 0 回退；
4. 至少一个 baseline 的 M=1 与 M=2 trip boundary 能在 10 mV grid 上区分。
```

其中 `V0` 表示该组实验的正常 baseline 电压。

若 Step 4 失败，candidate mapping = NO-GO。

如果 primary 失败且 fallback 尚未使用，可以只对 fallback 重做 Step 3 和 Step 4；不得重新运行 Step 1 sizing。

---

## 7. 最终 Gate

### GO

只有同时满足：

```text
A. 0.80--1.10 V 七个正常锚点都通过真实 DFF boundary Gate；
B. 每个正常锚点的 C_lock 都在 code1..5；
C. C_lock+1 和 C_lock+2 在正常状态均为 Q=0 且 delay 继续增加；
D. 0.85 / 0.95 / 1.10 V 三个代表点的 M=1 均有合法范围内真实 trip；
E. M=2 ordering 正确；
F. 至少一个代表点显示可分辨的 M=1 / M=2 trip boundary。
```

则：

```text
Delay-Code Boundary Refinement = GO
Refined 3-bit Mapping = READY_FOR_FULL_ACCEPTANCE_WINDOW_CHARACTERIZATION
```

这时只发布 refined mapping，不在本任务继续跑完整六-baseline acceptance map，也不进入 PVT。

### NO-GO

如果 primary + 唯一 fallback 都失败：

```text
3-bit Boundary-Centered Mapping = NO-GO
```

停止。

不要在本任务中自动：

```text
扩 4-bit
增加第二条 delay line
加入 coarse/fine bank
改 sensor tap
改 DFF
进入 PVT
```

失败结果将作为后续是否扩展 bit-width 的依据。

---

## 8. RTL 与历史代码处理原则

当前：

```text
delay_chain/ftc/rtl/ftc_static_calibration_controller.sv
```

保持不改。

它的 first-Q=0 线性扫描策略不是当前根因；只要新 mapping 的 `C_lock` 保持在 code1..5，现有 controller 语义仍然兼容。

本任务不增加 monitor RTL。

历史 runner 也不改：

```text
run_static_self_calibration.py
run_programmable_acceptance_window.py
```

新 refinement runner 单独维护新的 candidate/refined evidence，避免破坏旧结果可复现性。

### Q readout 统一

新 runner 只使用一个统一的 Q readout 规则：

```text
readout time >= 本轮最长真实 CK crossing + 200 ps
```

200 ps 沿用当前已使用的 DFF Q-settle requirement。

不要把旧 r2 与 acceptance-window runner 的不同固定 read time 混入新结论。

---

## 9. 最小交付物

新增：

```text
delay_chain/ftc/scripts/run_delay_code_refinement.py
delay_chain/ftc/analysis/delay_code_refinement/tap_screen.csv
delay_chain/ftc/analysis/delay_code_refinement/candidate_mapping.json
delay_chain/ftc/analysis/delay_code_refinement/calibration_gate.csv
delay_chain/ftc/analysis/delay_code_refinement/acceptance_feasibility.csv
delay_chain/ftc/analysis/delay_code_refinement/summary.json
delay_chain/ftc/reports/FTC_DELAY_CODE_BOUNDARY_REFINEMENT.md
```

若最终 GO，再额外生成：

```text
delay_chain/ftc/analysis/delay_code_refinement/refined_mapping.json
```

只需要少量 pure regression tests 检查：

```text
mapping 必须 8 个严格递增 taps
3-bit / 7-MUX topology 不变
VDD 不低于 0.80 V
candidate 数量最多 primary + one fallback
Step 4 失败时禁止发布 refined_mapping.json
```

测试本身不得调用 HSPICE。

---

## 10. 本任务的宏观判断标准

不要再问：

```text
“校准以后还剩几个 code？”
```

本任务真正要回答的是：

```text
“这些 code 是否围绕真实 normal pulse boundary 分布，
并且 C_lock+1 / C_lock+2 是否真的能够在合法 droop 范围内跨越 real-DFF boundary？”
```

如果答案为 YES，才允许新的 3-bit mapping 被正式冻结，并进入下一次完整 Programmable Acceptance Window characterization。
