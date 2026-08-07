// Structural Vernier sensor frontend.
//
// This wrapper connects the calibrated launch network, the sense/reference
// stage chains, and the comparator bank.  It returns only the raw thermometer
// word so the digital backend can stay separate and easy to verify.
`default_nettype none

(* keep_hierarchy = "yes" *)
module vernier_frontend_struct #(
    parameter int M_STAGES = 32,
    parameter int DUMMY_LOAD_COUNT = 1
) (
    // Local sense-domain supply rails.
    inout  wire  vdd_a_i,
    inout  wire  vss_a_i,

    // Local reference-domain supply rails.
    inout  wire  vdd_ref_i,
    inout  wire  vss_ref_i,

    // One-cycle launch request used by the physical launch-calibration path.
    input  logic launch_req_i,

    // Selected physical launch tap.  The default validated point is CAL_SEL=2.
    input logic [2:0] cal_sel_i,

    // Shared reset for the comparator DFF bank.
    input logic sensor_reset_i,

    // Raw comparator-bank thermometer word.
    output logic [M_STAGES-1:0] raw_code_o
);
    // The launch network remains a real cell chain.  The request pulse is
    // routed directly into the calibrated launch wrapper, which produces the
    // reference and sense start nodes used by the two physical delay chains.
    logic start_ref;
    logic start_sense;

    vernier_launch_cal_struct u_launch_cal (
        .vdd_ref_i     (vdd_ref_i),
        .vss_ref_i     (vss_ref_i),
        .launch_req_i  (launch_req_i),
        .cal_sel_i     (cal_sel_i),
        .start_ref_o   (start_ref),
        .start_sense_o (start_sense)
    );

    // Private stage taps.  Tap zero is the selected launch node and each stage
    // pushes the signal through one more non-inverting cell pair.
    logic [M_STAGES:0] sense_tap;
    logic [M_STAGES:0] ref_tap;

    assign sense_tap[0] = start_sense;
    assign ref_tap[0]   = start_ref;

    generate
        for (genvar stage_index = 0; stage_index < M_STAGES; stage_index++) begin : g_stage
            // The sense chain is powered from VDD_A/VSS_A and remains separate
            // from the reference island by construction.
            vernier_sense_stage_struct u_sense_stage (
                .vdd_a_i (vdd_a_i),
                .vss_a_i (vss_a_i),
                .a_i     (sense_tap[stage_index]),
                .y_o     (sense_tap[stage_index + 1])
            );

            // The reference chain uses the configured dummy load count so the
            // calibrated electrical loading matches the validated deck.
            vernier_reference_stage_struct #(
                .DUMMY_LOAD_COUNT(DUMMY_LOAD_COUNT)
            ) u_reference_stage (
                .vdd_ref_i (vdd_ref_i),
                .vss_ref_i (vss_ref_i),
                .a_i       (ref_tap[stage_index]),
                .y_o       (ref_tap[stage_index + 1])
            );

            // Each comparator samples the sense tap on the corresponding
            // reference edge and stores the bit into the raw thermometer word.
            vernier_comparator_struct u_comparator (
                .vdd_ref_i (vdd_ref_i),
                .vss_ref_i (vss_ref_i),
                .d_i       (sense_tap[stage_index + 1]),
                .ck_i      (ref_tap[stage_index + 1]),
                .rst_i     (sensor_reset_i),
                .q_o       (raw_code_o[stage_index])
            );
        end
    endgenerate

endmodule

`default_nettype wire
