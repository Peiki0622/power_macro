// One selected RVT non-inverting Vernier stage.
//
// This wrapper deliberately contains two explicit SMIC40LL RVT inverters.  A
// synthesizer must not replace this with a Boolean inversion because the two
// cell propagation arcs are the physical delay accumulated by the sensor.
`default_nettype none

(* keep_hierarchy = "yes" *)
module phase3_rvt_stage_struct (
    // Same-rail power interface:
    // vdd_a_i and vss_a_i connect directly to both RVT inverter VDD/VSS pins,
    // preserving the selected physical cell implementation of this stage.
    inout  wire  vdd_a_i,
    inout  wire  vss_a_i,

    // RVT timing-path interface:
    // a_i is the arrival from the preceding RVT stage or calibrated launch;
    // y_o is the same-polarity arrival after the explicit two-inverter stage.
    input  logic a_i,
    output logic y_o
);
    // Private inter-inverter node.  Keeping it named makes the two-cell
    // topology auditable and prevents hierarchy flattening from hiding a cell.
    (* keep = "true", dont_touch = "true" *) logic rvt_mid;

    // SMIC40LL RTL cell ports: Y=output, VDD=local supply, VSS=local return,
    // A=input.  The characterized CDL additionally ties VNW to VDD and VPW
    // to VSS; the Verilog view exposes the corresponding logical power pins.
    (* keep = "true", dont_touch = "true" *)
    INV_X0P5M_A9TR40 u_rvt_inv_a (
        .Y   (rvt_mid),
        .VDD (vdd_a_i),
        .VSS (vss_a_i),
        .A   (a_i)
    );

    // A second inverter restores the logical polarity while adding the second
    // real RVT propagation arc specified by the measured two-inverter stage.
    (* keep = "true", dont_touch = "true" *)
    INV_X0P5M_A9TR40 u_rvt_inv_b (
        .Y   (y_o),
        .VDD (vdd_a_i),
        .VSS (vss_a_i),
        .A   (rvt_mid)
    );
endmodule

`default_nettype wire
