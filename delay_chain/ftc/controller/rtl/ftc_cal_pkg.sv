// FTC startup calibration controller constants.
//
// This package contains only compile-time constants.  It intentionally has
// no functions: the synthesis RTL uses explicit sequential logic so the
// physical thermometer rails remain registered and easy to audit.
`timescale 1ns/1ps
`default_nettype none

package ftc_cal_pkg;
    // Physical control-vector sizes frozen by the Phase 0 contract.
    parameter int MEDIUM_BITS = 16;
    parameter int FINE_BITS   = 10;

    // Binary debug/position widths.  These values are sufficient for the
    // legal inclusive ranges 0..16 and 0..10 respectively.
    parameter int MEDIUM_CODE_WIDTH = 5;
    parameter int FINE_CODE_WIDTH   = 4;

    // Active RF7 re-frequency contract: 400 MHz (2.5 ns) calibration clock.
    // These cycle positions were re-solved from physical event separations;
    // they are not scaled copies of the historical 1 GHz values.  The RF7
    // machine audit binds every constant below to the active JSON handoff.
    // Configuration updates remain under asserted reset and S_CLK low; the
    // new period satisfies their required physical settling in one full cycle.
    parameter int CONFIG_SETTLE_CYCLES = 1;
    parameter int PROBE_RESET_RELEASE_CYCLE = 0;
    parameter int PROBE_SCLK_RISE_CYCLE = 1;
    parameter int PROBE_Q_SAMPLE_1_CYCLE = 2;
    parameter int PROBE_Q_SAMPLE_2_CYCLE = 3;
    parameter int PROBE_RESET_ASSERT_CYCLE = 4;
    parameter int PROBE_SCLK_FALL_CYCLE = 5;
    parameter int PROBE_RECOVERY_DONE_CYCLE = 7;
    parameter int PROBE_SCLK_HIGH_CYCLES = 4;

    // Classifier values are encoded explicitly for stable interface tracing.
    parameter logic [1:0] Q_CLASS_STABLE_LOW  = 2'b00;
    parameter logic [1:0] Q_CLASS_STABLE_HIGH = 2'b01;
    parameter logic [1:0] Q_CLASS_AMBIGUOUS   = 2'b10;

    // =========================================================================
    // Operation Types (for operation sequencer)
    // =========================================================================
    typedef enum logic [1:0] {
        OP_CONFIG_UPDATE = 2'b00,  // Update M or F thermometer, wait settle
        OP_PROBE         = 2'b01,  // Execute sensor probe with Q sampling
        OP_IDLE          = 2'b10   // No operation
    } op_type_e;

    // =========================================================================
    // Q Sample Classification (enumerated version for FSM use)
    // =========================================================================
    typedef enum logic [1:0] {
        Q_STABLE_LOW  = 2'b00,  // Both samples are 0
        Q_STABLE_HIGH = 2'b01,  // Both samples are 1
        Q_AMBIGUOUS   = 2'b10,  // Samples differ
        Q_INVALID     = 2'b11   // Not yet sampled
    } q_class_e;

    // =========================================================================
    // Calibration Failure Reasons
    // =========================================================================
    typedef enum logic [3:0] {
        FAIL_NONE                     = 4'b0000,
        FAIL_COARSE_RANGE             = 4'b0001,
        FAIL_COARSE_BACKOFF_UNDERFLOW = 4'b0010,
        FAIL_FINE_RANGE               = 4'b0011,
        FAIL_GUARD_RANGE              = 4'b0100,
        FAIL_GUARD_NOT_LOW            = 4'b0101,
        FAIL_HOLD_NOT_LOW             = 4'b0110
    } fail_reason_e;

endpackage

`default_nettype wire
