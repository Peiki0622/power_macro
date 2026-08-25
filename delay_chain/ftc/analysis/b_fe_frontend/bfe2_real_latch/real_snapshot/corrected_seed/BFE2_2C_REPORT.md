# B-FE2.2C corrected seed 离线分析

- Gate：`BFE2_2C_CORRECTED_SEED_FAILED`；本分析新增 HSPICE：0；物理 pair 新增 HSPICE：2。
- corrected requested close：`534.524618567 ps`；normal 实测 G：`534.524625137 ps`；L2 实测 G：`534.572355504 ps`。
- 修订判据审查：第一次由 pre-close D 和实测 D→Q 延迟解释的 post-close resolution 被保留为正常单次 resolution；只有同一 tap 的第二次无时间一致 D 源 Q crossing 才列为 genuine re-flip。
- normal single-resolution taps：[]; L2 single-resolution taps：[]；事件级 normal in-flight taps：normal [27]、L2 []。
- genuine re-flip taps：[27]；unresolved taps：[]；重点证据：normal tap 27。
- normal/L2 最终 Hamming distance：`9`；最小 Q bit margin：`0.474996444 V`；最差 post-close resolution：`18.334981 ps`。
- 结论：corrected seed has a genuine source-free post-close Q re-flip or unresolved tap; retain B-FE2.2 conditional and stop before B-FE2.3。B-FE2.3 未授权；不得再尝试新的关闭时刻。旧 6 场景、首次失败、retry 和 B-FE2.2R root-cause evidence 均未覆盖。
