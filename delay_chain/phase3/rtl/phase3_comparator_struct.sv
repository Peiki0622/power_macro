// Structural wrapper for one real Phase-3 comparator DFF.
//
// D is driven by the LVT tap and CK by the corresponding RVT tap, exactly as
// in the retained physical deck.  The selected DFF owns edge sampling; there
// is intentionally no always_ff replacement for this analog timing decision.
`default_nettype none

(* keep_hierarchy = "yes" *)
module phase3_comparator_struct (
    // Same-rail power interface:
    // vdd_a_i and vss_a_i supply the selected comparator DFF and correspond to
    // its physical well connections in the characterized CDL implementation.
    inout  wire  vdd_a_i,
    inout  wire  vss_a_i,

    // Physical-comparator interface:
    // lvt_d_i drives D, rvt_ck_i drives CK, and rst_i drives the asynchronous
    // R input of the real DFF.  q_o is this stage's captured thermometer bit.
    input  logic lvt_d_i,
    input  logic rvt_ck_i,
    input  logic rst_i,
    output logic q_o
);
    // SMIC40LL DFF Verilog ports are Q, VDD, VSS, CK, D, R.  The CDL order
    // additionally contains VNW/VPW, both tied to VDD_A/VSS_A in SPICE.
    (* keep = "true", dont_touch = "true" *)
    DFFRPQ_X0P5M_A9TR40 u_comparator_dff (
        .Q   (q_o),
        .VDD (vdd_a_i),
        .VSS (vss_a_i),
        .CK  (rvt_ck_i),
        .D   (lvt_d_i),
        .R   (rst_i)
    );
endmodule

`default_nettype wire
