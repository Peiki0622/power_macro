// Low-level, cycle-quantized FTC operation sequencer.
//
// The high-level FSM requests an operation and waits for done_o.  This block
// alone owns sensor reset, sensor S_CLK, configuration-step timing, and the
// two Q-sample strobes.  All externally visible sensor controls are flops.
`timescale 1ns/1ps
`default_nettype none

module ftc_operation_sequencer (
    // Synchronous 400 MHz calibration clock from the active RF7 handoff.
    input  logic       cal_clk_i,
    // Active-low controller POR; sensor reset returns asserted during POR.
    input  logic       ctrl_por_n_i,
    // Request handshake.  cmd_i is consumed only when busy_o is low.
    input  logic       req_i,
    input  logic [1:0] cmd_i,
    // One-hot configuration action forwarded to thermometer registers.
    input  logic       medium_inc_i,
    input  logic       medium_dec_i,
    input  logic       fine_inc_i,
    input  logic       fine_dec_i,
    // Sensor asynchronous-DFF output fed to the separate Q sampler.
    input  logic       q_final_i,
    // Registered sensor controls.  These are the only controller-to-sensor
    // timing outputs, preventing an inferred combinational clock gate.
    output logic       sense_dff_reset_o,
    output logic       sense_s_clk_o,
    // One-cycle update action.  Configuration registers consume it on the
    // same cal_clk edge at which this sequencer accepts CONFIG_UPDATE.
    output logic       cfg_medium_inc_o,
    output logic       cfg_medium_dec_o,
    output logic       cfg_fine_inc_o,
    output logic       cfg_fine_dec_o,
    // Request status returned to the high-level FSM.
    output logic       busy_o,
    output logic       done_o,
    output logic       probe_done_o,
    // Classifier result from two actual controller sample registers.
    output logic [1:0] q_class_o,
    output logic       q_class_valid_o,
    // Explicit debug strobes permit testbench/SVA event accounting.
    output logic       q_sample_1_event_o,
    output logic       q_sample_2_event_o,
    // One-cycle acceptance markers.  These markers are observability-only;
    // they are registered with the same handshake edge that starts the
    // corresponding operation and do not participate in sensor control.
    output logic       config_update_event_o,
    output logic       probe_start_event_o
);
    import ftc_cal_pkg::*;
    localparam logic [1:0] OP_CONFIG_UPDATE = 2'b01;
    localparam logic [1:0] OP_PROBE = 2'b10;

    logic [3:0] probe_count_q;
    logic [1:0] active_cmd_q;
    logic sample_1_fire;
    logic sample_2_fire;
    logic sampler_class_valid;

    // These are combinational decodes of already registered sequencer state.
    // They are not clock gates: they are one-cycle data strobes presented to
    // the sampler at the same edge on which the corresponding event is
    // recorded below.
    always_comb begin
        sample_1_fire = busy_o && (active_cmd_q == OP_PROBE) &&
                        (probe_count_q == PROBE_Q_SAMPLE_1_CYCLE - 1);
        sample_2_fire = busy_o && (active_cmd_q == OP_PROBE) &&
                        (probe_count_q == PROBE_Q_SAMPLE_2_CYCLE - 1);
    end

    ftc_q_sampler u_q_sampler (
        .clk_i(cal_clk_i), .por_n_i(ctrl_por_n_i), .q_final_i(q_final_i),
        .sample_1_i(sample_1_fire), .sample_2_i(sample_2_fire),
        .q_sample_1_o(), .q_sample_2_o(), .class_valid_o(sampler_class_valid),
        .q_class_o(q_class_o));

    always_ff @(posedge cal_clk_i or negedge ctrl_por_n_i) begin
        if (!ctrl_por_n_i) begin
            sense_dff_reset_o <= 1'b1;
            sense_s_clk_o <= 1'b0;
            cfg_medium_inc_o <= 1'b0;
            cfg_medium_dec_o <= 1'b0;
            cfg_fine_inc_o <= 1'b0;
            cfg_fine_dec_o <= 1'b0;
            busy_o <= 1'b0;
            done_o <= 1'b0;
            probe_done_o <= 1'b0;
            q_sample_1_event_o <= 1'b0;
            q_sample_2_event_o <= 1'b0;
            q_class_valid_o <= 1'b0;
            config_update_event_o <= 1'b0;
            probe_start_event_o <= 1'b0;
            probe_count_q <= '0;
            active_cmd_q <= '0;
        end else begin
            // Defaults make all command/update/sample indications one cycle.
            done_o <= 1'b0;
            probe_done_o <= 1'b0;
            cfg_medium_inc_o <= 1'b0;
            cfg_medium_dec_o <= 1'b0;
            cfg_fine_inc_o <= 1'b0;
            cfg_fine_dec_o <= 1'b0;
            q_sample_1_event_o <= 1'b0;
            q_sample_2_event_o <= 1'b0;
            config_update_event_o <= 1'b0;
            probe_start_event_o <= 1'b0;
            // Hold the classifier-valid indication through probe completion
            // so the high-level FSM observes a coherent result at seq_done.
            if (sampler_class_valid)
                q_class_valid_o <= 1'b1;

            if (!busy_o) begin
                sense_dff_reset_o <= 1'b1;
                sense_s_clk_o <= 1'b0;
                if (req_i && (cmd_i == OP_CONFIG_UPDATE)) begin
                    // The configuration pulse is emitted while the sensor is
                    // quiet.  The following busy cycle is the physically
                    // derived one-cycle settle interval in the RF7 contract.
                    busy_o <= 1'b1;
                    active_cmd_q <= OP_CONFIG_UPDATE;
                    probe_count_q <= '0;
                    q_class_valid_o <= 1'b0;
                    config_update_event_o <= 1'b1;
                    cfg_medium_inc_o <= medium_inc_i;
                    cfg_medium_dec_o <= medium_dec_i;
                    cfg_fine_inc_o <= fine_inc_i;
                    cfg_fine_dec_o <= fine_dec_i;
                end else if (req_i && (cmd_i == OP_PROBE)) begin
                    // Acceptance is local probe cycle 0: reset is released.
                    busy_o <= 1'b1;
                    active_cmd_q <= OP_PROBE;
                    probe_count_q <= '0;
                    probe_start_event_o <= 1'b1;
                    sense_dff_reset_o <= 1'b0;
                end
            end else if (active_cmd_q == OP_CONFIG_UPDATE) begin
                if (probe_count_q == CONFIG_SETTLE_CYCLES - 1) begin
                    busy_o <= 1'b0;
                    done_o <= 1'b1;
                end else begin
                    probe_count_q <= probe_count_q + 1'b1;
                end
            end else begin
                // probe_count_q denotes the elapsed local-cycle slot after
                // reset release.  Constants are audited against the active
                // RF7 JSON handoff before synthesis and timing verification.
                if (probe_count_q == PROBE_SCLK_RISE_CYCLE - 1)
                    sense_s_clk_o <= 1'b1;
                if (probe_count_q == PROBE_Q_SAMPLE_1_CYCLE - 1) begin
                    q_sample_1_event_o <= 1'b1;
                end
                if (probe_count_q == PROBE_Q_SAMPLE_2_CYCLE - 1) begin
                    q_sample_2_event_o <= 1'b1;
                end
                if (probe_count_q == PROBE_RESET_ASSERT_CYCLE - 1)
                    sense_dff_reset_o <= 1'b1;
                if (probe_count_q == PROBE_SCLK_FALL_CYCLE - 1)
                    sense_s_clk_o <= 1'b0;
                if (probe_count_q == PROBE_RECOVERY_DONE_CYCLE - 1) begin
                    busy_o <= 1'b0;
                    done_o <= 1'b1;
                    probe_done_o <= 1'b1;
                end else begin
                    probe_count_q <= probe_count_q + 1'b1;
                end
            end
        end
    end
endmodule

`default_nettype wire
