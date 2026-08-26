# B-FE2-CAL0 capture-safe 窗口修复说明

## 阶段边界

本阶段只修正 CAL0 的“安全关闭窗口”定义，不实现自校准控制器，也不进入运行时检测。
以下条件全部冻结：

- 只使用 B-FE2.2C `BFE2L-095-N` 的 `0.95 V` normal source；不使用 L2。
- `sample_close=534.524618567 ps`、launch=`1000 ps`，名义 `G close=1534.524618567 ps` 不变。
- 30 taps、4/0 RVT/LVT sensing geometry、Level-0 理想恢复、`VDD_SAFE=VNW=0.95 V`、
  `VPW=VSS=0 V` 不变。
- 真实捕获单元保持 `LATQ_X0P5M_A9TR40`；无电路、geometry、M/F code 或 FSM 修改。

## 修正方法

旧 CAL0 把相邻 `safe_d` crossings 之间的无事件区间直接视为安全关闭区。此次改为：

1. 读取已保留的 L1A-R normal 和 CAL0 LEFT/CENTER/RIGHT XA boundary evidence。
2. 对每个 tap 的 `q_event` 按时间排序，从 Q 自身的 `state_before/state_after` 推导
   `rise/fall`；不再使用当时的 `safe_d_v` 推断方向。
3. 将 Q event 与同方向的 `safe_d` crossing 配对，提取真实 D→Q flight 延迟。
4. 对每个 pre-close crossing 建立禁止窗口：从 crossing 时刻开始，直到实测 Q threshold
   resolution endpoint；不加入额外 delay、slew、hysteresis 或经验 margin。
5. 从原 LEFT/CENTER/RIGHT 附近 envelope 中扣除合并后的 in-flight 禁止窗口；只有剩余的
   正宽度区间才有资格选择新的 XA 代表点。

## 实测 flight 范围

- rise 最大 flight：`32.128162847 ps`（RIGHT tap29）。
- fall 最大 flight：`40.068196445 ps`（已有 fall 事件的最大值，用于未直接观测到的相关
  tap fall 方向保守裁剪）。
- nominal 附近合并禁止区：`1481.270581340–1578.636847028 ps`。
- 原 CAL0 local envelope：`1515.519619746–1567.568495557 ps`。

两者完全重叠，因此没有剩余 capture-safe interval，也没有合法的代表点可供新的 XA
验证。按照本阶段约束，未启动任何新的 VCS+PrimeSim XA 场景。

## Q 方向修正的直接证据

- LEFT tap27：`1498.554093337 ps` 的 source-backed rise 在 `1528 ps` 到达 Q threshold；
  随后的 `1544 ps` 是 Q 从 1 到 0 的 source-free fall。
- RIGHT tap29：`1529.871837153 ps` 的 source-backed rise 在 `1562 ps` 到达 Q threshold；
  随后的 `1565 ps` 是 Q 从 1 到 0 的 source-free fall。

这两个事件此前曾被错误地按 safe_d 电平归为同方向；修正后明确显示 source-free
re-flip/unresolved capture 失败。

## Gate 与验证

Gate 为 `BFE2_CAL0_CAPTURE_SAFE_WINDOW_BLOCKED`，原因是
`NO_CAPTURE_SAFE_INTERVALS_NEAR_NOMINAL`。由于没有至少两个相邻的真实 capture-safe 点，
不评估新的空间单调性，也不推进任何后续阶段。

已通过：

- `py_compile`（capture-safe runner/analyzer）；
- `pytest -q delay_chain/ftc/tests/test_bfe2_l1a.py`：4 passed；
- `git diff --check`。

本阶段在此停止；不进入自校准、旧 M/F 重用、FSM、运行时检测或其他后续阶段。
