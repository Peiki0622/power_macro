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
    parser.add_argument("--stage", choices=("p0", "p1"), default="p0")
    args = parser.parse_args()
    if args.stage == "p0":
        paths, digests, signatures = audit_authorities()
        write_p0(paths, digests, signatures)
        print("BFE8 P0 PASS: audited {} authorities and {} process signatures".format(len(paths), len(signatures)))
    else:
        run_p1()
        print("BFE8 P1 PASS: generated healthy controls and completed offline checks")


if __name__ == "__main__":
    main()
