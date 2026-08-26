# B-FE3-P0 detailed execution note

## Objective and boundaries

B-FE3-P0 asks a limited offline question: can retained front-end capture
variation be separated from the retained 0.95-to-0.86 V L2 response using only
three direct functions of the final raw Q bits? It does not alter the sensor,
the `LATQ_X0P5M_A9TR40` cell, G/sample close, power domains, circuit, RTL,
calibration controller, or detection logic.

The runner opens only retained `xa_boundary_samples.csv` files and their
already-published analysis JSON. It does not import a simulator launcher and
does not create a deck. The manifest records `simulation_run=false` and
`new_vcs_xa_scenarios=0`.

## Evidence population

The included population has `VDD_SAFE=0.95 V`, the fixed 30-tap 4/0 geometry,
and a final Q sample for every tap paired with its retained 1 ns tail sample.

| Population | Samples | Purpose |
|---|---:|---|
| L1A-R normal | 1 | Nominal normal reference |
| CAL0 normal | 3 | Existing sample-close capture perturbations |
| LATQ aperture normal | 4 | Existing D-versus-G capture perturbations |
| L1A-R 0.95-to-0.86 V L2 | 1 | Retained voltage-droop response |

All nine samples are final rail-resolved and have stable tails. CAL0 LEFT and
CAL0 RIGHT retain their historical source-free labels; LATQ aperture RIGHT also
retains its source-free re-flip/unresolved label. They remain in the normal
variation envelope because their final code is not mid-rail and their tail is
stable. This follows the stage contract: historical capture instability is
provenance, not automatic sample rejection.

The older `l1a_vcs_xa_1p10` XA family is explicitly excluded. Its real latch
uses a 1.10 V safe rail, which does not match the 0.95 V safe-domain contract
of this evidence population. The exclusion is a supply-contract mismatch, not
a result-based selection.

## Raw representation and features

For each sample, the CSV and JSON record both raw orderings:

```text
q_raw[29:0]             conventional descending tap display
q_raw_tap0_to_tap29     computation order for i = 0..29
```

No bit is modified. There is no bubble repair, longest-run operation, lookup
table, classifier, learned model, or filter. The only computed values are:

```text
N = sum(q[i])
M = sum(i * q[i]), i = 0..29
T = sum(q[i] XOR q[i-1]), i = 1..29
```

`N` records raw population, `M` records the raw index-weighted population, and
`T` records raw adjacent transitions. They are measurements, not a decoder or
an implemented digital post-processing block.

## Result and margin

The nominal L1A-R normal sample is `(N,M,T)=(14,287,2)`. Across all eight
normal/capture-perturbation samples, the inclusive observed envelope is:

```text
N = 13..14
M = 260..315
T = 1..2
```

The retained L2 sample is `(N,M,T)=(13,208,2)`, therefore its displacement
from nominal is `(-1,-79,0)`.

| Feature | L2 value | Normal envelope | Separate? |
|---|---:|---:|---|
| N | 13 | 13..14 | No, overlaps |
| M | 208 | 260..315 | Yes, 52 below lower edge |
| T | 2 | 1..2 | No, overlaps |

`M` alone places every retained L2 sample outside the observed normal envelope
with a nonzero margin of 52. With one retained L2 sample this is evidence of a
promising raw feature, not a statistical voltage-detection signoff, an
interpolated threshold, or authorization to implement a datapath.

## Gate and stop condition

The Gate is `BFE3_P0_POSTPROCESS_FEATURES_PROMISING` because at least one
permitted simple raw feature (`M`) separates every retained L2 sample from the
observed normal/capture-perturbation envelope. `N` and `T` are explicitly not
claimed to separate.

The conclusion applies only to this finite evidence set. B-FE3-P0 stops here;
it does not authorize P1, RTL, self-calibration, FSM, or detection work.
