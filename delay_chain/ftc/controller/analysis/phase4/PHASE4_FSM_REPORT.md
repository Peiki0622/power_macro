# Phase 4 - High-Level Calibration FSM Acceptance Report

**Date:** 2026-08-20  
**Status:** ✅ **GO**  
**Gate:** Calibration Algorithm FSM = GO

---

## Executive Summary

The high-level calibration FSM has been implemented and verified. All 3 nominal golden trajectories reproduce exactly, and all 6 failure detection modes operate correctly. The FSM correctly orchestrates the coarse search, two-step backoff, fine search, and guard/hold verification sequence.

---

## Implementation

**RTL Module:** `delay_chain/ftc/controller/rtl/ftc_cal_fsm.sv`

**State Machine:**
- 16 states implementing the calibration algorithm
- Coarse search with paired probe decision logic
- Exact two-step backoff (M_boundary → M-1 → M-2, zero probes between)
- Fine search with STABLE_HIGH continuation semantics
- Guard/hold dual-probe verification

**Interfaces:**
- Sequencer control (operation requests, configuration commands)
- Q classifier input (STABLE_LOW/STABLE_HIGH/AMBIGUOUS)
- Configuration register status (range flags)
- Top-level status outputs (cal_busy, cal_done, cal_fail, fail_reason)

---

## Verification Results

### Nominal Scenarios

| Scenario | VDD   | Expected | Actual | Operations | Result |
|----------|-------|----------|--------|------------|--------|
| Test 1   | 0.80V | M7/F6    | M7/F6  | 45         | ✅ PASS |
| Test 2   | 0.95V | M4/F6    | M4/F6  | 36         | ✅ PASS |
| Test 3   | 1.10V | M2/F9    | M2/F9  | 36         | ✅ PASS |

### Failure Detection

| Test | Failure Mode              | Detected | Fail Reason            | Result |
|------|---------------------------|----------|------------------------|--------|
| 4    | Coarse range exhausted    | Yes      | COARSE_RANGE_FAIL      | ✅ PASS |
| 5    | Backoff underflow         | Yes      | COARSE_BACKOFF_UNDERFLOW | ✅ PASS |
| 6    | Fine range exhausted      | Yes      | FINE_RANGE_FAIL        | ✅ PASS |
| 7    | Guard range exhausted     | Yes      | GUARD_RANGE_FAIL       | ✅ PASS |
| 8    | Guard not STABLE_LOW      | Yes      | GUARD_NOT_LOW          | ✅ PASS |
| 9    | Hold not STABLE_LOW       | Yes      | HOLD_NOT_LOW           | ✅ PASS |

---

## Algorithm Correctness Verification

**Coarse Search:**
- ✅ Paired probe decision: both probe A and B must be STABLE_LOW to confirm boundary
- ✅ Independent A/B results stored and evaluated together

**Two-Step Backoff:**
- ✅ Exactly 2 configuration decrements: M_boundary → M-1 → M-2
- ✅ Zero probes between backoff steps (verified in operation count)

**Fine Search:**
- ✅ STABLE_HIGH continues scanning
- ✅ STABLE_LOW or AMBIGUOUS confirms boundary

**Guard/Hold Verification:**
- ✅ Guard is F_boundary + 1
- ✅ Both guard and hold probes must independently be STABLE_LOW
- ✅ Lock asserted only after both verifications pass

---

## Behavioral Sensor Model

The testbench uses a scripted behavioral sensor model that returns predetermined Q classifications based on the current M/F configuration. This allows FSM verification independent of the transistor-level sensor.

**Operation Delays:**
- CONFIG_UPDATE: 3 cycles
- PROBE: 12 cycles

**Q Response Scripting:**
- Configurable per-scenario
- Returns STABLE_LOW, STABLE_HIGH, or AMBIGUOUS based on lookup table

---

## Artifacts

- **RTL:** `ftc_cal_fsm.sv` (1243 lines, fully commented)
- **Testbench:** `tb_ftc_cal_fsm.sv` (558 lines)
- **Simulation Log:** `phase4_vcs/sim.log`
- **Results:** `analysis/phase4/phase4_results.json`

---

## Gate Decision

**Calibration Algorithm FSM = GO**

The FSM correctly implements the frozen Phase 0 contract and reproduces all golden trajectories with exact operation counts. All failure detection modes operate correctly. Ready to proceed to Phase 5 (top-level integration).

---

## Next Phase

**Phase 5:** Integrate FSM with operation sequencer, Q sampler, and thermometer registers into `ftc_cal_controller_top.sv`. Create complete behavioral sensor model for end-to-end RTL verification.
