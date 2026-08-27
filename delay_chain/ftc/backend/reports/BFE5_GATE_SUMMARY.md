# B-FE5 ARCH0 backend gate summary

本轮按执行计划完成 P0、RTL0、RTL1、RTL2、RTL3；所有中间文件均集中在本目录下的 `p0/rtl0/rtl1/rtl2/rtl3`。

| 阶段 | 门禁 | 验证证据 |
|---|---|---|
| P0 | `BFE5_P0_DC_CAPTURE_CELL_PREFLIGHT_PASS` | `p0/p0_structure_summary.rpt`：真实 `LATQ_X0P5M_A9TR40`/`DFFRPQ_X0P5M_A9TR40` 各 1，Q→D 直连 |
| RTL0 | `BFE5_RTL0_CAPTURE_M_BACKEND_PASS` | `rtl0/vcs_run.log` 完成全零、单 bit、全一、32 个确定性随机向量；`rtl0/structure_summary.rpt`：30+30、直连、9 bit |
| RTL1 | `BFE5_RTL1_STARTUP_CALIBRATION_PASS` | `rtl1/vcs_run.log` 完成 invalid、4+4 均值、提前 lock、lock 后冻结；DC 报告完整 |
| RTL2 | `BFE5_RTL2_MINIMAL_DETECTOR_PASS` | `rtl2/vcs_run.log` 完成 rise/fall 参考与 margin、绝对差边界、严格大于、invalid/cal_mode、sticky/reset |
| RTL3 | `BFE5_RTL3_ARCH0_BACKEND_DC_PASS`（结构/映射门禁） | `rtl3/structure_summary.rpt`：12 个规定顶层端口、30+30、直连、ARCH1 未实现；VCS 复跑 RTL2 全回归；400 MHz 时序实测最差 slack=`-6.16 ns`，按计划仅记录原因，不擅自加入 pipeline/复杂 adder tree |

各阶段 DC 均保存 `check_design_precompile/postcompile`、reference/cell/resources/area/qor/timing 及 mapped Verilog/DDC/SDC。综合脚本只使用普通 `compile`、400 MHz `clk_probe` 约束，并仅保护 capture bank 与 60 个指定 sequential cells。网表未发现 GTECH/SEQGEN、乘法器或除法器；DC 日志中的 UPF-581 来自当前 Liberty 逻辑视图没有暴露 VDD logical pin，未形成 unresolved reference。

额外回归：`python3 -m unittest delay_chain.ftc.tests.test_bfe0_contract delay_chain.ftc.tests.test_bfe2_contract`，6 tests 全部通过。

## Timing optimization stage

新增固定流水：`P1 pair_sum`、`P2 level2_sum`、`P3 M_FF`、`P4a operand/方向与低半字`、`P4b 高半字 delta`。capture 后第 4 个 `clk_probe` 边沿消费事件，`droop_alarm` 随后按流水结果输出，sticky 再锁存一拍。最终真实 DC 结果：setup WNS=`+0.0523701 ns`、setup violating paths=`0`、hold violation=`0`、max-transition/max-cap violation=`0`，总 cell area=`2905.358401`。

证据目录：`reports/timing_opt/` 与 `netlist/timing_opt/`；综合脚本为 `backend/synthesis/run_timing_opt.tcl`。
