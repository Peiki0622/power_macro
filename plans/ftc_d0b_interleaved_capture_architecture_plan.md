# FTC D0-B：合法 capture 脉冲与最小交错架构闭合计划

## 1. 背景与入口

D0-A 已完成并发布 `ARCHITECTURE_ESCALATION_REQUIRED`。在两个正式 T0 L2/3002 ps target 点，冻结 sensor 的外部 `S_CLK` 高电平为 3001 ps，但真实 `dff_ck` 高脉宽仅为 519.665 ps（0.95 V）与 301.263 ps（1.10 V），均低于审计的 1000 ps sequential-cell 下限。D0-A 还确认：即便只按 formal CK high/low 1000 ps 下限计算，`P_runtime=2075 ps` 仅剩 75 ps 总余量；250 ps/half-cycle guard 的模型下界为 2500 ps。

因此 D0-B 不得把两个同样的窄 `dff_ck` 脉冲简单交错，也不得把 D0-A 的模型 `N_min=2` 误写为已验证实现。本计划只研究最小的 detection-only capture/交错架构；没有此计划明确的 Gate，不实现完整 D0 FSM、alarm、heartbeat、timeout 或系统跨域接收器。

权威入口：

- `delay_chain/ftc/analysis/d0_runtime_fastpath/baseline/frozen_input_sha256.json`
- `delay_chain/ftc/analysis/d0_runtime_fastpath/a1_physical_budget/physical_timing_budget.json`
- `delay_chain/ftc/analysis/d0_runtime_fastpath/a2_single_path_candidate/candidate_timing_contract.json`
- `delay_chain/ftc/analysis/d0_runtime_fastpath/a5_interleave_review/lane_count_analysis.json`
- `delay_chain/ftc/analysis/d0_runtime_fastpath/reports/D0_A_GATE_STATUS.json`

## 2. 不可变边界

- 保持 FTC_SENSOR、H0、M1、M/F 静态 DET 配置、T0 threat/phase 定义和已完成 T0 物理 Gate 不变。
- 保持 `phase = droop_start - S_CLK_rise`；aggregate probe 必须为每个实际 launch lane 分别记录该定义，不能用控制时钟替代。
- 不因 D0-B 改写 T0 `CONDITIONAL_GO`、2075 ps 覆盖要求、Q 的两次真实独立稳定观察要求或 PD1 电源域合同。
- 不得将 D0-A 旧 one-shot 的 5700 ps 或 guard-only 2500 ps 当成已验证单 lane 周期。
- H0/M1 CAL 路径必须完全旁路新增 detection-only 架构；M/F 只允许在 DET entry 前静态装载。
- 不新建/不复制完整 sensor lane，除非本计划的 B4 Gate 明确否定更小的 capture-bank 方案且另立下一份 plan。

所有 HSPICE 必须使用容器内 `/home/zhupl25/.local/bin/hspice`，并在 `delay_chain/ftc/runs/d0b_interleaved_capture/` 下以 task-owned 目录保存 deck、listing、measure 和 manifest；分析只提交紧凑 JSON/CSV/报告。

## 3. 分阶段执行

### D0-B0：冻结输入与范围审计（0 HSPICE）

做什么：重新 hash 上述 D0-A 输入、T0/M0/PD1/RF 合同与本计划，发布 D0-B baseline。显式记录 D0-A 的 CK high 实测违例、`P_lane_verified=null` 和“D0-B 未授权实现 RTL/复制 sensor”的范围。

验证：所有 hash 与 D0-A baseline 一致；D0-A Gate 为 `ARCHITECTURE_ESCALATION_REQUIRED`；运行账本为 HSPICE=0；若任一冻结输入漂移，停止并要求先完成证据重新评审。

### D0-B1：最小 capture 来源与负载可行性筛选（0 HSPICE）

做什么：只用已审计 CDL、cell timing check 与 PD1 合同，比较以下三类连接，不编写 RTL：

1. 原 capture DFF 的 Q-side hold；
2. 两个独立 reset/re-arm 的 capture bank，仍共享现有 sensing path；
3. 完整独立 sensor lane。

对每类写清 D、CK、XOR、medium/fine 上新增负载，是否仍依赖 D0-A 已否定的窄 `dff_ck`，是否可能提供每 bank 合规的 CK high/low，M/F/VDD_MONITORED 是否共享，CAL/DET ownership、aggregate phase、面积/功耗级别及 T0 证据继承边界。第一类和“复用同一窄 CK 的 bank”必须直接淘汰，不能以数字同步器或复制 Q 伪装双观察。

验证：发布 `b1_capture_source_screen.json` 与简短比较表；被选候选必须不加载或改变冻结原 XOR/medium/fine/capture 路径，且其合法 CK 来源在静态约束中没有矛盾。若没有候选满足该条件，发布 `ARCHITECTURE_REVIEW`，不运行 HSPICE、不进入后续阶段。

### D0-B2：单一最小候选的接口合同（0 HSPICE）

做什么：仅为 B1 唯一通过的候选发布 detection-only 微时序合同。合同必须定义每 bank 的 launch、合法 CK rise/fall/high/low、D 输入来源、两次真实 Q 观察的独立时刻、sticky/hold clear、reset assert/release/recovery/removal、bank 交接与 M/F 静态窗口。CAL 路径完全旁路，且不声称尚未物理验证的跨 PD_CTRL 接收器存在。

验证：逐项对照 2075 ps、CK high/low 1000 ps、recovery 1000 ps、removal 500 ps 与两次 Q 独立观察；确认不会使用原 D0-A 实测 301/520 ps 窄 CK。由静态合同不能闭合时停止，不为“试试看”直接仿真。

### D0-B3：受限晶体管级 capture-bank 物理预检（仅 B2 通过时）

做什么：只验证 B2 的一个候选及其新增最小接口，默认最多 2 个 task-owned 单-probe HSPICE 点：0.95 V/L2/0.86 V/3002 ps 与 1.10 V/L2/0.96 V/3002 ps，使用现有 T0 最坏相位附近。量测每 bank CK edge count、CK high/low、Q 10/90、两次独立观察、reset 清零、D/CK/XOR 负载导致的延迟变化和 M/F 恒定性。

验证：两点均满足 formal CK/recovery，并且原 sensing trip/target Q 判决未发生不可接受漂移；任一点出现新增 CK edge、CK width 违例或原 path 负载问题即停止。禁止相位、VDD、duration sweep，也不重跑 M0/T0/H0/M1。

### D0-B4：连续交错 probe 最小验证与 Gate（仅 B3 通过时）

做什么：最多 4 个核心 multi-probe HSPICE 场景：两正式基准无 droop 和两个正式 L2/3002 ps target，均至少覆盖三个连续 aggregate probe。记录每一 bank 的 CK high/low/edge count、两次 Q 观察、reset/re-arm、M/F、bank 交接和 phase；不新增边界扫描。

验证：仅当 `P_runtime<=2075 ps`、两个 no-droop 无误报、两个 target 可重复检测、每 bank 的 CK/recovery 与两次真实 Q 观察都成立、且 H0/M1 CAL 与 T0 threat 合同不受影响时，发布 `D0_INTERLEAVED_CAPTURE_GO` 并另立 D0-C 实现计划。否则发布 `ARCHITECTURE_ESCALATION_REQUIRED`；若失败根因要求改变 medium/fine/XOR 或复制完整 sensor，则停止并另立更大范围架构计划。

## 4. 禁止项与完成条件

本计划不允许把 B3/B4 变为扫描，不允许以功能波形“看起来正确”覆盖 formal timing check，也不允许实现完整 runtime 控制逻辑。D0-B 的完成只能是 B4 的真实 GO 或明确的升级 Gate；两者都必须保留 HSPICE 账本、冻结输入 hash、最小物理证据和未闭合项。
