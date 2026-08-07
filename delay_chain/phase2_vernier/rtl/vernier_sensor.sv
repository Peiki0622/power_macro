// Final macro wrapper for the Stage 2A Vernier sensor.
//
// This module exposes the compact functional interface expected by the future
// detector while keeping the physical frontend, the calibrated launch path, and
// the digital decoder separate enough to verify and synthesize cleanly.
`default_nettype none

module vernier_sensor (
    // Functional clocking and control inputs.
    input  logic clk_i,
    input  logic rst_i,
    input  logic sample_req_i,

    // Explicit physical power pins for the wrapped delay/comparator region.
    inout  wire  vdd_a_i,
    inout  wire  vss_a_i,
    inout  wire  vdd_ref_i,
    inout  wire  vss_ref_i,

    // Stable decoded sensor output and response flags.
    output logic [5:0] sensor_code_o,
    output logic       code_valid_o,
    output logic       sample_valid_o,
    output logic       sensor_fault_o
);
    import vernier_sensor_calibration_pkg::*;

    // The validated calibration point is fixed for Stage 2A.  Keeping this
    // value local avoids exposing an uncalibrated tap control to CUSUM.
    localparam logic [2:0] CAL_SEL_FIXED = DEFAULT_CAL_SEL;

    // The request launches the physical frontend immediately.  The small
    // adapter delays only the digital capture enable by one clk cycle, giving
    // the physical comparator bank time to settle before latching raw_code.
    logic                capture_enable;
    logic [31:0]         raw_code;
    logic [31:0]         corrected_code_unused;
    logic [5:0]          bubble_count_unused;

    vernier_sample_adapter u_sample_adapter (
        .clk_i            (clk_i),
        .rst_i            (rst_i),
        .sample_req_i     (sample_req_i),
        .capture_enable_o (capture_enable)
    );

    vernier_frontend_struct #(
        .M_STAGES         (32),
        .DUMMY_LOAD_COUNT (1)
    ) u_frontend (
        .vdd_a_i       (vdd_a_i),
        .vss_a_i       (vss_a_i),
        .vdd_ref_i     (vdd_ref_i),
        .vss_ref_i     (vss_ref_i),
        .launch_req_i  (sample_req_i),
        .cal_sel_i     (CAL_SEL_FIXED),
        .sensor_reset_i(rst_i),
        .raw_code_o    (raw_code)
    );

    vernier_sensor_digital_backend #(
        .M_STAGES  (32),
        .CODE_WIDTH(6)
    ) u_backend (
        .clk           (clk_i),
        .capture_enable (capture_enable),
        .sensor_reset   (rst_i),
        .cal_sel        (CAL_SEL_FIXED),
        .raw_code_i     (raw_code),
        .raw_code       (),
        .corrected_code (corrected_code_unused),
        .sensor_code    (sensor_code_o),
        .bubble_count   (bubble_count_unused),
        .code_valid     (code_valid_o),
        .sample_valid   (sample_valid_o)
    );

    // A fault is meaningful only with a returned sample.  Invalid thermometer
    // structure is therefore surfaced as a single-cycle fault pulse.
    assign sensor_fault_o = sample_valid_o && !code_valid_o;

endmodule

`default_nettype wire
