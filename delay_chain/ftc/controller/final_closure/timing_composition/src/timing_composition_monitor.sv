// ============================================================================
// Timing-composition event monitor (verification-only, non-synthesizable).
//
// This module is bound into the existing corrected autonomous testbench.  It
// has input-only ports and never drives the controller, sensor, bridge, or
// calibration clock.  Its sole purpose is to preserve real event timestamps
// after Phase 7 SDF delay annotation so C3 can distinguish a timing-composed
// result from the earlier no-SDF Phase 9 evidence.
//
// The monitor intentionally uses no RTL functions or procedural drivers for
// design signals.  It records the mapped controller's sensor-clock/reset
// edges, thermometer transitions, probe/sample/config events, and terminal
// lock.  A separate CSV row is emitted for every event; periodic snapshots in
// the legacy Phase 9 bench are not used to infer physical edge counts.
// ============================================================================
`timescale 1ns/1ps

module timing_composition_monitor (
    // External controller inputs are observed only to correlate events with
    // the canonical 1 ns calibration clock.  They are never assigned here.
    input wire        cal_clk,
    input wire        ctrl_por_n,
    input wire        cal_start,

    // Controller-owned sensor control crossings.  These ports are input-only
    // because the mapped controller remains the sole owner of every control.
    input wire        sense_s_clk,
    input wire        sense_dff_reset,
    input wire [15:0] medium_therm,
    input wire [9:0]  fine_therm,

    // Controller event markers and returned sensor result.  q_final is
    // observed for aperture reporting; q_sample events remain controller
    // generated and are not synthesized by this monitor.
    input wire        q_final,
    input wire        q_sample_1_event,
    input wire        q_sample_2_event,
    input wire        config_update_event,
    input wire        probe_start_event,
    input wire        cal_busy,
    input wire        cal_done,
    input wire        cal_fail,
    input wire        lock_valid
);
    integer event_fd;
    integer cal_edge_count;
    integer sclk_edge_count;
    integer sample1_count;
    integer sample2_count;
    integer config_count;
    integer probe_count;
    integer medium_delta;
    integer fine_delta;
    reg [15:0] medium_previous;
    reg [9:0] fine_previous;

    initial begin
        // The launcher starts in a task-owned run directory, so this file is
        // a compact committed-result candidate rather than a scattered raw DB.
        event_fd = $fopen("timing_events.csv", "w");
        if (event_fd == 0)
            $fatal(1, "TIMING_MONITOR_FAIL cause=event_csv_open");
        $fwrite(event_fd, "time_ns,event,cal_edge,sclk_edges,sample1,sample2,configs,probes,cal_busy,cal_done,cal_fail,lock_valid,reset,sclk,medium_therm,fine_therm,q_final\n");
        cal_edge_count = 0;
        sclk_edge_count = 0;
        sample1_count = 0;
        sample2_count = 0;
        config_count = 0;
        probe_count = 0;
        medium_previous = 16'b0;
        fine_previous = 10'b1111111111;
    end

    // Record every external calibration-clock edge.  This provides a stable
    // 1 ns reference for comparing delayed output events with contract cycles.
    always @(posedge cal_clk) begin
        cal_edge_count = cal_edge_count + 1;
        $fwrite(event_fd, "%0.6f,CAL_CLK_RISE,%0d,%0d,%0d,%0d,%0d,%0d,%b,%b,%b,%b,%b,%b,%h,%h,%b\n",
            $realtime, cal_edge_count, sclk_edge_count, sample1_count,
            sample2_count, config_count, probe_count, cal_busy, cal_done,
            cal_fail, lock_valid, sense_dff_reset, sense_s_clk,
            medium_therm, fine_therm, q_final);
    end

    // The physical sensor clock edge is the timing-sensitive event of each
    // probe.  Record its post-SDF timestamp and the reset level at that edge.
    always @(posedge sense_s_clk) begin
        sclk_edge_count = sclk_edge_count + 1;
        $fwrite(event_fd, "%0.6f,SCLK_RISE,%0d,%0d,%0d,%0d,%0d,%0d,%b,%b,%b,%b,%b,%b,%h,%h,%b\n",
            $realtime, cal_edge_count, sclk_edge_count, sample1_count,
            sample2_count, config_count, probe_count, cal_busy, cal_done,
            cal_fail, lock_valid, sense_dff_reset, sense_s_clk,
            medium_therm, fine_therm, q_final);
    end

    // Reset transitions are captured independently so the audit can verify
    // release before S_CLK rise and reassertion before the return/fall edge.
    always @(sense_dff_reset) begin
        $fwrite(event_fd, "%0.6f,RESET_CHANGE,%0d,%0d,%0d,%0d,%0d,%0d,%b,%b,%b,%b,%b,%b,%h,%h,%b\n",
            $realtime, cal_edge_count, sclk_edge_count, sample1_count,
            sample2_count, config_count, probe_count, cal_busy, cal_done,
            cal_fail, lock_valid, sense_dff_reset, sense_s_clk,
            medium_therm, fine_therm, q_final);
    end

    // Count physical thermometer transitions and preserve their exact time.
    // The C3 audit later checks that the total transition count equals the
    // controller's config_update count and that every transition is one bit.
    always @(medium_therm or fine_therm) begin
        medium_delta = 0;
        fine_delta = 0;
        for (integer index = 0; index < 16; index = index + 1)
            if (medium_therm[index] !== medium_previous[index]) medium_delta = medium_delta + 1;
        for (integer fine_index = 0; fine_index < 10; fine_index = fine_index + 1)
            if (fine_therm[fine_index] !== fine_previous[fine_index]) fine_delta = fine_delta + 1;
        if ((medium_delta != 0) || (fine_delta != 0))
            $fwrite(event_fd, "%0.6f,THERM_CHANGE,%0d,%0d,%0d,%0d,%0d,%0d,%b,%b,%b,%b,%b,%b,%h,%h,%b\n",
                $realtime, cal_edge_count, sclk_edge_count, sample1_count,
                sample2_count, config_count, probe_count, cal_busy, cal_done,
                cal_fail, lock_valid, sense_dff_reset, sense_s_clk,
                medium_therm, fine_therm, q_final);
        medium_previous = medium_therm;
        fine_previous = fine_therm;
    end

    always @(posedge q_sample_1_event) begin
        sample1_count = sample1_count + 1;
        $fwrite(event_fd, "%0.6f,Q_SAMPLE_1,%0d,%0d,%0d,%0d,%0d,%0d,%b,%b,%b,%b,%b,%b,%h,%h,%b\n",
            $realtime, cal_edge_count, sclk_edge_count, sample1_count,
            sample2_count, config_count, probe_count, cal_busy, cal_done,
            cal_fail, lock_valid, sense_dff_reset, sense_s_clk,
            medium_therm, fine_therm, q_final);
    end

    always @(posedge q_sample_2_event) begin
        sample2_count = sample2_count + 1;
        $fwrite(event_fd, "%0.6f,Q_SAMPLE_2,%0d,%0d,%0d,%0d,%0d,%0d,%b,%b,%b,%b,%b,%b,%h,%h,%b\n",
            $realtime, cal_edge_count, sclk_edge_count, sample1_count,
            sample2_count, config_count, probe_count, cal_busy, cal_done,
            cal_fail, lock_valid, sense_dff_reset, sense_s_clk,
            medium_therm, fine_therm, q_final);
    end

    always @(posedge config_update_event) begin
        config_count = config_count + 1;
        $fwrite(event_fd, "%0.6f,CONFIG_UPDATE,%0d,%0d,%0d,%0d,%0d,%0d,%b,%b,%b,%b,%b,%b,%h,%h,%b\n",
            $realtime, cal_edge_count, sclk_edge_count, sample1_count,
            sample2_count, config_count, probe_count, cal_busy, cal_done,
            cal_fail, lock_valid, sense_dff_reset, sense_s_clk,
            medium_therm, fine_therm, q_final);
    end

    always @(posedge probe_start_event) begin
        probe_count = probe_count + 1;
        $fwrite(event_fd, "%0.6f,PROBE_START,%0d,%0d,%0d,%0d,%0d,%0d,%b,%b,%b,%b,%b,%b,%h,%h,%b\n",
            $realtime, cal_edge_count, sclk_edge_count, sample1_count,
            sample2_count, config_count, probe_count, cal_busy, cal_done,
            cal_fail, lock_valid, sense_dff_reset, sense_s_clk,
            medium_therm, fine_therm, q_final);
    end

    always @(posedge cal_done or posedge cal_fail or posedge lock_valid) begin
        $fwrite(event_fd, "%0.6f,TERMINAL,%0d,%0d,%0d,%0d,%0d,%0d,%b,%b,%b,%b,%b,%b,%h,%h,%b\n",
            $realtime, cal_edge_count, sclk_edge_count, sample1_count,
            sample2_count, config_count, probe_count, cal_busy, cal_done,
            cal_fail, lock_valid, sense_dff_reset, sense_s_clk,
            medium_therm, fine_therm, q_final);
    end

    final begin
        if (event_fd != 0) begin
            $fflush(event_fd);
            $fclose(event_fd);
        end
    end
endmodule

// Bind-only integration keeps the accepted autonomous testbench unchanged:
// all ports below are observations of existing signals, never new drivers.
bind tb_ftc_vcs_xa_autonomous timing_composition_monitor u_timing_composition_monitor (
    .cal_clk(cal_clk), .ctrl_por_n(ctrl_por_n), .cal_start(cal_start),
    .sense_s_clk(sense_s_clk), .sense_dff_reset(sense_dff_reset),
    .medium_therm(medium_therm), .fine_therm(fine_therm), .q_final(q_final),
    .q_sample_1_event(q_sample_1_event), .q_sample_2_event(q_sample_2_event),
    .config_update_event(config_update_event), .probe_start_event(probe_start_event),
    .cal_busy(cal_busy), .cal_done(cal_done), .cal_fail(cal_fail),
    .lock_valid(lock_valid)
);
