// Physical launch-calibration wrapper for the Vernier sensor.
//
// The selected tap is formed from real SMIC40LL delay cells, not an abstract
// ps constant.  The reference launch carries a fixed physical balance path
// alongside the selected sense launch, removing the common three-MUX selection
// latency from the differential measurement while retaining the real tap delay.
`default_nettype none

(* keep_hierarchy = "yes" *)
module vernier_launch_cal_struct (
    // Reference-domain supply rails for the launch network.
    inout  wire  vdd_ref_i,
    inout  wire  vss_ref_i,

    // One-cycle launch request.  The launch network uses this pulse directly as
    // the reference start and then routes a physically delayed version to the
    // sense start through the selected tap.
    input  logic launch_req_i,

    // Three-bit physical tap selector.  CAL_SEL=2 is the validated default
    // point recorded in the Phase 2 calibration collateral.
    input  logic [2:0] cal_sel_i,

    // Non-inverting, physically balanced reference launch.  It has the same
    // same three selected MUX propagation arcs as the sense selector.  HSPICE
    // characterization shows this is the minimum matching path that keeps
    // CAL_SEL=2 at the frozen code point without adding unused delay cells.
    output logic start_ref_o,

    // Selected delayed sense launch.
    output logic start_sense_o
);
    // A selected tap always traverses three 2:1 MUX cells.  Without a matched
    // reference path their common delay would be misinterpreted as calibration
    // offset and every valid tap would be far too late.  The balance path uses
    // the same selector bits, but ties every A/B pair to the same request so
    // it preserves three physical MUX arcs without performing data selection.
    (* keep = "true", dont_touch = "true" *)
    logic ref_mux_l1;
    (* keep = "true", dont_touch = "true" *)
    logic ref_mux_l2;
    (* keep = "true", dont_touch = "true" *)
    logic ref_mux_l3;
    (* keep = "true", dont_touch = "true" *)
    logic ref_balance_dummy_sink;

    (* keep = "true", dont_touch = "true" *)
    MXT2_X0P5M_A9TR40 u_ref_balance_mux_l1 (
        .Y   (ref_mux_l1),
        .VDD (vdd_ref_i),
        .VSS (vss_ref_i),
        .A   (launch_req_i),
        .B   (launch_req_i),
        .S0  (cal_sel_i[0])
    );

    (* keep = "true", dont_touch = "true" *)
    MXT2_X0P5M_A9TR40 u_ref_balance_mux_l2 (
        .Y   (ref_mux_l2),
        .VDD (vdd_ref_i),
        .VSS (vss_ref_i),
        .A   (ref_mux_l1),
        .B   (ref_mux_l1),
        .S0  (cal_sel_i[1])
    );

    (* keep = "true", dont_touch = "true" *)
    MXT2_X0P5M_A9TR40 u_ref_balance_mux_l3 (
        .Y   (ref_mux_l3),
        .VDD (vdd_ref_i),
        .VSS (vss_ref_i),
        .A   (ref_mux_l2),
        .B   (ref_mux_l2),
        .S0  (cal_sel_i[2])
    );

    // The mux tree is non-inverting, so its final output can drive the
    // reference chain directly.  Keeping this continuous assignment separate
    // makes the three retained physical MUX arcs easy to audit in synthesis.
    assign start_ref_o = ref_mux_l3;

    // This private MUX presents one real selected-cell data-input load at the
    // final balanced-reference MUX output.  Its output is intentionally local;
    // the cell provides the small HSPICE-characterized capacitive adjustment
    // needed for CAL_SEL=2 without adding a series timing cell or a ps delay.
    (* keep = "true", dont_touch = "true" *)
    MXT2_X0P5M_A9TR40 u_ref_balance_dummy_load (
        .Y   (ref_balance_dummy_sink),
        .VDD (vdd_ref_i),
        .VSS (vss_ref_i),
        .A   (ref_mux_l3),
        .B   (launch_req_i),
        .S0  (cal_sel_i[0])
    );

    // The tap chain is built from real buffers on the reference rails.  Tap 0
    // is the unmodified request pulse, and each subsequent tap is one more buffer
    // deeper into the selected physical delay line.
    (* keep = "true", dont_touch = "true" *)
    logic tap_0;
    (* keep = "true", dont_touch = "true" *)
    logic tap_1;
    (* keep = "true", dont_touch = "true" *)
    logic tap_2;
    (* keep = "true", dont_touch = "true" *)
    logic tap_3;
    (* keep = "true", dont_touch = "true" *)
    logic tap_4;
    (* keep = "true", dont_touch = "true" *)
    logic tap_5;
    (* keep = "true", dont_touch = "true" *)
    logic tap_6;
    (* keep = "true", dont_touch = "true" *)
    logic tap_7;

    assign tap_0 = launch_req_i;

    (* keep = "true", dont_touch = "true" *)
    BUF_X0P7M_A9TR40 u_buf_0 (
        .Y   (tap_1),
        .VDD (vdd_ref_i),
        .VSS (vss_ref_i),
        .A   (tap_0)
    );

    (* keep = "true", dont_touch = "true" *)
    BUF_X0P7M_A9TR40 u_buf_1 (
        .Y   (tap_2),
        .VDD (vdd_ref_i),
        .VSS (vss_ref_i),
        .A   (tap_1)
    );

    (* keep = "true", dont_touch = "true" *)
    BUF_X0P7M_A9TR40 u_buf_2 (
        .Y   (tap_3),
        .VDD (vdd_ref_i),
        .VSS (vss_ref_i),
        .A   (tap_2)
    );

    (* keep = "true", dont_touch = "true" *)
    BUF_X0P7M_A9TR40 u_buf_3 (
        .Y   (tap_4),
        .VDD (vdd_ref_i),
        .VSS (vss_ref_i),
        .A   (tap_3)
    );

    (* keep = "true", dont_touch = "true" *)
    BUF_X0P7M_A9TR40 u_buf_4 (
        .Y   (tap_5),
        .VDD (vdd_ref_i),
        .VSS (vss_ref_i),
        .A   (tap_4)
    );

    (* keep = "true", dont_touch = "true" *)
    BUF_X0P7M_A9TR40 u_buf_5 (
        .Y   (tap_6),
        .VDD (vdd_ref_i),
        .VSS (vss_ref_i),
        .A   (tap_5)
    );

    (* keep = "true", dont_touch = "true" *)
    BUF_X0P7M_A9TR40 u_buf_6 (
        .Y   (tap_7),
        .VDD (vdd_ref_i),
        .VSS (vss_ref_i),
        .A   (tap_6)
    );

    // The selected sense launch is a real mux tree, not a behavioral case.
    // This keeps the calibration path synthesizable and still lets CAL_SEL=2
    // resolve to a concrete physical delay tap.
    (* keep = "true", dont_touch = "true" *)
    logic mux_l1_0;
    (* keep = "true", dont_touch = "true" *)
    logic mux_l1_1;
    (* keep = "true", dont_touch = "true" *)
    logic mux_l1_2;
    (* keep = "true", dont_touch = "true" *)
    logic mux_l1_3;
    (* keep = "true", dont_touch = "true" *)
    logic mux_l2_0;
    (* keep = "true", dont_touch = "true" *)
    logic mux_l2_1;

    (* keep = "true", dont_touch = "true" *)
    MXT2_X0P5M_A9TR40 u_mux_l1_0 (
        .Y   (mux_l1_0),
        .VDD (vdd_ref_i),
        .VSS (vss_ref_i),
        .A   (tap_0),
        .B   (tap_1),
        .S0  (cal_sel_i[0])
    );

    (* keep = "true", dont_touch = "true" *)
    MXT2_X0P5M_A9TR40 u_mux_l1_1 (
        .Y   (mux_l1_1),
        .VDD (vdd_ref_i),
        .VSS (vss_ref_i),
        .A   (tap_2),
        .B   (tap_3),
        .S0  (cal_sel_i[0])
    );

    (* keep = "true", dont_touch = "true" *)
    MXT2_X0P5M_A9TR40 u_mux_l1_2 (
        .Y   (mux_l1_2),
        .VDD (vdd_ref_i),
        .VSS (vss_ref_i),
        .A   (tap_4),
        .B   (tap_5),
        .S0  (cal_sel_i[0])
    );

    (* keep = "true", dont_touch = "true" *)
    MXT2_X0P5M_A9TR40 u_mux_l1_3 (
        .Y   (mux_l1_3),
        .VDD (vdd_ref_i),
        .VSS (vss_ref_i),
        .A   (tap_6),
        .B   (tap_7),
        .S0  (cal_sel_i[0])
    );

    (* keep = "true", dont_touch = "true" *)
    MXT2_X0P5M_A9TR40 u_mux_l2_0 (
        .Y   (mux_l2_0),
        .VDD (vdd_ref_i),
        .VSS (vss_ref_i),
        .A   (mux_l1_0),
        .B   (mux_l1_1),
        .S0  (cal_sel_i[1])
    );

    (* keep = "true", dont_touch = "true" *)
    MXT2_X0P5M_A9TR40 u_mux_l2_1 (
        .Y   (mux_l2_1),
        .VDD (vdd_ref_i),
        .VSS (vss_ref_i),
        .A   (mux_l1_2),
        .B   (mux_l1_3),
        .S0  (cal_sel_i[1])
    );

    (* keep = "true", dont_touch = "true" *)
    MXT2_X0P5M_A9TR40 u_mux_l3 (
        .Y   (start_sense_o),
        .VDD (vdd_ref_i),
        .VSS (vss_ref_i),
        .A   (mux_l2_0),
        .B   (mux_l2_1),
        .S0  (cal_sel_i[2])
    );

endmodule

`default_nettype wire
