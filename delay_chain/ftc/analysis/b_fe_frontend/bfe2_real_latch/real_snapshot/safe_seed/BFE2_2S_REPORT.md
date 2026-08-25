# B-FE2.2S 安全关闭种子离线重建

- Gate：`BFE2_2S_SAFE_SEED_BLOCKED`；本阶段新增 HSPICE：0。
- 0.95 V：normal/L2 共有 66 个干净 Q 稳定交集，经逐 tap、逐方向透明态 D→Q in-flight 检查后，保留 0 个正宽度 provisional 安全区，拒绝 129 个子区间。
- Liberty 审计仅证明 1.10 V typical-max 库中存在 `setup_falling`/`hold_falling` 约束表；没有可直接用于本 0.95 V 研究的数值，故未编造 setup/hold margin。采用的 provisional 边界仅为实测 Q 稳定区和每路 D→Q 完成。
- 1.10 V 历史 pair 的新规则一致性：存在 post-close in-flight 冲突。不重跑 1.10 V。
- 结论：0.95-V normal/L2 has no positive-width common Q-stable interval free of every measured pre-close D-to-Q flight。B-FE2.2C 未获授权，未创建或运行新 deck。

未来关闭点不得由 XOR `RAW_CODE` 平台中点生成；只有 Q 稳定、所有相关 D→Q 已完成且有明确 setup/hold 或 provisional 等效风险处理时，才允许进入一次确认仿真。
