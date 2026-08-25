// ============================================================================
// B-FE2-L0 VCS behavior-model contract
//
// This simulation-only marker module documents the exact idealized domain
// crossing used by tb_bfe2_l0.  The executable per-tap equations live in the
// testbench procedural replay loop so all 30 scalar tap ports and their
// fixed-width probe columns remain explicit and auditable.  Keeping the model
// contract separate from the replay driver prevents this artifact from being
// mistaken for a synthesizable level shifter.
//
// Contract for every tap:
//   safe_d = PD_SAFE (0.95 V) when xor > 0.5*VDD_SENSE, otherwise 0 V;
//   q follows safe_d only while G > 0.5*PD_SAFE, then holds indefinitely.
// No hysteresis, delay, slew, X region, PVT, or noise is modeled.
// ============================================================================
`timescale 1ps/1ps

module bfe2_l0_behavior_model;
    // Marker instance: executable equations are intentionally in the replay
    // loop so all 30 modular tap ports remain visible and auditable there.
    localparam real L0_PD_SAFE_V = 0.95;
endmodule
