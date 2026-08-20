# FTC Calibration Controller Functional Contract

This contract is a read-only translation of accepted exact-path evidence. No historical runner or HSPICE simulation was executed.

## Decision

**Controller Functional Contract = GO**

## Frozen Nominal Outcomes

| VDD | Coarse boundary | Selected M | Fine boundary | Final | Operations |
|---:|---:|---:|---:|---|---:|
| 0.80 V | M9 | M7 | F5 | M7/F6 | 45 |
| 0.95 V | M6 | M4 | F5 | M4/F6 | 36 |
| 1.10 V | M4 | M2 | F8 | M2/F9 | 36 |

The controller accepts a coarse boundary only after two independent stable-low probes, performs exactly two adjacent backoff updates, stops fine search at the first non-stable-high result, and requires stable-low guard and hold probes before lock.
