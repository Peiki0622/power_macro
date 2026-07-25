# Direct VDD_A Droop To Code Characterization

The static curve uses the calibrated real-DFF topology: M=32, one reference dummy load, CAL_SEL=2, and a 20 ps sense launch offset.  VDD_REF remains 1.100 V while only VDD_A is stepped.

| Metric | Value |
|---|---:|
| Static scenarios | 303 |
| Baseline code at 1.100 V | 15 |
| 35-bank last-pass droop (mV) | 45.938672293 |
| 35-bank last-pass code | 32 |
| 40-bank first-violation droop (mV) | 52.526057199 |
| 40-bank first-violation code | 32 |
| First-violation minus baseline code | 17 |
| First-violation minus last-pass code | 0 |
| Raw/corrected bubble scenarios | 0 |
| Invalid code scenarios | 0 |
| Reset failures | 0 |
| Metastability-risk bits | 266 |
| Monotonicity violations | 0 |

## PWL Dynamic Comparison

| Case | Capture droop (mV) | Dynamic code | Nearest static code | Dynamic-static delta |
|---|---:|---:|---:|---:|
| slow | 52.500000000 | 16 | 32 | -16 |
| medium | 52.500000000 | 18 | 32 | -14 |
| fast | 52.500000000 | 32 | 32 | 0 |
