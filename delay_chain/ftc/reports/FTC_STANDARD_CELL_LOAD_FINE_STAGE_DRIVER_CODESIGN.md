# FTC Standard-Cell Load Fine-Stage Driver Co-Design

## Decision

**Fine Driver Co-Design = NO-GO**

## Boundary

- Fixed load: `NOR2_X4A_A9TL40__signal_A`, signal `A`, control `B`, high-load control `0`.
- Frozen medium network: `N=16`, `BUF_X0P7M_A9TL40`, and `MXT2_X0P5M_A9TL40`.
- Original logic limits remain `output_high >= 0.90*VDD` and `output_low <= 0.10*VDD`.
- The historical endpoint probe is read-only evidence; endpoint PASS is not Fine Stage GO.

## Historical Endpoint Probe

Fixed endpoint: `M=15`, `F=8`, `K=8`, `VDD=0.80 V`.  The original high-level limit is `0.72 V`.

| Driver | Output high (V) | High/VDD | Rise (ps) | Delta high vs X0P7 (V) | Delta rise vs X0P7 (ps) | Endpoint result |
|---|---:|---:|---:|---:|---:|---|
| `BUF_X0P7M_A9TL40` (read-only baseline) | 0.717393004 | 0.896741255 | 396.473 | 0.000000000 | 0.000 | FAIL |
| `BUF_X0P8M_A9TL40` | 0.759572659 | 0.949465824 | 344.226 | 0.042179655 | -52.247 | PASS |
| `BUF_X1M_A9TL40` | 0.787057934 | 0.9838224175 | 295.632 | 0.069664930 | -100.840 | PASS |
| `BUF_X1P4M_A9TL40` | 0.799494337 | 0.999367921 | 205.763 | 0.082101333 | -190.709 | PASS |
| `BUF_X2M_A9TL40` | 0.799992493 | 0.99999061575 | 153.470 | 0.082599489 | -243.003 | PASS |

## Full Co-Design Results

| Driver | Status | K | Reasons |
|---|---|---:|---|
| `BUF_X0P8M_A9TL40` | NO-GO | 10 | driver_waveform_high_fail |
| `BUF_X1M_A9TL40` | NO-GO | 13 | driver_waveform_high_fail |
| `BUF_X1P4M_A9TL40` | NO-GO | 21 | driver_waveform_high_fail; driver_waveform_low_fail |
| `BUF_X2M_A9TL40` | NO-GO | 30 | driver_waveform_high_fail; driver_waveform_low_fail |

## Measured K And Critical Endpoint

| Driver | K | FineRange_8 at 1.10/0.95/0.80 V (ps) | Deep 0.80 V high/low (V) | Result |
|---|---:|---|---|---|
| `BUF_X0P8M_A9TL40` | 10 | 51.218/55.592/56.323 | 0.6856528515/0.0241139336 | False |
| `BUF_X1M_A9TL40` | 13 | 41.985/45.205/44.409 | 0.6343493771/0.04968455244 | False |
| `BUF_X1P4M_A9TL40` | 21 | 26.712/27.200/26.741 | 0.5702537681/0.08329650319 | False |
| `BUF_X2M_A9TL40` | 30 | 17.646/17.761/18.079 | 0.5417883611/0.117377286 | False |

## Coupled Gate Evidence

| Driver | Fine max at 1.10/0.95 V (ps) | Coupled medium min at 1.10/0.95 V (ps) | 0.80 V conclusion |
|---|---|---|---|
| `BUF_X0P8M_A9TL40` | 6.944/8.390 | 10.016/13.578 | deep waveform invalid; coverage/resolution gate not claimable |
| `BUF_X1M_A9TL40` | 5.753/6.893 | 10.322/13.171 | deep waveform invalid; coverage/resolution gate not claimable |
| `BUF_X1P4M_A9TL40` | 4.168/4.952 | 10.186/13.223 | deep waveform invalid; coverage/resolution gate not claimable |
| `BUF_X2M_A9TL40` | 3.067/3.586 | 10.027/13.150 | deep waveform invalid; coverage/resolution gate not claimable |

## Interpretation

- The historical X0P7M failure was a weak-driver waveform failure, not evidence that the fixed NOR2 load lacks range.  The endpoint probe confirms that stronger buffers improve that one endpoint, but it does not characterize the larger K required after the driver changes.
- Each candidate re-derived K from its own measured `FineRange_8`; the strongest tested driver reduces load sensitivity and therefore needs the largest K.
- Every derived K remains within 64, but all four final deep 0.80 V endpoints violate the original high-level requirement; X2 also violates the low-level requirement.  Therefore a coverage or resolution claim at that voltage is deliberately not made.
- A complete GO would require valid 0.80 V deep coverage in addition to monotonicity, 0.90/0.10 logic levels, K<=64, and fine resolution below the coupled medium step.  No `future_bypass_interface.json` is emitted because no driver passed all gates.

## Evidence Accounting

- Final-contract HSPICE scenarios: `378`; reused matching final-contract scenarios: `0`.
- Task-total HSPICE scenarios: `756`; superseded non-final-contract scenarios: `378`.
- The superseded revision is retained for audit only and excluded from the final decision because its scenario identity omitted `logic_low_max_ratio`; the final revision reran the complete bounded matrix with that field present.
- Historical medium/load-sweep/driver-probe scenarios rerun: `0/0/0`.
- No bypass, configuration skip, sensor, XOR, DFF, calibration, droop, PVT, RTL, power, area, or layout scenarios were created.
- A Fine Stage GO only covers this standard-cell fine stage and one-medium-step coverage; it is not a complete FTC droop-detection macro GO.

## Logic-Level Readback Audit

The final decision uses only revision `r2`.  Its `378` raw HSPICE scenarios
were checked twice without rerunning HSPICE: first by reparsing every retained
measurement file through the production reader and classifier, then by an
independent CSV readback and direct implementation of the frozen electrical
rule.  Both checks matched every public analysis row exactly.  In particular,
each final scenario manifest records `logic_high_min_ratio=0.90` and
`logic_low_max_ratio=0.10`; no X0P7 result, relaxed 0.88 rule, or prior
revision is reused in the decision.

The deck launches the input at `1.0 ns` with a `6.0 ns` period.  It reads
`out_logic_high` at `2.5 ns` and `out_logic_low` at `5.5 ns`, matching the
frozen measurement contract.  At `VDD=0.80 V`, those values are compared
directly against `0.72 V` and `0.08 V`, respectively.  The timing relation
below is derived from the raw `.mt0.csv` measurements; a negative value means
the fixed sample occurs before the stated threshold crossing.

| Driver | High sample minus 90% crossing (ps) | Low sample minus 10% crossing (ps) | Readback result |
|---|---:|---:|---|
| `BUF_X0P8M_A9TL40` | -40.556 | 56.009 | high fails; low passes |
| `BUF_X1M_A9TL40` | -86.308 | 26.776 | high fails; low passes |
| `BUF_X1P4M_A9TL40` | -142.156 | -2.607 | high and low fail |
| `BUF_X2M_A9TL40` | -163.144 | -22.479 | high and low fail |

Therefore the observed invalid levels are not a field-order, unit-conversion,
or threshold-calculation error.  They are the physical consequence of the
deep `M=15, F=K, VDD=0.80 V` path not reaching the required state before the
fixed acceptance samples.  Moving either sample would change the frozen
measurement contract and would require a separately authorized revalidation.
