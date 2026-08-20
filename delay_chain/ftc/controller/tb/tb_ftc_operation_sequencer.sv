`timescale 1ns/1ps
`default_nettype none

module tb_ftc_operation_sequencer;
    logic clk = 0, por_n = 0, req = 0;
    logic [1:0] cmd = 0;
    logic mi=0, md=0, fi=0, fd=0, q=0;
    logic rst, sclk, cmi, cmdc, cfi, cfd, busy, done, p_done;
    logic [1:0] cls; logic cls_v, s1, s2;
    always #5 clk = ~clk;
    ftc_operation_sequencer dut (
        .cal_clk_i(clk), .ctrl_por_n_i(por_n), .req_i(req), .cmd_i(cmd),
        .medium_inc_i(mi), .medium_dec_i(md), .fine_inc_i(fi), .fine_dec_i(fd),
        .q_final_i(q), .sense_dff_reset_o(rst), .sense_s_clk_o(sclk),
        .cfg_medium_inc_o(cmi), .cfg_medium_dec_o(cmdc), .cfg_fine_inc_o(cfi),
        .cfg_fine_dec_o(cfd), .busy_o(busy), .done_o(done), .probe_done_o(p_done),
        .q_class_o(cls), .q_class_valid_o(cls_v), .q_sample_1_event_o(s1),
        .q_sample_2_event_o(s2));

    integer rise_count, sample_count;
    logic [1:0] observed_class;
    logic observed_class_valid;
    always @(posedge sclk) rise_count = rise_count + 1;
    always @(posedge s1 or posedge s2) sample_count = sample_count + 1;
    // class_valid is intentionally a one-cycle response at sample #2.  The
    // testbench records it so operation completion can check the result after
    // the required recovery window without changing the RTL protocol.
    always @(posedge clk) begin
        if (cls_v) begin
            observed_class <= cls;
            observed_class_valid <= 1'b1;
        end
    end
    task automatic tick; begin @(posedge clk); #1; end endtask
    initial begin
        rise_count = 0; sample_count = 0; observed_class = 2'b11; observed_class_valid = 0;
        repeat (2) @(posedge clk); #1 por_n = 1;
        // CONFIG_UPDATE: action pulse at acceptance, done after two cycles.
        cmd = 2'b01; mi = 1; req = 1; tick(); req = 0; mi = 0;
        if (!busy || !rst || sclk || !cmi) begin
            $display("config values busy=%b rst=%b sclk=%b cmi=%b done=%b", busy, rst, sclk, cmi, done);
            $fatal(1, "config acceptance");
        end
        tick(); if (done) $fatal(1, "config done too early");
        tick(); if (!done || busy) $fatal(1, "config settle count");

        // PROBE with stable-low Q samples.
        cmd = 2'b10; req = 1; tick(); req = 0;
        if (!busy || rst || sclk) $fatal(1, "probe acceptance");
        tick(); if (!sclk || rst) $fatal(1, "sclk rise cycle");
        tick(); tick();
        q = 0; tick(); if (!s1) $fatal(1, "sample1 cycle");
        tick(); if (!s2) $fatal(1, "sample2 cycle");
        tick(); if (!rst) $fatal(1, "reset assert cycle");
        tick(); if (sclk) $fatal(1, "sclk fall cycle");
        repeat (3) tick();
        if (!p_done || busy || rise_count != 1 || sample_count != 2) $fatal(1, "probe accounting");
        if (!observed_class_valid || observed_class !== 2'b00) $fatal(1, "stable low classification");

        // Exercise the other three classifier combinations with isolated
        // probes; each must still have exactly one edge and two samples.
        q = 1; cmd = 2'b10; req = 1; tick(); req = 0;
        repeat (4) tick(); q = 1; tick(); tick(); repeat (5) tick();
        if (observed_class !== 2'b01) $fatal(1, "stable high classification");
        q = 0; cmd = 2'b10; req = 1; tick(); req = 0;
        repeat (4) tick(); q = 1; tick(); q = 0; tick(); repeat (5) tick();
        if (observed_class !== 2'b10) $fatal(1, "ambiguous classification 10");
        q = 1; cmd = 2'b10; req = 1; tick(); req = 0;
        repeat (4) tick(); q = 0; tick(); q = 1; tick(); repeat (5) tick();
        if (observed_class !== 2'b10) $fatal(1, "ambiguous classification 01");
        if (rise_count != 4 || sample_count != 8) $fatal(1, "aggregate probe accounting");
        $display("SEQUENCER_UNIT_PASS");
        $finish;
    end
endmodule
`default_nettype wire
