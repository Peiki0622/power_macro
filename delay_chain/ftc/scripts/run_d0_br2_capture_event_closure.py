#!/usr/bin/env python3
"""Close D0-BR2 statically; this command never invokes an EDA simulator.

BR1R established that the frozen shared sensor can pipeline E0/EF/E1 at the
T0 2075 ps cadence.  BR2 is deliberately narrower: it uses the retained
crossings plus the existing RVT Liberty/CDL files to decide whether a
direction selector followed by a *stateless* falling-edge extender can create
legal DFF clock events.  It does not edit a deck, H0/M1/T0/M0, a sensor, or
runtime RTL.
"""

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Tuple


FTC_ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = FTC_ROOT / "analysis" / "d0_interleaved_capture"
BR1R = ANALYSIS / "br1r_fall_retiming" / "retiming_search_contract.json"
CONTRACT = ANALYSIS / "contract" / "D0_INTERLEAVED_CAPTURE_CONTRACT.json"
GATE = ANALYSIS / "reports" / "D0_BR_GATE_STATUS.json"
OUT = ANALYSIS / "br2_capture_event_legalizer"
REPORT = FTC_ROOT / "reports" / "FTC_D0_BR2_CAPTURE_EVENT_ARCHITECTURE_CLOSURE.md"
CELLS = FTC_ROOT / "discovery" / "selected_cells.json"
RUNTIME_PERIOD_PS = 2075.0
DFF_MIN_HIGH_PS = 1000.0
DFF_MIN_LOW_PS = 1000.0
DFF_MIN_RESET_PS = 1000.0
DFF_RECOVERY_PS = 1000.0


def read_json(path: Path) -> Dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(value), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def braced(text: str, start: int) -> str:
    """Return one Liberty brace group, starting at its opening brace."""

    opening = text.find("{", start)
    if opening < 0:
        raise ValueError("opening brace not found")
    depth = 0
    for index in range(opening, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[opening + 1:index]
    raise ValueError("unterminated brace group")


def liberty_cell(text: str, cell: str) -> str:
    marker = "cell({})".format(cell)
    start = text.find(marker)
    if start < 0:
        raise ValueError("Liberty cell missing: {}".format(cell))
    return braced(text, start)


def liberty_pin(cell_text: str, pin: str) -> str:
    marker = "pin({})".format(pin)
    start = cell_text.find(marker)
    if start < 0:
        raise ValueError("Liberty pin missing: {}".format(pin))
    return braced(cell_text, start)


def liberty_capacitance(cell_text: str, pin: str) -> float:
    match = re.search(r"\bcapacitance\s*:\s*([-+0-9.eE]+)", liberty_pin(cell_text, pin))
    if match is None:
        raise ValueError("capacitance missing for {}".format(pin))
    return float(match.group(1))


def liberty_first_rise_ps(cell_text: str, output_pin: str, related_pin: str) -> float:
    """Read the first characterized cell_rise table point, explicitly not STA."""

    output = liberty_pin(cell_text, output_pin)
    cursor = 0
    while True:
        start = output.find("timing()", cursor)
        if start < 0:
            break
        timing = braced(output, start)
        cursor = start + len("timing()")
        pin = re.search(r"\brelated_pin\s*:\s*\"([^\"]+)\"", timing)
        if pin is None or pin.group(1) != related_pin:
            continue
        rise = timing.find("cell_rise(")
        if rise < 0:
            continue
        table = braced(timing, rise)
        values = re.search(r"\bvalues\s*\(\s*\"\s*([-+0-9.eE]+)", table, re.S)
        if values is not None:
            return float(values.group(1)) * 1000.0
    raise ValueError("cell_rise arc {} -> {} missing".format(related_pin, output_pin))


def liberty_first_fall_ps(cell_text: str, output_pin: str, related_pin: str) -> float:
    output = liberty_pin(cell_text, output_pin)
    cursor = 0
    while True:
        start = output.find("timing()", cursor)
        if start < 0:
            break
        timing = braced(output, start)
        cursor = start + len("timing()")
        pin = re.search(r"\brelated_pin\s*:\s*\"([^\"]+)\"", timing)
        if pin is None or pin.group(1) != related_pin:
            continue
        fall = timing.find("cell_fall(")
        if fall < 0:
            continue
        table = braced(timing, fall)
        values = re.search(r"\bvalues\s*\(\s*\"\s*([-+0-9.eE]+)", table, re.S)
        if values is not None:
            return float(values.group(1)) * 1000.0
    raise ValueError("cell_fall arc {} -> {} missing".format(related_pin, output_pin))


def cdl_ports(text: str, cell: str) -> List[str]:
    match = re.search(r"^\.SUBCKT\s+{}\s+(.+)$".format(re.escape(cell)), text, re.M)
    if match is None:
        raise ValueError("CDL cell missing: {}".format(cell))
    return match.group(1).split()


def accounting() -> Dict[str, int]:
    return {"new_hspice_scenarios": 0, "reused_hspice_scenarios": 6,
            "reparsed_hspice_scenarios": 6, "electrically_equivalent_reuse_scenarios": 0,
            "forbidden_flow_runs": 0}


def retained_events(br1r: Mapping[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for candidate in br1r["candidate_summary"]:
        for target in candidate["target_diagnostics"]:
            wavefronts = {row["id"]: row for row in target["wavefront_analysis"]["wavefronts"]}
            e0, e1 = wavefronts["E0"], wavefronts["E1"]
            separation = (e1["nodes"]["raw_ck"]["rise_s"] - e0["nodes"]["raw_ck"]["rise_s"]) * 1.0e12
            for wavefront in (e0, e1):
                width = float(wavefront["nodes"]["raw_ck"]["width_ps"])
                rows.append({
                    "fall_offset_ps": candidate["fall_offset_ps"],
                    "scenario_key": target["scenario_key"], "event": wavefront["id"],
                    "raw_width_ps": width, "e0_to_e1_raw_rise_spacing_ps": separation,
                    "extension_min_for_ck_high_ps": DFF_MIN_HIGH_PS - width,
                    "extension_max_for_next_ck_low_ps": separation - DFF_MIN_LOW_PS - width,
                })
    return rows


def close() -> Dict[str, Any]:
    br1r, selected = read_json(BR1R), read_json(CELLS)
    if br1r.get("decision") != "SHARED_SENSOR_CADENCE_RETIMING_GO":
        raise RuntimeError("BR2 requires BR1R shared-sensor GO")
    if float(br1r.get("runtime_probe_period_ps", -1.0)) != RUNTIME_PERIOD_PS:
        raise RuntimeError("BR1R cadence changed")
    rvt_lib = Path(selected["source_files"]["rvt_cdl"]).parents[1] / "lib" / "sc9mc_logic0040ll_base_rvt_c40_tt_typical_max_1p10v_25c.lib"
    # The selected CDL may be a copied FIR include.  Use the frozen source's
    # sibling technology Liberty only when it exists; otherwise use its known
    # canonical library location recorded by discovery.
    if not rvt_lib.is_file():
        rvt_lib = Path("/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1/lib/sc9mc_logic0040ll_base_rvt_c40_tt_typical_max_1p10v_25c.lib")
    rvt_cdl = Path("/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_rvt_c40/r1p1/cdl/sc9mc_logic0040ll_base_rvt_c40.cdl")
    if not rvt_lib.is_file() or not rvt_cdl.is_file():
        raise RuntimeError("frozen RVT Liberty/CDL source unavailable")
    libtext, cdltext = rvt_lib.read_text(errors="replace"), rvt_cdl.read_text(errors="replace")
    cells = {name: liberty_cell(libtext, name) for name in (
        "AND2_X0P5M_A9TR40", "NAND2_X0P5M_A9TR40", "NOR2_X0P5M_A9TR40",
        "AOI21_X0P5M_A9TR40", "INV_X0P5M_A9TR40", "DLY4_X0P5M_A9TR40",
        "OR2_X0P5M_A9TR40", "DFFRPQ_X0P5M_A9TR40")}
    # BUF is LVT, so obtain its input cap from the selected LVT family below
    # rather than pretending it is present in the RVT Liberty file.
    lvt_lib = Path(selected["source_files"]["lvt_cdl"]).parents[1] / "lib" / "sc9mc_logic0040ll_base_lvt_c40_tt_typical_max_1p10v_25c.lib"
    if not lvt_lib.is_file():
        lvt_lib = Path("/host/data/libtech/SMIC_40LL/ARM_SMIC40LL_Library_20131105/SMIC_log40ll_sc9mc/arm/smic/logic0040ll/sc9mc_base_lvt_c40/r0p1/lib/sc9mc_logic0040ll_base_lvt_c40_tt_typical_max_1p10v_25c.lib")
    lvt_cdl = Path(selected["source_files"]["lvt_cdl"])
    if not lvt_cdl.is_file():
        raise RuntimeError("frozen LVT CDL source unavailable")
    medium_input_cap = liberty_capacitance(liberty_cell(lvt_lib.read_text(errors="replace"), "BUF_X0P7M_A9TL40"), "A")
    cdl_ports(lvt_cdl.read_text(errors="replace"), "BUF_X0P7M_A9TL40")
    for cell in ("AND2_X0P5M_A9TR40", "NAND2_X0P5M_A9TR40", "NOR2_X0P5M_A9TR40",
                 "AOI21_X0P5M_A9TR40", "INV_X0P5M_A9TR40", "DLY4_X0P5M_A9TR40",
                 "OR2_X0P5M_A9TR40"):
        cdl_ports(cdltext, cell)

    and2, nand2, nor2, aoi21, inv, dly4, or2, dff = (cells[name] for name in (
        "AND2_X0P5M_A9TR40", "NAND2_X0P5M_A9TR40", "NOR2_X0P5M_A9TR40",
        "AOI21_X0P5M_A9TR40", "INV_X0P5M_A9TR40", "DLY4_X0P5M_A9TR40",
        "OR2_X0P5M_A9TR40", "DFFRPQ_X0P5M_A9TR40"))
    selector = {
        "primary": "xor_29_and_lvt_29_with_AND2_X0P5M_A9TR40",
        "boolean_identity": "xor_29 & lvt_29 == lvt_29 & ~rvt_29 when xor_29 == rvt_29 ^ lvt_29",
        "placement": "replace only the frozen xor_29-to-medium input with dir_event; DFF D remains xor_29",
        "candidate_a_direct_polarity": {
            "formula": "lvt_29 & ~rvt_29", "implementation": "INV_X0P5M_A9TR40 + AND2_X0P5M_A9TR40",
            "added_input_capacitance_pf": {"lvt_29": liberty_capacitance(and2, "A"), "rvt_29": liberty_capacitance(inv, "A")},
            "rejected_reason": "E0 lvt_29 rises before xor_29; without a further delay this can launch medium/CK before the DFF D=xor_29 validity event.",
        },
        "candidate_b_xor_gated": {
            "formula": "xor_29 & lvt_29", "implementation": "AND2_X0P5M_A9TR40",
            "added_input_capacitance_pf": {"xor_29": liberty_capacitance(and2, "A"), "lvt_29": liberty_capacitance(and2, "B")},
            "first_effective_rise_liberty_reference_ps": liberty_first_rise_ps(and2, "Y", "A"),
            "reference_condition": "first RVT TT 1.10 V/25 C Liberty table entry only; input slew/load are not extracted BR1R conditions and this is not a sign-off bound",
            "selection_reason": "xor-gating preserves D-before-CK causality and does not interpose a delay element in the frozen xor-to-D branch; its added xor fanout is explicitly recorded below and is not treated as neutral.",
            "residual_risk": "EF suppression is logically correct because lvt leaves first on a falling source wave.  Final-load transistor verification must still count rejected-event/glitch edges; scalar BR1R crossings do not expose lvt_29 crossings.",
        },
        "candidate_c_nand_inverse": {
            "formula": "!(NAND2(xor_29,lvt_29))", "implementation": "NAND2_X0P5M_A9TR40 + INV_X0P5M_A9TR40",
            "rejected_reason": "same Boolean function but two stages, larger xor_29 input capacitance, and an extra internal transition; no benefit over AND2.",
            "added_xor_capacitance_pf": liberty_capacitance(nand2, "A"),
        },
        "candidate_d_nor_de_morgan": {
            "formula": "NOR2(!xor_29,!lvt_29)", "implementation": "2 x INV_X0P5M_A9TR40 + NOR2_X0P5M_A9TR40",
            "added_input_capacitance_pf": {"xor_29": liberty_capacitance(inv, "A"), "lvt_29": liberty_capacitance(inv, "A")},
            "rejected_reason": "Boolean equivalent, but three stages create more first-edge delay and internal switching than AND2 without reducing sensor-side fanout.",
            "nor2_input_capacitance_pf": liberty_capacitance(nor2, "A"),
        },
        "candidate_e_aoi_tied_rail": {
            "formula": "!AOI21(xor_29,lvt_29,VSS)", "implementation": "AOI21_X0P5M_A9TR40 + INV_X0P5M_A9TR40; B0 tied to VSS",
            "added_input_capacitance_pf": {"xor_29": liberty_capacitance(aoi21, "A0"), "lvt_29": liberty_capacitance(aoi21, "A1")},
            "rejected_reason": "Boolean equivalent only with a tied rail; two stages and an additional constant-input assumption offer no causality, load, or glitch advantage over AND2.",
        },
        "pd_sense_contract": "All audited cells are ordinary combinational base-library cells with Liberty power_down_function.  They may be placed and powered wholly in PD_SENSE/VDD_MONITORED; this audit grants no PD_CTRL crossing, isolation, or off-domain behavior.",
        "load_obligation": {"xor_29_new_capacitance_pf": liberty_capacitance(and2, "A"), "medium_input_capacitance_pf": medium_input_cap,
                            "effect": "the AND output replaces, rather than adds to, the medium first-buffer input; the new xor load can move xor/medium/raw D_ref and M/F trip relation and is not declared physically neutral."},
    }
    events = retained_events(br1r)
    lower = max(row["extension_min_for_ck_high_ps"] for row in events)
    upper = min(row["extension_max_for_next_ck_low_ps"] for row in events)
    dly4_fall = liberty_first_fall_ps(dly4, "Y", "A")
    legalizer = {
        "template": "dir_event -> frozen medium/fine -> raw_dir_ck; raw_dir_ck direct + delayed replica -> OR2 -> legal_ck",
        "stateless_property": "legal_ck rise follows the direct branch; legal_ck fall follows raw pulse fall plus one common replica delay.",
        "candidate_library_cells": {"delay": "DLY4_X0P5M_A9TR40", "merge": "OR2_X0P5M_A9TR40"},
        "raw_dir_ck_new_input_capacitance_pf": liberty_capacitance(dly4, "A") + liberty_capacitance(or2, "A"),
        "dff_ck_existing_input_capacitance_pf": liberty_capacitance(dff, "CK"),
        "first_effective_rise_from_raw_dir_ck_liberty_reference_ps": liberty_first_rise_ps(or2, "Y", "A"),
        "first_effective_rise_note": "The direct OR branch preserves the event ordering and adds only this merge arc after raw_dir_ck; it is a Liberty reference entry, not a physical D_ref shift guarantee.",
        "dly4_first_falling_arc_reference_ps": dly4_fall,
        "dly4_x4_reference_extension_ps": 4.0 * dly4_fall,
        "all_retained_event_extension_interval_ps": {"required_min": lower, "permitted_max": upper,
                                                       "intersection_exists": lower <= upper},
        "decision": "NO_STATELESS_FIXED_EXTENSION_CLOSED",
        "reason": "A common added falling delay must be at least {:.6f} ps for the narrow 1.10 V E1 pulse, but at most {:.6f} ps for the long 0.95 V E0 pulse before the next legal CK-low interval.  The intervals do not intersect.".format(lower, upper),
        "dly4_x4_note": "Four DLY4 stages give {:.6f} ps only at the first Liberty reference point; even that cannot repair the empty all-event interval and is not selected.".format(4.0 * dly4_fall),
        "forbidden_inference": "No fixed DLY/OR chain is called a universal legalizer, and Liberty reference entries are not substituted for post-layout or transient HSPICE delay bounds.",
    }
    context = {
        "continuous_overwrite": {"selected_semantics": True,
            "reason": "It makes no per-probe reset-width/recovery payment; the DFF simply captures each legal E0/E1 event.",
            "single_context_status": "TIMING_FRAGILE_AND_NOT_CLOSED",
            "minimum_raw_e0_to_e1_spacing_ps": min(row["e0_to_e1_raw_rise_spacing_ps"] for row in events),
            "formal_ck_high_plus_low_ps": DFF_MIN_HIGH_PS + DFF_MIN_LOW_PS,
            "nominal_spacing_headroom_ps": min(row["e0_to_e1_raw_rise_spacing_ps"] for row in events) - DFF_MIN_HIGH_PS - DFF_MIN_LOW_PS,
            "reason_not_closed": "The 63.724113 ps aggregate high+low headroom is smaller than the raw-width span across retained targets, yielding the empty fixed-extension intersection above."},
        "per_probe_reset": {"selected_semantics": False,
            "safe_nonoverlap_lower_bound_ps": DFF_MIN_HIGH_PS + DFF_MIN_RESET_PS + DFF_RECOVERY_PS,
            "available_probe_spacing_ps": RUNTIME_PERIOD_PS,
            "rejected_reason": "Waiting for the legal CK high interval, then reset high and reset-release recovery already costs 3000 ps before routing/removal/Q observation; reset must not be inserted into the 2075 ps path."},
        "multi_context_note": "Alternating contexts could relax each context's reuse interval, but it cannot make a single global stateless legalizer satisfy its own CK-high/CK-low pulse train.  Per-context legalizers/gates require a later, separate static architecture and are not implemented here.",
        "n_capture_min": None,
    }
    result = {"schema_version": 1, "study": "ftc_d0b_br2_capture_event_static_closure_v1", "stage": "D0-BR2",
              "decision": "CAPTURE_EVENT_ARCHITECTURE_BLOCKED", "shared_sensor_conclusion": "PRESERVED_RETIMING_GO_NOT_PHYSICALLY_BLOCKED",
              "inputs": {"br1r": {"path": str(BR1R), "sha256": sha256(BR1R)}, "rvt_liberty": {"path": str(rvt_lib), "sha256": sha256(rvt_lib)}, "rvt_cdl": {"path": str(rvt_cdl), "sha256": sha256(rvt_cdl)}, "lvt_liberty": {"path": str(lvt_lib), "sha256": sha256(lvt_lib)}, "lvt_cdl": {"path": str(lvt_cdl), "sha256": sha256(lvt_cdl)}},
              "direction_selector": selector, "legalizer": legalizer, "capture_context": context,
              "retained_event_budget": events, "simulation_accounting": accounting(),
              "scope": {"new_hspice": False, "h0_m1_t0_m0_modified": False, "sensor_copied": False, "capture_bank_implemented": False, "runtime_fsm_implemented": False}}
    write_json(OUT / "direction_selector_audit.json", selector)
    write_json(OUT / "legalizer_candidate_screen.json", legalizer)
    write_json(OUT / "capture_context_contract.json", context)
    write_json(OUT / "br2_static_closure.json", result)

    contract = read_json(CONTRACT)
    contract.update({"current_stage": "D0-BR2", "capture_event_static_closure": {"decision": result["decision"], "path": str(OUT / "br2_static_closure.json"), "direction_selector_primary": selector["primary"], "legalizer_primary": None}, "terminal_stage": "D0-BR2"})
    write_json(CONTRACT, contract)
    gate = {"schema_version": 1, "study": result["study"], "current_stage": "D0-BR2", "decision": result["decision"],
            "reason": legalizer["reason"], "shared_sensor_status": result["shared_sensor_conclusion"],
            "next_permitted_stage": "D0-BR2_stateful_or_pulse_width_normalizing_legalizer_static_research",
            "forbidden_before_static_contract_closes": ["minimal_two_target_hspice", "capture_bank", "runtime_fsm", "sensor_lane_copy", "H0_M1_T0_M0_modification"], "simulation_accounting": accounting()}
    write_json(GATE, gate)
    REPORT.write_text("""# FTC D0-BR2 方向选择与合法 capture event 静态闭合

## 结论

**CAPTURE_EVENT_ARCHITECTURE_BLOCKED**，但这不是 shared sensor 的物理阻塞。BR1R 的 `SHARED_SENSOR_CADENCE_RETIMING_GO` 保持有效：冻结单 sensor 在 2075 ps 下的 E0/EF/E1 同节点传播仍已通过。本次只重解析 750/1000/1250 ps、两个正式 target 的 6 个 retained scenario；新 HSPICE 为 0。

唯一的方向选择 primary 是 `xor_29 & lvt_29` 的 `AND2_X0P5M_A9TR40`，插在 `xor_29 -> medium`，D 仍为 `xor_29`。它在上升波由已到达的 XOR 放行，逻辑上抑制 LVT 先离开的 EF。`lvt_29 & ~rvt_29` 虽布尔等价，却可能先于 XOR 抵达，不能直接作为 medium/CK 的发起事件。所有新负载与延迟仍需后续最小晶体管验证，尤其要数 EF/glitch；本审计没有把 Liberty 表点伪装成 HSPICE 结果。

## 为什么无状态 fixed-delay legalizer 不能闭合

对 direct + delayed-replica + OR 的 falling-edge 延展器，任一事件的共同延迟 `d` 必须同时满足 `raw_width+d >= 1000 ps` 和 `E0->E1_spacing-(raw_width+d) >= 1000 ps`。全部 retained E0/E1 中，窄高压 E1 要求 `d >= {lower:.6f} ps`，而长低压 E0 要求 `d <= {upper:.6f} ps`。交集为空。

因此没有选择 DLY/OR 链、没有创建 legalizer/bank/FSM，也不进入两个 target 的最小 HSPICE。连续 overwrite 比 per-probe reset 更合理（后者安全非重叠下至少 `1000+1000+1000=3000 ps`），但单 context 的原始 E0→E1 最小间隔仅 {spacing:.6f} ps，扣除 DFF CK high/low 只剩 {headroom:.6f} ps，静态上 timing-fragile。交错 context 本身不能修复全局 legalizer 的脉冲 high/low 冲突。

下一步只能是新的 0-HSPICE、固定宽度/有状态 legalizer 静态研究，并先证明其自身没有把 256--519 ps 输入 min-pulse 依赖转移到新 cell；在那之前禁止 capture bank、runtime FSM 和任何 HSPICE。
""".format(lower=lower, upper=upper, spacing=context["continuous_overwrite"]["minimum_raw_e0_to_e1_spacing_ps"], headroom=context["continuous_overwrite"]["nominal_spacing_headroom_ps"]), encoding="utf-8")
    return result


def main(argv: Iterable[str] = None) -> int:
    parser = argparse.ArgumentParser(description="0-HSPICE D0-BR2 capture-event static closure")
    parser.add_argument("--phase", choices=("close",), required=True)
    parser.parse_args(list(argv) if argv is not None else None)
    close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
