// Physical same-rail eight-tap launch calibration network.
//
// This hierarchy mirrors the final HSPICE deck.  RVT taps 1 and 2 use MXT2
// cells with A=B for fine physical delay; taps 3 through 7 use BUF cells for
// coarse delay.  Both branch selectors have three MXT2 levels, so selector
// propagation is common-mode.  No ps constant, source timing operator, or behavioral mux is
// used in the calibrated launch path.
`default_nettype none

(* keep_hierarchy = "yes" *)
module phase3_launch_cal_struct (
    // Same-rail power interface:
    // vdd_a_i and vss_a_i supply every BUF and MXT2 cell.  vss_a_i also holds
    // the two fixed fine-tap MXT2 select pins at the physical zero level.
    inout  wire        vdd_a_i,
    inout  wire        vss_a_i,

    // Calibration-control interface:
    // launch_req_i fans out to RVT tap zero and every LVT balance-tree leaf.
    // cal_sel_i is static for a sample: bit 0 selects within a pair, bit 1
    // selects within a four-tap group, and bit 2 selects the four-tap group.
    input  logic       launch_req_i,
    input  logic [2:0] cal_sel_i,

    // Calibrated-launch interface:
    // rvt_launch_o feeds the selected RVT 32-stage chain; lvt_launch_o feeds
    // the equal-depth LVT balance path.  Both are produced by real MUX trees.
    output logic       rvt_launch_o,
    output logic       lvt_launch_o
);
    // The selected CK input-load count is a package localparam shared with
    // configuration checks.  Importing it here keeps this structural module
    // self-contained when elaborated below the frontend hierarchy.
    import phase3_calibration_pkg::*;

    // Eight RVT tap nodes.  Tap zero is intentionally direct; fine taps use
    // MXT2 A=B and coarse taps use BUF, matching the calibrated SPICE network.
    (* keep = "true", dont_touch = "true" *) logic rvt_tap_0;
    (* keep = "true", dont_touch = "true" *) logic rvt_tap_1;
    (* keep = "true", dont_touch = "true" *) logic rvt_tap_2;
    (* keep = "true", dont_touch = "true" *) logic rvt_tap_3;
    (* keep = "true", dont_touch = "true" *) logic rvt_tap_4;
    (* keep = "true", dont_touch = "true" *) logic rvt_tap_5;
    (* keep = "true", dont_touch = "true" *) logic rvt_tap_6;
    (* keep = "true", dont_touch = "true" *) logic rvt_tap_7;

    assign rvt_tap_0 = launch_req_i;

    // Fine tap 1: MXT2 ports Y,VDD,VSS,A,B,S0.  A=B makes data selection
    // constant while retaining a real non-inverting MUX propagation delay.
    (* keep = "true", dont_touch = "true" *)
    MXT2_X0P5M_A9TR40 u_rvt_fine_tap_1 (
        .Y(rvt_tap_1), .VDD(vdd_a_i), .VSS(vss_a_i),
        .A(rvt_tap_0), .B(rvt_tap_0), .S0(vss_a_i)
    );

    // Fine tap 2: the second A=B MXT2 delay increment remains independent of
    // CAL_SEL so selecting a tap cannot change that tap's own delay.
    (* keep = "true", dont_touch = "true" *)
    MXT2_X0P5M_A9TR40 u_rvt_fine_tap_2 (
        .Y(rvt_tap_2), .VDD(vdd_a_i), .VSS(vss_a_i),
        .A(rvt_tap_1), .B(rvt_tap_1), .S0(vss_a_i)
    );

    // Coarse taps 3-7: each BUF ports Y,VDD,VSS,A and adds one real RVT arc.
    (* keep = "true", dont_touch = "true" *)
    BUF_X0P7M_A9TR40 u_rvt_coarse_tap_3 (.Y(rvt_tap_3), .VDD(vdd_a_i), .VSS(vss_a_i), .A(rvt_tap_2));
    (* keep = "true", dont_touch = "true" *)
    BUF_X0P7M_A9TR40 u_rvt_coarse_tap_4 (.Y(rvt_tap_4), .VDD(vdd_a_i), .VSS(vss_a_i), .A(rvt_tap_3));
    (* keep = "true", dont_touch = "true" *)
    BUF_X0P7M_A9TR40 u_rvt_coarse_tap_5 (.Y(rvt_tap_5), .VDD(vdd_a_i), .VSS(vss_a_i), .A(rvt_tap_4));
    (* keep = "true", dont_touch = "true" *)
    BUF_X0P7M_A9TR40 u_rvt_coarse_tap_6 (.Y(rvt_tap_6), .VDD(vdd_a_i), .VSS(vss_a_i), .A(rvt_tap_5));
    (* keep = "true", dont_touch = "true" *)
    BUF_X0P7M_A9TR40 u_rvt_coarse_tap_7 (.Y(rvt_tap_7), .VDD(vdd_a_i), .VSS(vss_a_i), .A(rvt_tap_6));

    // RVT binary MUX tree: eight physical leaves, four level-0 nodes, two
    // level-1 nodes, and one selected launch.  CAL_SEL is static per sample.
    (* keep = "true", dont_touch = "true" *) logic rvt_mux_l0_0, rvt_mux_l0_1, rvt_mux_l0_2, rvt_mux_l0_3;
    (* keep = "true", dont_touch = "true" *) logic rvt_mux_l1_0, rvt_mux_l1_1;
    (* keep = "true", dont_touch = "true" *)
    MXT2_X0P5M_A9TR40 u_rvt_mux_l0_0 (.Y(rvt_mux_l0_0), .VDD(vdd_a_i), .VSS(vss_a_i), .A(rvt_tap_0), .B(rvt_tap_1), .S0(cal_sel_i[0]));
    (* keep = "true", dont_touch = "true" *)
    MXT2_X0P5M_A9TR40 u_rvt_mux_l0_1 (.Y(rvt_mux_l0_1), .VDD(vdd_a_i), .VSS(vss_a_i), .A(rvt_tap_2), .B(rvt_tap_3), .S0(cal_sel_i[0]));
    (* keep = "true", dont_touch = "true" *)
    MXT2_X0P5M_A9TR40 u_rvt_mux_l0_2 (.Y(rvt_mux_l0_2), .VDD(vdd_a_i), .VSS(vss_a_i), .A(rvt_tap_4), .B(rvt_tap_5), .S0(cal_sel_i[0]));
    (* keep = "true", dont_touch = "true" *)
    MXT2_X0P5M_A9TR40 u_rvt_mux_l0_3 (.Y(rvt_mux_l0_3), .VDD(vdd_a_i), .VSS(vss_a_i), .A(rvt_tap_6), .B(rvt_tap_7), .S0(cal_sel_i[0]));
    (* keep = "true", dont_touch = "true" *)
    MXT2_X0P5M_A9TR40 u_rvt_mux_l1_0 (.Y(rvt_mux_l1_0), .VDD(vdd_a_i), .VSS(vss_a_i), .A(rvt_mux_l0_0), .B(rvt_mux_l0_1), .S0(cal_sel_i[1]));
    (* keep = "true", dont_touch = "true" *)
    MXT2_X0P5M_A9TR40 u_rvt_mux_l1_1 (.Y(rvt_mux_l1_1), .VDD(vdd_a_i), .VSS(vss_a_i), .A(rvt_mux_l0_2), .B(rvt_mux_l0_3), .S0(cal_sel_i[1]));
    (* keep = "true", dont_touch = "true" *)
    MXT2_X0P5M_A9TR40 u_rvt_mux_l2_0 (.Y(rvt_launch_o), .VDD(vdd_a_i), .VSS(vss_a_i), .A(rvt_mux_l1_0), .B(rvt_mux_l1_1), .S0(cal_sel_i[2]));

    // LVT balance tree: every leaf is the same request, but all three MUX
    // levels remain real cells so their propagation is common-mode with RVT.
    (* keep = "true", dont_touch = "true" *) logic lvt_mux_l0_0, lvt_mux_l0_1, lvt_mux_l0_2, lvt_mux_l0_3;
    (* keep = "true", dont_touch = "true" *) logic lvt_mux_l1_0, lvt_mux_l1_1;
    // Private RVT sink outputs represent six real BUF input loads on CK.  The
    // packed declaration is static hardware: each generated instance below
    // receives one bit, and no sink output can feed a timing-path cell.
    (* keep = "true", dont_touch = "true" *) logic [5:0] rvt_launch_load_sink;
    (* keep = "true", dont_touch = "true" *)
    MXT2_X0P5M_A9TR40 u_lvt_mux_l0_0 (.Y(lvt_mux_l0_0), .VDD(vdd_a_i), .VSS(vss_a_i), .A(launch_req_i), .B(launch_req_i), .S0(cal_sel_i[0]));
    (* keep = "true", dont_touch = "true" *)
    MXT2_X0P5M_A9TR40 u_lvt_mux_l0_1 (.Y(lvt_mux_l0_1), .VDD(vdd_a_i), .VSS(vss_a_i), .A(launch_req_i), .B(launch_req_i), .S0(cal_sel_i[0]));
    (* keep = "true", dont_touch = "true" *)
    MXT2_X0P5M_A9TR40 u_lvt_mux_l0_2 (.Y(lvt_mux_l0_2), .VDD(vdd_a_i), .VSS(vss_a_i), .A(launch_req_i), .B(launch_req_i), .S0(cal_sel_i[0]));
    (* keep = "true", dont_touch = "true" *)
    MXT2_X0P5M_A9TR40 u_lvt_mux_l0_3 (.Y(lvt_mux_l0_3), .VDD(vdd_a_i), .VSS(vss_a_i), .A(launch_req_i), .B(launch_req_i), .S0(cal_sel_i[0]));
    (* keep = "true", dont_touch = "true" *)
    MXT2_X0P5M_A9TR40 u_lvt_mux_l1_0 (.Y(lvt_mux_l1_0), .VDD(vdd_a_i), .VSS(vss_a_i), .A(lvt_mux_l0_0), .B(lvt_mux_l0_1), .S0(cal_sel_i[1]));
    (* keep = "true", dont_touch = "true" *)
    MXT2_X0P5M_A9TR40 u_lvt_mux_l1_1 (.Y(lvt_mux_l1_1), .VDD(vdd_a_i), .VSS(vss_a_i), .A(lvt_mux_l0_2), .B(lvt_mux_l0_3), .S0(cal_sel_i[1]));
    (* keep = "true", dont_touch = "true" *)
    MXT2_X0P5M_A9TR40 u_lvt_mux_l2_0 (.Y(lvt_launch_o), .VDD(vdd_a_i), .VSS(vss_a_i), .A(lvt_mux_l1_0), .B(lvt_mux_l1_1), .S0(cal_sel_i[2]));

    // The previous sparse implementation put two private BUF input loads on
    // D/companion.  Physical A/B data showed that they moved D later, away
    // from the aperture.  The repaired topology removes them and applies six
    // real BUF inputs to CK/RVT instead.  A generate loop emits fixed cells at
    // elaboration; it is fully synthesizable and adds no runtime selection.
    generate
        for (genvar load_index = 0;
             load_index < WIDE_RANGE_RVT_LAUNCH_LOAD_COUNT;
             load_index = load_index + 1) begin : g_rvt_launch_load
            (* keep = "true", dont_touch = "true" *)
            BUF_X0P7M_A9TR40 u_rvt_launch_load (
                .Y(rvt_launch_load_sink[load_index]), .VDD(vdd_a_i),
                .VSS(vss_a_i), .A(rvt_launch_o)
            );
        end
    endgenerate
endmodule

`default_nettype wire
