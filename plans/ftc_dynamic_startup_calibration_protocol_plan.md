# FTC 动态启动校准协议：Codex 逐步骤执行计划

## 0. 任务定位

本计划对应当前总体路线中的：

```text
F. 动态启动校准协议
```

它承接已经完成并正式 GO 的上一步：

```text
b1f511f57812b07c7d243413af456930ae197f8b
feat(ftc): validate two-stage real-DFF calibration
```

上一步已经证明：

```text
Two-Stage Real-DFF Hierarchical Self-Calibration = GO
```

并得到三个锚点的静态真实 DFF（真实 D 触发器）锁定参考：

```text
1.10 V : M_transition=4, M_fine=3, F_lock=4
0.95 V : M_transition=6, M_fine=5, F_lock=1
0.80 V : M