# FTC Delay-Code Boundary Refinement

## Decision

**3-bit Boundary-Centered Mapping = NO-GO**

## Scope

- 保持 tap29 sensor、真实 XOR/DFF、3-bit、7-MUX 和 0.80--1.10 V 不变。
- 只执行 3 个 sizing、最小 calibration Gate 和 3 个 baseline 的 feasibility Gate。
- 不重跑旧 42 个 acceptance-window 或旧 54 个 static-calibration probes。

## Candidate Attempts

| Candidate | Calibration | Feasibility | Taps |
|---|---|---|---|
| primary | NO-GO | NOT_RUN | `14,15,17,21,25,30,31,32` |
| fallback | NO-GO | NOT_RUN | `14,15,18,22,26,31,32,33` |

## Gate Evidence

- primary / 0.80 V: Q(k-1..k+2) is not [1,0,0,0]
- primary / 0.95 V: Q(k-1..k+2) is not [1,0,0,0]
- fallback / 0.80 V: Q(k-1..k+2) is not [1,0,0,0]
- fallback / 1.05 V: Q(k-1..k+2) is not [1,0,0,0]

## Next Step

- stop; do not add monitor RTL, expand bit-width, or enter PVT
