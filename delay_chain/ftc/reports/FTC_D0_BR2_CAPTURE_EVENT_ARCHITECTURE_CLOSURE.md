# FTC D0-BR2 方向选择与合法 capture event 静态闭合

## 结论

**CAPTURE_EVENT_ARCHITECTURE_BLOCKED**，但这不是 shared sensor 的物理阻塞。BR1R 的 `SHARED_SENSOR_CADENCE_RETIMING_GO` 保持有效：冻结单 sensor 在 2075 ps 下的 E0/EF/E1 同节点传播仍已通过。本次只重解析 750/1000/1250 ps、两个正式 target 的 6 个 retained scenario；新 HSPICE 为 0。

唯一的方向选择 primary 是 `xor_29 & lvt_29` 的 `AND2_X0P5M_A9TR40`，插在 `xor_29 -> medium`，D 仍为 `xor_29`。它在上升波由已到达的 XOR 放行，逻辑上抑制 LVT 先离开的 EF。`lvt_29 & ~rvt_29` 虽布尔等价，却可能先于 XOR 抵达，不能直接作为 medium/CK 的发起事件。所有新负载与延迟仍需后续最小晶体管验证，尤其要数 EF/glitch；本审计没有把 Liberty 表点伪装成 HSPICE 结果。

## 为什么无状态 fixed-delay legalizer 不能闭合

对 direct + delayed-replica + OR 的 falling-edge 延展器，任一事件的共同延迟 `d` 必须同时满足 `raw_width+d >= 1000 ps` 和 `E0->E1_spacing-(raw_width+d) >= 1000 ps`。全部 retained E0/E1 中，窄高压 E1 要求 `d >= 743.391464 ps`，而长低压 E0 要求 `d <= 544.622663 ps`。交集为空。

因此没有选择 DLY/OR 链、没有创建 legalizer/bank/FSM，也不进入两个 target 的最小 HSPICE。连续 overwrite 比 per-probe reset 更合理（后者安全非重叠下至少 `1000+1000+1000=3000 ps`），但单 context 的原始 E0→E1 最小间隔仅 2063.724113 ps，扣除 DFF CK high/low 只剩 63.724113 ps，静态上 timing-fragile。交错 context 本身不能修复全局 legalizer 的脉冲 high/low 冲突。

下一步只能是新的 0-HSPICE、固定宽度/有状态 legalizer 静态研究，并先证明其自身没有把 256--519 ps 输入 min-pulse 依赖转移到新 cell；在那之前禁止 capture bank、runtime FSM 和任何 HSPICE。
