# FTC DFF Falling-Data Hold/Aperture Protocol Repair Plan

## Objective

Repair the FTC calibration protocol after retained 0.80 V transistor-level
evidence showed that the apparent M8 history dependence is a DFF falling-data
hold/aperture boundary, not reset-arm dependence, extra active CK activity, or
configuration-induced CK glitches.

The repair is intentionally protocol-only: back off two medium steps from the
first non-stable-high coarse code, find the first non-stable-high fine code,
then advance one additional fine step before locking. If the first medium base
has no fine boundary by F=K-1, advance M exactly once and rescan F=0..K.

## Frozen Scope And Decisions

- Keep the existing sensor, tap29, N=16 medium path, fine path, DFF, K, reset
  timing, code-settle timing, 2.7 ns recovery guard, and isolation timing.
- `coarse_backoff_steps = 2`, `fine_guard_steps = 1`, and
  `max_medium_fallback_steps = 1` are fixed.
- A Q decision is valid only when both read samples resolve to the same rail.
- Stable-high means both reads are high; stable-low means both reads are low.
- The root cause identifier is `dff_falling_data_hold_aperture_boundary`.
- Do not modify legacy runners, `ftc_config.json`, RTL, cells, driver/load, K,
  ConfigSkip, bypass, clock gating, FSM, PVT, or droop behavior.
- Do not rerun retained static, old dynamic, root-cause, or reset-arm evidence.
- Preserve the retained `r1` diagnostic scenario and raw measurement file
  byte-for-byte.
- New HSPICE budget is exactly four complete scenarios. A failed scenario does
  not authorize an added sweep or replacement scenario.
- Keep all new outputs in the existing task-owned analysis and run directories.

## Step 1 - Correct The Retained Diagnostic Interpretation (0 HSPICE)

Fix the task-local parser so active and quiet transition searches have an
explicit end time. A CK edge after reset reassertion or during a later probe
must not be attributed to the earlier active/configuration window. Remove the
final cleanup transitions that have no observation window, or classify them as
invalid; they must never be reported as passing observations.

Regenerate the task-owned diagnostic CSV, audits, classification, summary, and
report from the retained `.mt0.csv` only. Withdraw the earlier extra-CK and
configuration-glitch conclusions and publish the bounded-window result:
active-window extra CK is 0/60 and all 496 transitions with actual bounded
measurements pass. Preserve missing data as invalid rather than PASS.

Verification: hash the retained raw file before and after regeneration and
require equality; require zero HSPICE launches; test a return CK after the
active-window end, a transition edge after the quiet-window end, and a missing
window; confirm every published PASS is backed by bounded measurements.

## Step 2 - Implement The Minimal Guarded-Lock Protocol (0 HSPICE)

Extend the existing task-local repair runner and contract with this algorithm:

```text
coarse_boundary = first coarse code that is not stable-high
M_base = max(coarse_boundary - 2, 0)

scan F=0..K at M_base
fine_boundary = first F that is not stable-high

if no boundary by F=K-1:
    M_base = M_base + 1
    reset F to 0
    rescan exactly once

candidate = fine_boundary + 1
lock only when candidate and lock-hold are both stable-low
```

The boundary observation may be stable-low or ambiguous, but the guarded lock
and lock-hold must each be stable-low at both reads. Reject an out-of-range
guard code, a second missing boundary, an ambiguous guard, or a failed hold.
Do not add a second runner or general-purpose calibration framework.

Verification: inspect the generated schedule and contract for the exact coarse
backoff, one-step fine guard, at-most-one fallback, two-read decisions, complete
coarse/fine/guard/lock-hold sequence, and absence of forbidden features.

## Step 3 - Pass Focused Static Gates (0 HSPICE)

Add focused unit tests for bounded event windows, missing-window invalidation,
normal and fallback trajectories, an F=K boundary/guard limit, guard failure,
lock-hold failure, and exact scenario identity reuse. Reuse the existing test
file and keep test fixtures compact.

Verification: all related unit tests pass, the runner passes `py_compile`,
generated contracts validate without invoking HSPICE, exact identity reuse
does not launch HSPICE, and `git diff --check` passes. Step 4 is forbidden
until every static gate passes.

## Step 4 - Run Four Complete Transistor-Level Scenarios

Run exactly these complete scenarios with full coarse, fine, guard, lock-hold,
CK, bounded quiet-window, and recovery-tail coverage:

```text
0.80 V normal trajectory
0.95 V normal trajectory
1.10 V normal trajectory
0.80 V forced-early coarse-boundary fallback trajectory
```

The fallback scenario changes only the diagnostic coarse decision stimulus
needed to exercise the specified fallback path; it must use the same physical
configuration trajectory and guarded-lock acceptance rules after fallback.
These are acceptance scenarios, not smoke simulations.

Verification per scenario: clean listing and manifest; exactly one active CK
edge per probe; no CK edge in every bounded configuration window; recovery
tail below 0.1*VDD; fine scan contains stable-high observations followed by a
non-stable-high boundary; the next fine code and lock-hold are stable-low at
both reads. Both 0.80 V paths must converge to the identical guarded lock.

## Step 5 - Publish And Close

Publish only task-owned contracts, compact CSV/JSON evidence, summary, and one
report in the existing analysis directory. Record measured lock codes rather
than hard-coding estimates; expected values may be mentioned only as context.

Verification: exactly four new successful scenario identities exist; no old
scenario was rerun; both 0.80 V paths have identical final locks; all scenario
and aggregate acceptance predicates pass; retained `r1` raw hash is unchanged;
related unit tests, `py_compile`, and `git diff --check` pass.

## Execution Result - 2026-08-19

Steps 1-4 were executed. The retained diagnostic correction passed, all static
gates passed, and exactly four full acceptance scenarios completed. Electrical
window checks passed for 110/110 probes and 98/98 bounded transitions, with a
worst recovery ratio of 0.047469 VDD. The repair acceptance is **NO-GO**:
dynamic boundaries differed from the frozen estimates, so the explicit final
guard/lock-hold probes were not at the measured boundary plus one. No fifth
scenario or replacement sweep was run. See the task-owned `summary.json` and
`report.md` for measured candidates and the required next verification method.

## Second Repair - Consecutive Fine Probe Pairs

The first repair predicted the final fine code before HSPICE ran.  That is not
valid because a pre-rendered transient deck cannot branch on a measured fine
boundary.  The second repair removes fine-code prediction entirely.  At each
fine code the deck runs two consecutive complete probes:

```text
F0 scan, F0 repeat, F1 scan, F1 repeat, ... , FK scan, FK repeat
```

Offline classification uses only each code's first probe to find the first
non-stable-high boundary.  For `candidate = boundary + 1`, the candidate's
first probe is the guard and its second, distinct probe is lock-hold.  Both
probes must independently have two stable-low Q reads.

The normal trajectories use the retained dynamic coarse boundaries M8, M6,
and M4 at 0.80 V, 0.95 V, and 1.10 V, giving bases M6, M4, and M2.  These
coarse values schedule the deck; no retained fine value is an acceptance
input.

The forced-fallback trajectory is diagnostic-only: force coarse boundary M7,
scan paired F0..F9 at M5, and allow exactly one fallback to paired F0..F10 at
M6 only when every M5 scan observation is stable-high.  It must be labelled
as a forced diagnostic decision and must not be reported as a natural coarse
boundary.

Before electrical execution, focused tests must cover arbitrary and ambiguous
boundaries, an out-of-range guard, independent guard/hold failures, normal
no-fallback, the single M5-to-M6 fallback, forbidden early fallback, and exact
identity reuse.  `py_compile`, protocol generation without HSPICE, the focused
tests, and `git diff --check` must all pass.

The new electrical budget is exactly four complete scenarios: three normal
voltages and the 0.80 V forced-fallback trajectory.  Old acceptance identities
remain read-only.  No failed scenario authorizes a replacement or sweep.  GO
requires four new PASS identities, independent stable-low guard and lock-hold
probes, one active CK per probe, all bounded quiet windows passing, recovery
below 0.1 VDD, identical 0.80 V locks, unchanged retained hashes, and zero old
reruns.  Outputs remain in the existing task-owned analysis and run trees.

## Second Repair Execution Result - 2026-08-19

All static gates passed and exactly four v2 transistor-level scenarios ran.
All four manifests are PASS, every active probe has one CK edge, every bounded
configuration window passes, and the worst recovery ratio is below 0.1 VDD.
The paired fine method provides complete independent guard and lock-hold
evidence for M6/F10, M4/F6, M2/F9, and fallback M6/F10.

The aggregate repair remains **NO-GO**.  The retained v1 0.80 V normal M8
probe was ambiguous, with Q reads of -10.87008945 mV and 0.8003538944 V.  The
v2 normal M8 probe at the same read times was stable-high, with Q reads of
0.7999962746 V and 0.8001898629 V.  V2 therefore had no non-stable-high coarse
boundary through M8 and could not derive M6 from its own coarse scan.  The
remaining issue is coarse-boundary reproducibility at the DFF aperture, not
fine-code prediction or missing guard/hold evidence.  No fifth scenario,
replacement scenario, or sweep was run.

## Third Repair - Coarse Boundary Reproducibility

The second repair closed the fine-code evidence gap but exposed a separate
coarse-code problem.  At 0.80 V, M8 is inside the DFF falling-data aperture:
the retained v1 M8 probe was ambiguous while the v2 M8 probe was stable-high,
although all controls before the read time were identical.  A single coarse
probe therefore cannot control the protocol branch.

The third repair uses exactly two complete probes at every coarse code.  A
coarse code is confirmed only when both probes independently have two stable
low Q reads.  Stable-high, ambiguous, or high/low disagreement continues the
scan and is recorded as an aperture observation; it never confirms a boundary.
The first confirmed-low coarse code is the boundary and the medium base is
exactly two codes below it.

Because a pre-rendered deck cannot branch after the coarse scan, each voltage
pre-renders only the smallest allowed base-code window:

```text
0.80 V: coarse M0..M10; fine bases M7, M8, M9
0.95 V: coarse M0..M7;  fine bases M4, M5, M6
1.10 V: coarse M0..M5;  fine bases M2, M3, M4
```

Every base scans F0..FK with consecutive scan/repeat probes.  Offline
classification selects the base derived from the measured coarse boundary.
If that base has no boundary by F=K-1, it falls back exactly once to the next
pre-rendered base.  No second fallback or full medium/fine sweep is allowed.

All three normal scenarios must use one common transient stop time with only
post-probe quiet padding; padding cannot alter any valid probe or transition.
The third electrical budget is exactly three new complete normal scenarios at
0.80 V, 0.95 V, and 1.10 V.  The second repair's four completed manifests,
including its forced fallback, remain read-only evidence and are not rerun.

Before HSPICE, focused tests must cover coarse stable-high, stable-low,
ambiguous and high/low disagreement, boundary selection, allowed base windows,
one fine fallback, early/absent coarse boundary, common stop time, and exact
v3 identity reuse.  Static tests, compilation, contract generation, and
format checks must all pass before the three runs.

GO requires three new PASS identities; every coarse boundary must be confirmed
by an independent stable-low pair; every selected fine candidate must have
independent stable-low guard and lock-hold pairs; all active CK, quiet-window,
and recovery predicates must pass; retained hashes and all old rerun counters
must remain unchanged.  Any failure publishes NO-GO without another run.

## 第三版执行结果 - 2026-08-19

第三版静态门禁已通过：相关测试 21 项全部通过，动态协议及历史根因相关
测试共 40 项全部通过，运行器编译和格式检查通过，合同生成未启动 HSPICE。

按固定预算只运行了三个完整正常场景：0.80 V、0.95 V、1.10 V；三个且仅
三个第三版 PASS manifest 已生成，旧版四个场景只读复用且没有重跑。总计
314/314 活动探测恰好一个 CK，187/187 有界配置过渡通过，三个场景的粗调
边界均由双探测确认，细调 guard/lock-hold 均为独立稳定低对。

最终判定为 NO-GO，唯一失败条件是 0.80 V 场景恢复尾部最大为 0.303787 VDD，
超过 0.1 VDD。依据计划规定，未追加第五个场景、替代场景或 sweep。保留
诊断原始文件 SHA256 仍为
`ba581f3d376fa19a4414959e9891440bcb75e0d529c10ebfe967982d65589c60`，所有
旧重跑计数为零。

## 第四版后续改进 - 恢复 Gate 反查与单次诊断

第三版 NO-GO 的恢复失败不能直接解释为 `0.1 VDD` 阈值过严。现有证据表明
2.7 ns 的恢复时间没有覆盖第三版新增的 M10 和完整细调探索分支；上一版
恢复诊断只覆盖旧轨迹，因此必须先反查 Gate 的适用范围和时间推导。

本阶段只允许一次新的 0.80 V 诊断 HSPICE 场景，不运行新的正式验收场景，
不重跑旧场景，不修改硬件、DFF、延时单元、搜索轨迹或电压条件。诊断使用
第三版完整 0.80 V 轨迹，额外设置 5.0 ns 诊断观察上限，仅用于测量返回波。

第一步为无仿真 Gate 审计：区分探索探测、选中基础码、guard、lock-hold、
后续配置更新和终端探测；分别记录观测完整性、下一次操作前的恢复隔离和
最终锁定证据。`0.1 VDD` 继续作为操作隔离门槛，不得直接放宽为更高电压。

第二步为一次完整第三版 0.80 V 返回诊断：对 `xor_29`、`medium_out`、
`dff_ck` 测量第一次 0.1 VDD 上升/下降、第二次上升、观察终点以及最后
200 ps 的最大值和最小值。新恢复时间只允许由完整第三版诊断的最大返回下降
时间加 200 ps 向上取整到 0.1 ns 得出，不能继续固定使用 2.7 ns。

第三步为静态验证和只读发布：缺失返回测量、第二次上升沿、终点或尾部超限
均必须有明确原因；旧 manifest、原始文件哈希和重跑计数必须保持不变。若
诊断证实恢复时间不足，则发布新的测量结论但不宣布 GO；若证实 2.7 ns 内
已恢复，则只修正测量窗口或 Gate 聚合方式，仍需另行批准完整验收预算。

## 第四版执行结果 - 2026-08-19

无仿真 Gate 反查完成：0.80 V 共有 19 个恢复超限探测，全部存在后续操作，
不是终端探测误伤；guard、lock-hold 和选中细调分支没有恢复失败，失败集中
在粗调探索和未选细调探索。因此没有证据表明 `0.1 VDD` 门槛过严，更符合
完整第三版轨迹超出固定 2.7 ns 观察间隔的解释。

按唯一批准的诊断预算运行一个完整 0.80 V 第三版轨迹诊断场景。场景 manifest
为 PASS，listing 正常，测量返回记录为 110 个探测乘以 3 个节点共 330 条，
全部有效；第二次上升沿在各自有界观察窗内为 0 条。最坏记录为 medium M9、
fine F10 的 `dff_ck`，返回下降后的稳定时间为 2.575046 ns。按“最大下降时间
加 200 ps，再向上取整到 0.1 ns”的规定，候选恢复时间为 2.8 ns。5 ns 诊断
窗口的最后 200 ps 最大尾部仅约 `1.31e-5 VDD`，没有尾部超限或缺失测量。

本结果确认固定 2.7 ns 时间不足，但只发布新的测量结论，不宣布完整协议 GO，
也不追加正式验收场景。保留诊断原始文件 SHA256 仍为
`ba581f3d376fa19a4414959e9891440bcb75e0d529c10ebfe967982d65589c60`，旧版
manifest 数量、唯一新增诊断 manifest 和全部旧重跑计数均保持不变。
