# B-FE7 W1 Normal Background

`NBG_7301.csv` and `NBG_7301.inc` are the one shared healthy-supply
realization used by all twelve future attacks.  The source drives the
monitored-domain positive rail `vdd_monitored` against the local return
`vss_a`; it does not instantiate a clock or any detector circuitry.

The background is a synthetic benchmark assumption.  Slow 2.5 ns knots use
bounded, centered samples in +/-5 mV, fast 250 ps knots use bounded samples in
/-3 mV with their full-grid sample mean removed, and the sum is hard-limited
to +/-8 mV around the 1.10 V nominal rail.  Sampling is explicit PCG64 with
seed 7301 in the `DL` environment, so no simulator noise source is involved.

The W1 gate records only offline checks: endpoint coverage, finite and
strictly-increasing time, healthy-rail range, and byte-identical regeneration.
No HSPICE or other circuit simulation was run.
