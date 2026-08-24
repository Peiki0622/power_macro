# FTC T0 瞬态电压跌落检测能力表征报告

## 最终判定

**CONDITIONAL_GO**

传感器的纠偏后瞬态检测物理证据、六个闭合单-probe 相位窗口和 T0-6 区间映射均已完成。
但当前冻结 one-shot 序列的约 5.70 ns 非重叠参考慢于目标要求的 2.075 ns，因此不能直接宣称已有 runtime probe 实现。

> 条件：未来 D0 必须实现不慢于 **2.075 ns** 的运行时 probe 序列，并重新验证 reset/S_CLK/两次 Q 采样/recovery 时序。

## 物理证据范围

- T0-2：纠偏后的本地 `VDD_MONITORED` 归一化长脉冲证据保持 PASS；历史固定高电平结果仅作审计，不进入正式曲线。
- T0-4：六个 formal margin 的 corrected GO duration 边界保持权威；两个恢复沿特殊点被保留为 ambiguous bracket，而非伪造 minimum。
- T0-5：六个场景均已由左右 `STABLE_Q0` 闭合；CLEAN 覆盖只按确认区间宽度衡量，采样边界间隙和 ambiguous 均为非保证区域。

| T0-5 场景 | 总脉冲 (ps) | 确认 clean 测度 (ps) | 单 probe clean 时间覆盖率 | 最大非保证窗口 (ps) |
|---|---:|---:|---:|---:|
| t0_5a_0p95_l2_boundary | 1456 | 525 | 52.50% | 250 |
| t0_5a_0p95_l2_long | 3002 | 2075 | 43.68% | 2425 |
| t0_5a_1p10_l2_boundary | 1190 | 525 | 52.50% | 250 |
| t0_5a_1p10_l2_long | 3002 | 2325 | 46.50% | 2475 |
| t0_5b_0p95_l3_recovery | 2002 | 875 | 70.00% | 250 |
| t0_5b_1p10_l1_recovery | 1502 | 950 | 76.00% | 175 |

## T0-6 运行时节拍推导（HSPICE=0）

- 目标威胁：L2 3002 ps long pulse at both formal baselines；要求：100_percent_full_phase_CLEAN_Q1_guarantee。
- `Pmax_coverage = 2075 ps = 2.075 ns`，由两个目标场景中较窄的确认 CLEAN_Q1 周期投影窗口限定。
- 400 MHz / 2.5 ns 是控制时钟合同，不等价于 runtime probe。其纯覆盖结果如下；5.70 ns 仅是冻结 one-shot 的非重叠实现参考。

| 参考 period | 0.95 V L2 clean 覆盖率 | 1.10 V L2 clean 覆盖率 | 目标全相位保证 |
|---|---:|---:|---|
| 2.500 ns 控制时钟 | 83.00% | 93.00% | False |
| 5.700 ns one-shot 参考 | 36.40% | 40.79% | False |

## T0-7 严重欠压边界

- `VDD_MONITORED < 0.80 V` 不作精确 timing-trip 声明；下游仅可采用 heartbeat、stuck-Q、timeout 或无有效检测结果等 fail-safe 语义。

## 证据、图与账本

- 正式图：`analysis/t0_transient_droop/figures/figure_manifest.json`（五张 PDF + 600 dpi PNG；manifest 记录输入、脚本和 DL 环境 hash）。
- 下游合同：`analysis/t0_transient_droop/contract/T0_DOWNSTREAM_D0_TIMING_CONTRACT.json`。
- T0-5 物理证据账本保持：新增 HSPICE 139；电气等价复用 46；禁止流程新增运行 0。
- 本轮 T0-6 interval mapping：新增 HSPICE 0；复用/重解析 HSPICE 0；T0-8 绘图和报告：HSPICE 0。
- 未重跑 H0、M0、M1、RF、XA、T0-2、T0-3、T0-4 或 T0-5；未实现 D0 RTL、DLL、时钟或 FSM。
