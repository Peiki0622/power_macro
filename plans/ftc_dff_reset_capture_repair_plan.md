# FTC 0.80 V DFF Reset-Arm Revalidation And Repair Plan

## Objective

Revalidate the M8 dynamic anomaly with a true reset-release-to-S_CLK interval.
The earlier history matrix incorrectly released reset at launch, so its DFF
classification is provisional and must not directly change the protocol.

## Frozen Scope

- Use the existing 0.80 V TT/25 C sensor, tap29, N=16 medium, F=0, fine
  driver/load, and `DFFRPQ_X0P5M_A9TR40`.
- Retain code-settle=1.5 ns, recovery=2.7 ns, and isolation=3.5 ns.
- Do not rerun retained static, old dynamic, or old diagnostic scenarios.
- Do not modify legacy runners, global config, the DFF cell, ConfigSkip, FSM,
  gating, bypass, PVT, or droop.
- New HSPICE budget: one diagnostic scenario and, only after its gate passes,
  one full 13-probe validation scenario.

## Step 1 - Freeze The Retest Baseline (0 HSPICE)

Create task-owned baseline and requirements records that hash retained evidence,
the old root-cause runner, and the selected DFF CDL. Record the static defect:
the old root-cause schedule has `reset_release_s == launch_time_s` for every
active probe, while the legacy dynamic timing contract requires 0.49 ns.

Verification: all frozen input files exist, legacy decisions remain NO-GO, all
old rerun counters are zero, and the schedule-defect predicate is true.

## Step 2 - Define One True Reset-Arm Matrix (0 HSPICE)

Build a new task-local runner and contract. The target sequence is always:

```text
reset asserted / S_CLK low during code update
-> 1.5 ns code-settle
-> reset-high timeline pad
-> reset release
-> reset arm
-> S_CLK launch
```

Use only reset-arm values 0, 0.49, and 1.00 ns. Use only reset-high timeline
pad values 0 and 0.51 ns. Cover active M7->M8, M9->M8, and M8->M8 predecessors;
repeat the M7/M9 target combinations in reverse order in the deck back half.
Predecessor probes always use the legacy 0.49 ns reset arm.

Verification: each active target satisfies `launch - reset_release = reset_arm`;
M transitions are one bit at a time; reset is asserted during every update; F
is always zero; every required condition and repeat is present exactly once.

## Step 3 - Measure The DFF Boundary (0 HSPICE)

For each target, measure reset and S_CLK crossings, XOR/medium/CK 10% and 50%
crossings, second CK edges, Q at the existing read time and read+200 ps, and
DFF hierarchical nodes `nclk`, `bclk`, `nd`, `nm`, `m`, `s`, and `ns`.
Missing measures remain missing and invalidate only the affected observation.

Verification: static deck checks prove the real DFF port mapping, all required
measure names, hierarchy node names, bounded transition audits, and absence of
forbidden features.

## Step 4 - Run And Classify The Single Diagnostic Scenario

Run exactly one 0.80 V diagnostic deck after all static tests pass. Derive the
noise gate from early/late repeated M7/M9 target measurements. A protocol arm
is accepted only when M8 Q=1 at both reads for all predecessor, pad, and repeat
controls, with stable external path measurements and no extra CK edge.

Decision: select 0.49 ns if it passes; otherwise select 1.00 ns only if it
passes; otherwise stop. A pad-sensitive result, unstable external path, or
missing required measurement also stops the plan. Do not screen or replace DFF
candidates in this task if it stops.

Verification: listing is clean, manifest is PASS, every matrix group is parsed,
classification contains the selected arm or a stopping reason, and exactly one
new successful scenario exists.

## Step 5 - Conditional Full Trajectory Validation

Only after Step 4 selects an arm, run one task-local complete 13-probe scenario
with that arm and recovery=2.7 ns. Do not alter legacy runners or global config.

Verification: coarse=1111111110, fine=10, hold=0, lock=(8,1), Q is stable at
both reads, every probe satisfies the selected arm, recovery tails pass, and
no configuration-induced or second CK edge exists. Any failure stops without a
sweep.

## Step 6 - Publish And Close

Write task-owned contracts, CSV evidence, classification, summary, and report.
Document that DFF candidates X1M/X2M/X3M/X4M are future-only if Step 4 fails;
a separate approved plan must screen them and choose the smallest passing drive.

Verification: diagnostic count=1, full-validation count=0 or 1, all old rerun
counters=0, unit tests pass, the runner compiles, and `git diff --check` passes.
