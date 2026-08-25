#!/usr/bin/env python3
"""Freeze the zero-HSPICE B-FE2 real-latch electrical contract.

This module is deliberately an evidence builder, not a circuit renderer.  It
audits the exact production latch sources which the later HSPICE deck must
instantiate and records the electrical-signature fields and scenario budgets
that prevent accidental repeated simulation.  It never invokes HSPICE.
"""

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping


FTC_ROOT = Path(__file__).resolve().parents[1]
ANALYSIS_ROOT = FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe2_real_latch"
BFE1R_STATUS = FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe1_spatial_observability" / "BFE1R_REVIEW_STATUS.json"
BFE1R_EVIDENCE = FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe1_spatial_observability" / "BFE1R_EVIDENCE_MANIFEST.json"

# These are the single vendor source set used for the selected RVT latch.
# They are intentionally not taken from historical generated run collateral.
RVT_CDL = Path("/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1/cdl/sc9mc_logic0040ll_base_rvt_c40.cdl")
RVT_VERILOG = Path("/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1/verilog/sc9mc_logic0040ll_base_rvt_c40.v")
RVT_LIB = Path("/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1/lib/sc9mc_logic0040ll_base_rvt_c40_tt_typical_max_1p10v_25c.lib")
LATCH_CELL = "LATQ_X0P5M_A9TR40"
LATCH_CDL_PORTS = ["Q", "VDD", "VNW", "VPW", "VSS", "D", "G"]


def sha256_file(path: Path) -> str:
    """Return one streaming SHA256 digest without loading a source wholesale."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> Dict[str, Any]:
    """Read one object-shaped compact evidence artifact."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def cell_block(text: str, marker: str, name: str) -> str:
    """Extract a named top-level Liberty cell block using brace balancing."""

    start = text.find(marker.format(name))
    if start < 0:
        raise ValueError("cell block absent: {}".format(name))
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    raise ValueError("unterminated cell block: {}".format(name))


def named_block(text: str, marker: str) -> str:
    """Extract one brace-balanced nested Liberty block from its exact marker."""

    start = text.find(marker)
    if start < 0:
        raise ValueError("Liberty block absent: {}".format(marker))
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    raise ValueError("unterminated Liberty block: {}".format(marker))


def extract_timing_constraints(pin_block: str) -> List[Dict[str, Any]]:
    """Preserve latch setup/hold/gating timing metadata without inventing values."""

    records = []
    cursor = 0
    while True:
        start = pin_block.find("timing()", cursor)
        if start < 0:
            break
        timing = named_block(pin_block[start:], "timing()")
        cursor = start + len(timing)
        timing_type = re.search(r"timing_type\s*:\s*([^;]+)", timing)
        related = re.search(r"related_pin\s*:\s*\"([^\"]+)\"", timing)
        if timing_type is None and related is None:
            continue
        records.append({
            "related_pin": related.group(1) if related else None,
            "timing_type": timing_type.group(1).strip() if timing_type else None,
            "constraint_tables": sorted(set(re.findall(r"\b([a-z_]+constraint)\(", timing))),
        })
    return records


def audit_latch_cell() -> Dict[str, Any]:
    """Audit physical and digital latch interfaces from the vendor sources."""

    for path in (RVT_CDL, RVT_VERILOG, RVT_LIB):
        if not path.is_file():
            raise FileNotFoundError("B-FE2 latch source is unavailable: {}".format(path))
    cdl = RVT_CDL.read_text(encoding="utf-8", errors="replace")
    cdl_header = re.search(r"(?im)^\.SUBCKT\s+{}\s+([^\n]+)".format(LATCH_CELL), cdl)
    if cdl_header is None:
        raise ValueError("latch CDL subcircuit is absent")
    cdl_ports = cdl_header.group(1).split()
    if cdl_ports != LATCH_CDL_PORTS:
        raise ValueError("latch CDL port order changed: {}".format(cdl_ports))
    verilog = RVT_VERILOG.read_text(encoding="utf-8", errors="replace")
    # The library contains power-aware and compact models.  The power-aware
    # declaration is required because it exposes VDD/VSS used by integration.
    powered = re.search(r"module\s+{}\s*\(Q,\s*VDD,\s*VSS,\s*D,\s*G\)".format(LATCH_CELL), verilog)
    if powered is None:
        raise ValueError("powered latch Verilog declaration is absent")
    lib_block = cell_block(RVT_LIB.read_text(encoding="utf-8", errors="replace"), "  cell({})", LATCH_CELL)
    latch_decl = re.search(r"latch\([^)]*\)\s*\{\s*enable\s*:\s*\"([^\"]+)\"\s*;\s*data_in\s*:\s*\"([^\"]+)\"", lib_block, re.S)
    if latch_decl is None or latch_decl.group(1) != "G" or latch_decl.group(2) != "D":
        raise ValueError("Liberty does not identify active-high G / D latch semantics")
    pins = {}
    for pin in ("D", "G"):
        block = named_block(lib_block, "pin({})".format(pin))
        capacitance = re.search(r"capacitance\s*:\s*([0-9.eE+-]+)", block)
        if capacitance is None:
            raise ValueError("Liberty capacitance is absent: {}".format(pin))
        pins[pin] = {"capacitance": float(capacitance.group(1)), "timing_constraints": extract_timing_constraints(block)}
    return {
        "cell": LATCH_CELL,
        "vt_class": "RVT",
        "cdl_ports": cdl_ports,
        "verilog_powered_ports": ["Q", "VDD", "VSS", "D", "G"],
        "port_semantics": {
            "Q": "latched output", "D": "data input", "G": "active-high transparent gate",
            "VDD/VNW": "PD_SENSE/VDD_MONITORED", "VPW/VSS": "PD_SENSE ground/vss_a",
        },
        "liberty": {"path": str(RVT_LIB), "sha256": sha256_file(RVT_LIB), "inputs": pins},
        "cdl": {"path": str(RVT_CDL), "sha256": sha256_file(RVT_CDL)},
        "verilog": {"path": str(RVT_VERILOG), "sha256": sha256_file(RVT_VERILOG)},
    }


def build_contract() -> Dict[str, Any]:
    """Build B-FE2 frozen inputs, signature schema, and bounded run budgets."""

    status = read_json(BFE1R_STATUS)
    evidence = read_json(BFE1R_EVIDENCE)
    ready = status.get("gate") == "BFE1R_READY_FOR_BFE2"
    return {
        "schema_version": 1,
        "stage": "B-FE2.0",
        "gate": "BFE2_0_LATCH_CONTRACT_READY" if ready else "BFE2_0_LATCH_CONTRACT_BLOCKED",
        "block_reason": None if ready else "B-FE1R gate is not ready",
        "new_hspice_scenarios": 0,
        "formal_latch": LATCH_CELL,
        "frontend_power_semantics": "all XOR and latch cells use PD_SENSE/VDD_MONITORED; G is an ideal external research source",
        "research_g_edge": {"transition_ps": 1.0, "meaning": "B-FE2 latch-intrinsic study only; not B-FE3 clock-tree signoff"},
        "signature_fields": ["topology_version", "rvt_lvt_buffer_cells", "xor_cell", "latch_cell", "supply_pwl", "s_clk_pwl", "g_pwl", "close_ps", "model_sha256", "hspice_version", "tran_step_ps"],
        "scenario_budgets": {"bfe2_1_latch_load": 4, "bfe2_2_real_snapshot": 8, "bfe2_3_close_aperture_additional": 16},
        "bfe1r_status_sha256": sha256_file(BFE1R_STATUS),
        "bfe1r_evidence_sha256": sha256_file(BFE1R_EVIDENCE),
    }


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Write deterministic compact JSON under the dedicated B-FE2 evidence root."""

    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    """Generate the three B-FE2.0 artifacts without creating a simulation run."""

    contract = build_contract()
    audit = audit_latch_cell()
    ANALYSIS_ROOT.mkdir(parents=True, exist_ok=True)
    write_json(ANALYSIS_ROOT / "BFE2_0_CONTRACT.json", contract)
    write_json(ANALYSIS_ROOT / "BFE2_0_LATCH_CELL_AUDIT.json", audit)
    write_json(ANALYSIS_ROOT / "BFE2_0_EVIDENCE_BASELINE.json", {
        "schema_version": 1, "stage": "B-FE2.0", "new_hspice_scenarios": 0,
        "contract_sha256": sha256_file(ANALYSIS_ROOT / "BFE2_0_CONTRACT.json"),
        "latch_audit_sha256": sha256_file(ANALYSIS_ROOT / "BFE2_0_LATCH_CELL_AUDIT.json"),
        "bfe1r_status_sha256": contract["bfe1r_status_sha256"],
        "bfe1r_evidence_sha256": contract["bfe1r_evidence_sha256"],
    })
    print(contract["gate"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
