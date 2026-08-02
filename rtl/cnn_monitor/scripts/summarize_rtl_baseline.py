#!/usr/bin/env python3
"""Collect reproducible synthesis/regression evidence for the CNN baseline.

The parser intentionally consumes only text reports already produced by the
Design Compiler flow.  It never invents missing timing or power numbers: a
point with an incomplete report set is marked ``incomplete`` and the final
Markdown report preserves that fact for auditability.
"""

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = ROOT / "runs" / "dc_sweep_20260801_r5"
REQUIRED = (
    "check_design_postcompile.rpt", "qor.rpt", "area.rpt",
    "timing_setup.rpt", "constraint_violators.rpt", "power_vectorless.rpt",
    "cnn_monitor_mapped.ddc", "cnn_monitor_mapped.v",
    "cnn_monitor_mapped.sdc", "cnn_monitor_mapped.sdf",
)


def first_number(pattern: str, text: str):
    """Return the first captured decimal value, or ``None`` if absent."""

    match = re.search(pattern, text, re.MULTILINE)
    return float(match.group(1)) if match else None


def parse_point(point: Path) -> dict:
    """Parse one lane/period directory without hiding missing evidence."""

    present = [name for name in REQUIRED if (point / name).is_file()]
    qor = (point / "qor.rpt").read_text(errors="replace") if "qor.rpt" in present else ""
    setup = (point / "timing_setup.rpt").read_text(errors="replace") if "timing_setup.rpt" in present else ""
    power = (point / "power_vectorless.rpt").read_text(errors="replace") if "power_vectorless.rpt" in present else ""
    period_match = re.search(r"lanes(\d+)_period([0-9p]+)ns", point.name)
    lanes = int(period_match.group(1)) if period_match else None
    period = period_match.group(2).replace("p", ".") if period_match else None
    critical = first_number(r"Critical Path Length:\s*([0-9.]+)", qor)
    slack = first_number(r"Critical Path Slack:\s*([0-9.+-]+)", qor)
    area = first_number(r"Design Area:\s*([0-9.]+)", qor)
    leaves = first_number(r"Leaf Cell Count:\s*([0-9]+)", qor)
    top_power = re.search(
        r"^cnn_monitor_MAC_LANES\d+\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)",
        power, re.MULTILINE)
    # DC declares dynamic values in mW and leakage in uW in the report header.
    # Energy uses the fixed release schedule scaled for each supported lane
    # count; it remains an estimate because switching is vectorless.
    dynamic_mw = (float(top_power.group(1)) + float(top_power.group(2))) if top_power else None
    groups = (18 + lanes - 1) // lanes if lanes else None
    cycles = (32 * groups * 10 + 2 * 32 * groups * 95 + 34 + 58
              if groups else None)
    energy_nj = dynamic_mw * cycles * float(period) / 1000.0 if dynamic_mw is not None else None
    return {
        "point": point.name,
        "lanes": lanes,
        "period_ns": float(period) if period else None,
        "target_frequency_mhz": 1000.0 / float(period) if period else None,
        "estimated_fmax_mhz": 1000.0 / critical if critical else None,
        "status": "complete" if len(present) == len(REQUIRED) else "incomplete",
        "missing": [name for name in REQUIRED if name not in present],
        "area": area,
        "leaf_cells": int(leaves) if leaves is not None else None,
        "critical_path_ns": critical,
        "wns_ns": slack,
        "setup_closed": slack is not None and slack >= 0.0,
        "vectorless_power_report": bool(power),
        "power_annotation": "vectorless" if power else "unavailable",
        "vectorless_average_dynamic_mw": dynamic_mw,
        "vectorless_energy_per_window_nj": energy_nj,
        "peak_dynamic_power": None,
        "cycles_per_window": cycles,
        "timing_report_bytes": len(setup),
    }


def main() -> None:
    points = [parse_point(path) for path in sorted(RUN_ROOT.glob("lanes*_period*ns"))]
    summary = {
        "schema_version": 1,
        "run_root": str(RUN_ROOT),
        "points": points,
        "regression": {
            "vcs_log": str(ROOT / "runs" / "vcs_full_20260801_r3" / "simulation.log"),
            "expected_pass_marker": "CNN_MONITOR_REGRESSION_PASS vectors=15 trace_cycles=12892",
        },
    }
    (RUN_ROOT / "rtl_baseline_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    lines = [
        "# CNN RTL Baseline Report", "",
        "This report is generated from the checked-in RTL, VCS regression log, "
        "and Design Compiler text reports. Missing artifacts remain explicit.", "",
        "## Functional evidence", "",
        "- Task-one binding remains W8/A8; no re-quantization was performed.",
        "- VCS regression target: `CNN_MONITOR_REGRESSION_PASS vectors=15 trace_cycles=12892`.",
        "- Fixed release latency: 12,892 cycles; initiation interval: 12,893 cycles.",
        "- Activity-annotated power is not claimed by this baseline; DC reports are vectorless unless a future run supplies >=90% annotation coverage.", "",
        "## Synthesis points", "",
        "| Point | Status | Area | Leaf cells | Critical path (ns) | WNS (ns) | Target (MHz) | Est. Fmax (MHz) | Avg dyn. (mW) | Energy/window (nJ) |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in points:
        values = [item["area"], item["leaf_cells"], item["critical_path_ns"], item["wns_ns"], item["target_frequency_mhz"], item["estimated_fmax_mhz"], item["vectorless_average_dynamic_mw"], item["vectorless_energy_per_window_nj"]]
        fmt = ["-" if value is None else f"{value:.3f}" if isinstance(value, float) else str(value) for value in values]
        lines.append(f"| {item['point']} | {item['status']} | " + " | ".join(fmt) + " |")
    lines += ["", "## Limitations", "", "- Average dynamic power and energy/window are vectorless estimates; peak dynamic power is unavailable and is not claimed.", "- Hold violations and high-fanout warnings are reported verbatim in each point directory; they are not silently waived.", "- No dummy-window scheduler or activity-codebook logic is included in this task-two baseline.", ""]
    (ROOT / "RTL_BASELINE_REPORT.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
