// Final Phase-3 same-rail RVT/LVT Vernier sensor macro.
//
// The public interface intentionally exposes only VDD_A/VSS_A.  The physical
// frontend is a real standard-cell launch/chain/DFF hierarchy, while this thin
// wrapper supplies a single controller-clock settlement interval before raw
// thermometer capture and presents the decoded result.
`default_nettype none

module phase3_sensor (
    // Controller interface:
    // clk_i advances the capture handshake, rst_i clears the physical/Digital
    // sampling state, and sample_req_i requests one physical launch.  A request
    // is captured on the following controller clock after frontend settlement.
    input  logic       clk_i,
    input  logic       rst_i,
    input  logic       sample_req_i,

    // Same-rail power interface:
    // vdd_a_i and vss_a_i are the only rails exposed by this macro.  They
    // supply the calibration network, RVT/LVT delay chains, and DFF bank;
    // the Phase-3 public interface intentionally has no reference rail.
    inout  wire        vdd_a_i,
    inout  wire        vss_a_i,

    // Decoded-result interface:
    // sensor_code_o is the settled 0..32 transition position; code_valid_o
    // qualifies the corrected thermometer word; sample_valid_o is a one-cycle
    // controller-clock pulse identifying a newly captured result.
    output logic [5:0] sensor_code_o,
    output logic       code_valid_o,
    output logic       sample_valid_o
);
    import phase3_calibration_pkg::*;

    // The pending bit supplies one full controller period between the rising
    // launch request and digital capture.  The actual Vernier/DFF timing is
    // still decided by physical cells; this is only the controller handshake.
    logic capture_pending;
    logic [31:0] raw_thermometer;

    // These retained internal nets support structural audit and raw-code replay
    // without widening the required public Phase-3 macro interface.
    logic [31:0] normalized_thermometer_unused;
    logic [31:0] corrected_thermometer_unused;
    logic [5:0]  bubble_count_unused;

    always_ff @(posedge clk_i or posedge rst_i) begin
        if (rst_i) begin
            capture_pending <= 1'b0;
        end else begin
            capture_pending <= sample_req_i;
        end
    end

    // The sparse frontend is permanently fixed to the separately characterized
    // wide-range CAL_SEL.  There is no runtime calibration input, which keeps
    // the HSPICE-qualified aperture and synthesizable hardware identical.
    phase3_frontend_struct u_frontend (
        .vdd_a_i(vdd_a_i), .vss_a_i(vss_a_i),
        .launch_req_i(sample_req_i), .cal_sel_i(WIDE_RANGE_DEFAULT_CAL_SEL),
        .rst_i(rst_i), .raw_thermometer_o(raw_thermometer)
    );

    phase3_decoder u_decoder (
        .clk_i(clk_i), .rst_i(rst_i), .capture_enable_i(capture_pending),
        .raw_thermometer_i(raw_thermometer),
        .raw_thermometer_o(),
        .normalized_thermometer_o(normalized_thermometer_unused),
        .corrected_thermometer_o(corrected_thermometer_unused),
        .sensor_code_o(sensor_code_o), .bubble_count_o(bubble_count_unused),
        .code_valid_o(code_valid_o), .sample_valid_o(sample_valid_o)
    );
endmodule

`default_nettype wire
