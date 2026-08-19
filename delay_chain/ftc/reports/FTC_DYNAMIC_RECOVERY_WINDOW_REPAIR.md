# FTC Dynamic Recovery Window Repair

**Dynamic Recovery Window Repair = NO-GO**

## Frozen handoff

The retained baseline is commit `568f8ace2b7fa813a2bb082302c182b51288dd53`.
The original protocol remains `Dynamic Startup Calibration Protocol = NO-GO`
with the sole reason `recovery_window_insufficient`.

Retained evidence was not rerun:

- 0.95 V: GO, coarse Q `1111110`, fine Q `10`, hold Q `0`, final `(5,1)`.
- 1.10 V: GO, coarse Q `11110`, fine Q `11110`, hold Q `0`, final `(3,4)`.
- 0.80 V: original NO-GO only at recovery, coarse Q `1111111110`, fine Q `10`, hold Q `0`, final `(8,1)`.
- Upstream static 84 scenarios rerun: 0.
- Upstream static HSPICE rerun: 0.
- Retained 0.95/1.10/old 0.80 dynamic reruns: 0.

## Old failure map

The retained 0.80 V raw measurement was parsed without rerunning HSPICE.
There are 7 failed node measurements across probes 7--12:

- `medium_out`: probe 7 (one failure).
- `dff_ck`: probes 7--12 (six failures).
- `xor_29`: no failure.

The worst retained failure is probe 9, `(M=9,F=0)`, at `dff_ck`:
the endpoint ratio was `0.0378013`, while the final 200 ps tail ratio was
`1.00340755` (`0.802726 V` at 0.80 V supply). This is the retained evidence
that the 2.5 ns endpoint/tail window ended during active return behavior.

## Diagnostic contract and result

The first bounded diagnostic window was derived from retained evidence only:

```
T_diag_bound = ceil_0.1ns(1.575187351 ns + 1.269042997 ns + 0.400 ns)
              = 3.3 ns
```

One new HSPICE scenario was run, `recovery_diagnostic_0p80`. It produced 39/39
valid return measurements (three nodes for each of 13 probes), with no second
rise. The measured worst return-fall settling time was:

| node | worst settle |
| --- | ---: |
| `xor_29` | 1.588652511 ns |
| `medium_out` | 2.306213900 ns |
| `dff_ck` | 2.474756780 ns |

The overall worst case was probe 9, coarse phase, `(M=9,F=0)`, `dff_ck`,
`2.474756780 ns` after `S_CLK` fall. These measurements support the return-
activity hypothesis, but they cannot authorize a repaired guard because the
diagnostic schedule changed the functional trajectory.

## Stop condition

The old 0.80 V Q sequence was `1111111110100` for the 13 probes. The diagnostic
sequence was `1111111100100`; the first difference was probe 8. The diagnostic
runner advances `cursor` to `recovery_end_s`, so changing the guard from 2.5 ns
to 3.3 ns shifts each later probe's update, launch, and Q-read times by
`0.8 ns` per preceding probe. This is a functional schedule change, not a
recovery-only change.

Therefore the plan's diagnostic gate fails with:

```text
diagnostic_q_sequence_changed
```

Phase 5 guard freezing and the single repaired-validation opportunity were not
authorized. No `repaired_timing_contract.json`, repaired probe result, repaired
transition audit, or repaired HSPICE scenario was created. No guard tuning or
hardware change was attempted.

## Accounting

```text
new_diagnostic_hspice_scenarios = 1
new_repaired_hspice_scenarios  = 0
reused_new_task_scenarios      = 1
upstream_static_84_scenarios_rerun = 0
upstream_static_hspice_rerun      = 0
old_dynamic_0p95_rerun = 0
old_dynamic_1p10_rerun = 0
old_dynamic_0p80_rerun = 0
```

The task ends at NO-GO. A future attempt would first need an explicitly
plan-compliant fixed original probe schedule (or an amended plan); it must not
rerun HSPICE until that contract is resolved.
