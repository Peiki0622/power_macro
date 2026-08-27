// B-FE5 ARCH0 fixed 30-bit safe-domain capture bank.
//
// The bank intentionally reuses the already reviewed ftc_capture_struct
// instead of duplicating its foundry-cell wrapper.  Each generated lane is
// therefore exactly: safe_d -> real LATQ -> real DFF -> q_ff.  The bank has no
// tap-count parameter, mask, repair path, or debug output beyond its internal
// q_ff vector, because ARCH0 freezes the physical width at thirty taps.
`timescale 1ns/1ps
`default_nettype none

module bfe_capture_bank (
    // Fixed 30-bit Level-0-restored data word.  Bit i is the data input of
    // the corresponding physical LATQ/DFF lane i.
    input  wire [29:0] safe_d_i,
    // One common active-high transparency gate shared by all thirty LATQs.
    input  wire        latch_gate_i,
    // One common positive-edge probe clock shared by all thirty DFFs.
    input  wire        clk_probe_i,
    // One common active-high asynchronous clear for all thirty DFFs.
    input  wire        reset_i,
    // Captured digital state consumed internally by the feature backend.
    // This is a module boundary for implementation, not a macro top-level
    // debug port; bfe_backend_top deliberately keeps it private.
    output wire [29:0] q_ff_o
);
    // The Liberty logical view proved in P0 has no power pins, so these local
    // supply nets are removed from the DC logical netlist.  They remain as
    // constant rails for the existing power-aware behavioral cell stubs used
    // by RTL simulation and do not become public backend ports.
    supply1 vdd_a;
    supply0 vss_a;

    genvar lane;
    generate
        for (lane = 0; lane < 30; lane = lane + 1) begin : g_capture_lane
            // Do not replace this instance with inferred storage: P0 and the
            // ARCH0 contract require the real LATQ followed by the real DFF.
            ftc_capture_struct u_capture (
                .d_i           (safe_d_i[lane]),
                .latch_gate_i  (latch_gate_i),
                .capture_clk_i (clk_probe_i),
                .reset_i       (reset_i),
                .q_o           (q_ff_o[lane]),
                .VDD_A         (vdd_a),
                .VSS_A         (vss_a)
            );
        end
    endgenerate
endmodule

`default_nettype wire
