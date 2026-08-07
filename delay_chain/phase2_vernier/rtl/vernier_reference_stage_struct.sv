// Structural wrapper for one SMIC40LL reference stage.
//
// The reference chain mirrors the SPICE topology and keeps the selected dummy
// inverter loads visible so synthesis cannot collapse the measured electrical
// loading.  The dummy load count is parameterized only to match the already
// validated Phase 2 collateral; the default remains the chosen D1 point.
`default_nettype none

(* keep_hierarchy = "yes" *)
module vernier_reference_stage_struct #(
    parameter int DUMMY_LOAD_COUNT = 1
) (
    // Local reference-island positive rail.
    inout  wire  vdd_ref_i,

    // Local reference-island return rail.
    inout  wire  vss_ref_i,

    // Non-inverting reference-stage input.
    input  logic a_i,

    // Non-inverting reference-stage output.
    output logic y_o
);
    // The internal midpoint is kept as a named physical node so the wrapper
    // still reflects the two-inverter structure from the SPICE include.
    (* keep = "true", dont_touch = "true" *)
    logic reference_mid;

    // Main reference chain: two inverters with the local reference-domain
    // VDD/VSS pins.  The characterized CDL ties the corresponding well pins to
    // the same local rails.
    (* keep = "true", dont_touch = "true" *)
    INV_X0P5M_A9TR40 u_inv_ref_a (
        .Y   (reference_mid),
        .VDD (vdd_ref_i),
        .VSS (vss_ref_i),
        .A   (a_i)
    );

    (* keep = "true", dont_touch = "true" *)
    INV_X0P5M_A9TR40 u_inv_ref_b (
        .Y   (y_o),
        .VDD (vdd_ref_i),
        .VSS (vss_ref_i),
        .A   (reference_mid)
    );

    // Dummy loads are kept as real inverter instances tied to the stage output.
    // The outputs go to private nodes so the synthesized structure still sees
    // the measured extra input loading without exposing the nodes upward.
    generate
        if (DUMMY_LOAD_COUNT > 0) begin : g_dummy_loads
            (* keep = "true", dont_touch = "true" *)
            logic [DUMMY_LOAD_COUNT-1:0] dummy_sink;

            for (genvar dummy_index = 0; dummy_index < DUMMY_LOAD_COUNT; dummy_index++) begin : g_dummy
                (* keep = "true", dont_touch = "true" *)
                INV_X0P5M_A9TR40 u_dummy (
                    .Y   (dummy_sink[dummy_index]),
                    .VDD (vdd_ref_i),
                    .VSS (vss_ref_i),
                    .A   (y_o)
                );
            end
        end
    endgenerate

endmodule

`default_nettype wire
