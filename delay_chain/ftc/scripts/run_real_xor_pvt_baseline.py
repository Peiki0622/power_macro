#!/usr/bin/env python3
"""Characterize the frozen FTC tap29 real-XOR pulse width across minimal PVT.

This task deliberately reuses the approved TT/25 C 36-point pulse-width
curve.  It only runs the PVT points that are absent from that evidence: a
three-voltage process screen, a TT temperature screen, then the smallest
matrix formed by the measured process envelope.  It does not alter the FTC
topology or introduce any calibration or detector logic.
"""

import argparse
import copy
import csv
import json
import math
import re
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

try:
    import matplotlib

    # PVT jobs run on non-interactive HSPICE hosts as well as local shells.
    # Selecting a file-only backend before pyplot avoids any display dependency.
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError as error:  # pragma: no cover - only relevant to a broken runtime.
    raise SystemExit("FTC PVT baseline characterization requires Matplotlib: {}".format(error))


FTC_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import generate_ftc_deck as deck  # noqa: E402  # Render the reviewed physical topology.
import run_ftc_characterization as characterization  # noqa: E402  # Reuse HSPICE execution/parsing.
import run_real_xor_pulse_width as real_xor  # noqa: E402  # Reuse validated tap29 row arithmetic.


TAP_INDEX = 29
ANCHOR_VDDS = (1.10, 0.90, 0.75)
TEMPERATURES_C = (-40.0, 25.0, 85.0, 125.0)
NOMINAL_CORNER = "tt"
NOMINAL_TEMPERATURE_C = 25.0

# These fields are the established, measured tap29 interface.  The PVT table
# adds only scenario provenance and PVT coordinates around this same evidence.
MEASUREMENT_FIELDS = real_xor.RESULT_FIELDS
PVT_FIELDS = (
    "scenario_id",
    "vdd_v",
    "corner",
    "temperature_c",
    *MEASUREMENT_FIELDS[1:],
    "source",
)
MANIFEST_FIELDS = ("scenario_id", "vdd_v", "corner", "temperature_c", "source", "needs_hspice")


def finite_number(value: Any) -> Optional[float]:
    """Return a finite scalar, preserving missing HSPICE measurements as ``None``.

    A failed rise/fall measure must remain distinguishable from zero because it
    is a physical incomplete-pulse result, not an arithmetic input.
    """

    return real_xor.finite_number(value)


def format_value(value: Any) -> Any:
    """Write finite floats deterministically while keeping absent values blank."""

    if value is None:
        return ""
    if isinstance(value, float):
        return "{:.12g}".format(value)
    return value


def write_csv(path: Path, fields: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    """Write one nonempty compact evidence table with its explicit public schema."""

    if not rows:
        raise ValueError("refusing to write an empty PVT evidence table: {}".format(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: format_value(row.get(field)) for field in fields})


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Write sorted reviewable JSON outside the ignored raw-simulation root."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def voltage_key(value: Any) -> float:
    """Normalize decimal VDD coordinates to the 10 mV grid used by fine.csv."""

    number = finite_number(value)
    if number is None:
        raise ValueError("VDD must be finite: {}".format(value))
    return round(number, 2)


def scenario_id(corner: str, temperature_c: float, vdd_v: float) -> str:
    """Build a stable ID from the only three variables permitted in this task."""

    temperature = "m{}c".format(abs(int(temperature_c))) if temperature_c < 0 else "{}c".format(int(temperature_c))
    voltage = "v{:0.2f}".format(vdd_v).replace(".", "p")
    return "{}_{}_{}".format(str(corner).lower(), temperature, voltage)


def verify_frozen_topology(config: Mapping[str, Any], cells: Mapping[str, Any]) -> Dict[str, Any]:
    """Reject drift from the approved tap29 physical experiment before any run.

    The base config must remain the TT/25 C nominal source.  Individual PVT
    scenarios are later derived from a deep copy and may change only corner
    and temperature; VDD is passed separately to the existing deck runner.
    """

    point = config.get("selected_operating_point")
    if not isinstance(point, dict):
        raise ValueError("FTC selected operating point is unavailable")
    expected_config = (
        ("technology", "SMIC40LL"),
        ("corner", NOMINAL_CORNER),
        ("temperature_c", NOMINAL_TEMPERATURE_C),
        ("observable_stages", 30),
        ("launch_time_s", 1.0e-9),
        ("tran_max_step_s", 1.0e-12),
        ("minimum_vdd_v", 0.75),
        ("nominal_vdd_v", 1.10),
    )
    for field, expected in expected_config:
        actual = config.get(field)
        if isinstance(expected, float):
            if finite_number(actual) != expected:
                raise ValueError("FTC config {} must remain {}".format(field, expected))
        elif actual != expected:
            raise ValueError("FTC config {} must remain {}".format(field, expected))
    if int(point.get("initial_rvt_stages", -1)) != 4 or int(point.get("initial_lvt_stages", -1)) != 0:
        raise ValueError("PVT baseline requires the approved 4-RVT/0-LVT operating point")
    if finite_number(point.get("capture_phase_s")) != 3.0e-10:
        raise ValueError("PVT baseline requires the approved 300 ps capture phase")
    expected_cells = {
        "delay_rvt": "BUF_X0P7M_A9TR40",
        "delay_lvt": "BUF_X0P7M_A9TL40",
        "xor2": "XOR2_X0P5M_A9TR40",
    }
    for role, expected in expected_cells.items():
        if cells.get(role, {}).get("cell") != expected:
            raise ValueError("PVT baseline requires {} for {}".format(expected, role))
    return dict(point)


def parse_measurement_row(raw: Mapping[str, Any]) -> Dict[str, Any]:
    """Convert a compact CSV row into typed established tap29 measurement fields."""

    row: Dict[str, Any] = {}
    for field in MEASUREMENT_FIELDS:
        value = raw.get(field)
        if field == "valid":
            try:
                row[field] = int(value) if value not in (None, "") else 0
            except ValueError as error:
                raise ValueError("invalid valid flag in fine evidence: {}".format(value)) from error
        else:
            row[field] = finite_number(value)
    return row


def load_nominal_fine(path: Path) -> Dict[float, Dict[str, Any]]:
    """Load and strictly validate the immutable 36-point TT/25 C baseline.

    The function intentionally validates every row rather than merely the
    three anchors.  That protects later voltage comparisons and inverse lookup
    from a partially replaced or malformed nominal source.
    """

    with path.open(newline="", encoding="utf-8") as stream:
        raw_rows = list(csv.DictReader(stream))
    expected_vdds = tuple(round(1.10 - 0.01 * index, 2) for index in range(36))
    if len(raw_rows) != len(expected_vdds):
        raise ValueError("nominal fine evidence must contain exactly 36 rows")
    rows = [parse_measurement_row(row) for row in raw_rows]
    actual_vdds = tuple(voltage_key(row["vdd_v"]) for row in rows)
    if actual_vdds != expected_vdds:
        raise ValueError("nominal fine VDD order must remain 1.10 V down to 0.75 V in 10 mV steps")
    if any(int(row["valid"]) != 1 for row in rows):
        raise ValueError("nominal fine evidence contains an invalid real-XOR pulse")
    widths = [finite_number(row["W_real_ps"]) for row in rows]
    if any(width is None for width in widths) or not all(float(later) > float(earlier) for earlier, later in zip(widths, widths[1:])):
        raise ValueError("nominal fine W_real must remain strictly increasing as VDD decreases")
    return {voltage_key(row["vdd_v"]): row for row in rows}


def scenario_config(base_config: Mapping[str, Any], corner: str, temperature_c: float) -> Dict[str, Any]:
    """Create one isolated in-memory PVT override without mutating frozen input JSON."""

    result = copy.deepcopy(dict(base_config))
    result["corner"] = str(corner)
    result["temperature_c"] = float(temperature_c)
    return result


def discover_process_corners(model_library: Path, nominal_corner: str) -> List[str]:
    """Discover the PDK-declared core MOS corners without naming candidates in code.

    This SMIC model file explicitly documents its supported MOS corner list in
    a comment immediately before the corresponding top-level ``.lib`` blocks.
    Reading that declaration and then requiring each named section prevents a
    guessed ``ff``/``ss`` list from silently selecting BJT, passive, or Monte
    Carlo sections.  A model file without that declaration fails explicitly
    instead of receiving a synthetic fallback corner list.
    """

    text = model_library.read_text(encoding="utf-8", errors="replace")
    declared: Optional[List[str]] = None
    for line in text.splitlines():
        match = re.search(r"\bcorners?\s+are\s+supported\s*:\s*(.+)$", line, flags=re.IGNORECASE)
        if match is None:
            continue
        names = [token.lower() for token in re.findall(r"[A-Za-z][A-Za-z0-9_]*", match.group(1)) if token.lower() != "and"]
        if not names:
            raise ValueError("PDK corner declaration contains no section names: {}".format(model_library))
        declared = names
        break
    if declared is None:
        raise ValueError("PDK does not declare its supported MOS corners: {}".format(model_library))
    sections = {
        match.group(1).lower(): match.group(1)
        for match in re.finditer(r"^\s*\.lib\s+([^\s*]+)", text, flags=re.IGNORECASE | re.MULTILINE)
    }
    if len(set(declared)) != len(declared):
        raise ValueError("PDK corner declaration contains duplicate names: {}".format(model_library))
    missing = [name for name in declared if name not in sections]
    if missing:
        raise ValueError("PDK-declared MOS corners lack .lib sections: {}".format(", ".join(missing)))
    nominal = str(nominal_corner).lower()
    if nominal not in declared:
        raise ValueError("nominal corner {} is absent from PDK MOS declaration".format(nominal_corner))
    # The PDK declaration is the authority; preserve its order and spelling
    # from the actual .lib section for auditability and deterministic tables.
    return [sections[name] for name in declared]


def process_corner_metadata(model_library: Path, nominal_corner: str) -> Dict[str, Any]:
    """Build the compact auditable record required before any HSPICE execution."""

    corners = discover_process_corners(model_library, nominal_corner)
    return {
        "model_library": str(model_library),
        "nominal_corner": str(nominal_corner),
        "available_process_corners": corners,
        "selected_process_corners_for_screen": corners,
    }


def scenario_key(corner: str, temperature_c: float, vdd_v: float) -> Tuple[str, float, float]:
    """Return the deduplication key for one physical PVT condition."""

    return (str(corner).lower(), float(temperature_c), voltage_key(vdd_v))


def manifest_entry(corner: str, temperature_c: float, vdd_v: float, source: Optional[str] = None) -> Dict[str, Any]:
    """Describe a scenario before HSPICE, reserving TT/25 C for fine.csv reuse."""

    reuse_nominal = scenario_key(corner, temperature_c, vdd_v)[:2] == (NOMINAL_CORNER, NOMINAL_TEMPERATURE_C)
    resolved_source = source if source is not None else ("reused_tt25_fine" if reuse_nominal else "new_pvt_hspice")
    if reuse_nominal and resolved_source != "reused_tt25_fine":
        raise ValueError("TT/25 C scenarios must always reuse fine.csv")
    if resolved_source not in ("reused_tt25_fine", "reused_process_screen", "reused_temperature_screen", "new_pvt_hspice"):
        raise ValueError("unknown PVT evidence source: {}".format(resolved_source))
    return {
        "scenario_id": scenario_id(corner, temperature_c, voltage_key(vdd_v)),
        "vdd_v": voltage_key(vdd_v),
        "corner": str(corner),
        "temperature_c": float(temperature_c),
        "source": resolved_source,
        "needs_hspice": 1 if resolved_source == "new_pvt_hspice" else 0,
    }


def deduplicate_manifest(entries: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Merge repeated screen references while rejecting contradictory scenario data.

    TT/25 C anchors are legitimately requested by both process and temperature
    screens.  They become one reused manifest row; any other accidental key or
    ID collision is rejected before a second physical run can be launched.
    """

    result: List[Dict[str, Any]] = []
    seen: Dict[Tuple[str, float, float], Dict[str, Any]] = {}
    for entry in entries:
        key = scenario_key(str(entry["corner"]), float(entry["temperature_c"]), float(entry["vdd_v"]))
        candidate = dict(entry)
        existing = seen.get(key)
        if existing is None:
            seen[key] = candidate
            result.append(candidate)
            continue
        if existing != candidate:
            raise ValueError("conflicting manifest definitions for {}".format(existing["scenario_id"]))
    ids = [str(entry["scenario_id"]) for entry in result]
    if len(ids) != len(set(ids)):
        raise ValueError("scenario ID collision in PVT manifest")
    return result


def initial_manifest(corners: Sequence[str]) -> List[Dict[str, Any]]:
    """Create the complete process/temperature screen queue before its first run."""

    entries = [
        manifest_entry(corner, NOMINAL_TEMPERATURE_C, voltage)
        for voltage in ANCHOR_VDDS
        for corner in corners
    ]
    entries.extend(
        manifest_entry(NOMINAL_CORNER, temperature, voltage)
        for voltage in ANCHOR_VDDS
        for temperature in TEMPERATURES_C
    )
    return deduplicate_manifest(entries)


def screen_entries(corners: Sequence[str], screen: str) -> List[Dict[str, Any]]:
    """Return one ordered, fixed-size screen rather than a broad PVT sweep."""

    if screen == "process":
        return [
            manifest_entry(corner, NOMINAL_TEMPERATURE_C, voltage)
            for voltage in ANCHOR_VDDS
            for corner in corners
        ]
    if screen == "temperature":
        return [
            manifest_entry(NOMINAL_CORNER, temperature, voltage)
            for voltage in ANCHOR_VDDS
            for temperature in TEMPERATURES_C
        ]
    raise ValueError("unknown PVT screen: {}".format(screen))


def pvt_row(entry: Mapping[str, Any], measurement: Mapping[str, Any], source: Optional[str] = None) -> Dict[str, Any]:
    """Attach PVT coordinates/provenance to the unchanged tap29 measurement schema."""

    measurement_voltage = voltage_key(measurement.get("vdd_v"))
    if measurement_voltage != voltage_key(entry["vdd_v"]):
        raise ValueError("measurement VDD differs from scenario manifest")
    result: Dict[str, Any] = {
        "scenario_id": str(entry["scenario_id"]),
        "vdd_v": measurement_voltage,
        "corner": str(entry["corner"]),
        "temperature_c": float(entry["temperature_c"]),
    }
    result.update({field: measurement.get(field) for field in MEASUREMENT_FIELDS[1:]})
    result["source"] = source if source is not None else str(entry["source"])
    return result


def complete_pulse(row: Mapping[str, Any]) -> bool:
    """Apply the established real-XOR VDD/2 crossing and peak completeness rule."""

    return (
        int(row.get("valid", 0)) == 1
        and finite_number(row.get("W_real_ps")) is not None
        and finite_number(row.get("W_proxy_ps")) is not None
        and (finite_number(row.get("xor29_peak_ratio")) or 0.0) > 0.5
    )


def require_complete_rows(rows: Sequence[Mapping[str, Any]], description: str, expected_count: int) -> None:
    """Gate later PVT work on complete evidence from every planned screen point."""

    if len(rows) != expected_count:
        raise ValueError("{} must contain {} rows, found {}".format(description, expected_count, len(rows)))
    incomplete = [str(row.get("scenario_id")) for row in rows if not complete_pulse(row)]
    if incomplete:
        raise RuntimeError("{} has incomplete real-XOR pulses: {}".format(description, ", ".join(incomplete)))


def verify_rendered_topology(config: Mapping[str, Any], cells: Mapping[str, Any], point: Mapping[str, Any]) -> None:
    """Inspect the generated PVT deck before HSPICE to protect the frozen topology.

    This is a textual contract check, not a proxy simulation: it proves each
    physical scenario still instantiates the entire 30-XOR bank and only asks
    HSPICE for the approved tap29 pulse crossing/peak measurements.
    """

    rendered = deck.render_deck(
        config=dict(config), cells=dict(cells), vdd_v=ANCHOR_VDDS[0], mode="xor",
        initial_rvt_stages=int(point["initial_rvt_stages"]),
        initial_lvt_stages=int(point["initial_lvt_stages"]),
        capture_phase_s=float(point["capture_phase_s"]), pulse_width_taps=[TAP_INDEX],
    )
    if rendered.count("XXOR_") != 30 or "XXOR_29 xor_29 " not in rendered:
        raise ValueError("PVT deck no longer retains the full 30-real-XOR bank at tap29")
    for measure in ("xor_29_rise", "xor_29_fall", "xor_29_peak_v"):
        if rendered.count(measure) != 1:
            raise ValueError("PVT deck is missing the required {} measure".format(measure))
    if any("xor_{:02d}_rise".format(index) in rendered for index in range(TAP_INDEX)):
        raise ValueError("PVT deck must not measure pulse width at an alternate tap")


def run_entries(hspice: Path, run_dir: Path, base_config: Mapping[str, Any], cells: Mapping[str, Any],
                point: Mapping[str, Any], entries: Sequence[Mapping[str, Any]], nominal: Mapping[float, Mapping[str, Any]],
                start_index: int, reused: Optional[Mapping[Tuple[str, float, float], Mapping[str, Any]]] = None) -> Tuple[List[Dict[str, Any]], int]:
    """Reuse nominal rows or execute exactly one isolated HSPICE deck per missing PVT row.

    ``start_index`` is carried across screens so raw scenario directories stay
    unique while their labels remain human-readable PVT condition IDs.  No
    retry, replacement topology, or unplanned voltage point is introduced.
    """

    rows: List[Dict[str, Any]] = []
    index = int(start_index)
    reusable = dict(reused or {})
    for entry in entries:
        voltage = voltage_key(entry["vdd_v"])
        if int(entry["needs_hspice"]) == 0:
            key = scenario_key(str(entry["corner"]), float(entry["temperature_c"]), voltage)
            measurement = nominal[voltage] if key[:2] == (NOMINAL_CORNER, NOMINAL_TEMPERATURE_C) else reusable.get(key)
            if measurement is None:
                raise ValueError("manifest references unavailable reused evidence: {}".format(entry["scenario_id"]))
            rows.append(pvt_row(entry, measurement))
            continue
        config = scenario_config(base_config, str(entry["corner"]), float(entry["temperature_c"]))
        record = characterization.run_scenario(
            hspice, run_dir, config, dict(cells), index, str(entry["scenario_id"]), voltage, "xor",
            int(point["initial_rvt_stages"]), int(point["initial_lvt_stages"]), float(point["capture_phase_s"]),
            pulse_width_taps=[TAP_INDEX],
        )
        rows.append(pvt_row(entry, real_xor.row_from_record(voltage, record)))
        index += 1
    return rows, index


def extend_manifest(existing: Sequence[Mapping[str, Any]], additions: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Append only newly required matrix conditions to the already-audited queue.

    A screen scenario can later appear in the matrix as *reused* evidence, but
    the manifest records the original physical acquisition once.  Retaining
    the first entry makes that provenance unambiguous and prevents duplicate
    scenario directories or repeat HSPICE invocations.
    """

    result = [dict(entry) for entry in existing]
    known = {scenario_key(str(entry["corner"]), float(entry["temperature_c"]), float(entry["vdd_v"])) for entry in result}
    for entry in additions:
        key = scenario_key(str(entry["corner"]), float(entry["temperature_c"]), float(entry["vdd_v"]))
        if key not in known:
            result.append(dict(entry))
            known.add(key)
    return result


def select_envelope_corners(process_rows: Sequence[Mapping[str, Any]], corners: Sequence[str]) -> Tuple[List[str], Dict[str, Any]]:
    """Select only corners that actually form a process-width envelope at an anchor.

    Exact ties deliberately retain every tied corner.  That is the smallest
    lossless interpretation of a measured envelope and avoids inventing an
    arbitrary score or a universal fast/slow label.
    """

    require_complete_rows(process_rows, "process screen", len(ANCHOR_VDDS) * len(corners))
    selected = {NOMINAL_CORNER}
    envelope: Dict[str, Any] = {}
    for voltage in ANCHOR_VDDS:
        rows = [row for row in process_rows if voltage_key(row["vdd_v"]) == voltage_key(voltage)]
        if len(rows) != len(corners):
            raise ValueError("process screen lacks a corner at {} V".format(voltage))
        widths = [float(row["W_real_ps"]) for row in rows]
        minimum = min(widths)
        maximum = max(widths)
        min_corners = [str(row["corner"]) for row in rows if float(row["W_real_ps"]) == minimum]
        max_corners = [str(row["corner"]) for row in rows if float(row["W_real_ps"]) == maximum]
        selected.update(corner.lower() for corner in min_corners + max_corners)
        envelope["{:.2f}".format(voltage)] = {
            "corner_min_width": min_corners,
            "corner_max_width": max_corners,
            "min_width_ps": minimum,
            "max_width_ps": maximum,
        }
    ordered = [corner for corner in corners if str(corner).lower() in selected]
    if NOMINAL_CORNER not in [corner.lower() for corner in ordered]:
        ordered.insert(0, NOMINAL_CORNER)
    return ordered, envelope


def evidence_by_key(rows: Sequence[Mapping[str, Any]]) -> Dict[Tuple[str, float, float], Mapping[str, Any]]:
    """Index compact rows for exact matrix reuse and reject conflicting duplicates."""

    result: Dict[Tuple[str, float, float], Mapping[str, Any]] = {}
    for row in rows:
        key = scenario_key(str(row["corner"]), float(row["temperature_c"]), float(row["vdd_v"]))
        if key in result and float(result[key]["W_real_ps"]) != float(row["W_real_ps"]):
            raise ValueError("conflicting compact evidence for {}".format(key))
        result[key] = row
    return result


def matrix_entries(selected_corners: Sequence[str], process_rows: Sequence[Mapping[str, Any]],
                   temperature_rows: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Build the minimal matrix, tagging every already measured condition for reuse."""

    process_keys = set(evidence_by_key(process_rows))
    temperature_keys = set(evidence_by_key(temperature_rows))
    entries: List[Dict[str, Any]] = []
    for voltage in ANCHOR_VDDS:
        for corner in selected_corners:
            for temperature in TEMPERATURES_C:
                key = scenario_key(corner, temperature, voltage)
                if key[:2] == (NOMINAL_CORNER, NOMINAL_TEMPERATURE_C):
                    source = "reused_tt25_fine"
                elif key in process_keys:
                    source = "reused_process_screen"
                elif key in temperature_keys:
                    source = "reused_temperature_screen"
                else:
                    source = "new_pvt_hspice"
                entries.append(manifest_entry(corner, temperature, voltage, source))
    return deduplicate_manifest(entries)


def widths_at_anchor(rows: Sequence[Mapping[str, Any]], vdd_v: float) -> List[float]:
    """Return all complete real widths at one anchor, rejecting partial arithmetic."""

    result = [float(row["W_real_ps"]) for row in rows if voltage_key(row["vdd_v"]) == voltage_key(vdd_v)]
    if not result:
        raise ValueError("no PVT widths available at {} V".format(vdd_v))
    return result


def offset_summary(rows: Sequence[Mapping[str, Any]], nominal: Mapping[float, Mapping[str, Any]], prefix: str) -> Dict[str, Any]:
    """Compute direct offsets/spans against TT/25 C without a statistical model."""

    result: Dict[str, Any] = {}
    for voltage in ANCHOR_VDDS:
        nominal_width = float(nominal[voltage_key(voltage)]["W_real_ps"])
        offsets = [width - nominal_width for width in widths_at_anchor(rows, voltage)]
        result["{:.2f}".format(voltage)] = {
            "W_nominal_ps": nominal_width,
            "min_{}_offset_ps".format(prefix): min(offsets),
            "max_{}_offset_ps".format(prefix): max(offsets),
            "{}_span_ps".format(prefix): max(offsets) - min(offsets),
        }
    return result


def combined_summary(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Report the observed PVT envelope directly from the selected matrix rows."""

    result: Dict[str, Any] = {}
    for voltage in ANCHOR_VDDS:
        widths = widths_at_anchor(rows, voltage)
        result["{:.2f}".format(voltage)] = {
            "pvt_min_width_ps": min(widths),
            "pvt_max_width_ps": max(widths),
            "pvt_span_ps": max(widths) - min(widths),
        }
    return result


def temperature_behavior(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Classify observed temperature direction per anchor without fitting a curve."""

    result: Dict[str, Any] = {}
    for voltage in ANCHOR_VDDS:
        ordered = sorted(
            (row for row in rows if voltage_key(row["vdd_v"]) == voltage_key(voltage)),
            key=lambda row: float(row["temperature_c"]),
        )
        if [float(row["temperature_c"]) for row in ordered] != list(TEMPERATURES_C):
            raise ValueError("temperature screen is incomplete at {} V".format(voltage))
        widths = [float(row["W_real_ps"]) for row in ordered]
        steps = [later - earlier for earlier, later in zip(widths, widths[1:])]
        if all(step > 0.0 for step in steps):
            label = "strict_increasing_with_temperature"
        elif all(step < 0.0 for step in steps):
            label = "strict_decreasing_with_temperature"
        elif all(step >= 0.0 for step in steps):
            label = "nondecreasing_with_plateau"
        elif all(step <= 0.0 for step in steps):
            label = "nonincreasing_with_plateau"
        else:
            label = "nonmonotonic_or_temperature_inversion"
        result["{:.2f}".format(voltage)] = {"behavior": label, "step_deltas_ps": steps}
    return result


def vdd_sensitivity(nominal: Mapping[float, Mapping[str, Any]]) -> Dict[str, Any]:
    """Read the prescribed voltage movements exclusively from existing fine.csv."""

    requested = {
        1.10: ((1.05, "50mV"), (1.00, "100mV"), (0.90, "200mV")),
        0.90: ((0.85, "50mV"), (0.80, "100mV"), (0.75, "150mV")),
    }
    result: Dict[str, Any] = {}
    for baseline, targets in requested.items():
        baseline_width = float(nominal[voltage_key(baseline)]["W_real_ps"])
        shifts: Dict[str, float] = {}
        for target, label in targets:
            shift = float(nominal[voltage_key(target)]["W_real_ps"]) - baseline_width
            if shift <= 0.0:
                raise ValueError("nominal fine curve has a nonpositive {} shift at {} V".format(label, baseline))
            shifts["shift_{}_ps".format(label)] = shift
        result["{:.2f}".format(baseline)] = shifts
    return result


def compare_pvt_to_vdd(combined: Mapping[str, Any], sensitivity: Mapping[str, Any]) -> Dict[str, Any]:
    """Compare each anchor's measured PVT span to its local 50/100 mV movement."""

    result: Dict[str, Any] = {}
    for key in ("1.10", "0.90"):
        span = float(combined[key]["pvt_span_ps"])
        shift_50 = float(sensitivity[key]["shift_50mV_ps"])
        shift_100 = float(sensitivity[key]["shift_100mV_ps"])
        result[key] = {
            "pvt_span_ps": span,
            "shift_50mV_ps": shift_50,
            "shift_100mV_ps": shift_100,
            "pvt_span_to_50mV_shift": span / shift_50,
            "pvt_span_to_100mV_shift": span / shift_100,
        }
    return result


def inverse_nominal_voltage(nominal: Mapping[float, Mapping[str, Any]], width_ps: float) -> Optional[float]:
    """Invert the measured monotonic TT/25 curve by bounded linear interpolation.

    The nominal widths increase as VDD decreases.  Sorting by width gives a
    normal ascending interpolation axis; widths outside its endpoints return
    ``None`` so a Golden Model error is never extrapolated beyond evidence.
    """

    points = sorted((float(row["W_real_ps"]), voltage_key(voltage)) for voltage, row in nominal.items())
    if width_ps < points[0][0] or width_ps > points[-1][0]:
        return None
    for left, right in zip(points, points[1:]):
        left_width, left_voltage = left
        right_width, right_voltage = right
        if width_ps == left_width:
            return left_voltage
        if left_width < width_ps <= right_width:
            fraction = (width_ps - left_width) / (right_width - left_width)
            return left_voltage + fraction * (right_voltage - left_voltage)
    return points[-1][1] if width_ps == points[-1][0] else None


def golden_equivalent_rows(matrix_rows: Sequence[Mapping[str, Any]], nominal: Mapping[float, Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Map every matrix width to a bounded TT/25 equivalent voltage for analysis only."""

    result: List[Dict[str, Any]] = []
    for row in matrix_rows:
        equivalent = inverse_nominal_voltage(nominal, float(row["W_real_ps"]))
        result.append({
            "scenario_id": str(row["scenario_id"]),
            "corner": str(row["corner"]),
            "temperature_c": float(row["temperature_c"]),
            "vdd_v": voltage_key(row["vdd_v"]),
            "V_equiv_golden": equivalent,
            "golden_equivalent_error_mV": None if equivalent is None else (equivalent - float(row["vdd_v"])) * 1000.0,
            "out_of_nominal_curve": 1 if equivalent is None else 0,
        })
    return result


def golden_summary(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Summarize equivalent-voltage error while retaining out-of-range count separately."""

    in_range = [row for row in rows if int(row["out_of_nominal_curve"]) == 0]
    if not in_range:
        return {
            "in_range_scenario_count": 0,
            "out_of_nominal_curve_count": len(rows),
            "max_abs_golden_equivalent_error_mV": None,
            "median_abs_golden_equivalent_error_mV": None,
            "worst_scenario": None,
        }
    worst = max(in_range, key=lambda row: abs(float(row["golden_equivalent_error_mV"])))
    absolute_errors = [abs(float(row["golden_equivalent_error_mV"])) for row in in_range]
    return {
        "in_range_scenario_count": len(in_range),
        "out_of_nominal_curve_count": len(rows) - len(in_range),
        "max_abs_golden_equivalent_error_mV": max(absolute_errors),
        "median_abs_golden_equivalent_error_mV": statistics.median(absolute_errors),
        "worst_scenario": dict(worst),
    }


def classify_pvt_impact(comparison: Mapping[str, Any]) -> Dict[str, Any]:
    """Assign the required label from direct width-movement relations only.

    ``SMALL`` requires every reported anchor to stay below its local 50 mV
    movement.  ``DOMINANT`` is triggered if any anchor exceeds its local 100
    mV movement.  The remaining measured middle range is ``NON_NEGLIGIBLE``;
    no percentage threshold, SNR, or statistical confidence is introduced.
    """

    relations: List[str] = []
    below_50 = True
    above_100 = False
    for voltage in ("1.10", "0.90"):
        values = comparison[voltage]
        span = float(values["pvt_span_ps"])
        shift_50 = float(values["shift_50mV_ps"])
        shift_100 = float(values["shift_100mV_ps"])
        if span < shift_50:
            relation = "combined PVT span < 50 mV width shift"
        elif span > shift_100:
            relation = "combined PVT span > 100 mV width shift"
        else:
            relation = "combined PVT span is between 50 mV and 100 mV width shifts"
        relations.append("{} V: {}".format(voltage, relation))
        below_50 = below_50 and span < shift_50
        above_100 = above_100 or span > shift_100
    label = "SMALL" if below_50 else ("DOMINANT" if above_100 else "NON_NEGLIGIBLE")
    return {"PVT_IMPACT": label, "basis": relations}


def build_summary(process_rows: Sequence[Mapping[str, Any]], temperature_rows: Sequence[Mapping[str, Any]],
                  matrix_rows: Sequence[Mapping[str, Any]], nominal: Mapping[float, Mapping[str, Any]],
                  selected_corners: Sequence[str], envelope: Mapping[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Collect every required direct result in one compact, reviewable JSON object."""

    process = offset_summary(process_rows, nominal, "process")
    temperature = offset_summary(temperature_rows, nominal, "temperature")
    combined = combined_summary(matrix_rows)
    sensitivity = vdd_sensitivity(nominal)
    comparison = compare_pvt_to_vdd(combined, sensitivity)
    golden_rows = golden_equivalent_rows(matrix_rows, nominal)
    return {
        "measured_tap": TAP_INDEX,
        "anchor_vdd_v": list(ANCHOR_VDDS),
        "temperatures_c": list(TEMPERATURES_C),
        "selected_process_corners_for_matrix": list(selected_corners),
        "process_envelope_by_vdd": dict(envelope),
        "process_only": process,
        "temperature_only": temperature,
        "temperature_behavior": temperature_behavior(temperature_rows),
        "combined_pvt": combined,
        "nominal_vdd_sensitivity": sensitivity,
        "pvt_vs_vdd_shift": comparison,
        "golden_model": golden_summary(golden_rows),
        "pvt_impact": classify_pvt_impact(comparison),
    }, golden_rows


def configure_plot_style() -> None:
    """Apply the repository's compact display-independent SVG plot style."""

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.labelsize": 10, "axes.titlesize": 11, "svg.fonttype": "none"})


def save_figure(figure: Any, path: Path) -> None:
    """Write deterministic SVG output and close the figure to bound batch memory use."""

    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, format="svg", bbox_inches="tight", metadata={"Date": None})
    plt.close(figure)
    path.write_text("\n".join(line.rstrip() for line in path.read_text(encoding="utf-8").splitlines()) + "\n", encoding="utf-8")


def plot_envelope(nominal: Mapping[float, Mapping[str, Any]], combined: Mapping[str, Any], output_dir: Path) -> None:
    """Plot the full existing nominal curve with only the three measured PVT envelopes."""

    ordered = sorted(nominal.items())
    configure_plot_style()
    figure, axis = plt.subplots(figsize=(7.0, 4.0))
    axis.plot([item[0] for item in ordered], [float(item[1]["W_real_ps"]) for item in ordered], "-o", markersize=3.0, label="TT / 25 C fine curve")
    anchors = list(ANCHOR_VDDS)
    minima = [float(combined["{:.2f}".format(voltage)]["pvt_min_width_ps"]) for voltage in anchors]
    maxima = [float(combined["{:.2f}".format(voltage)]["pvt_max_width_ps"]) for voltage in anchors]
    axis.vlines(anchors, minima, maxima, color="#D55E00", linewidth=3.0, label="selected PVT envelope")
    axis.scatter(anchors, minima, color="#D55E00", s=18)
    axis.scatter(anchors, maxima, color="#D55E00", s=18)
    axis.set_xlabel("VDD (V)")
    axis.set_ylabel("W_real (ps)")
    axis.set_title("Tap29 real-XOR PVT envelope versus nominal curve")
    axis.grid(True, linewidth=0.5, alpha=0.35)
    axis.legend(loc="best")
    save_figure(figure, output_dir / "fig1_pvt_envelope_vs_nominal.svg")


def plot_spread_comparison(summary: Mapping[str, Any], output_dir: Path) -> None:
    """Compare only the requested process/temperature/PVT and 50/100 mV magnitudes."""

    configure_plot_style()
    figure, axes = plt.subplots(1, 2, figsize=(9.0, 4.0), sharey=False)
    labels = ("Process", "Temperature", "Combined PVT", "50 mV shift", "100 mV shift")
    for axis, voltage in zip(axes, ("1.10", "0.90")):
        values = (
            float(summary["process_only"][voltage]["process_span_ps"]),
            float(summary["temperature_only"][voltage]["temperature_span_ps"]),
            float(summary["combined_pvt"][voltage]["pvt_span_ps"]),
            float(summary["pvt_vs_vdd_shift"][voltage]["shift_50mV_ps"]),
            float(summary["pvt_vs_vdd_shift"][voltage]["shift_100mV_ps"]),
        )
        axis.bar(range(len(labels)), values, color=("#0072B2", "#009E73", "#D55E00", "#666666", "#222222"))
        # The installed batch-host Matplotlib predates keyword label support
        # on set_xticks, so set positions and labels separately for portability.
        axis.set_xticks(range(len(labels)))
        axis.set_xticklabels(labels, rotation=30, ha="right")
        axis.set_ylabel("Width movement/span (ps)")
        axis.set_title("VDD = {} V".format(voltage))
        axis.grid(True, axis="y", linewidth=0.5, alpha=0.35)
    figure.suptitle("PVT spread versus TT/25 C voltage-induced movement")
    save_figure(figure, output_dir / "fig2_pvt_spread_vs_vdd_shift.svg")


def plot_golden_error(golden_rows: Sequence[Mapping[str, Any]], selected_corners: Sequence[str], output_dir: Path) -> None:
    """Display the specified corner/temperature/anchor Golden-equivalent errors only."""

    configure_plot_style()
    figure, axes = plt.subplots(1, len(ANCHOR_VDDS), figsize=(10.0, 3.8), sharey=True)
    if len(ANCHOR_VDDS) == 1:  # pragma: no cover - anchors are a fixed three-point contract.
        axes = [axes]
    finite_errors = [abs(float(row["golden_equivalent_error_mV"])) for row in golden_rows if row["golden_equivalent_error_mV"] is not None]
    limit = max([1.0] + finite_errors)
    image = None
    for axis, voltage in zip(axes, ANCHOR_VDDS):
        grid: List[List[float]] = []
        for corner in selected_corners:
            values: List[float] = []
            for temperature in TEMPERATURES_C:
                match = next(
                    row for row in golden_rows
                    if voltage_key(row["vdd_v"]) == voltage_key(voltage)
                    and str(row["corner"]).lower() == str(corner).lower()
                    and float(row["temperature_c"]) == temperature
                )
                values.append(math.nan if match["golden_equivalent_error_mV"] is None else float(match["golden_equivalent_error_mV"]))
            grid.append(values)
        image = axis.imshow(grid, cmap="coolwarm", vmin=-limit, vmax=limit, aspect="auto")
        axis.set_title("VDD = {:.2f} V".format(voltage))
        axis.set_xticks(range(len(TEMPERATURES_C)))
        axis.set_xticklabels(["{:.0f} C".format(value) for value in TEMPERATURES_C], rotation=30, ha="right")
        axis.set_yticks(range(len(selected_corners)))
        axis.set_yticklabels(list(selected_corners))
        for row_index, values in enumerate(grid):
            for column_index, value in enumerate(values):
                axis.text(column_index, row_index, "out" if math.isnan(value) else "{:.0f}".format(value), ha="center", va="center", fontsize=7)
    figure.colorbar(image, ax=list(axes), label="Golden-equivalent VDD error (mV)")
    save_figure(figure, output_dir / "fig3_golden_equivalent_error.svg")


def report_number(value: Any, digits: int = 3) -> str:
    """Render report numbers compactly while retaining unavailable values as n/a."""

    number = finite_number(value)
    return "n/a" if number is None else "{:.{}f}".format(number, digits)


def render_report(path: Path, process_rows: Sequence[Mapping[str, Any]], temperature_rows: Sequence[Mapping[str, Any]],
                  summary: Mapping[str, Any]) -> None:
    """Write the final report around exactly the four PVT baseline questions."""

    process_corners = []
    for row in process_rows:
        corner = str(row["corner"])
        if corner not in process_corners:
            process_corners.append(corner)
    lines = [
        "# FTC Tap29 Real-XOR PVT Baseline Characterization",
        "",
        "This report reuses the approved TT/25 C 36-point `fine.csv` baseline. It measures only the frozen 4-RVT/0-LVT, 30-stage, full-real-XOR-bank `xor_29` topology with a 1 ps transient maximum step.",
        "",
        "## Q1. Process variation 有多大？",
        "",
        "| Process corner | W_real @ 1.10 V (ps) | W_real @ 0.90 V (ps) | W_real @ 0.75 V (ps) |",
        "|---|---:|---:|---:|",
    ]
    for corner in process_corners:
        values = []
        for voltage in ANCHOR_VDDS:
            row = next(item for item in process_rows if str(item["corner"]) == corner and voltage_key(item["vdd_v"]) == voltage_key(voltage))
            values.append(report_number(row["W_real_ps"]))
        lines.append("| {} | {} | {} | {} |".format(corner, *values))
    lines.extend(["", "| VDD (V) | Process span (ps) |", "|---:|---:|"])
    for voltage in ANCHOR_VDDS:
        key = "{:.2f}".format(voltage)
        lines.append("| {} | {} |".format(key, report_number(summary["process_only"][key]["process_span_ps"])))
    lines.extend(["", "## Q2. Temperature variation 有多大？", "", "| Temperature (C) | W_real @ 1.10 V (ps) | W_real @ 0.90 V (ps) | W_real @ 0.75 V (ps) |", "|---:|---:|---:|---:|"])
    for temperature in TEMPERATURES_C:
        values = []
        for voltage in ANCHOR_VDDS:
            row = next(item for item in temperature_rows if float(item["temperature_c"]) == temperature and voltage_key(item["vdd_v"]) == voltage_key(voltage))
            values.append(report_number(row["W_real_ps"]))
        lines.append("| {:.0f} | {} | {} | {} |".format(temperature, *values))
    lines.extend(["", "| VDD (V) | Temperature span (ps) | Temperature behavior |", "|---:|---:|---|"])
    for voltage in ANCHOR_VDDS:
        key = "{:.2f}".format(voltage)
        lines.append("| {} | {} | `{}` |".format(key, report_number(summary["temperature_only"][key]["temperature_span_ps"]), summary["temperature_behavior"][key]["behavior"]))
    lines.extend(["", "## Q3. PVT spread 与 voltage sensitivity 相比是什么量级？", "", "![PVT envelope](../analysis/real_xor_pvt_baseline/fig1_pvt_envelope_vs_nominal.svg)", "", "![Spread comparison](../analysis/real_xor_pvt_baseline/fig2_pvt_spread_vs_vdd_shift.svg)", "", "| VDD (V) | Combined PVT span (ps) | 50 mV shift (ps) | 100 mV shift (ps) | PVT/50 mV | PVT/100 mV |", "|---:|---:|---:|---:|---:|---:|"])
    for voltage in ("1.10", "0.90"):
        values = summary["pvt_vs_vdd_shift"][voltage]
        lines.append("| {} | {} | {} | {} | {} | {} |".format(voltage, report_number(values["pvt_span_ps"]), report_number(values["shift_50mV_ps"]), report_number(values["shift_100mV_ps"]), report_number(values["pvt_span_to_50mV_shift"]), report_number(values["pvt_span_to_100mV_shift"])))
    lines.extend(["", "## Q4. 固定 TT/25 C Golden Model 会产生多大等效 VDD 偏差？", "", "![Golden-equivalent VDD error](../analysis/real_xor_pvt_baseline/fig3_golden_equivalent_error.svg)", ""])
    golden = summary["golden_model"]
    lines.extend([
        "- max |golden_equivalent_error_mV|: {} mV".format(report_number(golden["max_abs_golden_equivalent_error_mV"])),
        "- median |golden_equivalent_error_mV|: {} mV".format(report_number(golden["median_abs_golden_equivalent_error_mV"])),
        "- out_of_nominal_curve scenarios: {}.".format(golden["out_of_nominal_curve_count"]),
        "- worst scenario: `{}`.".format(golden["worst_scenario"] if golden["worst_scenario"] is not None else "n/a"),
        "",
        "## Research conclusion",
        "",
        "**PVT_IMPACT = {}**".format(summary["pvt_impact"]["PVT_IMPACT"]),
    ])
    lines.extend("- {}.".format(item) for item in summary["pvt_impact"]["basis"])
    impact = summary["pvt_impact"]["PVT_IMPACT"]
    # State the research implication explicitly while keeping it separate from
    # any unimplemented calibration design or final sensor GO/NO-GO claim.
    if impact == "SMALL":
        interpretation = "在这三个 anchor 上，固定 TT/25 C Golden Model 的 PVT 基线偏差小于 50 mV 特征；本表征本身不显示其必然失效。"
    elif impact == "NON_NEGLIGIBLE":
        interpretation = "固定 TT/25 C Golden Model 的 PVT 基线偏差已与目标电压特征同量级，因此 self-calibration / programmable reference 具有明确的定量研究必要性。"
    else:
        interpretation = "至少一个 anchor 的 combined PVT span 超过 100 mV 脉宽特征，因此固定 TT/25 C Golden Model 对该范围不够稳健；self-calibration / programmable reference 具有明确的定量研究必要性。"
    lines.extend([
        "",
        interpretation,
        "",
        "在当前已验证的 tap29 真实 XOR 脉宽传感前端中，以上实测 process/temperature 基线漂移及其相对 50 mV、100 mV VDD 脉宽特征的量级关系，定量说明固定 TT/25 C Golden Model 的适用边界，并为下一阶段自校准可编程时间参考提供输入；本报告未实现或验证任何自校准电路。",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    """Expose output locations only; PVT coordinates are fixed research controls."""

    parser = argparse.ArgumentParser(description="characterize frozen FTC xor_29 PVT baseline")
    parser.add_argument("--config", type=Path, default=FTC_ROOT / "ftc_config.json", help="frozen FTC configuration")
    parser.add_argument("--run-dir", type=Path, default=FTC_ROOT / "runs" / "real_xor_pvt_baseline", help="ignored raw HSPICE run root")
    parser.add_argument("--analysis-dir", type=Path, default=FTC_ROOT / "analysis" / "real_xor_pvt_baseline", help="compact PVT evidence directory")
    parser.add_argument("--report-output", type=Path, default=FTC_ROOT / "reports" / "FTC_TAP29_PVT_BASELINE_CHARACTERIZATION.md", help="final PVT report")
    return parser.parse_args(argv)


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Run the ordered, minimum PVT experiment and retain compact evidence.

    The manifest and PDK corner record are written before the first physical
    scenario.  Process and temperature screens are independently written and
    validated before envelope matrix scenarios are even placed in the queue.
    This ordering prevents both nominal reruns and a full-PVT expansion.
    """

    args = parse_args(argv)
    config = characterization.load_json(args.config.resolve())
    cells = characterization.load_json(FTC_ROOT / "discovery" / "selected_cells.json")
    point = verify_frozen_topology(config, cells)
    verify_rendered_topology(config, cells, point)
    nominal = load_nominal_fine(FTC_ROOT / "analysis" / "real_xor_pulse_width" / "fine.csv")
    analysis_dir = args.analysis_dir.resolve()
    run_dir = args.run_dir.resolve()
    report_output = args.report_output.resolve()

    metadata = process_corner_metadata(Path(config["model_library"]), str(config["corner"]))
    corners = [str(corner) for corner in metadata["selected_process_corners_for_screen"]]
    manifest = initial_manifest(corners)
    # These two compact artifacts intentionally precede prepare_output(): a
    # reviewer can inspect the exact PVT queue before any HSPICE deck exists.
    write_json(analysis_dir / "process_corners.json", metadata)
    write_csv(analysis_dir / "scenario_manifest.csv", MANIFEST_FIELDS, manifest)

    # The shared helper verifies HSPICE version and all collateral, writes the
    # raw-run manifest, and refuses to overwrite a prior physical campaign.
    hspice = characterization.prepare_output(run_dir, config, cells)
    process_plan = screen_entries(corners, "process")
    process_rows, next_index = run_entries(hspice, run_dir, config, cells, point, process_plan, nominal, 0)
    write_csv(analysis_dir / "process_screen.csv", PVT_FIELDS, process_rows)
    require_complete_rows(process_rows, "process screen", len(process_plan))

    temperature_plan = screen_entries(corners, "temperature")
    temperature_rows, next_index = run_entries(
        hspice, run_dir, config, cells, point, temperature_plan, nominal, next_index,
    )
    write_csv(analysis_dir / "temperature_screen.csv", PVT_FIELDS, temperature_rows)
    require_complete_rows(temperature_rows, "temperature screen", len(temperature_plan))

    selected_corners, envelope = select_envelope_corners(process_rows, corners)
    matrix_plan = matrix_entries(selected_corners, process_rows, temperature_rows)
    # Extend the audit queue before matrix HSPICE execution; duplicate screen
    # rows stay single manifest entries and are reused only in matrix evidence.
    manifest = extend_manifest(manifest, matrix_plan)
    write_csv(analysis_dir / "scenario_manifest.csv", MANIFEST_FIELDS, manifest)
    reusable = evidence_by_key(list(process_rows) + list(temperature_rows))
    matrix_rows, next_index = run_entries(
        hspice, run_dir, config, cells, point, matrix_plan, nominal, next_index, reusable,
    )
    write_csv(analysis_dir / "pvt_matrix.csv", PVT_FIELDS, matrix_rows)
    require_complete_rows(matrix_rows, "selected PVT matrix", len(matrix_plan))

    summary, golden_rows = build_summary(process_rows, temperature_rows, matrix_rows, nominal, selected_corners, envelope)
    summary.update({
        "process_screen_row_count": len(process_rows),
        "temperature_screen_row_count": len(temperature_rows),
        "pvt_matrix_row_count": len(matrix_rows),
        "new_hspice_scenario_count": next_index,
        "reused_tt25_fine_row_count": sum(1 for row in matrix_rows if row["source"] == "reused_tt25_fine"),
        "golden_equivalent_rows": golden_rows,
    })
    write_json(analysis_dir / "summary.json", summary)
    plot_envelope(nominal, summary["combined_pvt"], analysis_dir)
    plot_spread_comparison(summary, analysis_dir)
    plot_golden_error(golden_rows, selected_corners, analysis_dir)
    render_report(report_output, process_rows, temperature_rows, summary)
    print(
        "FTC_TAP29_PVT_BASELINE PVT_IMPACT={} selected_corners={} new_hspice_scenarios={}".format(
            summary["pvt_impact"]["PVT_IMPACT"], ",".join(selected_corners), next_index,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
