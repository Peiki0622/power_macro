# FTC M1 可编程检测裕量生成与安全配置逐阶段推进计划

**仓库：** `Peiki0622/power_macro`  
**目标分支：** `main`  
**M1 输入基线：** `935facf76f338d8a0e274f33655d746153a1b284`  
**阶段定位：** H0 原子校准→检测所有权切换 PASS、M0/M0-E 静态检测裕量与 Vtrip 表征闭合之后，T0 瞬态 droop threat/timing contract 与 D0 detection FSM 之前。

---

# 0. M1 的唯一核心目标

M1 不重新表征传感器，不定义检测 cadence，不实现动态 droop FSM，也不修改 H0。M1 只回答：

> 如何把 H0 冻结的一次性 `M_cal/F_cal` calibration snapshot 和外部选择的 margin level，安全、可综合、无插值地映射成 M0 已实测的 `M_det/F_det` 检测配置，并在严格遵守 H0 原子 handoff 语义的前提下，在 DET ownership 建立后完成一次性的 margin configuration。

M1 的硬件证据链必须是：

```text
H0 immutable calibration snapshot
        ↓
exact M0 codebook lookup
        ↓
registered target M_det/F_det + thermometer vectors
        ↓
H0 snapshot-safe preload / takeover
        ↓
DET owner established
        ↓
reset=1, S_CLK=0 下原子应用 margin
        ↓
至少一个完整 400 MHz controller cycle 配置稳定
        ↓
margin_cfg_valid
```

M1 **不得**把 M0 的局部时间面重新近似成 `F_cal + ΔF` 或 `M_cal + ΔM` 算术规则；当前 M0 已证明 1.10 V 锚点必须跨 medium/fine 组合选择，固定 fine 增量并不成立。

---

# 1. 上游冻结基线与绝对禁止事项

M1 必须只读复用并哈希冻结：

- M0-E 提交 `935facf76f338d8a0e274f33655d746153a1b284`；
- `delay_chain/ftc/analysis/m0_detection_margin_characterization/local_surface/candidate_selection_summary.json`；
- `delay_chain/ftc/analysis/m0_detection_margin_characterization/trip/trip_summary.json`；
- `delay_chain/ftc/analysis/m0_detection_margin_characterization/summary.json`；
- H0 frozen handoff interface、downstream contract、H0 RTL 和 H0 gate evidence；
- 六个冻结启动校准 RTL；
- `FTC_SENSOR`、medium/fine/XOR/DFF 拓扑；
- 当前 400 MHz / 2.5 ns controller timing contract；
- 当前 ideal power-aware CTRL↔SENSE interface abstraction。

## 1.1 本阶段禁止

```text
修改六个冻结启动校准 RTL
修改 FTC_SENSOR / medium / fine / XOR / DFF
修改 ftc_sensor_owner_handoff.sv
修改 ftc_cal_detect_handoff_top.sv
修改 400 MHz calibration timing contract
修改启动校准算法
重新跑完整 startup calibration
重新跑 HSPICE M0/M0-E
重新跑 RF6 / RF8 full / RF9C / RF9D
重新跑 XA / mixed-signal full campaign
搜索或引入跨压 level shifter / isolation cell
做 PVT / Monte Carlo / post-layout
实现 detection probe cadence
实现 transient droop amplitude×duration sweep
实现 alarm / status / runtime detection FSM
做动态 recalibration
```

**特别约束：** H0 时序纠偏后 `S_CLK_RISE -> Q_SAMPLE_1` 仅剩约 `+0.03 ns` 物理余量。M1 不得在 CAL→`sense_s_clk` 路径或 H0 输出之后再插入任何新的 CAL-side 组合逻辑/mux。M1 必须只位于 H0 的 detector-input 侧，保持冻结的 CAL dynamic path 结构不变。

---

# 2. M0 已冻结的 codebook 输入事实

M1 只能消费下面已经由 M0/M0-E 实测确认的映射，不得自行扩展：

```text
Calibration snapshot M7/F6  （0.80 V evidence anchor）
  L0 -> M7/F6
  L1 -> M8/F6
  L2 -> M8/F8
  L3 -> M8/F9

Calibration snapshot M4/F6  （0.95 V evidence anchor）
  L0 -> M4/F6
  L1 -> M4/F9
  L2 -> M5/F6
  L3 -> M5/F9

Calibration snapshot M2/F9  （1.10 V evidence anchor）
  L0 -> M2/F9
  L1 -> M2/F10
  L2 -> M3/F8
  L3 -> M3/F10
```

对应 M0 nominal timing shifts / static trip evidence：

```text
M4/F6 anchor:
  L1 24.305359 ps -> ΔVtrip  70 mV
  L2 43.785783 ps -> ΔVtrip  90 mV
  L3 68.103129 ps -> ΔVtrip 120 mV

M2/F9 anchor:
  L1  7.111682 ps -> ΔVtrip  90 mV
  L2 25.802928 ps -> ΔVtrip 140 mV
  L3 40.046293 ps -> ΔVtrip 170 mV
```

0.80 V anchor 只具有 local-code-surface / normal-point 合法性证据，没有 `<0.80 V` 的正式 Vtrip；因此它可以是 **mapping-supported**，但不能被标成 **trip-qualified**。

M1 硬件不接收 baseline VDD，也不得根据“估计电压”选择表项。codebook 唯一 key 是 H0 冻结的 `M_cal/F_cal snapshot + margin_sel`；`0.80/0.95/1.10 V` 仅作为证据 provenance 标签。

---

# 3. M1-0 —— F10 detection-only 编码闭合（硬停止门）

这是 M1 开始写 RTL 之前必须完成的第一步。

## 3.1 背景

冻结 calibration register `ftc_cfg_therm_regs.sv` 使用 10-bit active-low fine thermometer，启动校准步进逻辑把 F9 当作校准可达最大位置；但 M0 在 1.10 V 的 L1/L3 实测候选使用了 `F10`。

因此必须静态证明：

> `F10` 是否是物理 10-bit fine bank 的合法“全部十个 load 都被使能”状态，只是 calibration FSM/stepper 不主动走到该状态；若是，则定义为 **legal detection-only physical code**，不得为了它修改冻结 calibration RTL。

## 3.2 Codex 必须检查

1. M0 physical runner 如何从 `fine_code` 生成实际 fine control vector；
2. M0 的 `M2/F10`、`M3/F10` HSPICE scenario 实际 deck 中的 10-bit fine control 是否全部为 active 状态；
3. H0 frozen detector input `det_fine_therm_i[9:0]` 是否可以无歧义承载该 vector；
4. `F_cal/F_det` debug code width 是否能表达十进制 10；
5. F0..F10 的 detection-side encoding 是否连续、唯一、无 hole；
6. 不得通过重新跑 HSPICE 来证明，优先使用现有 M0 deck/CSV/runner 和冻结 RTL 静态审计。

期望编码若现有证据支持，应明确冻结为：

```text
F0  = 1111111111
F1  = 1111111110 或与现有 bit ordering 等价的“1 个 active”编码
...
F9  = 仅剩 1 个 inactive bit
F10 = 0000000000
```

**注意：上面只表达 active-low 语义；最终 bit ordering 必须以现有物理 renderer / frozen RTL 的真实 ordering 为准，不允许凭注释猜测。**

## 3.3 输出

建议：

```text
delay_chain/ftc/controller/m1_detection_margin/
└── contract/
    └── F10_DETECTION_ENCODING_CONTRACT.json
```

至少记录：

```text
fine_code
fine_therm_vector
physical_legal
calibration_reachable
detection_reachable
evidence_source
evidence_sha256
```

## 3.4 Gate

如果可以证明 F10 是合法 detection-only physical code：

```text
M1-0 = GO
```

并明确：

```text
calibration-unreachable != physically-illegal
```

如果不能证明：

```text
M1-0 = STOP / NO-GO
```

不得继续写 M1 RTL，也不得自行修改 calibration range；应报告需要回到 M0 对 1.10 V anchor 重新挑选不含 F10 的候选，但本轮不要自动重跑 M0/HSPICE。

**本阶段新 HSPICE：0。**

---

# 4. M1-1 —— 冻结机器可读 margin codebook 与 qualification 语义

只有 M1-0 GO 才执行。

## 4.1 目标

把 M0 数据转换成一个硬件可消费但仍可追溯到原始证据的 exact lookup contract。

建议输出：

```text
delay_chain/ftc/controller/m1_detection_margin/contract/M1_MARGIN_CODEBOOK.json
```

每个表项至少包含：

```text
M_cal
F_cal
margin_level
M_det
F_det
medium_therm
fine_therm
mapping_supported
trip_qualified
nominal_D_ref_shift_ps
static_Vtrip_v
DeltaV_trip_mv
m0_candidate_id
m0_source_sha256
```

## 4.2 qualification 定义

必须严格区分：

```text
mapping_supported
```

与：

```text
trip_qualified
```

建议冻结语义：

- 三个已表征 calibration snapshots 的 L0-L3：`mapping_supported=1`；
- 0.95 V / 1.10 V evidence anchors 的 L1-L3：`trip_qualified=1`；
- 0.80 V anchor 的所有 level：`trip_qualified=0`；
- L0 只是 calibration/guard snapshot，不是 M0 正式静态 droop trip candidate，故 `trip_qualified=0`；
- 任何未出现在 M0 codebook 的 `M_cal/F_cal`：`mapping_supported=0`，禁止插值、禁止最近邻、禁止 saturation 推导。

## 4.3 Gate

写一个纯软件/单元测试逐项核对：

```text
12 个已支持 snapshot×level 组合 exact match M0
所有未知 snapshot 均 unsupported
F10 vector 必须与 M1-0 合同一致
M0 trip 数值仅做 metadata，不参与组合算术生成
```

**新 HSPICE：0。**

---

# 5. M1-2 —— 可综合 exact lookup mapper

## 5.1 建议 RTL

新增独立模块，不修改 H0：

```text
delay_chain/ftc/controller/rtl/ftc_detection_margin_mapper.sv
```

输入建议：

```text
cal_medium_code_snapshot_i[4:0]
cal_fine_code_snapshot_i[3:0]
margin_sel_i[1:0]        // L0/L1/L2/L3
```

输出建议：

```text
mapping_supported_o
trip_qualified_o
M_det_o[4:0]
F_det_o[3:0]
target_medium_therm_o[15:0]
target_fine_therm_o[9:0]
```

## 5.2 实现要求

- 使用小型 `case`/constant lookup；
- 不实现 `ΔF`/`ΔM` arithmetic；
- 不根据 VDD 输入做判断；
- 不为未知 snapshot 构造近似配置；
- unsupported 时 target 可默认回退到 snapshot-compatible safe value，但 `mapping_supported_o` 必须为 0，后续 manager 不得 assert takeover-ready；
- mapper 输出不能直接驱动 sensor physical control rails，必须先进入 registered manager。

## 5.3 RTL unit gate

逐项 exhaustive 测试：

```text
3 anchors × 4 levels = 12 exact supported cases
若干邻近但未表征的 snapshot = unsupported
F10 两个正式 case exact vector match
```

---

# 6. M1-3 —— 安全 margin configuration manager

## 6.1 目标

实现一次性 margin selection / H0 preload / post-owner margin apply。该模块必须保护 H0 已冻结的原子切换合同。

建议 RTL：

```text
delay_chain/ftc/controller/rtl/ftc_detection_margin_manager.sv
```

建议输入：

```text
cal_clk_i
ctrl_por_n_i
cal_cfg_valid_i
cal_medium_code_snapshot_i
cal_fine_code_snapshot_i
cal_medium_therm_snapshot_i
cal_fine_therm_snapshot_i
det_prepare_i
det_owner_valid_i
handoff_blocked_i
margin_sel_i[1:0]
margin_select_valid_i
```

建议输出：

```text
det_takeover_ready_o
det_sense_dff_reset_o
det_sense_s_clk_o
det_medium_therm_o[15:0]
det_fine_therm_o[9:0]
margin_cfg_valid_o
mapping_supported_o
trip_qualified_o
margin_protocol_error_o
M_det_o
F_det_o
margin_level_o
```

## 6.2 强制 handoff 顺序

M1 必须保持：

```text
CAL LOCK / H0 snapshot valid
        ↓
接收并锁存一次 margin_sel
        ↓
lookup target，但先不把 target 放到 sensor
        ↓
PRELOAD H0：
  det medium/fine = exact calibration snapshot
  det reset       = 1
  det S_CLK       = 0
        ↓
只有上述值稳定且 mapping_supported 后
  det_takeover_ready = 1
        ↓
H0 完成 SWITCH_SAFE
        ↓
观察 det_owner_valid = 1
        ↓
APPLY_MARGIN：
  一次性注册 target medium/fine thermometer
  reset 仍为 1
  S_CLK 仍为 0
        ↓
至少等待一个完整 400 MHz controller cycle（2.5 ns）
        ↓
margin_cfg_valid = 1
```

**绝对禁止：** 在 `det_takeover_ready_o=1` 之前，把 M0 target `M_det/F_det` 直接送到 H0 detector inputs。ready 之前 detector controls 必须与 H0 snapshot 完全一致，否则会破坏 H0 已验证的 equality/safe-level handoff contract。

## 6.3 建议状态

可采用最小状态机，例如：

```text
WAIT_CAL
WAIT_SELECT
PRELOAD_SNAPSHOT
WAIT_OWNER
APPLY_MARGIN
SETTLE
READY
BLOCKED
```

具体编码不强制，但行为必须满足上述顺序。

## 6.4 Margin selection 锁定

- `margin_sel_i` 只在一次有效的 `margin_select_valid_i` 时采样；
- 一旦 accepted，直到 POR 不得改变实际 target；
- 后续重复/冲突 selection request 可以 sticky `margin_protocol_error_o`，但不得产生传感器 glitch；
- 本阶段不实现 runtime margin reprogramming。

## 6.5 Unsupported / blocked fail-safe

任何以下情况：

```text
unknown calibration snapshot
invalid F10 contract
handoff_blocked
malformed selection protocol
```

都必须保持：

```text
det_takeover_ready = 0（若尚未 ownership）
reset = 1
S_CLK = 0
medium/fine 保持最近稳定 snapshot/target，不乱跳
margin_cfg_valid = 0
```

不得通过 unsupported mapping 进入 READY。

---

# 7. M1-4 —— H0 集成，但不修改 H0

建议新增一个新的阶段顶层，而不是改动冻结 H0 top：

```text
delay_chain/ftc/controller/rtl/ftc_cal_detect_margin_top.sv
```

结构应为：

```text
frozen ftc_cal_detect_handoff_top
          ↑ detector-side controls
ftc_detection_margin_manager
          ↑
ftc_detection_margin_mapper
```

M1 stage top 中，在未来 D0 尚未实现前：

- detector runtime `S_CLK` 保持 0；
- detector sensor DFF reset 保持 1；
- 只证明 snapshot preload、ownership、margin apply、settle、margin_cfg_valid；
- 不做真实 detection probe。

未来 D0 应消费 `margin_cfg_valid`、target code/therm、`trip_qualified` 后再产生 runtime reset/S_CLK，不应要求重写 M1 codebook。

## Structural gate

必须哈希确认：

```text
ftc_sensor_owner_handoff.sv unchanged
ftc_cal_detect_handoff_top.sv unchanged
6 frozen calibration RTL unchanged
FTC_SENSOR unchanged
```

并证明新逻辑只接入 H0 detector input side，没有在 H0 output 后新增 CAL-path mux。

---

# 8. M1-5 —— RTL / SVA 功能与协议验证

建议新增：

```text
delay_chain/ftc/controller/m1_detection_margin/verification/rtl/
delay_chain/ftc/controller/m1_detection_margin/assertions/
```

至少覆盖以下断言：

## 8.1 H0 preload invariants

在 `det_owner_valid=0` 且 M1 准备 takeover 时：

```text
det_medium_therm == cal_medium_therm_snapshot
det_fine_therm   == cal_fine_therm_snapshot
det_sense_dff_reset == 1
det_sense_s_clk == 0
```

## 8.2 Margin apply invariants

检测 margin vector 只能在：

```text
det_owner_valid == 1
AND reset == 1
AND S_CLK == 0
```

时发生变化。

## 8.3 Settle invariant

从 detector medium/fine vector 最后一次变化到 `margin_cfg_valid=1` 之间必须至少跨过一个完整 `cal_clk` 周期；不得同周期宣告 valid。

## 8.4 No-probe invariant

M1 阶段：

```text
det_sense_s_clk == 0
```

始终成立；M1 不实现检测 probe。

## 8.5 Codebook invariants

```text
12 个 supported case exact match
unsupported snapshot never ready
F10 exact vector legal
thermometer 连续，无 hole
M/F debug code 与实际 thermometer vector 一致
```

## 8.6 Qualification invariants

```text
M4/F6 + L1/L2/L3 -> trip_qualified=1
M2/F9 + L1/L2/L3 -> trip_qualified=1
M7/F6 + any level -> trip_qualified=0
any L0 -> trip_qualified=0
unknown snapshot -> mapping_supported=0
```

## 8.7 Negative protocol cases

至少验证：

- selection 在 calibration snapshot valid 之前到达；
- selection 重复到达；
- selection 在 accepted 后改变；
- unsupported snapshot；
- H0 blocked；
- POR 在各状态中间发生；
- det_owner_valid 延迟若干 cycle；
- target 与 snapshot 相同的 L0 不得产生伪 config pulse/glitch。

输出建议：

```text
verification/rtl/M1_RTL_RESULTS.json
reports/M1_SVA_STATUS.json
```

---

# 9. M1-6 —— 独立综合 / STA

M1 RTL/SVA GO 后，只对 M1 新增逻辑做必要 EDA。

## 9.1 默认综合范围

优先 standalone synthesis：

```text
ftc_detection_margin_mapper
ftc_detection_margin_manager
必要时 M1 stage wrapper（不重新优化冻结 H0）
```

使用当前可信 PD_CTRL 的普通 SMIC40LL controller library 和 400 MHz / 2.5 ns clock contract，不搜索 level shifter。

## 9.2 时序目标

- 所有 M1 sequential setup/hold slack > 0；
- mapper→registered target path 正 slack；
- margin selection→manager state path 正 slack；
- 不允许 M1 逻辑进入冻结 CAL→`sense_s_clk` timing cone；
- 不重新宣称 H0 `+0.03 ns` margin 被扩大；M1 的正确目标是 **不触碰该路径**。

## 9.3 是否需要 H0 top 重新综合

默认：

```text
NO
```

先用结构/hash + RTL integration + standalone STA 证明 M1 位于 detector input side。

只有在新增 wrapper 导致无法静态证明 cone 隔离时，才允许做一次**针对 H0+M1 integration wrapper 的最小化综合/STA**，并明确这不是 RF8 full startup resynthesis，不得触发 RF6/RF9C/RF9D 重跑。

输出建议：

```text
synthesis/netlist/ftc_detection_margin_manager_synth.v
synthesis/netlist/ftc_detection_margin_manager_synth.sdf
synthesis/reports/*
timing/M1_TIMING_SUMMARY.json
```

---

# 10. M1-7 —— 小型 mapped + SDF 验证

仅验证新增 M1 logic 的时序行为和 safe handoff sequence。

必须：

- 使用 mapped M1 netlist + SDF；
- timing checks enabled；
- 覆盖 12 个 supported codebook cases；
- 覆盖 unsupported / repeated selection / delayed owner / POR negative cases；
- 检查 thermometer vector 变化只发生在 reset=1/S_CLK=0；
- 检查 takeover 前始终是 calibration snapshot；
- 检查 `margin_cfg_valid` 不早于一完整 settle cycle；
- 检查 gate/SDF 下无 sensor-control glitch。

输出建议：

```text
verification/gate_sdf/M1_GATE_SDF_RESULTS.json
```

**禁止**为了 M1 gate/SDF 再跑 transistor sensor、HSPICE、XA、RF9D。

---

# 11. M1-8 —— 最终证据包和 Gate

建议证据根目录：

```text
delay_chain/ftc/controller/m1_detection_margin/
├── baseline/
│   ├── frozen_input_sha256.json
│   └── m1_baseline_manifest.json
├── contract/
│   ├── F10_DETECTION_ENCODING_CONTRACT.json
│   ├── M1_MARGIN_CODEBOOK.json
│   ├── M1_INTERFACE_CONTRACT.json
│   └── M1_DOWNSTREAM_T0_D0_HANDOFF.json
├── verification/
│   ├── rtl/
│   │   └── M1_RTL_RESULTS.json
│   └── gate_sdf/
│       └── M1_GATE_SDF_RESULTS.json
├── synthesis/
├── timing/
│   └── M1_TIMING_SUMMARY.json
└── reports/
    ├── M1_GATE_STATUS.json
    └── M1_FINAL_REPORT.md
```

## 11.1 M1 = GO 至少满足

1. F10 被现有物理证据证明为合法 detection-only code，或 M1 在进入 RTL 前明确停止；
2. M0 codebook 12 个 supported case exact match；
3. 不存在 `ΔF/ΔM` 插值/算术猜测；
4. unknown snapshot fail-safe unsupported；
5. takeover ready 前 detector controls 与 calibration snapshot 完全一致；
6. margin 只在 `det_owner_valid && reset && !S_CLK` 下应用；
7. `margin_cfg_valid` 前至少一个完整 2.5 ns controller settle cycle；
8. 0.80 V anchor 的 mapping 与 trip qualification 被严格区分；
9. H0 和六个冻结 calibration RTL hash 不变；
10. CAL→`sense_s_clk` 关键 timing cone 未被 M1 修改；
11. RTL/SVA 全部 PASS；
12. M1 standalone synthesis/STA setup/hold 全正；
13. mapped+SDF 小型验证 PASS、无 control glitch；
14. 新 HSPICE = 0、XA = 0、RF6/RF9C/RF9D = 0、完整 calibration rerun = 0。

## 11.2 M1 = NO-GO / STOP

至少包括：

```text
F10 无法由现有物理证据证明合法
M0 codebook 无法 exact 映射到合法 thermometer vector
H0 preload equality 无法保持
margin apply 必须破坏 reset/S_CLK safe window
unsupported snapshot 会误进入 ready
M1 新逻辑侵入冻结 CAL critical path
standalone STA 或 mapped/SDF 无法闭合
```

NO-GO 后不要通过降低 400 MHz、修改 H0、改 sensor 或重跑大规模 HSPICE 来绕过问题，应先报告根因。

---

# 12. M1 的 Python/数据处理环境

如果 Codex 为 M1 编写 Python 证据生成、JSON/CSV 校验或测试辅助脚本，继续统一使用现有 Miniconda `DL` 环境：

```bash
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate DL
```

不得新建 Python 环境，不得临时 `pip install`。M1 本身不要求新的 matplotlib 论文图；如果为了报告确有必要生成图，只能使用 `DL + matplotlib` 可重复生成，不得手工修图。

---

# 13. M1 明确不做的事情

M1 结束时 sensor 仍然保持：

```text
margin configuration 已装载
reset = 1
S_CLK = 0
没有 detection probe
```

M1 不定义：

```text
detection probe cadence
runtime reset/S_CLK waveform
droop amplitude × duration coverage
worst-case attack phase
minimum detectable pulse duration
alarm latency
alarm latching / clear policy
heartbeat / stuck-Q timeout
dynamic recalibration
```

这些属于后续阶段。

---

# 14. M1 GO 后的下游路线

M1 成功后进入：

```text
T0 — 瞬态电压跌落威胁与检测时序合同
```

T0 才定义：

```text
目标 droop amplitude
目标 duration
attack phase relative to probe
detection cadence
minimum detectable duration
worst-case latency
false-positive / recovery assumptions
<0.80 V 是否需要 fail-safe heartbeat/timeout，而不是精细 timing compare
```

然后才进入：

```text
D0 — runtime detection FSM / alarm / status
```

总体路线：

```text
H0  atomic ownership handoff                PASS
 ↓
M0 + M0-E  static margin / Vtrip            CONDITIONAL_GO(scope only)
 ↓
M1-0  F10 detection-only encoding closure   ← 第一硬门
 ↓
M1  exact codebook + safe margin apply
 ↓
T0  transient droop threat/timing contract
 ↓
D0  detection FSM + Q decision + alarm
 ↓
V0/V1  mapped/SDF → mixed-signal → transistor transient
```

---

# 15. Codex 逐步骤执行顺序和停止规则

```text
M1-0  冻结输入 + F10 静态编码闭合
  ├─ FAIL/证据不足 -> STOP，不写 RTL，不跑 HSPICE
  ↓ GO
M1-1  从 M0/M0-E 生成 exact machine-readable codebook
  ↓
M1-2  实现 combinational exact lookup mapper
  ↓
M1-3  实现 registered safe margin manager
  ↓
M1-4  新建 M1 stage top，实例化 frozen H0，不修改 H0
  ↓
M1-5  RTL unit + SVA + negative protocol verification
  ↓
M1-6  M1-only synthesis / STA
  ↓
M1-7  M1 mapped + SDF 小型验证
  ↓
M1-8  证据包 + M1 GO/NO-GO + downstream contract
```

最重要的执行原则：

> **M1 是“把已经测出来的检测工作点安全变成硬件配置”的阶段，不是重新寻找 margin，也不是开始做 detection FSM。先证明 F10，再冻结 exact codebook；takeover 前永远保持 calibration snapshot，ownership 后才在 reset=1/S_CLK=0 下原子应用 margin；所有未知 snapshot fail-safe，绝不插值；整个阶段不新增 HSPICE/XA，不触碰 H0 的 +0.03 ns CAL 关键路径。**
