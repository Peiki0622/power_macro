// ============================================================================
// Corrected Phase 9 VCS-XA sensor boundary stub
//
// The Verilog view exposes only controller-owned control crossings and the
// analog Q result.  VDD and VSS are intentionally absent from this digital
// port list: the corrected SPICE wrapper creates the sensor supply internally,
// so the physical rails cannot be accidentally routed through a generic D2A
// element or inherit a hard-coded digital logic-high voltage.
//
// This module is non-synthesizable mixed-signal glue.  The `use_spice -cell`
// directive in the corrected vcsAD.init replaces this empty view with the
// transistor-level `ftc_sensor_ams` subcircuit during XA elaboration.
// ============================================================================
module ftc_sensor_ams (
    // Sensor DFF result returned from the analog domain through the normalized
    // A2D contract.  The synthesized controller is the sole digital consumer.
    output wire q_final,

    // Controller-owned active-high sensor sampling clock crossing.  The XA
    // bridge must preserve its 1 ns-cycle edge timing and configured slew.
    input wire sense_s_clk,

    // Controller-owned active-high sensor DFF reset crossing.  It is released
    // for the local probe window and reasserted at the frozen cycle six.
    input wire sense_dff_reset,

    // Medium path-selection thermometer rails.  Each bit is a separate D2A
    // control crossing; bit zero is the first physical medium stage.
    input wire [15:0] medium_therm,

    // Fine load-selection thermometer rails.  These rails are active-low in
    // the frozen sensor and each bit remains an individually audited crossing.
    input wire [9:0] fine_therm
);
    // No behavioral driver is allowed here.  XA supplies the analog cell and
    // Q conversion; an RTL assignment would create a competing Q source.
endmodule
