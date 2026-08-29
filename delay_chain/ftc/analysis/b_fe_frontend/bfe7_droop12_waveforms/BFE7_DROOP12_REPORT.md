# B-FE7 DROOP12 Waveform Contract Report

## Result

Twelve deterministic, HSPICE-feedable, noisy-1.10-V voltage-droop scenarios
were constructed, validated offline, SHA256-hashed, frozen, and visualized.
All twelve scenarios share the seed-7301 bounded normal background and use
explicit finite-slope attack PWL points.  The reusable source port is
`V_VDD_MONITORED vdd_monitored vss_a`.

## Verification

- W0 authority hashes and canonical 0--65 ns frame passed.
- W1 PCG64 background generation and byte-identical regeneration passed.
- W2 D01-D12 scenario geometry and immutable contract passed.
- W3 produced 24 compact CSV/INC HSPICE stimulus artifacts.
- W4 offline numerical, geometry, port, provenance, and anti-drift tests passed.
- W5 produced the vector PDF and 600 dpi PNG atlas from manifest-hashed CSV files.
- W6 final manifest includes source, waveform, validator, plotter, and figure hashes.

`DROOP12_RUN_LEDGER.json` records zero HSPICE, VCS, PrimeSim, DC, ARCH0, and
ARCH1 runs.  No production RTL, detector, sensor, clock, capture gate, or
circuit parameter was modified.

## Claim Boundary

This report makes no claim about ARCH0 detection rate, ARCH1 improvement,
false-positive rate, fault coverage, victim timing faults, or optimality of
the waveform amplitudes.  The package defines stimuli only.  Evaluating the
frozen files on ARCH0 or ARCH1 is a separate, explicitly authorized stage.
