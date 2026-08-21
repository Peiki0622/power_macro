// ============================================================================
// FTC Phase 9 VCS-XA integrated testbench
//
// Ownership contract:
//   The testbench drives ONLY VDD, VSS, ctrl_por_n, cal_start, and cal_clk.
//   Every thermometer, sensor-reset, sensor-clock, state, and Q-sample signal
//   is observed from the synthesized controller or XA sensor boundary.
//
// This testbench is verification-only and is not part of synthesizable RTL.
// The event CSV is deliberately compact: it records controller-visible events
// at each calibration clock and avoids dumping every internal digital net.
// ============================================================================
`timescale 1ps/1ps

module tb_ftc_vcs_xa;
    // ------------------------------------------------------------------------
    // External environment signals permitted by the Phase 9 ownership rule.
    // VDD/VSS are logical rails on the VCS side; their analog voltage values
    // are supplied by the XA SPICE deck for each nominal scenario.
    // ------------------------------------------------------------------------
    reg  VDD;
    reg  VSS;
    reg  ctrl_por_n;
    reg  cal_start;
    reg  cal_clk;

    // ------------------------------------------------------------------------
    // Synthesized-controller outputs.  These nets are intentionally not
    // assigned by this testbench.  They are the only source of sensor control.
    // ------------------------------------------------------------------------
    wire       q_final;
    wire       sense_dff_reset;
    wire       sense_s_clk;
    wire [15:0] medium_therm;
    wire [9:0]  fine_therm;
    wire        cal_busy;
    wire        cal_done;
    wire        cal_fail;
    wire        lock_valid;
    wire [4:0]  medium_code;
    wire [3:0]  fine_code;
    wire [2:0]  fail_reason;
    wire [4:0]  fsm_state;
    wire        q_sample_1_event;
    wire        q_sample_2_event;
    wire        config_update_event;
    wire        probe_start_event;

    // Synthesized gate-level controller under test.
    ftc_cal_controller_top u_controller (
        .cal_clk              (cal_clk),
        .ctrl_por_n           (ctrl_por_n),
        .cal_start            (cal_start),
        .q_final              (q_final),
        .sense_dff_reset      (sense_dff_reset),
        .sense_s_clk          (sense_s_clk),
        .medium_therm         (medium_therm),
        .fine_therm           (fine_therm),
        .cal_busy             (cal_busy),
        .cal_done             (cal_done),
        .cal_fail             (cal_fail),
        .lock_valid           (lock_valid),
        .medium_code          (medium_code),
        .fine_code            (fine_code),
        .fail_reason          (fail_reason),
        .fsm_state            (fsm_state),
        .q_sample_1_event     (q_sample_1_event),
        .q_sample_2_event     (q_sample_2_event),
        .config_update_event  (config_update_event),
        .probe_start_event    (probe_start_event)
    );

    // The empty digital view is replaced by the XA transistor-level cell.
    ftc_sensor_ams u_sensor (
        .q_final       (q_final),
        .sense_s_clk   (sense_s_clk),
        .sense_dff_reset(sense_dff_reset),
        .medium_therm  (medium_therm),
        .fine_therm    (fine_therm),
        .VDD           (VDD),
        .VSS           (VSS)
    );

    integer event_fd;
    integer clk_edge_count;

    // Record one row per external calibration-clock edge.  Event columns are
    // sampled directly from the real synthesized netlist and XA-returned Q.
    always @(posedge cal_clk) begin
        clk_edge_count = clk_edge_count + 1;
        $fwrite(event_fd,
            "%0t,%0d,%b,%b,%b,%b,%b,%b,%b,%b,%h,%h,%h,%h,%h,%h,%h,%h,%b,%b,%b,%b,%b,%b\n",
            $time, clk_edge_count, q_final, sense_s_clk, sense_dff_reset,
            cal_busy, cal_done, cal_fail, lock_valid, probe_start_event,
            medium_therm, fine_therm, medium_code, fine_code, fail_reason,
            fsm_state, q_sample_1_event, q_sample_2_event,
            config_update_event, cal_start, ctrl_por_n,
            VDD, VSS, 1'b0, 1'b0);
    end

    initial begin
        event_fd = $fopen("controller_events.csv", "w");
        if (event_fd == 0) begin
            $display("ERROR: cannot open controller_events.csv");
            $finish;
        end
        $fwrite(event_fd, "time_ps,clk_edge,q_final,sense_s_clk,sense_dff_reset,cal_busy,cal_done,cal_fail,lock_valid,probe_start_event,medium_therm,fine_therm,medium_code,fine_code,fail_reason,fsm_state,q_sample_1_event,q_sample_2_event,config_update_event,cal_start,ctrl_por_n,VDD,VSS,reserved0,reserved1\n");
        clk_edge_count = 0;

        // Only the five permitted external environment controls are assigned.
        VDD       = 1'b1;
        VSS       = 1'b0;
        ctrl_por_n = 1'b0;
        cal_start  = 1'b0;
        cal_clk    = 1'b0;

        // 10 ns clock, matching the Phase 8B and Phase 9 timing contract.
        #1000;
        forever #5000 cal_clk = ~cal_clk;
    end

    initial begin
        // Release reset and request one calibration after a quiet startup.
        #100000 ctrl_por_n = 1'b1;
        #50000  cal_start  = 1'b1;
        #10000  cal_start  = 1'b0;

        // The 8 us stop is the Phase 9 hard simulation budget.  No early smoke
        // finish is used; the controller must reach done/lock or fail first.
        #7840000;
        $fclose(event_fd);
        $finish;
    end
endmodule
