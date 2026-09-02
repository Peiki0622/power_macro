#!/usr/bin/env python3
"""Generate the single retained BFE12 SIGN0-vs-TRACK0 A/B replay bench.

The script consumes only the already-frozen BFE12 CSV/JSON replay contract.
It does not regenerate waveforms and never invokes an EDA simulator.  Six
controller instances are used in one VCS run: SIGN0 and TRACK0 at each of the
three authorized thresholds 435, 18, and 19.  TRACK0 parameters are all zero,
so this is an event-equivalence regression rather than tracker characterization.
"""

import csv
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
TASK = HERE.parent
BFE12 = TASK.parent / "bfe12_arch1_sign0_signed_droop_rtl"


def rows():
    with (BFE12 / "P3_REPLAY_MANIFEST.csv").open(newline="", encoding="ascii") as stream:
        return list(csv.DictReader(stream))


def calibrations():
    payload = json.loads((BFE12 / "P3_REPLAY_MANIFEST.json").read_text(encoding="ascii"))
    return sorted(payload["calibration"], key=lambda item: int(item["seed"]))


def render():
    header = r'''// BFE13 P4 retained-data controller A/B replay.
//
// A0/A18/A19 are the frozen BFE12 SIGN0 controller at T=435/18/19.
// B0/B18/B19 are the candidate TRACK0 controller with all four tracker
// parameters zero.  Every instance receives identical calibration and event
// inputs; no internal reference is forced and no physical waveform is read.
`timescale 1ns/1ps
`default_nettype none
module tb_bfe13_track0_retained_ab;
    reg clk; reg reset; reg event_valid; reg edge_pol; reg cal_mode;
    reg [8:0] m_ff; reg [8:0] margin_rise; reg [8:0] margin_fall;
    reg [8:0] t435; reg [8:0] t18; reg [8:0] t19;
    wire lock_a0, lock_a18, lock_a19, lock_b0, lock_b18, lock_b19;
    wire alarm_a0, alarm_a18, alarm_a19, alarm_b0, alarm_b18, alarm_b19;
    wire sticky_a0, sticky_a18, sticky_a19, sticky_b0, sticky_b18, sticky_b19;
    integer fd; integer event_count; integer mismatch_count;
    integer healthy_a0; integer healthy_b0; integer healthy_a18; integer healthy_b18;
    integer d01_a18; integer d01_b18; integer d02_a18; integer d02_b18;
    integer d04_a18; integer d04_b18;

    bfe_backend_ctrl_arch1_sign0 u_a0 (.clk_probe_i(clk), .reset_i(reset), .event_valid_i(event_valid), .edge_pol_i(edge_pol), .cal_mode_i(cal_mode), .m_ff_i(m_ff), .m_margin_rise_i(margin_rise), .m_margin_fall_i(margin_fall), .t_pos_rise_i(t435), .cal_lock_o(lock_a0), .droop_alarm_o(alarm_a0), .droop_alarm_sticky_o(sticky_a0));
    bfe_backend_ctrl_arch1_sign0 u_a18 (.clk_probe_i(clk), .reset_i(reset), .event_valid_i(event_valid), .edge_pol_i(edge_pol), .cal_mode_i(cal_mode), .m_ff_i(m_ff), .m_margin_rise_i(margin_rise), .m_margin_fall_i(margin_fall), .t_pos_rise_i(t18), .cal_lock_o(lock_a18), .droop_alarm_o(alarm_a18), .droop_alarm_sticky_o(sticky_a18));
    bfe_backend_ctrl_arch1_sign0 u_a19 (.clk_probe_i(clk), .reset_i(reset), .event_valid_i(event_valid), .edge_pol_i(edge_pol), .cal_mode_i(cal_mode), .m_ff_i(m_ff), .m_margin_rise_i(margin_rise), .m_margin_fall_i(margin_fall), .t_pos_rise_i(t19), .cal_lock_o(lock_a19), .droop_alarm_o(alarm_a19), .droop_alarm_sticky_o(sticky_a19));
    bfe_backend_ctrl_arch1_track0 #(.T_TRACK_RISE(0),.T_TRACK_FALL(0),.B_TRACK_RISE(0),.B_TRACK_FALL(0)) u_b0 (.clk_probe_i(clk), .reset_i(reset), .event_valid_i(event_valid), .edge_pol_i(edge_pol), .cal_mode_i(cal_mode), .m_ff_i(m_ff), .m_margin_rise_i(margin_rise), .m_margin_fall_i(margin_fall), .t_pos_rise_i(t435), .cal_lock_o(lock_b0), .droop_alarm_o(alarm_b0), .droop_alarm_sticky_o(sticky_b0));
    bfe_backend_ctrl_arch1_track0 #(.T_TRACK_RISE(0),.T_TRACK_FALL(0),.B_TRACK_RISE(0),.B_TRACK_FALL(0)) u_b18 (.clk_probe_i(clk), .reset_i(reset), .event_valid_i(event_valid), .edge_pol_i(edge_pol), .cal_mode_i(cal_mode), .m_ff_i(m_ff), .m_margin_rise_i(margin_rise), .m_margin_fall_i(margin_fall), .t_pos_rise_i(t18), .cal_lock_o(lock_b18), .droop_alarm_o(alarm_b18), .droop_alarm_sticky_o(sticky_b18));
    bfe_backend_ctrl_arch1_track0 #(.T_TRACK_RISE(0),.T_TRACK_FALL(0),.B_TRACK_RISE(0),.B_TRACK_FALL(0)) u_b19 (.clk_probe_i(clk), .reset_i(reset), .event_valid_i(event_valid), .edge_pol_i(edge_pol), .cal_mode_i(cal_mode), .m_ff_i(m_ff), .m_margin_rise_i(margin_rise), .m_margin_fall_i(margin_fall), .t_pos_rise_i(t19), .cal_lock_o(lock_b19), .droop_alarm_o(alarm_b19), .droop_alarm_sticky_o(sticky_b19));

    task automatic clock_once;
        begin clk=1'b1; #1; clk=1'b0; #1; end
    endtask

    task automatic check_event;
        input integer dataset_code; input integer seed_value; input integer m_value;
        input integer polarity_value; input integer margin_value; input integer ref_value;
        input integer expected_a; input integer expected_c; input integer expected_d;
        input integer calibration_value;
        begin
            m_ff=m_value[8:0]; edge_pol=polarity_value[0]; cal_mode=calibration_value[0];
            margin_rise=(!polarity_value && !calibration_value) ? margin_value[8:0] : 9'd0;
            margin_fall=(polarity_value && !calibration_value) ? margin_value[8:0] : 9'd0;
            event_valid=1'b1; clock_once(); event_valid=1'b0;
            clock_once(); clock_once(); clock_once();
            if (alarm_a0 !== expected_a[0] || alarm_b0 !== expected_a[0] ||
                alarm_a18 !== expected_c[0] || alarm_b18 !== expected_c[0] ||
                alarm_a19 !== expected_d[0] || alarm_b19 !== expected_d[0]) begin
                mismatch_count=mismatch_count+1;
                $fatal(1,"P4 event mismatch dataset=%0d seed=%0d M=%0d A0/B0/A18/B18/A19/B19=%b/%b/%b/%b/%b/%b",dataset_code,seed_value,m_value,alarm_a0,alarm_b0,alarm_a18,alarm_b18,alarm_a19,alarm_b19);
            end
            if (lock_a0 !== lock_b0 || lock_a18 !== lock_b18 || lock_a19 !== lock_b19 ||
                sticky_a0 !== sticky_b0 || sticky_a18 !== sticky_b18 || sticky_a19 !== sticky_b19)
                $fatal(1,"P4 lock/sticky mismatch dataset=%0d seed=%0d",dataset_code,seed_value);
            if (u_b0.m_ref_track_rise_q !== u_b0.m_ref_startup_rise_q ||
                u_b0.m_ref_track_fall_q !== u_b0.m_ref_startup_fall_q ||
                u_b18.m_ref_track_rise_q !== u_b18.m_ref_startup_rise_q ||
                u_b18.m_ref_track_fall_q !== u_b18.m_ref_startup_fall_q ||
                u_b19.m_ref_track_rise_q !== u_b19.m_ref_startup_rise_q ||
                u_b19.m_ref_track_fall_q !== u_b19.m_ref_startup_fall_q)
                $fatal(1,"P4 default-disable TRACK0 reference moved dataset=%0d seed=%0d",dataset_code,seed_value);
            $fwrite(fd,"%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d\n",dataset_code,seed_value,polarity_value,m_value,ref_value,margin_value,alarm_a0,alarm_b0,alarm_a18,alarm_b18,alarm_a19,alarm_b19,sticky_b18);
            if (!calibration_value) begin
                event_count=event_count+1;
                if (dataset_code==1) begin healthy_a0=healthy_a0+alarm_a0; healthy_b0=healthy_b0+alarm_b0; end
                if (dataset_code==2) begin healthy_a18=healthy_a18+alarm_a18; healthy_b18=healthy_b18+alarm_b18; end
                if (dataset_code==3) begin d01_a18=d01_a18+alarm_a18; d01_b18=d01_b18+alarm_b18; end
                if (dataset_code==4) begin d02_a18=d02_a18+alarm_a18; d02_b18=d02_b18+alarm_b18; end
                if (dataset_code==5) begin d04_a18=d04_a18+alarm_a18; d04_b18=d04_b18+alarm_b18; end
            end
        end
    endtask

    initial begin
        clk=0; reset=1; event_valid=0; edge_pol=0; cal_mode=0; m_ff=0;
        margin_rise=0; margin_fall=0; t435=435; t18=18; t19=19;
        event_count=0; mismatch_count=0; healthy_a0=0; healthy_b0=0; healthy_a18=0; healthy_b18=0;
        d01_a18=0; d01_b18=0; d02_a18=0; d02_b18=0; d04_a18=0; d04_b18=0;
        fd=$fopen("P4_EVENT_RESULTS.csv","w");
        if (fd==0) $fatal(1,"P4 result file could not be opened");
        $fwrite(fd,"dataset_code,seed,polarity,m_ff,m_ref,margin,sign0_435,track0_435,sign0_18,track0_18,sign0_19,track0_19,track0_sticky18\n");
        #1; reset=0;
'''
    lines = [header]
    code = {"healthy_fpr": 1, "healthy_signed_rise": 2, "d01_target": 3, "d02_target": 4, "d04_target": 5}
    for cal in calibrations():
        seed = int(cal["seed"])
        lines.append(f"        reset=1'b1; #1; reset=1'b0;")
        for value in cal["rise_samples"]:
            lines.append(f"        check_event(0,{seed},{int(value)},0,0,{int(cal['m_ref_rise'])},0,0,0,1);")
        for value in cal["fall_samples"]:
            lines.append(f"        check_event(0,{seed},{int(value)},1,0,{int(cal['m_ref_fall'])},0,0,0,1);")
        lines.append(f"        if (!lock_a0 || !lock_a18 || !lock_a19 || !lock_b0 || !lock_b18 || !lock_b19) $fatal(1,\"P4 CAL_LOCK missing seed=%0d\",{seed});")
        for row in [item for item in rows() if int(item["seed"]) == seed]:
            p = 0 if row["polarity"] == "RISE" else 1
            a = int(row["expected_arch0_alarm"])
            # SIGN0/zero-tracker outputs include the inherited absolute term;
            # the manifest's signed-only columns are not total alarm values.
            abs_hit = int(row["abs_e"]) > int(row["arch0_margin"])
            signed18 = row["polarity"] == "RISE" and int(row["signed_e"]) > 18
            signed19 = row["polarity"] == "RISE" and int(row["signed_e"]) > 19
            c = int(abs_hit or signed18)
            d = int(abs_hit or signed19)
            lines.append(f"        check_event({code[row['dataset']]},{seed},{int(row['m_ff'])},{p},{int(row['arch0_margin'])},{int(row['m_ref'])},{a},{c},{d},0);")
    lines += [
        '        if (event_count != 690) $fatal(1,"P4 event count mismatch got=%0d",event_count);',
        '        if (healthy_a0 != 1 || healthy_b0 != 1 || healthy_a18 != 0 || healthy_b18 != 0) $fatal(1,"P4 healthy mismatch a0=%0d b0=%0d a18=%0d b18=%0d",healthy_a0,healthy_b0,healthy_a18,healthy_b18);',
        '        if (d01_a18 != 30 || d01_b18 != 30 || d02_a18 != 30 || d02_b18 != 30 || d04_a18 != 30 || d04_b18 != 30) $fatal(1,"P4 coverage mismatch");',
        '        $fclose(fd);',
        '        $display("BFE13_TRACK0_P4_SIGN0_EQUIVALENCE_PASS");',
        '        $finish;',
        '    end',
        'endmodule',
        '`default_nettype wire',
        '',
    ]
    return "\n".join(lines)


def main():
    output = HERE / "tb_bfe13_track0_retained_ab.sv"
    output.write_text(render(), encoding="ascii")
    print(output)


if __name__ == "__main__":
    main()
