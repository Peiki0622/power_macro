# D0-A5 交错架构评审

## 结论

**ARCHITECTURE_ESCALATION_REQUIRED**。D0-A2 的两条 target 诊断在外部 S_CLK 高电平为 3001 ps 时，量到的真实 capture `dff_ck` 高脉宽仅为 301.263 ps 与 519.665 ps，均低于冻结 cell 模型 1000 ps 下限；即使忽略此直接违例，2075 ps 周期扣除 1000 ps CK-high 与 1000 ps CK-low 也只剩 75 ps。Q 侧 result hold 不会改变这个 CK 根因，因此不进入 D0-A4。

`P_lane_verified` 仍未由连续多 probe 晶体管级证据闭合；不得把旧 5700 ps one-shot 参考伪装成物理下限。仅由正式 cell check 加既有 guard 得到的模型下界是 2500 ps，对应 `ceil(2500 / 2075) = 2` 个 capture opportunity。这是后续架构最小规模的保守起点，不是已实现两 lane 的结论。

| 候选 | XOR/D/CK 负载与 trip | 校准、M/F、VDD_MONITORED | ownership、相位及开销 | T0 继承与结论 |
|---|---|---|---|---|
| A. 单 capture DFF 后的 Q/result hold | 不增加 XOR/D/CK 负载，因此不改变 CK high/low 或原 trip。 | 不需独立校准；可共享 M/F 与同一 VDD_MONITORED。 | 仅 PD_SENSE DET ownership；aggregate phase 仍为原 `droop_start-S_CLK_rise`；面积/功耗最小。 | 单-probe T0 Q 判决可继承，但本结构不能修复实测 CK 高宽违例，排除。 |
| B. 两个交错 capture bank | 新 D/CK 支路可能加载原 capture 输入并改变 trip，必须先用最小物理负载预算；每 bank 还必须生成合规的 CK high/low。 | 倾向共享静态 M/F 和 VDD_MONITORED；bank 的 reset/re-arm 与是否共享校准须独立证明。 | DET 期间本地使用，CAL 完全旁路；aggregate phase 需要按被选 bank 的 S_CLK rise 定义；面积/动态功耗约增加 capture/reset 资源。 | 现有 T0 只能继承原 sensing threat，不继承新 bank 的 CK、负载或连续 reset 结论。作为最小后续研究对象，但不能预先声称可行。 |
| C. 独立 sensor lane interleave | 复制 sensing 路径与 capture，可能改变每 lane 负载与 trip，风险最大。 | 每 lane 原则上需独立校准；M/F 是否共享及共享 VDD_MONITORED 都须物理验证。 | H0/M1 ownership 影响最大；aggregate phase 必须分别引用各 lane launch；面积/功耗接近多份完整 sensor。 | 不继承原 T0 对新 lane 的所有结论，需新的最小 target/multi-probe 验证；仅在 B 无法闭合时考虑。 |

下一份独立计划必须先回答“在不破坏冻结原 sensor 证据的条件下，新增 capture bank 如何取得合规 CK high/low”这一根问题；不得把两个同样的窄 CK 脉冲简单交错后宣称解决。本阶段不实现任何 bank、wrapper、FSM、alarm、heartbeat、timeout 或跨电源域接收器，也不运行 A3/A4 HSPICE。
