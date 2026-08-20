// Two-register Q classifier for the FTC sensor capture result.
`timescale 1ns/1ps
`default_nettype none

module ftc_q_sampler (
    // Controller clock used to make both observations real sequential samples.
    input  logic       clk_i,
    // Active-low controller POR clears retained observations and result-valid.
    input  logic       por_n_i,
    // Sensor DFF output sampled at the two frozen probe schedule points.
    input  logic       q_final_i,
    // One-cycle strobes owned exclusively by the operation sequencer.
    input  logic       sample_1_i,
    input  logic       sample_2_i,
    // Captured observations retained for waveform/audit visibility.
    output logic       q_sample_1_o,
    output logic       q_sample_2_o,
    // Result is valid for one cycle after sample_2_i.
    output logic       class_valid_o,
    // Stable-low, stable-high, or ambiguous encoding from ftc_cal_pkg.
    output logic [1:0] q_class_o
);
    import ftc_cal_pkg::*;

    always_ff @(posedge clk_i or negedge por_n_i) begin
        if (!por_n_i) begin
            q_sample_1_o <= 1'b0;
            q_sample_2_o <= 1'b0;
            q_class_o <= Q_CLASS_AMBIGUOUS;
            class_valid_o <= 1'b0;
        end else begin
            class_valid_o <= 1'b0;
            if (sample_1_i)
                q_sample_1_o <= q_final_i;
            if (sample_2_i) begin
                q_sample_2_o <= q_final_i;
                // q_sample_1_o is the first physical register.  At this edge
                // it still contains sample #1 while q_final_i supplies #2.
                if (!q_sample_1_o && !q_final_i)
                    q_class_o <= Q_CLASS_STABLE_LOW;
                else if (q_sample_1_o && q_final_i)
                    q_class_o <= Q_CLASS_STABLE_HIGH;
                else
                    q_class_o <= Q_CLASS_AMBIGUOUS;
                class_valid_o <= 1'b1;
            end
        end
    end
endmodule

`default_nettype wire
