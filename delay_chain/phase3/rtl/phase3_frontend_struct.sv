// Complete selected same-rail physical frontend.
//
// The module contains the physical launch network, two 32-stage paths, and 32
// real standard-cell DFF comparators.  Every physical cell receives only the
// VDD_A/VSS_A pair exposed at this boundary; no reference-island port exists.
`default_nettype none

(* keep_hierarchy = "yes" *)
module phase3_frontend_struct (
    // Same-rail power interface:
    // vdd_a_i and vss_a_i feed every calibration, RVT, LVT, and comparator
    // cell in this physical hierarchy.  No separate reference supply exists.
    inout  wire        vdd_a_i,
    inout  wire        vss_a_i,

    // Physical control interface:
    // launch_req_i enters the calibration tree, cal_sel_i selects its static
    // physical RVT tap, and rst_i asynchronously resets all 32 comparator DFFs.
    // The top-level wrapper freezes cal_sel_i at the characterized setting.
    input  logic       launch_req_i,
    input  logic [2:0] cal_sel_i,
    input  logic       rst_i,

    // Physical-capture interface:
    // raw_thermometer_o is the 32-bit comparator-DFF capture ordered from the
    // earliest stage at bit 0 through the latest stage at bit 31.
    output logic [31:0] raw_thermometer_o
);
    // Separate launch nodes are required because CAL_SEL intentionally delays
    // only the RVT branch; both nodes still traverse equal-depth MUX trees.
    logic rvt_launch;
    logic lvt_launch;

    phase3_launch_cal_struct u_launch_calibration (
        .vdd_a_i     (vdd_a_i),
        .vss_a_i     (vss_a_i),
        .launch_req_i(launch_req_i),
        .cal_sel_i   (cal_sel_i),
        .rvt_launch_o(rvt_launch),
        .lvt_launch_o(lvt_launch)
    );

    // Tap index zero is the selected launch; indexes 1..32 are outputs after
    // successive two-inverter stages.  The DFF at stage N observes tap N+1.
    (* keep = "true", dont_touch = "true" *) logic [32:0] rvt_tap;
    (* keep = "true", dont_touch = "true" *) logic [32:0] lvt_tap;
    assign rvt_tap[0] = rvt_launch;
    assign lvt_tap[0] = lvt_launch;

    generate
        for (genvar stage_index = 0; stage_index < 32; stage_index = stage_index + 1) begin : g_vernier_stage
            // RVT path: two selected RVT cells on the sole local rail pair.
            phase3_rvt_stage_struct u_rvt_stage (
                .vdd_a_i(vdd_a_i), .vss_a_i(vss_a_i),
                .a_i(rvt_tap[stage_index]), .y_o(rvt_tap[stage_index + 1])
            );

            // LVT path: two selected LVT cells plus exactly one dummy input load.
            phase3_lvt_stage_struct u_lvt_stage (
                .vdd_a_i(vdd_a_i), .vss_a_i(vss_a_i),
                .a_i(lvt_tap[stage_index]), .y_o(lvt_tap[stage_index + 1])
            );

            // Comparator direction matches the physical deck: LVT tap drives
            // D and RVT tap drives CK.  Bit numbering preserves stage order.
            phase3_comparator_struct u_comparator (
                .vdd_a_i(vdd_a_i), .vss_a_i(vss_a_i),
                .lvt_d_i(lvt_tap[stage_index + 1]),
                .rvt_ck_i(rvt_tap[stage_index + 1]),
                .rst_i(rst_i), .q_o(raw_thermometer_o[stage_index])
            );
        end
    endgenerate
endmodule

`default_nettype wire
