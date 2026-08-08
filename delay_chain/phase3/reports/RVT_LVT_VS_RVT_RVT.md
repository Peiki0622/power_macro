# RVT/LVT Versus RVT/RVT Same-Rail Control

## Construction

Both runs use the same 123 exact VDD points, TT/25 C, 32 real DFFRPQ comparators, `CAL_SEL=1`, the same BUF/MXT2 launch network, and only `VDD_A/VSS_A`. The control replaces the LVT companion inverter and its CDL with `INV_X0P5M_A9TR40` from the RVT CDL; the one-input dummy-load count remains one so loading methodology is unchanged.

## Code Sensitivity

The primary comparison uses the endpoint finite difference over 1.040-1.100 V:
`abs(dC/dVDD) = abs(C(1.040 V) - C(1.100 V)) / 0.060 V`.

| Structure | Code at 1.100 V | Code at 1.040 V | Code span | abs(dC/dVDD) (code/V) |
|---|---:|---:|---:|---:|
| RVT/LVT | 18 | 32 | 14 | 233.333333 |
| RVT/RVT control | 2 | 2 | 0 | 0.000000 |

The RVT/LVT code slope is strictly greater than the RVT/RVT control slope, which is code-locked across the complete sweep. The selected sensor's exact anchor residuals are +12 codes at last-pass and +14 codes at first-violation; the control residual is 0 at both anchors.

## Physical Differential Delay

The final-tap crossing measure is `lvt_031_cross - rvt_031_cross`; for the control the second path is also RVT, so this column is a same-cell loading/control diagnostic rather than an LVT device claim.

| Structure | Differential delay at 1.100 V (ps) | Differential delay at 1.040 V (ps) | abs change / V (s/V) |
|---|---:|---:|---:|
| RVT/LVT | -7.186855 | -21.307556 | 2.353450e-10 |
| RVT/RVT control | 177.704948 | 201.261681 | 3.926122e-10 |

The code result, rather than the control's raw timing offset, is the required sensitivity discriminator: the RVT/RVT pair never reaches a code transition while the RVT/LVT pair traverses fourteen codes.

## Evidence

- Sensor CSV: `../runs/voltage_sweep/voltage_code.csv`
- Control CSV: `../runs/voltage_sweep_rvt_rvt/voltage_code.csv`
- Sensor summary: `../runs/voltage_sweep/voltage_summary.json`
- Control summary: `../runs/voltage_sweep_rvt_rvt/voltage_summary.json`
