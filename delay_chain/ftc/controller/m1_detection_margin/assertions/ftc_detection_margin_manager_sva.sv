// ============================================================================
// M1 manager protocol assertions
// ============================================================================
// These properties observe the manager's public detector-side interface.  They
// intentionally allow the initial snapshot preload before DET ownership, but
// require any non-snapshot target application to occur only after H0 grants
// ownership and while the detector remains reset and unclocked.
// ============================================================================
`timescale 1ns/1ps
`default_nettype none

module ftc_detection_margin_manager_sva (
    // Trusted sequencing clock and POR for all temporal properties.
    input logic        cal_clk_i,
    input logic        ctrl_por_n_i,

    // H0 snapshot/ownership inputs used to distinguish preload from apply.
    input logic [15:0] cal_medium_therm_snapshot_i,
    input logic [9:0]  cal_fine_therm_snapshot_i,
    input logic        det_owner_valid_i,

    // Manager detector inputs and status outputs under verification.
    input logic        det_takeover_ready_o,
    input logic        det_sense_dff_reset_o,
    input logic        det_sense_s_clk_o,
    input logic [15:0] det_medium_therm_o,
    input logic [9:0]  det_fine_therm_o,
    input logic        margin_cfg_valid_o,
    input logic        mapping_supported_o
);
    // POR is asynchronous and may assert/deassert entirely between cal_clk_i
    // edges.  This sampled flag records every such event and suppresses only
    // the first post-POR comparison, where $changed legitimately observes the
    // reset vector rather than a protocol-driven preload or margin apply.
    logic por_seen_by_clock_q;
    always_ff @(posedge cal_clk_i or negedge ctrl_por_n_i) begin
        if (!ctrl_por_n_i)
            por_seen_by_clock_q <= 1'b0;
        else
            por_seen_by_clock_q <= 1'b1;
    end

    // M1 must never create a runtime detection probe.  This is deliberately
    // unconditional after POR rather than limited to a particular FSM state.
    property p_no_probe_clock;
        @(posedge cal_clk_i) disable iff (!ctrl_por_n_i)
            det_sense_s_clk_o == 1'b0;
    endproperty
    a_no_probe_clock: assert property (p_no_probe_clock)
        else $error("M1 SVA: detector S_CLK must remain low");

    // Readiness is legal only after an exact supported mapping is latched and
    // all detector-side safe controls equal the H0 raw snapshot.
    property p_preload_is_snapshot_equal;
        @(posedge cal_clk_i) disable iff (!ctrl_por_n_i)
            det_takeover_ready_o |->
                mapping_supported_o && det_sense_dff_reset_o && !det_sense_s_clk_o &&
                det_medium_therm_o == cal_medium_therm_snapshot_i &&
                det_fine_therm_o == cal_fine_therm_snapshot_i;
    endproperty
    a_preload_is_snapshot_equal: assert property (p_preload_is_snapshot_equal)
        else $error("M1 SVA: takeover ready without exact snapshot preload");

    // A control-vector change before ownership is permitted only for the
    // snapshot preload itself.  Once ownership exists, it still must happen
    // under reset-high/S_CLK-low safe conditions.
    property p_vector_change_is_safe;
        @(posedge cal_clk_i) disable iff (!ctrl_por_n_i)
            (por_seen_by_clock_q &&
             ($changed(det_medium_therm_o) || $changed(det_fine_therm_o))) |->
                det_sense_dff_reset_o && !det_sense_s_clk_o &&
                (det_owner_valid_i ||
                 ((det_medium_therm_o == cal_medium_therm_snapshot_i) &&
                  (det_fine_therm_o == cal_fine_therm_snapshot_i)));
    endproperty
    a_vector_change_is_safe: assert property (p_vector_change_is_safe)
        else $error("M1 SVA: unsafe non-snapshot detector-vector change");

    // Valid cannot be declared on the same sampled cycle as a post-owner
    // target-vector update.  The RTL promotes valid on the following edge,
    // after one full 2.5 ns controller period has elapsed.
    property p_target_change_waits_one_cycle;
        @(posedge cal_clk_i) disable iff (!ctrl_por_n_i)
            (por_seen_by_clock_q && det_owner_valid_i &&
             ($changed(det_medium_therm_o) || $changed(det_fine_therm_o))) |->
                !margin_cfg_valid_o ##1 margin_cfg_valid_o;
    endproperty
    a_target_change_waits_one_cycle: assert property (p_target_change_waits_one_cycle)
        else $error("M1 SVA: margin valid did not wait one full controller cycle");

    // A published configuration must have passed H0 ownership and retain the
    // inactive sensor controls; D0 alone is allowed to change those later.
    property p_valid_requires_safe_owner;
        @(posedge cal_clk_i) disable iff (!ctrl_por_n_i)
            margin_cfg_valid_o |-> det_owner_valid_i &&
                                  det_sense_dff_reset_o && !det_sense_s_clk_o;
    endproperty
    a_valid_requires_safe_owner: assert property (p_valid_requires_safe_owner)
        else $error("M1 SVA: valid configuration lacks safe DET ownership");
endmodule

`default_nettype wire
