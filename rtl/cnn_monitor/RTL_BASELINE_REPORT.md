# CNN RTL Baseline Report

This report is generated from the checked-in RTL, VCS regression log, and Design Compiler text reports. Missing artifacts remain explicit.

## Functional evidence

- Task-one binding remains W8/A8; no re-quantization was performed.
- VCS regression target: `CNN_MONITOR_REGRESSION_PASS vectors=15 trace_cycles=12892`.
- Fixed release latency: 12,892 cycles; initiation interval: 12,893 cycles.
- Activity-annotated power is not claimed by this baseline; DC reports are vectorless unless a future run supplies >=90% annotation coverage.

## SMIC40LL compiled ROM evidence

- Macro: `CNNW384X128`, 384 words x 128 bits, mux 8.
- Physical size: 394.535 x 37.250 um; area 14,696.428750 um2.
- TT/1.10 V/25 C, `EMA=010`, `KEN=1`: minimum cycle 1.8985 ns,
  CLK-to-Q 1.0792 ns, address setup/hold 0.2489/0.1428 ns.
- At the compiler's 500 MHz, 100% read activity setting: 8.8769 mA average
  read current and 51.4822 mA peak current.
- DC adapter gate contains exactly one `CNNW384X128` hard macro and four
  standard cells, total area 14,703.371311 um2. It contains no inferred ROM
  register array.
- These numbers are a TT baseline only. Slow-corner probes exceed 2 ns and no
  full-PVT signoff claim is made.

## Synthesis points

| Point | Status | Area | Leaf cells | Critical path (ns) | WNS (ns) | Target (MHz) | Est. Fmax (MHz) | Avg dyn. (mW) | Energy/window (nJ) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| lanes4_period4ns | complete | 207594.274 | 127894 | 3.750 | 0.000 | 250.000 | 266.667 | 21.329 | 2614.935 |
| lanes8_period4ns | incomplete | - | - | - | - | 250.000 | - | - | - |

## Limitations

- Average dynamic power and energy/window are vectorless estimates; peak dynamic power is unavailable and is not claimed.
- Hold violations and high-fanout warnings are reported verbatim in each point directory; they are not silently waived.
- No dummy-window scheduler or activity-codebook logic is included in this task-two baseline.
