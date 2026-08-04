#!/usr/bin/env python3
"""Audit the frozen CNN ROM data path before gate-level power measurement.

The compiler model exposes a private ``Q_`` implementation signal, but power
analysis must observe the mapped hard macro's public ``Q`` pin.  This script
performs a text-level, fail-closed audit of the immutable adapter, mapped
netlist, compiler model, and a gate VCD.  It does not edit any design input.
"""

import argparse
import json
import re
from pathlib import Path


class RomAuditError(ValueError):
    """Raised when an immutable ROM path contract cannot be demonstrated."""


def _require_match(text, expression, description):
    """Return one required regex match or fail with an actionable contract name."""
    match = re.search(expression, text, re.DOTALL)
    if not match:
        raise RomAuditError("missing required {}".format(description))
    return match


def _vcd_names(path):
    """Return all VCD declarations that name an observable macro-Q net.

    This intentionally checks declarations rather than numeric transitions:
    Stage 2 proves hierarchy/name mapping, while Stage 4 later measures the
    annotation coverage and activity through DC/SAIF.
    """
    names, scope = [], []
    for line in path.read_text(encoding="ascii", errors="replace").splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[0] == "$scope":
            scope.append(fields[2])
        elif fields and fields[0] == "$upscope":
            if scope:
                scope.pop()
        elif len(fields) >= 5 and fields[0] == "$var":
            name = fields[4]
            if name in ("weight_word", "Q", "macro_q"):
                names.append("/".join(scope + [name]))
    return sorted(set(names))


def audit(adapter, mapped_netlist, compiler_model, gate_vcd):
    """Return a serializable record proving the public-Q observability chain."""
    adapter_text = adapter.read_text(encoding="utf-8")
    mapped_text = mapped_netlist.read_text(encoding="ascii", errors="replace")
    model_text = compiler_model.read_text(encoding="ascii", errors="replace")

    adapter_instance = _require_match(
        adapter_text, r"CNNW384X128\s+(u_weight_rom)\s*\(", "RTL ROM instance"
    ).group(1)
    _require_match(adapter_text, r"\.Q\s*\(\s*macro_q\s*\)", "RTL public-Q wiring")
    _require_match(adapter_text, r"\.A\s*\(\s*read_address\s*\)", "RTL address wiring")
    _require_match(adapter_text, r"\.CEN\s*\(\s*~read_enable\s*\)", "RTL CEN contract")
    _require_match(adapter_text, r"\.CLK\s*\(\s*clk\s*\)", "RTL clock contract")

    macro_matches = list(re.finditer(r"CNNW384X128\s+u_weight_rom\s*\(", mapped_text))
    if len(macro_matches) != 1:
        raise RomAuditError("mapped netlist has {} CNNW384X128 instances, expected 1".format(
            len(macro_matches)))
    # Restrict the inspected cell body to the mapped adapter module so another
    # generated module cannot accidentally satisfy a pin-name search.
    mapped_adapter = _require_match(
        mapped_text, r"module\s+cnn_weight_rom\s*\(.*?\nendmodule", "mapped ROM adapter"
    ).group(0)
    q_match = _require_match(
        mapped_adapter, r"\.Q\s*\(\s*(weight_word)\s*\)", "mapped public-Q consumer net"
    )
    _require_match(mapped_adapter, r"\.A\s*\(\s*read_address\s*\)", "mapped address contract")
    _require_match(mapped_adapter, r"\.CEN\s*\(\s*n1\s*\)", "mapped active-low CEN net")
    _require_match(mapped_adapter, r"INV\w*\s+\w+\s*\(\s*\.A\(read_enable\),\s*\.Y\(n1\)",
                   "mapped CEN inversion")

    _require_match(model_text, r"\boutput\b[^;]*\bQ\b", "compiler public Q declaration")
    _require_match(model_text, r"\bQ_\b", "compiler internal Q_ declaration")
    vcd_q_names = _vcd_names(gate_vcd)
    if not any(name.endswith("/weight_word") for name in vcd_q_names):
        raise RomAuditError("gate VCD has no declared mapped public-Q consumer net weight_word")

    return {
        "status": "PASS",
        "rtl_adapter_instance": adapter_instance,
        "mapped_rom_instance_path": "cnn_weight_rom.u_weight_rom",
        "mapped_public_q_pin": "Q",
        "mapped_public_q_consumer_net": q_match.group(1),
        "compiler_public_q": "Q",
        "compiler_internal_q": "Q_",
        "address_contract": "A(read_address)",
        "control_contract": "CEN(~read_enable), CLK(clk)",
        "gate_vcd_public_q_hierarchies": vcd_q_names,
        "saif_expected_rom_output_hierarchy": "dut.convolution_engine.weight_rom.weight_word",
    }


def main():
    """Run the audit and write only the caller-selected task-scoped output."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", required=True, type=Path)
    parser.add_argument("--mapped-netlist", required=True, type=Path)
    parser.add_argument("--compiler-model", required=True, type=Path)
    parser.add_argument("--gate-vcd", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("refusing to overwrite ROM audit {}".format(args.output))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(audit(args.adapter, args.mapped_netlist,
                                            args.compiler_model, args.gate_vcd),
                                      indent=2, sort_keys=True) + "\n", encoding="ascii")


if __name__ == "__main__":
    main()
