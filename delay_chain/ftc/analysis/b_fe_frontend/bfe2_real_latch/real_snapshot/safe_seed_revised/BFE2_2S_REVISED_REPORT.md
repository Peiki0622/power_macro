# B-FE2.2S 修订安全关闭种子离线重建

- Gate：`BFE2_2S_SAFE_SEED_READY`；本阶段新增 HSPICE：0。
- 判据修订：允许每个 tap 在 G close 后 0 次或 1 次、且由关闭前 D crossing 和实测 D→Q 延迟解释的 `single-normal-resolution`；仍禁止 genuine re-flip、unresolved、多次响应、最终 Q 不稳定或 normal/L2 不可区分。
- 0.95 V 合法候选：133 个；选中：`530.125287-538.923950 ps midpoint 534.524619 ps`。
- 选中候选 normal single-resolution taps：[14, 27, 28, 29]；L2 single-resolution taps：[10, 22, 23]；re-flip taps：[]；unresolved taps：[]。
- 选中候选最差 post-close resolution：37.285605 ps；最小区间余量：4.399331 ps；最终 Hamming distance：9；最小 Q bit margin：0.288499398 V。
- 旧严格 NO-GO 证据保留在 `real_snapshot/safe_seed/`；本修订仅新增 `real_snapshot/safe_seed_revised/`。本候选尚未有新的 G/Q 波形，READY 只授权后续唯一一对 B-FE2.2C 确认仿真，本轮未创建 deck、未调用 HSPICE、未进入 B-FE2.3/B-FE3。
