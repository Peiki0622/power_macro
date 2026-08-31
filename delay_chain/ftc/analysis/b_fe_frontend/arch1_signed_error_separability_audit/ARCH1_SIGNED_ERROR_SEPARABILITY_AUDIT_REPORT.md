# ARCH1 signed-error separability audit

Final gate: `ARCH1_SIGNED_ERROR_SEPARABILITY_AUDIT_FROZEN`

本阶段只复用冻结的 BFE8/BFE9/BFE10 retained artifacts，审计 SUBTRACT 后、ABS 前的 signed error `e=M_FF-M_REF_RISE`。没有修改 production RTL、frontend、waveform、process population、startup reference、M_MARGIN_RISE=22、M_MARGIN_FALL=24 或 ARCH1 candidate。没有运行 HSPICE、VCS、PrimeSim、DC。

## 分布

| Dataset | Samples | signed-e min / median / max | positive min / max |
|---|---:|---:|---:|
| Healthy RISE | 360 | -22/0.0/18 | 6/18 |
| D01 target 30 mV | 30 | 20/28.5/45 | 20/45 |
| D02 target 60 mV | 30 | 41/60.0/72 | 41/72 |

正向 signed-e 分位数（p05/p25/p50/p75/p95）：Healthy RISE `{'p05': 6.0, 'p25': 6.0, 'p50': 6.0, 'p75': 6.0, 'p95': 17.0}`；D01 `{'p05': 21.0, 'p25': 22.25, 'p50': 28.5, 'p75': 40.0, 'p95': 44.099999999999994}`；D02 `{'p05': 45.900000000000006, 'p25': 57.25, 'p50': 60.0, 'p75': 63.0, 'p95': 67.64999999999999}`。完整 signed-e 计数、正向计数和每个 retained sample 均记录在 CSV/JSON。

## 诊断 sweep

规则为 `e > T_POS`，仅对 retained samples 做诊断。D01 30/30 的整数阈值为 `T_POS=0..19`；Healthy RISE 零观测正向误报的整数阈值为 `T_POS=18..435`；交集为 `18..19`，连续可行区间为 `[18,20)`。因此 signed-error alone 在本 retained population 上存在分离区间。

相对现有 RISE `abs(e)>22`：正式规则在 D01 为 22/30；诊断 `e>18` 为 30/30，并且 Healthy RISE 误报为 0。新增价值是 retained D01 coverage 增加 8 个 seed；这不是正式 margin 重选，也不是新 comparator 的实现依据。

## 范围限制

本结果只证明当前两种冻结 amplitude 与当前 retained process samples 上，signed direction 的局部分离价值。它不实现完整 ARCH1、不改变现有 ARCH1 candidate、不运行 D04，也不构成连续 minimum detectable voltage 或 silicon guarantee。
仿真 accounting：HSPICE=0，VCS=0，PrimeSim=0，DC=0。
