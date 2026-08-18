# SMIC40LL Fine-Driver Strength Probe

## Fixed Endpoint

- `NOR2_X4A_A9TL40`, signal `A`, control `B`, high-load control `0`.
- `M=15`, `F=8`, `K=8`, `VDD=0.80 V`; original high/low limits remain `0.72 V` / `0.08 V`.
- Existing X0P7M baseline is read-only and was not rerun.

## Measurements

| Driver | CDL total width (um) | Output high (V) | High/VDD | 10%-90% rise (ps) | Result |
|---|---:|---:|---:|---:|---|
| `BUF_X0P7M_A9TL40` (baseline) | 0.780 | 0.717393004 | 0.8967412549999999 | 396.4726550000003 | retained failure |
| `BUF_X0P8M_A9TL40` | 0.870 | 0.7595726592 | 0.949465824 | 344.2255810000001 | PASS |
| `BUF_X1M_A9TL40` | 0.985 | 0.787057934 | 0.9838224175 | 295.63245099999983 | PASS |
| `BUF_X1P4M_A9TL40` | 1.320 | 0.7994943368 | 0.999367921 | 205.76342599999992 | PASS |
| `BUF_X2M_A9TL40` | 1.830 | 0.7999924926 | 0.99999061575 | 153.46990299999987 | PASS |

## Decision

- Endpoint result: `IMPROVED_AT_FIXED_ENDPOINT`.
- Comparison rows: `4` of `4` driver entries (X0P8M retained, X1M/X1P4M/X2M newly measured).
- This probe does not rerank loads, derive K, or establish Fine Stage GO; any passing driver requires a separately authorized full re-evaluation.
- Historical medium scenarios rerun: `0`; historical runner invocations: `0`; bypass/configuration/sensor/XOR/DFF/calibration/PVT/RTL/power/area/layout scenarios: `0`.
