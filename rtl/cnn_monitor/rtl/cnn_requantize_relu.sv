`default_nettype none

// Combinational signed ties-to-even requantization followed by INT8 ReLU.
//
// The convolution accumulator is already proven to fit signed 20 bits.  An
// arithmetic right shift supplies the floor quotient for negative as well as
// positive values.  Reconstructing quotient*2^shift leaves a non-negative
// remainder, which makes the midpoint and odd-quotient tests identical to the
// accepted Python bit-true rule.
module cnn_requantize_relu (
    // Numeric input group.
    input  logic signed [19:0] accumulator, // Completed channel accumulator before scale alignment.
    input  logic        [4:0]  right_shift, // Per-channel non-negative power-of-two divisor.

    // Numeric output group.
    output logic        [7:0]  activation   // Saturated unsigned ReLU value in the signed-INT8 positive range.
);
    logic signed [20:0] floor_quotient;
    logic signed [20:0] reconstructed_value;
    logic        [20:0] nonnegative_remainder;
    logic        [20:0] half_denominator;
    logic               rounding_increment;
    logic signed [20:0] rounded_value;

    always_comb begin
        // Defaults cover the shift-zero path and ensure this arithmetic block
        // remains purely combinational for every control input value.
        floor_quotient       = {{1{accumulator[19]}}, accumulator};
        reconstructed_value = {{1{accumulator[19]}}, accumulator};
        nonnegative_remainder = 21'd0;
        half_denominator     = 21'd0;
        rounding_increment   = 1'b0;

        if (right_shift != 5'd0) begin
            floor_quotient = $signed({{1{accumulator[19]}}, accumulator})
                             >>> right_shift;
            reconstructed_value = floor_quotient <<< right_shift;
            nonnegative_remainder = $unsigned(
                $signed({{1{accumulator[19]}}, accumulator})
                - reconstructed_value);
            half_denominator = 21'd1 << (right_shift - 5'd1);
            rounding_increment =
                (nonnegative_remainder > half_denominator)
                || ((nonnegative_remainder == half_denominator)
                    && floor_quotient[0]);
        end

        rounded_value = floor_quotient
                        + $signed({20'd0, rounding_increment});
        // ReLU is not reported as overflow: negative values are expected
        // neural-network activity.  Only the positive signed-INT8 range is
        // retained, exactly matching task one's clamp-then-ReLU contract.
        if (rounded_value <= 21'sd0)
            activation = 8'd0;
        else if (rounded_value > 21'sd127)
            activation = 8'd127;
        else
            activation = rounded_value[7:0];
    end
endmodule

`default_nettype wire
