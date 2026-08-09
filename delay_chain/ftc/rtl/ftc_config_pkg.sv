// Selected, physically characterized constants for the standalone FTC macro.
`timescale 1ns/1ps
`default_nettype none

package ftc_config_pkg;
    // The paper's baseline observable depth, retained exactly in this reproduction.
    parameter integer OBSERVABLE_STAGES = 30;
    // The final RVT/LVT initial buffer counts selected from real-cell evidence.
    parameter integer RVT_INITIAL_STAGES = 4;
    parameter integer LVT_INITIAL_STAGES = 0;
    // Five bits represent the inclusive 0..29 physical tap index and length 0..30.
    parameter integer INDEX_WIDTH = 5;
endpackage

`default_nettype wire
