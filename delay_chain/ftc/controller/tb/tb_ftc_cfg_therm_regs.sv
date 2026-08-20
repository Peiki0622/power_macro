`timescale 1ns/1ps
`default_nettype none

module tb_ftc_cfg_therm_regs;
    localparam int MB = 16;
    localparam int FB = 10;
    logic clk = 1'b0;
    logic por_n = 1'b0;
    logic init = 1'b0;
    logic mi = 1'b0, md = 1'b0, fi = 1'b0, fd = 1'b0, lock = 1'b0;
    logic [MB-1:0] mt;
    logic [FB-1:0] ft;
    logic [4:0] mc;
    logic [3:0] fc;
    logic amin, amax, fmin, fmax, locked;

    always #5 clk = ~clk;
    ftc_cfg_therm_regs #(.MEDIUM_BITS(MB), .FINE_BITS(FB)) dut (
        .clk_i(clk), .por_n_i(por_n), .init_i(init),
        .medium_inc_i(mi), .medium_dec_i(md), .fine_inc_i(fi), .fine_dec_i(fd),
        .lock_i(lock), .medium_therm_o(mt), .fine_therm_o(ft),
        .medium_code_o(mc), .fine_code_o(fc), .medium_at_min_o(amin),
        .medium_at_max_o(amax), .fine_at_min_o(fmin), .fine_at_max_o(fmax),
        .cfg_locked_o(locked));

    task automatic tick;
        begin @(posedge clk); #1; end
    endtask
    integer i;
    logic [MB-1:0] mt_prev;
    logic [FB-1:0] ft_prev;
    integer changed;
    initial begin
        repeat (2) @(posedge clk);
        por_n = 1'b1;
        tick();
        if (mc !== 0 || fc !== 0 || mt !== '0 || ft !== {FB{1'b1}}) $fatal(1, "reset encoding");

        // Every medium increment changes one and only one physical bit.
        for (i = 0; i < MB; i = i + 1) begin
            mt_prev = mt; mi = 1'b1; tick(); mi = 1'b0;
            changed = 0;
            changed = $countones(mt ^ mt_prev);
            if (changed != 1 || mc !== i + 1) $fatal(1, "medium increment %0d", i);
        end
        mt_prev = mt; mi = 1'b1; tick(); mi = 1'b0;
        if (mt !== mt_prev || mc !== MB) $fatal(1, "medium overflow");
        for (i = MB; i > 0; i = i - 1) begin
            mt_prev = mt; md = 1'b1; tick(); md = 1'b0;
            if ($countones(mt ^ mt_prev) != 1 || mc !== i - 1) $fatal(1, "medium decrement");
        end
        mt_prev = mt; md = 1'b1; tick(); md = 1'b0;
        if (mt !== mt_prev || mc !== 0) $fatal(1, "medium underflow");

        for (i = 0; i < FB; i = i + 1) begin
            ft_prev = ft; fi = 1'b1; tick(); fi = 1'b0;
            if ($countones(ft ^ ft_prev) != 1 || fc !== i + 1) $fatal(1, "fine increment");
        end
        ft_prev = ft; fi = 1'b1; tick(); fi = 1'b0;
        if (ft !== ft_prev || fc !== FB) $fatal(1, "fine overflow");
        for (i = FB; i > 0; i = i - 1) begin
            ft_prev = ft; fd = 1'b1; tick(); fd = 1'b0;
            if ($countones(ft ^ ft_prev) != 1 || fc !== i - 1) $fatal(1, "fine decrement");
        end
        ft_prev = ft; fd = 1'b1; tick(); fd = 1'b0;
        if (ft !== ft_prev || fc !== 0) $fatal(1, "fine underflow");

        mi = 1'b1; fi = 1'b1; tick(); mi = 1'b0; fi = 1'b0;
        lock = 1'b1; tick(); lock = 1'b0;
        mt_prev = mt; ft_prev = ft; mi = 1'b1; fi = 1'b1; md = 1'b1; fd = 1'b1; tick();
        if (!locked || mt !== mt_prev || ft !== ft_prev) $fatal(1, "lock freeze");
        $display("THERMOMETER_UNIT_PASS");
        $finish;
    end
endmodule

`default_nettype wire
