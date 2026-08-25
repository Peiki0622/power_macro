# FTC B-FE 多抽头锁存式前端：B-FE0/B-FE1 架构合同与最小晶体管级验证计划

## 0. 计划定位

本计划只在分支 `bfe-multitap-latched-frontend` 上推进，基线为 `main` 提交 `725855dc71ce16362a2b84bd7f4d45fe7389d7cb`。该基线已经证明：共享 RVT/LVT 传感路径本身没有被 2075 ps 重复探测周期物理阻塞，当前 D0-BR2 的阻塞点来自“把窄参考事件合法化为标准 DFF 时钟”的路线，而不是双延迟线本身。

本分支正式把主研究问题前移到传感器前端：不再先问“如何把 `dff_ck` 拉宽”，而是先问“现有 30 级 RVT/LVT 可观察路径在多抽头真实 XOR 加载后，能否形成稳定、可校准、并随正式电压跌落发生可分辨移动的空间码”。

B-FE0/B-FE1 只闭合这一问题。真实锁存器阵列、M/F 采样控制、自校准状态机、运行时告警均属于后续阶段，禁止提前实现。

---

## 1. 新主路线的前端定义

目标前端为：

```text
                              S_CLK
                                |
                 +--------------+--------------+
                 |                             |
                 v                             v
          legacy RVT path               legacy LVT path
          prefix = 4 stages              prefix = 0 stages
                 |                             |
          30 observable taps              30 observable taps
                 |                             |
        rvt_0 ... rvt_29                lvt_0 ... lvt_29
                 |                             |
                 +--------------+--------------+
                                |
                                v
                 30 x real XOR2 observations
                                |
                 xor_0 ... xor_29
                                |
                                v
                   transient spatial vector
                   0000011111110000...
                                |
                    B-FE1: ideal offline snapshot
                                |
                                v
                   RAW_CODE / START / END
                    LEN / CENTER / bubbles
```

最终候选架构会在每个 `xor_i` 后加入真实锁存器并用可编程采样关闭信号冻结空间快照，但 **B-FE1 暂时不实例化真实 latch**。B-FE1 只用真实晶体管级 XOR 波形离线重建“若在某一采样时刻关闭锁存器，其理想输出会是什么”，从而把“空间码机制是否成立”和“具体 latch 能否可靠冻结空间码”严格拆开。

---

# 2. B-FE0：架构合同冻结（0 HSPICE）

## B-FE0.1 必须继承的物理基线

以下内容直接继承 legacy sensor，不得为了得到更漂亮的空间码而修改：

- RVT/LVT 双路径传感原则；
- RVT 初始前缀 4 级；
- LVT 初始前缀 0 级；
- 可观察级数 30，索引 `0..29`；
- 每一级原有 RVT/LVT 标准单元身份、连接顺序和供电域；
- `PD_SENSE / VDD_MONITORED` 供电语义；
- `S_CLK` 作为传感波前输入；
- 当前单点 XOR 使用的真实 `XOR2_X0P5M_A9TL40` 作为 B-FE1 第一版 30 路 XOR 的统一单元；
- 正式主基线 0.95 V、1.10 V；
- 正式 L2 电压目标 0.95→0.86 V、1.10→0.96 V；
- 正式 3002 ps 电压跌落波形定义继续从现有 T0 权威工件读取，不重新发明波形。

B-FE0 不重新证明这些历史结论，只冻结其 SHA/路径并建立新研究分支的输入合同。

## B-FE0.2 明确解除的旧架构约束

下列旧假设不再约束新前端：

- `xor_29` 必须是唯一传感输出；
- `xor_29` 必须直接作为最终 DFF 数据输入；
- M/F 输出必须作为标准 DFF 时钟；
- `dff_ck` 必须满足 1 ns 高脉宽和 1 ns 低脉宽；
- `DFFRPQ_X0P5M_A9TR40` 必须是最终时间比较原语；
- capture bank、pulse legalizer、per-probe reset/recovery 是当前新前端必须解决的问题。

旧结构不得删除或覆盖。legacy DFF/M0/T0/D0-BR2 证据作为历史对照继续保留，但不能自动转移为新前端的 sign-off 证据。

## B-FE0.3 新结构的唯一新增电气负载

B-FE1 的新物理前端只允许新增：

```text
rvt_i ----+
          +-- XOR2_X0P5M_A9TL40 --> xor_i
lvt_i ----+
```

对 `i = 0..29` 共 30 路。

这 30 个 XOR 的输入电容必须真实加载到每一级 RVT/LVT tap 上。禁止用理想 XOR、Verilog 行为异或或无输入电容探针代替。B-FE1 的第一风险就是检查这种规则的多抽头加载是否破坏差分传播。

B-FE1 暂时禁止把 latch 输入电容也叠加进来；真实 latch 负载留到 B-FE2。

## B-FE0.4 理想快照定义

对任意采样时刻 `Tsample`，定义：

```text
bit[i](Tsample) = 1, if V(xor_i,Tsample) > 0.5 * V(VDD_MONITORED,Tsample)
                  0, otherwise
```

阈值必须跟随瞬时本地供电，不使用固定绝对电压门限。

得到：

```text
RAW_CODE(Tsample) = bit[29:0]
```

随后只做离线描述性提取：

- `START`：最长连续 1 串的起点；
- `END`：最长连续 1 串的终点；
- `LEN = END - START + 1`；
- `CENTER = (START + END)/2`；
- `RUN_COUNT`：1 串数量；
- `BUBBLE_COUNT`：主 1 串内部的 0 气泡数量；
- `LEFT_HEADROOM = START`；
- `RIGHT_HEADROOM = 29 - END`。

必须保存原始 `RAW_CODE`。B-FE1 不实现 bubble-proof encoder，也不得只保存“修正后码”。

## B-FE0.5 输出工件

Codex 应建立：

```text
delay_chain/ftc/analysis/b_fe_frontend/
  bfe0_architecture_contract.json
  bfe0_legacy_baseline_sha256.json
  bfe0_observable_definition.json
```

至少记录：

```text
stage = B-FE0
observable_taps = 30
rvt_prefix = 4
lvt_prefix = 0
xor_count = 30
xor_cell = XOR2_X0P5M_A9TL40
snapshot_model = ideal_offline_threshold_snapshot
real_latch_instantiated = false
real_mf_sample_generator = false
legacy_sensor_modified = false
new_hspice_scenarios = 0
```

B-FE0 Gate 只有：

```text
BFE0_FRONTEND_CONTRACT_READY
```

只有 baseline SHA、legacy 不变性、30 路 tap 定义、禁止项和 HSPICE 预算全部满足才进入 B-FE1。

---

# 3. B-FE1：多抽头空间可观测性最小晶体管级验证

## B-FE1.1 唯一目标

只回答三个问题：

1. 多抽头真实 XOR 加载后，是否仍形成可解析的空间 1 带；
2. 同一 `Tsample` 下，正常电压和两个正式 L2 跌落目标是否产生可分辨空间码；
3. 这种可分辨性是否存在于一个正宽度的采样时间区间，而不是只存在于单个瞬态交叉点。

B-FE1 不验证最终 latch、不验证 M/F、不验证 2075 ps 重复运行、不验证完整 T0 phase coverage。

## B-FE1.2 新建独立研究拓扑，不修改 legacy sensor

新 deck/subckt 必须独立命名，例如：

```text
FTC_SENSOR_BFE1_MULTITAP
```

要求：

- 完整复用 legacy RVT/LVT 路径；
- 不实例化 legacy 的 `xor_29 -> M/F -> DFF` 比较链作为新结论路径；
- 30 个 tap 每一级各实例化一个真实 XOR；
- 保存 `rvt_0..29`、`lvt_0..29`、`xor_0..29`、`S_CLK`、`VDD_MONITORED` 波形；
- legacy sensor 文件本身保持 byte-identical，测试必须检查这一点。

若为了 deck 复用必须保留旧 DFF/M/F 作为旁路负载，必须明确标记为“非判决路径”并证明它不会改变 30 路观测定义；优先使用干净的独立 B-FE1 子电路，避免带入旧 DFF 语义。

## B-FE1.3 S_CLK 激励

只允许一次上升波：

```text
S_CLK  ____/-------------------------
             ^
          one rise
```

上升后保持高直到仿真结束。B-FE1 禁止加入 S_CLK falling edge，避免下降波 EF 混入第一轮空间码机制验证。

输入边沿继续使用现有正式传感仿真的物理边沿定义，不另造慢边沿。

## B-FE1.4 最小 HSPICE 场景矩阵

最多 4 个 electrically unique 新场景：

| 场景 | 基线 | 电压条件 | 目的 |
|---|---:|---:|---|
| BFE1-095-N | 0.95 V | 无跌落 | 正常空间码族 |
| BFE1-095-L2 | 0.95 V | 0.86 V 正式 L2/3002 ps | 跌落空间码族 |
| BFE1-110-N | 1.10 V | 无跌落 | 正常空间码族 |
| BFE1-110-L2 | 1.10 V | 0.96 V 正式 L2/3002 ps | 跌落空间码族 |

正式 L2 waveform 和代表性相位优先从现有 T0/D0-A 正式目标工件程序化读取；若引用 0.95 V L2 的 +75 ps 或 1.10 V L2 的 +25 ps 历史诊断点，必须先由权威 JSON 校验，不得散落硬编码。

B-FE1 的这两个 transient L2 点只是“代表性空间响应”而不是 phase coverage。

严格禁止在本阶段扩展到：L1、L3、0.80 V、PVT、Monte Carlo、全 phase、重复 probe。

## B-FE1.5 一次 transient 获取全部 Tsample，不做采样时刻 HSPICE sweep

每个电气场景只运行一次 transient。禁止按 `Tsample` 重复跑 HSPICE。

离线分析应直接从 30 路 XOR 波形构造所有阈值交叉事件：

```text
V(xor_i,t) - 0.5*VDD_MONITORED(t) = 0
```

将所有 tap 的真实交叉时间排序后，形成 piecewise-constant 的空间码时间区间。对相邻交叉事件之间的区间取中点，即可无额外 HSPICE 地得到该区间唯一的 `RAW_CODE`。

这样平台宽度由真实 crossing boundary 给出，而不是由任意 5 ps/25 ps 网格人为决定。

对 normal/droop 成对比较时，以二者所有 crossing boundary 的并集建立共同的 launch-relative 时间分段，并在同一个 `Tsample` 上比较两边代码。

## B-FE1.6 每个场景必须输出的轨迹

对每个常值区间输出：

```text
interval_start_ps
interval_end_ps
interval_width_ps
raw_code
start
end
len
center
run_count
bubble_count
left_headroom
right_headroom
```

还应输出：

- 所有 `xor_i` 首次 rise/fall crossing；
- 30 tap 的波前单调性诊断；
- 空间码是否为空；
- 最长 1 串是否贴左右边界；
- 是否存在等长的多个最大 1 串；
- 是否存在严重非单调/碎裂区域。

## B-FE1.7 正常与 L2 的成对判别指标

在同一 `Tsample` 区间内计算：

```text
delta_start  = START_L2  - START_N
delta_end    = END_L2    - END_N
delta_len    = LEN_L2    - LEN_N
delta_center = CENTER_L2 - CENTER_N
hamming_distance = popcount(RAW_CODE_L2 xor RAW_CODE_N)
```

B-FE1 不预先规定变化方向，也不预先要求必须由 `LEN`、`CENTER` 或某一个指标承担最终检测。先发布完整数据，再让后续阶段选择最稳定的检测码元。

## B-FE1.8 “共同判别平台”的定义

一个候选共同判别平台必须同时满足：

- normal 与 L2 在同一个 launch-relative `Tsample` 区间内各自 `RAW_CODE` 恒定；
- 两边主 1 串均非空；
- 两边主 1 串都不贴左右观察边界；
- `RAW_CODE_N != RAW_CODE_L2`；
- `START/END/LEN/CENTER` 至少有一个描述量不同；
- 区间宽度严格大于 0；
- 区分不依赖一个恰好发生 crossing 的单点；
- 该区间内不发生未定义/中间电平 bit 分类。

必须记录所有候选平台，并发布最大平台及其时间范围；不能只挑一个最漂亮的点。

## B-FE1.9 Gate

### `BFE1_SPATIAL_OBSERVABILITY_GO`

两个正式 baseline 对应的 normal/L2 成对场景都存在至少一个正宽度共同判别平台，且空间码在该平台内可解析、非空、不贴边，没有证据表明 30 路 XOR 加载已经破坏 RVT/LVT 差分传播。

这只表示“候选 B 的空间观测机制值得进入真实 latch 阶段”，不代表最终前端已完成。

### `BFE1_SPATIAL_OBSERVABILITY_CONDITIONAL`

空间码存在并且 normal/L2 可区分，但至少存在以下一种问题：

- 所有可区分平台都贴观察边界；
- 严重气泡/多段 1 串使最长串语义不稳定；
- 共同平台虽然正宽但非常局部，后续 latch/MF 裕量明显可疑；
- 两个 baseline 中只有一个具有干净的共同判别平台；
- 30 tap 观察窗口明显没有居中覆盖有效波前。

此结果不得直接进入 B-FE2。先建立一个独立的“前缀/观察窗口几何调整计划”，并继续禁止修改控制器。

### `BFE1_SPATIAL_OBSERVABILITY_BLOCKED`

满足任一情况即可：

- 两个正式 baseline 中有一个在合理波前时间区间内始终不存在可解析空间 1 带；
- normal/L2 在所有共同稳定区间内空间码始终相同；
- 区别只出现在 crossing 单点而不存在任何正宽平台；
- 多 tap XOR 加载导致差分传播基本消失或发生不可解析的严重波形破坏。

BLOCKED 只阻塞当前“4/0 前缀 + 30 tap + 当前 cell identity”的候选，不允许据此直接恢复 DFF pulse-legalizer 主线；应先决定是否值得重开前端几何。

---

# 4. B-FE1 输出工件与图

建议目录：

```text
delay_chain/ftc/analysis/b_fe_frontend/bfe1_spatial_observability/
  scenario_manifest.json
  waveform_crossings.json
  spatial_code_intervals.json
  normal_l2_pairwise_discrimination.json
  BFE1_GATE_STATUS.json
  BFE1_SPATIAL_OBSERVABILITY_REPORT.md
  figures/
```

至少形成以下论文级图：

1. 0.95 V normal 的 `Tsample × tap` 空间码图；
2. 0.95→0.86 V L2 的对应空间码图；
3. 1.10 V normal 的空间码图；
4. 1.10→0.96 V L2 的对应空间码图；
5. `START/END/LEN/CENTER` 随 launch-relative `Tsample` 的轨迹；
6. normal/L2 共同判别平台示意图。

图必须由保存的机器可读 JSON 自动生成，不手工整理结果。

---

# 5. 运行与证据纪律

- B-FE0：0 个新 HSPICE；
- B-FE1：最多 4 个新 electrically unique HSPICE；
- 不因报告格式、绘图或解析代码变化重跑 HSPICE；
- 每个 deck 保存 SHA256、HSPICE 版本、环境、完成状态、输入权威工件 SHA；
- 若匹配的 B-FE1 场景已经存在且 deck SHA 完全一致，必须复用；
- 禁止为了得到 GO 改动 threat waveform、RVT/LVT cell、前缀、tap 数量或门限定义；
- legacy M0/T0/H0/M1/PD1/D0-BR 工件禁止重写；
- 新分支的 regression 必须证明 legacy sensor 文件未被无意修改。

---

# 6. Codex 的逐步执行顺序

Codex 必须严格按以下顺序提交，不得跨阶段：

```text
B-FE0a  冻结 baseline SHA 与 legacy 文件清单
   |
B-FE0b  建立 30 tap / 30 XOR / ideal snapshot 架构合同
   |
B-FE0c  加入 0-HSPICE regression，发布 BFE0_FRONTEND_CONTRACT_READY
   |
   v
B-FE1a  新建独立 B-FE1 多抽头 transistor deck/subckt renderer
   |
B-FE1b  静态审查：只有 30 路真实 XOR 是新增前端负载；无 latch/MF/DFF legalizer
   |
B-FE1c  运行 4 个最小 HSPICE 场景，保存完整 30 tap 波形
   |
B-FE1d  0-HSPICE 后处理：按真实 crossing 重建 piecewise-constant 空间码
   |
B-FE1e  normal/L2 同 Tsample 成对判别、平台和 headroom 分析
   |
B-FE1f  生成机器可读合同、报告、论文级图和 Gate
   |
   +--> GO          -> 才允许编写 B-FE2 真实 latch 阵列计划
   +--> CONDITIONAL -> 先做前端几何调整计划
   +--> BLOCKED     -> 停止当前候选，不得继续 latch/MF/controller
```

每一个子阶段都应有独立、可审阅的小提交；不要在一个提交里同时创建新 sensor、跑 HSPICE、设计 latch、改 M/F 和改控制器。

---

# 7. B-FE1 明确禁止的后续工作

在 `BFE1_SPATIAL_OBSERVABILITY_GO` 之前，禁止：

- 真实 latch 单元选择和 latch 阵列实现；
- 把 legacy M/F 接到 `S_CLK` 形成 `sample_close`；
- 新的 startup calibration FSM；
- L1/L2/L3 新检测码表；
- runtime periodic detector；
- sticky alarm；
- PD_SENSE→PD_CTRL 新 crossing；
- 2075 ps repeated-probe closure；
- full T0 rerun；
- PVT / Monte Carlo；
- tap 裁剪或面积优化。

---

# 8. B-FE1 之后的预定路线（仅作接口定义，不提前执行）

若 B-FE1 = GO：

```text
B-FE2: 真实标准单元 latch 阵列
  - 审计库中 latch 或由 NAND/NOR 构造的可实现结构
  - 加入真实 latch 输入负载
  - 表征关闭孔径、亚稳态、气泡和最小稳定平台

B-FE3: M/F 重构为可编程采样时刻生成器
  - M/F 从“xor_29 延迟形成 DFF CK”改为“S_CLK 延迟形成 sample_close”
  - 保持粗调/精调能力，但重新表征码元

B-FE4: 空间码启动自校准
  - 从 Q=0/1 边界搜索升级为 START/END/LEN/CENTER 稳定区搜索
  - 自动得到本芯片 golden code 和采样时刻

B-FE5: 运行时电压跌落判决
  - 基于空间码偏移建立 L1/L2/L3
  - 再重新闭合 2075 ps 全相位覆盖和跨域接口
```

后续阶段不得引用 legacy DFF 的 M/F→Vtrip 码表作为新结构的已证明事实；新前端一旦改变 tap 负载和比较语义，物理码表必须重新表征。

---

# 9. 本计划的核心判定原则

B-FE0/B-FE1 不追求证明最终宏已经可用，只追求一个干净的物理结论：

> 在不修改现有 RVT/LVT 单元、4/0 初始偏移和 30 级观察长度的前提下，给每一对 tap 加入真实标准单元 XOR 后，是否仍能在同一个采样时刻下获得正常与正式 L2 电压跌落之间稳定、非饱和、正时间裕量的可区分空间码。

只有这个问题得到肯定答案，才值得继续为该空间码设计真实 latch、M/F 采样控制和新的自校准算法。
