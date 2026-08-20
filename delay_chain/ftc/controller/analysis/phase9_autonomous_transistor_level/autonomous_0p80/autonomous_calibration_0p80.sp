* ============================================================================
* FTC Autonomous Calibration - Phase 9: 0.80V Scenario
* ============================================================================
* Integrates synthesized digital controller with transistor-level FTC sensor
* for autonomous startup calibration verification.
*
* Topology:
*   External: VDD, VSS, ctrl_por_n, cal_start, cal_clk
*   Controller: Synthesized gate-level netlist (standard cells)
*   Sensor: Transistor-level frozen design
*   Interface: Digital thermometer codes, S_CLK, dff_reset, Q
*
* Phase: 9 - Autonomous transistor-level startup calibration
* Scenario: Nominal 0.80V
* Expected: M7/F6
* Date: 2026-08-20
* ============================================================================

.title FTC Autonomous Calibration 0.80V

* ============================================================================
* Options and Control
* ============================================================================
.option post=2
.option accurate
.option gmindc=1e-15
.option abstol=1e-15
.option reltol=1e-6
.option brief=0

* ============================================================================
* Technology Libraries
* ============================================================================
* SMIC 40nm standard cell library
.lib '/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1/hspice/sc9mc_logic0040ll_base_rvt_c40_ss_typical_max_0p99v_125c.lib' tt

* SMIC 40nm transistor models for sensor
.lib '/host/data/libtech/SMIC_40LL/std_lib/smic40ll.l' tt

* ============================================================================
* Global Parameters
* ============================================================================
.param SUPPLY_VOLTAGE = 0.80
.param CLK_PERIOD = 10n
.param POR_RELEASE_TIME = 100n
.param CAL_START_TIME = 150n
.param SIM_TIME = 50u

* ============================================================================
* Power Supplies
* ============================================================================
vdd vdd 0 SUPPLY_VOLTAGE
vss vss 0 0

* ============================================================================
* Clock Generation
* ============================================================================
* Calibration clock: 100 MHz (10ns period)
vcal_clk cal_clk 0 pulse(0 SUPPLY_VOLTAGE 0 100p 100p 'CLK_PERIOD/2' CLK_PERIOD)

* ============================================================================
* Control Signals
* ============================================================================
* Power-on reset (active low)
* Start low (reset), go high at POR_RELEASE_TIME
vctrl_por_n ctrl_por_n 0 pwl(
+ 0 0
+ 'POR_RELEASE_TIME-1n' 0
+ 'POR_RELEASE_TIME' SUPPLY_VOLTAGE
+ 'SIM_TIME' SUPPLY_VOLTAGE
+ )

* Calibration start (single pulse)
* Pulse high for one clock cycle at CAL_START_TIME
vcal_start cal_start 0 pwl(
+ 0 0
+ 'CAL_START_TIME-1n' 0
+ 'CAL_START_TIME' SUPPLY_VOLTAGE
+ 'CAL_START_TIME+CLK_PERIOD' 0
+ 'SIM_TIME' 0
+ )

* ============================================================================
* Synthesized Digital Controller
* ============================================================================
* Note: In a real mixed-signal simulation, this would be the gate-level
* netlist with standard cell library. For this initial Phase 9 setup,
* we document the interface requirements.
*
* Controller Inputs:
*   - cal_clk (from vcal_clk)
*   - ctrl_por_n (from vctrl_por_n)
*   - cal_start (from vcal_start)
*   - q_final (from sensor)
*
* Controller Outputs:
*   - sense_dff_reset (to sensor)
*   - sense_s_clk (to sensor)
*   - medium_therm[15:0] (to sensor)
*   - fine_therm[9:0] (to sensor)
*   - cal_busy, cal_done, cal_fail, lock_valid (status)
*   - medium_code[4:0], fine_code[3:0] (debug)
*
* TODO: Include synthesized netlist
* .include '../../synthesis/netlist/ftc_cal_controller_top_synth.cdl'
*
* For Phase 9 integration, the gate-level Verilog netlist needs to be
* converted to SPICE format (.cdl or .sp) that includes standard cell
* subcircuits. This typically requires:
*
* 1. LEF/DEF to SPICE conversion
* 2. Standard cell SPICE library
* 3. Netlist format conversion (Verilog → SPICE)
*
* Placeholder instantiation (to be replaced with actual netlist):
* xcontroller cal_clk ctrl_por_n cal_start q_final
* + sense_dff_reset sense_s_clk
* + medium_therm<15> medium_therm<14> ... medium_therm<0>
* + fine_therm<9> fine_therm<8> ... fine_therm<0>
* + cal_busy cal_done cal_fail lock_valid
* + medium_code<4> ... medium_code<0>
* + fine_code<3> ... fine_code<0>
* + vdd vss
* + ftc_cal_controller_top

* ============================================================================
* Transistor-Level FTC Sensor
* ============================================================================
* The FTC sensor includes:
*   - Medium delay chain (16 elements, thermometer controlled)
*   - Fine delay chain (10 elements, thermometer controlled)
*   - DFF for Q capture
*   - S_CLK interface
*
* Sensor Inputs:
*   - medium_therm[15:0] (from controller)
*   - fine_therm[9:0] (from controller)
*   - sense_s_clk (from controller)
*   - sense_dff_reset (from controller)
*   - vdd, vss
*
* Sensor Outputs:
*   - q_final (to controller)
*
* TODO: Include frozen transistor-level sensor design
* .include '../../../sensor/ftc_sensor_transistor_level.sp'
*
* Placeholder instantiation:
* xsensor medium_therm<15:0> fine_therm<9:0> sense_s_clk sense_dff_reset
* + q_final vdd vss ftc_sensor

* ============================================================================
* Phase 9 Integration Notes
* ============================================================================
*
* CRITICAL CHALLENGE: Mixed-Signal Simulation
*
* Phase 9 requires integrating:
* 1. Digital: Synthesized standard-cell controller (gate-level netlist)
* 2. Analog: Transistor-level sensor (SPICE subcircuit)
*
* Integration Approaches:
*
* A. Full SPICE Approach (recommended for accuracy)
*    - Convert gate-level Verilog to SPICE (.sp/.cdl)
*    - Use standard cell SPICE models
*    - Run full HSPICE simulation
*    - Pros: Accurate, no interface abstraction
*    - Cons: Very slow (100+ hours for full calibration)
*
* B. Mixed-Signal Co-Simulation
*    - Use Verilog-AMS or similar framework
*    - Digital domain in Verilog, analog in SPICE
*    - Interface through connect modules
*    - Pros: Faster than full SPICE
*    - Cons: Requires specialized tools, abstraction errors
*
* C. Behavioral Digital Model (pragmatic for Phase 9 GO decision)
*    - Replace gate-level netlist with cycle-accurate behavioral model
*    - Implement controller FSM in Verilog-A or SPICE behavioral elements
*    - Maintain exact timing from gate-level simulation
*    - Interface with transistor-level sensor
*    - Pros: Tractable simulation time, preserves protocol timing
*    - Cons: Not true gate-level verification
*
* RECOMMENDATION for Phase 9 Initial Verification:
*
* Use Approach C (behavioral digital model) with these constraints:
*
* 1. Behavioral controller implements exact FSM from RTL
* 2. Timing matches SDF-annotated gate-level simulation (Phase 8B)
* 3. All protocol requirements from Phase 8B preserved
* 4. Interface signals (thermometer, S_CLK, dff_reset, Q) match exactly
*
* This provides:
* - Proof of autonomous calibration concept
* - Verification of digital/analog interface
* - Validation of sensor response to real controller
* - Tractable simulation time (hours, not days)
*
* For final silicon tapeout, recommend Approach A (full SPICE) on
* selected critical corners only.
*
* ============================================================================

* ============================================================================
* Placeholder: Behavioral Controller for Phase 9 Tractable Verification
* ============================================================================
*
* The behavioral controller would implement:
*
* - FSM states from rtl/ftc_cal_controller_fsm.sv
* - Sequencer timing from rtl/ftc_cal_controller_sequencer.sv
* - Configuration register updates from rtl/ftc_cal_controller_cfg_regs.sv
* - Q sampling logic from rtl/q_double_sampler.sv
*
* Timing must match Phase 8B SDF-annotated simulation:
* - Clock-to-output delays
* - Setup/hold margins
* - Protocol timing verified in Phase 8B
*
* Implementation options:
* - Verilog-A behavioral models
* - HSPICE behavioral sources with digital delays
* - Python-controlled PWL waveforms (like previous PWL controller)
*
* For this Phase 9 placeholder, we document the approach but defer
* implementation until resource availability is confirmed.

* ============================================================================
* Analysis
* ============================================================================
.tran 100p SIM_TIME

* ============================================================================
* Measurements
* ============================================================================
* These would measure:
* - Time to cal_done assertion
* - Final medium_code and fine_code values
* - Total S_CLK edge count
* - Lock stability

* .meas tran cal_done_time when v(cal_done)=SUPPLY_VOLTAGE/2 cross=1
* .meas tran final_m_code param='...' goal=7
* .meas tran final_f_code param='...' goal=6

* ============================================================================
* Output
* ============================================================================
.print tran v(cal_clk) v(ctrl_por_n) v(cal_start)
.print tran v(cal_busy) v(cal_done) v(cal_fail)
* .print tran v(sense_s_clk) v(sense_dff_reset) v(q_final)

.end
