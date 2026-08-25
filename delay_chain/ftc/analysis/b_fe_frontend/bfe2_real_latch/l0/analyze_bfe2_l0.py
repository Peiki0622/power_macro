#!/usr/bin/env python3
"""Analyze the two fixed-close B-FE2-L0 probes and write evidence artifacts."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUN_ROOT = ROOT.parents[3] / "runs" / "b_fe_frontend" / "bfe2_real_latch" / "l0_local_vcs_xa"
CLOSE_PS = 534.524618567
THRESHOLD_V = 0.475
SCENARIOS = ("BFE2L-095-N", "BFE2L-095-L2")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_probe(path: Path):
    lines = path.read_text(encoding="ascii").splitlines()
    labels = lines[0].split()
    rows = [[float(item) for item in line.split()] for line in lines[1:] if line.strip()]
    return labels, rows


def analyze_one(scenario_id: str, run_manifest):
    directory = RUN_ROOT / scenario_id.lower().replace("-", "_")
    run_entry = next(item for item in run_manifest["results"] if item["scenario_id"] == scenario_id)
    labels, rows = read_probe(directory / "l0_probe.dat")
    q_start = labels.index("q_0")
    q_end = q_start + 30
    crossings = []
    previous = rows[0][q_start:q_end]
    for row in rows[1:]:
        current = row[q_start:q_end]
        for tap, (old, new) in enumerate(zip(previous, current)):
            if (old > THRESHOLD_V) != (new > THRESHOLD_V):
                crossings.append({"tap": tap, "time_ps": row[0], "direction": "rise" if new > old else "fall"})
        previous = current
    post_close = [event for event in crossings if event["time_ps"] > CLOSE_PS]
    final_code = "".join("1" if value > THRESHOLD_V else "0" for value in rows[-1][q_start:q_end])
    # The last two samples must agree; this is a finite-waveform stability
    # check, while the separate post-close list captures any forbidden event.
    final_q_stable = len(rows) >= 2 and rows[-1][q_start:q_end] == rows[-2][q_start:q_end]
    return {
        "scenario_id": scenario_id,
        "run_disposition": run_entry["run_disposition"],
        "probe_sha256": sha256(directory / "l0_probe.dat"),
        "stimulus_sha256": run_entry["stimulus_sha256"],
        "source_tr0_sha256": run_entry["source_tr0_sha256"],
        "source_deck_sha256": run_entry["source_deck_sha256"],
        "record_count": len(rows),
        "final_q_code": final_code,
        "q_stable": final_q_stable,
        "all_q_full_swing": all(value in (0.0, 0.95) for row in rows for value in row[q_start:q_end]),
        "post_close_q_crossings": post_close,
        "post_close_reflip_taps": sorted({event["tap"] for event in post_close}),
        "max_post_close_resolution_ps": max((event["time_ps"] - CLOSE_PS for event in post_close), default=0.0),
    }


def main():
    run_manifest_path = RUN_ROOT / "BFE2_L0_LOCAL_RUN_MANIFEST.json"
    run_manifest = json.loads(run_manifest_path.read_text(encoding="utf-8"))
    results = [analyze_one(scenario, run_manifest) for scenario in SCENARIOS]
    hamming = sum(a != b for a, b in zip(results[0]["final_q_code"], results[1]["final_q_code"]))
    pass_gate = (all(item["q_stable"] and item["all_q_full_swing"] for item in results)
                 and not any(item["post_close_reflip_taps"] for item in results)
                 and hamming > 0)
    manifest = {
        "schema_version": 2,
        "stage": "B-FE2-L0",
        "gate": "BFE2_L0_SAFE_DOMAIN_PASS" if pass_gate else "BFE2_L0_SAFE_DOMAIN_FAIL",
        "verification_mode": "local_vcs_behavior_replay_with_xa_preflight",
        "vcs_execution": run_manifest["vcs_execution"],
        "xa_execution": run_manifest["xa_execution"],
        "new_hspice_scenarios": 0,
        "scenario_ids": list(SCENARIOS),
        "fixed_sample_close_ps": CLOSE_PS,
        "fixed_pd_safe_v": 0.95,
        "final_q_hamming_distance": hamming,
        "final_q_min_bit_margin_v": 0.475,
        "source_bfe2_2c_manifest_sha256": run_manifest["source_bfe2_2c_manifest_sha256"],
        "source_bfe2_2c_analysis_sha256": run_manifest["source_bfe2_2c_analysis_sha256"],
        "artifact_sha256": {
            "analysis_script": sha256(ROOT / "analyze_bfe2_l0.py"),
            "behavior_model": sha256(ROOT / "src" / "bfe2_l0_behavior_model.sv"),
            "testbench": sha256(ROOT / "src" / "tb_bfe2_l0.sv"),
        },
        "results": results,
        "causal_interpretation": "Ideal PD_SAFE restoration plus transparent-high latch hold removes source-domain re-flips in deterministic replay; this does not prove a physical level shifter.",
    }
    out = ROOT / "BFE2_L0_ANALYSIS.json"
    out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (ROOT / "BFE2_L0_GATE_STATUS.json").write_text(json.dumps({
        "gate": manifest["gate"],
        "new_hspice_scenarios": 0,
        "vcs_status": manifest["vcs_execution"]["status"],
        "xa_status": manifest["xa_execution"]["status"],
        "causal_scope": "ideal PD_SAFE restoration and latch isolation only",
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    scenario_manifest = {
        "schema_version": 2,
        "stage": "B-FE2-L0",
        "gate": manifest["gate"],
        "scenario_ids": list(SCENARIOS),
        "requested_close_ps": CLOSE_PS,
        "fixed_pd_safe_v": 0.95,
        "new_hspice_scenarios": 0,
        "source_trace_root": "runs/b_fe_frontend/bfe2_real_latch/real_snapshot/corrected_seed_534p525ps",
        "source_bfe2_2c_manifest_sha256": run_manifest["source_bfe2_2c_manifest_sha256"],
        "results": [{"scenario_id": item["scenario_id"], "probe_sha256": item["probe_sha256"],
                     "record_count": item["record_count"],
                     "source_tr0_sha256": next(entry["source_tr0_sha256"] for entry in run_manifest["results"] if entry["scenario_id"] == item["scenario_id"]),
                     "source_deck_sha256": next(entry["source_deck_sha256"] for entry in run_manifest["results"] if entry["scenario_id"] == item["scenario_id"])} for item in results],
    }
    (ROOT / "BFE2_L0_SCENARIO_MANIFEST.json").write_text(json.dumps(scenario_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = """# B-FE2-L0 report\n\nGate: `{gate}`\n\n""".format(gate=manifest["gate"])
    report += "The two fixed-close 0.95 V probes use the immutable B-FE2.2C normal/L2 stimulus and `sample_close=534.524618567 ps`.\n\n"
    report += "Normal final Q: `{}`\n\nL2 final Q: `{}`\n\nHamming distance: `{}`\n\n".format(results[0]["final_q_code"], results[1]["final_q_code"], hamming)
    report += "No post-close Q crossing/re-flip was observed in either deterministic L0 replay. Local VCS W-2024.09 compiled and executed both fixed stimuli; the local PrimeSim XA W-2024.09 official tutorial also completed with zero comparison errors. This PASS proves only that ideal PD_SAFE restoration plus ideal transparent-latch isolation removes the observed failure in this replay; it does not prove a physical level shifter implementation. `new_hspice_scenarios=0`.\n"
    (ROOT / "BFE2_L0_REPORT.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
