# FTC Dynamic M8 History Root Cause

**CONCLUSIVE**

## Classification

- Primary: `real_dff_reset_or_capture_history_dependence` (conclusive)
- Secondary: `none`
- First divergent stage/node: `dff_capture` / `q_final`
- Recommended next action: `stop_and_enter_dff_reset_capture_repair_plan`
- Forbidden next actions: `ConfigSkip, FSM, guard_sweep, medium_or_fine_cell_change, DFF_or_reset_contract_change`

## Retained Evidence

- Probe 8 (M8,F0) D_total delta, 3.3 ns minus 2.5 ns: 0.41898999999318676 ps; XOR width delta: 0.14477000000522366 ps.
- Probe 10 (M8,F0) Q: 2.5 ns=1, 3.3 ns=1; this is the same final code after a different predecessor schedule.
- Probe 8 Q flip is not explained by the small XOR-width change alone; absolute launch shift is 6.400089430000004 ns.
- Retained Q sequences: 2.5 ns=`1111111110100`, 3.3 ns=`1111111100100`; publication/parser check passed.

## Matrix Evidence

- Isolated M8 Q before/after the deck: `n/a` / `n/a` (repeatable).
- M7->M8 versus M9->M8 at 2.7 ns: D_medium effect=0.21683999995934755 ps, D_fine effect=0.019730000042187612 ps, D_total effect=0.19710999991707467 ps; repeat spread=0.48210000008918996 ps.
- Recovery sensitivity (2.5/2.7/3.3 ns): `False`; code-settle sensitivity (1.5/3.3 ns): `False`.
- Reset sensitivity (0.49/1.00 ns): `True`; active-pulse predecessor sensitivity: `False`.
- Ascending monotonicity: `True`; descending consistency: `True`; configuration glitches: `False`.
- The first stage remains stable through XOR, medium, and CK; the positive/negative reset control separates at real DFF.Q.

## Accounting And Decision

- Root-cause matrix HSPICE scenarios: 1 (one completed PASS scenario).
- Repaired full-trajectory HSPICE scenarios: 0 (blocked by the classification gate).
- Reruns: upstream static 84=0, legacy dynamic A=0, B=0, C=0, legacy diagnostic=0.
- 2.7 ns remains the measured candidate functional guard, but no repaired trajectory is authorized while reset/history dependence is present.
- No evidence supports ConfigSkip or medium/fine cell changes; DFF/reset sensitivity is confirmed, but its contract is deferred to the dedicated repair plan.
