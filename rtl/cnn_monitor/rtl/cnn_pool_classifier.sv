`default_nettype none

// Fixed 34-cycle multistat pooling followed by a fixed 58-cycle binary head.
//
// Pooling uses one initialization cycle, one cycle per L32 position, and one
// summary-finalization cycle.  The classifier then uses one bias cycle, 54
// product-issue cycles, one product-drain cycle, one logit-prepare cycle, and
// one result-commit cycle.  No state transition or loop bound depends on
// feature values, so decision content cannot change latency.
module cnn_pool_classifier (
    // Clock and transaction-control group.
    input  logic               clk,                   // Compute clock shared with the convolution engine.
    input  logic               reset,                 // Active-high asynchronous reset.
    input  logic               start,                 // One-cycle pulse after the final conv3 writeback.
    output logic               busy,                  // High during all pooling and classifier states.
    output logic               result_valid,          // One-cycle pulse when logits and metadata commit.

    // Conv3 tensor and request metadata group.
    input  logic [7:0]         final_features [0:575],// Flattened unsigned ReLU tensor [channel][position].
    input  logic [31:0]        endpoint_index,        // Sensor index captured with the immutable input window.

    // Classification result group.
    output logic               safe_critical_decision,// Zero is Safe; one is Critical; exact logit ties are Safe.
    output logic signed [31:0] safe_logit,             // Safe INT32 logit represented at the common 2^-26 scale.
    output logic signed [31:0] critical_logit,         // Critical INT32 logit represented at the common 2^-26 scale.
    output logic signed [32:0] logit_difference,       // Critical minus Safe in 33 bits to prevent subtraction wrap.
    output logic [31:0]        result_endpoint_index, // Endpoint belonging to the emitted logits.

    // Sticky numeric diagnostic group.
    output logic               numeric_overflow       // Analytical classifier-bound violation; reset clears it.
);
    localparam logic [2:0] STATE_IDLE             = 3'd0;
    localparam logic [2:0] STATE_POOL_SCAN        = 3'd1;
    localparam logic [2:0] STATE_POOL_FINALIZE    = 3'd2;
    localparam logic [2:0] STATE_CLASS_BIAS_INIT  = 3'd3;
    localparam logic [2:0] STATE_CLASS_MAC        = 3'd4;
    localparam logic [2:0] STATE_CLASS_DRAIN      = 3'd5;
    localparam logic [2:0] STATE_LOGIT_PREPARE    = 3'd6;
    localparam logic [2:0] STATE_CLASS_RESULT     = 3'd7;

    logic [2:0] state;
    logic [4:0] pool_position;
    logic [5:0] summary_index;
    logic [12:0] average_sum [0:17];
    logic [7:0] maximum_value [0:17];
    logic [7:0] endpoint_value [0:17];
    // One operand register per Conv3 channel models a synchronous feature-bank
    // read boundary.  STATE_IDLE/start prefetches position zero; each scan
    // cycle consumes the registered position and, except at position 31,
    // captures the following one.  This preserves the frozen 34-cycle pool
    // budget while removing a feature-array-read plus add/compare path.
    logic [7:0] pool_operand [0:17];
    logic [7:0] summary_features [0:53];
    logic signed [19:0] classifier_accumulator [0:1];

    // Classifier product pipeline group.  A non-negative 8-bit pooled feature
    // is explicitly extended to signed 9 bits before multiplication by one
    // signed 8-bit class weight.  The mathematical product range is
    // [-16256, 16129], so a signed 16-bit register is sufficient.  The shared
    // valid token prevents the bias cycle and fixed drain bubble from being
    // accumulated as real features.
    logic signed [15:0] classifier_product [0:1];
    logic               classifier_product_valid;

    // Classifier operand-prefetch group.  The 54-entry summary array and the
    // generated weight decoder are combinational structures, while an 18x8
    // signed multiply is already the dominant arithmetic operation in this
    // stage.  These small registers isolate both selection structures from the
    // multiplier input.  STATE_CLASS_BIAS_INIT preloads feature/weight zero;
    // every STATE_CLASS_MAC edge multiplies the registered pair and preloads
    // the following pair.  Thus all 54 products are still issued in exactly 54
    // MAC cycles and the existing single drain cycle remains unchanged.
    logic [7:0]         classifier_feature_operand;
    logic [15:0]        classifier_weight_operands;
    logic [5:0]         classifier_rom_index;

    logic [15:0] rom_class_weights;
    logic [39:0] rom_class_biases;
    logic [9:0] rom_class_left_shifts;
    logic [39:0] rom_class_bounds;
    logic signed [63:0] aligned_safe;
    logic signed [63:0] aligned_critical;
    logic signed [31:0] next_safe_logit;
    logic signed [31:0] next_critical_logit;
    // Prepared logits isolate variable left-shift/saturation from the public
    // result outputs.  Difference, decision, endpoint, and valid commit from
    // these registers together on the following edge.
    logic signed [31:0] prepared_safe_logit;
    logic signed [31:0] prepared_critical_logit;
    integer channel;

    cnn_classifier_parameter_rom classifier_rom (
        .summary_index(classifier_rom_index),
        .class_weights(rom_class_weights),
        .class_biases(rom_class_biases),
        .class_left_shifts(rom_class_left_shifts),
        .class_bounds(rom_class_bounds)
    );

    // During bias initialization, explicitly address entry zero for the first
    // prefetch.  During MAC cycle N, the registered operands belong to N and
    // the ROM/summary selectors point at N+1.  At N=53 no further operand is
    // required, so holding address 53 also avoids a needless out-of-range 54
    // decode.  This is address look-ahead only; summary_index remains the
    // architecturally visible issue counter used by the fixed controller.
    always_comb begin
        classifier_rom_index = summary_index;
        if (state == STATE_CLASS_BIAS_INIT)
            classifier_rom_index = 6'd0;
        else if ((state == STATE_CLASS_MAC) && (summary_index < 6'd53))
            classifier_rom_index = summary_index + 6'd1;
    end

    always_comb begin
        // Sign extension precedes the variable shift.  Without this explicit
        // 64-bit domain, SystemVerilog would evaluate a 20-bit left shift and
        // discard significant result bits before assignment.
        aligned_safe = $signed({{44{classifier_accumulator[0][19]}},
                                classifier_accumulator[0]})
                       <<< rom_class_left_shifts[4:0];
        aligned_critical = $signed({{44{classifier_accumulator[1][19]}},
                                    classifier_accumulator[1]})
                           <<< rom_class_left_shifts[9:5];

        if (aligned_safe > 64'sh000000007fffffff)
            next_safe_logit = 32'sh7fffffff;
        else if (aligned_safe < -64'sh0000000080000000)
            next_safe_logit = -32'sh80000000;
        else
            next_safe_logit = aligned_safe[31:0];

        if (aligned_critical > 64'sh000000007fffffff)
            next_critical_logit = 32'sh7fffffff;
        else if (aligned_critical < -64'sh0000000080000000)
            next_critical_logit = -32'sh80000000;
        else
            next_critical_logit = aligned_critical[31:0];
    end

    always_ff @(posedge clk or posedge reset) begin
        if (reset) begin
            state                    <= STATE_IDLE;
            pool_position            <= 5'd0;
            summary_index            <= 6'd0;
            busy                     <= 1'b0;
            result_valid             <= 1'b0;
            safe_critical_decision   <= 1'b0;
            safe_logit               <= 32'sd0;
            critical_logit           <= 32'sd0;
            logit_difference         <= 33'sd0;
            result_endpoint_index    <= 32'd0;
            numeric_overflow         <= 1'b0;
            classifier_accumulator[0] <= 20'sd0;
            classifier_accumulator[1] <= 20'sd0;
            classifier_product[0]     <= 16'sd0;
            classifier_product[1]     <= 16'sd0;
            classifier_product_valid  <= 1'b0;
            classifier_feature_operand <= 8'd0;
            classifier_weight_operands <= 16'd0;
            prepared_safe_logit       <= 32'sd0;
            prepared_critical_logit   <= 32'sd0;
            for (channel = 0; channel < 18; channel = channel + 1) begin
                average_sum[channel]   <= 13'd0;
                maximum_value[channel] <= 8'd0;
                endpoint_value[channel] <= 8'd0;
                pool_operand[channel]    <= 8'd0;
            end
            for (channel = 0; channel < 54; channel = channel + 1)
                summary_features[channel] <= 8'd0;
        end else begin
            result_valid <= 1'b0;
            case (state)
                STATE_IDLE: begin
                    if (start) begin
                        // This start edge is the scheduled pool-init cycle.
                        // ReLU outputs are non-negative, so zero initializes
                        // both sums and maximum trackers correctly.
                        busy          <= 1'b1;
                        pool_position <= 5'd0;
                        for (channel = 0; channel < 18;
                             channel = channel + 1) begin
                            average_sum[channel]    <= 13'd0;
                            maximum_value[channel]  <= 8'd0;
                            endpoint_value[channel] <= 8'd0;
                            // Position zero is prefetched during pool-init, so
                            // the first STATE_POOL_SCAN edge consumes valid
                            // registered data without an extra launch bubble.
                            pool_operand[channel] <= final_features[
                                {channel[4:0], 5'b00000}];
                        end
                        state <= STATE_POOL_SCAN;
                    end
                end

                STATE_POOL_SCAN: begin
                    // All 18 registered channel operands update in parallel
                    // for one time position.  Endpoint storage is gated solely
                    // by fixed position 31, never by data, and maximum sees
                    // exactly the same 32 operands as the average accumulator.
                    for (channel = 0; channel < 18;
                         channel = channel + 1) begin
                        average_sum[channel] <= average_sum[channel]
                            + pool_operand[channel];
                        if (pool_operand[channel] > maximum_value[channel])
                            maximum_value[channel] <= pool_operand[channel];
                        if (pool_position == 5'd31)
                            endpoint_value[channel] <= pool_operand[channel];
                        else
                            // The next address is generated only for positions
                            // 0..30, proving the flattened array index remains
                            // within channel*32 through channel*32+31.
                            pool_operand[channel] <= final_features[
                                {channel[4:0], 5'b00000}
                                + pool_position + 5'd1];
                    end
                    if (pool_position == 5'd31) begin
                        pool_position <= 5'd0;
                        state <= STATE_POOL_FINALIZE;
                    end else begin
                        pool_position <= pool_position + 5'd1;
                    end
                end

                STATE_POOL_FINALIZE: begin
                    // For non-negative sums, quotient=sum[12:5] and the low
                    // five bits are the remainder.  Increment above half, or
                    // exactly at half when the floor quotient is odd.  This is
                    // round-to-nearest, ties-to-even division by exactly 32.
                    for (channel = 0; channel < 18;
                         channel = channel + 1) begin
                        summary_features[channel] <= average_sum[channel][12:5]
                            + ((average_sum[channel][4:0] > 5'd16)
                               || ((average_sum[channel][4:0] == 5'd16)
                                   && average_sum[channel][5]));
                        summary_features[18 + channel] <= maximum_value[channel];
                        summary_features[36 + channel] <= endpoint_value[channel];
                    end
                    state <= STATE_CLASS_BIAS_INIT;
                end

                STATE_CLASS_BIAS_INIT: begin
                    // The summary written on the preceding edge is now stable.
                    // Two class accumulators load their own 20-bit bias in
                    // parallel; summary feature zero is addressed next.
                    classifier_accumulator[0] <= $signed(rom_class_biases[19:0]);
                    classifier_accumulator[1] <= $signed(rom_class_biases[39:20]);
                    classifier_product[0] <= 16'sd0;
                    classifier_product[1] <= 16'sd0;
                    classifier_product_valid <= 1'b0;
                    // The summary finalized one cycle earlier is stable here.
                    // classifier_rom_index is forced to zero in this state, so
                    // both operand registers are aligned to feature zero before
                    // the first MAC edge without adding a launch cycle.
                    classifier_feature_operand <= summary_features[0];
                    classifier_weight_operands <= rom_class_weights;
                    summary_index <= 6'd0;
                    state <= STATE_CLASS_MAC;
                end

                STATE_CLASS_MAC: begin
                    // Safe and Critical use separate multipliers but share one
                    // registered non-negative feature operand.  This edge
                    // captures products for summary_index and retires the
                    // preceding products.  In parallel, it prefetches the next
                    // feature and both next weights.  Nonblocking assignment
                    // semantics keep prefetch, multiply, and retire at three
                    // distinct ages without a data-dependent stall.
                    classifier_product[0] <=
                        $signed({1'b0, classifier_feature_operand})
                        * $signed(classifier_weight_operands[7:0]);
                    classifier_product[1] <=
                        $signed({1'b0, classifier_feature_operand})
                        * $signed(classifier_weight_operands[15:8]);
                    classifier_product_valid <= 1'b1;
                    if (classifier_product_valid) begin
                        classifier_accumulator[0]
                            <= classifier_accumulator[0]
                               + classifier_product[0];
                        classifier_accumulator[1]
                            <= classifier_accumulator[1]
                               + classifier_product[1];
                    end
                    if (summary_index == 6'd53) begin
                        summary_index <= 6'd0;
                        state <= STATE_CLASS_DRAIN;
                    end else begin
                        // classifier_rom_index points at summary_index+1 in
                        // this branch.  Both values are captured together so a
                        // weight can never become misaligned with its feature.
                        classifier_feature_operand
                            <= summary_features[classifier_rom_index];
                        classifier_weight_operands <= rom_class_weights;
                        summary_index <= summary_index + 6'd1;
                    end
                end

                STATE_CLASS_DRAIN: begin
                    // Retire the product issued for feature 53.  The following
                    // prepare state therefore observes both fully completed
                    // class accumulators.
                    if (classifier_product_valid) begin
                        classifier_accumulator[0]
                            <= classifier_accumulator[0]
                               + classifier_product[0];
                        classifier_accumulator[1]
                            <= classifier_accumulator[1]
                               + classifier_product[1];
                    end
                    classifier_product_valid <= 1'b0;
                    classifier_product[0] <= 16'sd0;
                    classifier_product[1] <= 16'sd0;
                    state <= STATE_LOGIT_PREPARE;
                end

                STATE_LOGIT_PREPARE: begin
                    // Bound checks and exact power-of-two alignment use the
                    // completed accumulators.  Their saturated INT32 results
                    // are registered so the public commit path contains only
                    // subtraction, comparison, and output registers.
                    // Task one's classifier bounds (270233 and 129383) are
                    // positive signed-20 values, so same-width signed compares
                    // avoid implicit extension ambiguity in synthesis tools.
                    if ((classifier_accumulator[0]
                         > $signed(rom_class_bounds[19:0]))
                        || (classifier_accumulator[0]
                            < -$signed(rom_class_bounds[19:0]))
                        || (classifier_accumulator[1]
                            > $signed(rom_class_bounds[39:20]))
                        || (classifier_accumulator[1]
                            < -$signed(rom_class_bounds[39:20])))
                        numeric_overflow <= 1'b1;
                    prepared_safe_logit <= next_safe_logit;
                    prepared_critical_logit <= next_critical_logit;
                    state <= STATE_CLASS_RESULT;
                end

                STATE_CLASS_RESULT: begin
                    // Both logits, their non-overflowing difference, strict
                    // greater-than decision (ties remain Safe), endpoint, and
                    // valid pulse commit atomically from prepared registers.
                    safe_logit <= prepared_safe_logit;
                    critical_logit <= prepared_critical_logit;
                    logit_difference <= $signed(
                        {prepared_critical_logit[31],
                         prepared_critical_logit})
                        - $signed({prepared_safe_logit[31],
                                   prepared_safe_logit});
                    safe_critical_decision <=
                        (prepared_critical_logit > prepared_safe_logit);
                    result_endpoint_index <= endpoint_index;
                    result_valid <= 1'b1;
                    busy <= 1'b0;
                    state <= STATE_IDLE;
                end

                default: begin
                    state <= STATE_IDLE;
                    busy  <= 1'b0;
                end
            endcase
        end
    end
endmodule

`default_nettype wire
