# M1 programmable detection-margin safe configuration — M1-T STA evidence closure

## Gate decision

**GO (M1-T PASS)** — M1-T is a report-only closure of the committed mapped implementation. RTL, frozen H0, the six frozen calibration RTL files, FTC_SENSOR, M0/M0-E data, the 400 MHz / 2.5 ns contract, mapped netlist, SDC, and SDF are unchanged.

## Formal STA provenance

- Required baseline commit: `e3f8ba2ae629e7d0d4b75355eca548e9cad64391`.
- Library: `ss_typical_max_0p99v_125c`; clock: `cal_clk`, 2.500000 ns; uncertainty: setup 0.050000 ns, hold 0.020000 ns.
- Driver: `delay_chain/ftc/controller/m1_detection_margin/synthesis/scripts/report_m1_t_mapped_sta.tcl`. It performs `read_verilog`, `link`, `read_sdc`, and reporting only; no elaboration, compile, netlist write, RTL/SVA, gate simulation, HSPICE, XA, RF6/RF8/RF9C/RF9D, or calibration regression was run.
- The formal report index and SHA-256 values are in `delay_chain/ftc/controller/m1_detection_margin/timing/M1_T_TIMING_CLASSIFICATION.json`. Every path below is a first/worst path from its named, committed `.rpt`.
- At this mapped top-wire-load stage every printed net `Incr` on the listed worst paths is 0.000000 ns. `内部数据路径` therefore means the reported cell arc + pin arc path total, not post-layout extracted RC.

## Worst path classes (ns)

| Class / check | Startpoint → endpoint | Type | 内部数据路径 | 外部 delay（DC 符号） | clock uncertainty | library check | required | slack |
| --- | --- | --- | ---: | --- | ---: | ---: | ---: | ---: |
| I→R setup | `margin_sel_i[1]` → `m_det_q_reg[2]` | max | 1.868971 | in +0.500000; out +0.000000 | -0.050000 | -0.079861 | 2.370139 | +0.001168 |
| I→R hold | `margin_select_valid_i` → `margin_cfg_valid_q_reg` | min | 0.074407 | in +0.000000; out +0.000000 | +0.020000 | +0.016564 | 0.036564 | +0.037843 |
| R→R setup | `state_q_reg[2]` → `det_medium_therm_q_reg[15]` | max | 2.360888 | in +0.000000; out +0.000000 | -0.050000 | -0.082106 | 2.367894 | +0.007005 |
| R→R hold | `f_det_q_reg[1]` → `f_det_q_reg[1]` | min | 0.369713 | in +0.000000; out +0.000000 | +0.020000 | +0.037559 | 0.057559 | +0.312155 |
| R→O setup | `state_q_reg[2]` → `det_takeover_ready_o` | max | 0.798614 | in +0.000000; out -0.400000 | -0.050000 | +0.000000 | 2.050000 | +1.251386 |
| R→O hold | `margin_protocol_error_q_reg` → `margin_protocol_error_o` | min | 0.275003 | in +0.000000; out +0.000000 | +0.020000 | +0.000000 | 0.020000 | +0.255003 |


The global worst setup is `margin_sel_i[1] → m_det_q_reg[2]`, an **input→register** path: 2.368971 ns arrival = 0.500000 ns explicit input budget + 1.868971 ns mapped internal cell/pin path. Its required time is 2.500000 − 0.050000 uncertainty − 0.079861 setup = 2.370139 ns, leaving +0.001168 ns. Therefore the +1.168 ps value is not an internal mapper→target or state-register path.

The global worst hold is `margin_select_valid_i → margin_cfg_valid_q_reg`, also input→register: 0.074407 ns internal arrival + 0.000000 input budget, with +0.020000 ns hold uncertainty and +0.016564 ns library hold, leaving +0.037843 ns.

The independently reported worst **internal register→register** setup path is `state_q_reg[2] → det_medium_therm_q_reg[15]`: 2.360888 ns entirely internal (including launch clock-to-Q), zero I/O budget, −0.050000 ns uncertainty, −0.082106 ns setup, and +0.007005 ns slack. It is positive but explicitly retained as a small residual margin; it is not the +1.168 ps global I/O path and M1-T does not relax the 400 MHz contract.

## Targeted M1-T path families (ns)

| Targeted family | Startpoint → endpoint | Type | 内部数据路径 | 外部 delay（DC 符号） | uncertainty | library check | required | slack |
| --- | --- | --- | ---: | --- | ---: | ---: | ---: | ---: |
| selection→state | `margin_sel_i[1]` → `state_q_reg[2]` | max | 1.530383 | in +0.500000; out +0.000000 | -0.050000 | -0.058001 | 2.391999 | +0.361615 |
| selection→target | `margin_sel_i[1]` → `target_medium_therm_q_reg[5]` | max | 1.846430 | in +0.500000; out +0.000000 | -0.050000 | -0.079857 | 2.370143 | +0.023713 |
| cal code→mapper→target | `cal_medium_code_snapshot_i[2]` → `target_fine_therm_q_reg[3]` | max | 2.049216 | in +0.300000; out +0.000000 | -0.050000 | -0.068499 | 2.381501 | +0.032285 |
| config→det register setup | `state_q_reg[2]` → `det_medium_therm_q_reg[15]` | max | 2.360888 | in +0.000000; out +0.000000 | -0.050000 | -0.082106 | 2.367894 | +0.007005 |
| config→det register hold | `target_fine_therm_q_reg[9]` → `det_fine_therm_q_reg[9]` | min | 0.456592 | in +0.000000; out +0.000000 | +0.020000 | +0.040590 | 0.060590 | +0.396001 |
| config→det output setup | `state_q_reg[2]` → `det_takeover_ready_o` | max | 0.798614 | in +0.000000; out -0.400000 | -0.050000 | +0.000000 | 2.050000 | +1.251386 |
| config→det output hold | `state_q_reg[3]` → `det_takeover_ready_o` | min | 0.408567 | in +0.000000; out +0.000000 | +0.020000 | +0.000000 | 0.020000 | +0.388567 |
| det register→output setup | `det_medium_therm_q_reg[15]` → `det_medium_therm_o[15]` | max | 0.292289 | in +0.000000; out -0.500000 | -0.050000 | +0.000000 | 1.950000 | +1.657711 |
| det register→output hold | `det_medium_therm_q_reg[15]` → `det_medium_therm_o[15]` | min | 0.275023 | in +0.000000; out +0.000000 | +0.020000 | +0.000000 | 0.020000 | +0.255023 |


`margin_sel_i*` / `margin_select_valid_i` reports are separated from the code-snapshot mapper reports. The latter intentionally starts at `cal_medium_code_snapshot_i*` / `cal_fine_code_snapshot_i*`: these are the mapper's lookup keys; raw calibration thermometer snapshots are preload data, not codebook-selection sources.

For detector outputs, DC displays the SDC output budget as a negative required-time adjustment: `det_takeover_ready_o` uses −0.400000 ns, while `det_medium_therm_o[15]` uses −0.500000 ns. The two config→det-output reports and the two det-register→output reports retain both views so the output budget is never mistaken for internal sequential delay.

## Functional and frozen-boundary evidence

- Existing M1-5 RTL/SVA evidence remains PASS; no RTL changed in M1-T.
- Existing M1-7 mapped+SDF evidence remains PASS with timing checks enabled. It applies to the same byte-identified mapped netlist/SDF; no M1-T mapped+SDF rerun was necessary or performed.
- HSPICE reruns: 0; XA reruns: 0; RF6/RF8/RF9C/RF9D reruns: 0; complete calibration regressions: 0.
- Frozen H0 and the six frozen calibration RTL files remain covered by the existing M1-8 frozen manifest; M1-T did not modify any of them.

## Downstream handoff

Proceed only to T0 to define the transient threat and detection timing contract. M1 remains configuration-only: sensor reset is high, S_CLK remains low, and it does not implement a detection probe, Q decision, or alarm policy.
