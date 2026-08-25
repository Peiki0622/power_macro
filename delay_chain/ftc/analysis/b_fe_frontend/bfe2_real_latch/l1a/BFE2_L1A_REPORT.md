# B-FE2-L1A report

Gate: `BFE2_L1A_REAL_SAFE_LATCH_FAIL`

Verification mode: `equivalent causal isolation`.

The frozen B-FE2.2C 0.95 V normal/L2 XOR waveforms drive zero-delay, full-swing safe_d PWL sources. Thirty real `LATQ_X0P5M_A9TR40` cells are powered only from stable `PD_SAFE=0.95 V`; this is not a complete AMS co-simulation and does not prove a physical level shifter.

Normal final Q: `000000000000000011111111111111`

L2 final Q: `000000000000111111111111111111`

Hamming distance: `4`

Normal source-free re-flips: `[16]`; L2 source-free re-flips: `[12]`.

Normal unresolved taps: `[]`; L2 unresolved taps: `[]`.

Historical tap27 normal classification: `zero-crossing`.

Failure follow-up: `BFE2_CAPTURE_CELL_REVIEW_REQUIRED` (no close change, no L1B/L2 entry).

No subsequent L1B/L2 stage is authorized by this artifact.
