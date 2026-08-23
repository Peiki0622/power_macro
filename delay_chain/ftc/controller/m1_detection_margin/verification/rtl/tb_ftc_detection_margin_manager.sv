// ============================================================================
// M1 RTL integration test: registered margin manager plus frozen H0 handoff
// ============================================================================
// This bench connects the new M1 manager to the unmodified H0 ownership block
// rather than merely stubbing det_owner_valid.  It checks all twelve exact M0
// mappings, the complete preload/safe-switch/apply/settle sequence, protocol
// failures, delayed ownership, and POR recovery.  No calibration algorithm,
// transistor sensor, HSPICE deck, or runtime detector probe is instantiated.
// ============================================================================
`timescale 1ns/1ps
`default_nettype none

module tb_ftc_detection_margin_manager;
    // Gate/SDF cells need a longer post-edge observation window than RTL.  The
    // protocol still advances only on 2.5 ns clock edges; this parameter merely
    // prevents the checker from reading an SDF-delayed output in its aperture.
`ifdef M1_GATE_SDF
    localparam realtime OBSERVE_DELAY = 1.00;
`else
    localparam realtime OBSERVE_DELAY = 0.02;
`endif

    // ------------------------------------------------------------------------
    // Shared 400 MHz H0/M1 clock and controller POR
    // ------------------------------------------------------------------------
    logic cal_clk;
    logic ctrl_por_n;

    // Frozen calibration status/control inputs driven by this harness.  They
    // model only an already completed H0-safe calibration snapshot; the
    // calibration RTL itself is intentionally outside this focused protocol
    // test and remains separately frozen.
    logic        cal_busy;
    logic        cal_done;
    logic        cal_fail;
    logic        lock_valid;
    logic        cal_sense_dff_reset;
    logic        cal_sense_s_clk;
    logic [15:0] cal_medium_therm;
    logic [9:0]  cal_fine_therm;
    logic [4:0]  cal_medium_code;
    logic [3:0]  cal_fine_code;

    // M1 request interface.  The tests only raise valid at a clock edge after
    // H0 det_prepare, except in explicit malformed-protocol scenarios.
    logic [1:0] margin_sel;
    logic       margin_select_valid;

    // M1 detector-side outputs, connected to H0's already published detector
    // input interface.  allow_handoff is a test-only gate used to delay H0's
    // observation of ready without changing the manager implementation.
    logic        manager_ready;
    logic        manager_reset;
    logic        manager_sclk;
    logic [15:0] manager_medium_therm;
    logic [9:0]  manager_fine_therm;
    logic        margin_cfg_valid;
    logic        mapping_supported;
    logic        trip_qualified;
    logic        margin_protocol_error;
    logic [4:0]  m_det;
    logic [3:0]  f_det;
    logic [1:0]  margin_level;
    logic        allow_handoff;
    logic        h0_ready;

    // Actual frozen H0 output controls and immutable snapshot publication.
    logic        sense_dff_reset;
    logic        sense_s_clk;
    logic [15:0] medium_therm;
    logic [9:0]  fine_therm;
    logic        cal_cfg_valid;
    logic [4:0]  cal_medium_code_snapshot;
    logic [3:0]  cal_fine_code_snapshot;
    logic [15:0] cal_medium_therm_snapshot;
    logic [9:0]  cal_fine_therm_snapshot;
    logic        det_prepare;
    logic        det_owner_valid;
    logic        handoff_blocked;
    logic        handoff_protocol_error;
    logic [2:0]  handoff_state;

    integer failures;
    integer target_change_count;
    // cal_clk_epoch is deliberately a cycle counter rather than a wall-clock
    // timestamp.  SDF cell and net delays move the visible detector-vector
    // transition after its launching edge, so measuring from that delayed
    // transition to a separately delayed valid pin would undercount the
    // architectural M_APPLY cycle.  The counter records the actual controller
    // edges that define the protocol's one-full-cycle settle guarantee.
    integer cal_clk_epoch;
    integer target_apply_epoch;
    logic   monitor_active;

    // Count each controller launch edge.  Both the mapped and RTL benches use
    // this same edge-based definition, avoiding simulator scheduling or SDF
    // propagation delay from changing the protocol assertion.
    always @(posedge cal_clk) begin
        cal_clk_epoch = cal_clk_epoch + 1;
    end

    // H0 sees ready exactly as it would in the stage top.  The temporary gate
    // is held high for all nominal tests and deliberately low only to prove
    // manager WAIT_OWNER is stable when ownership acknowledgement is delayed.
    always_comb h0_ready = manager_ready && allow_handoff;

    initial begin
        cal_clk = 1'b0;
        forever #1.25 cal_clk = ~cal_clk;
    end

    ftc_detection_margin_manager u_manager (
        .cal_clk_i                   (cal_clk),
        .ctrl_por_n_i                (ctrl_por_n),
        .cal_cfg_valid_i             (cal_cfg_valid),
        .cal_medium_code_snapshot_i  (cal_medium_code_snapshot),
        .cal_fine_code_snapshot_i    (cal_fine_code_snapshot),
        .cal_medium_therm_snapshot_i (cal_medium_therm_snapshot),
        .cal_fine_therm_snapshot_i   (cal_fine_therm_snapshot),
        .det_prepare_i               (det_prepare),
        .det_owner_valid_i           (det_owner_valid),
        .handoff_blocked_i           (handoff_blocked),
        .margin_sel_i                (margin_sel),
        .margin_select_valid_i       (margin_select_valid),
        .det_takeover_ready_o        (manager_ready),
        .det_sense_dff_reset_o       (manager_reset),
        .det_sense_s_clk_o           (manager_sclk),
        .det_medium_therm_o          (manager_medium_therm),
        .det_fine_therm_o            (manager_fine_therm),
        .margin_cfg_valid_o          (margin_cfg_valid),
        .mapping_supported_o         (mapping_supported),
        .trip_qualified_o            (trip_qualified),
        .margin_protocol_error_o     (margin_protocol_error),
        .m_det_o                     (m_det),
        .f_det_o                     (f_det),
        .margin_level_o              (margin_level)
    );

    // The frozen H0 implementation is part of this integration test.  M1
    // cannot bypass its exact snapshot comparator or its registered safe mux.
    ftc_sensor_owner_handoff u_frozen_h0 (
        .cal_clk_i                    (cal_clk),
        .ctrl_por_n_i                 (ctrl_por_n),
        .cal_busy_i                   (cal_busy),
        .cal_done_i                   (cal_done),
        .cal_fail_i                   (cal_fail),
        .lock_valid_i                 (lock_valid),
        .cal_sense_dff_reset_i        (cal_sense_dff_reset),
        .cal_sense_s_clk_i            (cal_sense_s_clk),
        .cal_medium_therm_i           (cal_medium_therm),
        .cal_fine_therm_i             (cal_fine_therm),
        .cal_medium_code_i            (cal_medium_code),
        .cal_fine_code_i              (cal_fine_code),
        .det_takeover_ready_i         (h0_ready),
        .det_sense_dff_reset_i        (manager_reset),
        .det_sense_s_clk_i            (manager_sclk),
        .det_medium_therm_i           (manager_medium_therm),
        .det_fine_therm_i             (manager_fine_therm),
        .sense_dff_reset_o            (sense_dff_reset),
        .sense_s_clk_o                (sense_s_clk),
        .medium_therm_o               (medium_therm),
        .fine_therm_o                 (fine_therm),
        .cal_cfg_valid_o              (cal_cfg_valid),
        .cal_medium_code_snapshot_o   (cal_medium_code_snapshot),
        .cal_fine_code_snapshot_o     (cal_fine_code_snapshot),
        .cal_medium_therm_snapshot_o  (cal_medium_therm_snapshot),
        .cal_fine_therm_snapshot_o    (cal_fine_therm_snapshot),
        .det_prepare_o                (det_prepare),
        .det_owner_valid_o            (det_owner_valid),
        .handoff_blocked_o            (handoff_blocked),
        .handoff_protocol_error_o     (handoff_protocol_error),
        .handoff_state_o              (handoff_state)
    );

    // Compile and run the public M1 assertions against the live manager ports.
    ftc_detection_margin_manager_sva u_manager_sva (
        .cal_clk_i                    (cal_clk),
        .ctrl_por_n_i                 (ctrl_por_n),
        .cal_medium_therm_snapshot_i  (cal_medium_therm_snapshot),
        .cal_fine_therm_snapshot_i    (cal_fine_therm_snapshot),
        .det_owner_valid_i            (det_owner_valid),
        .det_takeover_ready_o         (manager_ready),
        .det_sense_dff_reset_o        (manager_reset),
        .det_sense_s_clk_o            (manager_sclk),
        .det_medium_therm_o           (manager_medium_therm),
        .det_fine_therm_o             (manager_fine_therm),
        .margin_cfg_valid_o           (margin_cfg_valid),
        .mapping_supported_o          (mapping_supported)
    );

    // Event monitors complement cycle assertions by catching any unexpected
    // physical H0 output glitch between clock edges.  Snapshot preload is not
    // counted as a target change; only a change while DET owns the sensor is.
    always @(sense_s_clk) begin
        if (monitor_active && sense_s_clk !== 1'b0) begin
            $display("FAIL physical sensor S_CLK glitch at %0t", $realtime);
            failures = failures + 1;
        end
    end

    always @(medium_therm or fine_therm) begin
        if (monitor_active && det_owner_valid) begin
            if (!sense_dff_reset || sense_s_clk) begin
                $display("FAIL target vector changed outside reset-high/SCLK-low safe window");
                failures = failures + 1;
            end
            target_change_count = target_change_count + 1;
            // A multi-bit mapped vector can report several bit events.  They
            // all belong to this one application edge, so preserving the same
            // epoch is both sufficient and insensitive to bit-level skew.
            target_apply_epoch = cal_clk_epoch;
        end
    end

    always @(posedge margin_cfg_valid) begin
        // `target_apply_epoch == cal_clk_epoch` means valid rose after the
        // same launching edge as the physical target change; that is illegal.
        // A valid edge is allowed only after at least one intervening complete
        // cal_clk interval, i.e. its sampled epoch is strictly later.
        if (monitor_active && (target_apply_epoch >= 0) &&
            (cal_clk_epoch <= target_apply_epoch)) begin
            $display("FAIL margin_cfg_valid arrived before one full controller settle cycle");
            failures = failures + 1;
        end
    end

    // Build frozen physical thermometer vectors in the testbench only.  M1
    // itself uses raw H0 snapshot rails for preload and literal M0 constants
    // for target mapping; it never contains this generic decoder behavior.
    task automatic drive_calibration_snapshot(
        input integer medium_code_i,
        input integer fine_code_i
    );
        integer index;
        begin
            cal_medium_code = medium_code_i[4:0];
            cal_fine_code = fine_code_i[3:0];
            cal_medium_therm = 16'h0000;
            cal_fine_therm = 10'h3ff;
            for (index = 0; index < medium_code_i; index = index + 1)
                cal_medium_therm[index] = 1'b1;
            for (index = 0; index < fine_code_i; index = index + 1)
                cal_fine_therm[index] = 1'b0;
        end
    endtask

    task automatic check_condition(input logic condition, input string label);
        begin
            if (!condition) begin
                $display("FAIL %s at %0t", label, $realtime);
                failures = failures + 1;
            end
        end
    endtask

    // Launch one cal_clk-synchronous request with a real mapped-path setup
    // budget.  The request is asserted immediately after one positive edge,
    // remains stable through exactly the next positive sampling edge, then is
    // released 0.10 ns later.  It is therefore a one-capture-cycle request
    // while selection and valid have roughly a full 2.5 ns cycle to traverse
    // the mapper/manager combinational cone.  This task returns at the early
    // post-acceptance point so the POR negative case can legally exercise the
    // M_PRELOAD state before the next clock edge.
    task automatic launch_margin_request(input logic [1:0] level_i);
        begin
            @(posedge cal_clk);
            #0.10;
            margin_sel = level_i;
            margin_select_valid = 1'b1;
            @(posedge cal_clk);
            #0.10;
            margin_select_valid = 1'b0;
        end
    endtask

    // Normal protocol tests need a stable observation aperture after the
    // sampled request.  Keep that testbench-only wait separate from the
    // electrical launch above so it cannot accidentally constrain POR timing.
    task automatic issue_margin_request(input logic [1:0] level_i);
        begin
            launch_margin_request(level_i);
            #OBSERVE_DELAY;
        end
    endtask

    // Apply a complete POR and restore benign calibration inputs.  The real
    // H0 and M1 both have asynchronous POR, so release is kept away from the
    // active edge before beginning each independent protocol scenario.
    task automatic reset_dut;
        begin
            monitor_active = 1'b0;
            ctrl_por_n = 1'b1;
            #OBSERVE_DELAY;
            ctrl_por_n = 1'b0;
            cal_busy = 1'b0;
            cal_done = 1'b0;
            cal_fail = 1'b0;
            lock_valid = 1'b0;
            cal_sense_dff_reset = 1'b1;
            cal_sense_s_clk = 1'b0;
            cal_medium_therm = 16'h0000;
            cal_fine_therm = 10'h3ff;
            cal_medium_code = 5'd0;
            cal_fine_code = 4'd0;
            margin_sel = 2'd0;
            margin_select_valid = 1'b0;
            allow_handoff = 1'b1;
            target_apply_epoch = -1;
            repeat (2) @(posedge cal_clk);
            #0.20;
            ctrl_por_n = 1'b1;
            @(posedge cal_clk);
            #OBSERVE_DELAY;
            monitor_active = 1'b1;
            check_condition(!cal_cfg_valid && !det_owner_valid && !manager_ready &&
                            !margin_cfg_valid && !margin_protocol_error,
                            "POR clears H0 and M1 state");
        end
    endtask

    // Drive an H0-safe completed calibration and wait until the manager has
    // copied the raw snapshot.  A request may only be issued after this task.
    task automatic establish_snapshot(
        input integer medium_code_i,
        input integer fine_code_i,
        input string label
    );
        begin
            drive_calibration_snapshot(medium_code_i, fine_code_i);
            cal_busy = 1'b0;
            cal_done = 1'b1;
            cal_fail = 1'b0;
            lock_valid = 1'b1;
            cal_sense_dff_reset = 1'b1;
            cal_sense_s_clk = 1'b0;
            @(posedge cal_clk);
            #OBSERVE_DELAY;
            check_condition(cal_cfg_valid && det_prepare && !det_owner_valid,
                            {label, " H0 publishes immutable snapshot"});
            @(posedge cal_clk);
            #OBSERVE_DELAY;
            check_condition(manager_medium_therm == cal_medium_therm_snapshot &&
                            manager_fine_therm == cal_fine_therm_snapshot &&
                            manager_reset && !manager_sclk,
                            {label, " M1 copied exact raw snapshot safely"});
        end
    endtask

    // Execute one nominal M1 sequence through the real H0 handoff.  delay_i
    // holds H0's observation of ready low for several full cycles, proving the
    // manager cannot leak the target while it waits for ownership.
    task automatic run_nominal(
        input integer cal_m,
        input integer cal_f,
        input logic [1:0] level,
        input logic expected_trip,
        input logic [4:0] expected_m,
        input logic [3:0] expected_f,
        input logic [15:0] expected_medium,
        input logic [9:0] expected_fine,
        input integer delay_i,
        input string label
    );
        integer changes_before_apply;
        integer index;
        begin
            reset_dut();
            establish_snapshot(cal_m, cal_f, label);
            changes_before_apply = target_change_count;

            // Legal one-capture-cycle request after det_prepare.  The helper
            // guarantees stable mapped-path setup before the acceptance edge.
            issue_margin_request(level);
            check_condition(mapping_supported && trip_qualified == expected_trip &&
                            m_det == expected_m && f_det == expected_f &&
                            manager_medium_therm == cal_medium_therm_snapshot &&
                            manager_fine_therm == cal_fine_therm_snapshot &&
                            !manager_ready && !margin_cfg_valid,
                            {label, " selection latches target but remains preloaded"});

            // PRELOAD completes for one full cycle before manager_ready rises.
            @(posedge cal_clk);
            #OBSERVE_DELAY;
            check_condition(manager_ready && manager_medium_therm == cal_medium_therm_snapshot &&
                            manager_fine_therm == cal_fine_therm_snapshot &&
                            manager_reset && !manager_sclk,
                            {label, " ready follows one-cycle snapshot preload"});

            if (delay_i > 0) begin
                allow_handoff = 1'b0;
                for (index = 0; index < delay_i; index = index + 1) begin
                    @(posedge cal_clk);
                    #OBSERVE_DELAY;
                    check_condition(!det_owner_valid && manager_ready &&
                                    manager_medium_therm == cal_medium_therm_snapshot &&
                                    manager_fine_therm == cal_fine_therm_snapshot &&
                                    !margin_cfg_valid,
                                    {label, " delayed owner retains snapshot"});
                end
                @(negedge cal_clk);
                allow_handoff = 1'b1;
            end

            // H0 performs SAFE then DET ownership.  Manager cannot apply until
            // the registered det_owner_valid publication is visible.
            // Sample after nonblocking state updates.  Testing the signal in
            // the raw posedge region would observe H0's previous state and
            // skip the intended first DET-owned snapshot-hold cycle.
            while (!det_owner_valid) begin
                @(posedge cal_clk);
                #OBSERVE_DELAY;
            end
            check_condition(sense_dff_reset && !sense_s_clk &&
                            medium_therm == cal_medium_therm_snapshot &&
                            fine_therm == cal_fine_therm_snapshot &&
                            !margin_cfg_valid,
                            {label, " H0 DET entry still sees snapshot"});

            // The next edge is the only target-vector application edge.
            @(posedge cal_clk);
            #OBSERVE_DELAY;
            check_condition(det_owner_valid && manager_reset && !manager_sclk &&
                            manager_medium_therm == expected_medium &&
                            manager_fine_therm == expected_fine &&
                            medium_therm == expected_medium && fine_therm == expected_fine &&
                            !margin_cfg_valid,
                            {label, " atomic target apply under DET ownership"});

            // Valid rises only after the full cycle occupied by M_APPLY.
            @(posedge cal_clk);
            #OBSERVE_DELAY;
            check_condition(margin_cfg_valid && det_owner_valid && manager_reset && !manager_sclk &&
                            sense_dff_reset && !sense_s_clk,
                            {label, " one full controller-cycle settle before valid"});
            if ((expected_medium == cal_medium_therm_snapshot) &&
                (expected_fine == cal_fine_therm_snapshot)) begin
                check_condition(target_change_count == changes_before_apply,
                                {label, " L0 has no pseudo configuration vector event"});
            end else begin
                check_condition(target_change_count > changes_before_apply,
                                {label, " non-L0 reaches exactly one post-owner target change"});
            end
        end
    endtask

    task automatic run_unsupported_case;
        begin
            reset_dut();
            establish_snapshot(6, 6, "unsupported");
            issue_margin_request(2'd1);
            @(posedge cal_clk);
            #OBSERVE_DELAY;
            check_condition(!mapping_supported && margin_protocol_error && !manager_ready &&
                            !margin_cfg_valid && !det_owner_valid &&
                            manager_reset && !manager_sclk &&
                            manager_medium_therm == cal_medium_therm_snapshot &&
                            manager_fine_therm == cal_fine_therm_snapshot,
                            "unsupported snapshot is fail-safe and never ready");
        end
    endtask

    task automatic run_early_selection_case;
        begin
            reset_dut();
            // This is synchronized electrically but intentionally violates
            // protocol order because no calibration snapshot exists yet.
            issue_margin_request(2'd2);
            check_condition(margin_protocol_error && !manager_ready && !margin_cfg_valid,
                            "early selection is sticky protocol error");
            establish_snapshot(4, 6, "early_selection");
            repeat (2) @(posedge cal_clk);
            #OBSERVE_DELAY;
            check_condition(!manager_ready && !det_owner_valid && !margin_cfg_valid,
                            "early selection cannot later take ownership");
        end
    endtask

    task automatic run_blocked_case;
        begin
            reset_dut();
            establish_snapshot(4, 6, "blocked");
            cal_fail = 1'b1;
            @(posedge cal_clk);
            @(posedge cal_clk);
            #OBSERVE_DELAY;
            check_condition(handoff_blocked && margin_protocol_error && !manager_ready &&
                            !margin_cfg_valid && manager_reset && !manager_sclk,
                            "H0 blocked state propagates M1 fail-safe rejection");
        end
    endtask

    task automatic run_por_during_preload_case;
        begin
            reset_dut();
            establish_snapshot(2, 9, "por_preload");
            launch_margin_request(2'd1);
            // M_PRELOAD is active now.  Begin POR 0.20 ns after the request
            // acceptance edge, rather than at the following negative edge:
            // this leaves enough room for both the library's minimum reset
            // pulse width and its SDF-annotated recovery/removal requirement.
            #0.10;
            ctrl_por_n = 1'b0;
            // The annotated SMIC asynchronous-reset cells require a 1.00 ns
            // minimum low pulse.  Preserve the completed-calibration input
            // only for the first 0.95 ns of the 1.05 ns POR interval, then
            // remove it before releasing POR.  Including SDF pin delay, the
            // final release remains well before the next cal_clk positive edge.
            #0.95;
            // POR clears only sequential state; the harness must also remove
            // its completed-calibration stimulus before release so H0 cannot
            // legitimately capture a new snapshot on the first active edge.
            cal_busy = 1'b0;
            cal_done = 1'b0;
            cal_fail = 1'b0;
            lock_valid = 1'b0;
            cal_sense_dff_reset = 1'b1;
            cal_sense_s_clk = 1'b0;
            #0.10;
            ctrl_por_n = 1'b1;
            @(posedge cal_clk);
            #OBSERVE_DELAY;
            check_condition(!cal_cfg_valid && !det_owner_valid && !manager_ready &&
                            !margin_cfg_valid && !margin_protocol_error,
                            "POR during preload clears partial M1 transaction");
        end
    endtask

    task automatic run_repeat_selection_case;
        logic [15:0] held_medium;
        logic [9:0] held_fine;
        begin
            run_nominal(4, 6, 2'd2, 1'b1, 5'd5, 4'd6, 16'h001f, 10'h3c0, 0, "repeat_base");
            held_medium = medium_therm;
            held_fine = fine_therm;
            issue_margin_request(2'd3);
            check_condition(margin_protocol_error && !margin_cfg_valid &&
                            medium_therm == held_medium && fine_therm == held_fine &&
                            sense_dff_reset && !sense_s_clk,
                            "repeated selection rejects without sensor-control glitch");
        end
    endtask

    initial begin
        failures = 0;
        target_change_count = 0;
        cal_clk_epoch = 0;
        target_apply_epoch = -1;
        monitor_active = 1'b0;

        // Full 12-entry table: 0.80 V entries are mapping-only; L0 is an
        // intentional no-vector-change guard configuration in every snapshot.
        run_nominal(7, 6, 2'd0, 1'b0, 5'd7, 4'd6, 16'h007f, 10'h3c0, 0, "M7F6_L0");
        run_nominal(7, 6, 2'd1, 1'b0, 5'd8, 4'd6, 16'h00ff, 10'h3c0, 0, "M7F6_L1");
        run_nominal(7, 6, 2'd2, 1'b0, 5'd8, 4'd8, 16'h00ff, 10'h300, 0, "M7F6_L2");
        run_nominal(7, 6, 2'd3, 1'b0, 5'd8, 4'd9, 16'h00ff, 10'h200, 0, "M7F6_L3");
        run_nominal(4, 6, 2'd0, 1'b0, 5'd4, 4'd6, 16'h000f, 10'h3c0, 0, "M4F6_L0");
        run_nominal(4, 6, 2'd1, 1'b1, 5'd4, 4'd9, 16'h000f, 10'h200, 0, "M4F6_L1");
        run_nominal(4, 6, 2'd2, 1'b1, 5'd5, 4'd6, 16'h001f, 10'h3c0, 3, "M4F6_L2_delayed_owner");
        run_nominal(4, 6, 2'd3, 1'b1, 5'd5, 4'd9, 16'h001f, 10'h200, 0, "M4F6_L3");
        run_nominal(2, 9, 2'd0, 1'b0, 5'd2, 4'd9, 16'h0003, 10'h200, 0, "M2F9_L0");
        run_nominal(2, 9, 2'd1, 1'b1, 5'd2, 4'd10, 16'h0003, 10'h000, 0, "M2F9_L1_F10");
        run_nominal(2, 9, 2'd2, 1'b1, 5'd3, 4'd8, 16'h0007, 10'h300, 0, "M2F9_L2");
        run_nominal(2, 9, 2'd3, 1'b1, 5'd3, 4'd10, 16'h0007, 10'h000, 0, "M2F9_L3_F10");

        run_unsupported_case();
        run_early_selection_case();
        run_blocked_case();
        run_por_during_preload_case();
        run_repeat_selection_case();

        if (failures != 0) begin
            $display("M1 manager/H0 integration FAIL: %0d failures", failures);
            $fatal(1);
        end
        $display("M1 manager/H0 integration PASS: 12 exact cases, F10, SVA, delayed owner, errors, POR");
        $finish;
    end
endmodule

`default_nettype wire
