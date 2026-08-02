#!/usr/bin/env python3
"""Authenticate SMIC40LL ROM views and publish a machine-readable summary."""

from __future__ import print_function

import argparse
import hashlib
import json
import re
from pathlib import Path


def _sha256(path):
    """Return a content digest without relying on file timestamps."""

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _scalar_table(path):
    """Parse the compiler's whitespace-separated scalar datatable entries."""

    values = {}
    for line in Path(path).read_text(encoding="ascii").splitlines():
        fields = line.split()
        if len(fields) == 2:
            try:
                values[fields[0]] = float(fields[1])
            except ValueError:
                pass
    return values


def summarize(run_root):
    """Validate independent views and create delivery_manifest.json once."""

    run_root = Path(run_root).resolve()
    output = run_root / "rom_compiler" / "output"
    evidence = run_root / "rom_compiler" / "evidence"
    content_manifest = json.loads((
        run_root / "rom_content" / "rom_content_manifest.json").read_text(
            encoding="ascii"))
    paths = {
        "verilog": output / "CNNW384X128.v",
        "verilog_rcf": output / "CNNW384X128_verilog.rcf",
        "liberty": output / "CNNW384X128_tt_1p10v_1p10v_25c.lib",
        "db": output / "CNNW384X128_tt_1p10v_1p10v_25c.db",
        "datatable": output / "CNNW384X128_tt_1p10v_1p10v_25c.dat",
        "lef": output / "CNNW384X128.lef",
        "gds2": output / "CNNW384X128.gds2",
    }
    for name, path in paths.items():
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError("missing required {} view: {}".format(name, path))

    verilog = paths["verilog"].read_text(encoding="ascii")
    liberty = paths["liberty"].read_text(encoding="ascii")
    lef = paths["lef"].read_text(encoding="ascii")
    if "module CNNW384X128" not in verilog:
        raise ValueError("Verilog model has the wrong macro name")
    if not re.search(r"cell\s*\(CNNW384X128\)\s*\{", liberty):
        raise ValueError("Liberty view has the wrong macro name")
    if not re.search(r"^MACRO CNNW384X128$", lef, re.MULTILINE):
        raise ValueError("LEF view has the wrong macro name")

    # Check the aggregate functional interface in the Verilog declaration.
    # Physical power pins are conditional and intentionally excluded from the
    # RTL adapter interface; all normal/test pins must still be present.
    expected_ports = {"CENY", "AY", "Q", "CLK", "CEN", "A", "EMA",
                      "TEN", "BEN", "TCEN", "TA", "TQ", "PGEN", "KEN"}
    declaration = re.search(
        r"module CNNW384X128 \((.*?)\);", verilog, re.DOTALL)
    if declaration is None:
        raise ValueError("cannot parse Verilog macro declaration")
    observed_ports = set(re.findall(r"\b[A-Z][A-Z0-9]*\b",
                                    declaration.group(1)))
    observed_ports.discard("VDDE")
    observed_ports.discard("VSSE")
    if observed_ports != expected_ports:
        raise ValueError("Verilog port set differs from the frozen adapter")

    # Liberty declares unrelated wire-loading areas before the macro.  Bind
    # the physical-area match to the named cell block so the result cannot
    # accidentally accept the library's illustrative wire-load value.
    area_match = re.search(
        r"cell\s*\(CNNW384X128\)\s*\{.*?\barea\s*:\s*([0-9.]+)\s*;",
        liberty, re.DOTALL)
    size_match = re.search(
        r"^\s*SIZE\s+([0-9.]+)\s+BY\s+([0-9.]+)\s*;",
        lef, re.MULTILINE)
    if area_match is None or size_match is None:
        raise ValueError("cannot parse ROM physical dimensions")
    width = float(size_match.group(1))
    height = float(size_match.group(2))
    area = float(area_match.group(1))
    # Inputs carry six decimal places at most.  A millith-square-micron
    # tolerance absorbs binary floating-point conversion only; it is far
    # below a physical database-grid discrepancy.
    if abs(width * height - area) > 1.0e-3:
        raise ValueError("LEF dimensions and Liberty area disagree")

    table = _scalar_table(paths["datatable"])
    required_scalars = ("geomx", "geomy", "tcyc_ema2ken1",
                        "taccq_ema2ken1", "tas", "tah",
                        "icc_ema2ken1", "icc_peak")
    if any(name not in table for name in required_scalars):
        raise ValueError("datatable lacks required TT metric")
    if table["tcyc_ema2ken1"] > 2.0:
        raise ValueError("ROM TT cycle time exceeds the 500 MHz acceptance period")
    if paths["verilog_rcf"].read_bytes() != (
            run_root / "rom_content" / "CNNW384X128.rcf").read_bytes():
        raise ValueError("compiler-copied simulation RCF differs from input RCF")

    manifest_path = output / "delivery_manifest.json"
    if manifest_path.exists():
        raise ValueError("refusing to overwrite existing delivery manifest")
    manifest = {
        "schema_version": 1,
        "instance_name": "CNNW384X128",
        "geometry": {"words": 384, "bits": 128, "mux": 8,
                     "width_um": width, "height_um": height,
                     "area_um2": area},
        "normal_mode": {"EMA": "010", "KEN": 1},
        "tt_1p10v_25c": {
            "acceptance_period_ns": 2.0,
            "minimum_cycle_ns": table["tcyc_ema2ken1"],
            "clock_to_q_ns": table["taccq_ema2ken1"],
            "address_setup_ns": table["tas"],
            "address_hold_ns": table["tah"],
            "read_current_ma_at_500mhz_100pct": table["icc_ema2ken1"],
            "peak_current_ma": table["icc_peak"],
            "scope": "TT baseline only; not full-PVT signoff",
        },
        "ports": sorted(expected_ports),
        "source_rcf_sha256": content_manifest["files"][
            "CNNW384X128.rcf"]["sha256"],
        "files": {name: {"path": path.name, "bytes": path.stat().st_size,
                          "sha256": _sha256(path)}
                  for name, path in sorted(paths.items())},
        "evidence": {
            "compiler_log": str((evidence / "compiler.stdout").relative_to(
                run_root)),
            "library_compiler_report": str((
                evidence / "lc_report_lib.rpt").relative_to(run_root)),
            "dc_read_db_report": str((
                evidence / "dc_report_lib_cell.rpt").relative_to(run_root)),
        },
    }
    manifest_path.write_text(json.dumps(
        manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    return manifest


def main():
    """Parse the task-scoped run root and print the accepted summary."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", required=True)
    arguments = parser.parse_args()
    print(json.dumps(summarize(arguments.run_root), sort_keys=True))


if __name__ == "__main__":
    main()
