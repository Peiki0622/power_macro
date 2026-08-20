# FTC Calibration Controller - Synthesis and Gate-Level Verification Report

**Phase:** 7-8  
**Date:** 2026-08-20  
**Status:** Phase 7 Complete, Phase 8A In Progress

---

## Phase 7: Controller Synthesis - COMPLETE ✓

### Summary

Successfully synthesized the FTC calibration controller using Synopsys Design Compiler W-2024.09 with SMIC 40nm LL standard cell library (sc9mc_base_rvt_c40).

### Key Results

**Timing:**
- **Target Clock:** 1.0 ns (1 GHz)
- **Critical Path:** 0.86 ns
- **Setup Slack:** 0.02 ns (MET)
- **Hold Slack:** 0.00 ns (MET)
- **Levels of Logic:** 8
- **WNS (Worst Negative Slack):** 0.00 ns
- **TNS (Total Negative Slack):** 0.00 ns
- **Violating Paths:** 0

**Area:**
- **Total Cell Area:** 947.55 µm²
- **Combinational Area:** 549.90 µm²
- **Sequential Area:** 397.64 µm²
- **Leaf Cell Count:** 495 cells
- **Sequential Cells:** 76 flip-flops
- **Buffer/Inverter Count:** 106 cells

**Hierarchy:**
- ftc_cal_controller_top: 100% (947.55 µm²)
  - Local combinational: 549.90 µm²
  - Local sequential: 397.64 µm²
  - No black boxes (all modules synthesized correctly)

**Power:** (Estimated at synthesis, high analysis effort)
- Dynamic power analysis available in reports/power.rpt

### Technology Details

**Library:** SMIC 40LL Low Leakage  
**Variant:** sc9mc_base_rvt_c40 (9-track, Regular Vt)  
**Corner:** ss_typical_max_0p99v_125c (worst case for setup)  
**Voltage:** 0.99V  
**Temperature:** 125°C  

### Files Generated

**Netlist:**
- `synthesis/netlist/ftc_cal_controller_top_synth.v` - Verilog gate-level netlist (42KB)
- `synthesis/netlist/ftc_cal_controller_top_synth.sdc` - Synopsys Design Constraints (4.0KB)

**Reports:**
- `synthesis/reports/qor.rpt` - Quality of Results summary
- `synthesis/reports/timing.rpt` - Detailed timing paths
- `synthesis/reports/area.rpt` - Area breakdown
- `synthesis/reports/power.rpt` - Power analysis
- `synthesis/reports/synthesis.log` - Full synthesis log (37KB)

### RTL Corrections Made

During synthesis, port width mismatches were discovered and corrected in `ftc_cal_controller_top.sv`:

1. **medium_code:** Changed from `[3:0]` to `[4:0]` to match `MEDIUM_CODE_WIDTH=5`
2. **fsm_state:** Changed from `[3:0]` to `[4:0]` to match FSM encoding (12 states require 5 bits)

These corrections ensure proper connectivity with submodules using parameterized widths.

### Synthesis Quality Assessment

**Timing:**
- ✓ Met 1 GHz target with 20 ps positive slack
- ✓ Critical path well-balanced at 8 logic levels
- ✓ No timing violations

**Area:**
- ✓ Compact design: < 1000 µm² total area
- ✓ Reasonable buffer/inverter percentage (21.4%)
- ✓ Good sequential/combinational balance

**Design Quality:**
- ✓ All modules successfully synthesized (no black boxes)
- ✓ No design rule violations (max_trans, max_cap)
- ✓ Clean linking and elaboration

### Next Steps

Proceed to Phase 8: Gate-level verification using the synthesized netlist.

---

## Phase 8A: Gate-Level Functional Simulation - IN PROGRESS

### Objective

Verify that synthesis preserved controller behavior by running the same test scenarios as RTL Phase 5, using the synthesized gate-level netlist with the behavioral sensor model.

### Test Scenarios

1. **Nominal 0.80V:** Expected M7/F6
2. **Nominal 0.95V:** Expected M4/F6
3. **Nominal 1.10V:** Expected M2/F9

### Current Status

**Infrastructure Created:**
- ✓ Gate-level testbench: `analysis/phase8_gate_level/functional/tb_gate_level_functional.sv`
- ✓ Simulation script: `run_gate_level_sim.sh`
- ✓ VCS compilation successful

**Simulation Challenges:**
- Initial clock period (1ns / 1 GHz) caused timing violations in gate-level primitives
- Relaxed clock to 10ns (100 MHz) for functional verification
- Simulation timeout increased to 500 µs to accommodate slower clock
- Currently debugging: Controller signals showing 'x' (undefined) state

**Next Actions:**
1. Add explicit initialization for gate-level simulation
2. Check reset sequence timing
3. Verify sensor model response timing matches gate delays
4. Complete functional verification for all three scenarios
5. Document operation counts and compare with RTL results

### Phase 8B: Delayed Gate-Level Simulation

**Status:** Not started (requires Phase 8A completion)

**Planned Approach:**
- Use SDF back-annotation for accurate cell delays
- Verify timing-critical requirements:
  - One probe → exactly one S_CLK rising edge
  - One config command → exactly one thermometer bit change
  - Reset sequencing obeys frozen cycle contract
  - Q sample events occur in intended controller cycles
  - No synthesis delay produces double-trigger or skipped operation
  - Lock freezes physical control vectors

---

## Tools and Environment

**Synthesis:**
- Synopsys Design Compiler Graphical W-2024.09
- Wrapper script: `/home/zhupl25/.local/bin/dc_shell` (with compatibility libraries)

**Simulation:**
- Synopsys VCS W-2024.09_Full64
- SystemVerilog support enabled
- Waveform dumping: VCD format

**Standard Cells:**
- Path: `/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/`
- Library: `SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1/`
- Formats: `.db` (synthesis), `.v` (simulation), `.lib` (Liberty)

---

## Open Issues

### Phase 7 (Synthesis)
- None. Phase complete and passing.

### Phase 8A (Gate-Level Functional)
1. **Issue:** Controller outputs showing undefined ('x') state in gate-level simulation
   - **Status:** Under investigation
   - **Hypothesis:** Initialization or reset timing issue
   - **Action:** Debug reset sequence, check for uninitialized latches

2. **Issue:** Simulation timeout at 100 µs with 10ns clock
   - **Status:** Timeout extended to 500 µs
   - **Action:** Monitor next run, may need further adjustment

---

## References

- **Plan Document:** `plans/ftc_synthesizable_startup_calibration_controller_plan.md`
- **RTL Source:** `delay_chain/ftc/controller/rtl/`
- **Synthesis Scripts:** `delay_chain/ftc/controller/synthesis/scripts/`
- **Gate-Level Verification:** `delay_chain/ftc/controller/analysis/phase8_gate_level/`

---

**Report Generated:** 2026-08-20  
**Author:** Autonomous FTC Controller Implementation  
**Next Update:** Upon Phase 8A completion
