# B-FE1 空间码图解

本说明对应 `bfe1_spatial_observability/figures/` 中的六张自动生成图。
它们都由保存的四个 B-FE1 transistor transient 的 JSON 后处理产生；绘图不新增
HSPICE 场景，也不修改任何 legacy sensor 文件。

## 先读懂空间码

每一个可观察 tap 都有一对同索引路径节点 `rvt_i`、`lvt_i`，并由真实
`XOR2_X0P5M_A9TL40` 产生 `xor_i`。对任意理想采样时刻 `Tsample`，离线定义：

```text
bit[i] = 1，当且仅当 V(xor_i, Tsample) > 0.5 × V(VDD_MONITORED, Tsample)
```

30 个 bit 按 `tap_0` 到 `tap_29` 的升序写为 `RAW_CODE`；因此 JSON 和报告中
字符串的最左字符是 tap 0，最右字符是 tap 29。深蓝色代表 `bit[i]=1`，浅色代表
`bit[i]=0`。这里的阈值随瞬时本地 `VDD_MONITORED` 变化，绝不是固定绝对电压。

图只显示包含非空 1 串的有效波前窗口。仿真仍保存到 7 ns；波前之后的全 0 区间
保留在 `spatial_code_intervals.json`，但若画到横轴会把实际码元压缩到不可读的像素
宽度。图中每一个垂直色带边界都来自真实 XOR 阈值 crossing，未使用人为 5 ps 或
25 ps 时间采样网格。

## 图 1：`bfe1-095-n_spatial_code.png`

这是 0.95 V、无电压跌落（normal）的原始空间码时空图。

- 横轴是相对唯一一次 `S_CLK` 上升沿的理想 `Tsample`，单位 ps；
- 纵轴是物理 tap 索引，tap 0 在底部、tap 29 在顶部；
- 深蓝 1 带随时间从低 tap 向高 tap 移动、扩展后收缩，反映两条继承的 RVT/LVT
  延迟路径在真实 XOR 负载下仍保持不同传播时间；
- 图中的阶梯边界是逐级 tap crossing 的实际结果，而非空间码修复或平滑处理。

此图本身不表示“报警”或最终采样点；它只是 normal 条件下全部可能理想采样时刻的
原始码族。

## 图 2：`bfe1-095-l2_spatial_code.png`

这是 0.95 V 基线下，从 0.95 V 跌落到 0.86 V 的正式 L2 / 3002 ps 波形。
其坐标和颜色定义与图 1 完全相同。把图 1、图 2 在同一个横轴 `Tsample` 对齐后，
比较蓝色带的 `START`、`END`、`LEN`、`CENTER` 或完整 `RAW_CODE`，即可观察
normal/L2 的空间响应变化。

不能仅比较每张图中“最宽的蓝带”来判断；B-FE1 的判别规则要求 normal 和 L2
必须在**同一**采样时间区间内都稳定，然后才比较两边码字。

## 图 3：`bfe1-110-n_spatial_code.png`

这是 1.10 V、无跌落的 normal 空间码图。它检查第二个正式基线下，30 路真实 XOR
加载仍没有破坏连续 1 带或逐级波前顺序。由于电压和延迟不同，蓝带的时间位置不能
直接与图 1 的数值位置等同。

## 图 4：`bfe1-110-l2_spatial_code.png`

这是 1.10 V 基线下，从 1.10 V 跌落到 0.96 V 的正式 L2 / 3002 ps 图。它应与图 3
成对阅读，方法与图 1、图 2 相同。两对图共同覆盖 B-FE1 计划规定的两个正式
baseline，而不是 PVT、Monte Carlo、完整 phase 覆盖或重复 probe 的结论。

## 图 5：`spatial_metrics.png`

这张图把每个 `RAW_CODE` 的最长连续 1 串压缩为四项描述量：

- `START`：最长连续 1 串的第一个 tap；
- `END`：最长连续 1 串的最后一个 tap；
- `LEN`：该串长度；
- `CENTER`：`(START + END) / 2`。

横轴仍是相对 `Tsample`。每条阶梯线只在真实 crossing 边界改变。该图方便比较
normal/L2 的码带移动趋势，但不是编码器输出：完整 `RAW_CODE`、所有相等最长串、
是否空码、是否贴边及是否碎裂均仍保存在 `spatial_code_intervals.json`，未被这四个
标量掩盖。

## 图 6：`common_discrimination_platforms.png`

每条横条是一段合格的“共同判别平台”。在该横条所对应的同一 `Tsample` 区间内：

1. normal 与 L2 的 `RAW_CODE` 都恒定；
2. 两边主 1 串都非空且不贴 tap 0 / tap 29 观察边界；
3. 两边 `RAW_CODE` 不同，且 `START`、`END`、`LEN`、`CENTER` 至少一项不同；
4. 区间宽度严格大于 0，且其中没有阈值未定义 bit。

每一条都被保存在 `normal_l2_pairwise_discrimination.json`；图没有挑选单个最好看
的点。横条宽度是本阶段由物理 crossing 得到的理想离线采样窗口，**不等于**最终
latch 的可用 aperture 或时序裕量。真实 latch 输入负载、关闭孔径、亚稳态与采样
控制仍属于尚未实施的 B-FE2/B-FE3。

本轮最大的共同判别平台如下：

| Baseline | 平台范围（相对 `S_CLK` 上升沿） | 宽度 | normal RAW_CODE | L2 RAW_CODE |
|---:|---:|---:|---|---|
| 0.95 V | 138.300487–154.328075 ps | 16.027588 ps | `001111100000000000000000000000` | `011111000000000000000000000000` |
| 1.10 V | 263.013042–274.903764 ps | 11.890722 ps | `000000000011111111100000000000` | `000000011111111000000000000000` |

## 结论边界

六张图支持的结论仅是：在固定 4/0 前缀、30 tap 和真实 XOR 加载下，两个正式
baseline 的 normal/L2 条件均存在正宽度、非边界、可解析的离线空间码判别平台。
因此 B-FE1 Gate 为 `BFE1_SPATIAL_OBSERVABILITY_GO`。它并不证明最终宏、真实
latch 阵列、M/F 采样发生器、启动校准、周期性运行或 2075 ps 闭合已经完成。
