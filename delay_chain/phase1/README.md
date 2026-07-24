# SMIC40LL Voltage Sensor Phase 1

This directory implements only the constant-supply delay-chain characterization
specified by `power_macro/plans/voltage_sensor_plan.md` section 4.  It compares
16, 32, and 64 non-inverting delay units.  A unit contains exactly two
`INV_X0P5M_A9TR40` instances, so all observed taps retain the START polarity.

## Electrical contract

The generated decks instantiate the transistor-level standard-cell CDL and the
SMIC40LL TT process model.  The inverter public port order is:

```text
Y VDD VNW VPW VSS A
```

Every instance connects `VDD` and `VNW` to `VDD_A`, and `VSS` and `VPW` to
`VSS_A`.  Phase 1 drives that local differential rail with an ideal DC source
only to characterize the `VDD_A -> K_sense` transfer function.  It does not
claim to measure package-induced droop or sensor self-disturbance; those are
explicitly deferred to the shared-RLC integration phase.

## Commands

Run the full reproducible study from the repository root:

```bash
python3 power_macro/delay_chain/phase1/scripts/run_dc_sweep.py \
  --config power_macro/delay_chain/phase1/phase1_config.json \
  --output-dir power_macro/delay_chain/phase1/runs/phase1_dc_<UTC-tag>
python3 power_macro/delay_chain/phase1/scripts/analyze_dc_sweep.py \
  --run-dir power_macro/delay_chain/phase1/runs/phase1_dc_<UTC-tag>
```

`run_dc_sweep.py` refuses to overwrite an existing run directory.  It produces
one deck and one HSPICE result set for every chain/voltage pair, including the
exact first-violation voltage from the existing FIR 770 MHz timing study.
`analyze_dc_sweep.py` writes `sweep_metrics.csv`, plots, a deterministic
selection report, and `phase1_summary.md`.  Generated EDA products remain
beneath the task-owned run directory.
