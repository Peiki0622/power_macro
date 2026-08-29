# B-FE7 W4 Offline Validation

The validator parses all twelve CSV/INC pairs and checks the frozen W2 attack
breakpoints, shared PCG64 background, `1.10 + noise - depth` arithmetic,
strict SI time order, formal 0.8 V minimum, and the modular monitored-rail
source contract.  It also checks D10/D11 mirroring, D07/D08 pulse cadence,
and D12 coverage of both reference edges.

The deterministic regression test regenerates the package in a task-local
temporary directory and compares artifact bytes.  Four tests passed.  No
HSPICE, VCS, DC, or PrimeSim process was launched.
