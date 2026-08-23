// ============================================================================
// M1 stage-top elaboration and inactive-detector integration check
// ============================================================================
// Detailed protocol coverage is performed by tb_ftc_detection_margin_manager.
// This complementary test elaborates the real frozen H0 calibration wrapper
// beneath the new M1 stage top and confirms that, before D0 exists, the public
// detector clock remains low and reset remains high throughout idle operation.
// ============================================================================
`timescale 1ns/1ps
`default_nettype none

module tb_ftc_cal_detect_margin_top;
    logic cal_clk;
    logic ctrl_por_n;
    logic cal_start;
    logic q_final;
    logic [1:0] margin_sel;
    logic margin_select_valid;
    logic sense_dff_reset;
    logic sense_s_clk;
    logic [15:0] medium_therm;
    logic [9:0] fine_therm;
    logic margin_cfg_valid;
    logic mapping_supported;
    logic trip_qualified;
    logic margin_protocol_error;
    logic [4:0] m_det;
    logic [3:0] f_det;
    logic [1:0] margin_level;
    integer failures;

    initial begin
        cal_clk = 1'b0;
        forever #1.25 cal_clk = ~cal_clk;
    end

    ftc_cal_detect_margin_top dut (
        .cal_clk_i(cal_clk),
        .ctrl_por_n_i(ctrl_por_n),
        .cal_start_i(cal_start),
        .q_final_i(q_final),
        .margin_sel_i(margin_sel),
        .margin_select_valid_i(margin_select_valid),
        .sense_dff_reset_o(sense_dff_reset),
        .sense_s_clk_o(sense_s_clk),
        .medium_therm_o(medium_therm),
        .fine_therm_o(fine_therm),
        .cal_busy_o(), .cal_done_o(), .cal_fail_o(), .lock_valid_o(),
        .medium_code_o(), .fine_code_o(), .fail_reason_o(), .fsm_state_o(),
        .q_sample_1_event_o(), .q_sample_2_event_o(), .config_update_event_o(),
        .probe_start_event_o(), .cal_cfg_valid_o(), .cal_medium_code_snapshot_o(),
        .cal_fine_code_snapshot_o(), .cal_medium_therm_snapshot_o(),
        .cal_fine_therm_snapshot_o(), .det_prepare_o(), .det_owner_valid_o(),
        .handoff_blocked_o(), .handoff_protocol_error_o(), .handoff_state_o(),
        .margin_cfg_valid_o(margin_cfg_valid),
        .mapping_supported_o(mapping_supported),
        .trip_qualified_o(trip_qualified),
        .margin_protocol_error_o(margin_protocol_error),
        .m_det_o(m_det), .f_det_o(f_det), .margin_level_o(margin_level)
    );

    always @(sense_s_clk) begin
        if (ctrl_por_n && sense_s_clk !== 1'b0) begin
            $display("FAIL M1 stage top emitted an inactive-stage sensor clock");
            failures = failures + 1;
        end
    end

    initial begin
        failures = 0;
        ctrl_por_n = 1'b0;
        cal_start = 1'b0;
        q_final = 1'b0;
        margin_sel = 2'd0;
        margin_select_valid = 1'b0;
        repeat (2) @(posedge cal_clk);
        #0.20;
        ctrl_por_n = 1'b1;
        repeat (3) @(posedge cal_clk);
        #0.02;
        if (sense_dff_reset !== 1'b1 || sense_s_clk !== 1'b0 ||
            margin_cfg_valid || mapping_supported || trip_qualified ||
            margin_protocol_error) begin
            $display("FAIL M1 stage top idle contract violated");
            failures = failures + 1;
        end
        if (failures != 0) $fatal(1);
        $display("M1 stage-top elaboration PASS: H0 child is idle and M1 detector remains inactive");
        $finish;
    end
endmodule

`default_nettype wire
