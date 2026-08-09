#!/usr/bin/env python3
"""Discover the exact SMIC40LL cells used by the standalone FTC reproduction.

The FTC electrical decks instantiate CDL subcircuits positionally, while the
structural RTL instantiates powered Verilog cell models by name.  This helper
reads both source views and emits one small selection record so neither deck
generation nor RTL has to guess a port order or sequential-cell polarity.
"""

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List


# These are immutable installed-library sources already used by the delay-chain
# work.  FTC has its own provenance record even though it does not copy PDK
# collateral into the repository.
RVT_CDL = Path(
    "/home/zhupl25/chiplet_side_channel/chiplet_gds_data/chiplets/FIR/syn/runs/"
    "fir_smic40ll_tt_1310ps_spice_20260722_r1/spice/"
    "sc9mc_logic0040ll_base_rvt_c40.hspice.cdl"
)
RVT_VERILOG = Path(
    "/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/"
    "SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1/"
    "verilog/sc9mc_logic0040ll_base_rvt_c40.v"
)
LVT_CDL = Path(
    "/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/"
    "SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_lvt_c40/r0p1/"
    "cdl/sc9mc_logic0040ll_base_lvt_c40.cdl"
)
LVT_VERILOG = Path(
    "/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/"
    "SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_lvt_c40/r0p1/"
    "verilog/sc9mc_logic0040ll_base_lvt_c40.v"
)

SUBCKT_RE = re.compile(r"^\s*\.subckt\s+(\S+)\s*(.*)$", re.IGNORECASE)


def parse_subckts(path: Path) -> Dict[str, List[str]]:
    """Return CDL public ports, preserving their required positional order."""

    if not path.is_file():
        raise ValueError("required CDL is unavailable: {}".format(path))
    result: Dict[str, List[str]] = {}
    for line in path.read_text(encoding="latin-1", errors="replace").splitlines():
        match = SUBCKT_RE.match(line)
        if match:
            result[match.group(1)] = match.group(2).split()
    if not result:
        raise ValueError("no CDL subcircuits found: {}".format(path))
    return result


def powered_module_ports(text: str, cell: str) -> List[str]:
    """Find the powered Verilog view used by structural FTC RTL.

    Vendor Verilog files contain multiple views of the same cell.  The FTC
    wrappers require the view whose public interface explicitly includes VDD
    and VSS; the timing-only cell view is not an acceptable RTL substitute.
    """

    pattern = re.compile(r"module\s+{}\s*\(([^;]+)\);".format(re.escape(cell)), re.DOTALL)
    for match in pattern.finditer(text):
        ports = [item.strip() for item in match.group(1).replace("\n", " ").split(",")]
        if "VDD" in ports and "VSS" in ports:
            return ports
    raise ValueError("powered Verilog module is unavailable: {}".format(cell))


def require_cell(
    cdl: Dict[str, List[str]], verilog: str, cell: str, expected_ports: List[str],
    vt_class: str, truth_function: str, extra_evidence: str = "",
) -> Dict[str, Any]:
    """Validate one selected cell and return its explicit implementation record."""

    actual = cdl.get(cell)
    if actual != expected_ports:
        raise ValueError("{} CDL ports {} do not match {}".format(cell, actual, expected_ports))
    ports = powered_module_ports(verilog, cell)
    if extra_evidence and extra_evidence not in verilog:
        raise ValueError("{} functional evidence is absent for {}".format(extra_evidence, cell))
    return {
        "cell": cell,
        "vt_class": vt_class,
        "cdl_ports": actual,
        "verilog_ports": ports,
        "power_well_mapping": {"VDD": "VDD_A", "VNW": "VDD_A", "VPW": "VSS_A", "VSS": "VSS_A"},
        "truth_function": truth_function,
    }


def discover() -> Dict[str, Any]:
    """Construct the FTC cell contract from real SMIC40LL library sources."""

    for source in (RVT_CDL, RVT_VERILOG, LVT_CDL, LVT_VERILOG):
        if not source.is_file():
            raise ValueError("required source is unavailable: {}".format(source))
    rvt_cdl = parse_subckts(RVT_CDL)
    lvt_cdl = parse_subckts(LVT_CDL)
    rvt_verilog = RVT_VERILOG.read_text(encoding="latin-1", errors="replace")
    lvt_verilog = LVT_VERILOG.read_text(encoding="latin-1", errors="replace")

    # Matching X0P7M buffers preserve the paper's non-inverting buffer-line
    # topology and avoid inventing a two-inverter substitute where it is not
    # needed.  Their direct CDC ports also keep every observable tap polarity.
    rvt_buffer = require_cell(
        rvt_cdl, rvt_verilog, "BUF_X0P7M_A9TR40",
        ["Y", "VDD", "VNW", "VPW", "VSS", "A"], "RVT", "Y = A",
    )
    lvt_buffer = require_cell(
        lvt_cdl, lvt_verilog, "BUF_X0P7M_A9TL40",
        ["Y", "VDD", "VNW", "VPW", "VSS", "A"], "LVT", "Y = A",
    )
    xor2 = require_cell(
        rvt_cdl, rvt_verilog, "XOR2_X0P5M_A9TR40",
        ["Y", "VDD", "VNW", "VPW", "VSS", "A", "B"], "RVT", "Y = A XOR B", "xor I0",
    )
    latch = require_cell(
        rvt_cdl, rvt_verilog, "LATQ_X0P5M_A9TR40",
        ["Q", "VDD", "VNW", "VPW", "VSS", "D", "G"], "RVT", "Q follows D while G is high",
        "$setuphold(negedge G",
    )
    latch.update({"enable_pin": "G", "enable_polarity": "active_high", "output_pin": "Q"})
    dff = require_cell(
        rvt_cdl, rvt_verilog, "DFFRPQ_X0P5M_A9TR40",
        ["Q", "VDD", "VNW", "VPW", "VSS", "CK", "D", "R"], "RVT",
        "Q samples D on CK rising edge; R asynchronously clears Q", "$setuphold(posedge CK",
    )
    dff.update({"clock_pin": "CK", "clock_polarity": "positive_edge", "reset_pin": "R", "reset_polarity": "active_high_async_clear"})

    return {
        "schema_version": 1,
        "technology": "SMIC40LL",
        "mapping_note": "FTC HVT path is intentionally mapped to RVT; target library has no HVT selection.",
        "source_files": {
            "rvt_cdl": str(RVT_CDL), "rvt_verilog": str(RVT_VERILOG),
            "lvt_cdl": str(LVT_CDL), "lvt_verilog": str(LVT_VERILOG),
        },
        "delay_rvt": rvt_buffer,
        "delay_lvt": lvt_buffer,
        "xor2": xor2,
        "latch": latch,
        "dff": dff,
    }


def render_report(cells: Dict[str, Any]) -> str:
    """Render concise human-readable cell provenance from the machine record."""

    lines = [
        "# FTC Cell Discovery", "",
        "This is an FTC-style RVT/LVT reproduction: the original HVT path is mapped to RVT because no HVT library is selected.", "",
        "| Role | Cell | Vt | CDL ports | Function |", "|---|---|---|---|---|",
    ]
    for role in ("delay_rvt", "delay_lvt", "xor2", "latch", "dff"):
        item = cells[role]
        lines.append("| {} | `{}` | {} | `{}` | {} |".format(role, item["cell"], item["vt_class"], " ".join(item["cdl_ports"]), item["truth_function"]))
    lines.extend([
        "", "All supply and well pins map to the sole FTC rail pair: `VDD/VNW -> VDD_A`, `VPW/VSS -> VSS_A`.",
        "The latch is a real active-high transparent latch; the DFF is a real positive-edge, active-high asynchronous-clear register.", "",
    ])
    return "\n".join(lines)


def main(argv: Iterable[str] = None) -> int:
    """Write FTC-owned discovery evidence without altering library collateral."""

    parser = argparse.ArgumentParser(description="discover SMIC40LL FTC cells")
    parser.add_argument("--output-dir", required=True, type=Path, help="FTC discovery directory")
    args = parser.parse_args(argv)
    cells = discover()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "selected_cells.json").write_text(json.dumps(cells, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    # ``output_dir`` is the FTC ``discovery`` directory, so its direct parent
    # is the independent task root that also owns the human-readable report.
    report = args.output_dir.parent / "reports" / "CELL_DISCOVERY.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(render_report(cells), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
