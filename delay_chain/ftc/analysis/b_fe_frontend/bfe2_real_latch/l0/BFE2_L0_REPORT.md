# B-FE2-L0 report

Gate: `BFE2_L0_SAFE_DOMAIN_PASS`

The two fixed-close 0.95 V probes use the immutable B-FE2.2C normal/L2 stimulus and `sample_close=534.524618567 ps`.

Normal final Q: `000000000000000111111111111111`

L2 final Q: `000000000001111111111111000000`

Hamming distance: `10`

No post-close Q crossing/re-flip was observed in either deterministic L0 replay. Local VCS W-2024.09 compiled and executed both fixed stimuli; the local PrimeSim XA W-2024.09 official tutorial also completed with zero comparison errors. This PASS proves only that ideal PD_SAFE restoration plus ideal transparent-latch isolation removes the observed failure in this replay; it does not prove a physical level shifter implementation. `new_hspice_scenarios=0`.
