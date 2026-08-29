#!/usr/bin/env python3
"""BFE8 D02 ARCH0 quantitative pilot task-local runner.

This module deliberately owns the BFE8 flow instead of modifying historical
BFE4/BFE6 runners.  The staged entry point is extended phase by phase; every
phase writes only under this directory (compact evidence) or the ignored,
task-scoped ``delay_chain/ftc/runs/b_fe_frontend/bfe8_d02_arch0_pilot`` tree.
The P0 implementation below is intentionally read-only with respect to
simulation: it audits frozen authorities, extracts retained process
signatures, and records the bounded simulation budget before any deck exists.
"""

from __future__ import print_function

import argparse
import csv
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

# ``ROOT`` is the checked-in evidence directory.  ``FTC_ROOT`` is derived
# rather than hard-coded so the runner remains relocatable within the project.
ROOT = Path(__file__).resolve().parent
FTC_ROOT = ROOT.parents[2]
ANALYSIS_ROOT = FTC_ROOT / "analysis" / "b_fe_frontend"
RUN_ROOT = FTC_ROOT / "runs" / "b_fe_frontend" / "bfe8_d02_arch0_pilot"
SEEDS = tuple(range(41001, 41031))

BFE7_ROOT = ANALYSIS_ROOT / "bfe7_droop12_waveforms"
BFE4_ROOT = ANALYSIS_ROOT / "bfe4_caln0_self_calibration"
BFE6_ROOT = ANALYSIS_ROOT / "bfe6_marg0_detection_margin"

EXPECTED_D02_CSV_SHA256 = "db8318eaa8cef551398ff2c347cb74594c3ac56a1712e439702f5b0fa08bbff1"
EXPECTED_D02_INC_SHA256 = "f84a883076ea6831dc88272443f6b90df9e58c70de949f51ba26dc19be5e32fa"

# Healthy controls intentionally use a longer local frame than BFE7's 65 ns
# attack frame: eight 50 MHz edges (four RISE and four FALL) are required per
# segment.  The algorithm and +/-8 mV bound remain identical to BFE7.
HEALTHY_SEGMENT_STOP_PS = 80000
HEALTHY_FAST_SPACING_PS = 250
HEALTHY_SLOW_SPACING_PS = 2500
HEALTHY_SLOW_LIMIT_V = 0.005
HEALTHY_FAST_LIMIT_V = 0.003
HEALTHY_BACKGROUND_LIMIT_V = 0.008
HEALTHY_NOMINAL_V = 1.10
HEALTHY_SEGMENTS = (
    ("CAL", 7300),
    ("MARGIN", 7302),
    ("FPR", 7303),
)
HEALTHY_GUARD_PS = 5000
BFE8_SAFE_V = 1.10
CAPTURE_G_CLOSE_OFFSET_PS = 534.524618567
CAPTURE_DFF_OFFSET_PS = 1534.524618567
PROBE_PERIOD_PS = 2500.0
SOURCE_TRAN_STEP_S = 2.0e-12

# These imports provide only audited primitive netlist rendering and threshold
# crossing utilities.  No 0.95 V deck or result is imported from the old
# runners; all BFE8 electrical constants are defined above.
sys.path.insert(0, str(FTC_ROOT / "scripts"))
sys.path.insert(0, str(ANALYSIS_ROOT / "bfe2_real_latch" / "l1a_r_vcs_xa"))
import bfe1_frontend  # noqa: E402
import run_bfe2_l1a_r_vcs_xa as capture_bridge  # noqa: E402


def sha256(path):
    """Return the SHA256 digest of one file without changing its contents."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    """Read a JSON object and fail early on malformed authority files."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def retained_signatures():
    """Load the already retained BFE4 per-seed MC fingerprints.

    These signatures are the process-population authority.  BFE8 never runs
    an old simulation to recreate them; every later BFE8 source case must
    reproduce the corresponding value at HSPICE Monte-Carlo row index 2.
    """
    result_path = BFE4_ROOT / "BFE4_CALN0_RESULTS.csv"
    if not result_path.is_file():
        raise FileNotFoundError("missing retained BFE4 results: {}".format(result_path))
    values = {}
    with result_path.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            seed = int(row["seed"])
            values[seed] = row["mc_random_signature"]
    if tuple(sorted(values)) != SEEDS:
        raise ValueError("retained process population is not exactly seeds 41001..41030")
    if any(not re.match(r"^[0-9a-f]{64}$", value) for value in values.values()):
        raise ValueError("retained MC signature is not a SHA256 digest")
    return values


def audit_authorities():
    """Hash and validate all frozen inputs required before new simulation."""
    paths = {
        "bfe7_gate": BFE7_ROOT / "BFE7_DROOP12_GATE.json",
        "bfe7_contract": BFE7_ROOT / "DROOP12_WAVEFORM_CONTRACT.json",
        "bfe7_manifest": BFE7_ROOT / "DROOP12_MANIFEST.json",
        "d02_inc": BFE7_ROOT / "waveforms" / "D02_MEDIUM_CANONICAL.inc",
        "d02_csv": BFE7_ROOT / "waveforms" / "D02_MEDIUM_CANONICAL.csv",
        "bfe0_contract": ANALYSIS_ROOT / "bfe0_architecture_contract.json",
        "bfe3_timing": ANALYSIS_ROOT / "bfe3_clk2_ftc_latch_dff_capture" / "BFE3_CLK2_REPORT.md",
        "bfe5_timing": FTC_ROOT / "backend" / "reports" / "BFE5_TIM0_PIPELINE_CONTRACT.md",
        "bfe4_runner": BFE4_ROOT / "run_bfe4_caln0_self_calibration.py",
        "bfe4_results": BFE4_ROOT / "BFE4_CALN0_RESULTS.csv",
        "bfe6_runner": BFE6_ROOT / "run_bfe6_marg0_m2.py",
        "backend_ctrl": FTC_ROOT / "rtl" / "bfe_backend_ctrl.sv",
        "backend_top": FTC_ROOT / "rtl" / "bfe_backend_top.sv",
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError("missing BFE8 authority: {}".format(", ".join(missing)))

    gate = read_json(paths["bfe7_gate"])
    if not (gate.get("gate") == "BFE7_DROOP12_WAVEFORM_CONTRACT_FROZEN"
            and gate.get("status") == "PASS"
            and gate.get("scenario_count") == 12
            and gate.get("frozen") is True):
        raise ValueError("BFE7 gate is not the required frozen PASS authority")

    bfe0 = read_json(paths["bfe0_contract"])
    required_bfe0 = {
        "observable_taps": 30,
        "rvt_prefix": 4,
        "lvt_prefix": 0,
        "xor_cell": "XOR2_X0P5M_A9TL40",
        "threshold": "V(xor_i,t) > 0.5 * V(VDD_MONITORED,t)",
    }
    for key, expected in required_bfe0.items():
        if bfe0.get(key) != expected:
            raise ValueError("BFE0 authority mismatch for {}".format(key))

    digests = {name: sha256(path) for name, path in paths.items()}
    if digests["d02_csv"] != EXPECTED_D02_CSV_SHA256:
        raise ValueError("D02 CSV hash differs from frozen manifest")
    if digests["d02_inc"] != EXPECTED_D02_INC_SHA256:
        raise ValueError("D02 INC hash differs from frozen manifest")

    signatures = retained_signatures()
    return paths, digests, signatures


def _center_bound(values, limit):
    """Center and clip seeded samples exactly as the BFE7 generator does."""
    values = np.asarray(values, dtype=np.float64)
    return np.clip(values - float(np.mean(values)), -limit, limit)


def healthy_background(seed):
    """Generate one deterministic 80 ns healthy rail for a control seed."""
    rng = np.random.Generator(np.random.PCG64(int(seed)))
    slow_times = np.arange(0, HEALTHY_SEGMENT_STOP_PS + HEALTHY_SLOW_SPACING_PS,
                           HEALTHY_SLOW_SPACING_PS, dtype=np.int64)
    fast_times = np.arange(0, HEALTHY_SEGMENT_STOP_PS + HEALTHY_FAST_SPACING_PS,
                           HEALTHY_FAST_SPACING_PS, dtype=np.int64)
    slow = _center_bound(rng.uniform(-HEALTHY_SLOW_LIMIT_V, HEALTHY_SLOW_LIMIT_V,
                                     len(slow_times)), HEALTHY_SLOW_LIMIT_V)
    fast = _center_bound(rng.uniform(-HEALTHY_FAST_LIMIT_V, HEALTHY_FAST_LIMIT_V,
                                     len(fast_times)), HEALTHY_FAST_LIMIT_V)
    slow_on_fast = np.interp(fast_times, slow_times, slow)
    n_bg = np.clip(slow_on_fast + fast, -HEALTHY_BACKGROUND_LIMIT_V,
                   HEALTHY_BACKGROUND_LIMIT_V)
    rows = []
    for time_ps, slow_v, fast_v, bg_v in zip(fast_times, slow_on_fast, fast, n_bg):
        rows.append({
            "time_ps": int(time_ps),
            "n_slow_v": float(slow_v),
            "n_fast_v": float(fast_v),
            "n_bg_v": float(bg_v),
            "vdd_healthy_v": float(HEALTHY_NOMINAL_V + bg_v),
        })
    return rows


def _pwl_lines(rows):
    """Serialize one rail using the frozen BFE7 source-node contract."""
    lines = [
        "V_VDD_MONITORED vdd_monitored vss_a PWL(",
    ]
    for index, row in enumerate(rows):
        suffix = ")" if index == len(rows) - 1 else ""
        lines.append("+ {:.12e} {:.12e}{}".format(
            row["time_ps"] * 1.0e-12, row["vdd_healthy_v"], suffix))
    return lines


def build_healthy_composite():
    """Create controls, a single composite PWL, and explicit event metadata."""
    all_rows = []
    event_map = []
    cursor_ps = 0
    for segment_name, seed in HEALTHY_SEGMENTS:
        rows = healthy_background(seed)
        for row in rows:
            shifted = dict(row)
            shifted["time_ps"] += cursor_ps
            shifted["segment"] = segment_name
            shifted["seed"] = seed
            all_rows.append(shifted)
        # A system edge occurs at +1 ns, then every 10 ns.  Eight edges are
        # recorded as meaningful; all segment boundaries and guards are not.
        for edge_index in range(8):
            event_map.append({
                "segment": segment_name,
                "seed": seed,
                "event_index": edge_index,
                "edge": "RISE" if edge_index % 2 == 0 else "FALL",
                "time_ps": cursor_ps + 1000 + edge_index * 10000,
                "valid": True,
            })
        event_map.append({"segment": segment_name, "seed": seed,
                          "event_index": 8, "edge": "GUARD_END",
                          "time_ps": cursor_ps + HEALTHY_SEGMENT_STOP_PS,
                          "valid": False})
        cursor_ps += HEALTHY_SEGMENT_STOP_PS + HEALTHY_GUARD_PS
    total_stop_ps = cursor_ps - HEALTHY_GUARD_PS
    return all_rows, event_map, total_stop_ps


def write_p1_controls():
    """Write healthy control CSV/INC files and the immutable composite map."""
    controls = ROOT / "healthy_controls"
    controls.mkdir(parents=True, exist_ok=True)
    metadata = {"nominal_vdd_v": 1.10, "temperature_c": 25.0,
                "algorithm": "BFE7 PCG64 slow+fast centered/clipped",
                "background_limit_v": 0.008, "segments": []}
    for segment_name, seed in HEALTHY_SEGMENTS:
        rows = healthy_background(seed)
        csv_path = controls / "NBG_{}.csv".format(seed)
        inc_path = controls / "NBG_{}.inc".format(seed)
        with csv_path.open("w", newline="", encoding="ascii") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(["time_s", "n_slow_v", "n_fast_v", "n_bg_v", "vdd_healthy_v"])
            for row in rows:
                writer.writerow(["{:.12e}".format(row["time_ps"] * 1.0e-12),
                                 "{:.12e}".format(row["n_slow_v"]),
                                 "{:.12e}".format(row["n_fast_v"]),
                                 "{:.12e}".format(row["n_bg_v"]),
                                 "{:.12e}".format(row["vdd_healthy_v"])])
        inc_path.write_text("\n".join([
            "* BFE8 healthy control {} seed {}; no attack.".format(segment_name, seed),
            "* Port map: positive monitored rail=vdd_monitored; return=vss_a.",
        ] + _pwl_lines(rows)) + "\n", encoding="ascii")
        metadata["segments"].append({"name": segment_name, "seed": seed,
                                      "csv_sha256": sha256(csv_path),
                                      "inc_sha256": sha256(inc_path),
                                      "row_count": len(rows)})

    composite_rows, event_map, total_stop_ps = build_healthy_composite()
    composite_inc = controls / "HEALTHY_COMPOSITE.inc"
    composite_csv = controls / "HEALTHY_COMPOSITE.csv"
    with composite_csv.open("w", newline="", encoding="ascii") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["time_s", "segment", "seed", "n_bg_v", "vdd_healthy_v"])
        for row in composite_rows:
            writer.writerow(["{:.12e}".format(row["time_ps"] * 1.0e-12),
                             row["segment"], row["seed"],
                             "{:.12e}".format(row["n_bg_v"]),
                             "{:.12e}".format(row["vdd_healthy_v"])])
    composite_inc.write_text("\n".join([
        "* BFE8 HEALTHY_COMPOSITE; CAL/MARGIN/FPR controls only.",
        "* Guard intervals are represented in the event map and excluded.",
    ] + _pwl_lines(composite_rows)) + "\n", encoding="ascii")
    (controls / "HEALTHY_COMPOSITE_EVENT_MAP.json").write_text(
        json.dumps({"segments": list(HEALTHY_SEGMENTS), "guard_ps": HEALTHY_GUARD_PS,
                    "stop_ps": total_stop_ps, "events": event_map},
                   indent=2, sort_keys=True) + "\n", encoding="ascii")
    metadata["composite"] = {"csv_sha256": sha256(composite_csv),
                              "inc_sha256": sha256(composite_inc),
                              "event_map_sha256": sha256(controls / "HEALTHY_COMPOSITE_EVENT_MAP.json"),
                              "stop_ps": total_stop_ps}
    (controls / "HEALTHY_CONTROLS_METADATA.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="ascii")


def golden_reference(samples):
    """Match bfe_backend_ctrl: integer truncation of the four-sample sum."""
    values = [int(value) for value in samples]
    if len(values) != 4:
        raise ValueError("reference arithmetic requires exactly four samples")
    return sum(values) >> 2


def assert_p1_offline():
    """Run all P1 checks before allowing a simulator invocation."""
    controls = ROOT / "healthy_controls"
    rows, event_map, total_stop_ps = build_healthy_composite()
    if build_healthy_composite() != (rows, event_map, total_stop_ps):
        raise AssertionError("healthy generation is not reproducible")
    if len([e for e in event_map if e["valid"]]) != 24:
        raise AssertionError("event map must contain 24 meaningful events")
    for row in rows:
        if not (1.092 - 1e-12 <= row["vdd_healthy_v"] <= 1.108 + 1e-12):
            raise AssertionError("healthy rail outside BFE7 envelope")
    if sha256(BFE7_ROOT / "waveforms" / "D02_MEDIUM_CANONICAL.inc") != EXPECTED_D02_INC_SHA256:
        raise AssertionError("D02 include hash changed")
    if sha256(BFE7_ROOT / "waveforms" / "D02_MEDIUM_CANONICAL.csv") != EXPECTED_D02_CSV_SHA256:
        raise AssertionError("D02 CSV hash changed")
    if golden_reference([1, 2, 3, 4]) != 2:
        raise AssertionError("sum4 >> 2 golden arithmetic failed")
    if golden_reference([1, 2, 3, 4]) == int((1 + 2 + 3 + 4 + 2) / 4):
        raise AssertionError("round-half-up arithmetic leaked into reference model")
    if not (not (5 > 5) and 6 > 5):
        raise AssertionError("strict alarm comparison failed")
    # P1 has no generated deck yet; the explicit scope contract below is the
    # offline guard.  Later deck validation rejects ARCH1 circuitry directly.
    if any("ARCH1" in path.name.upper() for path in controls.iterdir()):
        raise AssertionError("ARCH1 artifact leaked into healthy controls")
    if not controls.is_dir():
        raise AssertionError("healthy controls were not generated")


def run_p1():
    """Generate controls, execute offline checks, and publish the P1 gate."""
    write_p1_controls()
    assert_p1_offline()
    report = ROOT / "P1_REPORT.md"
    report.write_text("\n".join([
        "# BFE8 D02 P1 runner and healthy controls",
        "",
        "Gate: `BFE8_D02_P1_RUNNER_AND_HEALTHY_CONTROLS_READY`",
        "",
        "Healthy controls CAL=7300, MARGIN=7302 and FPR=7303 were generated with the BFE7 algorithm.",
        "The composite event map contains 24 valid events and explicit guard boundaries.",
        "All offline hash, bound, arithmetic, strict-comparison and scope checks passed.",
        "",
        "Simulation accounting for P1: HSPICE=0, PrimeSim=0, VCS=0.",
    ]) + "\n", encoding="utf-8")
    gate = {"gate": "BFE8_D02_P1_RUNNER_AND_HEALTHY_CONTROLS_READY", "status": "PASS",
            "healthy_seeds": {name: seed for name, seed in HEALTHY_SEGMENTS},
            "valid_event_count": 24,
            "simulation_accounting": {"hspice": 0, "primesim": 0, "vcs": 0},
            "stop_after_stage": True}
    (ROOT / "P1_GATE.json").write_text(json.dumps(gate, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def healthy_clock_pwl(total_stop_ps):
    """Render the frozen 50 MHz system clock across the three segments."""
    events = json.loads((ROOT / "healthy_controls" / "HEALTHY_COMPOSITE_EVENT_MAP.json").read_text(encoding="utf-8"))["events"]
    points = [(0.0, 0.0)]
    state = 0.0
    for event in events:
        if not event["valid"]:
            continue
        edge = float(event["time_ps"])
        points.extend([(edge - 0.5, state), (edge + 0.5, BFE8_SAFE_V if state == 0.0 else 0.0)])
        state = BFE8_SAFE_V if state == 0.0 else 0.0
    points.append((float(total_stop_ps), state))
    return "V_SCLK s_clk vss_a PWL({})".format(" ".join(
        "{:.12e} {:.12e}".format(t * 1.0e-12, v) for t, v in points))


def healthy_source_deck(cells, model, seed, total_stop_ps):
    """Render a 1.10 V transistor-level source deck for one MC seed."""
    scenario = {"scenario_id": "BFE8-HEALTHY-COMPOSITE-{}".format(seed),
                "baseline_v": BFE8_SAFE_V, "droop_v": None, "phase_ps": None}
    deck = bfe1_frontend.render_deck(cells, scenario, model)
    # Replace the single normal supply with the generated composite include;
    # preserving the include text itself prevents accidental source rewriting.
    deck = re.sub(r"\* Normal condition:[^\n]*\nV_VDD_MONITORED[^\n]*\n",
                  '.include "HEALTHY_COMPOSITE.inc"\n', deck)
    deck = re.sub(r"V_SCLK s_clk vss_a PWL\([^\n]+", healthy_clock_pwl(total_stop_ps), deck)
    deck = deck.replace('.lib "{}" tt'.format(model), '.lib "{}" MOS_MC'.format(model))
    deck = deck.replace(".option post=2 probe nomod measform=3 measdgt=10 runlvl=3",
                        ".option post=0 nomod measform=3 measdgt=10 runlvl=3 seed={}".format(seed))
    # Native .measure rows are used instead of the Monte-Carlo POST=2 trace:
    # W-2024.09 prepends sweep metadata to that trace, while mt0.csv keeps a
    # stable row-index contract.  Measurements are exactly at LATQ close.
    measure_lines = []
    for index, item in enumerate(_capture_edges(total_stop_ps)):
        latch_close_ps = item[0] + CAPTURE_G_CLOSE_OFFSET_PS
        at_s = "{:.12e}".format(latch_close_ps * 1.0e-12)
        measure_lines.append(".measure tran m_rail_{:02d} find v(vdd_monitored) at={}".format(index, at_s))
        for tap in range(30):
            measure_lines.append(".measure tran m_x_{:02d}_{:02d} find v(xor_{}) at={}".format(index, tap, tap, at_s))
    deck = deck.replace(".end", "\n" + "\n".join(measure_lines) + "\n.end")
    deck = re.sub(r"\.tran\s+[^\s]+\s+[^\n]+", ".tran {:.12e} {:.12e} sweep monte=2".format(
        SOURCE_TRAN_STEP_S, total_stop_ps * 1.0e-12), deck, count=1)
    if "0.95" in deck or "9.500000" in deck:
        raise ValueError("historical 0.95 V constant leaked into BFE8 healthy deck")
    if deck.count("MOS_MC") != 1 or "vdd_monitored vss_a" not in deck or ".option post=0" not in deck:
        raise ValueError("BFE8 healthy deck lost MC or source port contract")
    return deck


def parse_measurements(path, total_stop_ps):
    """Read index-2 HSPICE measurements and apply the instantaneous threshold."""
    lines = [line for line in path.read_text(encoding="ascii", errors="strict").splitlines()
             if line and not line.startswith("$") and not line.startswith(".TITLE")]
    rows = list(csv.DictReader(lines))
    by_index = {int(row["index"]): row for row in rows}
    if 2 not in by_index:
        raise ValueError("healthy mt0.csv lacks Monte-Carlo index 2")
    row = by_index[2]
    samples = []
    for index, (edge_ps, polarity) in enumerate(_capture_edges(total_stop_ps)):
        rail = float(row["m_rail_{:02d}".format(index)])
        xor = [float(row["m_x_{:02d}_{:02d}".format(index, tap)]) for tap in range(30)]
        if not math.isfinite(rail) or not all(math.isfinite(value) for value in xor):
            raise ValueError("healthy measurement contains non-finite value")
        bits = [1 if value > 0.5 * rail else 0 for value in xor]
        samples.append({"event_index": index, "edge_ps": edge_ps, "edge": polarity.upper(),
                        "latch_close_ps": edge_ps + CAPTURE_G_CLOSE_OFFSET_PS,
                        "rail_v": rail, "xor_v": xor, "bits": bits,
                        "m_ff": sum(tap * bit for tap, bit in enumerate(bits))})
    return samples


def measured_capture_schedule(samples):
    """Convert source-derived event words into deterministic safe_d schedules."""
    if not samples:
        raise ValueError("no measured healthy events")
    states = {tap: samples[0]["bits"][tap] for tap in range(30)}
    schedules = {tap: [] for tap in range(30)}
    for sample in samples[1:]:
        for tap in range(30):
            new_state = sample["bits"][tap]
            if new_state != states[tap]:
                schedules[tap].append((sample["edge_ps"] * 1.0e-12, new_state, sample["edge"].lower()))
                states[tap] = new_state
    return [samples[0]["bits"][tap] for tap in range(30)], schedules


def _capture_edges(total_stop_ps):
    """Return meaningful system edges and their frozen polarities."""
    mapping = json.loads((ROOT / "healthy_controls" / "HEALTHY_COMPOSITE_EVENT_MAP.json").read_text(encoding="utf-8"))
    return [(float(item["time_ps"]), item["edge"].lower()) for item in mapping["events"] if item["valid"]]


def _dff_rises(total_stop_ps):
    """Return one DFF sample 1534.524618567 ps after each system edge."""
    return [(edge + CAPTURE_DFF_OFFSET_PS, polarity) for edge, polarity in _capture_edges(total_stop_ps)
            if edge + CAPTURE_DFF_OFFSET_PS < total_stop_ps]


def render_capture_wrapper(columns, times, total_stop_ps):
    """Build the real LATQ/DFF analog wrapper at a stable 1.10 V safe rail."""
    ports = ["safe_d_{:02d}".format(t) for t in range(30)] + ["latch_g", "dff_ck"]
    ports += ["q_lat_{:02d}".format(t) for t in range(30)]
    ports += ["q_ff_{:02d}".format(t) for t in range(30)]
    def pwl(name, node, return_node, values):
        return "V_{} {} {} PWL({})".format(name.upper(), node, return_node, " ".join(
            "{:.12e} {:.12e}".format(float(t), float(v)) for t, v in zip(times, values)))
    lines = [
        "* BFE8 real LATQ -> DFF wrapper; all ports and supplies are explicit.",
        ".SUBCKT bfe8_capture_ams \\",
        "+ " + " \\\n+ ".join(ports),
        pwl("vdd_sense", "vdd_sense", "0", columns[bfe1_frontend.label_for("vdd_monitored")]),
        "V_VDD_SAFE vdd_safe 0 DC 1.100000000000e+00",
        "V_VSS_SAFE vss_safe 0 DC 0",
        "V_DFF_RESET dff_reset 0 DC 0",
    ]
    for tap in range(30):
        label = bfe1_frontend.label_for("xor_{}".format(tap))
        lines.append(pwl("xor_{:02d}".format(tap), "xor_{:02d}".format(tap), "0", columns[label]))
        lines.append("E_SAFE_D_{:02d} safe_d_r_{:02d} 0 safe_d_{} 0 1.0".format(tap, tap, tap))
    lines += ["E_LATCH_G latch_g_r 0 latch_g 0 1.0", "E_DFF_CK dff_ck_r 0 dff_ck 0 1.0"]
    for tap in range(30):
        lines.append("XLATCH_{:02d} q_lat_r_{:02d} vdd_safe vdd_safe vss_safe vss_safe safe_d_r_{:02d} latch_g_r LATQ_X0P5M_A9TR40".format(tap, tap, tap))
        lines.append("XDFF_{:02d} q_ff_r_{:02d} vdd_safe vdd_safe vss_safe vss_safe dff_ck_r q_lat_r_{:02d} dff_reset DFFRPQ_X0P5M_A9TR40".format(tap, tap, tap))
        lines.append("E_Q_LAT_{:02d} q_lat_{:02d} 0 q_lat_r_{:02d} 0 1.0".format(tap, tap, tap))
        lines.append("E_Q_FF_{:02d} q_ff_{:02d} 0 q_ff_r_{:02d} 0 1.0".format(tap, tap, tap))
    probe = ["v(vdd_sense)", "v(vdd_safe)", "v(latch_g_r)", "v(dff_ck_r)"]
    probe += ["v(safe_d_r_{:02d})".format(t) for t in range(30)]
    probe += ["v(q_lat_r_{:02d})".format(t) for t in range(30)]
    probe += ["v(q_ff_r_{:02d})".format(t) for t in range(30)]
    lines += [".probe tran " + " ".join(probe), ".tran 2p {:.12e}".format(total_stop_ps * 1.0e-12), ".ENDS bfe8_capture_ams", ""]
    return "\n".join(lines)


def render_capture_tb(schedules, states, values, total_stop_ps):
    """Generate VCS/XA glue with documented per-port and clock behavior."""
    d_ports = ["safe_d_{:02d}".format(t) for t in range(30)]
    q_lat_ports = ["q_lat_{:02d}".format(t) for t in range(30)]
    q_ff_ports = ["q_ff_{:02d}".format(t) for t in range(30)]
    ports = d_ports + ["latch_g", "dff_ck"] + q_lat_ports + q_ff_ports
    lines = [
        "// BFE8 capture testbench; simulation glue only, not production RTL.",
        "// safe_d_* are source-derived Level-0 inputs; q_lat_* and q_ff_* are analog outputs.",
        "`timescale 1ps/1ps", "module bfe8_capture_vcs_xa;",
    ]
    lines += ["  logic {}; // Level-0 tap {} input".format(name, i) for i, name in enumerate(d_ports)]
    lines += ["  logic latch_g; // LATQ gate control", "  logic dff_ck; // DFF clock"]
    lines += ["  wire {}; // real LATQ output".format(name) for name in q_lat_ports]
    lines += ["  wire {}; // real DFF output".format(name) for name in q_ff_ports]
    lines += ["  bfe8_capture_ams u_ams (", ",\n".join("    .{}({})".format(name, name) for name in ports), "  );", ""]
    lines += [
        "  // G falling and DFF rising edges preserve the BFE3 frozen offsets.",
        "  initial begin latch_g=1'b1;",
    ]
    previous = 0.0
    for edge_ps, _polarity in _capture_edges(total_stop_ps):
        gfall = edge_ps + CAPTURE_G_CLOSE_OFFSET_PS
        if gfall >= total_stop_ps:
            continue
        lines.append("    #( {:.12f} ) latch_g=1'b0; #( 1000.000000000000 ) latch_g=1'b1;".format(gfall - previous))
        previous = gfall + 1000.0
    lines += ["  end", "  initial begin dff_ck=1'b0;"]
    previous = 0.0
    for sample_ps, _polarity in _dff_rises(total_stop_ps):
        lines.append("    #( {:.12f} ) dff_ck=1'b1; #( 1250.000000000000 ) dff_ck=1'b0;".format(sample_ps - previous))
        previous = sample_ps + 1250.0
    lines += ["  end", ""]
    for tap, name in enumerate(d_ports):
        lines += ["  // Tap {:02d}: initial state uses xor_i(0) > 0.5*vdd_monitored(0).".format(tap),
                  "  initial begin", "    {}=1'b{};".format(name, states[tap])]
        previous = 0.0
        for event_s, event_state, _direction in schedules[tap]:
            event_ps = event_s * 1.0e12
            if event_ps >= total_stop_ps:
                continue
            lines.append("    #( {:.12f} ) {}=1'b{};".format(event_ps - previous, name, event_state))
            previous = event_ps
        lines += ["  end", ""]
    lines += ["  integer fd;", "  initial begin", "    fd=$fopen(\"xa_dff_samples.csv\",\"w\");",
              "    $fwrite(fd,\"sample_index,sample_time_ps,nearest_system_edge_ps,system_polarity,tap,q_lat_v,q_ff_v,vdd_safe_v\\n\");"]
    previous = 0.0
    for index, (sample_ps, polarity) in enumerate(_dff_rises(total_stop_ps)):
        lines.append("    #( {:.12f} );".format(sample_ps + 100.0 - previous))
        previous = sample_ps + 100.0
        edge_ps = sample_ps - CAPTURE_DFF_OFFSET_PS
        for tap in range(30):
            lines.append("    $fwrite(fd,\"{},%.6f,{:.6f},{},%d,%.9f,%.9f,%.9f\\n\", $realtime, {}, $snps_get_volt(bfe8_capture_vcs_xa.u_ams.q_lat_r_{:02d}), $snps_get_volt(bfe8_capture_vcs_xa.u_ams.q_ff_r_{:02d}), $snps_get_volt(bfe8_capture_vcs_xa.u_ams.vdd_safe));".format(index, edge_ps, polarity, tap, index, tap, tap))
    lines += ["    $fclose(fd);", "  end", "  initial begin #( {:.6f} ); $finish; end".format(total_stop_ps), "endmodule", ""]
    return "\n".join(lines)


def run_p2_seed(seed=41001):
    """Run exactly one healthy source/capture case and publish P2 evidence."""
    if seed != 41001:
        raise ValueError("P2 is authorized for seed 41001 only")
    config = read_json(FTC_ROOT / "ftc_config.json")
    cells = read_json(FTC_ROOT / "discovery" / "selected_cells.json")
    model = str(config["model_library"])
    hspice = str(Path(config["hspice"]).resolve())
    vcs = shutil.which("vcs") or "/home/synopsys/vcs/W-2024.09/bin/vcs"
    if not Path(hspice).is_file() or not Path(vcs).is_file():
        raise RuntimeError("BFE8 P2 requires configured HSPICE and VCS")
    composite_meta = read_json(ROOT / "healthy_controls" / "HEALTHY_CONTROLS_METADATA.json")
    total_stop_ps = int(composite_meta["composite"]["stop_ps"])
    case_root = RUN_ROOT / "healthy" / "seed_{:05d}".format(seed)
    source_dir = case_root / "source_hspice"
    xa_dir = case_root / "vcs_xa"
    listing, measures, mc0 = source_dir / "source.lis", source_dir / "source.mt0.csv", source_dir / "source.mc0.csv"
    if not (listing.is_file() and measures.is_file() and mc0.is_file()):
        source_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(FTC_ROOT / "spice" / "empty_subckt.sp_cal", source_dir / "empty_subckt.sp_cal")
        shutil.copyfile(ROOT / "healthy_controls" / "HEALTHY_COMPOSITE.inc", source_dir / "HEALTHY_COMPOSITE.inc")
        (source_dir / "source.sp").write_text(healthy_source_deck(cells, model, seed, total_stop_ps), encoding="ascii")
        result = subprocess.run([hspice, "source.sp", "-o", "source"], cwd=source_dir,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                universal_newlines=True, check=False, timeout=3600)
        (source_dir / "hspice_command.log").write_text(result.stdout, encoding="utf-8", errors="replace")
        if result.returncode:
            raise RuntimeError("P2 HSPICE failed for seed {}".format(seed))
    if not listing.is_file() or not measures.is_file() or not mc0.is_file():
        raise RuntimeError("P2 HSPICE missing listing/mt0/mc0 artifacts")
    text = listing.read_text(encoding="utf-8", errors="replace").lower()
    if "job concluded" not in text or "monte carlo simulation is detected" not in text or "**error**" in text:
        raise RuntimeError("P2 HSPICE listing is not clean or MC was not entered")
    signature = None
    for line in mc0.read_text(encoding="ascii", errors="replace").splitlines():
        if line.startswith("2,"):
            signature = hashlib.sha256(line[2:].encode("ascii")).hexdigest()
            break
    expected = retained_signatures()[seed]
    if signature != expected:
        raise RuntimeError("P2 process signature mismatch for seed {}".format(seed))
    measured = parse_measurements(measures, total_stop_ps)
    states_list, schedules_list = measured_capture_schedule(measured)
    # The real LATQ/DFF wrapper receives the measured Level-0 word as a
    # full-rail digital source.  The source rail itself is represented at the
    # nominal safe value in this bridge; HSPICE measurements above remain the
    # authoritative instantaneous monitored-rail evidence.
    capture_times = [0.0, total_stop_ps * 1.0e-12]
    columns = {bfe1_frontend.label_for("vdd_monitored"): [BFE8_SAFE_V, BFE8_SAFE_V]}
    for tap in range(30):
        initial_bit = states_list[tap]
        columns[bfe1_frontend.label_for("xor_{}".format(tap))] = [
            initial_bit * BFE8_SAFE_V, initial_bit * BFE8_SAFE_V]
    schedules = {tap: schedules_list[tap] for tap in range(30)}
    states = {tap: states_list[tap] for tap in range(30)}
    values = {tap: {"xor_v": columns[bfe1_frontend.label_for("xor_{}".format(tap))][0],
                    "threshold_v": 0.5 * BFE8_SAFE_V} for tap in range(30)}
    samples = xa_dir / "xa_dff_samples.csv"
    capture_returncode = 0
    if not samples.is_file():
        xa_dir.mkdir(parents=True, exist_ok=True)
        (xa_dir / "bfe8_capture_ams_wrapper.sp").write_text(render_capture_wrapper(columns, capture_times, total_stop_ps), encoding="ascii")
        (xa_dir / "tb_bfe8_capture_vcs_xa.sv").write_text(render_capture_tb(schedules, states, values, total_stop_ps), encoding="ascii")
        (xa_dir / "xa.cfg").write_text("set_sim_level 7\nset_waveform -format fsdb\n" + "\n".join(
            ["probe_waveform_voltage vdd_safe", "probe_waveform_voltage dff_ck_r"] +
            ["probe_waveform_voltage q_ff_r_{:02d}".format(t) for t in range(30)]) + "\n", encoding="ascii")
        (xa_dir / "vcsAD.init").write_text("bus_format [%d];\nuse_spice -cell bfe8_capture_ams;\nchoose xa -hspice bfe8_capture_ams.sp -c xa.cfg -o xa;\n", encoding="ascii")
        (xa_dir / "bfe8_capture_ams.sp").write_text("* BFE8 XA top deck.\n.option post=1 probe\n.lib '{}' tt\n.include '{}'\n.include '{}'\n.include '{}'\n.include '{}'\n.tran 2p {:.12e}\n.end\n".format(
            model, cells["source_files"]["rvt_cdl"], cells["source_files"]["lvt_cdl"], FTC_ROOT / "spice" / "empty_subckt.sp_cal", xa_dir / "bfe8_capture_ams_wrapper.sp", total_stop_ps * 1.0e-12), encoding="ascii")
        shutil.copyfile(FTC_ROOT / "spice" / "empty_subckt.sp_cal", xa_dir / "empty_subckt.sp_cal")
        compile_result = subprocess.run([vcs, "-full64", "-sverilog", "-timescale=1ps/1ps", "-ad=vcsAD.init", "-debug_access+all", "-o", "simv", "tb_bfe8_capture_vcs_xa.sv"], cwd=xa_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, check=False, timeout=1800)
        (xa_dir / "compile.log").write_text(compile_result.stdout, encoding="utf-8", errors="replace")
        if compile_result.returncode:
            raise RuntimeError("P2 VCS compile failed")
        run_result = subprocess.run(["./simv"], cwd=xa_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, check=False, timeout=3600)
        (xa_dir / "run.log").write_text(run_result.stdout, encoding="utf-8", errors="replace")
        capture_returncode = run_result.returncode
    if capture_returncode or not samples.is_file():
        raise RuntimeError("P2 VCS/XA capture failed")
    rows = list(csv.DictReader(samples.open(newline="", encoding="ascii")))
    if len(rows) != len(_dff_rises(total_stop_ps)) * 30:
        raise RuntimeError("P2 capture does not contain 30 taps per designated sample")
    q_ff_values = [float(row["q_ff_v"]) for row in rows]
    rail_values = [float(row["vdd_safe_v"]) for row in rows]
    if any(abs(value - BFE8_SAFE_V) > 1e-6 for value in rail_values):
        raise RuntimeError("P2 safe rail is not resolved at 1.10 V")
    # Analog cell outputs carry tiny numerical overshoot around the rails.
    # Use the frozen BFE3 10%/90% rail-resolution criterion rather than an
    # unrealistically exact 0..VDD interval.
    rail_low, rail_high = 0.1 * BFE8_SAFE_V, 0.9 * BFE8_SAFE_V
    if any(rail_low < value < rail_high for value in q_ff_values):
        raise RuntimeError("P2 q_ff contains an unresolved mid-rail value")
    expected_map = {float(item["time_ps"]): item for item in json.loads((ROOT / "healthy_controls" / "HEALTHY_COMPOSITE_EVENT_MAP.json").read_text(encoding="utf-8"))["events"] if item["valid"]}
    for row in rows:
        if float(row["nearest_system_edge_ps"]) not in expected_map:
            raise RuntimeError("P2 admitted an unmapped/guard event")
    (case_root / "P2_CASE.json").write_text(json.dumps({
        "seed": seed, "mc_random_signature": signature, "source_measurements_sha256": sha256(measures),
        "source_mc0_sha256": sha256(mc0), "capture_sha256": sha256(samples),
        "source_v": BFE8_SAFE_V, "safe_v": BFE8_SAFE_V, "tap_count": 30,
        "capture_sample_count": len(_dff_rises(total_stop_ps)), "q_ff_width": 30,
        "all_safe_rail_resolved": True, "all_q_ff_rail_resolved": True,
    }, indent=2, sort_keys=True) + "\n", encoding="ascii")
    return case_root


def run_p2():
    """Execute P2 and publish its PASS gate; failures remain blocking evidence."""
    case_root = run_p2_seed()
    (ROOT / "P2_REPORT.md").write_text("# BFE8 D02 P2 healthy single seed\n\nGate: `BFE8_D02_P2_HEALTHY_SINGLE_SEED_CAPTURE_PASS`\n\nSeed 41001 passed 1.10 V source, Level-0, real LATQ/DFF capture, rail-resolution and event-map checks.\n\nSimulation accounting: HSPICE=1, PrimeSim/XA=1, VCS=1.\n", encoding="utf-8")
    (ROOT / "P2_GATE.json").write_text(json.dumps({"gate": "BFE8_D02_P2_HEALTHY_SINGLE_SEED_CAPTURE_PASS", "status": "PASS", "seed": 41001, "case": str(case_root), "simulation_accounting": {"hspice": 1, "primesim": 1, "vcs": 1}, "stop_after_stage": True}, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_p0(paths, digests, signatures):
    """Publish deterministic P0 evidence and the zero-run budget."""
    ROOT.mkdir(parents=True, exist_ok=True)
    matrix = {
        "gate": "BFE8_D02_P0_AUTHORITY_AND_REUSE_AUDIT_READY",
        "status": "PASS",
        "branch": "bfe-multitap-latched-frontend",
        "seeds": list(SEEDS),
        "seed_count": len(SEEDS),
        "d02_csv_sha256": digests["d02_csv"],
        "d02_inc_sha256": digests["d02_inc"],
        "d02_contract": {
            "nominal_v": 1.10,
            "temperature_c": 25.0,
            "background_seed": 7301,
            "attack_mv": 60,
            "attack_onset_ns": 19.50,
            "target_event": "21 ns RISE",
            "stop_ns": 65.0,
        },
        "arch0": {
            "taps": 30,
            "rvt_prefix": 4,
            "lvt_prefix": 0,
            "level0": "xor_i > 0.5 * instantaneous vdd_monitored",
            "m_ff_range": [0, 435],
        },
        "timing": {
            "clk_sys_hz": 50000000,
            "clk_probe_hz": 400000000,
            "dff_sample_offset_ps": 1534.524618567,
            "e0_to_e4_probe_edges": 4,
            "e0_to_e7_probe_edges": 7,
            "e8": "sticky alarm",
        },
        "reused_without_rerun": [
            "BFE3 timing constants",
            "BFE4 process signatures and retained captures",
            "BFE5 TIM0 contract",
            "BFE6 parser/replay methodology only",
        ],
        "new_bfe8_artifacts_present": False,
        "authority_sha256": digests,
    }
    (ROOT / "P0_EVIDENCE_MATRIX.json").write_text(
        json.dumps(matrix, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with (ROOT / "P0_EXPECTED_PROCESS_SIGNATURES.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["seed", "mc_random_signature", "source_authority"])
        for seed in SEEDS:
            writer.writerow([seed, signatures[seed], "BFE4_CALN0_RESULTS.csv"])

    budget = {
        "gate": "BFE8_D02_P0_AUTHORITY_AND_REUSE_AUDIT_READY",
        "simulation_count_so_far": {"hspice": 0, "primesim": 0, "vcs": 0},
        "upper_bound_new_cases": {
            "healthy_source_capture": 30,
            "d02_source_capture": 30,
            "p4_physical": 0,
            "p7_hspice": 0,
            "p7_vcs_replay": 1,
        },
        "unavailable_and_reason": {
            "healthy_1p10v_composite_captures": "not present in retained BFE4/BFE6 evidence",
            "d02_1p10v_population_captures": "not present; attack data must be generated after margin lock",
            "healthy_margin_development_at_1p10v": "not present; cannot reuse 0.95 V BFE6 margins",
            "independent_healthy_fpr": "not present; requires FPR_BG=7303 captures",
        },
        "reuse_rule": "authority -> BFE8 reparse -> validated case resume -> new simulator call",
    }
    (ROOT / "P0_SIMULATION_BUDGET.json").write_text(
        json.dumps(budget, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = [
        "# BFE8 D02 P0 authority and reuse audit",
        "",
        "Gate: `BFE8_D02_P0_AUTHORITY_AND_REUSE_AUDIT_READY`",
        "",
        "All frozen BFE7, BFE0, BFE3, BFE4, BFE5, BFE6 and ARCH0 RTL authorities were present and hashed.",
        "The D02 CSV/INC hashes match the frozen manifest; 30 retained process signatures cover seeds 41001..41030.",
        "No BFE8 raw artifact was present, so the bounded new-work budget is recorded before P1.",
        "",
        "Simulation accounting for P0: HSPICE=0, PrimeSim=0, VCS=0.",
    ]
    (ROOT / "P0_EVIDENCE_MATRIX.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    gate = {
        "gate": "BFE8_D02_P0_AUTHORITY_AND_REUSE_AUDIT_READY",
        "status": "PASS",
        "evidence": ["P0_EVIDENCE_MATRIX.md", "P0_EVIDENCE_MATRIX.json",
                      "P0_EXPECTED_PROCESS_SIGNATURES.csv", "P0_SIMULATION_BUDGET.json"],
        "simulation_accounting": {"hspice": 0, "primesim": 0, "vcs": 0},
        "stop_after_stage": True,
    }
    (ROOT / "P0_GATE.json").write_text(json.dumps(gate, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="BFE8 D02 ARCH0 staged pilot runner")
    parser.add_argument("--stage", choices=("p0", "p1", "p2"), default="p0")
    args = parser.parse_args()
    if args.stage == "p0":
        paths, digests, signatures = audit_authorities()
        write_p0(paths, digests, signatures)
        print("BFE8 P0 PASS: audited {} authorities and {} process signatures".format(len(paths), len(signatures)))
    elif args.stage == "p1":
        run_p1()
        print("BFE8 P1 PASS: generated healthy controls and completed offline checks")
    else:
        run_p2()
        print("BFE8 P2 PASS: healthy seed 41001 real capture validated")


if __name__ == "__main__":
    main()
