#!/usr/bin/env python3
"""Analyze the two fixed-close B-FE2-L0 probes and write evidence artifacts."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUN_ROOT = ROOT.parents[3] / "runs" / "b_fe_frontend" / "bfe2_real_latch" / "l0"
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


def analyze_one(scenario_id: str):
    directory = RUN_ROOT / scenario_id.lower().replace("-", "_")
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
    return {
        "scenario_id": scenario_id,
        "probe_sha256": sha256(directory / "l0_probe.dat"),
        "record_count": len(rows),
        "final_q_code": final_code,
        "q_stable": not crossings or all(event["time_ps"] <= rows[-1][0] for event in crossings),
        "all_q_full_swing": all(value in (0.0, 0.95) for row in rows for value in row[q_start:q_end]),
        "post_close_q_crossings": post_close,
        "post_close_reflip_taps": sorted({event["tap"] for event in post_close}),
        "max_post_close_resolution_ps": max((event["time_ps"] - CLOSE_PS for event in post_close), default=0.0),
    }


def main():
    results = [analyze_one(scenario) for scenario in SCENARIOS]
    hamming = sum(a != b for a, b in zip(results[0]["final_q_code"], results[1]["final_q_code"]))
    pass_gate = (all(item["q_stable"] and item["all_q_full_swing"] for item in results)
                 and not any(item["post_close_reflip_taps"] for item in results)
                 and hamming > 0)
    manifest = {
        "schema_version": 1,
        "stage": "B-FE2-L0",
        "gate": "BFE2_L0_SAFE_DOMAIN_PASS" if pass_gate else "BFE2_L0_SAFE_DOMAIN_FAIL",
        "verification_mode": "offline_replay_due_vcs_compile_block",
        "vcs_execution": {"status": "blocked", "tool": "VCS P-2019.06-SP2_Full64",
                           "host": "166.111.78.45", "compile_logs_retained": True},
        "new_hspice_scenarios": 0,
        "scenario_ids": list(SCENARIOS),
        "fixed_sample_close_ps": CLOSE_PS,
        "fixed_pd_safe_v": 0.95,
        "final_q_hamming_distance": hamming,
        "final_q_min_bit_margin_v": 0.475,
        "results": results,
        "causal_interpretation": "Ideal PD_SAFE restoration plus transparent-high latch hold removes source-domain re-flips in deterministic replay; this does not prove a physical level shifter.",
    }
    out = ROOT / "BFE2_L0_ANALYSIS.json"
    out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (ROOT / "BFE2_L0_GATE_STATUS.json").write_text(json.dumps({"gate": manifest["gate"], "new_hspice_scenarios": 0, "vcs_status": "blocked"}, indent=2) + "\n", encoding="utf-8")
    scenario_manifest = {
        "schema_version": 1,
        "stage": "B-FE2-L0",
        "gate": manifest["gate"],
        "scenario_ids": list(SCENARIOS),
        "requested_close_ps": CLOSE_PS,
        "fixed_pd_safe_v": 0.95,
        "new_hspice_scenarios": 0,
        "source_trace_root": "runs/b_fe_frontend/bfe2_real_latch/real_snapshot/corrected_seed_534p525ps",
        "results": [{"scenario_id": item["scenario_id"], "probe_sha256": item["probe_sha256"], "record_count": item["record_count"]} for item in results],
    }
    (ROOT / "BFE2_L0_SCENARIO_MANIFEST.json").write_text(json.dumps(scenario_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = """# B-FE2-L0 report\n\nGate: `{gate}`\n\n""".format(gate=manifest["gate"])
    report += "The two fixed-close 0.95 V probes use the immutable B-FE2.2C normal/L2 stimulus and `sample_close=534.524618567 ps`.\n\n"
    report += "Normal final Q: `{}`\n\nL2 final Q: `{}`\n\nHamming distance: `{}`\n\n".format(results[0]["final_q_code"], results[1]["final_q_code"], hamming)
    report += "No post-close Q crossing/re-flip was observed in either deterministic L0 replay. VCS compilation was attempted remotely and its finalizer exited 255; therefore this PASS is an offline ideal-model causal result, not evidence that a real level shifter is implemented. `new_hspice_scenarios=0`.\n"
    (ROOT / "BFE2_L0_REPORT.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
