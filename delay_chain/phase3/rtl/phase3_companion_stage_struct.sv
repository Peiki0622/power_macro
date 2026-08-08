// Static wide-range companion stage for the Phase-3 Vernier frontend.
//
// ACTIVE_DIFFERENTIAL is an elaboration-time parameter selected from the
// frozen package mask.  It is not a signal and therefore cannot infer a
// runtime mux or alter the characterized topology after synthesis.
`default_nettype none

(* keep_hierarchy = "yes" *)
module phase3_companion_stage_struct #(
    parameter bit ACTIVE_DIFFERENTIAL = 1'b0
) (
    // The only power pins.  Both inverters use the same VDD_A/VSS_A domain.
    inout wire vdd_a_i,
    inout wire vss_a_i,
    // Non-inverting delay-stage data interface.
    input logic a_i,
    output logic y_o
);
    (* keep = "true", dont_touch = "true" *) logic companion_mid;

    generate
        if (ACTIVE_DIFFERENTIAL) begin : g_active_lvt_rvt
            // Active stage: LVT first increases the differential delay gain;
            // RVT second restores polarity and gives the DFF an RVT driver.
            INV_X0P5M_A9TL40 u_first_lvt (.Y(companion_mid), .VDD(vdd_a_i), .VSS(vss_a_i), .A(a_i));
            INV_X0P5M_A9TR40 u_second_rvt (.Y(y_o), .VDD(vdd_a_i), .VSS(vss_a_i), .A(companion_mid));
        end else begin : g_neutral_rvt_rvt
            // Neutral stage: two RVT cells preserve the 32-tap observation
            // structure without adding an LVT/RVT differential contribution.
            INV_X0P5M_A9TR40 u_first_rvt (.Y(companion_mid), .VDD(vdd_a_i), .VSS(vss_a_i), .A(a_i));
            INV_X0P5M_A9TR40 u_second_rvt (.Y(y_o), .VDD(vdd_a_i), .VSS(vss_a_i), .A(companion_mid));
        end
    endgenerate
endmodule

`default_nettype wire
