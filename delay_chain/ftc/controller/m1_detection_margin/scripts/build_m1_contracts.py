#!/usr/bin/env python3
"""Build the read-only M1 F10 and exact-margin contracts.

M1 deliberately consumes the already accepted M0 characterization rather
than recalculating any delay or voltage quantity.  This script is the single
provenance boundary between M0 evidence and the small synthesizable lookup:
it validates the physical F10 encoding, joins candidate and trip records by
their immutable candidate ID, and emits reproducible JSON contracts.

No simulator, circuit deck, calibration controller, or source RTL is invoked
or changed by this script.  It only writes task-owned evidence below the M1
directory after every required upstream input has been validated.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Tuple


# The three snapshots and twelve mappings below are intentionally not another
# source of truth.  The script derives them from M0 JSON and rejects any M0
# candidate outside this frozen scope.  These constants describe only the
# expected allowed key set needed to fail closed on an accidental M0 drift.
EXPECTED_SNAPSHOTS: Tuple[Tuple[int, int], ...] = ((7, 6), (4, 6), (2, 9))
EXPECTED_LEVELS: Tuple[str, ...] = ("L0", "L1", "L2", "L3")
MEDIUM_BITS = 16
FINE_BITS = 10
FINE_CALIBRATION_MAX = 9


def repository_root() -> Path:
    """Return the repository root without relying on the caller's directory."""

    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "plans").is_dir() and (parent / ".git").exists():
            return parent
    raise RuntimeError("unable to locate repository root from M1 contract script")


def sha256_file(path: Path) -> str:
    """Return a content hash while keeping large frozen collateral streamed."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git_blob(root: Path, path: Path) -> str:
    """Read a worktree blob identity without changing the index or worktree."""

    relative = path.relative_to(root)
    return subprocess.check_output(
        ["git", "hash-object", str(relative)], cwd=root, text=True
    ).strip()


def load_json(path: Path) -> Dict[str, Any]:
    """Load a JSON object and reject malformed evidence before using it."""

    with path.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Write stable, task-owned JSON suitable for hash and review comparison."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def prefix_bits(width: int, asserted_count: int, active_low: bool) -> str:
    """Encode one physical thermometer vector in explicit [width-1:0] order.

    M0's renderer defines bit 0 as the first physical element.  A medium code
    asserts that low-index prefix high; a fine code selects the same prefix
    but drives its active-low controls low.  Returning MSB-to-LSB text makes
    the JSON directly comparable with SystemVerilog packed-vector literals.
    """

    if not 0 <= asserted_count <= width:
        raise ValueError("thermometer code outside physical range")
    bits_lsb_to_msb = []
    for index in range(width):
        selected = index < asserted_count
        if active_low:
            bits_lsb_to_msb.append("0" if selected else "1")
        else:
            bits_lsb_to_msb.append("1" if selected else "0")
    return "".join(reversed(bits_lsb_to_msb))


def require_f10_source_semantics(m0_renderer_text: str, physical_renderer_text: str,
                                 cfg_text: str) -> None:
    """Statically establish F10 physical legality and calibration exclusion.

    The M0 renderer must admit code 10 for the ten-element physical bank and
    generate all ten rails.  Frozen calibration RTL must separately prevent
    its stepper from incrementing past code 9.  Both facts are needed: merely
    finding a decimal F10 in a CSV would not prove the physical vector.
    """

    # M0 imports the previously frozen physical renderer rather than copying
    # its implementation.  Check both files so the evidence records the true
    # owner of the FINE_K and thermometer definitions as well as the M0-side
    # active-low constant-rail rendering that consumed those definitions.
    required_physical_fragments = (
        "FINE_K = 10",
        "if units < 0 or not 0 <= code <= units:",
    )
    for fragment in required_physical_fragments:
        if fragment not in physical_renderer_text:
            raise ValueError("physical renderer no longer proves F10 semantics: {}".format(fragment))

    required_m0_fragments = (
        "import run_dynamic_startup_calibration_protocol as physical",
        "value_high = bool(bit) if high_when_set else not bool(bit)",
        "if not 0 <= medium_code <= physical.MEDIUM_N or not 0 <= fine_code <= physical.FINE_K:",
    )
    for fragment in required_m0_fragments:
        if fragment not in m0_renderer_text:
            raise ValueError("M0 renderer no longer consumes F10 semantics: {}".format(fragment))

    required_cfg_fragments = (
        "if (fine_inc_i && (fine_code_o < FINE_BITS-1))",
        "fine_at_max_o = (fine_code_o == FINE_BITS-1);",
    )
    for fragment in required_cfg_fragments:
        if fragment not in cfg_text:
            raise ValueError("frozen calibration range check drifted: {}".format(fragment))


def source_records(root: Path, paths: Mapping[str, Path]) -> Dict[str, Dict[str, str]]:
    """Hash every read-only input used to build the M1 contract."""

    records: Dict[str, Dict[str, str]] = {}
    for name, path in sorted(paths.items()):
        if not path.is_file():
            raise FileNotFoundError("required M1 input is missing: {}".format(path))
        records[name] = {
            "path": str(path.relative_to(root)),
            "sha256": sha256_file(path),
            "git_blob_sha": git_blob(root, path),
        }
    return records


def expected_candidate_keys(candidates: Iterable[Mapping[str, Any]]) -> None:
    """Reject M0 evidence that no longer contains exactly the approved table."""

    keys = {(int(item["M_cal"]), int(item["F_cal"]), str(item["margin_level"]))
            for item in candidates}
    expected = {(medium, fine, level)
                for medium, fine in EXPECTED_SNAPSHOTS for level in EXPECTED_LEVELS}
    if keys != expected:
        raise ValueError("M0 candidates are not the frozen 3 snapshots x 4 levels")


def build_f10_contract(inputs: Mapping[str, Dict[str, str]]) -> Dict[str, Any]:
    """Publish every legal fine code, including the detection-only F10 state."""

    entries: List[Dict[str, Any]] = []
    for fine_code in range(FINE_BITS + 1):
        vector = prefix_bits(FINE_BITS, fine_code, active_low=True)
        entries.append({
            "fine_code": fine_code,
            "fine_therm_vector_bits_msb_to_lsb": vector,
            "physical_legal": True,
            "calibration_reachable": fine_code <= FINE_CALIBRATION_MAX,
            "detection_reachable": True,
            "evidence_source": [
                inputs["m0_renderer"]["path"],
                inputs["physical_renderer"]["path"],
                inputs["frozen_cfg_therm_regs"]["path"],
                inputs["m0_candidate_selection"]["path"],
                inputs["m0_trip_summary"]["path"],
            ],
            "evidence_sha256": {
                "m0_renderer": inputs["m0_renderer"]["sha256"],
                "physical_renderer": inputs["physical_renderer"]["sha256"],
                "frozen_cfg_therm_regs": inputs["frozen_cfg_therm_regs"]["sha256"],
                "m0_candidate_selection": inputs["m0_candidate_selection"]["sha256"],
                "m0_trip_summary": inputs["m0_trip_summary"]["sha256"],
            },
        })

    if entries[-1]["fine_therm_vector_bits_msb_to_lsb"] != "0" * FINE_BITS:
        raise AssertionError("F10 must activate all ten active-low fine rails")
    return {
        "schema_version": 1,
        "stage": "M1-0",
        "decision": "GO",
        "bit_order": "packed vector [9:0], text is bit9 through bit0",
        "active_low_semantics": "0 selects one fine NOR-load control; F10 selects all ten loads",
        "calibration_unreachable_not_physically_illegal": True,
        "entries": entries,
    }


def build_codebook(candidates: Iterable[Mapping[str, Any]], trip_summary: Mapping[str, Any],
                   inputs: Mapping[str, Dict[str, str]]) -> Dict[str, Any]:
    """Build the twelve exact entries and keep M0 trip numbers as metadata."""

    trip_by_candidate = {
        str(item["candidate_id"]): item for item in trip_summary.get("trip_map", [])
    }
    entries: List[Dict[str, Any]] = []
    for candidate in sorted(candidates, key=lambda item: (
            int(item["M_cal"]), int(item["F_cal"]), str(item["margin_level"]))):
        medium_cal = int(candidate["M_cal"])
        fine_cal = int(candidate["F_cal"])
        medium_det = int(candidate["M_det"])
        fine_det = int(candidate["F_det"])
        level = str(candidate["margin_level"])
        candidate_id = str(candidate["candidate_id"])
        trip = trip_by_candidate.get(candidate_id)
        trip_qualified = trip is not None and level != "L0" and float(candidate["baseline_vdd_v"]) > 0.80
        entries.append({
            "M_cal": medium_cal,
            "F_cal": fine_cal,
            "margin_level": level,
            "M_det": medium_det,
            "F_det": fine_det,
            "medium_therm_bits_msb_to_lsb": prefix_bits(MEDIUM_BITS, medium_det, active_low=False),
            "fine_therm_bits_msb_to_lsb": prefix_bits(FINE_BITS, fine_det, active_low=True),
            "mapping_supported": True,
            "trip_qualified": trip_qualified,
            "nominal_D_ref_shift_ps": float(candidate["nominal_D_ref_shift_ps"]),
            "static_Vtrip_v": None if trip is None else trip["Vtrip_v"],
            "DeltaV_trip_mv": None if trip is None else trip["DeltaV_trip_mv"],
            "m0_candidate_id": candidate_id,
            "m0_source_sha256": {
                "candidate_selection": inputs["m0_candidate_selection"]["sha256"],
                "trip_summary": inputs["m0_trip_summary"]["sha256"],
            },
        })

    if len(entries) != 12:
        raise AssertionError("exactly twelve M1 codebook entries are required")
    return {
        "schema_version": 1,
        "stage": "M1-1",
        "decision": "GO",
        "lookup_key": ["M_cal", "F_cal", "margin_level"],
        "unsupported_behavior": "mapping_supported=false; no interpolation, nearest-neighbor, or saturation",
        "trip_metadata_role": "reporting only; it must not drive RTL arithmetic or selection",
        "entries": entries,
    }


def main() -> None:
    """Validate frozen evidence and write the three M1-owned contract files."""

    root = repository_root()
    m1_root = root / "delay_chain/ftc/controller/m1_detection_margin"
    inputs = {
        "m0_candidate_selection": root / "delay_chain/ftc/analysis/m0_detection_margin_characterization/local_surface/candidate_selection_summary.json",
        "m0_trip_summary": root / "delay_chain/ftc/analysis/m0_detection_margin_characterization/trip/trip_summary.json",
        "m0_summary": root / "delay_chain/ftc/analysis/m0_detection_margin_characterization/summary.json",
        "m0_renderer": root / "delay_chain/ftc/scripts/run_m0_detection_margin_characterization.py",
        "physical_renderer": root / "delay_chain/ftc/scripts/run_dynamic_startup_calibration_protocol.py",
        # All six P10-frozen calibration RTL files are hashed here even though
        # M1 consumes only the H0-published snapshot interface.  Recording all
        # six makes the M1 Gate independently prove that the new detector-side
        # logic did not revise any frozen calibration behavior.
        "frozen_cal_pkg": root / "delay_chain/ftc/controller/rtl/ftc_cal_pkg.sv",
        "frozen_cfg_therm_regs": root / "delay_chain/ftc/controller/rtl/ftc_cfg_therm_regs.sv",
        "frozen_cal_operation_sequencer": root / "delay_chain/ftc/controller/rtl/ftc_operation_sequencer.sv",
        "frozen_cal_q_sampler": root / "delay_chain/ftc/controller/rtl/ftc_q_sampler.sv",
        "frozen_cal_fsm": root / "delay_chain/ftc/controller/rtl/ftc_cal_fsm.sv",
        "frozen_cal_controller_top": root / "delay_chain/ftc/controller/rtl/ftc_cal_controller_top.sv",
        # These H0 records document the fixed ownership interface and its
        # existing CAL-to-sensor timing composition.  M1 uses them strictly as
        # read-only evidence; it does not re-synthesize or retime frozen H0.
        "frozen_h0_owner": root / "delay_chain/ftc/controller/rtl/ftc_sensor_owner_handoff.sv",
        "frozen_h0_top": root / "delay_chain/ftc/controller/rtl/ftc_cal_detect_handoff_top.sv",
        "h0_frozen_baseline": root / "delay_chain/ftc/controller/h0_calibration_detection_handoff/baseline/frozen_input_sha256.json",
        "h0_interface_contract": root / "delay_chain/ftc/controller/h0_calibration_detection_handoff/contract/handoff_interface_contract.json",
        "h0_timing_composition": root / "delay_chain/ftc/controller/h0_calibration_detection_handoff/timing/handoff_timing_composition.json",
        "frozen_sensor": root / "delay_chain/ftc/controller/analysis/phase9_autonomous_transistor_level/vcs_xa/inputs/ftc_sensor_frozen.sp",
    }
    records = source_records(root, inputs)
    candidate_summary = load_json(inputs["m0_candidate_selection"])
    trip_summary = load_json(inputs["m0_trip_summary"])
    m0_summary = load_json(inputs["m0_summary"])
    candidates = candidate_summary.get("candidates", [])
    if candidate_summary.get("decision") != "GO" or trip_summary.get("decision") != "GO":
        raise ValueError("M0 candidate/trip evidence is not GO")
    if m0_summary.get("decision") != "CONDITIONAL_GO":
        raise ValueError("M0 scope boundary changed from CONDITIONAL_GO")
    expected_candidate_keys(candidates)
    require_f10_source_semantics(
        inputs["m0_renderer"].read_text(encoding="utf-8"),
        inputs["physical_renderer"].read_text(encoding="utf-8"),
        inputs["frozen_cfg_therm_regs"].read_text(encoding="utf-8"),
    )

    f10_contract = build_f10_contract(records)
    codebook = build_codebook(candidates, trip_summary, records)
    baseline = {
        "schema_version": 1,
        "stage": "M1-0",
        "decision": "GO",
        "current_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
        "m0_input_baseline_commit": "935facf76f338d8a0e274f33655d746153a1b284",
        "new_hspice_count": 0,
        "new_xa_count": 0,
        "inputs": records,
    }
    write_json(m1_root / "contract/F10_DETECTION_ENCODING_CONTRACT.json", f10_contract)
    write_json(m1_root / "contract/M1_MARGIN_CODEBOOK.json", codebook)
    write_json(m1_root / "baseline/frozen_input_sha256.json", baseline)
    print("M1-0/M1-1 GO: F10 contract and 12-entry exact codebook generated")


if __name__ == "__main__":
    main()
