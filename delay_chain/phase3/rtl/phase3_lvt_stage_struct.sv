// One selected LVT non-inverting Vernier stage with the measured dummy load.
//
// The selected Phase-3 companion is INV_X0P5M_A9TL40 with exactly one private
// LVT inverter input load on each stage output.  The dummy output is not part
// of the signal path; it retains the capacitive loading used in HSPICE.
`default_nettype none

(* keep_hierarchy = "yes" *)
module phase3_lvt_stage_struct (
    // Same-rail power interface:
    // vdd_a_i and vss_a_i connect to both functional LVT inverters and the
    // private dummy-load inverter, matching the same rail pair used by RVT.
    inout  wire  vdd_a_i,
    inout  wire  vss_a_i,

    // LVT timing-path interface:
    // a_i is the arrival from the preceding LVT stage or calibrated launch;
    // y_o is the same-polarity arrival after two functional LVT inverters.
    input  logic a_i,
    output logic y_o
);
    // Internal series node between the two functional LVT inverters.
    (* keep = "true", dont_touch = "true" *) logic lvt_mid;

    // Private dummy output.  It has no fanout outside this wrapper, ensuring
    // the third inverter loads y_o only through its real input capacitance.
    (* keep = "true", dont_touch = "true" *) logic lvt_dummy_sink;

    // Functional inverter one.  Port names match the installed LVT Verilog
    // view; its CDL well pins are tied to the same VDD_A/VSS_A rails.
    (* keep = "true", dont_touch = "true" *)
    INV_X0P5M_A9TL40 u_lvt_inv_a (
        .Y   (lvt_mid),
        .VDD (vdd_a_i),
        .VSS (vss_a_i),
        .A   (a_i)
    );

    // Functional inverter two restores polarity and creates the stage tap.
    (* keep = "true", dont_touch = "true" *)
    INV_X0P5M_A9TL40 u_lvt_inv_b (
        .Y   (y_o),
        .VDD (vdd_a_i),
        .VSS (vss_a_i),
        .A   (lvt_mid)
    );

    // The selected D1 loading: one real LVT input driven by the output tap.
    // Its private Y connection must remain present so synthesis preserves the
    // input capacitance without creating a logic path to a later stage.
    (* keep = "true", dont_touch = "true" *)
    INV_X0P5M_A9TL40 u_lvt_dummy_load (
        .Y   (lvt_dummy_sink),
        .VDD (vdd_a_i),
        .VSS (vss_a_i),
        .A   (y_o)
    );
endmodule

`default_nettype wire
