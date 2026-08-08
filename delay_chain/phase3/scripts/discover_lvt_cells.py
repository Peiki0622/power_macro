#!/usr/bin/env python3
"""Discover the small, real SMIC40LL LVT inverter set used by Phase 3.

The vendor files contain several Verilog views for the same logical cell.  The
powered view is selected for RTL packaging, while the CDL declaration remains
the source of truth for HSPICE positional ports.  This script intentionally
only handles the first three M-drive LVT inverter candidates; it is not a
general standard-cell database generator.
"""

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


SUBCKT_RE = re.compile(r"^\s*\.subckt\s+(\S+)\s*(.*)$", re.IGNORECASE)
# Cell names contain underscores between the drive suffix and library suffix;
# accepting only alphanumeric characters would silently miss every real INV
# module even though its CDL declaration was found successfully.
# The same parser is also used to verify the four already-selected RVT cells;
# therefore the module name must cover DFF/BUF/MUX as well as INV.
MODULE_RE = re.compile(r"\bmodule\s+([A-Za-z0-9_]+)\s*\(([^;]+)\);", re.IGNORECASE | re.DOTALL)
LVT_INV_RE = re.compile(r"^INV_(X[0-9P]+M)_A9TL40$", re.IGNORECASE)
DRIVE_RE = re.compile(r"X([0-9]+(?:P[0-9]+)?)M", re.IGNORECASE)

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_RVT_CDL = (
    REPO_ROOT
    / "chiplets/FIR/syn/runs/fir_smic40ll_tt_1310ps_spice_20260722_r1/spice/"
    / "sc9mc_logic0040ll_base_rvt_c40.hspice.cdl"
)
DEFAULT_RVT_VERILOG = Path(
    "/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/"
    "SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1/verilog/"
    "sc9mc_logic0040ll_base_rvt_c40.v"
)
DEFAULT_LVT_CDL = Path(
    "/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/"
    "SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_lvt_c40/r0p1/cdl/"
    "sc9mc_logic0040ll_base_lvt_c40.cdl"
)
DEFAULT_LVT_VERILOG = Path(
    "/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/"
    "SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_lvt_c40/r0p1/verilog/"
    "sc9mc_logic0040ll_base_lvt_c40.v"
)


def load_json(path: Path) -> Dict[str, Any]:
    """Read a JSON object and reject arrays or scalar configuration values."""

    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def parse_subckts(path: Path) -> Dict[str, List[str]]:
    """Return complete public CDL port lists keyed by exact subcircuit name."""

    result: Dict[str, List[str]] = {}
    for line in path.read_text(encoding="latin-1", errors="replace").splitlines():
        match = SUBCKT_RE.match(line)
        if not match:
            continue
        name = match.group(1)
        if name in result:
            raise ValueError("duplicate CDL declaration: {} ({})".format(name, path))
        result[name] = match.group(2).split()
    if not result:
        raise ValueError("no CDL subcircuits found: {}".format(path))
    return result


def parse_powered_verilog_ports(path: Path) -> Dict[str, List[str]]:
    """Choose powered Verilog views, ignoring the vendor's signal-only views."""

    result: Dict[str, List[str]] = {}
    text = path.read_text(encoding="latin-1", errors="replace")
    for match in MODULE_RE.finditer(text):
        cell = match.group(1)
        ports = [port.strip() for port in match.group(2).replace("\n", " ").split(",")]
        if "VDD" in ports and "VSS" in ports and cell not in result:
            result[cell] = ports
    return result


def drive_strength(cell: str) -> float:
    """Convert the library X0P5M-style suffix to a comparable numeric value."""

    match = DRIVE_RE.search(cell)
    if not match:
        raise ValueError("cannot parse drive strength from {}".format(cell))
    token = match.group(1).upper().replace("P", ".")
    return float(token)


def require_file(path: Path, description: str) -> Path:
    """Fail before output creation when a required foundry collateral file is absent."""

    resolved = path.resolve()
    if not resolved.is_file() or resolved.stat().st_size == 0:
        raise ValueError("{} is missing or empty: {}".format(description, resolved))
    return resolved


def discover(config: Dict[str, Any], rvt_cdl: Path, rvt_verilog: Path, lvt_cdl: Path, lvt_verilog: Path) -> Dict[str, Any]:
    """Build the selected-cell manifest from traceable installed source files."""

    rvt_cdl = require_file(rvt_cdl, "RVT CDL")
    rvt_verilog = require_file(rvt_verilog, "RVT Verilog")
    lvt_cdl = require_file(lvt_cdl, "LVT CDL")
    lvt_verilog = require_file(lvt_verilog, "LVT Verilog")
    lvt_subckts = parse_subckts(lvt_cdl)
    lvt_powered = parse_powered_verilog_ports(lvt_verilog)
    candidates = []
    for cell, ports in lvt_subckts.items():
        if not LVT_INV_RE.match(cell) or cell not in lvt_powered:
            continue
        if ports != ["Y", "VDD", "VNW", "VPW", "VSS", "A"]:
            continue
        candidates.append(
            {
                "cell": cell,
                "cdl_source_path": str(lvt_cdl),
                "verilog_source_path": str(lvt_verilog),
                "cdl_ports": ports,
                "verilog_ports": lvt_powered[cell],
                "drive_strength": drive_strength(cell),
            }
        )
    candidates.sort(key=lambda item: (abs(item["drive_strength"] - 0.5), item["drive_strength"], item["cell"]))
    candidates = candidates[:3]
    if not candidates:
        raise ValueError("no usable powered LVT M-drive inverter was found")

    rvt_subckts = parse_subckts(rvt_cdl)
    rvt_powered = parse_powered_verilog_ports(rvt_verilog)
    rvt_names = [
        str(config["rvt_inverter_cell"]),
        str(config["rvt_dff_cell"]),
        str(config["rvt_buffer_cell"]),
        str(config["rvt_mux_cell"]),
    ]
    rvt_cells = {}
    for cell in rvt_names:
        if cell not in rvt_subckts or cell not in rvt_powered:
            raise ValueError("required RVT cell is absent from both views: {}".format(cell))
        rvt_cells[cell] = {
            "cdl_source_path": str(rvt_cdl),
            "verilog_source_path": str(rvt_verilog),
            "cdl_ports": rvt_subckts[cell],
            "verilog_ports": rvt_powered[cell],
        }
    return {
        "schema_version": 1,
        "technology": config["technology"],
        "rvt_cells": rvt_cells,
        "lvt_inverter_candidates": candidates,
        "source_files": {
            "rvt_cdl": str(rvt_cdl),
            "rvt_verilog": str(rvt_verilog),
            "lvt_cdl": str(lvt_cdl),
            "lvt_verilog": str(lvt_verilog),
        },
    }


def write_markdown(path: Path, result: Dict[str, Any]) -> None:
    """Publish compact human-readable evidence without copying library text."""

    lines = [
        "# LVT Inverter Candidates",
        "",
        "Source CDL: `{}`".format(result["source_files"]["lvt_cdl"]),
        "Source Verilog: `{}`".format(result["source_files"]["lvt_verilog"]),
        "",
        "| Candidate | Drive | CDL ports | Verilog ports |",
        "|---|---:|---|---|",
    ]
    for item in result["lvt_inverter_candidates"]:
        lines.append(
            "| `{}` | {:.2f} | `{}` | `{}` |".format(
                item["cell"], item["drive_strength"], " ".join(item["cdl_ports"]), " ".join(item["verilog_ports"])
            )
        )
    lines.extend(["", "Selection is limited to powered M-drive LVT inverters nearest to RVT X0P5M.", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def build_argument_parser() -> argparse.ArgumentParser:
    """Expose explicit paths so a future library revision cannot be implicit."""

    parser = argparse.ArgumentParser(description="discover Phase 3 SMIC40LL LVT inverter cells")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--rvt-cdl", type=Path, default=DEFAULT_RVT_CDL)
    parser.add_argument("--rvt-verilog", type=Path, default=DEFAULT_RVT_VERILOG)
    parser.add_argument("--lvt-cdl", type=Path, default=DEFAULT_LVT_CDL)
    parser.add_argument("--lvt-verilog", type=Path, default=DEFAULT_LVT_VERILOG)
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Run discovery and emit only compact manifests under the task directory."""

    args = build_argument_parser().parse_args(argv)
    config = load_json(args.config)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    result = discover(config, args.rvt_cdl, args.rvt_verilog, args.lvt_cdl, args.lvt_verilog)
    (output_dir / "lvt_inverter_candidates.json").write_text(
        json.dumps(result["lvt_inverter_candidates"], indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_markdown(output_dir / "lvt_inverter_candidates.md", result)
    selected = {
        "schema_version": 1,
        "rvt": result["rvt_cells"],
        "lvt_inverter_candidates": result["lvt_inverter_candidates"],
        "source_files": result["source_files"],
    }
    (output_dir / "selected_cells.json").write_text(json.dumps(selected, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
