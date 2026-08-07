// Structural wrapper for the selected SMIC40LL comparator DFF.
//
// The comparator bank must preserve the discovered DFFRPQ_X0P5M_A9TR40 cell,
// including its active-high asynchronous clear and reference-domain VDD/VSS
// pins.  No always_ff replacement is allowed here.
`default_nettype none

(* keep_hierarchy = "yes" *)
module vernier_comparator_struct (
    // Reference-domain supply rail for the comparator DFF.
    inout  wire  vdd_ref_i,

    // Reference-domain return rail for the comparator DFF.
    inout  wire  vss_ref_i,

    // Sense-chain data input sampled by the comparator.
    input  logic d_i,

    // Reference-chain clock input that decides the sampled edge.
    input  logic ck_i,

    // Active-high asynchronous clear shared by the full comparator bank.
    input  logic rst_i,

    // Captured comparator bit.
    output logic q_o
);
    // The selected DFF is instantiated directly so the macro boundary keeps
    // the physical implementation visible to both synthesis and verification.
    (* keep = "true", dont_touch = "true" *)
    DFFRPQ_X0P5M_A9TR40 u_dff (
        .Q   (q_o),
        .VDD (vdd_ref_i),
        .VSS (vss_ref_i),
        .CK  (ck_i),
        .D   (d_i),
        .R   (rst_i)
    );
endmodule

`default_nettype wire
