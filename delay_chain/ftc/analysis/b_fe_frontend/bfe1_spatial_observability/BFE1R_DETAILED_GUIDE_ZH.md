# B-FE1R 详细审查说明

## 目的与边界

B-FE1R 是对 B-FE1 提交 `59a852c80d44c15b54726a095e0476c3d382cc4c`
的极短修正审查。它不创建或重跑 HSPICE deck，不进入 B-FE2，也不实现真实 latch，
不修改 M/F、控制器或 legacy sensor。其输入仅为已经保存的四个 B-FE1 场景元数据、
`normal_l2_pairwise_discrimination.json` 及库文件；输出是 XOR 选择闭合、候选采样
窗口重排名和轻量可追溯证据清单。

因此 `BFE1R_READY_FOR_BFE2` 的含义是“B-FE1 的 LVT XOR 选择和后续 latch 研究
优先窗口已经闭合”，不是“真实 latch 阵列、关闭孔径、M/F、校准或运行时检测已经
完成”。原有 `BFE1_SPATIAL_OBSERVABILITY_GO` 继续有效，未被本审查替换。

## 一、XOR2_X0P5M 的 LVT/RVT 不一致如何闭合

legacy FTC sensor 使用 `XOR2_X0P5M_A9TR40`（RVT）；B-FE1 根据其独立前端合同
使用 `XOR2_X0P5M_A9TL40`（LVT）。两者并非同一模型，因此不能把 legacy 的 RVT
结果直接当作 B-FE1 的 LVT 电气证据。

本审查对 SMIC40LL 的 TT/1.10 V/25 C Liberty 和对应 CDL 做了静态、只读比较：

| 项目 | LVT：`A9TL40` | RVT：`A9TR40` | 结论 |
|---|---:|---:|---|
| 功能 | `Y=A XOR B` | `Y=A XOR B` | 一致 |
| CDL 端口 | `Y VDD VNW VPW VSS A B` | 相同 | 一致 |
| CDL 晶体管数 | 10 | 10 | 一致 |
| 设备 W/L | 120/190 nm、L=40 nm | 相同 | 拓扑尺寸一致 |
| Liberty area | 1.6758 | 1.6758 | 一致 |
| A 输入电容 | 0.00121463 | 0.00115199 | LVT +5.44% |
| B 输入电容 | 0.000612013 | 0.000572185 | LVT +6.96% |

两者差异是阈值电压模型：LVT 使用 `nlvt11ll_ckt/plvt11ll_ckt`，RVT 使用
`n11ll_ckt/p11ll_ckt`。这是预期的库差异，不是端口或逻辑连接错误。LVT 负载略大，
但 B-FE1 的四个正式 transistor 场景已经把这 30 路真实 LVT XOR 输入电容加载到每对
RVT/LVT tap 上，并得到 30 tap 全单调、非碎裂的空间码结果。因此该额外负载已被实测
覆盖，而不是假定可忽略。

Liberty 组合弧的均值对比也没有给出“LVT 系统性变慢”的证据：A/B 的主要
`cell_rise/cell_fall` 项相对 RVT 多为约 6–18% 更低；转换时间项目在约 ±4% 内，
个别 rise transition 略高。这与 LVT 作为前端观测 XOR 的适用性一致。

正式选择是继续使用 LVT `XOR2_X0P5M_A9TL40`。如果改回 RVT，输入负载和输出延迟
都会改变，当前 B-FE1 的四个 `.tr0` 不再是该拓扑的证据；必须重跑四个 B-FE1 场景。
本阶段明确没有执行该重跑。

## 二、为什么不只选“最宽”的 RAW_CODE 平台

B-FE1 的共同判别平台已经保证 normal/L2 在同一 `Tsample` 区间内稳定、非空、
不贴边、码不同且没有 undefined bit。不过，后续真实 latch 关闭窗口还应偏好：

- 更宽的时间区间；
- 正常/L2 两边都距 tap 0 和 tap 29 有较多余量；
- 较大的汉明距离和较清晰的 `START/END/CENTER` 位移；
- 更高的两边最小 bit 电压裕量；
- 中部 tap，而非接近观察窗口边界；
- 单一连续 1 串、无并列最长串、无碎裂和无未定义 bit。

所以 B-FE1R 从既有 `normal_l2_pairwise_discrimination.json` 的全部 134 个候选中，
以以下归一化分数排序：

```text
score = fragmentation_factor × (
    0.30 × normalized_width
  + 0.20 × normalized_minimum_four_sided_headroom
  + 0.15 × normalized_hamming_distance
  + 0.15 × normalized_abs(ΔSTART, ΔEND, ΔCENTER)
  + 0.15 × normalized_minimum_bit_margin
  + 0.05 × center_tap_preference
)
```

`fragmentation_factor` 只有在 normal/L2 都是单一、无并列、无 undefined bit 的连续
主 1 串时为 1，否则为 0。该分数不是新运行时检测算法，也不修复 RAW_CODE；只是让
后续 latch 研究优先检查更宽、更居中、更有电压/码元区分度的现有物理平台。

完整的 65 个 0.95 V、69 个 1.10 V 排名以及各项原始数值均在
`BFE1R_REVIEW_STATUS.json` 中。原始未压缩平台记录仍只存在于
`normal_l2_pairwise_discrimination.json`。

## 三、优先窗口结果

### 0.95 V：中部 tap 明确优于旧报告最大宽度窗口

旧报告只按宽度选择的最大平台为 138.300487–154.328075 ps，宽 16.027588 ps。
它虽然最长，但 normal/L2 的平均主串中心只有 tap 3.50，最小四侧 headroom 仅为
1 tap，汉明距离为 2，因此不适合作为第一个真实 latch 关闭窗口研究点。

| 排名 | 平台范围 (ps) | 宽度 (ps) | 平均中心 | 最小 headroom | HD | \|ΔSTART\|+\|ΔEND\|+\|ΔCENTER\| | 最小 bit 裕量 (V) | 分数 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 410.717842–424.631112 | 13.913270 | 14.75 | 7 | 7 | 10.5 | 0.232330 | 0.709451 |
| 2 | 395.535621–409.692173 | 14.156552 | 14.25 | 8 | 7 | 10.5 | 0.190100 | 0.701289 |
| 3 | 430.859669–444.837399 | 13.977730 | 15.75 | 6 | 7 | 10.5 | 0.206446 | 0.677168 |
| 旧最大宽度 | 138.300487–154.328075 | 16.027588 | 3.50 | 1 | 2 | 3.0 | 0.238963 | 0.520900 |

因此，0.95 V 的中部窗口不以牺牲可读性来换取宽度：它们仍有约 14 ps 的正宽度，
并显著增加两侧观察余量、汉明距离和空间码位移。后续 latch 研究应优先从排名 1、2
开始，而非沿用旧报告的早期边缘窗口。

### 1.10 V：首选窗口同样位于中部

| 排名 | 平台范围 (ps) | 宽度 (ps) | 平均中心 | 最小 headroom | HD | \|ΔSTART\|+\|ΔEND\|+\|ΔCENTER\| | 最小 bit 裕量 (V) | 分数 |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 300.987260–312.678869 | 11.691609 | 14.25 | 8 | 9 | 13.5 | 0.240996 | 0.756114 |
| 2 | 263.013042–274.903764 | 11.890722 | 12.25 | 7 | 7 | 10.5 | 0.257242 | 0.708649 |
| 3 | 329.289906–340.074141 | 10.784235 | 15.75 | 6 | 9 | 13.5 | 0.222074 | 0.692635 |

这里排名第一的平台并非 1.10 V 中最宽，但其中心位置、8 tap headroom、HD=9 和
较大的描述量位移使其整体最适合作为后续 latch 关闭窗口的第一个研究候选。

## 四、轻量证据清单和可追溯性

`BFE1R_EVIDENCE_MANIFEST.json` 只记录以下紧凑信息，不复制巨大 `.tr0`：

- 四个场景的 identity、baseline/droop/phase 和 T0 authority scenario key；
- `bfe1.sp` SHA256、`bfe1.tr0` SHA256、HSPICE W-2024.09 版本；
- 各 trace 的 record count 和固定的 93 列（`TIME + 92` B-FE1 probes）；
- B-FE0、T0、配置和 cell discovery 的输入权威工件 SHA256；
- BFE1 原始分析 JSON/报告以及 BFE1R 状态/报告的 SHA256；
- LVT/RVT CDL 与 Liberty 的 SHA256。

对应原始 `.tr0` 仍只保存在受 `.gitignore` 管理的
`delay_chain/ftc/runs/b_fe_frontend/scenarios/`；本审查不复制其数据到 analysis 或 Git。

## 五、Gate 解释

`BFE1R_READY_FOR_BFE2` 是本次允许的三种 B-FE1R Gate 之一。它依赖以下事实：

1. LVT XOR 的端口、功能、加载和 Liberty/CDL 来源可追溯；
2. LVT 是已保存 B-FE1 四场景的实际被测 cell，不存在“用 RVT 数据替 LVT 结论”的
   错置；
3. 两个正式 baseline 都保留了多条正宽度、非碎裂、中部可用的候选平台；
4. 四场景 deck/tr0/authority/分析 SHA 都可核对；
5. 本阶段 0 个新 HSPICE，并且现有 BFE1 GO 未被推翻。

它只解除“是否值得启动 B-FE2 真实 latch 阵列研究”的前置审查。任何 B-FE2 仍必须
单独表征 latch 输入负载、关闭孔径、亚稳态、气泡及最小稳定平台；不得把本说明当作
这些后续问题已解决的证据。
