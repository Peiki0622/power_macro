# BFE10-D01-MISS0：D01 ARCH0 MISS 机制离线审计

最终 gate：`BFE10_D01_ARCH0_MISS_MECHANISM_FROZEN`

本报告只读取冻结的 BFE8/BFE9 retained artifacts。没有启动 HSPICE、VCS、PrimeSim 或 DC；没有修改 production RTL、frontend、波形、30-seed population、reference、margin 或 ARCH1。

## 1. 标量 D_M 分布与诊断 sweep

健康 RISE retained 样本为 360 个，D01 target 为 30 个，D02 target 为 30 个。健康 RISE 的 D_M 范围为 0..22，D01 为 20..45，D02 为 41..72。
诊断规则为 `alarm iff D_M > T`，仅用于 retained sample sensitivity，不改变锁定的 RISE=22/FALL=24 margin。D01 全覆盖需要 `T <= 19`；健康 RISE 零观测误报需要 `T >= 22`；交集为空，因此不存在可同时满足两者的单一 scalar threshold。

## 2. 八个 MISS 的空间审计

| Seed | D01 D_M | H_D | D01 Hamming | D01 changed taps | ΔM D01 | D02 Hamming | ΔM D02 | 机制 |
|---:|---:|---:|---:|:---|---:|---:|---:|:---|
| 41005 | 21 | -1 | 1 | 21 | +21 | 3 | +60 | SCALAR_THRESHOLD_OVERLAP+SPATIAL_COMPRESSION_LOSS |
| 41007 | 21 | -1 | 1 | 21 | +21 | 3 | +60 | SCALAR_THRESHOLD_OVERLAP+SPATIAL_COMPRESSION_LOSS |
| 41012 | 21 | -1 | 1 | 21 | +21 | 3 | +60 | SCALAR_THRESHOLD_OVERLAP+SPATIAL_COMPRESSION_LOSS |
| 41015 | 21 | -1 | 1 | 21 | +21 | 3 | +60 | SCALAR_THRESHOLD_OVERLAP+SPATIAL_COMPRESSION_LOSS |
| 41016 | 22 | 0 | 1 | 22 | +22 | 3 | +63 | SCALAR_THRESHOLD_OVERLAP+SPATIAL_COMPRESSION_LOSS |
| 41022 | 21 | -1 | 1 | 21 | +21 | 2 | +41 | SCALAR_THRESHOLD_OVERLAP+SPATIAL_COMPRESSION_LOSS |
| 41025 | 20 | -2 | 1 | 20 | +20 | 3 | +57 | SCALAR_THRESHOLD_OVERLAP+SPATIAL_COMPRESSION_LOSS |
| 41028 | 21 | -1 | 1 | 21 | +21 | 3 | +60 | SCALAR_THRESHOLD_OVERLAP+SPATIAL_COMPRESSION_LOSS |

八个 MISS 的 D01 q_ff 相对同 seed healthy RISE 均只改变一个 tap：41005/41007/41012/41015/41022/41028 为 tap 21，41016 为 tap 22，41025 为 tap 20。D01 的 `N=sum(q)` 增量均为 +1，D01 `ΔM` 为 +20/+21/+22；匹配的 D02 target 改变 2～3 个 taps，产生更大的 `|ΔM|`。

## 3. 机制结论

结论为混合机制：`SCALAR_THRESHOLD_OVERLAP + SPATIAL_COMPRESSION_LOSS`。标量层面，D01 的 20..22 M-code 信号与健康 RISE 的最大 D_M=22 重叠；空间层面，30 mV D01 在这些 process instances 只保留一个高位 tap 的输出变化，而 60 mV D02 保留两个或三个 tap 变化。
`FRONTEND_LOW_OBSERVABILITY` 在本审计中不能作为独立模拟因果机制从 q_ff-only retained evidence 中分离出来。证据支持的是 frontend 输出端的低空间可观测性/压缩现象；没有内部模拟节点或新增仿真，不能进一步断言具体晶体管级原因。

MISS 是 sensor/detector observability miss，不是 timing fault 结论；本报告也不据两种 amplitude 推导连续 minimum detectable voltage，不重新选择 margin，不继续执行 D04，也不实现 ARCH1。

仿真 accounting：HSPICE=0，VCS=0，PrimeSim=0，DC=0。
