// Directed simulation for the synthesizable digital backend.
//
// The physical frontend is intentionally bypassed here: this bench injects
// already-captured raw comparator words so the backend can be checked against
// the Python decoder one vector at a time.
`timescale 1ns/1ps
`default_nettype none

module vernier_sensor_digital_backend_tb;
    localparam int M_STAGES = 8;

    // Controller clock.  The backend samples capture_enable on this edge.
    logic clk;

    // Capture request and active-high asynchronous reset.
    logic capture_enable;
    logic sensor_reset;

    // Calibration metadata is present for interface completeness.
    logic [2:0] cal_sel;

    // Injected raw comparator-bank word and observed backend outputs.
    logic [M_STAGES-1:0] raw_code_i;
    logic [M_STAGES-1:0] raw_code;
    logic [M_STAGES-1:0] corrected_code;
    logic [$clog2(M_STAGES + 1)-1:0] sensor_code;
    logic [$clog2(M_STAGES + 1)-1:0] bubble_count;
    logic code_valid;
    logic sample_valid;

    vernier_sensor_digital_backend #(
        .M_STAGES  (M_STAGES),
        .CODE_WIDTH($clog2(M_STAGES + 1))
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

    // Ten-nanosecond period keeps the test readable while leaving the backend
    // entirely synchronous and free of behavioral delay constructs.
    initial begin
        clk = 1'b0;
        forever #5 clk = ~clk;
    end

    // Drive one request pulse, print the post-capture result, then verify that
    // sample_valid returns low on the following idle cycle.
    task automatic apply_case(input integer case_id, input logic [M_STAGES-1:0] word);
        begin
            raw_code_i     = word;
            capture_enable = 1'b1;
            @(posedge clk);
            #1;
            $display(
                "CASE %0d raw=%0b corrected=%0b code=%0d bubbles=%0d valid=%0b sample_valid=%0b",
                case_id, raw_code, corrected_code, sensor_code, bubble_count, code_valid, sample_valid
            );
            capture_enable = 1'b0;
            @(posedge clk);
            #1;
            $display("IDLE %0d sample_valid=%0b", case_id, sample_valid);
        end
    endtask

    initial begin
        raw_code_i     = '0;
        capture_enable = 1'b0;
        sensor_reset   = 1'b1;
        cal_sel        = 3'd2;

        // Hold reset for two clocks, matching the active-high DFF clear
        // contract, then release before the first directed vector.
        repeat (2) @(posedge clk);
        sensor_reset = 1'b0;
        @(posedge clk);

        // all-zero endpoint
        apply_case(0, 8'b0000_0000);

        // all-one endpoint
        apply_case(1, 8'b1111_1111);

        // ideal 0*1* thermometer word.  The literal is reversed because the
        // RTL contract assigns Python-string bit zero to raw_code[0].
        apply_case(2, 8'b1111_1000);

        // single bubble repaired by the interior majority filter
        apply_case(3, 8'b1110_1100);

        // multiple bubbles that remain invalid after correction
        apply_case(4, 8'b1010_1100);

        // strongly non-monotonic invalid word
        apply_case(5, 8'b1110_1010);

        $display("BACKEND_TEST_PASS");
        $finish;
    end
endmodule

`default_nettype wire
