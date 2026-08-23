# FTC M0 检测裕量与电压灵敏度表征逐阶段推进计划

**仓库：** `Peiki0622/power_macro`  
**目标分支：** `main`  
**M0 输入基线：** `6c45dc4c8daa0146d96a3d68bf0accda8c44b452`  
**阶段定位：** H0 校准→检测控制权切换闭合之后、可编程检测裕量 RTL 和检测状态机之前。  

## 0. M0 的唯一核心目标

M0 不写检测状态机，也不先假定 `F_det = F_cal + ΔF`。本阶段只回答：

> 当前冻结的 `N=16 中调路径选择 + BUF_X0P8M_A9TL40/NOR2_X4A_A9TL40 K=10 细调 + 真实 XOR + 真实 DFF` 结构，在启动校准结束后，是否存在可利用的电压检测裕量；若存在，建立 `(M,F) -> 时间裕量 -> 静态 Vtrip -> 可检测跌落深度` 的定量映射，并输出可以直接用于 SCI 论文的图表证据。

正式冻结的三个启动校准锚点为：

```text
0.80 V -> M7/F6
0.95 V -> M4/F6
1.10 V -> M2/F9
```

H0 已通过正确时序纠偏，其中 `S_CLK_RISE -> Q_SAMPLE_1` 剩余物理余量约 `+0.03 ns`。因此 M0 **不得**在 CAL→`sense_s_clk` 动态关键路径上增加任何逻辑，也不得修改 400 MHz 校准时序。

---

# 1. 强制执行环境：Miniconda `DL`

本计划中所有 Python 数据处理、CSV/JSON 生成、统计分析和绘图脚本，**必须使用 Miniconda 的 `DL` 环境执行**。

Codex 开始 M0-0 时首先验证：

```bash
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate DL
python -c "import sys, matplotlib; print(sys.executable); print(matplotlib.__version__)"
```

如果普通 shell 中还没有 `conda`，应先定位现有 Miniconda 安装并激活已有 `DL`，不要另建新环境、不要 `pip install`、不要修改环境依赖。

要求：

```text
所有 M0 Python runner       -> DL 环境
所有 M0 matplotlib 绘图      -> DL 环境
不得使用系统 Python 替代 DL
不得使用 seaborn
```

每个最终 M0 报告必须记录：

```text
python executable
python version
matplotlib version
conda environment name = DL
```

建议在任务专用脚本入口检查 `CONDA_DEFAULT_ENV == "DL"`；如果不是 `DL`，对需要绘图/分析的正式执行直接失败，避免不同 Python 环境造成不可复现图表。

---

# 2. 上游冻结和禁止事项

## 2.1 冻结内容

M0 必须只读复用：

- P10 冻结的传感器拓扑和启动校准算法；
- 400 MHz / 2.5 ns 当前时序合同；
- H0 handoff RTL 和已纠偏时序证据；
- 三个正式校准锚点；
- 当前真实中调/细调/XOR/DFF 单元；
- 既有 HSPICE 渲染器和已验证的 cell/CDL 端口语义。

## 2.2 默认禁止

本阶段禁止：

```text
修改六个冻结启动校准 RTL
修改 FTC_SENSOR
修改 H0 ownership RTL
修改 400 MHz 时序
重新做 RF6/RF8/RF9C/RF9D
重新跑三电压完整启动校准
重新搜索标准单元
重新设计中调或细调拓扑
加入 level shifter / UPF / isolation
实现 detection FSM / alarm RTL
实现动态重新校准
做 PVT / Monte Carlo / post-layout
做 transient droop amplitude×duration 全矩阵
```

M0 新的 HSPICE 只能用于**当前冻结结构在指定 `(M,F,VDD)` 下的单次探测和静态电压灵敏度表征**。

---

# 3. M0 专属目录与主产物

建议创建：

```text
delay_chain/ftc/analysis/m0_detection_margin_characterization/
├── baseline/
│   ├── frozen_inputs.json
│   └── environment_manifest.json
├── probe_contract/
│   ├── single_probe_contract.json
│   └── scenario_manifest.json
├── local_surface/
│   ├── local_code_surface.csv
│   └── local_code_surface_summary.json
├── mechanism_gate/
│   ├── mechanism_gate.csv
│   └── mechanism_gate_summary.json
├── trip/
│   ├── trip_sweep.csv
│   ├── trip_map.csv
│   └── trip_summary.json
├── figures/
│   ├── fig_m0_local_code_surface.pdf
│   ├── fig_m0_local_code_surface.png
│   ├── fig_m0_voltage_response.pdf
│   ├── fig_m0_voltage_response.png
│   ├── fig_m0_residual_trip.pdf
│   ├── fig_m0_residual_trip.png
│   ├── fig_m0_trip_depth_summary.pdf
│   └── fig_m0_trip_depth_summary.png
├── tables/
│   ├── table_m0_candidate_summary.csv
│   └── table_m0_trip_summary.csv
├── figure_manifest.json
└── summary.json
```

新增 runner / plotter 建议：

```text
delay_chain/ftc/scripts/run_m0_detection_margin_characterization.py
delay_chain/ftc/scripts/plot_m0_detection_margin_figures.py
```

最终报告：

```text
delay_chain/ftc/reports/FTC_M0_DETECTION_MARGIN_CHARACTERIZATION.md
```

---

# 4. M0-0 —— 基线冻结与环境确认

## 动作

1. 确认 `main` 基线和当前 H0 PASS。
2. 哈希冻结：
   - 当前 H0 handoff RTL；
   - 六个启动校准 RTL；
   - 传感器/中调/细调相关 runner 与合同；
   - 三个最终 calibration result；
   - 当前 HSPICE/PDK 输入。
3. 激活 Miniconda `DL`，记录 Python/matplotlib 版本。
4. 生成：

```text
baseline/frozen_inputs.json
baseline/environment_manifest.json
```

## Gate

任一冻结输入漂移，或无法使用 `DL` 环境，停止 M0，不得自动重建环境或继续仿真。

## 新 HSPICE

```text
0
```

---

# 5. M0-1 —— 建立“单次探测”物理表征合同

## 目标

从完整启动校准中抽离一个最小的、可重复的单次 probe：给定 `(M,F,VDD)`，直接使用冻结的真实 sensor + medium + fine + XOR + DFF，测量时间量和真实 `Q_FINAL`。

必须复用已经验证的物理拓扑/渲染器，不得重新发明另一套传感器网表。

## 每个 scenario 至少记录

```text
scenario_id
baseline_vdd_v
physical_vdd_v
medium_code
fine_code
t_xor_rise_s
t_xor_fall_s
t_ck_rise_s
W_xor_ps
D_ref_ps
R_ps
q_final_v
q_final
valid
reason
```

定义：

```text
W_xor = t_xor_fall - t_xor_rise
D_ref = t_ck_rise   - t_xor_rise
R     = W_xor - D_ref
      = t_xor_fall - t_ck_rise
```

`R` 只作为物理诊断量：

```text
R < 0 : CK 在 XOR pulse 结束之后
R ≈ 0 : 接近真实捕获边界
R > 0 : CK 落入 XOR pulse 内
```

**最终 trip 必须以真实 DFF 稳定 Q 判定，不能用 `R` 代替真实 DFF。**

## 可信度检查

只用少量已存在的冻结校准点/附近证据验证 runner 的连接、极性、单位和 Q 判决一致性；不要重新执行完整校准轨迹。

## 输出

```text
probe_contract/single_probe_contract.json
probe_contract/scenario_manifest.json
```

---

# 6. M0-2 —— 三个校准点附近的二维 `(M,F)` 局部码空间

## 目标

不要先假定 detection margin 是 `F+1`。先建立真实二维局部时间面，找出“物理时间上相邻”的候选检测点。

### 0.80 V

中心：

```text
M7/F6
```

建议初始合法窗口：

```text
M = 6..8
F = 3..9
```

### 0.95 V

中心：

```text
M4/F6
```

建议初始合法窗口：

```text
M = 3..5
F = 3..9
```

### 1.10 V

中心：

```text
M2/F9
```

因为 F 已接近上界，必须显式覆盖 medium/fine 跨级组合：

```text
M = 1..3
F = 6..10
```

如果已有只读证据能够覆盖窗口中的某些完全相同 `(M,F,VDD,topology)` 场景，应优先复用；只有缺失点才新增 HSPICE。场景复用必须通过完整合同哈希确认，不得只凭代码相同就复用。

## 每点分析

记录：

```text
W_xor_ps
D_ref_ps
R_ps
Q
```

并计算相对校准中心的：

```text
Delta_D_ref_ps
Delta_R_ps
```

候选检测点的首要定义是：

> 正常电压下真实 Q 必须保持安全状态，并且其时间边界相对校准点形成有序、可解释的正裕量。

## Gate

如果局部 `(M,F)` 空间出现大量无法解释的非单调、同一方向代码增加却反复跨边界，先停止并分析物理原因，不能直接跳到大范围 VDD sweep。

## 输出

```text
local_surface/local_code_surface.csv
local_surface/local_code_surface_summary.json
```

---

# 7. M0-3 —— 候选检测裕量选择（基于 ps，不基于固定 ΔF）

## 目标

从 M0-2 的二维表面中，为后续机制门选择少量候选。

每个 baseline 最多选择 2–4 个代表性候选，优先形成：

```text
L0 = calibration/guard baseline
L1 = 小时间裕量
L2 = 中等时间裕量
必要时 L3 = 更大裕量
```

这里的 `L1/L2/L3` 是**时间裕量等级**，不是固定 `F+1/F+2/F+3`。

每个候选必须记录：

```text
baseline_vdd_v
M_cal/F_cal
M_det/F_det
nominal_D_ref_shift_ps
nominal_R_ps
normal_Q
selection_reason
```

特别检查 `1.10 V -> M2/F9`：如果 F 方向没有合法上移空间，必须允许通过 `(M+1,F')` 找到时间上连续的候选，而不是越界或强行饱和到 F10。

## Gate

如果无法构造至少一个“正常不报警且比校准点有可解释时间裕量”的候选，则：

```text
M0 = NO-GO
```

停止，不进入电压 sweep。

---

# 8. M0-4 —— 最小电压灵敏度机制门

## 目标

这是 M0 最重要的生死门：先验证当前新结构是否真的存在可利用的 voltage sensitivity contrast，再决定是否值得做 trip sweep。

对 M0-3 的少量候选，仅运行小规模静态 VDD 点。

### 1.10 V baseline

```text
1.10 V
1.05 V
1.00 V
```

### 0.95 V baseline

```text
0.95 V
0.90 V
0.85 V
```

### 0.80 V baseline

本阶段只做正常点和代码邻域确认；**默认不把 <0.80 V 当成正式检测能力范围**。若需要低于 0.80 V 的攻击实验，留给后续明确 threat contract 后执行。

## 观察量

每个候选画出/记录：

```text
W_xor(VDD)
D_ref(VDD)
R(VDD)
Q(VDD)
```

期望机制是：

```text
normal VDD:
  Q = 0
  R < 0

VDD 降低:
  R 向 0 增大

足够跌落:
  R 接近/穿过边界
  真实 Q: 0 -> 1
```

不要强制要求 50 mV 就必须 trip；这一步首先看**方向性和可分性**。

## 立即停止条件

若代表性候选普遍出现：

```text
W_xor 与 D_ref 随 VDD 几乎同比例变化
R 不向触发方向移动
或者 R/Q 变化无一致方向
```

则当前 reference mechanism 没有证明出检测能力：

```text
M0 mechanism = NO-GO
```

停止，不扩大 sweep，不通过更多点数“寻找偶然 trip”，不写检测 RTL。

## 输出

```text
mechanism_gate/mechanism_gate.csv
mechanism_gate/mechanism_gate_summary.json
```

---

# 9. M0-5 —— 自适应静态 Vtrip 提取

只有 M0-4 机制门通过才执行。

## 目标

对 `0.95 V` 和 `1.10 V` baseline 的候选裕量，提取真实 DFF 的静态 trip boundary。

## Sweep 原则

不要做完整二维矩形扫。

每个候选：

1. 从 baseline 开始降低 VDD；
2. 先用较粗步长寻找最后一个稳定 `Q=0` 和第一个稳定 `Q=1`；
3. 只在该 bracket 内细化；
4. 最终分辨率建议到 `10 mV`；
5. 一旦得到稳定 trip boundary 就停止更深 sweep；
6. 若直到 0.80 V 仍无 trip，记录 `NO_IN_RANGE_TRIP`，不要自动继续向 0.80 V 以下。

定义：

```text
DeltaV_trip = V_baseline - V_trip
```

其中 `V_trip` 为最高的、已经真实稳定触发 `Q=1` 的 VDD。

同时检查：

```text
更大 nominal timing margin
不应对应更浅的 trip_depth
```

也就是说时间裕量等级增大时，静态跌落触发深度总体应保持有序；如果排序反转，必须回到实际 `W_xor/D_ref/R/Q` 解释原因，不能直接平均或隐藏异常。

## 输出

```text
trip/trip_sweep.csv
trip/trip_map.csv
trip/trip_summary.json
```

---

# 10. M0-6 —— SCI 学术论文级绘图（强制交付，不是附加项）

M0 不能只交一张 CSV 表。图形结果是本阶段正式 acceptance evidence 的组成部分。

所有绘图必须：

```text
使用 Miniconda DL 环境
使用 matplotlib
不得使用 seaborn
绘图脚本可重复执行
图中的所有点必须能回溯到 CSV/JSON
同时输出矢量 PDF + 高分辨率 PNG
PNG 建议 600 dpi
不把手工编辑后的图片当正式证据
```

绘图脚本：

```text
delay_chain/ftc/scripts/plot_m0_detection_margin_figures.py
```

建议统一科研图格式：

- 单栏/双栏尺寸明确；
- 字体、字号、线宽、marker 一致；
- 坐标轴必须带物理单位；
- 图例不遮挡关键数据；
- 对打印和灰度阅读友好，不能只靠颜色区分曲线，结合 marker/line style；
- 不使用 3D surface 代替主要定量图，二维码空间优先用二维 heatmap/contour；
- 不使用渐变阴影或装饰性背景制造“视觉效果”；
- 需要 error/invalid point 时显式使用特殊 marker，而不是删掉；
- 标题保持论文式简洁，详细解释写入 caption/report；
- 图文件命名固定并写入 `figure_manifest.json`。

## Fig. M0-1：二维局部 `(M,F)` 码空间图

目标：证明检测点来自真实二维码空间，而不是固定 `F+1` 假设。

建议做三 panel：

```text
(a) 0.80 V, centered at M7/F6
(b) 0.95 V, centered at M4/F6
(c) 1.10 V, centered at M2/F9
```

坐标：

```text
x = F
y = M
```

颜色量优先使用：

```text
R_ps 或相对校准点的 nominal timing shift (ps)
```

必须标记：

```text
calibration point
selected L1/L2/L3 candidates
Q state/boundary
illegal code 不得伪造成数据
```

输出：

```text
fig_m0_local_code_surface.pdf
fig_m0_local_code_surface.png
```

## Fig. M0-2：`W_xor` 与 `D_ref` 的 VDD 响应

用于回答“传感脉宽和参考延迟是否具有足够不同的电压响应”。

建议至少对：

```text
0.95 V baseline 的代表候选
1.10 V baseline 的代表候选
```

绘制：

```text
x = VDD (V)
y = time (ps)
curves = W_xor, D_ref
```

必要时用 panel 分 baseline，避免不同绝对尺度混在一起。

输出：

```text
fig_m0_voltage_response.pdf
fig_m0_voltage_response.png
```

## Fig. M0-3：Residual `R` 与真实 Q/trip 的对应关系

这是 M0 的核心机制图。

绘制：

```text
x = VDD (V)
y = R (ps)
```

每条曲线代表一个候选 margin level，并用不同 marker 明确标注真实：

```text
Q=0
Q=1
```

必须标出：

```text
R = 0 reference line
first stable Q=1 trip
Vtrip
```

但不得声称真实 DFF 的 exact boundary 必然等于 `R=0`；`R=0` 仅用于物理解释，真实 trip 由 Q 决定。

输出：

```text
fig_m0_residual_trip.pdf
fig_m0_residual_trip.png
```

## Fig. M0-4：检测裕量等级与最小静态跌落深度

最终性能总结图。

绘制：

```text
x = nominal timing margin level / nominal shift (ps)
y = DeltaV_trip (mV)
```

分别展示：

```text
0.95 V baseline
1.10 V baseline
```

如果候选数量少，用 marker+line；不要为了“好看”做柱状图堆叠。`NO_IN_RANGE_TRIP` 必须在图或 caption 中明确，不得当作 0 mV。

输出：

```text
fig_m0_trip_depth_summary.pdf
fig_m0_trip_depth_summary.png
```

## 图形 QA

绘图完成后，Codex 必须自动检查：

```text
所有目标 PDF/PNG 存在且非空
PNG 像素尺寸和 dpi 满足要求
figure_manifest 中的 source CSV hash 与当前文件一致
所有 plotted scenario 均存在于正式 CSV
没有绘制超出 formal scope 的 <0.80 V detection claim
```

然后人工/视觉检查图例、标签、字体重叠和可读性；若需要修图，只修改绘图脚本重新生成，不能用图像编辑器手工改正式图。

---

# 11. M0-7 —— 论文表格与机器可读 summary

生成两张正式表：

## Table M0-A：候选检测配置

至少包含：

```text
baseline_vdd_v
M_cal
F_cal
margin_level
M_det
F_det
nominal_D_ref_shift_ps
nominal_R_ps
normal_Q
```

## Table M0-B：静态 trip map

至少包含：

```text
baseline_vdd_v
margin_level
M_det
F_det
trip_status
Vtrip_v
DeltaV_trip_mv
R_at_last_q0_ps
R_at_first_q1_ps
```

机器可读：

```text
summary.json
figure_manifest.json
```

`figure_manifest.json` 必须记录每张图：

```text
figure_id
pdf_path
png_path
source_files
source_sha256
plot_script_sha256
python_executable
matplotlib_version
conda_env
```

---

# 12. M0-8 —— 最终 GO / CONDITIONAL_GO / NO-GO

## M0 = GO

至少满足：

1. 单次 probe 合同与冻结真实电路一致；
2. 二维 `(M,F)` 局部时间面可解释；
3. 0.95 V 与 1.10 V 都至少存在正常不误报的 detection candidate；
4. voltage sensitivity mechanism 方向一致；
5. 两个 baseline 都至少有一个 `IN_RANGE_TRIP`；
6. 时间 margin 与 trip depth 基本有序，不存在无法解释的严重反转；
7. 真实 DFF Q 是最终 trip 判据；
8. 所有 SCI 图/表可从正式 CSV/JSON 一键复现；
9. 未修改冻结校准、H0 或 sensor；
10. 未执行未授权 RF6/RF9C/RF9D 重跑。

## M0 = CONDITIONAL_GO

允许的典型情况：

```text
0.95/1.10 V 机制和 trip map 成立，
但 0.80 V 因 formal minimum VDD 边界只完成局部码空间/正常点验证，
不声称 <0.80 V 的正式 droop detection 能力。
```

这种情况报告必须明确 scope，不能把 0.80 V 未验证区间写成“已覆盖”。

## M0 = NO-GO

至少包括以下任一：

```text
局部二维码空间不可形成可靠 detection candidate
W_xor 与 D_ref 电压响应过度共模，R 不向 trip 方向移动
合理 formal VDD 范围内真实 Q 完全没有 trip
trip ordering 严重反转且无法物理解释
```

NO-GO 后停止，不写 detection RTL。

---

# 13. 最终报告结构

`FTC_M0_DETECTION_MARGIN_CHARACTERIZATION.md` 至少包含：

1. Frozen architecture and H0 handoff；
2. Single-probe physical definition；
3. Local two-dimensional `(M,F)` timing surface；
4. Candidate margin selection in ps；
5. Voltage sensitivity mechanism；
6. Real-DFF static trip extraction；
7. `margin -> M_det/F_det -> ps -> Vtrip -> mV` 映射；
8. 0.80 V scope boundary；
9. Figure/table index；
10. HSPICE scenario accounting；
11. Miniconda `DL` / matplotlib environment；
12. Final M0 decision；
13. Downstream handoff。

正式报告中建议直接引用四张论文图，并给出适合后续 SCI 论文复用的 caption 初稿。

---

# 14. M0 通过后的下游 handoff

M0 不实现硬件 margin generator，只冻结后续 M1 要消费的数据：

```text
baseline calibration snapshot semantics
legal candidate margin levels
M_det/F_det for each margin level
nominal timing shift in ps
static Vtrip / DeltaV_trip envelope
unsupported baseline/scope
```

下一阶段 M1 才回答：

> 如何从 H0 保存的 `M_cal/F_cal` 在可综合 RTL 中安全生成 `M_det/F_det`，包括 F 上界附近的跨 medium/fine 编码映射。

M0 不提前写该逻辑。

---

# 15. Codex 逐阶段执行顺序和停止规则

```text
M0-0  冻结输入 + 强制 DL 环境
  ↓
M0-1  单次真实 probe 合同
  ↓
M0-2  三个锚点局部二维 M/F 表面
  ↓
M0-3  以 ps 为依据选择少量候选 margin
  ↓
M0-4  小规模 voltage sensitivity mechanism gate
  ├─ FAIL -> M0 NO-GO，立即停止
  ↓ PASS
M0-5  自适应静态 Vtrip 提取
  ↓
M0-6  DL + matplotlib 生成 SCI 级四张主图
  ↓
M0-7  正式表格 + figure manifest + summary
  ↓
M0-8  GO / CONDITIONAL_GO / NO-GO
```

最重要的执行原则：

> **先证明物理机制，再扩展 sweep；先用真实数据建立图和映射，再考虑 RTL。不要为了获得“好看的结果”扩大实验范围或修改冻结结构。所有正式绘图必须在 Miniconda `DL` 环境中使用 matplotlib 可重复生成。**
