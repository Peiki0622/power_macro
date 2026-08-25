# FTC 候选 B：从受监测域空间感知到安全域可靠捕获的逐阶段执行计划

> 本文件是候选 B 在 `bfe-multitap-latched-frontend` 分支上的唯一阶段执行计划。2026-08-25 在 B-FE2.2C 失败与 B-FE2-L0 安全域因果验证通过后重构。Codex 必须严格按 Gate 顺序推进；不得继续沿旧的“在 PD_SENSE 内寻找新的 latch close”路线试点。

---

# 0. 当前冻结状态与本轮架构纠偏

当前工作分支：

`bfe-multitap-latched-frontend`

本轮计划重构依据的最新验证提交：

`cad9610c8c37f45950a6b35dbc04e6f535abe0e2`

当前已经成立、后续不得通过重复仿真重新争论的事实如下。

1. B-FE0/B-FE1/B-FE1R 已证明“4 级 RVT 前缀 / 0 级 LVT 前缀 + 30 对 RVT/LVT 抽头 + 30 个真实 `XOR2_X0P5M_A9TL40`”能够形成随电压状态移动的空间信息；该感知几何目前继续冻结。
2. B-FE2.0/B-FE2.1 已证明真实 `LATQ_X0P5M_A9TR40` 的连接、透明高/下降关闭语义，以及 30 个 latch D 负载不会破坏前端空间可观测性。B-FE2.1 已执行 4 个新 HSPICE 场景，Gate 为 `BFE2_1_LATCH_LOAD_GO`。
3. 历史 B-FE2.2 在 `PD_SENSE/VDD_MONITORED` 内直接使用真实 latch 关闭，共执行 6 个新 HSPICE 场景；B-FE2.2R 用 0 个新 HSPICE 闭合了首次失败/retry 的因果分析。
4. B-FE2.2S 的“必须无任何 in-flight D→Q”规则曾得到 BLOCKED；修订后允许单次正常关闭后解析，离线选出 `sample_close=534.524618567 ps`。这两个 B-FE2.2S 版本都作为方法学历史证据保留，不得覆盖。
5. B-FE2.2C 在同一个 `sample_close=534.524618567 ps` 上又执行了 0.95 V normal 与 0.95→0.86 V formal L2 两个新物理场景，使 B-FE2.2 系列真实 HSPICE 累计达到 8 个。normal 的 tap27 出现一次可由 pre-close D 解释的 Q 上翻，随后出现 source-free Q 下翻，因此 Gate 为 `BFE2_2C_CORRECTED_SEED_FAILED`；不得再把此失败解释为“只需要第四/第五个关闭点”。
6. B-FE2-L0 严格保持同一 0.95 V normal/L2 stimulus、同一 30 路 XOR 波形和同一 `sample_close=534.524618567 ps`，仅把 XOR 后的接收/锁存语义改成：以 `VDD_SENSE` 为参考进行理想 0/1 恢复，并在固定 `PD_SAFE=0.95 V` 的理想透明高 latch 中保持。该验证通过本地 VCS W-2024.09 行为 replay；PrimeSim XA W-2024.09 的官方 tutorial/preflight 也通过，但 XA tutorial 不是该 30-tap 电路的实际 transistor-level co-simulation。
7. B-FE2-L0 Gate 为 `BFE2_L0_SAFE_DOMAIN_PASS`：normal 最终 Q 为 `000000000000000111111111111111`，L2 最终 Q 为 `000000000001111111111111000000`，Hamming distance=10；两边均无 post-close Q crossing/re-flip，最终 Q 全摆幅、稳定。
8. B-FE2-L0 只证明：**理想电压域恢复 + 安全域理想锁存语义能够消除当前已观察到的失败，同时保留空间可分辨性**。它不证明真实 level shifter 已存在，也不证明真实 `LATQ_X0P5M_A9TR40` 在 `PD_SAFE` 下已经通过。
9. 因此从本提交起，候选 B 的主问题从“在受监测域继续寻找更好的 G close”改为“建立并逐步收敛 `PD_SENSE → 跨域恢复接口 → PD_SAFE 捕获` 的物理契约”。

本轮正式废止旧的主链：

```text
B-FE2.2C FAIL
   -> 再找 corrected seed
   -> B-FE2.3 在 PD_SENSE 内扫 global-G aperture
```

新的唯一主链为：

```text
B-FE2-L0   DONE / ideal restoration + ideal safe-domain latch / PASS
    |
    v
B-FE2-L1A  ideal restoration + REAL LATQ @ PD_SAFE
    |
    +-- FAIL --> 停止，进入 capture-cell review；不得靠换 close 掩盖
    |
    v
B-FE2-L1B  REAL LATQ @ PD_SAFE + bounded non-ideal crossing model
    |
    +-- FAIL --> 输出 interface-spec BLOCKED/INCONCLUSIVE
    |
    v
B-FE2-L2   集成 PD_SENSE 前端 + 跨域接口模型 + PD_SAFE 真实捕获
    |
    +-- FAIL --> 回到接口/负载/捕获契约复审，不改 sensing geometry
    |
    v
B-FE2-L3   在新跨域架构上闭合真实 sample-close aperture
    |
    v
BFE2_SAFE_DOMAIN_FRONTEND_GO
    |
    v
B-FE3 / B-FE4 / B-FE5
```

---

# 1. 最终宏的唯一主路线

从本轮开始，候选 B 的电源域边界固定为：

```text
                         S_CLK
                           |
              +------------+------------+
              |                         |
         4级RVT前缀                  0级LVT前缀
              |                         |
         30级RVT路径                30级LVT路径
              |                         |
       rvt_0 ... rvt_29          lvt_0 ... lvt_29
              |                         |
              +------------+------------+
                           |
                 30 x XOR2_X0P5M_A9TL40
                           |
                    xor_0 ... xor_29
                           |
                  [ PD_SENSE 边界 ]
                           |
          30 x voltage-domain restoration interface
                           |
                    safe_d_0 ... safe_d_29
                           |
                   [ PD_SAFE 边界 ]
                           |
                30 x LATQ_X0P5M_A9TR40
                           |
                     q_0 ... q_29
                           |
                    稳定30位空间码
                           |
                 START / END / LEN / CENTER
                           |
              +------------+------------+
              |                         |
           启动自校准                运行时检测
              |
              v
       trusted programmable sample_close
```

电源职责固定为：

- `PD_SENSE / VDD_MONITORED`：只承担对被监测电压敏感的 RVT/LVT delay path 与 XOR 空间信息形成。
- `PD_SAFE / VDD_SAFE`：承担真实 latch 捕获、空间码保存与后续数字处理；研究阶段首先固定 `VDD_SAFE=0.95 V` 以保持 B-FE2-L0 连续性。
- `sample_close/G` 必须属于可信控制/安全域语义，不能再由受跌落电源直接决定可靠性。
- `PD_SENSE → PD_SAFE` 之间必须存在显式的跨电压域恢复接口。SMIC40 当前数字库未提供可直接使用的真实 level-shifter cell，因此研究阶段允许用 VCS/VCS-AMS/RNM/Verilog-AMS 或等价 mixed-signal 行为模型定义接口 contract；该模型不得被描述成已实现的物理 level shifter。

`sample_close` 仍表示 30 个捕获单元公共 G 的关闭时刻，但只有在 B-FE2-L2 证明完整跨域结构成立后，才允许进入新的 aperture 搜索。

---

# 2. 永久防跑偏规则

以下行为在本分支禁止，除非人工再次修改本计划。

- 禁止恢复 `xor_29` 单点检测主线。
- 禁止把 XOR 脉冲或延迟 XOR 脉冲直接作为 DFF clock。
- 禁止回到“脉冲拉宽满足 DFF minimum pulse width”作为候选 B 主路线。
- 禁止在 B-FE2-L1A/L1B/L2 通过前继续尝试新的 `sample_close`、新的 G 相位或新的 G sweep。
- 禁止为了修 Gate 修改 4/0 prefix、30 taps、正式 0.95→0.86 V L2 波形、LVT XOR 单元身份或 B-FE2.2C 固定 close。
- 禁止把 B-FE2-L0 的理想行为 latch 称为真实 `LATQ_X0P5M_A9TR40` 验证。
- 禁止把 PrimeSim XA 官方 tutorial/preflight PASS 称为候选 B 电路已经完成 XA mixed-signal 验证。
- 禁止把 B-FE2-L0 的 `xor > 0.5*VDD_SENSE` 零延迟恢复模型称为真实 level shifter。
- 禁止把接口做成理想模型后直接进入 PVT/Monte Carlo/signoff；必须先经过 L1A、L1B、L2。
- 禁止用行为模型删除、滤掉或手工压制 XOR 毛刺来制造 PASS；任何 pulse rejection/min-pulse 行为必须在 L1B 中作为显式接口参数研究。
- 禁止把 B-FE2.2R 的 5 ps 因果分类容差当作接口延迟、setup/hold、安全余量或 G 精度。
- 禁止把旧 T0 的 2075 ps 或旧 M/F codebook 直接继承为新架构运行时参数。
- 禁止覆盖、删除或重命名 B-FE2.2/B-FE2.2R/B-FE2.2S/B-FE2.2C 的失败工件；这些是架构转向的冻结证据。
- 禁止在 B-FE2-L3 之前做大规模 PVT、Monte Carlo、全攻击相位、面积裁剪、运行时 FSM 或复杂 alarm logic。

---

# 3. 证据复用与仿真记账

## 3.1 先复用后运行

任何新仿真前必须先检查并记录：

- 输入 stimulus 来源；
- deck / testbench / behavior model；
- `.tr0` / replay probe / simulator log；
- simulator 与版本；
- 电气/行为签名；
- SHA256；
- source commit；
- Gate JSON / report。

拓扑、源波形、close、供电和模型完全一致时必须复用，禁止“为了保险”重跑。

## 3.2 当前冻结记账

```text
B-FE2.1        4 个新 HSPICE
B-FE2.2历史    6 个新 HSPICE
B-FE2.2C       2 个新 HSPICE
B-FE2.2R/S     0 个新 HSPICE
B-FE2-L0       0 个新 HSPICE；本地 VCS 行为 replay PASS
```

因此旧 `PD_SENSE` latch-close 路线已经有 8 个真实关闭 HSPICE 场景，禁止继续追加“另一个 close”。

## 3.3 新路线预算

- B-FE2-L1A：最多 **2 个新的真实 latch transistor-level/mixed-signal 场景**，仅 0.95 V normal/L2 固定 pair。
- B-FE2-L1B：优先行为/mixed-signal 参数实验，不得大范围暴力 sweep；在明确接口参数边界前不得新增感知链 HSPICE。
- B-FE2-L2：第一轮最多 2 个 0.95 V integrated pair；只有 PASS 后才允许最多再加 2 个 1.10 V integrated pair。
- B-FE2-L3：只有 L2 PASS 后才允许新的 sample-close aperture 搜索，预算另行由 L2 结果收敛，不得预先继承旧 B-FE2.3 的 16 场景额度。

“物理场景”按电气签名计数，而不是按脚本调用次数计数。

---

# 4. 当前阶段总图

```text
B-FE1/B-FE1R  空间可观测性                  DONE
       |
B-FE2.1       真实 latch D-load              DONE / GO
       |
B-FE2.2/R/S/C 旧 PD_SENSE latch-close 路线   FROZEN HISTORY
       |                                     BFE2_2C_CORRECTED_SEED_FAILED
       |
       +----------------------------------------------+
                                                      |
B-FE2-L0      ideal restoration + ideal PD_SAFE latch DONE / PASS
                                                      |
                                                      v
B-FE2-L1A     ideal restoration + REAL LATQ @ PD_SAFE    <-- NEXT
                                                      |
                         +----------------------------+------------------+
                         | FAIL                                          | PASS
                         v                                               v
              CAPTURE_CELL_REVIEW_REQUIRED                       B-FE2-L1B
              不得换 close 掩盖失败                      bounded non-ideal interface
                                                                         |
                                                                         v
                                                                    B-FE2-L2
                                                      integrated PD_SENSE->PD_SAFE
                                                                         |
                                                                         v
                                                                    B-FE2-L3
                                                        safe-domain sample-close aperture
                                                                         |
                                                                         v
                                                      BFE2_SAFE_DOMAIN_FRONTEND_GO
                                                                         |
                                                                         v
                                                          B-FE3 / B-FE4 / B-FE5
```

每个新子阶段必须独立提交并发布机器可读 Gate。一个提交不得跨越两个尚未解锁的阶段。

---

# 5. 历史阶段冻结结论

## 5.1 B-FE2.1

B-FE2.1 继续作为前端加载证据使用，但其“latch 与 XOR 同在 PD_SENSE”的供电连接不再代表最终宏拓扑。

其权威价值仅包括：

- 30 个真实 latch D 负载未破坏空间可观测性；
- 已保存 30 路真实 XOR 与透明态 D→Q 历史；
- 提供旧架构 closing-race 的因果对照。

不得因为最终 latch 移到 `PD_SAFE` 就删除这些数据。

## 5.2 B-FE2.2 / B-FE2.2R / B-FE2.2S / B-FE2.2C

这些阶段统一改为 **FROZEN HISTORICAL EVIDENCE**。

它们证明：

- 在 `PD_SENSE` 内同时让 sensing path、XOR 与真实 latch 经历受监测供电，会产生难以通过单一 global G close 稳健消除的 closing/re-flip 行为；
- 修改 seed 语义可以改变失败 tap，却没有给出足够理由继续用新的 close 试点；
- B-FE2.2C 的 final normal/L2 code 仍有可分辨信息，因此感知信息本身并未消失。

它们不再授权 B-FE2.3。

---

# 6. B-FE2-L0：安全域 Level-0 因果验证

状态：**DONE**

Gate：

`BFE2_L0_SAFE_DOMAIN_PASS`

固定条件：

```text
source stimulus: B-FE2.2C immutable 0.95-V normal/L2 XOR waveforms
sample_close:    534.524618567 ps
PD_SAFE:         0.95 V
interface:       safe_d=0.95 V if xor>0.5*VDD_SENSE else 0 V
interface delay: 0
interface slew:  ideal
hysteresis/X:    none
latch:           ideal transparent-high / hold-low behavior
```

冻结结果：

```text
normal final Q = 000000000000000111111111111111
L2 final Q     = 000000000001111111111111000000
Hamming        = 10
post-close Q crossings = 0 / 0
re-flip taps           = [] / []
```

L0 的唯一结论是：安全域恢复方向有继续研究价值。L0 不允许直接跳到 B-FE3。

---

# 7. B-FE2-L1A：理想跨域恢复 + 真实 LATQ@PD_SAFE

这是 Codex 从当前提交之后**必须立即执行的下一阶段**。

## 7.1 唯一问题

回答：

> 保持 B-FE2-L0 的理想跨域恢复不变，仅把理想行为 latch 替换成真实 `LATQ_X0P5M_A9TR40`，并让真实 latch 的 `VDD/VNW/VPW/VSS` 正确属于稳定 `PD_SAFE=0.95 V` 后，B-FE2.2C 中的 source-free post-close re-flip 是否仍然存在？

这是单变量因果实验，不是接口优化阶段。

## 7.2 必须冻结的条件

- 仍使用 B-FE2.2C 的 0.95 V normal 与 0.95→0.86 V L2 source stimulus；
- `sample_close` 固定 `534.524618567 ps`；
- 30 taps、4/0 prefix、LVT XOR 身份不变；
- 理想跨域判决仍为 `xor > 0.5*VDD_SENSE`；
- 理想接口仍为零额外 delay、零额外 slew、无 hysteresis、无 X-region；
- latch 必须恢复为真实 `LATQ_X0P5M_A9TR40`；
- latch 供电固定在 `PD_SAFE=0.95 V`，不得再接 `VDD_MONITORED`；
- G 为与 L0 相同语义的可信安全域关闭控制；
- 不允许换第二个 close，不允许扫 G slew，不允许扫接口参数。

## 7.3 推荐执行方式

优先级：

1. 若本地 VCS AMS / PrimeSim XA / CustomSim 能够对该真实 LATQ CDL/模型完成实际 mixed-signal 联合求解，则使用真实 mixed-signal 仿真，并在报告中明确 simulator、analog solver、model path 与版本；
2. 若当前工具链不能把 VCS 行为接口与真实 LATQ 直接联立求解，则允许用 transistor-level HSPICE/XA 等价验证：从权威 L0/source replay 中按同一 `0.5*VDD_SENSE` crossing 构造 30 路**零额外延迟、PD_SAFE 全摆幅** `safe_d_i` PWL，驱动真实 `LATQ_X0P5M_A9TR40@0.95 V`。这种方式只验证“真实安全域 latch”这一变量，报告必须标记为 equivalent causal isolation，而不能伪称完整 AMS co-sim。

PrimeSim XA 官方 tutorial/preflight 不能代替上述任一真实场景。

## 7.4 必须保存的波形/证据

至少保存：

```text
VDD_SENSE
VDD_SAFE
G
xor_0..29 或其权威 source crossing ledger
safe_d_0..29
q_0..29
```

每个 scenario 必须记录：

- input/source SHA；
- behavior/PWL generation contract；
- LATQ cell/CDL/model SHA；
- deck 或 mixed-signal testbench SHA；
- simulator/version；
- 实测 G threshold crossing；
- 每个 safe_d crossing；
- 每个 Q crossing；
- post-close Q event 分类；
- final code 与 tail stability；
- source-free re-flip taps；
- unresolved/mid-rail taps。

## 7.5 Gate

### `BFE2_L1A_REAL_SAFE_LATCH_PASS`

两个固定场景必须同时满足：

- 无 source-free post-close re-flip；
- 无 unresolved/multiple-closing oscillation；
- 最终所有 Q 可明确解析并保持稳定；
- final Q 不严重碎裂；
- normal/L2 final code 可分辨；
- Hamming distance 不低于冻结 B-FE2.2C 的 9；
- 最终每位应进入明确 safe-domain rail 区，建议检查 `Q<=0.1*VDD_SAFE` 或 `Q>=0.9*VDD_SAFE`；
- 未改变 fixed close 或正式 stimulus。

PASS 只证明真实 LATQ 在安全域供电下与理想跨域输入兼容，不证明真实 level shifter。

### `BFE2_L1A_REAL_SAFE_LATCH_FAIL`

只要任一固定场景仍存在 genuine re-flip、unresolved、长期 mid-rail、严重碎裂或丧失 normal/L2 可分辨性，即 FAIL。

FAIL 后必须：

- 停止，不得尝试新的 close；
- 不得进入 L1B；
- 发布 `BFE2_CAPTURE_CELL_REVIEW_REQUIRED`；
- 允许后续人工决定改用其他 latch、DFF/sampler 或重新定义 capture mechanism，但不得修改 sensing geometry 来隐藏捕获失败。

L1A 最多 2 个新的真实物理场景。

---

# 8. B-FE2-L1B：真实安全域 latch + 有界非理想跨域接口

只有 `BFE2_L1A_REAL_SAFE_LATCH_PASS` 才能进入。

## 8.1 目标

把 L0/L1A 的理想接口逐步替换成参数化、可审计的跨域接收/恢复模型，并得到下一阶段 integrated simulation 需要满足的接口 specification。

接口至少显式参数化：

- `VIL/VIH`，以 `VDD_SENSE` 为参考而不是直接以 `VDD_SAFE` 判源域逻辑；
- rise/fall propagation delay；
- output slew；
- 可选 hysteresis；
- uncertainty/X region；
- minimum input pulse / pulse-transfer behavior；
- source-side input loading contract（至少 `CIN_EQ` 或等价描述）。

## 8.2 执行约束

- 仍只使用 0.95 V normal/L2 fixed pair；
- close 仍固定 534.524618567 ps；
- 不做 PVT/Monte Carlo；
- 不允许一次性大网格暴力 sweep；
- 应从 L0 理想点开始，一次引入一类非理想因素，并通过边界/二分或少量代表点得到可接受区间；
- 任何 pulse filtering 都必须由接口参数明确产生，不得脚本后处理删除 XOR pulse。

## 8.3 输出

至少输出：

- 接口模型版本与 SHA；
- 每个参数的 tested range；
- PASS/FAIL boundary；
- normal/L2 code robustness；
- 真实 LATQ capture stability；
- `INTERFACE_REQUIREMENTS.json`，给出 L2 所需的 provisional specification。

Gate：

`BFE2_L1B_INTERFACE_ENVELOPE_READY`

如果不能得到非零参数余量，只能输出 `BFE2_L1B_INTERFACE_ENVELOPE_BLOCKED` 或 `...INCONCLUSIVE`，不得直接跳到集成。

---

# 9. B-FE2-L2：集成 PD_SENSE → 接口 → PD_SAFE 真实捕获

只有 `BFE2_L1B_INTERFACE_ENVELOPE_READY` 才能进入。

## 9.1 目标

第一次在同一电气实验中同时包含：

```text
真实 RVT/LVT sensing paths @ PD_SENSE
真实 XOR2_X0P5M_A9TL40 @ PD_SENSE
经过 L1B 冻结的跨域接口模型
真实 LATQ_X0P5M_A9TR40 @ PD_SAFE
可信 G/sample_close
```

L2 的关键意义是重新引入接口对 XOR 的 source-side load 与完整因果链，不能继续只 replay 历史 XOR waveform。

## 9.2 第一轮矩阵

最多两个：

```text
0.95 V normal
0.95 -> 0.86 V formal L2
```

仍固定 `sample_close=534.524618567 ps`。

只有这两个都 PASS 后，才允许最多再执行：

```text
1.10 V normal
1.10 -> 0.96 V formal L2
```

1.10 V 下 `PD_SAFE` 供电策略必须在进入该 pair 前单独记录；禁止临时改变以制造 PASS。

## 9.3 Gate

`BFE2_L2_INTEGRATED_SAFE_DOMAIN_GO` 要求：

- sensing spatial observability 未被接口负载破坏；
- interface 输入/输出符合 L1B specification；
- 真实 LATQ final Q 稳定、无 genuine re-flip/unresolved；
- normal/L2 空间码可分辨；
- 0.95 V pair 必须首先成立；
- 证据可以从 PD_SENSE 的 XOR 一直追踪到 PD_SAFE 的 final Q。

失败时必须判断是 source loading、interface contract、real latch capture 还是 sensing geometry；在证明 sensing geometry 本身失效前禁止修改 4/0/30-tap 前端。

---

# 10. B-FE2-L3：新跨域架构下的 sample-close aperture

只有 `BFE2_L2_INTEGRATED_SAFE_DOMAIN_GO` 才能进入。

此时才重新研究 `sample_close`。

目标不再是为旧 `PD_SENSE latch` 找安全点，而是回答：

> 在“PD_SENSE 感知 + 跨域恢复 + PD_SAFE 真实捕获”成立的前提下，normal/L2 共用的真实关闭安全区有多宽？

搜索规则：

- 从已经通过的 534.524618567 ps 开始；
- normal/L2 必须成对共享同一 close；
- 使用有界自适应搜索，不做固定细网格暴力扫；
- 记录通过点与失败点；
- failure mechanism 必须区分 interface、safe_d/G setup-hold、real LATQ closing、source loading；
- 只有正宽度 aperture 才能进入 B-FE3。

最终 Gate：

`BFE2_SAFE_DOMAIN_FRONTEND_GO`

该 Gate 才取代旧的 `BFE2_2_REAL_SNAPSHOT_GO/BFE2_READY_FOR_BFE3` 作为候选 B 新架构进入控制与运行时阶段的唯一授权。

---

# 11. B-FE3：可信 sample_close 生成器

只有 `BFE2_SAFE_DOMAIN_FRONTEND_GO` 才能进入。

旧 M/F 中调/细调结构可以被重新利用，但只能作为 **trusted sample_close generator** 的候选实现。

必须依据 L3 实测 aperture 重新定义：

- coarse range；
- fine step；
- jitter/skew budget；
- G edge/slew contract；
- PD_SAFE/PD_CTRL 分发边界。

不得继承旧 delayed-DFF 的 codebook 或 2075 ps 周期。

---

# 12. B-FE4：空间码启动自校准

在安全域捕获结构上完成：

- startup code acquisition；
- normal reference spatial code；
- START/END/LEN/CENTER 或等价 robust feature；
- 可编程 sample_close 选择；
- 合法 codebook；
- 参考值存于 PD_SAFE/PD_CTRL。

必须容忍并记录边界 bit 的物理不确定性，不能简单要求 30 位永远逐位完全一致。

---

# 13. B-FE5：运行时电压跌落检测

最终运行时判据基于安全域稳定空间码，验证：

- formal 0.95→0.86 V L2；
- formal 1.10→0.96 V L2；
- normal false-positive；
- 攻击相位覆盖；
- detection latency；
- repeated-probe cadence。

只有此阶段之后才允许讨论全 PVT、Monte Carlo、版图寄生、接口物理实现、面积优化和最终 macro integration。

---

# 14. 研究结论边界

在真实硬件 level shifter 尚未实现前，论文/报告中的措辞必须保持以下边界：

可以说：

> 候选 B 采用受监测域空间感知与安全域捕获解耦。由于当前 SMIC40 标准数字库未提供目标跨电压域接收单元，研究阶段使用参数化 mixed-signal 行为模型定义并验证跨域接口 specification。

不可以说：

> 已使用 SMIC40 标准单元实现并 signoff 了真实 level shifter。

B-FE2-L0/L1B 的行为模型是 architecture/specification evidence；B-FE2-L1A/L2 的真实 LATQ 与 sensing-path 电气结果负责收敛物理可信度。最终若需要流片级实现，必须设计 custom level shifter/receiver 或替换成工艺可用的真实跨域单元并重新做 transistor-level/PVT/physical signoff。

---

# 15. Codex 当前唯一允许的下一动作

从本计划提交之后，Codex 只能执行 **B-FE2-L1A**：

```text
ideal source-domain threshold/restoration
        +
REAL LATQ_X0P5M_A9TR40 @ fixed PD_SAFE=0.95 V
        +
fixed sample_close=534.524618567 ps
        +
ONLY 0.95-V normal/L2 pair
```

不得先实现 L1B，不得搜索新 close，不得进入 B-FE3，不得修改 sensing geometry。

L1A 必须形成独立 manifest、analysis、report、Gate 和单独 commit；只有 `BFE2_L1A_REAL_SAFE_LATCH_PASS` 才能继续下一阶段。
