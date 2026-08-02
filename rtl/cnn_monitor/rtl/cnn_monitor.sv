`default_nettype none

// Top-level real-window L32 CNN monitor.
//
// This module contains no dummy-input source or scheduler.  Its only work is
// caused by an explicitly accepted snapshot request.  The acquisition buffer,
// convolution engine, and pooling/classifier engine have separate storage so
// legal sensor samples continue to transfer during the fixed compute schedule.
module cnn_monitor #(
    parameter integer MAC_LANES = 16 // Release configuration is 16; 4 and 8 are synthesis comparison points.
) (
    // Clock and reset group.
    input  logic               clk,                    // Synchronous sample and compute clock.
    input  logic               reset,                  // Active-high asynchronous reset.

    // Vernier sample-stream group.
    input  logic [5:0]         sensor_code,            // Unsigned sensor code, legal interval 0 through 32.
    input  logic               sample_valid,           // Requests transfer of sensor_code on this rising edge.
    output logic               sample_ready,           // Legal-code readiness; intentionally independent of busy.

    // Inference request/status group.
    input  logic               inference_request,      // Requests an atomic newest-L32 snapshot.
    output logic               inference_ready,        // Idle with at least one complete live window available.
    output logic               busy,                   // High from accepted request through the compute schedule.

    // Result payload group.
    output logic               result_valid,           // One-cycle result pulse at fixed release latency.
    output logic               safe_critical_decision, // Zero Safe, one Critical; an exact tie remains Safe.
    output logic signed [31:0] safe_logit,              // Safe INT32 logit at task-one scale 2^-26.
    output logic signed [31:0] critical_logit,          // Critical INT32 logit at task-one scale 2^-26.
    output logic signed [32:0] logit_difference,        // Critical minus Safe without signed-32 overflow.
    output logic [31:0]        result_endpoint_index,  // Newest sensor index used by this result.

    // Sticky error-status group.
    output logic               numeric_overflow,       // Any accumulator exceeds its accepted analytical bound.
    output logic               protocol_error          // Invalid sample or request made outside ready.
);
    logic snapshot_start;
    logic [31:0] snapshot_endpoint_index;
    logic [31:0] active_endpoint_index;
    logic [4:0] snapshot_base;
    logic [5:0] snapshot [0:31];
    logic [7:0] final_features [0:575];
    logic convolution_busy;
    logic convolution_done;
    logic convolution_overflow;
    logic postprocess_busy;
    logic postprocess_overflow;
    logic compute_reservation;

    // snapshot_start bridges request acceptance to convolution busy, while
    // convolution_done bridges convolution completion to postprocess busy.
    // Including both pulses prevents a one-cycle false-ready aperture between
    // independently registered engines and enforces the stated initiation interval.
    always_comb begin
        compute_reservation = snapshot_start || convolution_busy
                              || convolution_done || postprocess_busy;
        busy = compute_reservation;
        numeric_overflow = convolution_overflow || postprocess_overflow;
    end

    cnn_window_buffer window_buffer (
        .clk(clk),
        .reset(reset),
        .sensor_code(sensor_code),
        .sample_valid(sample_valid),
        .sample_ready(sample_ready),
        .inference_request(inference_request),
        .compute_busy(compute_reservation),
        .inference_ready(inference_ready),
        .snapshot_start(snapshot_start),
        .snapshot_endpoint_index(snapshot_endpoint_index),
        .snapshot_base(snapshot_base),
        .snapshot(snapshot),
        .protocol_error(protocol_error)
    );

    cnn_convolution_engine #(.MAC_LANES(MAC_LANES)) convolution_engine (
        .clk(clk),
        .reset(reset),
        .start(snapshot_start),
        .busy(convolution_busy),
        .done(convolution_done),
        .snapshot_base(snapshot_base),
        .snapshot(snapshot),
        .final_features(final_features),
        .numeric_overflow(convolution_overflow)
    );

    // Capture request metadata when the registered snapshot pulse is observed.
    // This endpoint remains stable while live acquisition advances independently.
    always_ff @(posedge clk or posedge reset) begin
        if (reset)
            active_endpoint_index <= 32'd0;
        else if (snapshot_start)
            active_endpoint_index <= snapshot_endpoint_index;
    end

    cnn_pool_classifier pool_classifier (
        .clk(clk),
        .reset(reset),
        .start(convolution_done),
        .busy(postprocess_busy),
        .result_valid(result_valid),
        .final_features(final_features),
        .endpoint_index(active_endpoint_index),
        .safe_critical_decision(safe_critical_decision),
        .safe_logit(safe_logit),
        .critical_logit(critical_logit),
        .logit_difference(logit_difference),
        .result_endpoint_index(result_endpoint_index),
        .numeric_overflow(postprocess_overflow)
    );
endmodule

`default_nettype wire
