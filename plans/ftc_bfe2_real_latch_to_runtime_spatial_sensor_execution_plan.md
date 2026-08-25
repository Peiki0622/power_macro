# FTC 候选 B：从真实锁存器到运行时空间码检测的逐阶段执行计划

> 本文件是候选 B 的唯一阶段执行计划。2026-08-25 在 B-FE2.2R 根因闭合后修订。Codex 必须按 Gate 顺序推进；没有满足当前阶段 Gate 时，不得越级实现后续阶段。

---

# 0. 当前冻结状态与本轮修订

当前工作分支：

`bfe-multitap-latched-frontend`

本计划最初起点：

`b4aaec19349344ef503e369c4300f78fa40a7be7`

B-FE2.2R 根因闭合提交：

`c5097c911c39f83f7977ddeb9b5cad8ed22938b0`

当前已经成立、后续不得重复争论的事实如下。

1. B-FE0/B-FE1/B-FE1R 已证明候选 B 的“30 个 RVT/LVT 对应抽头 + 30 个真实低阈值异或门”的空间观测机制成立。
2. B-FE2.0 已冻结真实透明锁存器 `LATQ_X0P5M_A9TR40`，其 `G` 为高电平透明、下降沿进入保持状态。
3. B-FE2.1 已真实加入 30 个 `LATQ_X0P5M_A9TR40` 的 D 输入负载，4 个必要 HSPICE 场景已经完成，Gate 为 `BFE2_1_LATCH_LOAD_GO`。30 个真实锁存器输入负载没有破坏空间可观测机制。
4. B-FE2.2 已经执行 6 个真实关闭 HSPICE 场景：首轮 4 个，加 0.95 V normal/L2 一对替代关闭点。当前正式 Gate 仍是 `BFE2_2_REAL_SNAPSHOT_CONDITIONAL`，不能直接进入 B-FE2.3。
5. B-FE2.2R 使用已有波形、0 个新 HSPICE，已得到 `BFE2_2R_ROOT_CAUSE_CONFIRMED`。
6. 0.95 V normal retry 的 tap 6 中，关闭前 XOR/D 下穿事件可以通过 B-FE2.1 透明态实测 D→Q 延迟解释第一次关闭后 Q 下穿；之后的 Q 上穿没有时间一致的 D 上穿来源，因此是真正的外部 Q 关闭后再翻转。具体内部反馈晶体管未被探测，不得声称已直接观察到内部反馈节点。
7. 根因是：旧 B-FE2.2 关闭种子直接来自 XOR `RAW_CODE` 平台，没有考虑真实透明锁存器 D→Q 传播、尚在传播中的 pre-close D 事件以及关闭 setup/hold（建立/保持）行为。
8. B-FE2.2R 已生成 `BFE2_1_TRANSPARENT_DQ_TIMING.json`、`BFE2_2R_ROOT_CAUSE.json` 和 `BFE2_2R_EVIDENCE_LEDGER.json`。这些是后续关闭种子选择的权威输入。
9. 物理仿真记账冻结为：B-FE2.1 已执行 4 个新 HSPICE；B-FE2.2 已执行 6 个新 HSPICE；B-FE2.2R 为 0 个新 HSPICE。

因此，本计划现在**不能原样从旧 B-FE2.2 跳到 B-FE2.3**。必须先插入：

```text
B-FE2.2S  安全关闭种子离线重建，0 HSPICE
    |
    v
B-FE2.2C  根因修正后的最后一对 0.95 V 确认仿真，最多 2 HSPICE
    |
    +-- 失败 --> 停止，不得继续试新的关闭点
    |
    v
BFE2_2_REAL_SNAPSHOT_GO
    |
    v
B-FE2.3   真实关闭安全窗口自适应闭合
```

B-FE2.2C 是对旧 B-FE2.2 “每个失败基线最多一个替代点”规则的一次**明确、受控、仅此一次的计划修订例外**。原因是前两个 0.95 V 关闭点都来自已经被 B-FE2.2R 证明错误的 XOR-only 种子规则。这个例外不能泛化成继续试第三、第四、第五个点。

---

# 1. 最终宏的唯一主路线

候选 B 的主结构继续冻结为：

```text
                         S_CLK
                           |
             +-------------+-------------+
             |                           |
        4级RVT前缀                    0级LVT前缀
             |                           |
        30级RVT路径                  30级LVT路径
             |                           |
      rvt_0 ... rvt_29            lvt_0 ... lvt_29
             |                           |
             +-------------+-------------+
                           |
                30 x XOR2_X0P5M_A9TL40
                           |
                   xor_0 ... xor_29
                           |
                30 x LATQ_X0P5M_A9TR40
                           |
                   q_0 ... q_29
                           |
                    稳定30位空间码
                           |
                 START / END / LEN / CENTER
                           |
             +-------------+-------------+
             |                           |
          启动自校准                  运行时检测
             |
             v
       可编程 sample_close
```

`sample_close` 的含义固定为“30 个真实透明锁存器公共 G 的关闭时刻”。它不是旧架构中的 D 型触发器时钟。

如果当前 4/0 前缀、30 抽头、当前 XOR/LATQ 单元最终在 B-FE2 无法形成正宽度真实关闭安全区，应输出阻塞或几何复审 Gate；不得未经新计划自行恢复旧的窄脉冲 DFF 路线。

---

# 2. 永久防跑偏规则

以下行为在本分支禁止，除非人工明确再次修改本计划：

- 禁止恢复 `xor_29` 单点检测主线。
- 禁止把 XOR 脉冲或延迟后的 XOR 脉冲直接作为最终 DFF 时钟。
- 禁止继续把“脉冲拉宽到满足 DFF 最小高/低脉宽”当作候选 B 主路线。
- 禁止把旧 M/F 中调/细调码表直接当成新 `sample_close` 的已验证码表。
- 禁止把旧 T0 的 2075 ps 直接宣布为候选 B 最终运行时重复探测周期。
- 禁止为了得到更漂亮数据擅自改变 4/0 前缀、30 抽头、正式 L2 波形、正式基线或 LVT XOR 身份。
- 禁止在 B-FE2 完成前做 PVT、Monte Carlo、全攻击相位、面积裁剪、运行时 FSM 或复杂告警逻辑。
- 禁止通过修改判据、威胁波形或丢弃失败场景让 Gate 变成 GO。
- 禁止再使用“XOR `RAW_CODE` 平台中点”直接产生真实锁存器 G 关闭时刻。
- 禁止把 B-FE2.2R 使用的 5 ps 因果分类容差当成设计安全余量、setup、hold、抖动余量或 B-FE3 细调精度要求。

---

# 3. 仿真复用与物理运行预算

这是硬规则。

## 3.1 先复用后运行

准备任何 HSPICE 前，必须检查已有：

- deck；
- `.tr0`；
- `.lis`；
- HSPICE 命令记录；
- 电气签名；
- SHA256；
- 阶段 JSON/报告。

如果拓扑、单元、供电波形、输入波形、G 波形/关闭时刻、模型和其他电气参数完全一致，必须复用已有结果，不允许“为了保险”重跑。

## 3.2 不得因为离线分析变化而重跑

下列变化只能复用已有 `.tr0`：

- 修报告；
- 修图；
- 修改候选排序；
- 增加派生指标；
- 修解析器；
- 补 SHA/manifest；
- 调整 root-cause 分类逻辑但不改变电路/激励。

## 3.3 当前累计预算

```text
B-FE2.1  已执行 4 个新 HSPICE
B-FE2.2  已执行 6 个新 HSPICE
B-FE2.2R 已执行 0 个新 HSPICE
B-FE2.2S 预算严格为 0
B-FE2.2C 最多再执行 2 个新 HSPICE
B-FE2.3 在通过 B-FE2.2C 后最多额外执行 16 个新 HSPICE
```

因此 B-FE2.2 最终物理场景总数不得超过 8。

---

# 4. 从当前状态开始的阶段总图

已经完成的阶段不得为了重复生成结果而重跑。

```text
B-FE2.0  DONE / BFE2_0_LATCH_CONTRACT_READY
   |
B-FE2.1  DONE / BFE2_1_LATCH_LOAD_GO / 4 HSPICE
   |
B-FE2.2  DONE但未通过 / BFE2_2_REAL_SNAPSHOT_CONDITIONAL / 6 HSPICE
   |
B-FE2.2R DONE / BFE2_2R_ROOT_CAUSE_CONFIRMED / 0 HSPICE
   |
   v
B-FE2.2S 安全关闭种子离线重建 / 0 HSPICE
   |
   +-- BLOCKED/INCONCLUSIVE --> 停止，不得运行新关闭点
   |
   v
B-FE2.2C 只运行 0.95 V normal/L2 最后一对确认 / 最多2 HSPICE
   |
   +-- FAIL --> 停止，输出复审 Gate，不得继续试点
   |
   v
BFE2_2_REAL_SNAPSHOT_GO
   |
   v
B-FE2.3 真实关闭安全窗口自适应闭合 / 最多额外16 HSPICE
   |
   v
BFE2_READY_FOR_BFE3
   |
   v
B-FE3 中调/细调重构为可编程 sample_close 生成器
   |
   v
B-FE4 空间码启动自校准
   |
   v
B-FE5 运行时电压跌落检测与覆盖闭合
   |
   v
后续 PVT / Monte Carlo / 版图寄生 / 物理集成 / 面积优化
```

每个新的子阶段必须独立提交并发布机器可读 Gate。一个提交不得跨越两个尚未解锁的阶段。

---

# 5. 已完成阶段的冻结结论

## 5.1 B-FE2.0

冻结 `LATQ_X0P5M_A9TR40`，`G` 高透明、下降关闭；XOR 和 latch 均属于 `PD_SENSE / VDD_MONITORED`。B-FE2 研究阶段的 G 仍允许理想外部源，真实控制域与分发属于 B-FE3。

Gate：

`BFE2_0_LATCH_CONTRACT_READY`

不得为本阶段新增 HSPICE。

## 5.2 B-FE2.1

真实结构：

```text
rvt_i ----+
          +-- XOR2_X0P5M_A9TL40 --> xor_i --> D LATQ_X0P5M_A9TR40 Q --> q_i
lvt_i ----+                                  G=持续高
```

四个正式场景已完成：

- 0.95 V normal；
- 0.95→0.86 V L2；
- 1.10 V normal；
- 1.10→0.96 V L2。

Gate：

`BFE2_1_LATCH_LOAD_GO`

后续必须继续复用 `BFE2_1_TRANSPARENT_DQ_TIMING.json` 中 30 路真实透明态 D→Q 交叉事件和 Q 空间码稳定区。

## 5.3 B-FE2.2 / B-FE2.2R

B-FE2.2 的 6 个真实关闭场景全部保留为不可变历史证据。first attempt 与 retry 不能互相覆盖。

当前 Gate：

`BFE2_2_REAL_SNAPSHOT_CONDITIONAL`

B-FE2.2R Gate：

`BFE2_2R_ROOT_CAUSE_CONFIRMED`

B-FE2.2R 的根因结论只证明旧关闭种子规则错误，不等价于真实快照已经 GO。

---

# 6. B-FE2.2S：安全关闭种子离线重建

这是 Codex 从当前提交之后**必须立即执行的下一阶段**。

本阶段严格 0 HSPICE。

## 6.1 唯一目标

从已有 B-FE2.1/B-FE2.2/B-FE2.2R 波形中，程序化建立“真实透明锁存器可以安全关闭”的 normal/L2 公共候选区，并只在存在物理上合理的正宽度区间时选出一个 0.95 V 研究关闭种子。

本阶段不是再次给 XOR 平台排序。

## 6.2 权威输入

至少读取并校验：

```text
latch_load/BFE2_1_SCENARIO_MANIFEST.json
latch_load/BFE2_1_TRANSPARENT_DQ_TIMING.json
latch_load/BFE2_1_GATE_STATUS.json
real_snapshot/BFE2_2_SCENARIO_MANIFEST.json
real_snapshot/BFE2_2_RETRY_MANIFEST.json
real_snapshot/BFE2_2_GATE_STATUS.json
real_snapshot/root_cause/BFE2_2R_ROOT_CAUSE.json
real_snapshot/root_cause/BFE2_2R_EVIDENCE_LEDGER.json
BFE2_0_LATCH_CELL_AUDIT.json
```

必须验证 SHA/场景身份/电压条件一致，不得手抄时间常数替代权威工件。

## 6.3 正确的安全关闭候选定义

对每个基线分别处理 normal 和 L2，然后取两者交集。

候选时刻 `t_close` 必须同时满足：

1. normal/L2 使用同一个 `t_close`。
2. `t_close` 位于两边都干净、非空、非碎裂、非贴 tap 边界、无未定义位的 **Q 空间码稳定区**，而不是只看 XOR 空间码。
3. 对所有在 `t_close` 前已经发生、并会改变所观察 Q 码的 D/XOR 事件，必须利用对应 B-FE2.1 透明态实测 D→Q 延迟证明其 Q 响应已经在 `t_close` 前完成。若存在 `D < t_close` 但预测 `Q > t_close` 的 in-flight 事件，该时刻直接禁止。
4. 对 `t_close` 附近的下一次 D 事件，必须检查 hold（保持）风险；不得只因为 Q 当前不跳变就认为安全。
5. 必须考虑锁存器 G 下降沿实际阈值交叉相对 requested close 的偏差；后续候选应使用“实际 G 关闭”的语义，而不是假定 PWL 命令时刻就是内部有效关闭时刻。
6. 必须应用可获得的 Liberty setup/hold 约束；若库中没有与该研究电压完全匹配且可直接使用的约束，禁止编造数值。
7. 若缺少可直接适用的 Liberty 数值，允许本阶段形成一个**研究用经验关闭候选**，但必须显式标为 provisional（暂定），并用已有 transistor-level（晶体管级）D→Q、Q 稳定区、G 实测交叉、历史失败事件构造等效风险边界。这个等效边界只用于授权 B-FE2.2C 的一次确认仿真，不得宣称为 signoff setup/hold。
8. B-FE2.2R 的 5 ps `classification_tolerance_ps` 仅用于判断一个 Q 事件是否与历史 D 事件时间一致，禁止直接作为第 6/7 条中的安全余量。

可把核心禁止条件表达为：

```text
存在某个 pre-close D 事件 d：
    d.time < t_close
且 d.time + measured_DQ_delay > t_close
=> t_close 禁止
```

但实现时必须逐 tap、逐方向使用真实测得的 D→Q 数据，不能只用一个全局平均值。

## 6.4 normal/L2 公共安全区

对 0.95 V 与 1.10 V 分别生成：

- normal Q 稳定区；
- L2 Q 稳定区；
- 去除 in-flight D 风险后的区间；
- setup/hold 或 provisional 等效风险收缩后的区间；
- normal/L2 最终公共候选区；
- 每个公共候选区中的 normal/L2 最终空间码、汉明距离、START/END/LEN/CENTER；
- 左右最近失败机制与 tap；
- 到最近 Q crossing、D crossing、预测 Q arrival、G 关闭风险边界的距离。

如果候选区只有数学单点或宽度在数值误差量级内，不得视为 READY。

## 6.5 种子排序

只有已经满足 6.3/6.4 的候选区才允许排序。

优先级依次为：

1. 最小物理时间余量最大；
2. normal/L2 两边都远离风险边界；
3. 位于观察空间中部；
4. 空间码无碎裂、无未定义位；
5. normal/L2 可分辨性清楚；
6. 不靠近 tap 0/29。

禁止先按汉明距离或平台宽度挑点，再事后检查真实锁存器时序。

最终只能选择 **一个 0.95 V normal/L2 共用的 corrected seed（根因修正关闭种子）** 供 B-FE2.2C 使用。

1.10 V 已有通过的 B-FE2.2 正式 pair，不得因为本阶段重新排序而重跑。可以离线检查它是否也符合新规则；若不符合，应把 B-FE2.2S Gate 降为 INCONCLUSIVE 并停止，而不是偷偷挑新 1.10 V 点运行。

## 6.6 输出

建议新增：

```text
real_snapshot/safe_seed/
  BFE2_2S_SAFE_INTERVALS.json
  BFE2_2S_SELECTED_SEED.json
  BFE2_2S_GATE_STATUS.json
  BFE2_2S_REPORT.md
```

至少保存：

- 所有输入 SHA；
- 所有候选区及被剔除原因；
- 选中候选点的 normal/L2 同时满足条件的证据；
- margin 来源是 Liberty 还是 provisional transistor-level equivalent；
- 1.10 V 历史通过 pair 对新规则的离线一致性检查；
- `new_hspice_scenarios = 0`。

## 6.7 Gate

### `BFE2_2S_SAFE_SEED_READY`

必须满足：

- 0.95 V normal/L2 存在正宽度公共安全区；
- 能选出唯一 corrected seed；
- 所有相关 pre-close D 事件均不存在未完成 D→Q 传播；
- setup/hold 或明确标注的 provisional 等效风险处理已完成；
- 1.10 V 历史通过 pair 与新规则不存在明显冲突；
- 0 个新 HSPICE。

### `BFE2_2S_SAFE_SEED_INCONCLUSIVE`

存在 Q 稳定交集，但无法用已有证据排除 in-flight/setup/hold 风险，或 1.10 V 历史通过点与新规则冲突。

### `BFE2_2S_SAFE_SEED_BLOCKED`

0.95 V normal/L2 在真实 Q 稳定与 D→Q 完成条件下没有任何正宽度公共候选区。

只有 READY 才允许进入 B-FE2.2C。

---

# 7. B-FE2.2C：根因修正后的最后一对确认仿真

只有 `BFE2_2S_SAFE_SEED_READY` 才能进入。

这是对 B-FE2.2 的**最后一次、仅一对、根因修正后的计划授权确认**。

## 7.1 唯一目标

用 B-FE2.2S 选出的 corrected seed，验证 0.95 V normal 和正式 0.95→0.86 V L2 在同一真实 G 关闭时刻下，都能冻结稳定、可解析、可分辨的 30 位 Q 空间码。

## 7.2 仿真矩阵

最多只允许两个新场景：

```text
0.95 V normal @ corrected seed
0.95 -> 0.86 V formal L2 @ 同一个 corrected seed
```

不允许：

- 重跑 1.10 V；
- 再试第二个 corrected seed；
- 在失败后自动扫参；
- 更改前缀、tap、XOR、LATQ；
- 做 PVT/Monte Carlo；
- 提前做 B-FE2.3。

运行前必须先建立电气签名并确认仓库中不存在完全相同的历史场景；若已存在则直接复用。

## 7.3 必须检查

对两个场景都检查：

- 实测 G 关闭阈值交叉；
- `xor_0..29` / `q_0..29`；
- 所有关闭后 Q crossing；
- 关闭后是否存在 genuine re-flip；
- 是否存在未完成的 in-flight D 事件；
- Q 最终空间码是否非空、无严重碎裂、无未定义位；
- normal/L2 是否可分辨；
- START/END/LEN/CENTER、汉明距离；
- 最慢 Q 解析时间；
- 离最近失败 tap/时间边界的余量。

B-FE2.2R 的因果分类逻辑可以复用，但必须区分：

- 正常的 pre-close in-flight 解析；
- 真正关闭后 source-free re-flip。

corrected seed 的设计目标应使前者在有效 G 关闭前已经完成；若仍出现，应视为种子规则没有真正修正。

## 7.4 成功条件

只有两个场景同时满足：

- 30 个 Q 最终均明确解析；
- 没有真正关闭后再翻转；
- 没有影响目标空间码的未完成 pre-close D→Q 传播；
- normal/L2 均得到稳定空间码；
- normal/L2 空间码可区分；
- 证据完整；

才能把 B-FE2.2 正式 Gate 更新为：

`BFE2_2_REAL_SNAPSHOT_GO`

同时明确保留旧 6 场景及 root-cause 证据，不允许覆盖历史失败。

## 7.5 失败条件

如果 corrected seed 的任一场景仍存在 genuine post-close re-flip、未解析 Q、严重碎裂或 normal/L2 不可分辨：

- 不得继续尝试新的关闭点；
- 不得进入 B-FE2.3；
- 保持 `BFE2_2_REAL_SNAPSHOT_CONDITIONAL` 或输出更明确的 `BFE2_2_CORRECTED_SEED_FAILED`；
- 输出“锁存器关闭机制/前端几何复审”证据，等待新计划决定是否调整 latch、驱动、前缀或抽头几何。

本阶段最多新增 2 个 HSPICE，使 B-FE2.2 累计场景总数最多达到 8。

---

# 8. B-FE2.3：真实关闭安全窗口自适应闭合

只有新的 `BFE2_2_REAL_SNAPSHOT_GO` 才能进入。

## 8.1 唯一目标

回答：

> 对 0.95 V 和 1.10 V 两个正式基线，分别存在多宽的真实公共关闭安全区，使 normal 与 L2 在同一关闭时刻下都能稳定得到可分辨空间码？

该阶段的结果才允许设计 B-FE3 的中调/细调范围、步进和关闭分发。

## 8.2 搜索边界必须使用修正后的物理语义

禁止回到旧规则“用 XOR crossing 决定左右边界”。

B-FE2.3 的搜索先验必须来自：

- B-FE2.2S 的 Q 空间码安全候选区；
- 真实透明态 D→Q 延迟；
- pre-close in-flight 约束；
- setup/hold 或 provisional 等效风险边界；
- B-FE2.2/B-FE2.2C 已有通过/失败点。

XOR crossing 仍可作为辅助因果信息，但不能单独定义真实 latch 关闭孔径。

## 8.3 禁止固定细网格暴力扫描

不得从大范围按 1 ps/2 ps/5 ps 固定步长扫。

必须采用有界自适应搜索：

1. 从已经通过的 B-FE2.2/B-FE2.2C 关闭点开始；
2. 使用 B-FE2.2S 给出的安全候选区作为先验范围；
3. 先向左右各测试少量较远候选；
4. 只在“通过点与失败点”之间局部二分/有界细化；
5. 每个时刻 normal/L2 必须成对使用同一关闭时间；
6. 完全相同电气签名必须复用；
7. 必须保留通过点和失败点。

## 8.4 仿真预算

B-FE2.3 在已有全部 B-FE2.2 场景之外，最多额外执行 16 个 electrically unique HSPICE 场景。

预算内无法形成清楚左右边界时，输出：

`BFE2_3_APERTURE_CONDITIONAL`

不得自动增加预算。

## 8.5 安全点判据

一个真实关闭点只有同时满足以下条件才算通过：

- normal/L2 两边波形有效；
- 30 个 Q 均可解析；
- 没有 genuine post-close re-flip；
- 没有影响目标码的未完成 pre-close in-flight D→Q；
- 两边空间码非空、无严重碎裂、无未定义位；
- normal/L2 保持明确差异；
- 不依赖数学单点；
- 没有明显亚稳态或极慢解析；
- 关闭时刻与风险边界具有正余量。

## 8.6 输出与最终 Gate

建议：

```text
close_aperture/
  BFE2_3_SEARCH_POINTS.json
  BFE2_3_SAFE_APERTURES.json
  BFE2_3_GATE_STATUS.json
BFE2_GATE_STATUS.json
BFE2_REAL_LATCH_REPORT.md
```

最终报告至少给出：

- 0.95 V 真实关闭安全区；
- 1.10 V 真实关闭安全区；
- 左右失败边界及失败机制；
- 首个失败 tap；
- 最慢 Q 解析时间；
- 最小真实时间余量；
- 后续可编程关闭生成器所需粗略范围/分辨率，但不得提前实现 B-FE3。

### `BFE2_READY_FOR_BFE3`

仅当两个正式基线均存在正宽度真实关闭安全区，且真实 Q 空间码稳定、可解析、可区分时输出。

### `BFE2_FRONTEND_GEOMETRY_REVIEW`

机制工作但安全区过窄、贴边或对实现分辨率明显不现实。此时不得进入 B-FE3，先由新计划决定是否调整前缀、tap、驱动或单元。

### `BFE2_REAL_LATCH_BLOCKED`

真实锁存器机制无法为两个正式基线形成可用安全关闭区。

---

# 9. B-FE3：中调/细调重构为可编程 sample_close 生成器

只有 `BFE2_READY_FOR_BFE3` 才能创建和执行 B-FE3 详细子计划。

核心语义固定为：

```text
S_CLK / 稳定控制参考
        |
        v
路径选择中调
        |
        v
标准单元电容细调
        |
        v
sample_close_pre
        |
        v
真实驱动/分发
        |
        v
30个透明锁存器公共 G 关闭
```

禁止再恢复：

```text
XOR事件 -> M/F -> 窄DFF时钟
```

B-FE3 必须回答：

- 可编程关闭范围是否覆盖 B-FE2 两个安全区；
- 实际步进是否足够；
- 码到关闭时间是否单调；
- 30 个 G 总负载所需真实驱动；
- G 分发偏斜是否侵蚀 B-FE2 安全区；
- 关闭控制是否来自 `PD_CTRL` 或其他不会被 `VDD_MONITORED` 跌落显著污染的稳定控制域。

旧 M/F 数据只能用于结构参考和粗略范围经验，不能直接作为新码表。

---

# 10. B-FE4：空间码启动自校准

只有 B-FE3 证明真实可编程关闭生成器能覆盖 B-FE2 安全区后进入。

校准目标从旧单 bit Q 边界搜索改为：

- 找到可实现的关闭控制码；
- 得到当前芯片正常供电下稳定 30 位参考空间码；
- 得到参考 START/END/LEN/CENTER；
- 建立运行时允许变化包络。

建议输出：

```text
selected_close_code
reference_raw_code
reference_start
reference_end
reference_len
reference_center
allowed_runtime_envelope
calibration_valid
```

禁止为每个 M/F 代码重跑晶体管级 HSPICE；优先使用 B-FE3 的码到时间模型，仅对最终候选和少量边界做晶体管级锚点。

---

# 11. B-FE5：运行时电压跌落检测与覆盖闭合

只有 B-FE4 启动自校准稳定后进入。

运行时检测使用启动时获得的参考空间码/特征，研究：

- START 位移；
- END 位移；
- CENTER 位移；
- LEN 变化；
- 汉明距离；
- 异常碎裂。

不得提前假设某一个特征必然单独判决。

只有在 B-FE5 才允许：

- 扩展 L1/L2/L3；
- 做完整攻击相位覆盖；
- 重新推导候选 B 最大重复探测间隔；
- 研究恢复/重臂；
- 加 sticky alarm、heartbeat、timeout 等系统逻辑。

旧 T0 的 2075 ps 只是历史目标，不是新前端已证明的最终周期。

旧 T0 冻结的正式电压跌落波形继续作为威胁输入权威；不得重新发明同样的威胁定义。

---

# 12. 后续物理签核

只有 B-FE5 功能闭合后才系统扩展：

- PVT；
- Monte Carlo；
- 版图寄生；
- `sample_close` 分发偏斜；
- 电源完整性；
- 真实跨电源域单元；
- 面积/功耗优化；
- 抽头裁剪；
- SoC/Chiplet 集成。

不要在基本物理机制尚未通过时消耗大量 PVT/统计仿真预算。

---

# 13. 每阶段证据纪律

每个阶段至少保存：

- 输入权威工件 SHA256；
- 新脚本 SHA256；
- 新 deck SHA256；
- 新 `.tr0` SHA256；
- HSPICE 版本；
- 电气签名；
- `run_disposition = new/reused`；
- 失败场景；
- Gate 的程序化推导原因；
- 本阶段实际新增 HSPICE 数；
- 历史累计 HSPICE 数；
- 本阶段明确未做的工作。

原始大 `.tr0` 留在任务专属 `runs/` 目录，不复制进 Git 分析目录。Git 中保存紧凑证据与派生结果。

任何报告数字必须可追溯到机器 JSON 或原始波形。

---

# 14. 推荐目录

```text
delay_chain/ftc/runs/b_fe_frontend/bfe2_real_latch/
  latch_load/
  real_snapshot/
  close_aperture/

delay_chain/ftc/analysis/b_fe_frontend/bfe2_real_latch/
  BFE2_0_CONTRACT.json
  BFE2_0_LATCH_CELL_AUDIT.json
  BFE2_0_EVIDENCE_BASELINE.json
  latch_load/
  real_snapshot/
    root_cause/
    safe_seed/
    corrected_confirmation/
  close_aperture/
  BFE2_GATE_STATUS.json
  BFE2_REAL_LATCH_REPORT.md
```

新增脚本应按职责拆分，例如：

```text
analyze_bfe2_2s_safe_seed.py
run_bfe2_2c_corrected_pair.py
analyze_bfe2_2c_corrected_pair.py
analyze_bfe2_close_aperture.py
```

不要把 runner、分析、Gate、B-FE3 实现写成一个巨型脚本。

---

# 15. Codex 从当前提交之后的严格执行顺序

Codex 只允许按下面顺序继续：

```text
下一提交：B-FE2.2S
  - 读取 B-FE2.1/B-FE2.2/B-FE2.2R 已有证据
  - 逐 tap 使用真实透明态 D→Q
  - 建 Q 稳定区
  - 排除 in-flight D 风险
  - 处理 setup/hold 或明确的 provisional 等效风险边界
  - 检查 1.10 V 历史通过 pair 与新规则一致性
  - 选择唯一 0.95 V corrected seed
  - 0 HSPICE
  - 输出 READY / INCONCLUSIVE / BLOCKED

若且仅若 BFE2_2S_SAFE_SEED_READY：

下一提交：B-FE2.2C-run
  - 只运行 0.95 V normal/L2 同一 corrected seed
  - 最多 2 个新 HSPICE
  - 不重跑 1.10 V
  - 不尝试第二个 corrected seed
  - 保存 deck/tr0/SHA/电气签名/实测 G close

下一提交：B-FE2.2C-analysis
  - 0 HSPICE
  - 分析 Q 稳定、in-flight、genuine re-flip、空间可分辨性
  - 成功则更新正式 Gate 为 BFE2_2_REAL_SNAPSHOT_GO
  - 失败则停止，不得进入 B-FE2.3

若且仅若 BFE2_2_REAL_SNAPSHOT_GO：

下一阶段：B-FE2.3
  - 从通过点开始
  - 使用 Q/D→Q/setup-hold 修正后的安全先验
  - 自适应寻找左右失败边界
  - 额外最多 16 个新 HSPICE
  - 输出 BFE2_READY_FOR_BFE3 / GEOMETRY_REVIEW / BLOCKED

若且仅若 BFE2_READY_FOR_BFE3：

才允许创建 B-FE3 详细计划和实现提交。
```

在 `BFE2_READY_FOR_BFE3` 出现之前，**禁止 Codex 实现 B-FE3、B-FE4、B-FE5**。

---

# 16. 当前最重要的防跑偏判定

如果 Codex 出现下列倾向，立即停止对应动作：

1. “B-FE2.2R 根因确认了，所以直接进入 B-FE2.3” —— 错。B-FE2.2 正式 Gate 仍是 CONDITIONAL；先 B-FE2.2S，再 B-FE2.2C。
2. “Q stable interval 有交集，所以直接取中点跑” —— 错。还必须排除 pre-close in-flight D→Q，并处理 setup/hold/等效风险。
3. “5 ps root-cause tolerance 就当安全 margin” —— 错。它只是事件分类容差。
4. “0.95 V 已经试过替代点，再随便试一个点也一样” —— 错。B-FE2.2C 仅授权由 B-FE2.2S 新规则程序化选出的唯一 corrected seed，且只允许一对。
5. “corrected seed 失败，再选第二名” —— 错。失败即停止，进入复审，不得继续试点。
6. “1.10 V 已经通过，但为了统一新算法顺手重跑” —— 错。先离线一致性审计；除非未来新计划明确证明原 1.10 V 证据失效，否则不得重跑。
7. “B-FE1R 平台十几 ps，所以现在先做超细 M/F” —— 错。必须先闭合真实 latch 安全区。
8. “旧 `ftc_sensor.sv` 有 latch+DFF，可以直接作为最终结构” —— 错。候选 B 的真实快照核心是透明锁存器，旧 DFF 语义不自动继承。
9. “旧 2075 ps 已证明，所以直接做运行时 FSM” —— 错。B-FE5 才重新闭合新前端运行时覆盖。
10. “B-FE2 成功后立刻 PVT/Monte Carlo” —— 错。先 B-FE3/B-FE4/B-FE5。

---

# 17. 计划成功标准

本计划的物理因果链必须始终保持：

```text
空间观测存在
   -> 真实锁存器 D 负载下仍存在
   -> 理解真实 D→Q 与关闭时序
   -> 用正确规则找到安全关闭种子
   -> 真实关闭确认通过
   -> 找到正宽度真实关闭安全区
   -> 可编程控制命中安全区
   -> 启动自校准得到正常参考
   -> 运行时空间偏移检测正式电压跌落
   -> 最后做全相位/PVT/统计/物理集成
```

任何阶段失败，都必须停在该层保留证据并分析根因。不要用后级数字逻辑掩盖前级物理问题，也不要用更多仿真代替对失败原因的理解。
