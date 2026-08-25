# FTC 候选 B：B-FE2 安全域捕获纠偏计划（仅推进到 L1A）

> 本文件只定义当前已经有证据支持的架构纠偏与**下一步单变量验证**。禁止提前规划、实现或暗示后续接口优化、完整跨域集成、sample-close aperture、启动校准或最终电压检测。L1A 结果出来以后再人工决定下一步。

---

# 0. 当前冻结事实

工作分支：`bfe-multitap-latched-frontend`

当前 Level-0 依据提交：`cad9610c8c37f45950a6b35dbc04e6f535abe0e2`

以下事实冻结，不得为了重复生成结果而重跑：

1. 4 级 RVT 前缀 / 0 级 LVT 前缀、30 对 RVT/LVT tap、30 个真实 `XOR2_X0P5M_A9TL40` 已形成可用空间观测信息；当前不得修改 sensing geometry。
2. 历史 B-FE2.2/B-FE2.2R/B-FE2.2S/B-FE2.2C 的 `PD_SENSE` 内真实 latch 捕获路线全部作为冻结历史证据保留。
3. B-FE2.2C 固定 `sample_close=534.524618567 ps`，0.95 V normal 中 tap27 出现 source-free post-close re-flip，Gate 为 `BFE2_2C_CORRECTED_SEED_FAILED`。不得继续尝试新的 close 来规避该失败。
4. B-FE2-L0 保持同一 0.95 V normal/L2 XOR stimulus 与同一 `sample_close`，只把 XOR 后的语义改成理想电平恢复并在固定 `PD_SAFE=0.95 V` 的理想透明 latch 中捕获，得到 `BFE2_L0_SAFE_DOMAIN_PASS`。
5. L0 冻结结果：normal final Q=`000000000000000111111111111111`，L2 final Q=`000000000001111111111111000000`，Hamming distance=10，两边无 post-close Q crossing/re-flip。
6. L0 只说明“把捕获从受跌落域隔离到安全域”值得继续验证；它**没有**证明真实 `LATQ_X0P5M_A9TR40`@PD_SAFE 已通过，也没有证明真实 level shifter 已实现。

因此当前只能提出一个新的局部假设：

> 先保持理想 XOR→PD_SAFE 恢复接口不变，仅把理想 latch 恢复成真实 `LATQ_X0P5M_A9TR40` 并供在稳定 `PD_SAFE`，检查原来的 re-flip 是否仍然存在。

---

# 1. 当前允许的架构边界

本阶段只研究下面这一条路径：

```text
PD_SENSE
RVT/LVT paths
    |
30 x XOR2_X0P5M_A9TL40
    |
    |  Level-0 ideal restoration
    |  safe_d = 0.95 V if xor > 0.5*VDD_SENSE else 0 V
    v
PD_SAFE = 0.95 V
30 x REAL LATQ_X0P5M_A9TR40
    |
q[29:0]
```

当前**不定义**：

- 非理想 level-shifter/interface specification；
- 接口 delay/slew/hysteresis/X-region；
- 完整 `PD_SENSE→PD_SAFE` integrated front-end；
- 新的 sample-close aperture；
- M/F 控制；
- startup calibration；
- runtime detector；
- 最终电压检测覆盖；
- PVT/Monte Carlo/版图/面积优化。

这些全部等待 L1A 结果后再决定是否需要以及如何定义。

---

# 2. 永久防跑偏规则（当前阶段）

在 L1A Gate 形成之前：

- 禁止修改 4/0 prefix、30 taps、RVT/LVT path 或 LVT XOR 单元；
- 禁止尝试新的 `sample_close`、G phase、G slew sweep；
- 禁止重新进入旧 B-FE2.3；
- 禁止把 XOR pulse 当 DFF clock；
- 禁止实现非理想 level-shifter 模型；
- 禁止开始完整 AMS 集成；
- 禁止做 startup calibration/runtime detection；
- 禁止做 PVT/Monte Carlo；
- 禁止覆盖 B-FE2.2/B-FE2.2C 失败证据；
- 禁止把 L0 行为 latch 描述成真实 LATQ；
- 禁止把 XA tutorial/preflight 描述成该 30-tap 电路已经完成 transistor-level mixed-signal 验证。

---

# 3. 当前唯一下一阶段：B-FE2-L1A

## 3.1 唯一目标

只回答一个问题：

> 当 XOR→safe_d 仍使用 L0 的理想恢复语义，但 30 个捕获单元改回真实 `LATQ_X0P5M_A9TR40` 且真实 latch 全部供在稳定 `PD_SAFE=0.95 V` 时，固定 B-FE2.2C close 下的 source-free post-close re-flip 是否消失，同时 normal/L2 空间码是否仍然稳定可分辨？

这是单变量因果实验。

## 3.2 必须冻结

```text
scenario 1: 0.95 V normal
scenario 2: 0.95 -> 0.86 V formal L2
sample_close: 534.524618567 ps
PD_SAFE: 0.95 V
interface rule: xor > 0.5*VDD_SENSE -> safe_d=0.95 V, else 0 V
interface added delay: 0
interface slew/hysteresis/X-region: none
capture cell: REAL LATQ_X0P5M_A9TR40
```

不得添加第三个场景，不得改 close。

## 3.3 执行方式

优先实际 mixed-signal 联合求解；如果当前 VCS/AMS/PrimeSim 工具链无法直接把行为接口与真实 LATQ 联立，则允许使用等价的 transistor-level 因果隔离实验：

1. 从冻结的 B-FE2.2C/L0 source waveform 生成 30 路 `safe_d_i`；
2. `safe_d_i` 严格遵守 L0 阈值规则且为 PD_SAFE 全摆幅；
3. 用这些 `safe_d_i` 驱动真实 `LATQ_X0P5M_A9TR40@0.95 V`；
4. G 使用固定 `sample_close=534.524618567 ps`；
5. 最多执行 normal/L2 两个真实物理场景。

若采用等价 PWL 驱动，报告必须明确写成 `equivalent causal isolation`，不得伪称完整 AMS co-simulation。

## 3.4 必须检查

至少检查并保存：

- `safe_d_0..29`；
- `q_0..29`；
- `G`；
- `VDD_SAFE`；
- 每个 Q crossing；
- 所有 post-close Q crossing；
- source-free re-flip taps；
- unresolved / long mid-rail taps；
- normal/L2 final Q code；
- Hamming distance；
- tail stability；
- deck/testbench/model/source SHA 与 simulator/version。

重点必须单独报告历史问题 tap27，而不是只给 aggregate Gate。

---

# 4. L1A Gate

## `BFE2_L1A_REAL_SAFE_LATCH_PASS`

两个固定场景必须同时满足：

- 无 source-free post-close re-flip；
- 无 unresolved/multiple oscillation；
- final Q 稳定；
- normal/L2 final code 可分辨；
- Hamming distance >= 9；
- tap27 不再出现 B-FE2.2C 同类 source-free re-flip；
- 没有修改 fixed close、stimulus 或 sensing geometry。

PASS 的唯一含义：

> 真实 `LATQ_X0P5M_A9TR40` 在稳定 PD_SAFE 下与 L0 理想恢复输入兼容，因此“安全域捕获”假设得到进一步支持。

PASS **不授权任何预定义的下一阶段**。Codex 必须停止，等待人工复审后再修改本计划。

## `BFE2_L1A_REAL_SAFE_LATCH_FAIL`

只要任一固定场景出现 genuine re-flip、unresolved、长期 mid-rail 或丧失 normal/L2 可分辨性，即 FAIL。

FAIL 后：

- 禁止换 close；
- 禁止改 sensing geometry；
- 禁止自动换 latch/DFF；
- 禁止自动引入更复杂接口模型；
- 输出 `BFE2_L1A_REAL_SAFE_LATCH_FAIL` 和完整根因证据后停止，等待人工重新判断 capture mechanism。

---

# 5. 仿真记账与停止条件

历史冻结：

```text
B-FE2.1      4 new HSPICE
B-FE2.2      6 new HSPICE
B-FE2.2C     2 new HSPICE
B-FE2-L0     0 new HSPICE; VCS behavior replay PASS
```

L1A 新预算：最多 **2 个真实物理场景**。

L1A 形成独立 manifest、analysis、report、Gate 和单独 commit 后，**无论 PASS 还是 FAIL 都立即停止**。本计划不允许 Codex继续推演或实现任何后续电压检测阶段。
