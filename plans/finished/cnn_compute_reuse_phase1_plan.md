# 多统计量二分类 1D-CNN 计算复用第一阶段实施计划

## 1. 目的

本计划用于指导 Codex 在当前仓库基础上，按可验证、可回退的小步方式推进以下三项任务：

1. 完成 `multistat_w18_k5` 二分类 1D-CNN 的定点参考模型；
2. 实现仅处理真实 L32 传感器窗口的 CNN RTL 原型；
3. 使用手工构造的 dummy 窗口测量 CNN 硬件自身的功耗差异，并建立第一版计算活动码本。

这三项任务是后续“计算复用 + 电荷整形 + 随机扰动”的基础，但本计划本身不实现分段储能、电荷整形、TRNG/PRNG 调度或完整侧信道防护闭环。

总体顺序必须保持为：

```text
冻结模型与数值合同
        -> 定点 bit-true 参考模型
        -> 真实窗口 CNN RTL
        -> RTL/门级活动测量
        -> 手工 dummy 窗口功耗码本
        -> 判断是否值得进入窗口时隙复用
```

Codex 可以根据仓库现有结构决定文件拆分、类名、脚本参数和局部实现方式，但不得改变本计划规定的模型任务、验证边界和阶段顺序。

---

## 2. 当前模型口径

本阶段的开发目标是最新的普通多统计量二分类 CNN，而不是早期全局平均池化 CNN，也不是历史 TCN。

目标模型：

```text
architecture_id = multistat_w18_k5
input_channels  = 1
window_length   = 32
classes         = Safe / Critical
channels        = [18, 18, 18]
kernel_size     = 5
pooling         = global average + global maximum + endpoint
classifier      = two-class linear head
```

当前源码依据至少包括：

```text
tcn_detection/models/cnn1d.py
tcn_detection/train/common.py
tcn_detection/config/model_cnn_state_code_binary_multistat_w18_k5_v1.json
tcn_detection/config/state_code_binary_cnn_multistat_training_stage2_v1_20260731_r1.json
tcn_detection/runs/formal_v1_20260727_r1/reports/
  state_code_binary_multistat_training_v1_20260731_r1/final/FINAL_TRAINING.md
```

开发 checkpoint 应以 `FINAL_TRAINING.md` 中聚合选择规则给出的最终代表 checkpoint 为权威。当前报告记录的代表种子为 `20260727`，checkpoint SHA256 为：

```text
b6741281203fc4593b6434df584ace44cffa5daed23ece8745d1b14215a64814
```

仓库不提交神经网络 checkpoint。Codex 必须：

1. 从现有 run manifest 或训练目录解析实际 checkpoint 路径；
2. 在任何定点导出前验证 checkpoint SHA256；
3. checkpoint 缺失或摘要不匹配时立即停止，并输出清晰的阻塞报告；
4. 不得静默改用 seed `20260725` 或其他 checkpoint；
5. 不得为了本阶段重新打开或重跑已冻结 IID 测试。

需要保留的科学边界：

- 当前最新 CNN 的优势证据主要来自固定 validation 集的三种子聚合；
- 本阶段不得宣称模型已经 deployment-ready；
- 不修改 Safe/Critical 标签定义；
- 不增加新的在线输入特征；
- 不把测得电压、slack、波形族或未来样本送入 CNN；
- 不重写已有不可变数据、预测文件和报告；
- 不根据 IID/OOD 结果选择位宽、阈值或 RTL 结构。

---

## 3. 全局执行规则

### 3.1 小步提交

建议按以下独立提交推进，Codex 可在不破坏依赖关系的前提下微调：

```text
commit 1: add fixed-point contracts and checkpoint provenance gate
commit 2: add bit-true fixed-point reference model and tests
commit 3: add golden-vector export and quantization report
commit 4: add real-window CNN RTL skeleton and cycle model
commit 5: complete RTL datapath, testbench, and synthesis smoke flow
commit 6: add handcrafted dummy-window library and activity characterization
commit 7: publish phase-1 acceptance report and next-stage decision
```

每个提交必须保持测试可运行；不得在一个提交中同时引入定点算法、完整 RTL 和功耗实验。

### 3.2 可复现性

所有新脚本必须显式记录：

```text
source commit SHA
model config SHA256
checkpoint SHA256
quantization config SHA256
input window set SHA256
random seed, if any
tool versions
command line
start/end time
exit status
```

所有生成目录必须版本化，默认拒绝覆盖。禁止将大型 checkpoint、波形数据库、VCD/FSDB、综合临时目录和工具缓存提交到 Git。

### 3.3 测试边界

本阶段允许使用：

- 训练集样本做量化校准；
- validation 样本做定点精度选择和阶段验收；
- 人工合成的合法 sensor-code 窗口做硬件活动实验；
- 少量固定 golden windows 做 RTL 回归。

本阶段禁止：

- 读取 IID 特征或预测来选择量化方案；
- 重新计算冻结 IID 指标；
- 使用 OOD 结果调硬件位宽；
- 将 dummy 窗口加入模型训练；
- 修改已有 validation/test 划分；
- 在功耗实验前加入随机调度，以免失去可重复性。

---

# 任务一：完成 `multistat_w18_k5` 定点参考模型

## 4. 任务一目标

建立一个独立于 PyTorch 浮点执行细节的 bit-true 参考模型，为 RTL 提供唯一数值真值。

要求覆盖完整推理路径：

```text
normalized sensor-code L32 window
        -> Conv1D layer 1, k=5, 1->18
        -> ReLU
        -> Conv1D layer 2, k=5, 18->18
        -> ReLU
        -> Conv1D layer 3, k=5, 18->18
        -> ReLU
        -> global average
        -> global maximum
        -> endpoint feature
        -> concatenate 54 features
        -> two-class linear classifier
        -> Safe/Critical logits or decision
```

部署硬件不需要实现 softmax。默认应比较两个定点 logit，或比较等价的单一 logit difference。Codex 可以选择实现形式，但必须证明它与浮点 argmax 决策等价。

## 5. 任务一实施步骤

### Step 1.1：模型和 checkpoint 解析

新增一个只读导出入口，完成：

- 解析模型 JSON；
- 构造 `CNN1D`；
- 严格加载权重；
- 校验参数名称、shape 和 checkpoint SHA256；
- 输出权重、偏置、层顺序和池化合同清单；
- 拒绝带缺失键、额外键或 shape 不匹配的 checkpoint。

不得依赖代码中的隐式默认值。所有定点配置必须写入版本化 JSON。

### Step 1.2：冻结浮点基准

从 train/validation 中选取小而覆盖充分的窗口集，至少包括：

```text
Safe 稳态
Safe 缓慢变化
接近分类边界
Critical 短峰值
Critical 持续低裕量
末端状态主导
窗口内部最大值主导
平均水平主导
```

保存浮点中间层输出和最终 logits，作为定点调试基准。窗口选择必须按 trace 分组，记录来源，不得从 IID 读取样本。

### Step 1.3：量化配置搜索

Codex 可以决定具体搜索范围，但至少比较：

```text
weight: INT8 and one higher-precision candidate
activation: INT8 and one higher-precision candidate
accumulator: no-overflow width derived from worst-case bound
bias: explicit aligned fixed-point format
```

必须明确：

- 对称或非对称量化；
- per-tensor 或 per-output-channel weight scale；
- 每层 activation scale；
- rounding 规则；
- saturation 规则；
- ReLU 截断范围；
- average pooling 除以 32 的实现；
- classifier accumulator 位宽；
- logit comparison 格式。

优先选择硬件简单且精度退化可接受的方案，不以最小位宽为唯一目标。

### Step 1.4：归一化折叠

当前输入归一化为：

```text
x = (sensor_code - 15) / 17
```

RTL 中不应实例化通用除法器。Codex 应优先将常数归一化折叠进第一层权重和偏置，或实现等价的常数乘移位近似。

无论采用哪种方式，都必须由 bit-true 模型逐点验证 0 到 32 的全部 sensor code。

### Step 1.5：实现 bit-true 推理

建议提供纯 Python/Numpy 参考实现，避免依赖 PyTorch quantization runtime。实现必须：

- 使用与 RTL 一致的整数操作顺序；
- 每个截断点与 RTL 对齐；
- 可导出逐层整数 tensor；
- 能单独运行一个窗口；
- 能批量运行 validation 子集；
- 能生成机器可读差异报告。

### Step 1.6：导出硬件包

输出至少包括：

```text
quantization_config.json
model_provenance.json
weights/*.mem or equivalent neutral text format
golden/windows.jsonl
golden/expected_layer_outputs.npz or equivalent
golden/expected_logits.csv
FIXED_POINT_REPORT.md
```

权重导出格式必须稳定、有字段说明、带 SHA256，并与 RTL 加载顺序一致。

## 6. 任务一验收门槛

必须同时满足：

1. checkpoint 摘要与权威报告一致；
2. bit-true 模型对 golden windows 完全确定；
3. 定点实现不存在 accumulator 溢出或未定义截断；
4. validation Accuracy、Macro-F1、Critical PR-AUC、Critical Recall、Safe FAR 均被报告；
5. 精度退化阈值由 Codex在实现前写入量化配置或验收脚本，不得看到结果后放宽；
6. 不读取或重跑 IID；
7. 所有逐层数值测试通过；
8. `FIXED_POINT_REPORT.md` 明确记录最终位宽、scale、舍入、饱和和未解决风险。

若 INT8 无法满足预设门槛，可以选择更高位宽，但必须保留 INT8 失败证据和比较结果。

---

# 任务二：实现仅处理真实 L32 窗口的 CNN RTL 原型

## 7. 任务二目标

实现第一版可综合 RTL，只执行真实 Vernier `sensor_code` 历史窗口的 Safe/Critical 推理。

本任务不允许加入：

- dummy 窗口；
- real/dummy 仲裁；
- TRNG/PRNG；
- 分段储能控制；
- 电荷整形；
- 根据 CNN 输入动态 early exit；
- 数据相关的可变推理流程。

第一版的目标是证明：

```text
软件浮点模型
    -> bit-true 定点模型
    -> cycle-accurate 模型
    -> 可综合 RTL
```

四者具有可审计的一致关系。

## 8. RTL 宏观架构

Codex 可以决定 MAC 数量、SRAM/register-file 组织和流水线细节，但应遵守以下数据流：

```text
sensor_code sample stream
        -> L32 circular input buffer
        -> inference request scheduler
        -> shared k=5 convolution MAC array
        -> ping-pong/intermediate feature storage
        -> average accumulator
        -> maximum tracker
        -> endpoint register
        -> feature concatenation
        -> binary linear head
        -> logits + Safe/Critical valid
```

建议支持参数化 MAC 并行度，例如 4/8/16 个 MAC 设计点，但第一版只需冻结一个综合可行配置。选择必须由周期、面积和功耗证据支持。

## 9. 任务二实施步骤

### Step 2.1：定义 RTL 接口合同

至少定义：

```text
clock/reset
sensor_code input
sample_valid/sample_ready, or equivalent
inference_request
result_valid
safe_critical_decision
raw logits or logit difference
overflow/error flags
busy/idle
```

必须明确：

- 每 4 ns 传感器采样与 CNN 推理是否解耦；
- L32 窗口如何滑动；
- 推理 stride 如何配置；
- CNN 忙时新样本如何缓存；
- 不允许使用决策点之后的样本；
- 输出对应的 window endpoint index。

不得在没有综合和时序结果前承诺“每 4 ns 完成一个完整 CNN 窗口”。

### Step 2.2：建立周期精确软件模型

在 RTL 前或并行建立 cycle model，记录：

```text
per-layer loop order
weight address
activation address
MAC issue/retire cycle
round/saturate cycle
pooling update cycle
result-valid cycle
```

cycle model 应使用任务一的同一权重包和定点规则，并能生成 RTL 预期 trace。

### Step 2.3：实现卷积数据通路

要求：

- 支持三层 `[1,18,18,18]`、k=5；
- 边界 padding 语义与当前普通 CNN 完全一致；
- 中间激活按任务一合同截断；
- 权重和偏置加载顺序有单元测试；
- MAC accumulator 位宽有静态断言或等价检查；
- 层间 feature storage 不发生读写冲突。

### Step 2.4：实现多统计量池化

三条路径必须同时保留：

```text
global average
maximum
last-position endpoint
```

需要验证：

- average 的整数除法与 bit-true 模型一致；
- maximum 覆盖完整输出长度；
- endpoint 对应最后一个时间位置；
- 拼接顺序与 PyTorch `torch.cat` 顺序一致；
- 分类头权重地址与拼接顺序一致。

### Step 2.5：建立 RTL 验证环境

至少包含：

- 单窗口 directed tests；
- 多窗口连续输入；
- Safe/Critical 边界窗口；
- 0、15、32 等极值码；
- 全平、单峰、末端跳变窗口；
- reset 中断和恢复；
- backpressure 或 buffer 满条件；
- 权重摘要错误的启动拒绝或构建期检查；
- RTL 与 cycle model 逐周期比对；
- RTL 最终 logits 与 bit-true 模型逐窗口相等。

### Step 2.6：综合与初步功耗基线

使用仓库可用工具完成至少一个可重复的综合 smoke flow。报告：

```text
target technology/tool
clock constraint
area or cell count
critical path
maximum frequency
SRAM/register estimate
cycles/window
inferences/second
energy/window, if available
average and peak dynamic power, if available
```

若目标工艺工具暂不可自动运行，Codex 应提供脚本、约束和结构检查，并明确标记未执行项，不得伪造结果。

## 9A. 阶段 8-9：SMIC40LL 编译 ROM 与 500 MHz 流水实现计划

本节是任务二 Step 2.3 至 Step 2.6 的后续执行清单。执行每个步骤前必须重新读取本节，
并把步骤号、UTC 时间和本文件 SHA256 写入同一个任务专用 `rtl/cnn_monitor/runs/<tag>/evidence/plan_reads.log`。
所有 ROM compiler、VCS、Design Compiler 中间文件和报告必须位于该 run 子树，禁止散落到源码目录。

冻结实现口径如下：

```text
发布 MAC 配置：16 lanes
ROM 宏：CNNW384X128，384 words x 128 bits，mux=8
ROM 地址：0..9 Conv1，10..189 Conv2，190..369 Conv3，370..383 零填充
ROM lane 0：Q[7:0]，即 RCF 每行最右侧 8 bit
ROM 正常读控制：CEN=~read_enable, TEN=1, BEN=1, TCEN=1,
                 TA=0, TQ=0, PGEN=0, KEN=1, EMA=3'b010
时序验收：TT/1.10 V/25 C，500 MHz（2.000 ns）；传感器采样周期保持 4 ns
量化包：既有 W8/A8，不重新量化；所有已冻结 validation 指标 delta 必须为零
```

### Step 8.1：建立认证 ROM 内容打包器

要做什么：新增版本化 ROM 配置和 Python 打包器，从任务一认证权重包生成 384 行、每行
128 bit 的 RCF；显式实现三层地址映射、lane 0 最低有效字节、未使用 lane 和尾部地址零填充，
并输出内容 SHA256 与逐层地址清单。代码不得依赖工作目录或未经认证的权重文件。

验证措施：穷举比较 384x16 个字节与任务一张量；检查每个有效权重恰好出现于预期地址/lane；
检查 370..383 和无效 lane 全零；重复生成逐字节一致；篡改权重摘要必须在写 RCF 前失败。

### Step 8.2：建立非 GUI ROM compiler 驱动器

要做什么：新增宿主机非 GUI driver，先验证 compiler 路径、版本、合法 size/mux/view 参数，
再在独立 run 子目录调用 SMIC40LL compiler 生成 simulation、Liberty、LEF/GDS 等可用视图；记录
命令、环境、开始/结束时间和退出状态。driver 必须默认拒绝覆盖已有非空 run。

验证措施：执行只读 preflight 和一次完整生成；日志中不得出现 fatal/error；核对实例名、
384x128、mux=8、RCF 摘要以及预期视图清单，缺少任一综合或仿真必需视图即失败。

### Step 8.3：认证并归档宏交付物

要做什么：为 compiler 输出建立 manifest，记录每个视图的相对路径、字节数和 SHA256；从
Liberty/LEF 抽取 pin、面积、同步读时序和 TT 工作条件，并将生成命令与工具版本一并归档。

验证措施：用独立解析检查宏名和端口集合；确认 Liberty 的 `lc_shell` 转换 `.db` 可由已知
稳定的 DC wrapper `~/.local/bin/dc_shell` 成功 `read_db/report_lib`；核对 TT 最小周期不超过
2.000 ns，且报告不得扩展为全 PVT signoff 声明。

### Step 8.4：实现可综合 ROM 适配器和仿真模型接入

要做什么：新增独立 `cnn_weight_rom` 适配器，以模块化端口注释封装宏控制脚和一拍同步 Q；
综合路径仅实例化 `CNNW384X128`，仿真路径使用 compiler 交付模型。适配器不使用 `function`、
初始化块、`$readmem*` 或不可综合控制逻辑。

验证措施：静态检查综合 RTL 无 `function`/`$readmem`；用 compiler 模型穷举读取 384 个地址，
逐位比较 RCF 期望值，并验证 read disable 时接口保持合同和首个有效 Q 的周期位置。

### Step 8.5：建立带宏的综合入口

要做什么：调整 DC Tcl/driver，在 2.000 ns TT 约束下读入 ROM `.db`，禁止展开回组合 case-ROM，
并用稳定 DC wrapper 运行；报告标准单元和 hard macro 的数量、面积与关键路径。

验证措施：`link/check_design` 无 unresolved reference；`report_cell`/网表中恰有一个
`CNNW384X128` 实例且不被替换为寄存器；约束、库角、wrapper 路径和命令均进入证据文件。

### Step 8.6：完成阶段 8 门禁

要做什么：汇总内容映射、compiler 交付物、仿真读回和综合识别结果，更新 README/基线报告
中的 ROM 结构、物理尺寸、TT 时序以及非 signoff 边界。

验证措施：运行全部 ROM 单元测试和交付物 manifest 复核；只有内容、仿真、Liberty 和 DC
识别四项同时通过才进入阶段 9。

### Step 9.1：先更新周期精确模型和冻结流水 schedule

要做什么：在 Python cycle model 中加入同步 ROM 请求/Q、activation、product、accumulator，
requantize prepare/write，pool operand prefetch，classifier operand/product/accumulate，以及 logit
prepare/commit 的明确事件；冻结 16-lane 周期为 Conv1 640、Conv2 6080、Conv3 6080、Pooling 34、
Classifier 58，总 latency 12892、II 12893。

验证措施：所有任务一 golden tensor/logit 逐元素相等；trace 周期连续且事件计数符合冻结值；
每个 ROM 请求与消费相隔规定拍数；对全部合法控制边界检查固定 latency 且无数据相关分支。

### Step 9.2：重构卷积 ROM、activation、乘法和累加流水

要做什么：修改卷积引擎，使同步 ROM 地址先发射，随后寄存 activation，再寄存乘积并在下一拍
累加；每组用固定 drain 周期完成，保持 position/group/input/tap 顺序、padding 语义和 16-lane
写地址不变。所有新增流水寄存器需有宽度、符号和有效位说明。

验证措施：逐周期比较 RTL 与 cycle trace 的 ROM 地址、activation、product 和 retire 地址；
在全部 golden 与 directed windows 上逐层比较 576 个激活；综合 lint/check_design 无锁存、
多驱动、越界和不可综合结构。

### Step 9.3：拆分卷积 requantize prepare/write

要做什么：把长的 rounding/saturation/bound-check/writeback 路径拆成 prepare 和 write 两拍，
寄存每 lane 的量化结果、有效掩码、目标 bank 和目标地址，确保最后一组/层切换无读写冲突。

验证措施：穷举单元测试 ties-to-even 边界和饱和边界；逐层 tensor 与 W8/A8 golden 完全相等；
断言每个有效输出只写一次、无效 lane 不写、层切换前最后一笔写已提交。

### Step 9.4：流水化 pooling operand 读取

要做什么：在不改变 34-cycle 总预算的前提下预取 conv3 position operand，并流水更新 sum/max/
endpoint；拼接仍严格为 average、maximum、endpoint，各 18 项。

验证措施：对 15 个 golden/directed 窗口逐元素比较 sum、average、maximum、endpoint 和 summary；
专门覆盖 position 0/31 最大值、全零、全 127 和 ties-to-even average；检查恰好扫描 32 个位置。

### Step 9.5：流水化 classifier 与 logit 提交

要做什么：把 summary/weight 读取、乘法和 accumulator 更新分拍，并把 accumulator bound/左移
饱和与最终 difference/decision 分为 prepare、commit；总 classifier 固定 58 cycles，tie 仍为 Safe。

验证措施：逐周期核对 54 个 feature 地址和乘积退休顺序；所有窗口的两个 INT32 logits、33-bit
difference 和 decision 与 bit-true 完全一致；覆盖正负饱和与 exact tie 的定向单元测试。

### Step 9.6：同步顶层、配置、生成器和验证数据合同

要做什么：更新顶层连接、JSON schedule、trace serializer、测试平台里程碑和 README；保留 4/8
lane 地址兼容参数，但发布和本轮验收只使用 16 lanes，不对 feature bank 做额外 SRAM 化。

验证措施：配置 schema/静态合同测试通过；生成文件可重复；全仓综合 RTL 扫描确认无 `function`、
仿真系统任务和隐式 ROM；端口注释覆盖每个功能组及新增信号。

### Step 9.7：执行软件与静态完整回归

要做什么：运行参数认证、ROM pack、cycle model、RTL contract 及新增流水边界测试，并生成一份
集中测试报告；不得读取或重跑 IID/OOD 数据。

验证措施：完整测试集零失败；记录测试数、命令、Python 版本、输入摘要和退出码；再次核对既有
W8/A8 validation 指标文件未被修改且指标摘要与冻结值一致。

### Step 9.8：执行非 smoke RTL 全回归

要做什么：使用 compiler ROM 仿真模型运行所有 8 个 task-one golden、7 个 directed window、
逐周期首窗口 trace、连续采样、同拍 sample/request、最早二次请求、busy 非法请求、reset 中断恢复、
非法 sensor code 和 tie/协议检查；所有产物进入同一 run 子树。

验证措施：VCS 编译零 error；测试平台明确报告每个窗口和协议场景通过；每个内部 tensor、最终
logit、endpoint、固定 12892-cycle latency 和 12893-cycle II 均由 self-checking testbench 验证。

### Step 9.9：执行 500 MHz 宏感知综合与时序分析

要做什么：使用 TT 标准单元库和生成 ROM `.db`，通过稳定 DC wrapper 对 16-lane RTL 进行完整
compile/report，必要时只做局部、可验证的时序修正，不改变数值或固定 schedule。

验证措施：宏实例数为 1；setup slack 在 2.000 ns 约束下非负；无未约束关键寄存器路径、无
unresolved/multidriven/latch；报告总面积、宏面积、标准单元面积、关键路径、功耗口径和吞吐。

### Step 9.10：完成量化零退化与任务二发布报告

要做什么：更新 `RTL_BASELINE_REPORT.md` 和机器可读 summary，列出 ROM 生成复现方法、流水周期、
500 MHz QoR、测试覆盖、限制以及任务二十项验收门槛；禁止重新量化或用 IID/OOD 调参。

验证措施：认证 golden 回归证明整数输出逐位相等，因此相对既有 W8/A8 的 Accuracy 0.987251、
Balanced Accuracy 0.986458、Macro-F1 0.951032、Critical PR-AUC 0.899175、Critical Recall
0.985547、Safe FAR 0.012631 的 delta 全为 0；复核 run manifest、摘要、报告路径和 Git diff，
确认没有散落中间产物或超出任务二范围的设计。

## 10. 任务二验收门槛

必须同时满足：

1. 所有 golden windows 的 RTL logits 与 bit-true 模型一致；
2. RTL 不读取 endpoint 之后的样本；
3. 连续采样条件下不静默丢失 sensor code；
4. 输出携带可追踪 endpoint；
5. 推理 latency 和 initiation interval 固定且被报告；
6. 无输入相关 early exit；
7. 多统计量三条路径全部执行；
8. 综合或 lint/elaboration smoke test 通过；
9. 形成 `RTL_BASELINE_REPORT.md`；
10. 明确给出未来可用于 dummy 窗口的空闲周期预算，但本任务不实现 dummy 调度。

若真实推理占满全部计算周期，应如实报告“无安全空闲 slot”，不得为了制造空闲而降低真实推理正确性。

---

# 任务三：使用手工 dummy 窗口建立 CNN 功耗活动码本

## 11. 任务三目标

在不引入随机性和电荷整形的前提下，验证：

> 同一个 CNN RTL 执行不同、数值合法的 L32 dummy sensor-code 窗口时，是否能够产生稳定、可重复、可调节的内部开关活动和供电功耗差异。

只有证明 CNN 可作为可控功耗执行器，才进入后续真实/dummy 窗口时隙复用。

本任务不要求侧信道攻击成功率实验，也不宣称已经完成防护。

## 12. dummy 窗口约束

所有 dummy 窗口必须：

- 长度固定为 32；
- 每个码值位于 `[0,32]`；
- 使用与真实输入相同的数据表示；
- 执行完整三层卷积、Average、Max、Endpoint 和分类头；
- 分类结果被记录但不用于控制功能逻辑；
- 不修改真实 CNN 权重；
- 不与密钥、中间值或功能芯粒秘密状态相关。

第一版必须是固定手工码本，不加入 PRNG，以保证重复测量。

## 13. 手工窗口族

至少构造以下窗口族，每族包含多个幅度和转移密度变体：

### 13.1 Mean-dominant

用于改变窗口整体水平和 Average 路径：

```text
constant low/mid/high
slow ramp up
slow ramp down
wide plateau
```

### 13.2 Peak-dominant

用于激活 Maximum 路径：

```text
single narrow peak
double peak
short burst
peak-position sweep
```

### 13.3 Endpoint-dominant

用于改变最后位置特征和分类头：

```text
flat then final rise
flat then final fall
last-4-sample ramp
same prefix, different endpoint
```

### 13.4 Mixed-statistic

用于同时改变三条路径：

```text
random walk with bounded slope
ramp + peak + recovery
double plateau with endpoint transition
alternating low/high with bounded amplitude
```

### 13.5 控制组

至少包括：

```text
all 15
all 0
all 32
repeated real Safe window
repeated real Critical window
```

人工窗口生成器必须输出 manifest，记录 pattern family、参数和 SHA256。

## 14. 任务三实施步骤

### Step 3.1：建立活动测量接口

优先使用 RTL/门级可获得的 VCD、SAIF 或等价开关活动文件。至少区分：

```text
convolution MAC datapath
weight/intermediate storage
average accumulator
maximum tracker
endpoint registers
classifier
control/address generation
```

如果暂时没有可信的工艺功耗模型，可先报告归一化 toggle count 和合成估算功耗，但必须明确它不是最终硅功耗。

### Step 3.2：固定测量协议

每种窗口应在完全相同的条件下运行：

```text
same reset sequence
same clock count
same idle preamble
same inference start cycle
same postamble
same weights
same RTL configuration
```

真实窗口和 dummy 窗口都必须执行相同周期数。不得通过跳过分类头或池化路径来人为增加差异。

### Step 3.3：生成活动与功耗指标

每个窗口至少输出：

```text
total toggle count
toggle count by module
average dynamic power estimate
peak-cycle activity or peak power estimate
energy/window
cycle-level activity waveform
latency
logits/decision
overflow/error status
```

在工具允许时，增加：

```text
frequency spectrum of cycle-level activity
MAC operand Hamming distance
SRAM address/data switching
Average/Max/Endpoint contribution
```

### Step 3.4：建立第一版活动码本

输出机器可读表：

```text
pattern_id
family
parameters
input_sha256
total_energy
average_power
peak_power
peak_cycle
module_toggle_vector
frequency_summary
validity_status
```

根据测量结果而不是输入外观，将模式聚类或分档为：

```text
low activity
medium activity
high activity
peak-heavy
average-heavy
endpoint-heavy
```

Codex 可以决定聚类方法；第一版允许使用简单阈值和人工检查，但必须保存原始指标。

### Step 3.5：检查对真实检测路径的影响

本任务还没有 real/dummy 时隙仲裁，因此只需验证：

- 加入 dummy 测量基础设施不改变真实窗口 RTL 输出；
- 活动计数器或 dump 逻辑不进入综合功能路径，或能通过参数关闭；
- 所有 dummy 窗口无溢出和非法状态；
- 相同 dummy 窗口重复运行得到一致结果；
- 不同窗口之间的活动差异明显高于测量噪声或工具不确定度。

若仓库已有 Vernier/PDN 联合仿真接口，可选做少量 co-simulation，观察 dummy CNN 活动对传感器码的影响；但这不是任务三完成的前置条件。

## 15. 任务三验收门槛

必须形成 `CNN_ACTIVITY_CODEBOOK_REPORT.md`，并回答：

1. 是否存在至少三个可重复的活动/能量档位；
2. 不同窗口族主要激活哪些模块；
3. 峰值活动是否集中在固定周期；
4. 哪些窗口会造成不安全的峰值或过高能量；
5. 哪些窗口适合作为后续 dummy 候选；
6. 真实窗口与 dummy 窗口是否执行相同完整路径；
7. 计算活动差异是否足够支持后续时隙复用研究。

建议的继续条件：

```text
至少 3 个稳定活动档位
AND 每个档位有多个不同输入模式
AND 重复运行方差显著小于档位间差异
AND 无定点溢出
AND 不改变真实窗口结果
```

如果不同 dummy 窗口的功耗/活动几乎相同，必须停止进入随机扰动阶段，优先调查：

- 数据通路是否被过度时钟门控；
- 权重广播是否主导总功耗；
- 输入/激活编码是否压低翻转差异；
- MAC 并行度是否掩盖模式差异；
- 中间 SRAM 活动是否固定并占主导；
- 是否需要增加合法的计算模式控制，而不是简单增加随机窗口。

不得在证据不足时直接宣称 CNN 可有效掩盖密码功耗。

---

# 16. 建议目录与产物

Codex 应先检查仓库现有目录约定，再决定最终放置位置。推荐的逻辑组织如下，可按现有风格调整：

```text
tcn_detection/
  fixed_point/
    export_model.py
    bittrue_cnn.py
    quantization.py
    configs/
    tests/
  hardware_ref/
    cycle_model.py
    golden/
  activity/
    generate_dummy_windows.py
    characterize_activity.py
    configs/
    tests/

rtl/
  cnn_monitor/
    rtl/
    tb/
    scripts/
    constraints/

reports/
  cnn_fixed_point_phase1/
  cnn_rtl_baseline_phase1/
  cnn_activity_codebook_phase1/
```

如果仓库已有统一的 `runs/`、`reports/` 或硬件目录，优先沿用，不要创建重复体系。

必须提交到 Git 的内容：

- 源码；
- 小型配置；
- 小型 golden vectors；
- 测试；
- Markdown 报告；
- 机器可读摘要；
- 可复现命令；
- 工具和输入摘要。

不得提交：

- checkpoint；
- 大型中间 tensor；
- VCD/FSDB；
- 综合数据库；
- 工具缓存；
- 大型功耗波形；
- 可由脚本重新生成的临时文件。

---

# 17. 最终阶段报告

三项任务完成后，新增一个总报告，至少包含：

```text
model/checkpoint provenance
final fixed-point formats
validation metric deltas
RTL architecture and MAC parallelism
cycles/window and maximum sustainable inference rate
area/timing/power baseline
handcrafted window activity codebook
accepted/rejected dummy patterns
known limitations
next-stage recommendation
```

最终只能给出以下两种结论之一。

## 结论 A：允许进入窗口时隙复用

条件：

- 定点模型通过门槛；
- RTL 与 bit-true 一致；
- 真实推理存在明确的可调度空闲预算，或硬件可在不影响真实 deadline 的情况下提供 dummy slot；
- dummy 窗口能形成多个稳定活动档位；
- 没有不可接受的峰值或可靠性风险。

下一阶段再规划：

```text
real/dummy 双窗口缓冲
固定长度 slot 仲裁
真实窗口最高优先级
快速硬保护
dummy 结果丢弃
```

## 结论 B：暂不进入计算复用

触发条件包括：

- 定点退化过大；
- RTL 无法满足真实监测吞吐；
- 无空闲 slot；
- dummy 窗口活动差异不足；
- 峰值功耗过高；
- 功耗主要由固定存储访问支配，输入模式不可调。

此时应保留失败证据，回到定点格式、数据通路、存储组织或 MAC 并行度优化，不得跨步进入电荷整形和随机扰动。

---

# 18. 本计划明确不包含的工作

以下内容留到后续独立计划：

- real/dummy 窗口时隙调度器的正式实现；
- 快速硬保护和安全仲裁器；
- 分段储能电容的 PRECHARGE/ISOLATE/ASSIST 控制；
- 计算活动与电荷释放的联合调度；
- TRNG/PRNG；
- dummy pattern 随机化；
- 电容段随机选择；
- 随机目标电流包络；
- 密码功能芯粒集成；
- TVLA、CPA、模板攻击和深度学习侧信道评估；
- 包含防护器自身活动的闭环 CNN 数据集重建。

这些工作只有在本计划的三项任务全部完成并通过阶段门后才允许启动。
