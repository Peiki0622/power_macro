# B-FE1 多抽头空间可观测性报告

## Gate

**BFE1_SPATIAL_OBSERVABILITY_GO**

both formal baselines have a positive-width, interior, stable common discrimination platform

四个正式 transient 场景均只运行一次；每个保存的 `.tr0` 严格包含 `TIME + 92` 个计划定义观测项。

## 共同判别平台

| Baseline | 候选数 | 最大平台范围 (launch-relative ps) | 宽度 (ps) | normal RAW_CODE | L2 RAW_CODE |
|---:|---:|---:|---:|---|---|
| 0.95 | 65 | 138.300487–154.328075 | 16.027588 | `001111100000000000000000000000` | `011111000000000000000000000000` |
| 1.10 | 69 | 263.013042–274.903764 | 11.890722 | `000000000011111111100000000000` | `000000011111111000000000000000` |

全部 crossing、原始码区间、成对分段和平台均保存在相邻 JSON；六张图由这些 JSON 自动生成。
本阶段未实例化 latch、M/F、DFF、控制器，也未运行 PVT、Monte Carlo、全 phase 或重复 probe。
