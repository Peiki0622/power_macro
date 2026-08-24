# FTC T0-4E 证据闭合与 T0-5 解封报告

## 当前判定

**T0-4 = GO；T0-5 = ENABLED**

本阶段只冻结纠偏后的 T0-4 权威证据、取代旧 STOP 占位状态并建立跨 source-hash 的电气等价复用。未运行 HSPICE，未重跑 238 个正式 T0-4 场景，也未提前声明 T0-5 覆盖率或 T0-6 cadence。

## 已冻结证据

- 正式历史场景：238；6 个 last-Q0 负控制通过，18 个 clean-Q1 minimum-duration 边界有效。
- 唯一诊断电气点：4；诊断目录累计运行：8；真实二次时钟：False。
- 电气等价复用只接受相同的显式物理参数投影和规范化 deck SHA256；单独的 source_hash 漂移不再触发 HSPICE。

## 下游状态

- T0-5 已解封，必须先完成两个 L2 的完整单-probe 窗口；T0-6 仍等待 T0-5 gate。
- `runtime_probe_period.maximum_period_s` 仍为 null；2.5 ns 控制时钟不被当作 runtime probe cadence。
- `VDD_MONITORED < 0.80 V` 继续只允许 heartbeat、stuck-Q、timeout 或无有效检测结果等 fail-safe 语义。

## 本阶段账本

- 新增 HSPICE：0；复用旧场景：0；电气等价复用：0；仅重解析：0；禁止流程新增运行：0。
