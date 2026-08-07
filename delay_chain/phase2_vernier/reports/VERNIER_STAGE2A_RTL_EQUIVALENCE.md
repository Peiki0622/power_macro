# Stage 2A RTL Equivalence

Status: PASS

## Digital decoder

The complete Phase 2 regression was run with:

```
python3 -m unittest discover -s delay_chain/phase2_vernier/tests -p 'test_*.py'
```

The regression covers all-zero, all-one, ideal thermometer, single-bubble,
multiple-bubble, and strongly invalid vectors.  The SystemVerilog backend
matches the Python `0*1*` reference for corrected word, leading-zero code,
bubble count, `code_valid`, and one-cycle `sample_valid` behavior.

## HSPICE raw-Q replay

The retained direct-rail capture contains exactly 500 32-bit `raw_code` rows.
`test_spice_raw_q_replay.py` now compiles the real
`vernier_sensor_digital_backend.sv` once with VCS, replays every row through
the backend, and compares raw word, corrected word, code, bubble count,
validity, and sample pulse.  The test passed with zero mismatches and printed
`SPICE_RAW_Q_REPLAY_PASS`.

## Interface/elaboration checks

Final top-level VCS elaboration of `vernier_sensor` against the SMIC40LL cell
Verilog model returned status 0.  A static scan found no synthesizable
`function`, `#delay`, `sample_done`, or `capture_clk` construct in the RTL.
