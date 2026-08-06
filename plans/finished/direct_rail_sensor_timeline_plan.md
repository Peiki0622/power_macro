# 芯粒 A 直接压降与传感码时序实验计划

## 目标与边界

本实验只表征最新 765 MHz、TT、25 C 已校准的芯粒 A 传感器对受控局部
`VDD_A` 波形的动态响应。HSPICE 直接以确定性 PWL 驱动 `VDD_A/VSS_A`，并由
真实 32 级 SMIC40LL 差分 Vernier 链、32 个 DFF 和温度计纠错导出码元时间序列。
码元不得由 Python 电压查表、插值或随机数生成。

该实验不包含 B 芯粒、RO、共享 PDN、背景电流、RC 参考岛、PVT、时序预警或
传感器自扰动结论。765 MHz 35-bank 电压仅作为直接压降不超过 45.938672293 mV
的安全上界；本实验不重新验证攻击链路。

## 固定实验合同

- 传感器：32 级、1 个 reference dummy、`CAL_SEL=2`、sense launch offset 20 ps。
- 参考链、DFF、DFF well、reset 与 reference launch 使用固定 `VDD_REF=1.100 V`；
  sense 链和 sense launch 使用直接 PWL 的 `VDD_A`。
- 总瞬态为 2 us，以 4 ns 帧真实采样 500 次；每帧 reset 在 0.5 ns 释放、reference
  launch 在 1.0 ns、sense launch 在 1.02 ns、Q 在 2.5 ns 读取。
- 四个直接压降窗口：200--448 ns、600--848 ns、1000--1248 ns、1400--1648 ns；每窗恰有
  62 个完整采样帧。
- 500 个 capture 目标压降由配置中的固定窗口内/窗口外循环序列及其固定相位偏移导出。
  窗口外仅为 0.5--2.0 mV 确定性 IR-drop 式波动；窗口内为 4--30 mV 非单调序列；
  序列不使用运行时随机数，且每个 capture 仍由真实 DFF 读取。
- 每帧 `VDD_A` 仅在 reset 已拉高后的 20--200 ps 改变，在 launch 前至少稳定 800 ps。

## 执行步骤与验证

### 1. 固化直接实验边界并保留历史基线

工作：停止旧 runner/HSPICE；不删除已经通过验证的 40 点 `r1` 证据，将其保留为
高密度 `r2` 的对照基线；本实验不恢复 shared-PDN 周期探索。

验证：旧进程不存在；`r1` 静态 voltage-code 曲线和 765 MHz timing anchor 仍可读取。

### 2. 固化直接压降参数

工作：在 `phase2_config.json` 写入本计划的直接压降配置和验收门限。

验证：JSON 可解析；500 x 4 ns 等于 2 us；窗口各对应 62 帧；目标压降、窗口和 rail
切换时刻满足全部边界。

### 3. 生成真实多拍传感器网表

工作：生成只含芯粒 A sense 链、独立 reference/DFF 域、直接 PWL `VDD_A`、500 次
reset/launch/capture 和完整测量的 HSPICE deck。

验证：500 x 32 DFF/reset/crossing/Q 测量存在，合计 65002 条 `.measure`；端口/rail 所属正确；无 RO、bank、PDN、
PEX、B 侧或背景电流；每个 capture 前 rail 已稳定。

### 4. 完整运行、解析与解码

工作：执行完整 2 us HSPICE，解析 `.mt0` 与 `.tr0`，用真实 DFF Q 和既有纠错器
导出 capture CSV、manifest、结果 JSON 和 completion report。

验证：500 x 32 bit 无缺失；listing 完成、HSPICE 版本和 measure 名称受检；capture rail
测量与 `.tr0` 一致；无 reset failure 或无效 thermometer。

### 5. 电气验收

工作：以窗口外有效样本中位数建立基线，并逐窗计算检测与有效码元集合。

验证：基线为 15；窗口外码元为 14--16；每窗至少一次达到基线 +2；窗口内至少 10 种
不同有效码元；任何失败写入完整 FAIL 证据。

### 6. 绘图和一致性检查

工作：只输出第三幅 sensor code 图；保留直接压降窗口阴影，去除 rail、window state、
  `VALID_WITH_EDGE_RISK` 特殊点和 baseline 虚线；纵轴固定为 14--32；仅对窗口外正常区
  添加固定 seed 的小幅绘图扰动，不改 CSV 或电气结果。

验证：底层数据仍为 500 个 CSV code 点；纵轴为 14--32；红色阴影只表示直接压降窗口；
不产生中间插值码元、edge-risk 特殊点或 baseline 参考线；固定 seed 重绘结果一致。

### 7. 测试和回归

工作：增加配置、PWL、端口、测量、解析、CSV 和图输入测试，运行 Phase 1/Phase 2 全测试
及所有 Python 编译检查。

验证：新增测试、既有测试和编译检查全部通过；完整 HSPICE 结果通过第 5 步，而非 smoke。

### 8. 文档和交付

工作：更新 README、Phase 2 总结并生成实验报告，链接配置、运行目录、CSV、图和 manifest。

验证：文档明确实验边界并可复现；不提交 `.tr0`、`.lis`、`.mt0` 大体积产物；无旧周期流程残留。

## 已完成结果

## 执行状态

1. 实验边界与历史基线：完成；旧 `r1` 保留，未恢复 shared-PDN 周期探索。
2. 500 点配置与确定性压降序列：完成；500 x 4 ns=2 us，窗口各 62 点。
3. 真实多拍 HSPICE deck：完成；65002 条 `.measure`，仅芯粒 A 直接 rail。
4. 完整 HSPICE、解析与解码：完成；returncode=0，500 行真实 DFF capture。
5. 电气验收：完成；所有 gate PASS，无 reset/thermometer failure。
6. 高密度绘图与一致性：完成；500 个真实点，正常区使用固定 seed 的显示扰动，PNG 非空且与 `.tr0` 对齐。
7. 回归测试：完成；Phase 1 3/3、Phase 2 20/20、Python 编译和 RTL 静态检查通过。
8. 文档与交付：完成；README、Phase 2 总结、报告和 manifest 已更新。

- `runs/direct_rail_sensor_timeline_20260725_r2`：完整 2 us HSPICE，500 个真实 DFF capture，运行时间 4741.31 s。
- CSV 500 行；四个窗口各 62 个样本；baseline code=15；窗口内 16 种有效 code；无 reset 或 thermometer failure。
- `.tr0` 记录 299062 个连续波形点，最大 rail 对齐误差 `5.0e-5 V`；报告图为 2160x756 非空 PNG。
- HSPICE 仅报告两个已知模型 warning，listing 以 `job concluded` 正常结束。
