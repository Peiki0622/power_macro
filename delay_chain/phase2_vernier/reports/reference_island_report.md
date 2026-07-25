# RC Reference Island Selection

The PWL sense-domain source falls from 1.100 V to the 765 MHz 40-bank anchor,
1.047473942801 V.  Each point instantiates the real 32-stage reference chain
and 32 discovered `DFFRPQ_X0P5M_A9TR40` comparators on `VDD_REF/VSS_REF`.

Selected point: `R_ISO=1 ohm`, `C_REF=10 pF`.

| Metric | Result |
|---|---:|
| VDD_A minimum | 1.0475 V |
| VDD_REF minimum | 1.0999 V |
| VDD_REF at 3.5 ns | 1.1000 V |
| Upstream peak current | 76.49 uA |

The full 16-point measurement table is in
`runs/reference_island_20260724_r1/reference_island_metrics.csv`.
