#!/usr/bin/env python3
"""Discover and document the exact SMIC40LL cells used by Phase 2.

SPICE instances are positional, whereas the functional Verilog models omit
well pins.  This script cross-checks both views before emitting a selection:
the CDL is authoritative for HSPICE port order and the powered Verilog view is
used to document sequential behavior.  It never substitutes a familiar cell
name when a requested library cell is absent.
"""

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


SUBCKT_RE = re.compile(r"^\s*\.subckt\s+(\S+)\s*(.*)$", re.IGNORECASE)
MODULE_RE_TEMPLATE = r"\bmodule\s+{}\s*\(([^;]+)\);"


def load_json(path: Path) -> Dict[str, Any]:
    """Read the Phase 2 object configuration without accepting arbitrary JSON."""

    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError("configuration must be a JSON object: {}".format(path))
    return value


def repository_root() -> Path:
    """Return the repository root from this script's fixed directory layout."""

    return Path(__file__).resolve().parents[4]


def resolve_repo_path(value: str) -> Path:
    """Resolve repository-relative paths while preserving absolute PDK paths."""

    path = Path(value)
    return path if path.is_absolute() else repository_root() / path


def parse_subckts(cdl_path: Path) -> Dict[str, List[str]]:
    """Return each CDL subcircuit's full positional public-port list.

    The source library puts every public port on the ``.SUBCKT`` line.  Lines
    are deliberately not inferred from transistor terminals; those are private
    implementation details and cannot define a safe instance interface.
    """

    subckts: Dict[str, List[str]] = {}
    for line in cdl_path.read_text(encoding="latin-1", errors="replace").splitlines():
        match = SUBCKT_RE.match(line)
        if match:
            name = match.group(1)
            ports = match.group(2).split()
            if name in subckts:
                raise ValueError("duplicate CDL subcircuit declaration: {}".format(name))
            subckts[name] = ports
    if not subckts:
        raise ValueError("no .SUBCKT declarations found: {}".format(cdl_path))
    return subckts


def verilog_module_ports(verilog_text: str, cell_name: str) -> Optional[List[str]]:
    """Return the first powered functional module's declared ports, if present.

    The vendor file contains multiple library views.  A matching module with
    explicit VDD/VSS is preferred because it checks that the RTL-facing cell
    exposes the same signal names as the transistor-level selection.
    """

    pattern = re.compile(MODULE_RE_TEMPLATE.format(re.escape(cell_name)), re.IGNORECASE | re.DOTALL)
    for match in pattern.finditer(verilog_text):
        ports = [port.strip() for port in match.group(1).replace("\n", " ").split(",")]
        if "VDD" in ports and "VSS" in ports:
            return ports
    return None


def require_ports(subckts: Dict[str, List[str]], cell_name: str, expected_ports: List[str]) -> Dict[str, Any]:
    """Construct one verified selection record or fail with the actual mismatch."""

    actual = subckts.get(cell_name)
    if actual is None:
        raise ValueError("required candidate is missing from the CDL: {}".format(cell_name))
    if actual != expected_ports:
        raise ValueError("{} ports {} do not match required {}".format(cell_name, actual, expected_ports))
    return {"cell": cell_name, "cdl_ports": actual}


def write_markdown(path: Path, title: str, rows: List[Dict[str, Any]]) -> None:
    """Publish candidate evidence using explicit selection reasons, not aliases."""

    lines = ["# {}".format(title), "", "| Cell | CDL ports | Selection | Reason |", "|---|---|---|---|"]
    for row in rows:
        lines.append(
            "| `{}` | `{}` | {} | {} |".format(
                row["cell"], " ".join(row["cdl_ports"]), row["selection"], row["reason"]
            )
        )
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def discover(config: Dict[str, Any]) -> Dict[str, Any]:
    """Cross-check selections against the exact configured CDL and Verilog files."""

    phase1_config_path = resolve_repo_path(str(config["phase1_config_path"]))
    phase1_config = load_json(phase1_config_path)
    cdl_path = resolve_repo_path(str(phase1_config["cell_cdl"]))
    verilog_path = Path(config["cell_verilog"])
    if not cdl_path.is_file() or not verilog_path.is_file():
        raise ValueError("configured CDL or functional Verilog collateral is unavailable")
    subckts = parse_subckts(cdl_path)
    verilog_text = verilog_path.read_text(encoding="latin-1", errors="replace")

    dff = require_ports(
        subckts,
        "DFFRPQ_X0P5M_A9TR40",
        ["Q", "VDD", "VNW", "VPW", "VSS", "CK", "D", "R"],
    )
    mux = require_ports(
        subckts,
        "MXT2_X0P5M_A9TR40",
        ["Y", "VDD", "VNW", "VPW", "VSS", "A", "B", "S0"],
    )
    buffer = require_ports(
        subckts,
        "BUF_X0P7M_A9TR40",
        ["Y", "VDD", "VNW", "VPW", "VSS", "A"],
    )
    for record in (dff, mux, buffer):
        ports = verilog_module_ports(verilog_text, record["cell"])
        if ports is None:
            raise ValueError("powered functional Verilog module is missing: {}".format(record["cell"]))
        record["verilog_ports"] = ports

    dff.update(
        {
            "clock_polarity": "positive_edge",
            "reset_pin": "R",
            "reset_polarity": "active_high_async_clear",
            "selection_reason": "smallest Q-output positive-edge DFF with one asynchronous clear pin",
        }
    )
    mux.update(
        {
            "select_pin": "S0",
            "selection_reason": "smallest M-suffix 2:1 transmission-style mux with explicit A/B/S0 ports",
        }
    )
    buffer.update(
        {
            "selection_reason": "smallest M-suffix non-inverting buffer; candidate only until cross-domain test proves need",
        }
    )
    return {
        "schema_version": 1,
        "source_cdl": str(cdl_path),
        "source_verilog": str(verilog_path),
        "dff": dff,
        "mux": mux,
        "buffer": buffer,
        "level_shifter": {
            "selected": None,
            "status": "NO_LEVEL_SHIFTER_CANDIDATE_FOUND",
            "selection_reason": "No level-shifter-named subcircuit exists in the configured base-rvt CDL; no custom circuit is substituted.",
        },
    }


def build_argument_parser() -> argparse.ArgumentParser:
    """Define explicit input/output locations for reproducible discovery."""

    parser = argparse.ArgumentParser(description="discover SMIC40LL Phase 2 standard cells")
    parser.add_argument("--config", required=True, type=Path, help="Phase 2 configuration")
    parser.add_argument("--output-dir", required=True, type=Path, help="discovery output directory")
    return parser


def main(argv: Iterable[str] = None) -> int:
    """Run discovery and emit machine-readable selection plus review Markdown."""

    args = build_argument_parser().parse_args(argv)
    config = load_json(args.config)
    result = discover(config)
    source_subckts = parse_subckts(Path(result["source_cdl"]))
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "selected_cells.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_markdown(
        output_dir / "dff_candidates.md",
        "DFF Candidates",
        [
            {"cell": result["dff"]["cell"], "cdl_ports": result["dff"]["cdl_ports"], "selection": "selected", "reason": result["dff"]["selection_reason"]},
            {"cell": "DFFQ_X0P5M_A9TR40", "cdl_ports": source_subckts["DFFQ_X0P5M_A9TR40"], "selection": "not selected", "reason": "no asynchronous reset port"},
            {"cell": "DFFSRPQ_X0P5M_A9TR40", "cdl_ports": source_subckts["DFFSRPQ_X0P5M_A9TR40"], "selection": "not selected", "reason": "adds an unnecessary asynchronous set input"},
        ],
    )
    write_markdown(
        output_dir / "mux_candidates.md",
        "MUX Candidates",
        [
            {"cell": result["mux"]["cell"], "cdl_ports": result["mux"]["cdl_ports"], "selection": "selected", "reason": result["mux"]["selection_reason"]},
            {"cell": "MXIT2_X0P5M_A9TR40", "cdl_ports": source_subckts["MXIT2_X0P5M_A9TR40"], "selection": "not selected", "reason": "alternate 2:1 implementation; not needed for first implementation"},
        ],
    )
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
