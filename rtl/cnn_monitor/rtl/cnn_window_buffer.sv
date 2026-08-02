`default_nettype none

// Continuously acquires legal Vernier samples and atomically snapshots L32.
//
// Acquisition never stops for CNN computation.  The live circular buffer and
// the compute snapshot are physically separate register arrays, so samples
// accepted after a request cannot change that request's operands.  No request
// queue is hidden inside this module: a request outside inference_ready is
// rejected and reported through the sticky protocol flag.
module cnn_window_buffer (
    // Clock and reset group.
    input  logic        clk,                     // Shared synchronous sample/compute clock.
    input  logic        reset,                   // Active-high asynchronous reset.

    // Synchronous sensor stream group.
    input  logic [5:0]  sensor_code,             // Vernier code; only unsigned values 0 through 32 are legal.
    input  logic        sample_valid,            // Requests one sample transfer on this rising edge.
    output logic        sample_ready,            // High outside reset when sensor_code is legal.

    // Snapshot request group.
    input  logic        inference_request,       // Requests the newest complete L32 window.
    input  logic        compute_busy,            // Prevents overwriting the snapshot during inference.
    output logic        inference_ready,         // High only with 32 live samples and an idle compute engine.
    output logic        snapshot_start,          // One-cycle pulse that starts computation on the captured window.

    // Captured request metadata and data group.
    output logic [31:0] snapshot_endpoint_index, // Monotonic index of the logical endpoint, modulo 2^32.
    output logic [4:0]  snapshot_base,           // Physical slot containing logical oldest sample position zero.
    output logic [5:0]  snapshot [0:31],          // Immutable physical-slot copy of the accepted circular window.

    // Sticky integration diagnostic group.
    output logic        protocol_error           // Invalid code or rejected request; cleared only by reset.
);
    logic [5:0] circular_buffer [0:31];
    logic [4:0] write_pointer;
    logic [5:0] retained_sample_count;
    logic [31:0] next_sample_index;
    logic sample_accept;
    logic request_accept;
    // snapshot_capture_data is the physical-slot image committed on a request.
    // A simultaneous accepted sample replaces only its addressed physical slot;
    // no 32-way rotation is performed in this module.
    logic [5:0] snapshot_capture_data [0:31];
    integer capture_index;
    integer snapshot_index;

    always_comb begin
        // A malformed code is backpressured and also reported if sample_valid
        // is asserted.  Busy is deliberately absent from this expression.
        sample_ready = (!reset) && (sensor_code <= 6'd32);
        sample_accept = sample_valid && sample_ready;
        inference_ready = (!reset) && (!compute_busy)
                          && (retained_sample_count == 6'd32);
        request_accept = inference_request && inference_ready;

        // Default to a direct bit-for-bit physical copy.  The single dynamic
        // override implements write-through for an accepted sample on the same
        // edge as a request, so the new value becomes the logical endpoint even
        // though the circular-buffer nonblocking write commits on that edge.
        for (capture_index = 0; capture_index < 32;
             capture_index = capture_index + 1)
            snapshot_capture_data[capture_index]
                = circular_buffer[capture_index];
        if (sample_accept)
            snapshot_capture_data[write_pointer] = sensor_code;
    end

    always_ff @(posedge clk or posedge reset) begin
        if (reset) begin
            write_pointer           <= 5'd0;
            retained_sample_count   <= 6'd0;
            next_sample_index       <= 32'd0;
            snapshot_endpoint_index <= 32'd0;
            snapshot_base           <= 5'd0;
            snapshot_start          <= 1'b0;
            protocol_error          <= 1'b0;
            // The two data arrays deliberately have no reset assignment.  A
            // request remains blocked until retained_sample_count reaches 32,
            // which proves all circular slots have been overwritten after the
            // most recent reset.  A request edge then overwrites every snapshot
            // slot before snapshot_start permits the compute engine to read it.
            // Only the occupancy, pointer, metadata, pulse, and error controls
            // require architectural reset values.
        end else begin
            snapshot_start <= 1'b0;

            // Valid acquisition advances a power-of-two circular pointer and
            // saturates the retained-count at one complete L32 window.
            if (sample_accept) begin
                circular_buffer[write_pointer] <= sensor_code;
                write_pointer <= write_pointer + 5'd1;
                next_sample_index <= next_sample_index + 32'd1;
                if (retained_sample_count < 6'd32)
                    retained_sample_count <= retained_sample_count + 6'd1;
            end

            if (sample_valid && !sample_ready)
                protocol_error <= 1'b1;
            if (inference_request && !inference_ready)
                protocol_error <= 1'b1;

            if (request_accept) begin
                snapshot_start <= 1'b1;
                // Copy matching physical slots.  Logical chronology is encoded
                // by snapshot_base and restored by the convolution engine with
                // one shared 5-bit wrapping address, replacing 32 independently
                // rotated 32:1 muxes in the previous implementation.
                for (snapshot_index = 0; snapshot_index < 32;
                     snapshot_index = snapshot_index + 1)
                    snapshot[snapshot_index]
                        <= snapshot_capture_data[snapshot_index];
                if (sample_accept) begin
                    // When a legal sample and request share an edge, the live
                    // buffer was already full by contract.  The just-accepted
                    // value replaces the oldest physical slot and is the new
                    // logical endpoint.  The following slot becomes oldest.
                    snapshot_base <= write_pointer + 5'd1;
                    snapshot_endpoint_index <= next_sample_index;
                end else begin
                    // write_pointer names the oldest entry of a full circular
                    // buffer and therefore directly becomes the snapshot base.
                    snapshot_base <= write_pointer;
                    snapshot_endpoint_index <= next_sample_index - 32'd1;
                end
            end
        end
    end
endmodule

`default_nettype wire
