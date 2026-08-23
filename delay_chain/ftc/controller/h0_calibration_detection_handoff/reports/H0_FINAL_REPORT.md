# H0 Calibration-to-Detection Atomic Handoff

决策：**H0 校准到检测原子化控制权切换 = 通过**

## Implementation

新增 `ftc_sensor_owner_handoff`，保持五态对外编码；传感器 mux 使用寄存的 CAL/SAFE/DET/blocked enables，SAFE 到 DET 首个周期保持同值重叠以消除 mapped SDF mux 毛刺，detector 必须在该首个 DET 周期继续保持 snapshot precharge。六个冻结校准 RTL 未修改。

## Verification

- RTL unit: nominal M7/F6, M4/F6, M2/F9 plus negative/POR-only cases PASS。
- SVA bind: ownership monotonicity, snapshot stability, failure blocking, exact-ready checking, safe window and POR-only reset all PASS；VCS 完整回放无 assertion failure。
- SMIC40LL independent STA: setup WNS 0.29 ns，hold WNS 0.03 ns，max transition/fanout/cap 违例为 0。
- H0-6: SCLK rise/fall 0.47/0.45 ns，reset rise/fall 0.44/0.47 ns，therm max 0.48 ns；SCLK→Q_SAMPLE_1 剩余 1.83 ns，reset release/fall 剩余 0.49/0.27 ns，configuration 剩余 2.02 ns。
- mapped+SDF: `+neg_tchk`，SDF annotation errors 0，timing violations 0，三组黄金切换 glitch_events=0。

## H0-8

完整 `ftc_cal_detect_handoff_top` 综合/STA = `not_required`：独立 H0 逻辑时序、物理事件组合和 mapped+SDF 已分别回答 H0 门要求，未重跑 RF6/RF8/RF9C/RF9D。

## 工艺库与证据卫生

本轮 H0 综合和 mapped+SDF 使用的 SMIC40LL 工艺库根路径固定为：

`/host/data/libtech/SMIC_40LL`

特别是独立 STA 使用 `sc9mc_logic0040ll_base_rvt_c40_ss_typical_max_0p99v_125c.db`。本轮 H0 活动脚本和结果没有访问 `/home/yangz`；该路径只在既有 RF8/RF9 历史运行产物中作为只读审计信息保留，未被本轮重跑或改写。

VCS 编译数据库、`simv` 可执行文件和 `*.daidir` 中间物已清理；日志、综合网表、SDF、约束和可解析证据 JSON 均保留在本 H0 目录内。

## Evidence

详见 `H0_TIMING_COMPOSITION.json`、`H0_FROZEN_HANDOFF_INTERFACE.json`、`verification/rtl/H0_RTL_UNIT_RESULTS.json`、`verification/gate_sdf/H0_GATE_SDF_RESULTS.json`，以及 `baseline/frozen_input_sha256.json`、`timing/existing_timing_inputs.json`、`timing/handoff_incremental_delays.json`、`timing/handoff_timing_composition.json`。
