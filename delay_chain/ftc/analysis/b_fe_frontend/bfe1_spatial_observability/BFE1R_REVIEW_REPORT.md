# B-FE1R 修正审查报告

## Gate

**BFE1R_READY_FOR_BFE2**

本阶段 0 个新 HSPICE；未实现 latch，未修改 M/F、控制器或旧 sensor。

## XOR 选择

正式选择：`XOR2_X0P5M_A9TL40`（LVT）。它与 legacy `XOR2_X0P5M_A9TR40` 具有相同七端口、真值函数、10 个晶体管和相同 W/L；LVT A/B 输入电容分别比 RVT 高约 5.44%/6.96%，但已有四场景就是在该真实 LVT 负载下完成，且 TT Liberty 时序没有显示系统性变慢。
若未来改回 RVT，必须重新运行 B-FE1 四场景；本阶段没有重跑。

## 候选窗口

评分同时考虑平台宽度、四侧最小 headroom、汉明距离、ΔSTART/ΔEND/ΔCENTER、最小 bit 裕量、中心 tap 偏好及碎裂。完整排名在 `BFE1R_REVIEW_STATUS.json`。
- 0.95 V：首选 410.717842–424.631112 ps，宽 13.913270 ps，中心 14.75，headroom 7 tap，HD 7，最小裕量 0.232330 V。
  0.95 V 中部 tap 候选优于旧报告最大平台：综合分 0.7095 对 0.5209；旧平台中心 3.50、headroom 1，中部首选中心 14.75、headroom 7。
- 1.10 V：首选 300.987260–312.678869 ps，宽 11.691609 ps，中心 14.25，headroom 8 tap，HD 9，最小裕量 0.240996 V。

## 证据边界

`BFE1R_EVIDENCE_MANIFEST.json` 只保存四个场景的身份、deck/tr0 SHA256、HSPICE 版本、record count、权威输入 SHA 和分析产物 SHA，不复制巨大 `.tr0`。现有 `BFE1_SPATIAL_OBSERVABILITY_GO` 未被无依据推翻。
