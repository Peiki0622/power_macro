// Full-width replay bench for retained HSPICE comparator-bank captures.
//
// The Python test writes one 32-bit raw-Q vector per line into raw_q.mem and
// invokes this bench once.  The vector order is physical-stage order at the
// Python boundary (stage 0 is the leftmost character), while readmemb fills a
// packed SystemVerilog vector from bit 31 toward bit 0; the Python harness
// therefore reverses each line before writing it.  This bench intentionally
// contains no synthesizable design logic: it is only the execution harness
// that drives the already-synthesizable vernier_sensor_digital_backend.
`timescale 1ns/1ps
`default_nettype none

module vernier_sensor_spice_raw_q_replay_tb;
    localparam int M_STAGES = 32;
    localparam int CODE_WIDTH = 6;
    localparam int SAMPLE_COUNT = 500;

    // Controller clock for the backend capture register.  The physical
    // frontend is bypassed because every input vector is a retained HSPICE
    // raw comparator word, not a newly generated delay-chain waveform.
    logic clk;

    // One-cycle request and active-high asynchronous reset, matching the
    // public backend contract and the selected comparator reset polarity.
    logic capture_enable;
    logic sensor_reset;

    // Calibration metadata is carried through the interface for completeness;
    // decoding is intentionally independent of the selected tap value.
    logic [2:0] cal_sel;

    // Raw vector memory loaded from the temporary HSPICE replay file and the
    // complete observed backend result for the current capture.
    logic [M_STAGES-1:0] raw_vectors [0:SAMPLE_COUNT-1];
    logic [M_STAGES-1:0] raw_code_i;
    logic [M_STAGES-1:0] raw_code;
    logic [M_STAGES-1:0] corrected_code;
    logic [CODE_WIDTH-1:0] sensor_code;
    logic [CODE_WIDTH-1:0] bubble_count;
    logic code_valid;
    logic sample_valid;

    vernier_sensor_digital_backend #(
        .M_STAGES  (M_STAGES),
        .CODE_WIDTH(CODE_WIDTH)
    ) dut (
        .clk            (clk),
        .capture_enable (capture_enable),
        .sensor_reset   (sensor_reset),
        .cal_sel        (cal_sel),
        .raw_code_i     (raw_code_i),
        .raw_code       (raw_code),
        .corrected_code (corrected_code),
        .sensor_code    (sensor_code),
        .bubble_count   (bubble_count),
        .code_valid     (code_valid),
        .sample_valid   (sample_valid)
    );

    // A fixed simulation clock avoids any dependence on physical delay values;
    // only the synchronous backend transaction is being replayed.
    initial begin
        clk = 1'b0;
        forever #5 clk = ~clk;
    end

    integer sample_index;
    initial begin
        $readmemb("raw_q.mem", raw_vectors);
        raw_code_i     = '0;
        capture_enable = 1'b0;
        sensor_reset   = 1'b1;
        cal_sel        = 3'd2;

        // Keep reset asserted for two complete cycles before replaying data.
        repeat (2) @(posedge clk);
        sensor_reset = 1'b0;
        @(posedge clk);

        for (sample_index = 0; sample_index < SAMPLE_COUNT; sample_index = sample_index + 1) begin
            raw_code_i     = raw_vectors[sample_index];
            capture_enable = 1'b1;
            @(posedge clk);
            #1;
            $display(
                "CASE %0d raw=%032b corrected=%032b code=%0d bubbles=%0d valid=%0b sample_valid=%0b",
                sample_index, raw_code, corrected_code, sensor_code, bubble_count, code_valid, sample_valid
            );
            capture_enable = 1'b0;
            @(posedge clk);
            #1;
        end

        $display("SPICE_RAW_Q_REPLAY_PASS");
        $finish;
    end
endmodule

`default_nettype wire
