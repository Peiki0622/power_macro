# FTC M0 检测裕量与电压灵敏度表征

## 1. Frozen architecture and H0 handoff

- 冻结结构：N=16 medium、`BUF_X0P8M_A9TL40`、`NOR2_X4A_A9TL40` K=10、真实 tap29 XOR 与真实 DFF。
- H0 snapshot anchors：0.80 V M7/F6，0.95 V M4/F6，1.10 V M2/F9。
- 所有冻结输入的 SHA256、H0/exact acceptance 与兼容 HSPICE 版本记录在 `analysis/m0_detection_margin_characterization/baseline/`。

## 2. Single-probe physical definition

- 单 probe 在校准之后保持 M/F snapshot 恒定；真实 DFF 双读稳定 Q 是唯一 trip 判据，R 仅作物理诊断。

控制码在 t=0 以 thermometer snapshot 固定。reset release→S_CLK rise 为 0.49 ns，rise→Q1 为 2.30 ns，Q1→Q2 为 0.20 ns，Q2→reset assert 为 0.20 ns，reset complete→fall 为 0.29 ns，fall→recovery 为 2.70 ns。每个 deck 直接测量 `t_xor_rise/fall`、`t_ck_rise` 和两次 `q_final`。

## 3. Local two-dimensional (M,F) timing surface

- 三个锚点局部面均为 GO：0.80 V 21 个点、0.95 V 21 个点、1.10 V 15 个点；每个点由真实 M/F 码、真实 XOR、真实 reference chain 与真实 DFF 得到。
- 合法候选仅从实测二维面选择，未假设固定的 `F+1` 映射，也未把非法码伪造成数据。

## 4. Candidate margin selection in ps (Table M0-A)

| Baseline (V) | Level | M_cal/F_cal | M_det/F_det | Nominal shift (ps) | Nominal R (ps) | Normal Q |
|---:|---|---|---|---:|---:|---:|
| 0.8 | L0 | M7/F6 | M7/F6 | 0.000000 | 59.916549 | 0 |
| 0.8 | L1 | M7/F6 | M8/F6 | 66.793920 | -7.043778 | 0 |
| 0.8 | L2 | M7/F6 | M8/F8 | 84.888558 | -25.137398 | 0 |
| 0.8 | L3 | M7/F6 | M8/F9 | 94.640212 | -34.887421 | 0 |
| 0.95 | L0 | M4/F6 | M4/F6 | 0.000000 | 22.815484 | 0 |
| 0.95 | L1 | M4/F6 | M4/F9 | 24.305359 | -1.482253 | 0 |
| 0.95 | L2 | M4/F6 | M5/F6 | 43.785783 | -20.855358 | 0 |
| 0.95 | L3 | M4/F6 | M5/F9 | 68.103129 | -45.170456 | 0 |
| 1.1 | L0 | M2/F9 | M2/F9 | 0.000000 | 4.155605 | 0 |
| 1.1 | L1 | M2/F9 | M2/F10 | 7.111682 | -2.955219 | 0 |
| 1.1 | L2 | M2/F9 | M3/F8 | 25.802928 | -21.623445 | 0 |
| 1.1 | L3 | M2/F9 | M3/F10 | 40.046293 | -35.865499 | 0 |

## 5. Voltage sensitivity mechanism

- M0-4 mechanism gate = GO：0.95 V 的 L1/L2/L3 在 0.95/0.90/0.85 V，1.10 V 的 L1/L2/L3 在 1.10/1.05/1.00 V 进行小规模静态点验证。
- 六个候选均在正常 VDD 保持稳定 Q=0、负 R，并在降压时 R 向触发方向增长；该方向性由 Fig. M0-2/M0-3 中的真实 W_xor、D_ref、R 与 Q 数据展示。

## 6. Real-DFF static trip extraction (Table M0-B)

| Baseline (V) | Level | M_det/F_det | Status | Vtrip (V) | ΔVtrip (mV) | R@last Q=0 (ps) | R@first Q=1 (ps) |
|---:|---|---|---|---:|---:|---:|---:|
| 0.95 | L1 | M4/F9 | IN_RANGE_TRIP | 0.88 | 69.99999999999996 | 54.62660399999976 | 68.17643000000004 |
| 0.95 | L2 | M5/F6 | IN_RANGE_TRIP | 0.86 | 89.99999999999997 | 54.41640100000012 | 69.27948300000025 |
| 0.95 | L3 | M5/F9 | IN_RANGE_TRIP | 0.83 | 120.0 | 74.75259299999982 | 94.27401099999997 |
| 1.1 | L1 | M2/F10 | IN_RANGE_TRIP | 1.01 | 90.00000000000009 | 29.28060999999974 | 35.04463299999969 |
| 1.1 | L2 | M3/F8 | IN_RANGE_TRIP | 0.96 | 140.0000000000001 | 35.57361400000002 | 42.79617300000007 |
| 1.1 | L3 | M3/F10 | IN_RANGE_TRIP | 0.93 | 170.00000000000003 | 41.96404099999967 | 50.959621999999854 |

- `Vtrip` 是完整 `trip_sweep.csv` 中最高 VDD 的稳定 Q=1；`R@last Q=0` 是其上方最近稳定 Q=0。M0-E 仅据此重派生表格，未增加任何 HSPICE 场景。

## 7. margin -> M_det/F_det -> ps -> Vtrip -> mV mapping

- Table M0-A 与 Table M0-B 通过相同的 baseline、margin level 和 M_det/F_det 连接：每个 level 的实测 nominal shift、真实 DFF Vtrip 与 ΔVtrip 均可在正式 CSV 中逐行追溯。
- 两个 baseline 的 ΔVtrip 随 nominal timing shift 均单调增加；没有将 R=0 当作 DFF trip 的代理判据。

## 8. 0.80 V scope boundary

- 0.80 V 仅完成局部码空间和正常点验证；未进行、也未声明 `<0.80 V` 的正式 droop detection 能力。

## 9. Figure/table index and SCI caption draft

- Fig. M0-1：三个 H0 calibration anchor 附近的二维 M/F 真实 residual 面；候选来自实测时间面而非固定 F 增量。
- Fig. M0-2：真实 XOR 脉宽与 reference delay 随静态 VDD 的响应，显示是否存在可用的非共模灵敏度。
- Fig. M0-3：residual R 与真实 DFF Q/Vtrip 的对应；R=0 为解释参考线，不是替代 DFF 的 trip 判据。
- Fig. M0-4：nominal timing margin 与最小静态跌落深度的关系；`NO_IN_RANGE_TRIP` 不按 0 mV 绘制。
- 图：`analysis/m0_detection_margin_characterization/figures/fig_m0_*.{pdf,png}`；表：`tables/table_m0_candidate_summary.csv` 与 `tables/table_m0_trip_summary.csv`；图的输入哈希、脚本哈希和 DL/matplotlib 环境记录于 `figure_manifest.json`。

## 10. HSPICE scenario accounting

- 新建 task-owned HSPICE scenario：91，PASS：91；未重跑启动校准、RF6/RF8/RF9C/RF9D 或上游物理 campaign。

## 11. Miniconda DL and matplotlib environment

- Python：`/home/zhupl25/miniconda3/envs/DL/bin/python`；版本 `3.9.25`；matplotlib `3.9.4`；conda 环境 `DL`。

## 12. Final M0 decision

**M0 = CONDITIONAL_GO**

- 0.80 V is local-code-surface/normal-point only; no <0.80 V detection claim
- 因 0.80 V 保持 formal minimum 的局部验证边界，M0 不夸大为全范围检测能力，最终状态为 CONDITIONAL_GO。

## 13. Downstream handoff

M1 may consume snapshot semantics, legal M_det/F_det levels, nominal ps shifts, Vtrip envelope, and unsupported scope; M0 implements no margin-generator RTL.
