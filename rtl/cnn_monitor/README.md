# Real-Window `multistat_w18_k5` CNN RTL

This block implements only real L32 Vernier sensor-code inference. It contains
no dummy input, random scheduler, charge shaping, early exit, or data-dependent
control path. The numeric source of truth is the task-one W8/A8 package bound
by `config/cnn_rtl_config_v1.json`.

## Clock and Integration Boundary

`sample_valid` is synchronous to `clk`. An integration wrapper must perform any
CDC from the Vernier backend's capture domain before driving this block. The
release synthesis target is 500 MHz at TT/1.10 V/25 C. Samples may arrive every 4 ns while inference
is busy because acquisition and computation own separate storage.

## Compiled Weight ROM

Convolution weights reside in one SMIC40LL `CNNW384X128` synchronous ROM. The
authenticated RCF maps Conv1 to addresses 0..9, Conv2 to 10..189, Conv3 to
190..369, and forces 370..383 to zero. Lane zero is `Q[7:0]`. Normal controls
are `EMA=010`, `KEN=1`, `TEN=BEN=TCEN=1`, `TA=TQ=0`, `PGEN=0`, and
`CEN=~read_enable`.

Use `generate_smic40ll_rom_content.py`, `run_smic40ll_rom_compiler.sh`, and
`run_smic40ll_rom_lib.sh` in that order. Every generated view remains under a
single `runs/<tag>` directory. The compiler model has a VCS W-2024.09 public-Q
compatibility defect; its internal synchronous Q_ node is exhaustively checked
for all 384 addresses, while the physical Q pin is independently proven by
Liberty `.db` linking and mapped-netlist inspection.

## Port Contract

| Port | Direction | Width | Contract |
| --- | --- | ---: | --- |
| `clk` | input | 1 | Synchronous compute and sample-stream clock. |
| `reset` | input | 1 | Active-high asynchronous reset. |
| `sensor_code` | input | 6 | Legal Vernier code is 0 through 32. |
| `sample_valid` | input | 1 | Requests one sensor transfer. |
| `sample_ready` | output | 1 | High outside reset for a legal input code. |
| `inference_request` | input | 1 | Requests an atomic snapshot of the newest complete L32 window. |
| `inference_ready` | output | 1 | High only when idle and at least 32 samples exist. |
| `busy` | output | 1 | High from accepted request through the fixed compute schedule. |
| `result_valid` | output | 1 | One-cycle pulse when both logits and endpoint are committed. |
| `safe_critical_decision` | output | 1 | Zero is Safe; one is Critical. Ties are Safe. |
| `safe_logit` | output | 32 | Signed INT32 Safe logit at scale 2^-26. |
| `critical_logit` | output | 32 | Signed INT32 Critical logit at scale 2^-26. |
| `logit_difference` | output | 33 | Signed Critical-minus-Safe difference without 32-bit subtraction overflow. |
| `result_endpoint_index` | output | 32 | Index of the newest sample in the snapshotted window. |
| `numeric_overflow` | output | 1 | Sticky assertion failure for an accumulator contract violation. |
| `protocol_error` | output | 1 | Sticky invalid-code or rejected-request indication. |

`sample_ready` never depends on `busy`. A request made while
`inference_ready=0` is rejected and sets `protocol_error`; there is no hidden
queue. Once a request is accepted, the compute engine reads only the snapshot,
so later samples cannot alter its result. If a legal sample and request are both
accepted on one edge while the circular buffer is full, that new sample is the
snapshot endpoint.

## Fixed Schedule

The release schedule is fixed and contains no input-dependent branch:

```text
Conv1       640 cycles  = 32 positions x 2 groups x (5 issues + 5 overhead)
Conv2      6080 cycles  = 32 positions x 2 groups x (90 issues + 5 overhead)
Conv3      6080 cycles  = 32 positions x 2 groups x (90 issues + 5 overhead)
Pooling      34 cycles  = init + 32 registered-operand updates + finalize
Classifier   58 cycles  = bias + 54 product issues + drain + prepare + commit
Total      12892 cycles
II         12893 cycles
```

The five convolution overhead cycles are bias initialization, two fixed
ROM/product drain cycles, requantize prepare, and registered bank write. The
release clock constraint is 2.000 ns. The delivered compiler model is run at a
4 ns functional-simulation period because its legacy timing checker hard-codes
a 3 ns minimum model period; Liberty/DB timing, not that unit-delay model, is
the evidence for the 2.000 ns synthesis target.

At maximum sustained real-request rate there is no safe idle slot. For a real
request interval of `R` clocks, a future scheduler may consider at most
`max(0, R-II)` clocks idle, where `II` is the checked-in release initiation
interval. This module does not implement that scheduler.
