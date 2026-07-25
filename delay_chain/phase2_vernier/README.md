# SMIC40LL 765 MHz Differential Vernier Sensor

This directory implements standard-cell SPICE characterization of the
differential delay sensor, including a controlled direct-`VDD_A` multi-capture
timeline.  The timeline directly drives the chiplet-A sense rail and measures
real DFF-derived codes; it is not a shared-PDN or RO-attack integration.
Shared-PDN, PVT, and sensor-self-disturbance studies remain separate work.

## Timing anchor

All Phase 2 decisions use
`chiplets/FIR/timing_droop/runs/fir_parallel_ro_bank_timing_765mhz_20260724_r3`.
That 765 MHz TT/25 C run reports 35 coherent 31-stage RO banks as the last
passing point at `1.054061327707 V`, and 40 banks as the first violating point
at `1.047473942801 V`.  The historical 770 MHz voltage is intentionally not a
Phase 2 input.

## Electrical boundary

The sense delay chain is powered only by `VDD_A/VSS_A`.  The reference chain,
launch-offset network, comparator DFFs, and their well pins are powered only
by `VDD_REF/VSS_REF`.  The direct timeline holds `VDD_REF` at 1.100 V and
applies its deterministic PWL only to `VDD_A`; it does not instantiate a
reference-island RC network.  All standard-cell instantiations use the CDL pin
order discovered from the source library; no transistor-level replacement or
fixed HDL delay is permitted.

## Direct-rail timeline

`scripts/run_direct_rail_sensor_timeline.py` runs one complete 2 us HSPICE
transient with 500 real DFF captures.  Its 4 ns frames include reset, calibrated
reference/sense launches, capture, and recovery.  Four frame-aligned 248 ns
direct-PWL windows use fixed nonmonotonic 4--30 mV target droops; closed frames
retain deterministic 0.5--2.0 mV fluctuations.  The corresponding plotter
consumes only the completed capture CSV and HSPICE `.tr0` rail trace:

```bash
python3 scripts/run_direct_rail_sensor_timeline.py \
  --config phase2_config.json \
  --output-dir runs/direct_rail_sensor_timeline_YYYYMMDD_rN
python3 scripts/plot_direct_rail_sensor_timeline.py \
  --config phase2_config.json \
  --run-dir runs/direct_rail_sensor_timeline_YYYYMMDD_rN \
  --output-dir reports/direct_rail_sensor_timeline_YYYYMMDD_rN
```

The historical `runs/direct_rail_sensor_timeline_20260725_r1` run remains a
40-capture baseline.  The high-density `runs/direct_rail_sensor_timeline_20260725_r2`
run passes all 500 capture/code/rail checks.  Its compact results are
`direct_rail_samples.csv`, `timeline_result.json`, and `completion.rpt`; the
500-point plot and scope-limited report are under
`reports/direct_rail_sensor_timeline_20260725_r2`.

## Run data

Each simulator invocation owns a new directory below `runs/`.  HSPICE raw
products are retained there for local evidence but are not source artifacts.
The scripts export compact CSV, Markdown reports, manifests, and selected
figures required for review and reproduction.
