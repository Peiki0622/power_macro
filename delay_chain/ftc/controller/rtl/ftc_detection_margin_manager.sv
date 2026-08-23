// ============================================================================
// FTC M1 safe one-shot detection-margin configuration manager
// ============================================================================
// This module owns only H0's future detector-input controls.  It never edits
// the frozen calibration controller or H0 ownership mux.  Before H0 grants
// detection ownership, it holds the exact H0 snapshot with reset asserted and
// S_CLK low.  After ownership, it makes exactly one registered target-vector
// update, keeps the sensor inactive, and waits at least one full 400 MHz
// controller cycle before declaring the margin configuration valid.
//
// The implementation intentionally has no synthesizable functions, arithmetic
// codebook derivation, runtime reprogramming, timeout, probe generator, or
// alarm logic.  All state is reset only by controller POR, matching H0's
// one-way ownership model.
// ============================================================================
`timescale 1ns/1ps
`default_nettype none

module ftc_detection_margin_manager (
    // ------------------------------------------------------------------------
    // Trusted M1 sequencing clock and POR
    // ------------------------------------------------------------------------
    // cal_clk_i is the same 400 MHz H0 ownership clock.  The selection request
    // is contractually synchronous to this clock; M1 contains no CDC logic.
    // ctrl_por_n_i is the only way to clear a selected configuration or error.
    input  logic        cal_clk_i,
    input  logic        ctrl_por_n_i,

    // ------------------------------------------------------------------------
    // Immutable H0 snapshot and ownership-contract inputs
    // ------------------------------------------------------------------------
    // H0 captures these fields once after calibration.  The raw thermometer
    // vectors, rather than a newly decoded copy of the binary codes, are used
    // for preloading so the H0 exact-equality check observes its own snapshot.
    input  logic        cal_cfg_valid_i,
    input  logic [4:0]  cal_medium_code_snapshot_i,
    input  logic [3:0]  cal_fine_code_snapshot_i,
    input  logic [15:0] cal_medium_therm_snapshot_i,
    input  logic [9:0]  cal_fine_therm_snapshot_i,
    input  logic        det_prepare_i,
    input  logic        det_owner_valid_i,
    input  logic        handoff_blocked_i,

    // ------------------------------------------------------------------------
    // One-shot, cal_clk_i-synchronous margin request
    // ------------------------------------------------------------------------
    // margin_select_valid_i is accepted only once in WAIT_SELECT after H0 has
    // advertised det_prepare_i.  An early request, a repeated request, an
    // unsupported snapshot, or a blocked handoff enters sticky REJECTED state.
    input  logic [1:0]  margin_sel_i,
    input  logic        margin_select_valid_i,

    // ------------------------------------------------------------------------
    // Detector-side inputs supplied to the frozen H0 handoff wrapper
    // ------------------------------------------------------------------------
    // H0 samples ready only after the preloaded raw vectors and safe controls
    // have been stable.  These outputs remain registered at every point where
    // a control vector may change, preventing a mapper combinational glitch
    // from reaching the sensor boundary.
    output logic        det_takeover_ready_o,
    output logic        det_sense_dff_reset_o,
    output logic        det_sense_s_clk_o,
    output logic [15:0] det_medium_therm_o,
    output logic [9:0]  det_fine_therm_o,

    // ------------------------------------------------------------------------
    // M1 status forwarded to future T0/D0 logic
    // ------------------------------------------------------------------------
    // margin_cfg_valid_o means the target was applied under DET ownership and
    // remained stable for at least one complete controller period.  M1 leaves
    // reset high and S_CLK low even after this signal rises; probe scheduling
    // is explicitly deferred to D0.
    output logic        margin_cfg_valid_o,
    output logic        mapping_supported_o,
    output logic        trip_qualified_o,
    output logic        margin_protocol_error_o,
    output logic [4:0]  m_det_o,
    output logic [3:0]  f_det_o,
    output logic [1:0]  margin_level_o
);

    // Explicit encodings keep the minimal sequencing protocol reviewable in
    // waveforms and make it clear that no hidden runtime configuration state
    // exists.  REJECTED is a POR-only recovery state and never asserts ready.
    localparam logic [3:0] M_WAIT_CAL    = 4'd0;
    localparam logic [3:0] M_WAIT_SELECT = 4'd1;
    localparam logic [3:0] M_PRELOAD     = 4'd2;
    localparam logic [3:0] M_WAIT_OWNER  = 4'd3;
    localparam logic [3:0] M_APPLY       = 4'd4;
    localparam logic [3:0] M_SETTLE      = 4'd5;
    localparam logic [3:0] M_READY       = 4'd6;
    localparam logic [3:0] M_REJECTED    = 4'd7;

    logic [3:0]  state_q;
    logic [3:0]  state_d;

    // The mapper is combinational by design, but every selected value is
    // copied into these registers before being observable at an H0 input.
    logic        mapper_mapping_supported;
    logic        mapper_trip_qualified;
    logic [4:0]  mapper_m_det;
    logic [3:0]  mapper_f_det;
    logic [15:0] mapper_medium_therm;
    logic [9:0]  mapper_fine_therm;

    logic        mapping_supported_q;
    logic        trip_qualified_q;
    logic [4:0]  m_det_q;
    logic [3:0]  f_det_q;
    logic [1:0]  margin_level_q;
    // H0's snapshot is immutable once valid, but recording that the raw rails
    // were copied lets a malformed early request still settle at the first
    // subsequently available snapshot instead of retaining POR defaults.
    logic        snapshot_loaded_q;
    logic        margin_protocol_error_q;
    logic        margin_cfg_valid_q;
    // The selected target is captured with margin_sel_i.  Keeping it separate
    // from live detector-control registers prevents later changes on an idle
    // margin_sel_i bus from altering the pending one-shot configuration.
    logic [15:0] target_medium_therm_q;
    logic [9:0]  target_fine_therm_q;
    logic [15:0] det_medium_therm_q;
    logic [9:0]  det_fine_therm_q;

    ftc_detection_margin_mapper u_exact_mapper (
        .cal_medium_code_snapshot_i(cal_medium_code_snapshot_i),
        .cal_fine_code_snapshot_i  (cal_fine_code_snapshot_i),
        .margin_sel_i               (margin_sel_i),
        .mapping_supported_o        (mapper_mapping_supported),
        .trip_qualified_o           (mapper_trip_qualified),
        .m_det_o                    (mapper_m_det),
        .f_det_o                    (mapper_f_det),
        .target_medium_therm_o      (mapper_medium_therm),
        .target_fine_therm_o        (mapper_fine_therm)
    );

    // The state transition logic never depends on detector thermometer data.
    // In particular, it cannot form a combinational ready-to-vector path into
    // H0.  A missing owner response simply waits; M1 deliberately has no
    // timeout policy because recovery/availability belongs to later stages.
    always_comb begin
        state_d = state_q;
        case (state_q)
            M_WAIT_CAL: begin
                if (handoff_blocked_i || margin_select_valid_i)
                    state_d = M_REJECTED;
                else if (cal_cfg_valid_i)
                    state_d = M_WAIT_SELECT;
            end

            M_WAIT_SELECT: begin
                if (handoff_blocked_i)
                    state_d = M_REJECTED;
                else if (margin_select_valid_i) begin
                    if (det_prepare_i && mapper_mapping_supported)
                        state_d = M_PRELOAD;
                    else
                        state_d = M_REJECTED;
                end
            end

            // PRELOAD lasts one full cycle.  H0 therefore observes stable
            // snapshot-equal detector inputs for a cycle before ready rises.
            M_PRELOAD: begin
                if (handoff_blocked_i || margin_select_valid_i)
                    state_d = M_REJECTED;
                else
                    state_d = M_WAIT_OWNER;
            end

            M_WAIT_OWNER: begin
                if (handoff_blocked_i || margin_select_valid_i)
                    state_d = M_REJECTED;
                else if (det_owner_valid_i)
                    state_d = M_APPLY;
            end

            // The target is written on entry to M_APPLY.  M_SETTLE becomes
            // visible on the following clock edge, exactly one full period
            // later, which is also when margin_cfg_valid is asserted.
            M_APPLY: begin
                if (handoff_blocked_i || margin_select_valid_i)
                    state_d = M_REJECTED;
                else
                    state_d = M_SETTLE;
            end

            M_SETTLE: begin
                if (handoff_blocked_i || margin_select_valid_i)
                    state_d = M_REJECTED;
                else
                    state_d = M_READY;
            end

            M_READY: begin
                if (handoff_blocked_i || margin_select_valid_i)
                    state_d = M_REJECTED;
            end

            M_REJECTED: state_d = M_REJECTED;
            default:    state_d = M_REJECTED;
        endcase
    end

    // All detector configuration outputs are stored in flops.  Their safe
    // reset/S_CLK levels are constants for all M1 states, so no M1 behavior
    // can issue a detection probe or release the sensor capture DFF.
    always_ff @(posedge cal_clk_i or negedge ctrl_por_n_i) begin
        if (!ctrl_por_n_i) begin
            state_q                 <= M_WAIT_CAL;
            mapping_supported_q     <= 1'b0;
            trip_qualified_q        <= 1'b0;
            m_det_q                 <= 5'd0;
            f_det_q                 <= 4'd0;
            margin_level_q          <= 2'd0;
            snapshot_loaded_q       <= 1'b0;
            margin_protocol_error_q <= 1'b0;
            margin_cfg_valid_q      <= 1'b0;
            target_medium_therm_q   <= 16'h0000;
            target_fine_therm_q     <= 10'h3ff;
            det_medium_therm_q      <= 16'h0000;
            det_fine_therm_q        <= 10'h3ff;
        end else begin
            state_q <= state_d;

            // A request outside its sole legal acceptance state is a sticky
            // protocol failure.  The retained detector controls are not
            // rewritten, so the rejection cannot create a rail glitch.
            if (handoff_blocked_i ||
                (margin_select_valid_i && (state_q != M_WAIT_SELECT)) ||
                (margin_select_valid_i && (state_q == M_WAIT_SELECT) &&
                 (!det_prepare_i || !mapper_mapping_supported))) begin
                margin_protocol_error_q <= 1'b1;
                margin_cfg_valid_q      <= 1'b0;
            end

            // Copy H0 raw rails exactly once whenever the immutable snapshot
            // first becomes available.  This is deliberately independent of
            // the request state: an early malformed request still leaves the
            // detector-side inputs at the first stable snapshot, while its
            // sticky error continues to prohibit ready/ownership.
            if (cal_cfg_valid_i && !snapshot_loaded_q) begin
                det_medium_therm_q <= cal_medium_therm_snapshot_i;
                det_fine_therm_q   <= cal_fine_therm_snapshot_i;
                snapshot_loaded_q  <= 1'b1;
            end

            // The only legal margin request latches the complete mapper
            // result.  Target rails remain private in these registers during
            // PRELOAD/WAIT_OWNER and cannot replace the snapshot prematurely.
            if ((state_q == M_WAIT_SELECT) && margin_select_valid_i &&
                det_prepare_i && mapper_mapping_supported && !handoff_blocked_i) begin
                mapping_supported_q <= 1'b1;
                trip_qualified_q    <= mapper_trip_qualified;
                m_det_q             <= mapper_m_det;
                f_det_q             <= mapper_f_det;
                margin_level_q      <= margin_sel_i;
                target_medium_therm_q <= mapper_medium_therm;
                target_fine_therm_q   <= mapper_fine_therm;
            end

            // H0 has granted DET ownership only after its own safe handoff.
            // At this edge the manager atomically replaces both registered
            // vectors while reset remains high and S_CLK remains low.
            if ((state_q == M_WAIT_OWNER) && det_owner_valid_i &&
                !handoff_blocked_i && !margin_select_valid_i) begin
                det_medium_therm_q <= target_medium_therm_q;
                det_fine_therm_q   <= target_fine_therm_q;
            end

            // M_APPLY occupied the full interval since the vector update.
            // Asserting valid at entry to M_SETTLE proves one complete 2.5 ns
            // controller cycle elapsed, without adding an unnecessary delay.
            if ((state_q == M_APPLY) && !handoff_blocked_i &&
                !margin_select_valid_i) begin
                margin_cfg_valid_q <= 1'b1;
            end
        end
    end

    // H0 must receive a registered precharge indication only after PRELOAD.
    // In every other state—including REJECTED—ready remains low and H0 keeps
    // CAL ownership or its own safe blocked behavior.
    always_comb begin
        det_takeover_ready_o      = (state_q == M_WAIT_OWNER);
        det_sense_dff_reset_o     = 1'b1;
        det_sense_s_clk_o         = 1'b0;
        det_medium_therm_o        = det_medium_therm_q;
        det_fine_therm_o          = det_fine_therm_q;
        margin_cfg_valid_o        = margin_cfg_valid_q;
        mapping_supported_o       = mapping_supported_q;
        trip_qualified_o          = trip_qualified_q;
        margin_protocol_error_o   = margin_protocol_error_q;
        m_det_o                   = m_det_q;
        f_det_o                   = f_det_q;
        margin_level_o            = margin_level_q;
    end

endmodule

`default_nettype wire
