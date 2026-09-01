#!/usr/bin/env python3
"""Generate the deterministic BFE12 controller-level A/B VCS testbench."""

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASK_ROOT = HERE.parent


def read_rows(path):
    with path.open(newline="", encoding="ascii") as stream:
        return list(csv.DictReader(stream))


def load_inputs():
    manifest = read_rows(TASK_ROOT / "P3_REPLAY_MANIFEST.csv")
    summary = json.loads((TASK_ROOT / "P3_REPLAY_MANIFEST.json").read_text(encoding="ascii"))
    return manifest, {int(item["seed"]): item for item in summary["calibration"]}


def expected(row, threshold):
    """Apply the frozen strict absolute and signed-RISE equations."""
    absolute = int(row["abs_e"]) > int(row["arch0_margin"])
    signed = row["polarity"] == "RISE" and int(row["signed_e"]) > threshold
    return int(absolute or signed)


def render(manifest, calibrations):
    # Triple-quoted text preserves the detailed generated port/pipeline
    # comments required for review of this simulation-only harness.
    header = r'''// BFE12 P4 exhaustive retained-data A/B controller replay.
//
// This generated bench is controller-level: retained M_FF values enter the
// normal event interface, while all four DUTs receive identical controls.
// DUT_A is untouched ARCH0; DUT_B/C/D are SIGN0 at T_POS_RISE=435/18/19.
// No internal reference is forced, and each event is allowed to reach E7.
`timescale 1ns/1ps
`default_nettype none
module tb_bfe12_sign0_retained_ab;
    // Common event inputs driven identically to all four controllers.
    reg clk_probe_i; reg reset_i; reg event_valid_i; reg edge_pol_i; reg cal_mode_i;
    reg [8:0] m_ff_i; reg [8:0] m_margin_rise_i; reg [8:0] m_margin_fall_i;
    reg [8:0] t_pos_rise_b_i; reg [8:0] t_pos_rise_c_i; reg [8:0] t_pos_rise_d_i;
    wire cal_lock_a; wire alarm_a; wire sticky_a;
    wire cal_lock_b; wire alarm_b; wire sticky_b;
    wire cal_lock_c; wire alarm_c; wire sticky_c;
    wire cal_lock_d; wire alarm_d; wire sticky_d;
    integer result_fd; integer event_count; integer healthy_fpr_alarm_count;
    integer signed_healthy_c_count; integer signed_healthy_d_count;
    integer d01_a; integer d01_c; integer d01_d;
    integer d02_a; integer d02_c; integer d02_d;
    integer d04_a; integer d04_c; integer d04_d;

    // The four instances share the exact same calibration and event stream.
    bfe_backend_ctrl u_arch0 (
        .clk_probe_i(clk_probe_i), .reset_i(reset_i), .event_valid_i(event_valid_i),
        .edge_pol_i(edge_pol_i), .cal_mode_i(cal_mode_i), .m_ff_i(m_ff_i),
        .m_margin_rise_i(m_margin_rise_i), .m_margin_fall_i(m_margin_fall_i),
        .cal_lock_o(cal_lock_a), .droop_alarm_o(alarm_a), .droop_alarm_sticky_o(sticky_a));
    bfe_backend_ctrl_arch1_sign0 u_sign0_off (
        .clk_probe_i(clk_probe_i), .reset_i(reset_i), .event_valid_i(event_valid_i),
        .edge_pol_i(edge_pol_i), .cal_mode_i(cal_mode_i), .m_ff_i(m_ff_i),
        .m_margin_rise_i(m_margin_rise_i), .m_margin_fall_i(m_margin_fall_i),
        .t_pos_rise_i(t_pos_rise_b_i), .cal_lock_o(cal_lock_b),
        .droop_alarm_o(alarm_b), .droop_alarm_sticky_o(sticky_b));
    bfe_backend_ctrl_arch1_sign0 u_sign0_18 (
        .clk_probe_i(clk_probe_i), .reset_i(reset_i), .event_valid_i(event_valid_i),
        .edge_pol_i(edge_pol_i), .cal_mode_i(cal_mode_i), .m_ff_i(m_ff_i),
        .m_margin_rise_i(m_margin_rise_i), .m_margin_fall_i(m_margin_fall_i),
        .t_pos_rise_i(t_pos_rise_c_i), .cal_lock_o(cal_lock_c),
        .droop_alarm_o(alarm_c), .droop_alarm_sticky_o(sticky_c));
    bfe_backend_ctrl_arch1_sign0 u_sign0_19 (
        .clk_probe_i(clk_probe_i), .reset_i(reset_i), .event_valid_i(event_valid_i),
        .edge_pol_i(edge_pol_i), .cal_mode_i(cal_mode_i), .m_ff_i(m_ff_i),
        .m_margin_rise_i(m_margin_rise_i), .m_margin_fall_i(m_margin_fall_i),
        .t_pos_rise_i(t_pos_rise_d_i), .cal_lock_o(cal_lock_d),
        .droop_alarm_o(alarm_d), .droop_alarm_sticky_o(sticky_d));

    // One probe edge lets nonblocking assignments settle before the next edge.
    task automatic clock_once;
        begin clk_probe_i=1'b1; #1; clk_probe_i=1'b0; #1; end
    endtask

    // Drive one event, wait E4->E7, compare all DUTs, and write one row.
    task automatic check_event;
        input integer dataset_code; input integer seed_value; input integer m_value;
        input integer polarity_value; input integer margin_value; input integer ref_value;
        input integer expected_a; input integer expected_b; input integer expected_c; input integer expected_d;
        input integer expected_signed_c; input integer expected_signed_d; input integer calibration_value;
        begin
            m_ff_i = m_value[8:0]; edge_pol_i = polarity_value[0]; cal_mode_i = calibration_value[0];
            m_margin_rise_i = (!polarity_value && !calibration_value) ? margin_value[8:0] : 9'd0;
            m_margin_fall_i = (polarity_value && !calibration_value) ? margin_value[8:0] : 9'd0;
            event_valid_i = 1'b1; clock_once(); event_valid_i = 1'b0;
            clock_once(); clock_once(); clock_once();
            if (alarm_a !== expected_a[0] || alarm_b !== expected_b[0] ||
                alarm_c !== expected_c[0] || alarm_d !== expected_d[0])
                $fatal(1, "P4 event mismatch dataset=%0d seed=%0d M=%0d A/B/C/D=%b/%b/%b/%b expected=%0d/%0d/%0d/%0d", dataset_code, seed_value, m_value, alarm_a, alarm_b, alarm_c, alarm_d, expected_a, expected_b, expected_c, expected_d);
            if (!calibration_value) begin
                if (u_sign0_18.alarm_edge_pol_q !== polarity_value[0] ||
                    u_sign0_19.alarm_edge_pol_q !== polarity_value[0] ||
                    u_sign0_18.alarm_t_pos_rise_q !== t_pos_rise_c_i ||
                    u_sign0_19.alarm_t_pos_rise_q !== t_pos_rise_d_i)
                    $fatal(1, "P4 signed context mismatch dataset=%0d seed=%0d", dataset_code, seed_value);
                if (u_sign0_18.signed_rise_alarm !== expected_signed_c[0] ||
                    u_sign0_19.signed_rise_alarm !== expected_signed_d[0])
                    $fatal(1, "P4 signed term mismatch dataset=%0d seed=%0d", dataset_code, seed_value);
            end
            $fwrite(result_fd, "%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d\n", dataset_code, seed_value, polarity_value, m_value, ref_value, margin_value, alarm_a, alarm_b, alarm_c, alarm_d, u_sign0_18.abs_alarm, u_sign0_18.signed_rise_alarm, u_sign0_19.signed_rise_alarm);
            event_count = event_count + (!calibration_value);
            if (dataset_code == 1) healthy_fpr_alarm_count = healthy_fpr_alarm_count + alarm_a;
            if (dataset_code == 2) signed_healthy_c_count = signed_healthy_c_count + u_sign0_18.signed_rise_alarm;
            if (dataset_code == 2) signed_healthy_d_count = signed_healthy_d_count + u_sign0_19.signed_rise_alarm;
            if (dataset_code == 3) begin d01_a=d01_a+alarm_a; d01_c=d01_c+alarm_c; d01_d=d01_d+alarm_d; end
            if (dataset_code == 4) begin d02_a=d02_a+alarm_a; d02_c=d02_c+alarm_c; d02_d=d02_d+alarm_d; end
            if (dataset_code == 5) begin d04_a=d04_a+alarm_a; d04_c=d04_c+alarm_c; d04_d=d04_d+alarm_d; end
        end
    endtask

    initial begin
        clk_probe_i=1'b0; reset_i=1'b1; event_valid_i=1'b0; edge_pol_i=1'b0; cal_mode_i=1'b0;
        m_ff_i=9'd0; m_margin_rise_i=9'd0; m_margin_fall_i=9'd0;
        t_pos_rise_b_i=9'd435; t_pos_rise_c_i=9'd18; t_pos_rise_d_i=9'd19;
        event_count=0; healthy_fpr_alarm_count=0; signed_healthy_c_count=0; signed_healthy_d_count=0;
        d01_a=0; d01_c=0; d01_d=0; d02_a=0; d02_c=0; d02_d=0; d04_a=0; d04_c=0; d04_d=0;
        result_fd=$fopen("P4_EVENT_RESULTS.csv", "w");
        if (result_fd == 0) $fatal(1, "P4 result file could not be opened");
        $fwrite(result_fd, "dataset_code,seed,polarity,m_ff,m_ref,margin,arch0,sign0_off,sign0_18,sign0_19,abs_term_18,signed_term_18,signed_term_19\n");
        #1; reset_i=1'b0;
'''
    lines = [header]
    code = {"healthy_fpr": 1, "healthy_signed_rise": 2, "d01_target": 3,
            "d02_target": 4, "d04_target": 5}
    for seed in sorted(calibrations):
        cal = calibrations[seed]
        lines.append("        // Seed {}: calibrate references through the normal interface.".format(seed))
        lines.append("        reset_i=1'b1; #1; reset_i=1'b0;")
        for value in cal["rise_samples"]:
            lines.append("        check_event(0, {}, {}, 0, 0, {}, 0, 0, 0, 0, 0, 0, 1);".format(seed, value, cal["m_ref_rise"]))
        for value in cal["fall_samples"]:
            lines.append("        check_event(0, {}, {}, 1, 0, {}, 0, 0, 0, 0, 0, 0, 1);".format(seed, value, cal["m_ref_fall"]))
        lines.append("        if (!cal_lock_a || !cal_lock_b || !cal_lock_c || !cal_lock_d) $fatal(1, \"P4 CAL_LOCK missing seed=%0d\", {});".format(seed))
        for row in [item for item in manifest if int(item["seed"]) == seed]:
            p = 0 if row["polarity"] == "RISE" else 1
            a = int(row["expected_arch0_alarm"])
            b = expected(row, 435)
            c = expected(row, 18)
            d = expected(row, 19)
            sc = int(row["polarity"] == "RISE" and int(row["signed_e"]) > 18)
            sd = int(row["polarity"] == "RISE" and int(row["signed_e"]) > 19)
            lines.append("        check_event({}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, 0);".format(code[row["dataset"]], seed, int(row["m_ff"]), p, int(row["arch0_margin"]), int(row["m_ref"]), a, b, c, d, sc, sd))
    lines.extend([
        "        if (event_count != 690) $fatal(1, \"P4 event count mismatch got=%0d\", event_count);",
        "        if (healthy_fpr_alarm_count != 1 || signed_healthy_c_count != 0 || signed_healthy_d_count != 0) $fatal(1, \"P4 healthy result mismatch FPR=%0d signed18=%0d signed19=%0d\", healthy_fpr_alarm_count, signed_healthy_c_count, signed_healthy_d_count);",
        "        if (d01_a != 22 || d01_c != 30 || d01_d != 30 || d02_a != 30 || d02_c != 30 || d02_d != 30 || d04_a != 24 || d04_c != 30 || d04_d != 30) $fatal(1, \"P4 coverage mismatch D01=%0d/%0d/%0d D02=%0d/%0d/%0d D04=%0d/%0d/%0d\", d01_a, d01_c, d01_d, d02_a, d02_c, d02_d, d04_a, d04_c, d04_d);",
        "        $fclose(result_fd);",
        "        $display(\"BFE12_SIGN0_P4_RETAINED_AB_RTL_CHARACTERIZED\");",
        "        $finish;",
        "    end",
        "endmodule",
        "`default_nettype wire",
        "",
    ])
    return "\n".join(lines)


def main():
    manifest, calibrations = load_inputs()
    output = HERE / "tb_bfe12_sign0_retained_ab.sv"
    output.write_text(render(manifest, calibrations), encoding="ascii")
    print(output)


if __name__ == "__main__":
    main()
