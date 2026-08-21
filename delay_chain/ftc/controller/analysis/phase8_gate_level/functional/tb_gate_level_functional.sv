// ============================================================================
// Phase 8A functional GLS regression for the mapped FTC controller.
// The 10 ns clock is a simulation-only relaxation; Phase 7 keeps the 1 GHz
// synthesis target.  Public event ports provide exact operation accounting.
// All controller-owned sensor controls are observed, never testbench-driven.
// ============================================================================
`timescale 1ns/1ps
module tb_gate_level_functional;
    localparam real CLK_PERIOD_NS = 10.0;
    localparam int RESET_CYCLES = 10;
    localparam time MAX_SIM_TIME = 200_000ns;

    // External inputs and controller outputs.  Port comments document the
    // complete interface because this bench is also a netlist contract check.
    logic cal_clk, ctrl_por_n, cal_start, q_final;
    logic sense_dff_reset, sense_s_clk;
    logic [15:0] medium_therm;
    logic [9:0] fine_therm;
    logic cal_busy, cal_done, cal_fail, lock_valid;
    logic [4:0] medium_code, fsm_state;
    logic [3:0] fine_code;
    logic [2:0] fail_reason;
    logic q_sample_1_event, q_sample_2_event;
    logic config_update_event, probe_start_event;

    // Per-run audit counters.  config/probe markers are one-cycle registered
    // events from the mapped sequencer, so their sum is the exact operation
    // count required by the functional contract.
    integer operation_count, config_count, probe_count, sclk_count;
    integer sample1_count, sample2_count, therm_change_count;
    bit run_active, monitor_error, terminal_seen;
    string active_scenario;
    logic [15:0] medium_prev, terminal_medium;
    logic [9:0] fine_prev, terminal_fine;

    ftc_cal_controller_top dut (
        .cal_clk(cal_clk), .ctrl_por_n(ctrl_por_n), .cal_start(cal_start),
        .q_final(q_final), .sense_dff_reset(sense_dff_reset),
        .sense_s_clk(sense_s_clk), .medium_therm(medium_therm),
        .fine_therm(fine_therm), .cal_busy(cal_busy), .cal_done(cal_done),
        .cal_fail(cal_fail), .lock_valid(lock_valid),
        .medium_code(medium_code), .fine_code(fine_code),
        .fail_reason(fail_reason), .fsm_state(fsm_state),
        .q_sample_1_event(q_sample_1_event), .q_sample_2_event(q_sample_2_event),
        .config_update_event(config_update_event), .probe_start_event(probe_start_event)
    );

    // Verification-only response oracle.  Sample event ports permit explicit
    // (0,1) ambiguity without driving any physical controller output.
    ftc_sensor_behavior_model sensor_model (
        .medium_therm(medium_therm), .fine_therm(fine_therm),
        .sense_s_clk(sense_s_clk), .sense_dff_reset(sense_dff_reset),
        .q_sample_1_event(q_sample_1_event), .q_sample_2_event(q_sample_2_event),
        .q_final(q_final)
    );

    initial begin
        cal_clk = 1'b0;
        forever #(CLK_PERIOD_NS / 2.0) cal_clk = ~cal_clk;
    end

    // Testbench-only bit-difference helpers; no synthesis RTL function is used.
    function automatic integer changed16(input logic [15:0] n, input logic [15:0] o);
        integer i; begin changed16 = 0; for (i=0;i<16;i=i+1) if (n[i]!==o[i]) changed16=changed16+1; end
    endfunction
    function automatic integer changed10(input logic [9:0] n, input logic [9:0] o);
        integer i; begin changed10 = 0; for (i=0;i<10;i=i+1) if (n[i]!==o[i]) changed10=changed10+1; end
    endfunction

    always @(posedge config_update_event) if (run_active) begin config_count=config_count+1; operation_count=operation_count+1; end
    always @(posedge probe_start_event) if (run_active) begin probe_count=probe_count+1; operation_count=operation_count+1; end
    always @(posedge q_sample_1_event) if (run_active) sample1_count=sample1_count+1;
    always @(posedge q_sample_2_event) if (run_active) sample2_count=sample2_count+1;

    // Exactly one released-reset S_CLK edge per probe is required.
    always @(posedge sense_s_clk) if (run_active) begin
        sclk_count=sclk_count+1;
        if (sense_dff_reset!==1'b0) begin monitor_error=1'b1; $display("PHASE8A_MONITOR_ERROR scenario=%s cause=sclk_with_reset",active_scenario); end
    end

    // Every physical config transition must be one thermometer rail while
    // reset is high and sensor clock is low.
    always @(medium_therm or fine_therm) begin
        integer md, fd;
        if (run_active) begin
            md=changed16(medium_therm,medium_prev); fd=changed10(fine_therm,fine_prev);
            if ((md!=0)||(fd!=0)) begin
                therm_change_count=therm_change_count+1;
                if (((md+fd)!=1)||(sense_dff_reset!==1'b1)||(sense_s_clk!==1'b0)) begin
                    monitor_error=1'b1;
                    $display("PHASE8A_MONITOR_ERROR scenario=%s cause=illegal_therm_transition md=%0d fd=%0d reset=%b sclk=%b",active_scenario,md,fd,sense_dff_reset,sense_s_clk);
                end
            end
        end
        medium_prev=medium_therm; fine_prev=fine_therm;
    end

    // Capture and then continuously check terminal vectors for lock/fail freeze.
    always @(posedge cal_clk) begin
        if (run_active&&(cal_done||cal_fail)&&!terminal_seen) begin terminal_seen=1'b1; terminal_medium=medium_therm; terminal_fine=fine_therm; end
        if (run_active&&terminal_seen&&((medium_therm!==terminal_medium)||(fine_therm!==terminal_fine))) begin monitor_error=1'b1; $display("PHASE8A_MONITOR_ERROR scenario=%s cause=terminal_config_changed",active_scenario); end
    end
    always @(negedge ctrl_por_n) begin run_active=1'b0; medium_prev=medium_therm; fine_prev=fine_therm; end

    // Run one exact nominal or defensive scenario from the Phase 6 response
    // contract, with deterministic POR isolation and a bounded timeout.
    task automatic run_scenario(input string name, input bit success,
                                input integer exp_m, input integer exp_f,
                                input integer exp_reason, input integer exp_ops);
        integer cycles;
        begin
            active_scenario=name; operation_count=0; config_count=0; probe_count=0; sclk_count=0;
            sample1_count=0; sample2_count=0; therm_change_count=0; monitor_error=1'b0; terminal_seen=1'b0;
            ctrl_por_n=1'b0; cal_start=1'b0; repeat(RESET_CYCLES) @(posedge cal_clk);
            sensor_model.load_scenario(name); sensor_model.reset_stats();
            medium_prev=medium_therm; fine_prev=fine_therm; ctrl_por_n=1'b1; repeat(2) @(posedge cal_clk);
            @(negedge cal_clk); run_active=1'b1; cal_start=1'b1; @(negedge cal_clk); cal_start=1'b0;
            cycles=0; while (!(cal_done||cal_fail)&&(cycles<4000)) begin @(posedge cal_clk); cycles=cycles+1; end
            if (cycles==4000) $fatal(1,"PHASE8A_FAIL scenario=%s cause=timeout",name);
            repeat(10) @(posedge cal_clk);
            if (success) begin
                if (!cal_done||cal_fail||!lock_valid) $fatal(1,"PHASE8A_FAIL scenario=%s cause=status",name);
                if ((medium_code!==exp_m)||(fine_code!==exp_f)) $fatal(1,"PHASE8A_FAIL scenario=%s cause=code got=M%0d/F%0d",name,medium_code,fine_code);
                if (operation_count!==exp_ops) $fatal(1,"PHASE8A_FAIL scenario=%s cause=ops got=%0d expected=%0d",name,operation_count,exp_ops);
            end else begin
                if (cal_done||!cal_fail||lock_valid||fail_reason!==exp_reason) $fatal(1,"PHASE8A_FAIL scenario=%s cause=fail_contract",name);
            end
            if (monitor_error||(sensor_model.violation_count!=0)) $fatal(1,"PHASE8A_FAIL scenario=%s cause=protocol_monitor",name);
            if (sclk_count!==probe_count) $fatal(1,"PHASE8A_FAIL scenario=%s cause=sclk_count",name);
            if ((sample1_count!==probe_count)||(sample2_count!==probe_count)) $fatal(1,"PHASE8A_FAIL scenario=%s cause=sample_count",name);
            if (therm_change_count!==config_count) $fatal(1,"PHASE8A_FAIL scenario=%s cause=therm_count",name);
            $display("PHASE8A_PASS scenario=%s ops=%0d configs=%0d probes=%0d samples=%0d/%0d final=M%0d/F%0d fail_reason=%0d",name,operation_count,config_count,probe_count,sample1_count,sample2_count,medium_code,fine_code,fail_reason);
            run_active=1'b0;
        end
    endtask

    initial begin
        ctrl_por_n=1'b0; cal_start=1'b0; run_active=1'b0; monitor_error=1'b0; terminal_seen=1'b0;
        medium_prev='0; fine_prev='0; $dumpfile("gate_level_functional.vcd"); $dumpvars(0,tb_gate_level_functional);
        run_scenario("0p80V",1'b1,7,6,0,45); run_scenario("0p95V",1'b1,4,6,0,36); run_scenario("1p10V",1'b1,2,9,0,36);
        run_scenario("coarse_range_fail",1'b0,0,0,3'b001,-1); run_scenario("backoff_underflow",1'b0,0,0,3'b010,-1);
        run_scenario("fine_range_fail",1'b0,0,0,3'b011,-1); run_scenario("guard_range_fail",1'b0,0,0,3'b100,-1);
        run_scenario("guard_not_low_high",1'b0,0,0,3'b101,-1); run_scenario("guard_not_low_ambig",1'b0,0,0,3'b101,-1);
        run_scenario("hold_not_low_high",1'b0,0,0,3'b110,-1); run_scenario("hold_not_low_ambig",1'b0,0,0,3'b110,-1);
        $display("PHASE8A_ALL_PASS nominal=3 negative=8 exact_ops=45,36,36"); $finish;
    end
    initial begin #MAX_SIM_TIME; $fatal(1,"PHASE8A_FAIL cause=global_timeout scenario=%s",active_scenario); end
endmodule
