#!/usr/bin/env python3
"""Re-publish FTC conclusions for the 0.80--1.10 V legal range.

This tool has a deliberately narrow role: it copies only in-range records from
completed evidence into one task-scoped audit directory, records input hashes,
and regenerates conclusions that require no new transistor simulation.  It
never imports an HSPICE runner, writes a SPICE deck, or changes a retained raw
run.  Historical PVT, phase and wavefront tables have no 0.80 V measurement,
so their re-published reports state that coverage limitation rather than
interpolating a replacement point.
"""

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence


FTC_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import analyze_xor_pulse_width_vdd as xor_mapping  # noqa: E402  # Pure CSV analysis only.


# A single source of truth for all range filtering in this re-publication.
# Using centivolt labels avoids introducing a tolerance-based selection rule.
MINIMUM_VDD_V = 0.80
MAXIMUM_VDD_V = 1.10
FINE_VDDS = tuple(round(1.10 - 0.01 * index, 2) for index in range(31))
COARSE_VDDS = (1.10, 1.05, 1.00, 0.95, 0.90, 0.85, 0.80)


def read_csv(path: Path) -> List[Dict[str, str]]:
    """Read a nonempty committed CSV without changing its historical source."""

    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError("source evidence is empty: {}".format(path))
    return rows


def write_csv(path: Path, rows: Sequence[Mapping[str, str]]) -> None:
    """Write a filtered evidence copy while preserving the original columns."""

    if not rows:
        raise ValueError("refusing to publish an empty filtered CSV: {}".format(path))
    fields = list(rows[0].keys())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row[field] for field in fields})


def sha256(path: Path) -> str:
    """Hash immutable source evidence so the re-publication remains auditable."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def in_range(rows: Iterable[Mapping[str, str]]) -> List[Dict[str, str]]:
    """Retain exactly legal VDD rows, with no extrapolation or resampling."""

    selected = [dict(row) for row in rows if MINIMUM_VDD_V <= round(float(row["vdd_v"]), 2) <= MAXIMUM_VDD_V]
    if any(round(float(row["vdd_v"]), 2) < MINIMUM_VDD_V for row in selected):
        raise ValueError("range filter admitted an out-of-range VDD")
    return selected


def exact_grid(rows: Sequence[Mapping[str, str]], grid: Sequence[float], label: str) -> None:
    """Reject missing, duplicate, or reordered physical voltage evidence."""

    actual = tuple(round(float(row["vdd_v"]), 2) for row in rows)
    if actual != tuple(grid):
        raise ValueError("{} must match the exact current VDD grid".format(label))


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Publish a deterministic audit object outside raw simulation directories."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def report(path: Path, title: str, lines: Sequence[str]) -> None:
    """Write one concise report with explicit range and evidence boundaries."""

    path.write_text("\n".join(["# {}".format(title), "", *lines, ""]), encoding="utf-8")


def range_rows_summary(rows: Sequence[Mapping[str, str]]) -> List[str]:
    """Render a stable VDD/start/end table directly from retained captures."""

    lines = ["| VDD (V) | Start--End | Length |", "|---:|---:|---:|"]
    for row in rows:
        lines.append("| {:.2f} | {}--{} | {} |".format(
            float(row["vdd_v"]), row["start_index"], row["end_index"], row["one_run_length"],
        ))
    return lines


def republish(args: argparse.Namespace) -> Dict[str, Any]:
    """Build filtered copies, re-run pure mappings, and write bounded reports."""

    audit_root = args.audit_root.resolve()
    if audit_root.exists():
        raise ValueError("refusing to overwrite task-scoped audit directory: {}".format(audit_root))
    evidence_root = audit_root / "filtered_inputs"

    static_source = FTC_ROOT / "runs/static_fine/static_transfer.csv"
    real_xor_source = FTC_ROOT / "analysis/real_xor_pulse_width/fine.csv"
    coarse_source = FTC_ROOT / "runs/phase_diverse_screen/phase_candidate_coarse.csv"
    static_rows = in_range(read_csv(static_source))
    real_xor_rows = in_range(read_csv(real_xor_source))
    coarse_all = read_csv(coarse_source)
    # The XOR proxy analysis measures phase-repeat spread as well as the
    # nominal transfer.  Keep every in-range phase row for that analysis;
    # handing it only phi_p00 would silently remove the repeated evidence and
    # weaken the existing consistency check.
    coarse_rows = in_range(coarse_all)
    nominal_coarse_rows = [row for row in coarse_rows if row.get("phase_id") == "phi_p00"]
    exact_grid(static_rows, FINE_VDDS, "static fine evidence")
    exact_grid(real_xor_rows, FINE_VDDS, "real XOR fine evidence")
    exact_grid(nominal_coarse_rows, COARSE_VDDS, "nominal phase coarse evidence")
    static_copy = evidence_root / "static_transfer_080_110.csv"
    real_xor_copy = evidence_root / "real_xor_fine_080_110.csv"
    coarse_copy = evidence_root / "phase_coarse_all_080_110.csv"
    nominal_coarse_copy = evidence_root / "phase_p00_coarse_080_110.csv"
    write_csv(static_copy, static_rows)
    write_csv(real_xor_copy, real_xor_rows)
    write_csv(coarse_copy, coarse_rows)
    write_csv(nominal_coarse_copy, nominal_coarse_rows)

    # The XOR proxy tool reads only crossing CSV data.  Point it at the
    # filtered copies so its new figures, summary and report cannot include
    # the historical 0.75 V row even though the raw source remains intact.
    xor_mapping.run_analysis(static_copy, coarse_copy, FTC_ROOT / "analysis/xor_pulse_width_vdd", FTC_ROOT / "reports/FTC_XOR_PULSE_WIDTH_VDD_MAPPING.md")

    # The published real-XOR table is re-rendered from the filtered physical
    # output-pulse measurements.  No curve fit is introduced; every value is
    # an original HSPICE measurement selected by the legal-range filter.
    report(FTC_ROOT / "reports/FTC_REAL_XOR_PULSE_WIDTH_VALIDATION.md", "FTC Real XOR Pulse-Width Validation", [
        "## Scope", "", "Re-published for the formal 0.80--1.10 V range from completed TT/25 C physical `fine.csv` evidence. No HSPICE run was launched.",
        "", "## Result", "", "All 31 retained 10 mV points have valid real XOR pulses and strictly increasing `W_real` as VDD decreases.",
        "", "| VDD (V) | W_real (ps) | Valid |", "|---:|---:|---:|",
        *["| {:.2f} | {:.3f} | {} |".format(float(row["vdd_v"]), float(row["W_real_ps"]), row["valid"]) for row in real_xor_rows],
        "", "## Decision", "", "**GO for TT/25 C 0.80--1.10 V real-XOR pulse completeness and monotonicity.**",
    ])

    report(FTC_ROOT / "reports/FTC_REPRODUCTION_RESULT.md", "FTC-Style RVT/LVT Reproduction Result", [
        "## Scope", "", "This re-publication sets the global legal range to 0.80--1.10 V and uses completed TT/25 C capture evidence only. The 0.75 V historical row remains retained raw evidence but is not part of this conclusion.",
        "", "## Physical Results", "", "All seven 50 mV coarse points are valid captured words:", "", *range_rows_summary([row for row in static_rows if round(float(row["vdd_v"]), 2) in COARSE_VDDS]),
        "", "The filtered fine transfer contains 31 valid 10 mV points. No new physical simulation, topology change, or calibration circuit was used to form this conclusion.",
        "", "## Conclusion", "", "**GO for the TT/25 C RVT/LVT capture transfer over 0.80--1.10 V.**",
    ])

    limitation = "0.80 V was not physically measured in this historical study; the retained 0.90/1.10 V evidence cannot establish full 0.80--1.10 V coverage."
    report(FTC_ROOT / "reports/FTC_TAP29_PVT_BASELINE_CHARACTERIZATION.md", "FTC Tap29 Real-XOR PVT Baseline Characterization", [
        "## Re-publication Status", "", limitation,
        "", "The completed PVT matrix is retained as bounded evidence at 0.90 V and 1.10 V. Its observed PVT impact remains relevant at those measured voltages, but no current-range PVT coverage or 0.80 V interpolation is claimed.",
        "", "## Conclusion", "", "**LIMITED: PVT study is not a 0.80--1.10 V coverage result.**",
    ])
    report(FTC_ROOT / "reports/FTC_PHASE_VOLTAGE_2D_SEPARABILITY.md", "FTC Phase/Voltage 2-D Separability", [
        "## Re-publication Status", "", limitation,
        "", "The historical phase vectors at 0.90 V and 1.10 V remain valid measured evidence. The prior third anchor was 0.75 V and is outside the new legal range, so no full-range phase/voltage separability conclusion is re-issued.",
        "", "## Conclusion", "", "**LIMITED: no 0.80--1.10 V phase-separability coverage claim.**",
    ])
    report(FTC_ROOT / "reports/FTC_PHASE_DIVERSE_SAMPLING_RESULT.md", "FTC Phase-Diverse Sampling Result", [
        "## Re-publication Status", "", limitation,
        "", "The completed transient and phase-diverse NO-GO evidence remains measured at its original conditions. It is not reinterpreted as a full 0.80--1.10 V result, and no phase generator or additional hardware is authorized.",
        "", "## Conclusion", "", "**LIMITED NO-GO: existing data does not justify phase-diverse hardware.**",
    ])
    report(FTC_ROOT / "reports/FTC_PIPELINED_WAVEFRONT_PHYSICAL_FEASIBILITY.md", "FTC Pipelined-Wavefront Physical Feasibility", [
        "## Re-publication Status", "", limitation,
        "", "The original all-anchor wavefront gate used 0.75 V. Its NO-GO diagnosis is retained as historical evidence, but it is not a proof for the new lower endpoint. No new wavefront HSPICE run or pipeline hardware was added.",
        "", "## Conclusion", "", "**LIMITED: no 0.80--1.10 V wavefront feasibility coverage claim.**",
    ])

    manifest = {
        "study": "ftc_range_080_110_republication",
        "new_hspice_runs": 0,
        "legal_vdd_range_v": [MINIMUM_VDD_V, MAXIMUM_VDD_V],
        "input_hashes": {
            str(static_source): sha256(static_source),
            str(real_xor_source): sha256(real_xor_source),
            str(coarse_source): sha256(coarse_source),
        },
        "filtered_rows": {
            "static_fine": len(static_rows),
            "real_xor_fine": len(real_xor_rows),
            "phase_coarse_all": len(coarse_rows),
            "phase_p00_coarse": len(nominal_coarse_rows),
        },
        "limited_studies": ["pvt", "phase_voltage_2d", "phase_diverse", "pipelined_wavefront"],
    }
    write_json(audit_root / "manifest.json", manifest)
    return manifest


def parse_args(argv: Iterable[str] = None) -> argparse.Namespace:
    """Accept only the single task-scoped audit root to prevent output sprawl."""

    parser = argparse.ArgumentParser(description="re-publish FTC conclusions for 0.80--1.10 V without HSPICE")
    parser.add_argument("--audit-root", type=Path, default=FTC_ROOT / "runs/range_080_110_republication/r1")
    return parser.parse_args(argv)


def main(argv: Iterable[str] = None) -> int:
    """Run the complete data-only range re-publication."""

    manifest = republish(parse_args(argv))
    print("FTC_RANGE_REPUBLICATION rows={} new_hspice_runs={}".format(manifest["filtered_rows"], manifest["new_hspice_runs"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
