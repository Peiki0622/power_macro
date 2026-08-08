// Phase-3 constants frozen from the physical HSPICE selection.
//
// The package contains only static elaboration-time values.  In particular, it
// does not describe a delay in time units: the calibrated delay is implemented
// structurally by the BUF/MXT2 cells in phase3_launch_cal_struct.sv.
`default_nettype none

package phase3_calibration_pkg;
    // Number of physical non-inverting stages and real comparator DFFs.
    localparam int PHASE3_STAGES = 32;

    // Physical 8-tap launch setting selected at 1.100 V by the real DFF bank.
    localparam logic [2:0] DEFAULT_CAL_SEL = 3'd1;

    // Observed real-DFF nominal code for DEFAULT_CAL_SEL at 1.100 V.
    localparam logic [5:0] DEFAULT_BASELINE_CODE = 6'd18;

    // Wide-range constants are frozen only after the 83-point real-DFF sweep.
    // Bit i maps to companion stage i; the alternating mask has 16 active
    // LVT->RVT stages and 16 neutral RVT->RVT stages.
    localparam logic [31:0] WIDE_RANGE_ACTIVE_STAGE_MASK = 32'h5555_5555;
    localparam int WIDE_RANGE_ACTIVE_STAGE_COUNT = 16;
    localparam logic [2:0] WIDE_RANGE_DEFAULT_CAL_SEL = 3'd0;
    localparam logic [5:0] WIDE_RANGE_BASELINE_CODE = 6'd0;

    // Step 5 established that the raw DFF word is 1*0.  The frontend keeps
    // that physical direction and the decoder inverts it to the 0*1* contract.
    localparam logic THERMOMETER_INVERT = 1'b1;
endpackage

`default_nettype wire
