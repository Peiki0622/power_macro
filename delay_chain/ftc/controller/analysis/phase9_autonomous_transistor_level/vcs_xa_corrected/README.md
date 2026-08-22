# Phase 9 corrected VCS-XA flow

This sibling flow is the recovery workspace for the historical Phase 9 mixed-
signal NO-GO.  The original `vcs_xa/` directory is immutable historical
evidence and is never overwritten by this flow.

The corrected flow consumes the frozen synthesized controller, frozen
transistor sensor, and Phase 1 timing handoff.  It separates static forensic
checks, a 1 GHz digital diagnostic, electrical-boundary checks, short analog
probes, and only then autonomous mixed-signal runs.  Generated XA databases,
FSDB files, and logs stay below this directory's `diagnostics/` or `runs/`
subdirectories; compact JSON reports and hashes are the reviewable evidence.

R0 is intentionally static.  No transient simulation is launched by the
baseline-freeze script.
