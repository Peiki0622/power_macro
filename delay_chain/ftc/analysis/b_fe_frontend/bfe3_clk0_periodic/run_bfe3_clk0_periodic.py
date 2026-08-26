#!/usr/bin/env python3
"""B-FE3-CLK0 periodic 50 MHz raw-XOR wave-packet audit.

The electrical topology is the frozen B-FE1 30-tap 4/0 RVT/LVT front-end.
Only the S_CLK source and transient stop time are changed.  XOR outputs are
threshold-restored with the frozen Level-0 rule and analyzed per system-clock
edge.  No latch timing, RTL, calibration, lookup table, or fault decision is
introduced by this stage.
"""

import csv
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FTC_ROOT = ROOT.parents[2]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import bfe1_frontend  # noqa: E402
import run_dc_sweep  # noqa: E402

TAPS = 30
VDD = 0.95
HALF_PERIOD_PS = 10000.0
PERIOD_PS = 20000.0
FIRST_EDGE_PS = 1000.0
STOP_PS = 81000.0
TRAN_STEP_S = 1.0e-12
TIMING_TOL_PS = 5.0
EDGE_COUNT = 8
RUN_ROOT = FTC_ROOT / "runs" / "b_fe_frontend" / "bfe3_clk0_periodic"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def periodic_deck(cells: dict, model_library: str) -> str:
    scenario = {"scenario_id": "BFE3-CLK0-095-N", "baseline_v": VDD, "droop_v": None, "phase_ps": None}
    deck = bfe1_frontend.render_deck(cells, scenario, model_library)
    deck = re.sub(
        r"V_SCLK s_clk vss_a PWL\([^\n]+",
        "V_SCLK s_clk vss_a PULSE(0 'VDD_VALUE' 1.0e-9 1.0e-12 1.0e-12 1.0e-8 2.0e-8)",
        deck,
    )
    deck = deck.replace(
        "* S_CLK port: one 1-ps rising edge at 1 ns, then a constant high level through STOP_S.",
        "* CLK_SYS_MON: 50 MHz, 50% duty, 10 ns high and 10 ns low.",
    )
    deck = re.sub(r"\.tran\s+[^\s]+\s+[^\s]+", ".tran {:.12e} {:.12e}".format(TRAN_STEP_S, STOP_PS * 1.0e-12), deck)
    return deck


def threshold_events(trace: dict, tap: int) -> tuple:
    times = trace["columns"]["time"]
    xor = trace["columns"][bfe1_frontend.label_for("xor_{}".format(tap))]
    rail = trace["columns"][bfe1_frontend.label_for("vdd_monitored")]
    delta = [x - 0.5 * r for x, r in zip(xor, rail)]
    state = 1 if delta[0] > 0.0 else 0
    events = []
    for index in range(1, len(delta)):
        left, right = delta[index - 1], delta[index]
        if left == 0.0:
            left = -1.0e-30 if state == 0 else 1.0e-30
        if right == 0.0 or left * right < 0.0:
            if right == left:
                continue
            crossing = times[index - 1] + (-left / (right - left)) * (times[index] - times[index - 1])
            new_state = 1 if right > left else 0
            if new_state != state:
                events.append((crossing, tap, new_state, "rise" if new_state else "fall"))
                state = new_state
    return state, events


def build_segments(trace: dict) -> tuple:
    initial = []
    events = []
    for tap in range(TAPS):
        state, tap_events = threshold_events(trace, tap)
        initial.append(state)
        events.extend(tap_events)
    events.sort(key=lambda item: item[0])
    grouped = []
    for event in events:
        if grouped and abs(event[0] - grouped[-1][0][0]) < 1.0e-18:
            grouped[-1].append(event)
        else:
            grouped.append([event])
    state = list(initial)
    segments = []
    previous = trace["columns"]["time"][0]
    for group in grouped:
        time_s = group[0][0]
        if time_s > previous:
            segments.append((previous, time_s, tuple(state)))
        for _, tap, new_state, _ in group:
            state[tap] = new_state
        previous = time_s
    final_time = trace["columns"]["time"][-1]
    if final_time > previous:
        segments.append((previous, final_time, tuple(state)))
    return initial, events, segments


def packets(segments: list) -> list:
    result = []
    start = None
    for begin, end, bits in segments:
        active = any(bits)
        if active and start is None:
            start = begin
        if not active and start is not None:
            result.append((start, begin))
            start = None
    if start is not None:
        result.append((start, segments[-1][1]))
    return result


def edge_schedule(trace: dict) -> list:
    """Extract absolute CLK_SYS_MON threshold crossings from the retained trace."""

    crossings = bfe1_frontend.crossing_times(trace, "s_clk", "vdd_monitored")
    events = [(time, "rise") for time in crossings["rise_ps"]] + [(time, "fall") for time in crossings["fall_ps"]]
    events.sort(key=lambda item: item[0])
    deduped = []
    for time, polarity in events:
        if deduped and polarity == deduped[-1][1] and abs(time - deduped[-1][0]) < 2.0:
            continue
        deduped.append((time, polarity))
    return [{"edge_index": index, "edge_time_ps": time, "polarity": polarity} for index, (time, polarity) in enumerate(deduped)]


def code_for_packet(packet: tuple, segments: list) -> dict:
    start_s, end_s = packet
    candidates = []
    for begin, end, bits in segments:
        overlap_start, overlap_end = max(begin, start_s), min(end, end_s)
        if overlap_end <= overlap_start:
            continue
        width_ps = (overlap_end - overlap_start) * 1.0e12
        n = sum(bits)
        candidates.append((n, width_ps, -abs((overlap_start + overlap_end) / 2.0 - (start_s + end_s) / 2.0), bits))
    if not candidates:
        raise ValueError("packet has no threshold-resolved spatial segment")
    _, _, _, bits = max(candidates)
    return {
        "q_raw_tap0_to_tap29": "".join(str(bit) for bit in bits),
        "q_raw_29_to_0": "".join(str(bit) for bit in reversed(bits)),
        "N": sum(bits),
        "M": sum(index * bit for index, bit in enumerate(bits)),
        "T": sum(bits[index] ^ bits[index - 1] for index in range(1, TAPS)),
    }


def analyze_edges(trace: dict) -> tuple:
    _, events, segments = build_segments(trace)
    active_packets = packets(segments)
    schedule = edge_schedule(trace)
    if len(active_packets) != len(schedule):
        raise ValueError("expected {} independent XOR packets, found {}".format(len(schedule), len(active_packets)))
    rows = []
    for edge, packet in zip(schedule, active_packets):
        start_s, end_s = packet
        start_ps, end_ps = start_s * 1.0e12, end_s * 1.0e12
        feature = code_for_packet(packet, segments)
        packet_events = [event for event in events if start_s <= event[0] <= end_s]
        rise_by_tap = [None] * TAPS
        fall_by_tap = [None] * TAPS
        for event_time, tap, new_state, _direction in packet_events:
            if new_state:
                rise_by_tap[tap] = event_time * 1.0e12
            else:
                fall_by_tap[tap] = event_time * 1.0e12
        row = {
            **edge,
            "packet_start_ps": start_ps,
            "packet_end_ps": end_ps,
            "packet_width_ps": end_ps - start_ps,
            "packet_center_ps": 0.5 * (start_ps + end_ps),
            "packet_before_edge_ps": start_ps - edge["edge_time_ps"],
            "packet_after_edge_ps": end_ps - edge["edge_time_ps"],
            "raw_event_count": len(packet_events),
            "xor_rise_crossing_ps_by_tap": rise_by_tap,
            "xor_fall_crossing_ps_by_tap": fall_by_tap,
            **feature,
        }
        rows.append(row)
    for index, row in enumerate(rows):
        next_row = rows[index + 1] if index + 1 < len(rows) else None
        if next_row is None:
            row["overlaps_adjacent_packet"] = False
            row["recovery_complete_before_next_edge"] = True
            row["idle_at_half_cycle_end"] = True
            row["inter_packet_idle_ps"] = None
        else:
            row["overlaps_adjacent_packet"] = row["packet_end_ps"] > next_row["packet_start_ps"]
            row["recovery_complete_before_next_edge"] = row["packet_end_ps"] < next_row["edge_time_ps"]
            row["idle_at_half_cycle_end"] = row["packet_end_ps"] < next_row["edge_time_ps"] and not row["overlaps_adjacent_packet"]
            row["inter_packet_idle_ps"] = next_row["packet_start_ps"] - row["packet_end_ps"]
    return rows, events, segments


def consistency(rows: list, polarity: str) -> dict:
    group = [row for row in rows if row["polarity"] == polarity]
    def span(key, relative=False):
        values = [float(row[key]) - (float(row["edge_time_ps"]) if relative else 0.0) for row in group]
        return max(values) - min(values)
    codes = sorted(set(row["q_raw_tap0_to_tap29"] for row in group))
    return {
        "count": len(group),
        "raw_codes": codes,
        "M_values": sorted(set(row["M"] for row in group)),
        "packet_start_span_ps": span("packet_start_ps", relative=True),
        "packet_end_span_ps": span("packet_end_ps", relative=True),
        "packet_width_span_ps": span("packet_width_ps"),
        "consistent_raw_code": len(codes) == 1,
        "consistent_M": len(set(row["M"] for row in group)) == 1,
        "consistent_position_width": span("packet_start_ps", relative=True) <= TIMING_TOL_PS and span("packet_end_ps", relative=True) <= TIMING_TOL_PS and span("packet_width_ps") <= TIMING_TOL_PS,
    }


def publish(rows: list, trace_path: Path, deck_path: Path, hspice_version: str, events: list) -> int:
    rise = consistency(rows, "rise")
    fall = consistency(rows, "fall")
    overlap_free = all(not row["overlaps_adjacent_packet"] for row in rows)
    recovered = all(row["recovery_complete_before_next_edge"] and row["idle_at_half_cycle_end"] for row in rows)
    complete = len(rows) >= 6 and all(row["raw_event_count"] > 0 for row in rows)
    packet_consistent = all(group["consistent_raw_code"] and group["consistent_M"] and group["consistent_position_width"] for group in (rise, fall))
    rise_m = sorted(set(row["M"] for row in rows if row["polarity"] == "rise"))
    fall_m = sorted(set(row["M"] for row in rows if row["polarity"] == "fall"))
    m_difference = rise_m != fall_m
    gate = "BFE3_CLK0_50MHZ_PERIODIC_FRONTEND_PASS" if complete and packet_consistent and overlap_free and recovered else "BFE3_CLK0_50MHZ_PERIODIC_FRONTEND_FAIL"
    for row in rows:
        stem = "edge_{:03d}_{}".format(row["edge_index"], row["polarity"])
        with (ROOT / (stem + ".csv")).open("w", newline="", encoding="ascii") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(row), lineterminator="\n")
            writer.writeheader()
            writer.writerow(row)
        (ROOT / (stem + ".json")).write_text(json.dumps(row, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    aggregate = ROOT / "BFE3_CLK0_EDGE_SAMPLES.csv"
    with aggregate.open("w", newline="", encoding="ascii") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    manifest = {
        "schema_version": 1, "stage": "B-FE3-CLK0", "gate": gate,
        "verification_mode": "HSPICE W-2024.09 transistor-level periodic raw XOR + Level-0 threshold restoration",
        "simulation_run": True, "new_hspice_scenarios": 1, "hspice_version": hspice_version,
        "clock": {"name": "CLK_SYS_MON", "frequency_mhz": 50.0, "period_ns": 20.0, "high_ns": 10.0, "low_ns": 10.0, "first_edge_ps": FIRST_EDGE_PS, "edge_count": len(rows), "stop_ps": STOP_PS},
        "sensing_geometry": {"rvt_prefix": 4, "lvt_prefix": 0, "tap_count": TAPS, "xor_cell": bfe1_frontend.XOR_CELL},
        "vdd_monitored_v": VDD, "level0_restoration": "q[i]=1 iff XOR_i > 0.5*VDD_MONITORED",
        "safe_domain_latch_cell_frozen": "LATQ_X0P5M_A9TR40", "real_latch_instantiated_in_this_wavepacket_audit": False,
        "raw_code_definition": "q[i] is the threshold-restored XOR spatial code at the widest packet segment; M=sum(i*q[i])",
        "forbidden": ["CLK_PROBE", "RTL", "self_calibration", "fault_decision", "lookup_table", "multi_feature_fusion", "frequency_scan", "duty_cycle_scan", "phase_scan"],
        "deck_sha256": sha256(deck_path), "trace_sha256": sha256(trace_path), "edge_csv_sha256": sha256(aggregate),
        "edge_files": ["edge_{:03d}_{}.csv".format(row["edge_index"], row["polarity"]) for row in rows],
        "threshold_event_count": len(events), "stop_after_stage": True, "next_stage_authorized": False,
    }
    manifest_path = ROOT / "BFE3_CLK0_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    analysis = {"schema_version": 1, "stage": "B-FE3-CLK0", "gate": gate, "rows": rows, "rise_consistency": rise, "fall_consistency": fall, "rise_M_values": rise_m, "fall_M_values": fall_m, "rise_fall_M_systematic_difference": m_difference, "baseline_recommendation": "separate M_RISE/M_FALL baselines" if m_difference else "a common M baseline remains plausible", "all_packets_nonoverlap": overlap_free, "all_half_cycle_recovery_complete": recovered, "manifest_sha256": sha256(manifest_path), "stop_after_stage": True, "next_stage_authorized": False}
    analysis_path = ROOT / "BFE3_CLK0_ANALYSIS.json"
    analysis_path.write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = ["# B-FE3-CLK0 periodic frontend audit", "", "Gate: `{}`".format(gate), "", "Frozen 0.95 V normal condition with 50 MHz / 50% `CLK_SYS_MON` (20 ns period, 10 ns high and 10 ns low). The 30-tap 4/0 RVT/LVT geometry and real `XOR2_X0P5M_A9TL40` loads are unchanged.", "", "| Edge | Time (ps) | Polarity | Raw code [29:0] | M | Packet start (ps) | Packet end (ps) | Width (ps) | Overlap | Recovery |", "|---:|---:|---|---|---:|---:|---:|---:|---|---|"]
    for row in rows:
        report.append("| {} | {:.3f} | {} | `{}` | {} | {:.3f} | {:.3f} | {:.3f} | {} | {} |".format(row["edge_index"], row["edge_time_ps"], row["polarity"], row["q_raw_29_to_0"], row["M"], row["packet_start_ps"], row["packet_end_ps"], row["packet_width_ps"], row["overlaps_adjacent_packet"], row["recovery_complete_before_next_edge"]))
    report += ["", "Rise consistency: code={}, M={}, start span={:.3f} ps, end span={:.3f} ps, width span={:.3f} ps.".format(rise["consistent_raw_code"], rise["consistent_M"], rise["packet_start_span_ps"], rise["packet_end_span_ps"], rise["packet_width_span_ps"]), "Fall consistency: code={}, M={}, start span={:.3f} ps, end span={:.3f} ps, width span={:.3f} ps.".format(fall["consistent_raw_code"], fall["consistent_M"], fall["packet_start_span_ps"], fall["packet_end_span_ps"], fall["packet_width_span_ps"]), "Rise M values: `{}`; fall M values: `{}`.".format(rise_m, fall_m), "Recommendation: **{}**.".format("establish separate M_RISE/M_FALL baselines" if m_difference else "a common M baseline remains plausible"), "", "This stage stops here. No CLK_PROBE, glitch detection, frequency/duty/phase scan, RTL, calibration, fault decision, lookup table, or multi-feature fusion was added."]
    report_path = ROOT / "BFE3_CLK0_REPORT.md"
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    gate_path = ROOT / "BFE3_CLK0_GATE.json"
    gate_path.write_text(json.dumps({"stage": "B-FE3-CLK0", "gate": gate, "analysis_sha256": sha256(analysis_path), "report_sha256": sha256(report_path), "all_packets_nonoverlap": overlap_free, "all_half_cycle_recovery_complete": recovered, "rise_consistency": rise, "fall_consistency": fall, "stop_after_stage": True, "next_stage_authorized": False}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if gate.endswith("PASS") else 1


def main() -> int:
    config = load_json(FTC_ROOT / "ftc_config.json")
    cells = load_json(FTC_ROOT / "discovery" / "selected_cells.json")
    hspice = Path(config["hspice"])
    version = run_dc_sweep.hspice_version(hspice)
    if str(config["expected_hspice_version"]) not in version:
        raise RuntimeError("unexpected HSPICE version: {}".format(version))
    if RUN_ROOT.exists():
        raise FileExistsError("refusing to overwrite periodic run root: {}".format(RUN_ROOT))
    RUN_ROOT.mkdir(parents=True)
    run_dir = RUN_ROOT / "normal_0p95"
    run_dir.mkdir()
    shutil.copyfile(FTC_ROOT / "spice" / "empty_subckt.sp_cal", run_dir / "empty_subckt.sp_cal")
    deck_path = run_dir / "bfe3_clk0_periodic.sp"
    deck_path.write_text(periodic_deck(cells, str(config["model_library"])), encoding="ascii")
    result = subprocess.run([str(hspice), deck_path.name, "-o", "bfe3_clk0_periodic"], cwd=str(run_dir), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False, timeout=1200)
    (run_dir / "hspice_command.log").write_text("returncode={}\nstdout:\n{}\nstderr:\n{}\n".format(result.returncode, result.stdout, result.stderr), encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError("periodic HSPICE failed")
    run_dc_sweep.validate_listing(run_dir / "bfe3_clk0_periodic.lis")
    trace_path = run_dir / "bfe3_clk0_periodic.tr0"
    trace = bfe1_frontend.parse_ascii_tr0(trace_path)
    expected = ["time", bfe1_frontend.label_for("vdd_monitored"), bfe1_frontend.label_for("s_clk")]
    expected += [bfe1_frontend.label_for("rvt_{}".format(i)) for i in range(TAPS)]
    expected += [bfe1_frontend.label_for("lvt_{}".format(i)) for i in range(TAPS)]
    expected += [bfe1_frontend.label_for("xor_{}".format(i)) for i in range(TAPS)]
    if trace["record_width"] != len(expected) or any(label not in trace["columns"] for label in expected):
        raise ValueError("periodic trace does not retain TIME plus 92 required probes")
    rows, events, _ = analyze_edges(trace)
    return publish(rows, trace_path, deck_path, version, events)


if __name__ == "__main__":
    raise SystemExit(main())
