#!/usr/bin/env python3
"""Build the FTC controller contract from immutable acceptance evidence.

This utility deliberately does not import or execute either historical runner.
It reads their published outputs, validates the frozen decisions, and creates
the controller-owned contract consumed by all later RTL regressions.
"""

import hashlib
import json
from pathlib import Path


FTC_ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = FTC_ROOT / "analysis" / "reachable_path_acceptance"
SPEC_DIR = FTC_ROOT / "controller" / "spec"


def read_object(path: Path):
    """Read one non-empty JSON object and reject malformed evidence early."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def sha256_file(path: Path):
    """Hash an immutable input without copying it into the task output tree."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value):
    """Write stable, machine-readable controller-owned evidence."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main():
    """Construct the single source of functional truth for the new controller."""

    contract_paths = {
        "0p80": EVIDENCE / "exact_path_0p80_contract.json",
        "0p95": EVIDENCE / "exact_path_0p95_contract.json",
        "1p10": EVIDENCE / "exact_path_1p10_contract.json",
    }
    final_path = EVIDENCE / "exact_hspice" / "final_acceptance.json"
    semantics_path = EVIDENCE / "decision_semantics.json"
    inputs = list(contract_paths.values()) + [final_path, semantics_path]
    if any(not path.is_file() or path.stat().st_size == 0 for path in inputs):
        raise ValueError("required accepted evidence is missing")

    accepted = read_object(final_path)
    semantics = read_object(semantics_path)
    expected = {
        "0p80": {"coarse_boundary": 9, "selected_medium_base": 7, "fine_boundary": 5, "guard_code": 6, "final": {"M": 7, "F": 6}, "operations": 45},
        "0p95": {"coarse_boundary": 6, "selected_medium_base": 4, "fine_boundary": 5, "guard_code": 6, "final": {"M": 4, "F": 6}, "operations": 36},
        "1p10": {"coarse_boundary": 4, "selected_medium_base": 2, "fine_boundary": 8, "guard_code": 9, "final": {"M": 2, "F": 9}, "operations": 36},
    }
    scenarios = {}
    checks = {
        "accepted_exact_path_go": accepted.get("decision") == "GO",
        "coarse_semantics": semantics.get("coarse", {}).get("decision") == "two_independent_probes_both_stable_low_stop",
        "backoff_semantics": semantics.get("backoff", {}).get("steps") == 2 and semantics.get("backoff", {}).get("comparison_probes") == 0,
        "fine_semantics": semantics.get("fine", {}).get("boundary") == "first_not_stable_high",
        "guard_hold_semantics": semantics.get("fine", {}).get("guard") == "boundary_plus_one" and semantics.get("fine", {}).get("lock_hold") == "one_independent_repeat",
    }

    for voltage, path in contract_paths.items():
        raw = read_object(path)
        result = accepted.get("results", {}).get(voltage, {})
        target = expected[voltage]
        scenario = {
            "coarse_boundary": target["coarse_boundary"],
            "selected_medium_base": target["selected_medium_base"],
            "fine_boundary": target["fine_boundary"],
            "guard_code": target["guard_code"],
            "final_locked_code": target["final"],
            "operation_count": target["operations"],
            "source_contract_sha256": sha256_file(path),
        }
        scenarios[voltage] = scenario
        checks["{}_result_go".format(voltage)] = result.get("status") == "GO"
        checks["{}_final_code".format(voltage)] = result.get("final_locked_code") == target["final"]
        checks["{}_operation_count".format(voltage)] = result.get("operation_count") == target["operations"]
        checks["{}_contract_boundary".format(voltage)] = (
            raw.get("coarse_boundary") == target["coarse_boundary"]
            and raw.get("selected_medium_base") == target["selected_medium_base"]
            and raw.get("fine_boundary") == target["fine_boundary"]
            and raw.get("guard_code") == target["guard_code"]
        )

    output = {
        "schema_version": 1,
        "baseline_commit": "4e69acca9e82ae32f982014ced969d270ab8c8fa",
        "decision": "Controller Functional Contract = GO" if all(checks.values()) else "Controller Functional Contract = NO-GO",
        "physical_interface": {"medium_bits": 16, "fine_bits": 10, "medium_encoding": "first_code_high", "fine_encoding": "first_code_low_active_low"},
        "timing_reference": {"recovery_guard_s": 2.7e-9, "corner": "tt", "temperature_c": 25},
        "q_classes": ["STABLE_LOW", "STABLE_HIGH", "AMBIGUOUS"],
        "failure_reasons": ["COARSE_RANGE_FAIL", "COARSE_BACKOFF_UNDERFLOW", "FINE_RANGE_FAIL", "GUARD_RANGE_FAIL", "GUARD_NOT_LOW", "HOLD_NOT_LOW"],
        "scenarios": scenarios,
        "checks": checks,
        "source_sha256": {str(path.relative_to(FTC_ROOT)): sha256_file(path) for path in inputs},
        "historical_runners_executed": False,
        "hspice_runs": 0,
    }
    write_json(SPEC_DIR / "ftc_calibration_controller_contract.json", output)
    report = [
        "# FTC Calibration Controller Functional Contract",
        "",
        "This contract is a read-only translation of accepted exact-path evidence. No historical runner or HSPICE simulation was executed.",
        "",
        "## Decision",
        "",
        "**{}**".format(output["decision"]),
        "",
        "## Frozen Nominal Outcomes",
        "",
        "| VDD | Coarse boundary | Selected M | Fine boundary | Final | Operations |",
        "|---:|---:|---:|---:|---|---:|",
    ]
    for voltage in ("0p80", "0p95", "1p10"):
        item = scenarios[voltage]
        code = item["final_locked_code"]
        report.append("| {} V | M{} | M{} | F{} | M{}/F{} | {} |".format(voltage.replace("p", "."), item["coarse_boundary"], item["selected_medium_base"], item["fine_boundary"], code["M"], code["F"], item["operation_count"]))
    report.extend(["", "The controller accepts a coarse boundary only after two independent stable-low probes, performs exactly two adjacent backoff updates, stops fine search at the first non-stable-high result, and requires stable-low guard and hold probes before lock.", ""])
    (SPEC_DIR / "FTC_CALIBRATION_CONTROLLER_SPEC.md").write_text("\n".join(report), encoding="utf-8")
    if not all(checks.values()):
        raise SystemExit("phase 0 contract checks failed")


if __name__ == "__main__":
    main()
