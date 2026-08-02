`default_nettype none

// Fixed-schedule shared-MAC implementation of the three k=5 CNN layers.
//
// The controller order is output position, output-channel group, input
// channel, then kernel tap.  Every issued operand crosses an explicit
// synchronous-ROM/activation/product pipeline before it reaches an
// accumulator.  Two fixed drain states retire the final products without any
// data-dependent control.  Exactly two 576-byte feature banks alternate
// ownership: final_features is the physical A bank used by both conv1 and
// conv3, while feature_bank_b is the physical B bank used by conv2.  Conv2 does
// not start until conv1 has completely filled A, and pooling does not start
// until conv3 has completely overwritten A, so this lifetime reuse removes an
// otherwise duplicate 576-byte register array without creating a read/write
// collision or changing a controller cycle.
module cnn_convolution_engine #(
    parameter integer MAC_LANES = 16 // Supported synthesis design points are exactly 4, 8, and 16 lanes.
) (
    // Clock and transaction-control group.
    input  logic        clk,                     // Compute clock for all controller and datapath registers.
    input  logic        reset,                   // Active-high asynchronous reset.
    input  logic        start,                   // One-cycle pulse; accepted only while busy is low.
    output logic        busy,                    // High throughout all three convolution layers.
    output logic        done,                    // One-cycle pulse after the final conv3 writeback.

    // Immutable L32 snapshot input group.
    input  logic [4:0]  snapshot_base,            // Physical slot of logical position zero in snapshot.
    input  logic [5:0]  snapshot [0:31],          // Raw sensor codes retained in circular physical-slot order.

    // Final feature tensor and numeric diagnostic group.
    output logic [7:0]  final_features [0:575],  // Physical bank A; holds conv1 during conv2, then final conv3 tensor.
    output logic        numeric_overflow         // Sticky analytical-bound violation; reset clears it.
);
    localparam logic [2:0] STATE_IDLE       = 3'd0;
    localparam logic [2:0] STATE_BIAS_INIT  = 3'd1;
    localparam logic [2:0] STATE_MAC_ISSUE  = 3'd2;
    localparam logic [2:0] STATE_DRAIN_1    = 3'd3;
    localparam logic [2:0] STATE_DRAIN_2    = 3'd4;
    localparam logic [2:0] STATE_REQUANT_PREPARE = 3'd5;
    localparam logic [2:0] STATE_REQUANT_WRITE   = 3'd6;
    localparam logic [4:0] MAC_LANES_VALUE = MAC_LANES;

    // Selecting an unsupported lane count deliberately instantiates an
    // unresolved cell at elaboration.  Legal constant parameters prune this
    // branch completely, providing a synthesis-time parameter assertion.
    generate
        if ((MAC_LANES != 4) && (MAC_LANES != 8) && (MAC_LANES != 16)) begin : g_illegal_lane_count
            CNN_MONITOR_ILLEGAL_MAC_LANE_CONFIGURATION illegal_parameter();
        end
    endgenerate

    logic [2:0] state;
    logic [1:0] layer_id;
    logic [4:0] output_position;
    logic [4:0] output_base;
    logic [4:0] input_channel;
    logic [2:0] kernel_tap;
    // Physical bank B holds only conv2 output.  Physical bank A is the public
    // final_features array so the design contains the two banks declared by
    // the architecture contract rather than a third mirrored final array.
    logic [7:0] feature_bank_b [0:575];
    logic signed [19:0] accumulators [0:MAC_LANES-1];

    // Compiled-ROM request/response group.  The physical ROM stores one
    // 16-channel output word per fan-in operand.  Smaller legal MAC arrays
    // select a contiguous byte slice from that word, preserving the same
    // physical address map without creating another weight store.
    logic         rom_read_enable;
    logic [8:0]   rom_read_address;
    logic         rom_q_valid;
    logic [127:0] rom_weight_word;

    // Activation/product pipeline group.  source_activation is the operand
    // addressed by the current controller fields.  activation_pipe holds the
    // signed 8-bit operand aligned with the following ROM response.  Each
    // product_pipe element is a full signed 8x8=16-bit product; product_valid
    // is the sole accumulator write enable and therefore prevents reset or
    // drain bubbles from altering numeric state.
    logic signed [7:0]  activation_pipe;
    logic               activation_valid;
    logic signed [15:0] product_pipe [0:MAC_LANES-1];
    logic               product_valid;

    // Packed parameter-ROM response group.  Each decoder returns one physical
    // 16-channel word.  output_base[4] selects channels 0..15 or 16..31;
    // output_base[3:0] selects a contiguous 4/8-lane comparison slice within
    // that word.  The 16-lane release build therefore consumes each word from
    // lane zero and does not replicate a decoder per arithmetic lane.
    logic [319:0] rom_lane_biases;
    logic [79:0]  rom_lane_right_shifts;
    logic [319:0] rom_lane_magnitude_bounds;
    logic [79:0]  registered_lane_right_shifts;
    logic [2:0] bias_position_class;
    logic signed [6:0] source_position;
    logic [4:0] snapshot_physical_position;
    logic signed [7:0] source_activation;
    logic signed [19:0] lane_bias [0:MAC_LANES-1];
    logic [4:0] lane_right_shift [0:MAC_LANES-1];
    logic [19:0] lane_magnitude_bound [0:MAC_LANES-1];
    logic [7:0] lane_weight [0:MAC_LANES-1];
    logic [7:0] lane_requantized [0:MAC_LANES-1];

    // Requantization commit pipeline group.  The prepare state captures the
    // combinational rounding/saturation result and all destination metadata.
    // The write state uses only these registers, which removes rounding and
    // analytical-bound comparison from the feature-bank write path.  One
    // valid bit per lane proves that channels 18..31 in the final physical ROM
    // word can never write an out-of-range feature address.
    logic [7:0] prepared_activation [0:MAC_LANES-1];
    logic       prepared_lane_valid [0:MAC_LANES-1];
    logic [1:0] prepared_layer_id;
    logic [4:0] prepared_output_position;
    logic [4:0] prepared_output_base;
    integer lane;
    integer write_channel;
    integer write_position;

    // Conv1 bias has five padding classes.  Interior positions 2 through 29
    // share one authenticated value; the generator rejects the package if that
    // equality ever stops holding.  Later layers are position independent and
    // use class zero.  An explicit case keeps this mapping fully synthesizable
    // without a procedural helper or division/modulo arithmetic.
    always_comb begin
        bias_position_class = 3'd0;
        if (layer_id == 2'd1) begin
            case (output_position)
                5'd0:    bias_position_class = 3'd0;
                5'd1:    bias_position_class = 3'd1;
                5'd30:   bias_position_class = 3'd3;
                5'd31:   bias_position_class = 3'd4;
                default: bias_position_class = 3'd2;
            endcase
        end

        source_position = $signed({2'b00, output_position})
                          + $signed({4'b0000, kernel_tap}) - 7'sd2;
        // Five-bit arithmetic intentionally wraps modulo 32.  This address is
        // used only after the signed padding-range test below succeeds, so the
        // wrapped values corresponding to logical positions -2, -1, 32, and 33
        // are never observed as real operands.
        snapshot_physical_position = snapshot_base + output_position
                                     + {2'b00, kernel_tap} - 5'd2;
        source_activation = 8'sd0;
        if ((source_position >= 7'sd0) && (source_position < 7'sd32)) begin
            if (layer_id == 2'd1)
                source_activation = $signed(
                    {1'b0, snapshot[snapshot_physical_position]})
                                    - 8'sd15;
            else if (layer_id == 2'd2)
                source_activation = $signed(final_features[
                    {input_channel, 5'b00000} + source_position[4:0]]);
            else
                source_activation = $signed(feature_bank_b[
                    {input_channel, 5'b00000} + source_position[4:0]]);
        end
    end

    // The 384-word compiler image is partitioned as 10 Conv1 words followed
    // by 180 Conv2 and 180 Conv3 words.  output_base[4] selects the lower or
    // upper 16-channel physical word; output_base[3:0] is used only for the
    // byte selection of 4/8-lane comparison builds.
    always_comb begin
        rom_read_enable = (state == STATE_MAC_ISSUE);
        rom_read_address = 9'd0;
        if (layer_id == 2'd1)
            rom_read_address = (output_base[4] ? 9'd5 : 9'd0)
                               + {6'd0, kernel_tap};
        else if (layer_id == 2'd2)
            rom_read_address = 9'd10
                               + (output_base[4] ? 9'd90 : 9'd0)
                               + ({4'd0, input_channel} << 2)
                               + {4'd0, input_channel}
                               + {6'd0, kernel_tap};
        else if (layer_id == 2'd3)
            rom_read_address = 9'd190
                               + (output_base[4] ? 9'd90 : 9'd0)
                               + ({4'd0, input_channel} << 2)
                               + {4'd0, input_channel}
                               + {6'd0, kernel_tap};
    end

    cnn_weight_rom weight_rom (
        .clk(clk),
        .reset(reset),
        .read_enable(rom_read_enable),
        .read_address(rom_read_address),
        .q_valid(rom_q_valid),
        .weight_word(rom_weight_word)
    );

    cnn_conv_bias_rom bias_rom (
        .layer_id(layer_id),
        .physical_group(output_base[4]),
        .position_class(bias_position_class),
        .lane_biases(rom_lane_biases)
    );

    cnn_channel_contract_rom contract_rom (
        .layer_id(layer_id),
        .physical_group(output_base[4]),
        .lane_right_shifts(rom_lane_right_shifts),
        .lane_magnitude_bounds(rom_lane_magnitude_bounds)
    );

    generate
        genvar generated_lane;
        for (generated_lane = 0; generated_lane < MAC_LANES;
             generated_lane = generated_lane + 1) begin : g_lane_numeric_contract
            localparam logic [4:0] LANE_INDEX = generated_lane;

            if (MAC_LANES == 16) begin : g_release_static_lane_slice
                // In the release configuration each ROM word always maps its
                // physical slot zero through fifteen directly onto MAC lane
                // zero through fifteen.  output_base selects the lower or upper
                // 16-channel word before these packed buses are produced; its
                // low four bits are therefore architecturally zero.  Constant
                // generated slices make that invariant structural, preventing
                // DC from building a dynamic 16-way packed-bus selector on the
                // multiplier and requantization paths.  Group one still masks
                // lanes 2..15 through the existing channel-valid predicate.
                assign lane_weight[generated_lane]
                    = rom_weight_word[(generated_lane * 8) +: 8];
                assign lane_bias[generated_lane] = $signed(
                    rom_lane_biases[(generated_lane * 20) +: 20]);
                assign lane_right_shift[generated_lane]
                    = registered_lane_right_shifts[
                        (generated_lane * 5) +: 5];
                assign lane_magnitude_bound[generated_lane]
                    = rom_lane_magnitude_bounds[
                        (generated_lane * 20) +: 20];
            end else begin : g_compatible_dynamic_lane_slice
                logic [4:0] physical_lane_index;
                logic [6:0] packed_shift_bit_index;
                logic [8:0] packed_bias_bound_bit_index;

                // Four- and eight-lane configurations advance output_base by
                // less than one physical ROM word, so they retain dynamic slot
                // selection.  Expressing offsets as shifts and additions avoids
                // address multipliers.  Explicit zero extension is required
                // because SystemVerilog preserves the left operand width during
                // shifts; omitting it would truncate offsets above lane one.
                assign physical_lane_index
                    = {1'b0, output_base[3:0]} + LANE_INDEX;
                assign packed_shift_bit_index
                    = ({2'b00, physical_lane_index} << 2)
                      + {2'b00, physical_lane_index};
                assign packed_bias_bound_bit_index
                    = ({4'b0000, physical_lane_index} << 4)
                      + ({4'b0000, physical_lane_index} << 2);
                assign lane_weight[generated_lane]
                    = rom_weight_word[
                        ({physical_lane_index, 3'b000}) +: 8];
                assign lane_bias[generated_lane] = $signed(
                    rom_lane_biases[packed_bias_bound_bit_index +: 20]);
                assign lane_right_shift[generated_lane]
                    = registered_lane_right_shifts[
                        packed_shift_bit_index +: 5];
                assign lane_magnitude_bound[generated_lane]
                    = rom_lane_magnitude_bounds[
                        packed_bias_bound_bit_index +: 20];
            end
            cnn_requantize_relu requantizer (
                .accumulator(accumulators[generated_lane]),
                .right_shift(lane_right_shift[generated_lane]),
                .activation(lane_requantized[generated_lane])
            );
        end
    endgenerate

    always_ff @(posedge clk or posedge reset) begin
        if (reset) begin
            state             <= STATE_IDLE;
            layer_id          <= 2'd1;
            output_position   <= 5'd0;
            output_base       <= 5'd0;
            input_channel     <= 5'd0;
            kernel_tap        <= 3'd0;
            activation_pipe   <= 8'sd0;
            activation_valid  <= 1'b0;
            product_valid     <= 1'b0;
            prepared_layer_id <= 2'd1;
            prepared_output_position <= 5'd0;
            prepared_output_base <= 5'd0;
            registered_lane_right_shifts <= 80'd0;
            busy              <= 1'b0;
            done              <= 1'b0;
            numeric_overflow  <= 1'b0;
            for (lane = 0; lane < MAC_LANES; lane = lane + 1) begin
                accumulators[lane] <= 20'sd0;
                product_pipe[lane] <= 16'sd0;
                prepared_activation[lane] <= 8'd0;
                prepared_lane_valid[lane] <= 1'b0;
            end
            // Feature data intentionally has no reset assignment.  After reset,
            // inference cannot start until the window buffer accepts a complete
            // L32 request.  Conv1 then overwrites every entry of physical bank A
            // before conv2 reads it, conv2 overwrites every entry of bank B
            // before conv3 reads it, and conv3 overwrites A before pooling.
            // Resetting these 9,216 data bits would add asynchronous-reset cells
            // and a very large reset tree without protecting an observable read.
        end else begin
            done <= 1'b0;

            // This is the sole physical convolution-product capture point.
            // During MAC_ISSUE it captures the response for the preceding ROM
            // request; during DRAIN_1 it captures the response for the final
            // request.  DRAIN_2 sees activation_valid cleared by DRAIN_1, so
            // this block inserts a bubble while the already registered final
            // product retires.  Keeping capture outside the state branches is
            // important structurally: each lane contains exactly one signed
            // 8x8 multiplier instead of separate ISSUE and DRAIN multiplier
            // cones selected onto the same product register.
            product_valid <= rom_q_valid && activation_valid;
            for (lane = 0; lane < MAC_LANES; lane = lane + 1) begin
                if (rom_q_valid && activation_valid
                    && ((output_base + lane) < 18))
                    product_pipe[lane] <= activation_pipe
                        * $signed(lane_weight[lane]);
                else
                    product_pipe[lane] <= 16'sd0;
            end

            case (state)
                STATE_IDLE: begin
                    if (start) begin
                        // Snapshot values were committed on the preceding
                        // request edge.  This edge is the first scheduled
                        // bias-init cycle, avoiding an unreported launch bubble.
                        // Capture the complete shift contract with the bias;
                        // it remains constant through this output group's MAC
                        // and drain cycles.  This removes output_base and the
                        // packed-ROM decoder from the requantize critical path
                        // without adding a controller state or changing data.
                        busy            <= 1'b1;
                        layer_id        <= 2'd1;
                        output_position <= 5'd0;
                        output_base     <= 5'd0;
                        input_channel   <= 5'd0;
                        kernel_tap      <= 3'd0;
                        registered_lane_right_shifts
                            <= rom_lane_right_shifts;
                        for (lane = 0; lane < MAC_LANES; lane = lane + 1) begin
                            if (lane < 18)
                                accumulators[lane] <= lane_bias[lane];
                            else
                                accumulators[lane] <= 20'sd0;
                        end
                        activation_valid <= 1'b0;
                        product_valid    <= 1'b0;
                        state <= STATE_MAC_ISSUE;
                    end
                end

                STATE_BIAS_INIT: begin
                    // All active output lanes load their accumulator-domain
                    // bias in parallel.  Channels above 17 are masked to zero.
                    // The matching packed shifts are captured on this same
                    // edge and are therefore registered long before the later
                    // STATE_REQUANT_PREPARE edge consumes them.
                    registered_lane_right_shifts <= rom_lane_right_shifts;
                    for (lane = 0; lane < MAC_LANES; lane = lane + 1) begin
                        if ((output_base + lane) < 18)
                            accumulators[lane] <= lane_bias[lane];
                        else
                            accumulators[lane] <= 20'sd0;
                    end
                    input_channel <= 5'd0;
                    kernel_tap    <= 3'd0;
                    activation_valid <= 1'b0;
                    product_valid    <= 1'b0;
                    state         <= STATE_MAC_ISSUE;
                end

                STATE_MAC_ISSUE: begin
                    // The address and activation for one fan-in operand are
                    // issued together.  On this edge, the previous ROM word
                    // and activation form a registered product, while an even
                    // older product retires into the accumulator.  Nonblocking
                    // assignments preserve these three distinct pipeline ages.
                    activation_pipe  <= source_activation;
                    activation_valid <= 1'b1;
                    for (lane = 0; lane < MAC_LANES; lane = lane + 1) begin
                        if (product_valid && ((output_base + lane) < 18))
                            accumulators[lane] <= accumulators[lane]
                                + product_pipe[lane];
                    end
                    if (kernel_tap == 3'd4) begin
                        kernel_tap <= 3'd0;
                        if (((layer_id == 2'd1) && (input_channel == 5'd0))
                            || ((layer_id != 2'd1)
                                && (input_channel == 5'd17))) begin
                            state <= STATE_DRAIN_1;
                        end else begin
                            input_channel <= input_channel + 5'd1;
                        end
                    end else begin
                        kernel_tap <= kernel_tap + 3'd1;
                    end
                end

                STATE_DRAIN_1: begin
                    // No new request is issued.  The response belonging to
                    // the final request is captured as a product, and the
                    // preceding product (when present) retires in parallel.
                    activation_valid <= 1'b0;
                    for (lane = 0; lane < MAC_LANES; lane = lane + 1) begin
                        if (product_valid && ((output_base + lane) < 18))
                            accumulators[lane] <= accumulators[lane]
                                + product_pipe[lane];
                    end
                    state <= STATE_DRAIN_2;
                end

                STATE_DRAIN_2: begin
                    // The last registered product retires here.  Requantizing
                    // on the following cycle guarantees that it observes the
                    // completed accumulator rather than its previous value.
                    product_valid <= 1'b0;
                    for (lane = 0; lane < MAC_LANES; lane = lane + 1) begin
                        if (product_valid && ((output_base + lane) < 18))
                            accumulators[lane] <= accumulators[lane]
                                + product_pipe[lane];
                    end
                    state <= STATE_REQUANT_PREPARE;
                end

                STATE_REQUANT_PREPARE: begin
                    // Runtime bound checking occurs only after the final
                    // product has retired.  Rounding/saturation and all target
                    // metadata are captured here; no feature bank is written
                    // on this edge.
                    prepared_layer_id       <= layer_id;
                    prepared_output_position <= output_position;
                    prepared_output_base    <= output_base;
                    for (lane = 0; lane < MAC_LANES; lane = lane + 1) begin
                        if ((output_base + lane) < 18) begin
                            prepared_activation[lane]
                                <= lane_requantized[lane];
                            prepared_lane_valid[lane] <= 1'b1;
                            if ((accumulators[lane] > $signed(
                                    lane_magnitude_bound[lane]))
                                || (accumulators[lane] < -$signed(
                                    lane_magnitude_bound[lane])))
                                numeric_overflow <= 1'b1;
                        end else begin
                            prepared_activation[lane] <= 8'd0;
                            prepared_lane_valid[lane] <= 1'b0;
                        end
                    end
                    state <= STATE_REQUANT_WRITE;
                end

                STATE_REQUANT_WRITE: begin
                    // Writeback is expressed as static channel/position
                    // registers with local enables.  A flattened dynamic index
                    // into a 576-byte unpacked array makes DC construct a full
                    // 4,608-bit mux for each procedural write.  These bounded
                    // loops elaborate to the same 576 physical bytes, but each
                    // byte now owns a simple equality-gated write enable.  The
                    // selected lane is valid because the range predicates prove
                    // write_channel-prepared_output_base lies in 0..MAC_LANES-1.
                    // No data register, state, or schedule cycle is added.
                    for (write_channel = 0; write_channel < 18;
                         write_channel = write_channel + 1) begin
                        for (write_position = 0; write_position < 32;
                             write_position = write_position + 1) begin
                            if ((prepared_output_position == write_position)
                                && (write_channel >= prepared_output_base)
                                && (write_channel
                                    < (prepared_output_base + MAC_LANES_VALUE))
                                && prepared_lane_valid[
                                    write_channel - prepared_output_base]) begin
                                if (prepared_layer_id == 2'd2)
                                    feature_bank_b[
                                        {write_channel[4:0], 5'b00000}
                                        + write_position]
                                        <= prepared_activation[
                                            write_channel
                                            - prepared_output_base];
                                else
                                    // Layer 1 and layer 3 have disjoint
                                    // lifetimes in physical bank A.  Layer 1
                                    // is consumed only by layer 2; layer 3 then
                                    // overwrites every A byte before pooling.
                                    final_features[
                                        {write_channel[4:0], 5'b00000}
                                        + write_position]
                                        <= prepared_activation[
                                            write_channel
                                            - prepared_output_base];
                            end
                        end
                    end

                    if ((prepared_output_base + MAC_LANES) >= 18) begin
                        output_base <= 5'd0;
                        if (prepared_output_position == 5'd31) begin
                            output_position <= 5'd0;
                            if (prepared_layer_id == 2'd3) begin
                                // The last conv3 values are committed on this
                                // edge; consumers observe done on the next cycle.
                                state <= STATE_IDLE;
                                busy  <= 1'b0;
                                done  <= 1'b1;
                                // Preselect conv1's first group so a future
                                // IDLE/start edge can perform bias-init directly.
                                layer_id <= 2'd1;
                            end else begin
                                layer_id <= prepared_layer_id + 2'd1;
                                state    <= STATE_BIAS_INIT;
                            end
                        end else begin
                            output_position
                                <= prepared_output_position + 5'd1;
                            state <= STATE_BIAS_INIT;
                        end
                    end else begin
                        output_base
                            <= prepared_output_base + MAC_LANES_VALUE;
                        state <= STATE_BIAS_INIT;
                    end
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
