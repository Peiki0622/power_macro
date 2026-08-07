// Structural wrapper for one SMIC40LL sense stage.
//
// The sense chain must preserve the real inverter topology used by the SPICE
// characterization.  This module therefore does not infer logic; it only
// instantiates two explicit INV_X0P5M_A9TR40 cells on the local VDD_A/VSS_A
// domain and keeps the hierarchy intact for synthesis and audit.
`default_nettype none

(* keep_hierarchy = "yes" *)
module vernier_sense_stage_struct (
    // Local chiplet-A supply rail for the sense chain.
    inout  wire  vdd_a_i,

    // Local chiplet-A return rail for the sense chain.
    inout  wire  vss_a_i,

    // Non-inverting stage input.
    input  logic a_i,

    // Non-inverting stage output.
    output logic y_o
);
    // The middle tap is private to this wrapper and is retained so the two
    // inverter cells remain visible as physical stages during synthesis.
    (* keep = "true", dont_touch = "true" *)
    logic sense_mid;

    // First inverter.  The RTL power-aware model exposes VDD/VSS; the CDL well
    // pins are physically tied to those same rails in the characterized cell.
    (* keep = "true", dont_touch = "true" *)
    INV_X0P5M_A9TR40 u_inv_sense_a (
        .Y   (sense_mid),
        .VDD (vdd_a_i),
        .VSS (vss_a_i),
        .A   (a_i)
    );

    // Second inverter restores the observable polarity while keeping the tap
    // as a real standard-cell output instead of a behavioral delay.
    (* keep = "true", dont_touch = "true" *)
    INV_X0P5M_A9TR40 u_inv_sense_b (
        .Y   (y_o),
        .VDD (vdd_a_i),
        .VSS (vss_a_i),
        .A   (sense_mid)
    );

endmodule

`default_nettype wire
