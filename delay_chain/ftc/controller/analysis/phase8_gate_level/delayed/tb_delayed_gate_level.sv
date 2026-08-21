// ============================================================================
// Phase 8B SDF gate-level regression for the synthesized FTC controller.
// Uses the permitted 10 ns GLS clock while preserving the Phase 7 1 GHz SDC.
// SDF cell delays are allowed to move events in time, never to change the
// exact transaction, edge, sample, reset, or lock invariants audited here.
// ============================================================================
`timescale 1ns/1ps
module tb_delayed_gate_level;
    localparam real CLK_PERIOD_NS=10.0;
    localparam int RESET_CYCLES=10;
    localparam time MAX_SIM_TIME=100_000ns;

    // Complete external and sensor-facing port declarations.  The testbench
    // drives only clock/POR/start and receives q_final from the sensor oracle.
    logic cal_clk,ctrl_por_n,cal_start,q_final;
    logic sense_dff_reset,sense_s_clk;
    logic [15:0] medium_therm;
    logic [9:0] fine_therm;
    logic cal_busy,cal_done,cal_fail,lock_valid;
    logic [4:0] medium_code,fsm_state;
    logic [3:0] fine_code;
    logic [2:0] fail_reason;
    logic q_sample_1_event,q_sample_2_event,config_update_event,probe_start_event;

    integer config_count,probe_count,sclk_count,sample1_count,sample2_count,therm_change_count;
    bit run_active,monitor_error,terminal_seen;
    string active_scenario;
    logic [15:0] medium_prev,locked_medium;
    logic [9:0] fine_prev,locked_fine;

    ftc_cal_controller_top dut (
        .cal_clk(cal_clk),.ctrl_por_n(ctrl_por_n),.cal_start(cal_start),.q_final(q_final),
        .sense_dff_reset(sense_dff_reset),.sense_s_clk(sense_s_clk),.medium_therm(medium_therm),
        .fine_therm(fine_therm),.cal_busy(cal_busy),.cal_done(cal_done),.cal_fail(cal_fail),
        .lock_valid(lock_valid),.medium_code(medium_code),.fine_code(fine_code),
        .fail_reason(fail_reason),.fsm_state(fsm_state),.q_sample_1_event(q_sample_1_event),
        .q_sample_2_event(q_sample_2_event),.config_update_event(config_update_event),
        .probe_start_event(probe_start_event)
    );
    ftc_sensor_behavior_model sensor_model (
        .medium_therm(medium_therm),.fine_therm(fine_therm),.sense_s_clk(sense_s_clk),
        .sense_dff_reset(sense_dff_reset),.q_sample_1_event(q_sample_1_event),
        .q_sample_2_event(q_sample_2_event),.q_final(q_final)
    );

    initial begin cal_clk=1'b0; forever #(CLK_PERIOD_NS/2.0) cal_clk=~cal_clk; end

    // Verification-only bit transition helpers; synthesizable RTL contains no
    // function and is unaffected by these testbench utilities.
    function automatic integer changed16(input logic [15:0] n,input logic [15:0] o);
        integer i; begin changed16=0; for(i=0;i<16;i=i+1) if(n[i]!==o[i]) changed16=changed16+1; end
    endfunction
    function automatic integer changed10(input logic [9:0] n,input logic [9:0] o);
        integer i; begin changed10=0; for(i=0;i<10;i=i+1) if(n[i]!==o[i]) changed10=changed10+1; end
    endfunction

    always @(posedge config_update_event) if(run_active) config_count=config_count+1;
    always @(posedge probe_start_event) if(run_active) probe_count=probe_count+1;
    always @(posedge q_sample_1_event) if(run_active) sample1_count=sample1_count+1;
    always @(posedge q_sample_2_event) if(run_active) sample2_count=sample2_count+1;

    // SDF must not create a second physical sensor clock edge or assert reset
    // concurrently with its intended rising edge.
    always @(posedge sense_s_clk) if(run_active) begin
        sclk_count=sclk_count+1;
        if(sense_dff_reset!==1'b0) begin monitor_error=1'b1; $display("PHASE8B_MONITOR_ERROR scenario=%s cause=sclk_with_reset",active_scenario); end
    end

    // Cell delays may shift a rail transition but may not make it multi-bit or
    // occur while the sensor is active.
    always @(medium_therm or fine_therm) begin
        integer md,fd;
        if(run_active) begin
            md=changed16(medium_therm,medium_prev); fd=changed10(fine_therm,fine_prev);
            if((md!=0)||(fd!=0)) begin
                therm_change_count=therm_change_count+1;
                if(((md+fd)!=1)||(sense_dff_reset!==1'b1)||(sense_s_clk!==1'b0)) begin
                    monitor_error=1'b1;
                    $display("PHASE8B_MONITOR_ERROR scenario=%s cause=illegal_therm_transition md=%0d fd=%0d reset=%b sclk=%b",active_scenario,md,fd,sense_dff_reset,sense_s_clk);
                end
            end
        end
        medium_prev=medium_therm; fine_prev=fine_therm;
    end

    // Terminal state must freeze the actual physical vectors despite SDF delay.
    always @(posedge cal_clk) begin
        if(run_active&&(cal_done||cal_fail)&&!terminal_seen) begin terminal_seen=1'b1; locked_medium=medium_therm; locked_fine=fine_therm; end
        if(run_active&&terminal_seen&&((medium_therm!==locked_medium)||(fine_therm!==locked_fine))) begin monitor_error=1'b1; $display("PHASE8B_MONITOR_ERROR scenario=%s cause=terminal_config_changed",active_scenario); end
    end
    always @(negedge ctrl_por_n) begin run_active=1'b0; medium_prev=medium_therm; fine_prev=fine_therm; end

    task automatic run_nominal(input string name,input integer exp_m,input integer exp_f,input integer exp_ops);
        integer cycles;
        begin
            active_scenario=name; config_count=0; probe_count=0; sclk_count=0; sample1_count=0; sample2_count=0; therm_change_count=0; monitor_error=1'b0; terminal_seen=1'b0;
            ctrl_por_n=1'b0; cal_start=1'b0; repeat(RESET_CYCLES) @(posedge cal_clk);
            sensor_model.load_scenario(name); sensor_model.reset_stats(); medium_prev=medium_therm; fine_prev=fine_therm;
            ctrl_por_n=1'b1; repeat(2) @(posedge cal_clk); @(negedge cal_clk); run_active=1'b1; cal_start=1'b1; @(negedge cal_clk); cal_start=1'b0;
            cycles=0; while(!(cal_done||cal_fail)&&(cycles<4000)) begin @(posedge cal_clk); cycles=cycles+1; end
            if(cycles==4000) $fatal(1,"PHASE8B_FAIL scenario=%s cause=timeout",name);
            repeat(10) @(posedge cal_clk);
            if(!cal_done||cal_fail||!lock_valid) $fatal(1,"PHASE8B_FAIL scenario=%s cause=status",name);
            if((medium_code!==exp_m)||(fine_code!==exp_f)) $fatal(1,"PHASE8B_FAIL scenario=%s cause=code got=M%0d/F%0d",name,medium_code,fine_code);
            if((config_count+probe_count)!==exp_ops) $fatal(1,"PHASE8B_FAIL scenario=%s cause=ops got=%0d expected=%0d",name,config_count+probe_count,exp_ops);
            if(monitor_error||(sensor_model.violation_count!=0)) $fatal(1,"PHASE8B_FAIL scenario=%s cause=protocol_monitor",name);
            if(sclk_count!==probe_count) $fatal(1,"PHASE8B_FAIL scenario=%s cause=sclk_count",name);
            if((sample1_count!==probe_count)||(sample2_count!==probe_count)) $fatal(1,"PHASE8B_FAIL scenario=%s cause=sample_count",name);
            if(therm_change_count!==config_count) $fatal(1,"PHASE8B_FAIL scenario=%s cause=therm_count",name);
            $display("PHASE8B_PASS scenario=%s ops=%0d configs=%0d probes=%0d samples=%0d/%0d final=M%0d/F%0d",name,config_count+probe_count,config_count,probe_count,sample1_count,sample2_count,medium_code,fine_code);
            run_active=1'b0;
        end
    endtask

    initial begin
        ctrl_por_n=1'b0; cal_start=1'b0; run_active=1'b0; monitor_error=1'b0; terminal_seen=1'b0; medium_prev='0; fine_prev='0;
        $dumpfile("delayed_gate_level.vcd"); $dumpvars(0,tb_delayed_gate_level);
        run_nominal("0p80V",7,6,45); run_nominal("0p95V",4,6,36); run_nominal("1p10V",2,9,36);
        $display("PHASE8B_ALL_PASS nominal=3 sdf=max exact_ops=45,36,36"); $finish;
    end
    initial begin #MAX_SIM_TIME; $fatal(1,"PHASE8B_FAIL cause=global_timeout scenario=%s",active_scenario); end
endmodule
