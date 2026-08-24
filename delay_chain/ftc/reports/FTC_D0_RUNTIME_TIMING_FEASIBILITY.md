# FTC D0-0 运行时 probe 微时序可行性

## 结论

**ARCHITECTURE_REVIEW**。在不修改冻结 `FTC_SENSOR`、H0、M1、T0 合同和既有物理证据的条件下，不能构造 `P_runtime <= 2075 ps` 的连续 probe 微时序。D0-0 没有实现 FSM、alarm、heartbeat 或 timeout，也没有改变 M1 的静态 M/F 输出配置。

本结论是零 HSPICE 的合同算术，不把 400 MHz / 2.5 ns 控制时钟等同于 runtime probe，也不把现有 5.70 ns one-shot 参考直接压缩为新设计。

## 已复用的冻结证据

| 从本 probe 的 `S_CLK rise` 起 | 已验证事件 | 偏移 (ps) |
|---|---:|---:|
| -490 | reset release | -490 |
| 0 | `S_CLK rise` | 0 |
| +2300 | Q sample 1 | 2300 |
| +2500 | Q sample 2 / 双采样判决完成 | 2500 |
| +2700 | reset assert start | 2700 |
| +2710 | reset assert end | 2710 |
| +3000 | `S_CLK fall` | 3000 |
| +5700 | recovery end | 5700 |

M0 的真实 DFF 判定仍是两次稳定 Q 采样都满足阈值后的 `stable_real_dff_q_equals_1`；本轮未以残余时间或数字推断替代它。

## 连续 probe 的最早合法关系

令当前 `S_CLK rise` 为 `t=0`。下一次 probe 自己的 reset release 必须先于下一次 `S_CLK rise` 490 ps。当前 probe 又必须先完成 Q2、随后 reset assert 200 ps、保持 reset 10 ps。因此在**甚至尚未要求 recovery 完成**的最乐观串行预算中：

```text
Q2 complete                  = 2500 ps
Q2 -> reset assert start     =  200 ps
reset assert width           =   10 ps
next reset release -> rise   =  490 ps
------------------------------------------------
next S_CLK rise earliest     = 3200 ps
```

这个 3200 ps 只是下界，不是已经验证的连续 cadence：现有 `S_CLK` 本身到 3000 ps 才 fall，内部 recovery 到 5700 ps 才结束。它们不能被当作可以免费重叠的时间。

若强制按 T0 要求在 2075 ps 发起下一次 rise，当前 probe 仍有下列动作尚未发生：

| 当前 probe 未完成事件 | 相对该错误 next rise 的滞后 (ps) |
|---|---:|
| Q sample 1 | 225 |
| Q sample 2 | 425 |
| reset assert start | 625 |
| `S_CLK fall` | 925 |
| recovery end | 3625 |

最直接的矛盾是 Q2 本身在 2500 ps，已经比目标周期晚 425 ps；完整的 reset→下一 rise 串行下界则比目标周期晚 1125 ps。因而无法用冻结单 capture DFF/控制时序得到一次真实、可重复的双采样判决和相邻 reset 周期。

## HSPICE 与范围边界

本轮 HSPICE = 0；没有重跑 T0-3、T0-4、M0、M1、H0、RF 或 XA。没有提出多 probe HSPICE deck，因为合同算术已表明没有一个保持冻结事件关系的 `<= 2075 ps` 候选序列；在此之前人为猜测更早 fall、更早 reset 或重叠 capture 的波形，会先改变本阶段禁止改动的时序前提。

需要架构评审的具体瓶颈是：单一真实 DFF capture 路径需要一个 `S_CLK` 波形、两次独立稳定 Q 观察以及 probe 间 reset，而这些已验证事件在目标周期内无法串行完成。不能以更复杂的数字 FSM 掩盖这一物理/时序矛盾。

## Provenance

| 输入 | SHA-256 |
|---|---|
| M0 single-probe contract | `3cadeaa3bcb0f064ce53751acd1af8456a043843e4733455b6b2250258faeea7` |
| T0 downstream D0 timing contract | `e666d94526ecd1cdd254bc0bbd5eb1dc12e8693debf782399de72cc246f0618f` |
| M1 downstream handoff | `736b0ec505af181ecfe53d587e6123633ea354b108099dec0a6366da3718bca5` |

机器可读预算：[D0_0_RUNTIME_TIMING_BUDGET.json](../analysis/d0_runtime_timing/contract/D0_0_RUNTIME_TIMING_BUDGET.json)。
