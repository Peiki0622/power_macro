# B-FE3-P0 offline raw-feature audit

Gate: `BFE3_P0_POSTPROCESS_FEATURES_PROMISING`

No VCS/XA run was launched. This is an offline extraction from retained 0.95 V safe-domain XA final/tail Q samples only.
The three features are raw: `N=sum(q[i])`, `M=sum(i*q[i])`, `T=sum(q[i] XOR q[i-1])`; no bubble repair, encoding, table, model, or filter is used.
A historical source-free re-flip does not exclude a sample if its final Q is rail-resolved and its 1 ns tail is stable; its provenance remains in the table.

| Sample | Label | Source | q_raw[29:0] | N | M | T | Historical source-free | Historical unresolved |
|---|---|---|---|---:|---:|---:|---|---|
| L1AR_095_NORMAL | NORMAL_NOMINAL | L1A-R | `001111111111111100000000000000` | 14 | 287 | 2 | [] | False |
| L1AR_095_L2 | L2_DROOP | L1A-R | `000000011111111111110000000000` | 13 | 208 | 2 | [] | False |
| CAL0_LEFT | NORMAL_CAPTURE_PERTURBATION | CAL0 | `000111111111111100000000000000` | 13 | 260 | 2 | [27] | True |
| CAL0_CENTER | NORMAL_CAPTURE_PERTURBATION | CAL0 | `001111111111111100000000000000` | 14 | 287 | 2 | [] | False |
| CAL0_RIGHT | NORMAL_CAPTURE_PERTURBATION | CAL0 | `011111111111111000000000000000` | 14 | 301 | 2 | [29] | True |
| LATQ_APERTURE_CENTER | NORMAL_CAPTURE_PERTURBATION | LATQ_APERTURE | `001111111111111100000000000000` | 14 | 287 | 2 | [] | False |
| LATQ_APERTURE_MID | NORMAL_CAPTURE_PERTURBATION | LATQ_APERTURE | `011111111111111000000000000000` | 14 | 301 | 2 | [] | False |
| LATQ_APERTURE_RIGHT | NORMAL_CAPTURE_PERTURBATION | LATQ_APERTURE | `011111111111111000000000000000` | 14 | 301 | 2 | [29] | True |
| LATQ_APERTURE_LATE_CAPTURE | NORMAL_CAPTURE_PERTURBATION | LATQ_APERTURE | `111111111111110000000000000000` | 14 | 315 | 1 | [] | False |

Normal/capture-perturbation envelope: `N=13-14; M=260-315; T=1-2.`
Nominal normal is `L1AR_095_NORMAL` with `(N,M,T)=(14, 287, 2)`.
L2 `L1AR_095_L2`: displacement `(dN,dM,dT)=(-1, -79, 0)`; outside envelope `{'N': False, 'M': True, 'T': False}`; outside-envelope margin `{'N': 0, 'M': 52, 'T': 0}`.

Separating raw feature(s): `['M']`. The Gate is promising because M alone places every retained L2 sample outside the normal envelope with nonzero margin; N and T alone overlap and are not claimed to separate.

This evidence is limited to its retained sample set and does not authorize P1, RTL implementation, calibration, or detection work. B-FE3-P0 stops here.
