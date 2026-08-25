# B-FE2.2R 根因闭合

- Gate：`BFE2_2R_ROOT_CAUSE_CONFIRMED`；本阶段新增 HSPICE：0。
- 0.95 V normal retry 的实测 G 关闭为 320.334161 ps。tap 6 的 XOR/D 在 280.066209 ps 下穿；透明态 B-FE2.1 同方向实测 D→Q 延迟为 47.090214 ps，预测 Q 下穿 327.156423 ps，而快照实测为 329.278963 ps（误差 2.122540 ps）。因此这是关闭前已进入锁存器、关闭后完成的正常 in-flight 数据响应。
- 同一 tap 的 Q 随后在 368.394335 ps 上穿；不存在可在透明态实测 D→Q 延迟内预测该上穿的 XOR/D 上穿。因此这是外部 Q 端真正关闭后再翻转，不能归为正常透明态 D→Q 传播。闭锁反馈恢复与此一致；内部 LATQ 节点未探测，故不声称已直接观测到具体反馈晶体管。
- 新规则：不得再把 XOR `RAW_CODE` 平台中点直接作为 G 关闭时刻。未来真实关闭仿真前，normal/L2 成对候选必须位于 Q 空间码稳定区，并证明相关 pre-close D 事件已按实测透明态 D→Q 延迟传播完成；还必须留出 Liberty setup/hold 或晶体管级等效余量。该规则不是新的关闭点，本轮未运行 HSPICE，也未进入 B-FE2.3/B-FE3。

机器证据：`real_snapshot/root_cause/BFE2_2R_ROOT_CAUSE.json` 与 `BFE2_2R_EVIDENCE_LEDGER.json`。
