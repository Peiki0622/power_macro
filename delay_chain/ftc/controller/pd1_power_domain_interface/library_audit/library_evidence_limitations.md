# PD1 库证据限制

远端同工艺 `sc9mc_pmk_rvt_c40_c50` PMK Liberty 库可读，且包含明确 `is_level_shifter` 和 `is_isolation_cell` 标记。`A2LVLUO_X1M_A9TR40`、`A2LVLU_X1M_A9TR40` 与 `LVLUO_X1M_A9TR40` 提供多电源 pin、rise/fall timing/transition 表和 `power_down_function`。

这些候选公布的输入/输出电压范围均为 0.99-1.21 V，不能覆盖冻结的 0.80 V `VDD_MONITORED` 场景；`power_down_function` 也是逻辑可用性表达式，不是掉电注入电流或反向供电上限。故候选已登记但不合格，不能用于声明 PD1 物理实现或掉电安全已闭合。
