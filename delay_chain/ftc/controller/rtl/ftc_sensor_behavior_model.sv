// FTC sensor behavioral model for controller verification.
//
// This model emulates the transistor-level sensor's Q output behavior based
// on the current medium/fine configuration and S_CLK sampling edges.
//
// The model is configured with a scenario-specific Q classification table
// that maps [M][F] coordinates to expected Q behavior (STABLE_LOW, STABLE_HIGH,
// or AMBIGUOUS).
//
// On each S_CLK rising edge (when reset is released), the model samples the
// current configuration and returns the scripted Q value after a realistic
// propagation delay.
//
// This behavioral model is used for Phase 5-6 RTL-only controller testing.
// Phase 9 replaces this with the real transistor-level HSPICE sensor.
`timescale 1ns/1ps
`default_nettype none

module ftc_sensor_behavior_model (
    // =========================================================================
    // Sensor Controls (from controller)
    // =========================================================================
    // Sensor DFF reset (active high). When asserted, q_final_o is forced low.
    input  logic                          sense_dff_reset_i,
    // Sensor sampling clock. Rising edge captures delay chain state.
    input  logic                          sense_s_clk_i,

    // =========================================================================
    // Configuration Inputs (from controller)
    // =========================================================================
    // Medium path selection thermometer.
    input  logic [ftc_cal_pkg::MEDIUM_BITS:0] medium_therm_i,
    // Fine load tuning thermometer.
    input  logic [ftc_cal_pkg::FINE_BITS:0]   fine_therm_i,

    // =========================================================================
    // Sensor Output
    // =========================================================================
    // Final Q output from sensor DFF. This is the value the controller samples.
    output logic                          q_final_o
);

    import ftc_cal_pkg::*;

    // =========================================================================
    // Internal Signals
    // =========================================================================
    // Decoded medium and fine codes from thermometer inputs.
    int unsigned medium_code;
    int unsigned fine_code;

    // Q classification lookup table (scenario-specific, loaded by testbench).
    // Indexed by [medium_code][fine_code].
    // Values: Q_CLASS_STABLE_LOW (2'b00), Q_CLASS_STABLE_HIGH (2'b11),
    //         Q_CLASS_AMBIGUOUS (2'b01 or 2'b10).
    logic [1:0] q_class_table [0:MEDIUM_BITS][0:FINE_BITS];

    // Previous S_CLK value for edge detection.
    logic sense_s_clk_prev;

    // Propagation delay parameter (realistic sensor delay).
    localparam realtime SENSOR_PROP_DELAY = 150ps;

    // =========================================================================
    // Thermometer to Binary Decoder
    // =========================================================================
    // Count the number of asserted bits in the thermometer code to get binary.
    // Thermometer encoding: 000...0 (code 0), 100...0 (code 1), 110...0 (code 2), etc.
    always_comb begin
        medium_code = 0;
        for (int i = 0; i <= MEDIUM_BITS; i++) begin
            if (medium_therm_i[i]) medium_code = medium_code + 1;
        end

        fine_code = 0;
        for (int i = 0; i <= FINE_BITS; i++) begin
            if (fine_therm_i[i]) fine_code = fine_code + 1;
        end
    end

    // =========================================================================
    // Q Output Generation
    // =========================================================================
    // Initialize Q classification table to default STABLE_HIGH.
    initial begin
        for (int m = 0; m <= MEDIUM_BITS; m++) begin
            for (int f = 0; f <= FINE_BITS; f++) begin
                q_class_table[m][f] = Q_CLASS_STABLE_HIGH;
            end
        end
    end

    // Behavioral Q generation based on S_CLK edges and reset.
    always @(posedge sense_s_clk_i or posedge sense_dff_reset_i) begin
        if (sense_dff_reset_i) begin
            // Reset forces Q low immediately.
            q_final_o <= #1ps 1'b0;
        end else begin
            // S_CLK rising edge: sample configuration and return scripted Q value.
            // Apply realistic propagation delay.
            automatic logic [1:0] q_class = q_class_table[medium_code][fine_code];

            // For STABLE_LOW, return 0. For STABLE_HIGH, return 1.
            // For AMBIGUOUS (metastable), return 0 on first sample, 1 on second.
            // Simplified: return the LSB of the class encoding.
            // Proper handling: testbench should configure AMBIGUOUS carefully.
            if (q_class == Q_CLASS_STABLE_LOW) begin
                q_final_o <= #SENSOR_PROP_DELAY 1'b0;
            end else if (q_class == Q_CLASS_STABLE_HIGH) begin
                q_final_o <= #SENSOR_PROP_DELAY 1'b1;
            end else begin
                // AMBIGUOUS: return metastable-like value (testbench controls this).
                // For now, return 0 (conservative choice).
                q_final_o <= #SENSOR_PROP_DELAY q_class[0];
            end
        end
    end

    // =========================================================================
    // Waveform Debug Support
    // =========================================================================
    // Track edge count for debug visibility.
    int unsigned s_clk_edge_count;

    initial begin
        sense_s_clk_prev = 1'b0;
        s_clk_edge_count = 0;
    end

    always @(sense_s_clk_i) begin
        if (sense_s_clk_i && !sense_s_clk_prev) begin
            s_clk_edge_count = s_clk_edge_count + 1;
        end
        sense_s_clk_prev = sense_s_clk_i;
    end

endmodule

`default_nettype wire
