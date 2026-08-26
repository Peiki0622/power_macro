# B-FE2-CAL0 详细说明

## 结论

本阶段的 Gate 为 `BFE2_CAL0_SAMPLE_CLOSE_NOT_CALIBRATABLE`，失败类别明确为
`CAPTURE_SEMANTICS_FAIL`。空间判别本身没有失败：三点的 Q ones 数为
`[13, 14, 14]`，具备局部非递减特征；三个离线 ledger 区间均为正宽度。

## 冻结边界

- 唯一 source waveform：B-FE2.2C `BFE2L-095-N`，normal `0.95 V`；未使用 L2。
- `sample_close` 名义值为 `534.524618567 ps`；launch 为 `1000 ps`，名义 G close 为
  `1534.524618567 ps`。
- source signature 冻结为 30 taps、`XOR2_X0P5M_A9TL40`、RVT/LVT path、既有
  `bfe2_real_latch_30tap_4over0_corrected_seed_v1` geometry。
- Level-0 恢复规则为 `safe_d = 0.95 V` 当 `xor > 0.5*VDD_SENSE`，否则 `0 V`；无额外
  delay、slew、hysteresis 或 X-region。
- 捕获单元为真实 `LATQ_X0P5M_A9TR40`；未修改电路、geometry、M/F code 或 FSM。

## 离线区间重建

只读取已通过 L1A-R normal `safe_d` crossing ledger，未运行 solver，也未做密集网格扫描。
围绕名义 G close 的局部事件为 tap28 rise `1515.519619746 ps`、tap29 rise
`1529.871837153 ps`、tap15 fall `1538.568650583 ps`、tap16 fall
`1567.568495557 ps`。因此选择三个 event-free 区间及代表点：

| 点 | sample_close / G close (ps) | START..END (ps) | LEN (ps) | CENTER (ps) | LEFT / RIGHT_HEADROOM (ps) |
|---|---:|---:|---:|---:|---:|
| LEFT | 522.695728450 / 1522.695728450 | 515.519619746..529.871837153 | 14.352217407 | 522.695728450 | 7.176108704 / 7.176108704 |
| CENTER | 534.524618567 / 1534.524618567 | 529.871837153..538.568650583 | 8.696813430 | 534.220243868 | 4.652781414 / 4.044032016 |
| RIGHT | 553.068573070 / 1553.068573070 | 538.568650583..567.568495557 | 28.999844974 | 553.068573070 | 14.499922487 / 14.499922487 |

## VCS+XA 结果

| 点 | Q[29:0] | ones | source-free re-flip | unresolved | mid-rail | tail | post-close safe_d→Q |
|---|---|---:|---|---|---|---|---|
| LEFT | `000000000000001111111111111000` | 13 | tap27 | tap27 | none | stable | none |
| CENTER | `000000000000001111111111111100` | 14 | none | none | none | stable | none |
| RIGHT | `000000000000000111111111111110` | 14 | tap29 | tap29 | none | stable | none |

LEFT tap27 在 G close 后出现 source-backed Q event 后又出现无对应 source crossing 的
source-free rise；RIGHT tap29 同样出现 source-free rise。CENTER tap27 无后置 Q event。
这些 re-flip/unresolved 违反“G 关闭后 safe_d 变化不得再改变 Q”的捕获语义，故即使
空间 ones 特征单调且区间有正 headroom，整体仍不可校准。

## 验证与停止

- `py_compile`：通过。
- `pytest -q delay_chain/ftc/tests/test_bfe2_l1a.py`：`4 passed`。
- `git diff --check`：通过。
- 本阶段只提交 CAL0 目录；既有无关 plan 文件改动未纳入。
- `stop_after_stage=true`、`next_stage_authorized=false`；不进入自校准控制器、旧 M/F
  重用、运行时检测或任何后续阶段。
