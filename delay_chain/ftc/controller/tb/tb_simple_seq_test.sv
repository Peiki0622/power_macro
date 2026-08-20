//==============================================================================
// Simple Sequencer Test
// Purpose: Verify operation sequencer responds to commands and completes
//==============================================================================

`timescale 1ns / 1ps

module tb_simple_seq_test;
    import ftc_cal_pkg::*;

    // Clock and reset
    logic cal_clk;
    logic ctrl_por_n;

    // Sequencer request interface
    logic       seq_req;
    logic [1:0] seq_cmd;
    logic       seq_medium_inc;
    logic       seq_medium_dec;
    logic       seq_fine_inc;
    logic       seq_fine_dec;

    // Sequencer status
    logic       seq_busy;
    logic       seq_done;
    logic       seq_probe_done;
    logic [1:0] seq_q_class;
    logic       seq_q_class_valid;

    // Sensor signals
    logic       sense_dff_reset;
    logic       sense_s_clk;
    logic       q_final;

    // Debug strobes
    logic       q_sample_1_event;
    logic       q_sample_2_event;

    // Clock generation: 1 GHz (1 ns period)
    initial cal_clk = 0;
    always #0.5 cal_clk = ~cal_clk;

    // DUT: Operation Sequencer
    ftc_operation_sequencer u_sequencer (
        .cal_clk_i           (cal_clk),
        .ctrl_por_n_i        (ctrl_por_n),
        .req_i               (seq_req),
        .cmd_i               (seq_cmd),
        .medium_inc_i        (seq_medium_inc),
        .medium_dec_i        (seq_medium_dec),
        .fine_inc_i          (seq_fine_inc),
        .fine_dec_i          (seq_fine_dec),
        .q_final_i           (q_final),
        .sense_dff_reset_o   (sense_dff_reset),
        .sense_s_clk_o       (sense_s_clk),
        .cfg_medium_inc_o    (),
        .cfg_medium_dec_o    (),
        .cfg_fine_inc_o      (),
        .cfg_fine_dec_o      (),
        .busy_o              (seq_busy),
        .done_o              (seq_done),
        .probe_done_o        (seq_probe_done),
        .q_class_o           (seq_q_class),
        .q_class_valid_o     (seq_q_class_valid),
        .q_sample_1_event_o  (q_sample_1_event),
        .q_sample_2_event_o  (q_sample_2_event)
    );

    // Test stimulus
    initial begin
        $display("=== Simple Sequencer Test ===");

        // Initialize
        ctrl_por_n = 0;
        seq_req = 0;
        seq_cmd = 2'b00;
        seq_medium_inc = 0;
        seq_medium_dec = 0;
        seq_fine_inc = 0;
        seq_fine_dec = 0;
        q_final = 0;

        repeat(10) @(posedge cal_clk);
        ctrl_por_n = 1;
        $display("Time %0t: Released POR", $time);

        repeat(5) @(posedge cal_clk);

        // Test 1: Issue PROBE operation (cmd=10)
        $display("\nTime %0t: Starting PROBE operation", $time);
        @(posedge cal_clk);
        seq_req = 1;
        seq_cmd = 2'b10;  // OP_PROBE
        @(posedge cal_clk);
        seq_req = 0;

        // Monitor progress with timeout
        fork
            begin
                while (!seq_done) begin
                    @(posedge cal_clk);
                    $display("  Time %0t: busy=%b, done=%b, reset=%b, s_clk=%b",
                             $time, seq_busy, seq_done, sense_dff_reset, sense_s_clk);
                end
            end
            begin
                #200ns;
                if (!seq_done) begin
                    $display("ERROR: PROBE operation timeout");
                    $finish;
                end
            end
        join_any
        disable fork;

        $display("Time %0t: PROBE complete, q_class=%2b, valid=%b",
                 $time, seq_q_class, seq_q_class_valid);

        repeat(10) @(posedge cal_clk);

        $display("\n=== PASS: Sequencer responds to commands ===");
        $finish;
    end

    // Provide Q response: after S_CLK rises, set q_final
    always @(posedge sense_s_clk) begin
        #2ns;
        q_final = 1;
    end

endmodule
