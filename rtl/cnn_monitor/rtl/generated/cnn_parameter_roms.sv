`default_nettype none

// Generated file: do not hand edit.
// Packed accumulator-domain convolution biases for one physical group.
// Lane zero always occupies the least-significant packed slice.
module cnn_conv_bias_rom (
    input  logic [1:0]   layer_id, // 1/2/3 select the convolution layer.
    input  logic         physical_group, // Zero selects channels 0..15; one selects 16..31.
    input  logic [2:0]   position_class, // Conv1 classes 0/1/interior/30/31; other layers use zero.
    output logic [319:0] lane_biases // Sixteen signed 20-bit biases; physical lane zero is [19:0].
);

    // Only fourteen whole-word alternatives are decoded: ten Conv1
    // position/group words plus two words for each later layer.
    always_comb begin
        lane_biases = 320'b0;
        case ({layer_id, physical_group, position_class})
            6'h10: lane_biases = 320'hffecb001f80002effcfdffe760008200171ffd64ffba8fffe400221fffe1ffdaeffb7e0017affff1;
            6'h11: lane_biases = 320'hffefb001b80005effd11fff860018500187ffd80ffbeffff9900187000acffd6fffb8300146fffed;
            6'h12: lane_biases = 320'hffeaf002cb00021ffd2afff36001ca001bbffd96ffc14fff8f00298000eaffd8cffbc30016f000b1;
            6'h13: lane_biases = 320'hfff21002e900022ffd4cffe3d001cb001fbffd96ffcf5fff0200195000b7ffe1dffb150011f0002b;
            6'h14: lane_biases = 320'hfff500021e00060ffd2fffe3800184001fcffe25ffd8effea4000c3000e8ffe12ffbca0008100019;
            6'h18: lane_biases = 320'h0000000000000000000000000000000000000000000000000000000000000000000000fffdbfff57;
            6'h19: lane_biases = 320'h00000000000000000000000000000000000000000000000000000000000000000000000000c0000a;
            6'h1a: lane_biases = 320'h00000000000000000000000000000000000000000000000000000000000000000000000000100037;
            6'h1b: lane_biases = 320'h00000000000000000000000000000000000000000000000000000000000000000000000005b00061;
            6'h1c: lane_biases = 320'h00000000000000000000000000000000000000000000000000000000000000000000000004d0003a;
            6'h20: lane_biases = 320'h00019fff470003c004dcffead0001c002a800186000d7ffdb700253003b2ffe7fff941001670011e;
            6'h28: lane_biases = 320'h0000000000000000000000000000000000000000000000000000000000000000000000fff32ffad3;
            6'h30: lane_biases = 320'h000310003d0004f00023fff70fffd7ffe420004bfffa6ffffcffe91fff840017d00018fff7500005;
            6'h38: lane_biases = 320'h0000000000000000000000000000000000000000000000000000000000000000000000000c0fff5a;
            default: lane_biases = 320'b0;
        endcase
    end
endmodule

// Generated file: do not hand edit.
// Packed fixed-point shifts and overflow bounds for one physical group.
// Lane zero always occupies the least-significant packed slice.
module cnn_channel_contract_rom (
    input  logic [1:0]  layer_id, // 1/2/3 select the convolution layer.
    input  logic        physical_group, // Zero selects channels 0..15; one selects 16..31.
    output logic [79:0] lane_right_shifts, // Sixteen unsigned five-bit requantization shifts.
    output logic [319:0] lane_magnitude_bounds // Sixteen unsigned twenty-bit accumulator bounds.
);

    // One decoder supplies every lane; channels 18 through 31 remain
    // zero-filled in physical group one and are masked by the engine.
    always_comb begin
        lane_right_shifts = 80'b0;
        lane_magnitude_bounds = 320'b0;
        case ({layer_id, physical_group})
            3'h2: begin
                lane_right_shifts = 80'h2146429484290a421484;
                lane_magnitude_bounds = 320'h00eee0152c009df00ac801aaf010de00ce0008a7016ce00c7301f4800cbc00c540154100d080114b;
            end
            3'h3: begin
                lane_right_shifts = 80'h00000000000000000063;
                lane_magnitude_bounds = 320'h00000000000000000000000000000000000000000000000000000000000000000000000099600b27;
            end
            3'h4: begin
                lane_right_shifts = 80'h3a10849d073a0e842d08;
                lane_magnitude_bounds = 320'h2f1aa38f8d569d33c7485803f21fd43dde223b8926bf7405b21ee73352083f8835266b38ac640a7b;
            end
            3'h5: begin
                lane_right_shifts = 80'h0000000000000000010a;
                lane_magnitude_bounds = 320'h00000000000000000000000000000000000000000000000000000000000000000000003d3993bbb1;
            end
            3'h6: begin
                lane_right_shifts = 80'h394c5399063190739906;
                lane_magnitude_bounds = 320'h52ebf211134f64f25b634417d4372a59af52a5f535d9235e3a32619305e553def4038156b204720f;
            end
            3'h7: begin
                lane_right_shifts = 80'h000000000000000000c6;
                lane_magnitude_bounds = 320'h00000000000000000000000000000000000000000000000000000000000000000000003f4c844885;
            end
            default: begin
                lane_right_shifts = 80'b0;
                lane_magnitude_bounds = 320'b0;
            end
        endcase
    end
endmodule

// Generated file: do not hand edit.
// Binary classifier constants in the task-one summary concatenation order.
// Lane zero always occupies the least-significant packed slice.
module cnn_classifier_parameter_rom (
    input  logic [5:0]  summary_index, // Summary feature 0 through 53 in average/max/endpoint order.
    output logic [15:0] class_weights, // Signed 8-bit Safe weight in [7:0], Critical in [15:8].
    output logic [39:0] class_biases, // Signed 20-bit Safe bias in [19:0], Critical in [39:20].
    output logic [9:0]  class_left_shifts, // Five-bit exact left shift for each output class.
    output logic [39:0] class_bounds // Twenty-bit magnitude bound for each output class.
);

    always_comb begin
        class_weights = 16'b0;
        case (summary_index)
            6'd0: class_weights = 16'hec3c;
            6'd1: class_weights = 16'h0504;
            6'd2: class_weights = 16'h0402;
            6'd3: class_weights = 16'hef45;
            6'd4: class_weights = 16'h0ef6;
            6'd5: class_weights = 16'hfb0b;
            6'd6: class_weights = 16'hec44;
            6'd7: class_weights = 16'h07ee;
            6'd8: class_weights = 16'hee34;
            6'd9: class_weights = 16'h0608;
            6'd10: class_weights = 16'hd94d;
            6'd11: class_weights = 16'h08e6;
            6'd12: class_weights = 16'hef2b;
            6'd13: class_weights = 16'hda44;
            6'd14: class_weights = 16'h1fbd;
            6'd15: class_weights = 16'he522;
            6'd16: class_weights = 16'hdf4a;
            6'd17: class_weights = 16'hf919;
            6'd18: class_weights = 16'hea39;
            6'd19: class_weights = 16'hfef3;
            6'd20: class_weights = 16'h14e7;
            6'd21: class_weights = 16'h0cf5;
            6'd22: class_weights = 16'h000b;
            6'd23: class_weights = 16'h02f6;
            6'd24: class_weights = 16'h0be4;
            6'd25: class_weights = 16'hdc3d;
            6'd26: class_weights = 16'h0ffd;
            6'd27: class_weights = 16'hfa04;
            6'd28: class_weights = 16'h09d2;
            6'd29: class_weights = 16'hf507;
            6'd30: class_weights = 16'hc775;
            6'd31: class_weights = 16'hd94c;
            6'd32: class_weights = 16'hea1e;
            6'd33: class_weights = 16'h08ec;
            6'd34: class_weights = 16'hc77d;
            6'd35: class_weights = 16'h09df;
            6'd36: class_weights = 16'hf22b;
            6'd37: class_weights = 16'h060b;
            6'd38: class_weights = 16'hf41f;
            6'd39: class_weights = 16'hed44;
            6'd40: class_weights = 16'h02f2;
            6'd41: class_weights = 16'hfc0a;
            6'd42: class_weights = 16'hdc3f;
            6'd43: class_weights = 16'h11fd;
            6'd44: class_weights = 16'hea1b;
            6'd45: class_weights = 16'hfd0e;
            6'd46: class_weights = 16'hb77d;
            6'd47: class_weights = 16'h07fb;
            6'd48: class_weights = 16'hea19;
            6'd49: class_weights = 16'h11d4;
            6'd50: class_weights = 16'he83a;
            6'd51: class_weights = 16'hc673;
            6'd52: class_weights = 16'h15d4;
            6'd53: class_weights = 16'hfb1e;
            default: class_weights = 16'b0;
        endcase
        class_biases = 40'h0015fffd9c;
        class_left_shifts = 10'h230;
        class_bounds = 40'h1f96741f99;
    end
endmodule

`default_nettype wire
