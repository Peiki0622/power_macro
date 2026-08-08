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

    // Wide-range constants are frozen from the selected physical screen and
    // then checked again by the final 83-point real-DFF sweep.  Bit i maps to
    // companion stage i.  Eight selected LVT->RVT stages create the measured
    // voltage-sensitive D path; all other stages remain neutral RVT->RVT.
    // The early set {0,2,3,5} establishes the measured +1 response at 25 mV
    // and 50 mV droop.  The remaining set {28,29,30,31} lies after the
    // 0.70 V transition region, so stages 6..27 stay neutral and prevent the
    // former low-voltage three-code jumps.  This is a static elaboration-time
    // mask: it adds no stage, DFF, clock, control input, or runtime mux.
    localparam logic [31:0] WIDE_RANGE_ACTIVE_STAGE_MASK = 32'hf000_002d;
    localparam int WIDE_RANGE_ACTIVE_STAGE_COUNT = 8;
    localparam logic [2:0] WIDE_RANGE_DEFAULT_CAL_SEL = 3'd0;
    localparam logic [5:0] WIDE_RANGE_BASELINE_CODE = 6'd6;
    // HSPICE-qualified static launch topology: no companion-side balance
    // inputs, six CK/RVT-side BUF inputs.  These are cell counts, not delays.
    localparam int WIDE_RANGE_COMPANION_LAUNCH_LOAD_COUNT = 0;
    localparam int WIDE_RANGE_RVT_LAUNCH_LOAD_COUNT = 6;

    // Step 5 established that the raw DFF word is 1*0.  The frontend keeps
    // that physical direction and the decoder inverts it to the 0*1* contract.
    localparam logic THERMOMETER_INVERT = 1'b1;
endpackage

`default_nettype wire
