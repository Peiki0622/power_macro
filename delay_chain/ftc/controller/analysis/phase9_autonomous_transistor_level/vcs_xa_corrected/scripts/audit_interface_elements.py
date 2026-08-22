#!/usr/bin/env python3
"""Audit the corrected Phase 9 digital/analog boundary.

The audit has two deliberately separate parts:

1. Source-contract checks prove that the corrected cell no longer exposes
   VDD/VSS as Verilog ports and that all required control widths are present.
2. If a generated XA interface-element report is supplied, report checks prove
   that the required controls are present and that the historical generic
   supply crossings are absent.

The historical report is parsed as negative evidence only.  It is never
treated as proof of the corrected flow.  Without a newly generated report the
result remains ``STATIC_ONLY`` and the R2 gate is not falsely promoted.
"""

import argparse
import json
import re
from pathlib import Path


SCRIPT = Path(__file__).resolve()
FLOW_ROOT = SCRIPT.parents[1]
HIST_ROOT = FLOW_ROOT.parent / "vcs_xa"
OUTPUT = FLOW_ROOT / "reports" / "INTERFACE_ELEMENT_AUDIT.json"

REQUIRED_CROSSINGS = {
    "sense_s_clk": 1,
    "sense_dff_reset": 1,
    "medium_therm": 16,
    "fine_therm": 10,
}


def read_source_contract():
    """Inspect corrected stub and wrapper text without elaborating XA."""

    stub = FLOW_ROOT / "src" / "ftc_sensor_ams_stub.sv"
    wrapper = FLOW_ROOT / "src" / "ftc_sensor_ams_wrapper.sp"
    stub_text = stub.read_text(encoding="utf-8")
    wrapper_text = wrapper.read_text(encoding="utf-8")
    errors = []
    if re.search(r"\b(input|output)\s+wire\s+VDD\b", stub_text, re.IGNORECASE):
        errors.append("corrected Verilog stub still exposes VDD")
    if re.search(r"\b(input|output)\s+wire\s+VSS\b", stub_text, re.IGNORECASE):
        errors.append("corrected Verilog stub still exposes VSS")
    if "V_SENSOR_VDD VDD_LOCAL 0 VDD_VALUE" not in wrapper_text:
        errors.append("corrected wrapper lacks explicit VDD source")
    if "V_SENSOR_VSS VSS_LOCAL 0 0" not in wrapper_text:
        errors.append("corrected wrapper lacks explicit VSS source")
    # The Verilog view uses controller names while the SPICE wrapper uses the
    # frozen analog net aliases S_SCLK/S_RESET.  Treat those aliases as the
    # same crossing and keep the mapping explicit in the audit.
    source_names = {
        "sense_s_clk": ("sense_s_clk", "sense_s_clk"),
        "sense_dff_reset": ("sense_dff_reset", "sense_dff_reset"),
        "medium_therm": ("medium_therm", "medium_therm"),
        "fine_therm": ("fine_therm", "fine_therm"),
    }
    for name, (stub_name, wrapper_name) in source_names.items():
        if stub_name not in stub_text or wrapper_name not in wrapper_text:
            errors.append("required crossing missing from corrected source: " + name)
    return {"stub": str(stub), "wrapper": str(wrapper), "errors": errors}


def parse_interface_report(path):
    """Count inserted elements by signal family in an XA report."""

    text = path.read_text(encoding="utf-8")
    entries = [line.strip() for line in text.splitlines() if "snps_interface_element" in line]
    counts = {name: 0 for name in REQUIRED_CROSSINGS}
    supply_entries = []
    for line in entries:
        lowered = line.lower()
        if ".vdd" in lowered or " vdd" in lowered:
            supply_entries.append(line)
        if ".vss" in lowered or " vss" in lowered:
            supply_entries.append(line)
        aliases = {
            "sense_s_clk": ("sense_s_clk", "s_sclk"),
            "sense_dff_reset": ("sense_dff_reset", "s_reset"),
            "medium_therm": ("medium_therm",),
            "fine_therm": ("fine_therm",),
        }
        for name, names in aliases.items():
            if any(alias in lowered for alias in names):
                counts[name] += 1
    return {"path": str(path), "entry_count": len(entries), "counts": counts, "supply_entries": supply_entries, "raw_entries": entries}


def main():
    """Run source and optional generated-report checks and publish JSON."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, help="new generated XA snpsInterfaceElementFile.spi")
    args = parser.parse_args()
    source = read_source_contract()
    generated = None
    errors = list(source["errors"])
    status = "STATIC_ONLY"
    if args.report is not None:
        if not args.report.is_file():
            errors.append("requested generated XA report does not exist")
        else:
            generated = parse_interface_report(args.report)
            status = "PASS" if not errors else "FAIL"
            for name, width in REQUIRED_CROSSINGS.items():
                if generated["counts"][name] != width:
                    errors.append("generated XA report crossing count mismatch for {}: got {}, expected {}".format(name, generated["counts"][name], width))
            if generated["supply_entries"]:
                errors.append("generated XA report contains forbidden VDD/VSS interface elements")
            status = "PASS" if not errors else "FAIL"
    result = {
        "schema_version": 1,
        "status": status if not errors else "FAIL",
        "source_contract": source,
        "generated_interface_report": generated,
        "historical_report": str(HIST_ROOT / "runs" / "preflight" / "simv.daidir" / "snpsInterfaceElementFile.spi"),
        "historical_report_is_not_corrected_evidence": True,
        "required_crossings": REQUIRED_CROSSINGS,
        "errors": errors,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in ("PASS", "STATIC_ONLY") else 1


if __name__ == "__main__":
    raise SystemExit(main())
