#!/usr/bin/env python3
"""Map completed FTC RVT/LVT crossing differences to XOR-width proxies.

This module is deliberately a CSV-only post-processing tool.  It consumes
completed crossing evidence, never imports an FTC deck or runner, and never
interpolates a missing voltage or tap.  Its result is an *ideal XOR input
window* proxy, not a claim about the pulse width at a physical XOR-cell
output.
"""

import argparse
import csv
import json
import math
import statistics
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

try:
    import matplotlib

    # The analysis is also run in batch shells; force a non-interactive
    # backend before pyplot is imported so SVG generation needs no display.
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except ImportError as error:  # pragma: no cover - only reached without plotting support.
    raise SystemExit(
        "FTC XOR pulse-width analysis requires Matplotlib. Install it with "
        "`python -m pip install matplotlib`: {}".format(error)
    )


FTC_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FINE_INPUT = FTC_ROOT / "runs/static_fine/static_transfer.csv"
DEFAULT_COARSE_INPUT = FTC_ROOT / "runs/phase_diverse_screen/phase_candidate_coarse.csv"
DEFAULT_OUTPUT_DIR = FTC_ROOT / "analysis/xor_pulse_width_vdd"
DEFAULT_REPORT_OUTPUT = FTC_ROOT / "reports/FTC_XOR_PULSE_WIDTH_VDD_MAPPING.md"

TAP_COUNT = 30
FINE_VDDS = tuple(round(1.10 - 0.01 * index, 2) for index in range(36))
COARSE_VDDS = (1.10, 1.05, 1.00, 0.95, 0.90, 0.85, 0.80, 0.75)
MATRIX_FIELDS = (
    "vdd_v",
    "tap_index",
    "rvt_cross_s",
    "lvt_cross_s",
    "delta_signed_ps",
    "xor_width_proxy_ps",
    "lead_path",
)


def vdd_key(value: float) -> float:
    """Normalize decimal labels before using VDD as an evidence-table key.

    CSV values such as ``1.10`` are physical labels rather than computed
    results.  Rounding only for dictionary/grid comparison prevents binary
    floating-point representation from splitting an otherwise identical VDD.
    """

    return round(float(value), 9)


def format_number(value: Any) -> Any:
    """Keep output CSVs compact while preserving analysis-significant values."""

    return "{:.12g}".format(float(value)) if isinstance(value, float) else value


def read_csv_rows(path: Path) -> Tuple[List[Dict[str, str]], List[str]]:
    """Load nonempty completed evidence without changing the source file.

    Rows stay string-keyed until per-row validation identifies the physical
    source field and row responsible for any malformed evidence.
    """

    if not path.is_file():
        raise ValueError("required completed FTC evidence is unavailable: {}".format(path))
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames:
            raise ValueError("CSV has no header: {}".format(path))
        rows = list(reader)
        fields = list(reader.fieldnames)
    if not rows:
        raise ValueError("CSV has no physical samples: {}".format(path))
    return rows, fields


def required_float(row: Mapping[str, Any], field: str, source: Path, row_number: int) -> float:
    """Read one required finite scalar and identify bad evidence precisely."""

    try:
        value = float(row[field])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("{} row {} has invalid {}".format(source, row_number, field)) from error
    if not math.isfinite(value):
        raise ValueError("{} row {} has non-finite {}".format(source, row_number, field))
    return value


def required_integer(row: Mapping[str, Any], field: str, source: Path, row_number: int) -> int:
    """Read an integer-valued optional operating-point field without rounding."""

    value = required_float(row, field, source, row_number)
    if not value.is_integer():
        raise ValueError("{} row {} has non-integer {}".format(source, row_number, field))
    return int(value)


def parse_crossings(row: Mapping[str, Any], field: str, source: Path, row_number: int) -> List[float]:
    """Parse exactly 30 finite positive crossing times from one CSV cell.

    A malformed array is not repaired or truncated: every crossing is a
    measured physical input and omitting one would invent a tap alignment.
    """

    try:
        values = json.loads(str(row[field]))
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("{} row {} has invalid {} JSON".format(source, row_number, field)) from error
    if not isinstance(values, list) or len(values) != TAP_COUNT:
        raise ValueError("{} row {} {} must contain {} crossings".format(source, row_number, field, TAP_COUNT))
    try:
        parsed = [float(value) for value in values]
    except (TypeError, ValueError) as error:
        raise ValueError("{} row {} has non-numeric {}".format(source, row_number, field)) from error
    if not all(math.isfinite(value) and value > 0.0 for value in parsed):
        raise ValueError("{} row {} {} must contain finite positive crossings".format(source, row_number, field))
    return parsed


def validate_record(row: Mapping[str, Any], source: Path, row_number: int) -> Dict[str, Any]:
    """Validate one source row against the fixed FTC crossing contract."""

    required = ("vdd_v", "rvt_crossings_s", "lvt_crossings_s")
    missing = [field for field in required if field not in row]
    if missing:
        raise ValueError("{} is missing required columns: {}".format(source, ", ".join(missing)))
    vdd = required_float(row, "vdd_v", source, row_number)
    if not 0.75 <= vdd <= 1.10:
        raise ValueError("{} row {} VDD lies outside 0.75--1.10 V".format(source, row_number))
    if "initial_rvt_stages" in row and required_integer(row, "initial_rvt_stages", source, row_number) != 4:
        raise ValueError("{} row {} is not the selected 4-RVT operating point".format(source, row_number))
    if "initial_lvt_stages" in row and required_integer(row, "initial_lvt_stages", source, row_number) != 0:
        raise ValueError("{} row {} is not the selected 0-LVT operating point".format(source, row_number))
    return {
        "vdd_v": vdd,
        "rvt_crossings_s": parse_crossings(row, "rvt_crossings_s", source, row_number),
        "lvt_crossings_s": parse_crossings(row, "lvt_crossings_s", source, row_number),
        "source_row": row_number,
    }


def validate_grid(records: Sequence[Mapping[str, Any]], expected_vdds: Sequence[float], source: Path) -> List[Dict[str, Any]]:
    """Require one measured row at every prescribed VDD, in descending order.

    The task permits a fine 10 mV grid or a committed coarse 50 mV grid, but
    not a partial curve.  Rejecting missing and duplicate labels prevents any
    downstream metric from silently interpolating or mixing experiments.
    """

    actual_vdds = tuple(vdd_key(record["vdd_v"]) for record in records)
    expected = tuple(vdd_key(value) for value in expected_vdds)
    if actual_vdds != expected:
        raise ValueError("{} must contain exactly the required descending VDD grid".format(source))
    if len({vdd_key(record["vdd_v"]) for record in records}) != len(records):
        raise ValueError("{} contains duplicate VDD evidence".format(source))
    return [dict(record) for record in records]


def select_nominal_coarse_rows(rows: Sequence[Mapping[str, str]], fields: Sequence[str], source: Path) -> List[Dict[str, str]]:
    """Select only the nominal 300 ps phase from repeated coarse experiments.

    Other phase rows remain useful for a later repeatability check, but using
    them as extra VDD samples would create a false transfer curve.
    """

    if "phase_id" in fields:
        selected = [dict(row) for row in rows if row.get("phase_id") == "phi_p00"]
        selector = "phase_id=phi_p00"
    elif "phase_multiplier" in fields:
        selected = []
        for row_number, row in enumerate(rows, start=2):
            if required_integer(row, "phase_multiplier", source, row_number) == 0:
                selected.append(dict(row))
        selector = "phase_multiplier=0"
    else:
        raise ValueError("{} lacks phase_id and phase_multiplier for nominal coarse selection".format(source))
    if not selected:
        raise ValueError("{} has no {} rows".format(source, selector))
    return selected


def load_primary_evidence(fine_path: Path, coarse_path: Path) -> Tuple[str, Path, List[Dict[str, Any]]]:
    """Choose fine evidence first, falling back only when the fine file is absent."""

    if fine_path.is_file():
        raw_rows, _ = read_csv_rows(fine_path)
        records = [validate_record(row, fine_path, index + 2) for index, row in enumerate(raw_rows)]
        return "36-point fine evidence", fine_path, validate_grid(records, FINE_VDDS, fine_path)
    raw_rows, fields = read_csv_rows(coarse_path)
    nominal = select_nominal_coarse_rows(raw_rows, fields, coarse_path)
    records = [validate_record(row, coarse_path, index + 2) for index, row in enumerate(nominal)]
    return "8-point committed coarse evidence", coarse_path, validate_grid(records, COARSE_VDDS, coarse_path)


def lead_path(delta_signed_ps: float) -> str:
    """Name the leading path directly from the exact measured signed delta."""

    if delta_signed_ps > 0.0:
        return "LVT"
    if delta_signed_ps < 0.0:
        return "RVT"
    return "tie"


def build_proxy_matrix(records: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Expand one physical crossing row into 30 same-index proxy measurements."""

    matrix: List[Dict[str, Any]] = []
    for record in records:
        for tap_index, (rvt_cross_s, lvt_cross_s) in enumerate(zip(record["rvt_crossings_s"], record["lvt_crossings_s"])):
            delta_signed_ps = (float(rvt_cross_s) - float(lvt_cross_s)) * 1.0e12
            matrix.append(
                {
                    "vdd_v": float(record["vdd_v"]),
                    "tap_index": tap_index,
                    "rvt_cross_s": float(rvt_cross_s),
                    "lvt_cross_s": float(lvt_cross_s),
                    "delta_signed_ps": delta_signed_ps,
                    "xor_width_proxy_ps": abs(delta_signed_ps),
                    "lead_path": lead_path(delta_signed_ps),
                }
            )
    return matrix


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> None:
    """Write deterministic task outputs with an explicit, stable schema."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(fields), extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: format_number(row.get(field, "")) for field in fields})


def sign(value: float) -> int:
    """Return the exact sign used by the task's lead-path reversal rule."""

    return 1 if value > 0.0 else (-1 if value < 0.0 else 0)


def lead_sign_metrics(deltas_signed_ps: Sequence[float]) -> Dict[str, Any]:
    """Describe whether one physical path leads throughout the VDD range.

    A zero is retained as a real tie.  A ``+ -> 0 -> -`` sequence counts as
    one reversal, whereas ``+ -> 0 -> +`` does not fabricate a reversal.
    """

    signs = [sign(value) for value in deltas_signed_ps]
    lead_sign_stable = bool(signs) and len(set(signs)) == 1 and signs[0] != 0
    last_nonzero: Optional[int] = None
    sign_flip_count = 0
    for current in signs:
        if current == 0:
            continue
        if last_nonzero is not None and current != last_nonzero:
            sign_flip_count += 1
        last_nonzero = current
    if lead_sign_stable:
        stable_lead_path = "LVT" if signs[0] > 0 else "RVT"
    elif all(current == 0 for current in signs):
        stable_lead_path = "tie"
    else:
        stable_lead_path = "mixed"
    return {
        "lead_sign_stable": lead_sign_stable,
        "lead_path": stable_lead_path,
        "sign_flip_count": sign_flip_count,
    }


def monotonic_summary(widths_ps: Sequence[float]) -> Dict[str, Any]:
    """Classify only adjacent measured changes; no smoothing or fitting occurs."""

    if len(widths_ps) < 2:
        raise ValueError("monotonicity requires at least two measured VDD points")
    steps = [later - earlier for earlier, later in zip(widths_ps, widths_ps[1:])]
    positive = sum(step > 0.0 for step in steps)
    negative = sum(step < 0.0 for step in steps)
    plateau_count = sum(step == 0.0 for step in steps)
    if positive == len(steps):
        classification = "strict_increasing"
        violations = 0
    elif negative == len(steps):
        classification = "strict_decreasing"
        violations = 0
    elif negative == 0:
        classification = "nondecreasing_with_plateau"
        violations = 0
    elif positive == 0:
        classification = "nonincreasing_with_plateau"
        violations = 0
    else:
        classification = "nonmonotonic"
        # The smaller opposing-direction count states how many measured steps
        # prevent the best possible monotonic interpretation of this curve.
        violations = min(positive, negative)
    return {
        "monotonic_class": classification,
        "monotonic_violation_count": violations,
        "plateau_count": plateau_count,
        "step_deltas_ps": steps,
    }


def matrix_by_tap(matrix: Sequence[Mapping[str, Any]]) -> Dict[int, List[Dict[str, Any]]]:
    """Group the already VDD-ordered long table without changing its evidence order."""

    grouped: Dict[int, List[Dict[str, Any]]] = {tap_index: [] for tap_index in range(TAP_COUNT)}
    for row in matrix:
        grouped[int(row["tap_index"])].append(dict(row))
    if any(len(rows) == 0 for rows in grouped.values()):
        raise ValueError("proxy matrix does not contain every required tap")
    return grouped


def metrics_from_matrix(matrix: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Calculate the plan's direct, per-tap mapping metrics from physical rows."""

    result: List[Dict[str, Any]] = []
    for tap_index, rows in matrix_by_tap(matrix).items():
        vdds = [float(row["vdd_v"]) for row in rows]
        widths = [float(row["xor_width_proxy_ps"]) for row in rows]
        deltas = [float(row["delta_signed_ps"]) for row in rows]
        monotonic = monotonic_summary(widths)
        step_deltas = list(monotonic["step_deltas_ps"])
        sensitivities = [
            step_delta / (later_vdd - earlier_vdd) * 0.1
            for step_delta, earlier_vdd, later_vdd in zip(step_deltas, vdds, vdds[1:])
        ]
        sign_result = lead_sign_metrics(deltas)
        result.append(
            {
                "tap_index": tap_index,
                **sign_result,
                "monotonic_class": monotonic["monotonic_class"],
                "monotonic_violation_count": monotonic["monotonic_violation_count"],
                "plateau_count": monotonic["plateau_count"],
                "span_ps": max(widths) - min(widths),
                "endpoint_delta_ps": widths[-1] - widths[0],
                "abs_endpoint_delta_ps": abs(widths[-1] - widths[0]),
                "min_abs_step_ps": min(abs(value) for value in step_deltas),
                "median_abs_step_ps": statistics.median(abs(value) for value in step_deltas),
                "max_abs_step_ps": max(abs(value) for value in step_deltas),
                "median_abs_sensitivity_ps_per_100mV": statistics.median(abs(value) for value in sensitivities),
                "min_abs_sensitivity_ps_per_100mV": min(abs(value) for value in sensitivities),
                "max_abs_sensitivity_ps_per_100mV": max(abs(value) for value in sensitivities),
                "min_abs_50mV_step_ps": None,
                "max_repeat_range_ps": None,
                "step_margin_ps": None,
            }
        )
    return result


def add_50mv_step_metrics(metrics: Sequence[Mapping[str, Any]], matrix: Sequence[Mapping[str, Any]]) -> None:
    """Add the measured 50 mV movement used for the coarse-repeat comparison."""

    coarse_keys = {vdd_key(value) for value in COARSE_VDDS}
    by_tap = matrix_by_tap(matrix)
    for metric in metrics:
        rows = [row for row in by_tap[int(metric["tap_index"])] if vdd_key(float(row["vdd_v"])) in coarse_keys]
        if tuple(vdd_key(float(row["vdd_v"])) for row in rows) != tuple(vdd_key(value) for value in COARSE_VDDS):
            raise ValueError("proxy matrix lacks the required 50 mV comparison grid")
        widths = [float(row["xor_width_proxy_ps"]) for row in rows]
        metric["min_abs_50mV_step_ps"] = min(abs(later - earlier) for earlier, later in zip(widths, widths[1:]))


def repeat_consistency(coarse_path: Path) -> Tuple[Optional[List[Dict[str, Any]]], Dict[int, float]]:
    """Measure existing phase-run spread without treating it as PVT or noise.

    ``None`` means the optional coarse file is unavailable.  A present but
    malformed file remains an error, because silently dropping available
    physical evidence would make the reported consistency claim misleading.
    """

    if not coarse_path.is_file():
        return None, {}
    raw_rows, fields = read_csv_rows(coarse_path)
    if "phase_id" in fields:
        def phase_label(row: Mapping[str, str], row_number: int) -> str:
            value = str(row.get("phase_id", ""))
            if not value:
                raise ValueError("{} row {} has empty phase_id".format(coarse_path, row_number))
            return value
    elif "phase_multiplier" in fields:
        def phase_label(row: Mapping[str, str], row_number: int) -> str:
            return "multiplier={}".format(required_integer(row, "phase_multiplier", coarse_path, row_number))
    else:
        raise ValueError("{} lacks a phase label for repeat consistency".format(coarse_path))
    records = []
    for index, row in enumerate(raw_rows, start=2):
        record = validate_record(row, coarse_path, index)
        record["phase_label"] = phase_label(row, index)
        records.append(record)
    grouped: Dict[float, List[Dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(vdd_key(float(record["vdd_v"])), []).append(record)
    if tuple(sorted(grouped, reverse=True)) != tuple(vdd_key(value) for value in COARSE_VDDS):
        raise ValueError("{} does not cover the completed coarse VDD grid".format(coarse_path))
    if any(len({record["phase_label"] for record in grouped[vdd_key(value)]}) < 2 for value in COARSE_VDDS):
        raise ValueError("{} lacks repeated phase evidence at one or more coarse VDDs".format(coarse_path))

    rows: List[Dict[str, Any]] = []
    max_ranges = {tap_index: 0.0 for tap_index in range(TAP_COUNT)}
    for vdd in COARSE_VDDS:
        repeats = grouped[vdd_key(vdd)]
        for tap_index in range(TAP_COUNT):
            widths = [
                abs((record["rvt_crossings_s"][tap_index] - record["lvt_crossings_s"][tap_index]) * 1.0e12)
                for record in repeats
            ]
            repeat_range_ps = max(widths) - min(widths)
            rows.append(
                {
                    "vdd_v": vdd,
                    "tap_index": tap_index,
                    "repeat_count": len(widths),
                    "repeat_min_ps": min(widths),
                    "repeat_max_ps": max(widths),
                    "repeat_range_ps": repeat_range_ps,
                }
            )
            max_ranges[tap_index] = max(max_ranges[tap_index], repeat_range_ps)
    return rows, max_ranges


def add_repeat_metrics(metrics: Sequence[Mapping[str, Any]], max_ranges: Mapping[int, float]) -> None:
    """Attach each tap's worst repeat spread and its 50 mV separation margin."""

    for metric in metrics:
        tap_index = int(metric["tap_index"])
        if tap_index not in max_ranges:
            continue
        metric["max_repeat_range_ps"] = float(max_ranges[tap_index])
        metric["step_margin_ps"] = float(metric["min_abs_50mV_step_ps"]) - float(max_ranges[tap_index])


def eligible_for_mapping(metric: Mapping[str, Any]) -> bool:
    """Apply the plan's explainability gates before comparing sensitivity."""

    return bool(metric["lead_sign_stable"]) and metric["monotonic_class"] != "nonmonotonic"


def rank_and_shortlist(metrics: Sequence[Mapping[str, Any]], repeat_available: bool) -> List[Dict[str, Any]]:
    """Rank explainable taps without a weighted score or a multi-tap decoder.

    A tap that uniquely maximizes both span and median sensitivity after all
    prior gates is the sole obvious winner.  Otherwise the first three ranked
    taps remain a measurement shortlist, never a proposed fusion architecture.
    """

    eligible = [dict(metric) for metric in metrics if eligible_for_mapping(metric)]
    ranked = sorted(
        eligible,
        key=lambda metric: (
            int(metric["plateau_count"]),
            0 if (not repeat_available or float(metric["step_margin_ps"]) > 0.0) else 1,
            -float(metric["span_ps"]),
            -float(metric["median_abs_sensitivity_ps_per_100mV"]),
            int(metric["tap_index"]),
        ),
    )
    if not ranked:
        return []
    first = ranked[0]
    unique_best = all(
        int(other["tap_index"]) == int(first["tap_index"])
        or (
            float(first["span_ps"]) > float(other["span_ps"])
            and float(first["median_abs_sensitivity_ps_per_100mV"])
            > float(other["median_abs_sensitivity_ps_per_100mV"])
        )
        for other in ranked
    )
    return ranked[:1] if unique_best else ranked[:3]


def decision_from_metrics(metrics: Sequence[Mapping[str, Any]], repeat_available: bool) -> Tuple[str, List[str]]:
    """Make only the prescribed GO/CONDITIONAL/NO-GO research decision."""

    go_taps = [
        metric
        for metric in metrics
        if eligible_for_mapping(metric)
        and metric["monotonic_class"] in ("strict_increasing", "strict_decreasing")
        and int(metric["plateau_count"]) == 0
        and float(metric["span_ps"]) > 0.0
        and float(metric["min_abs_step_ps"]) > 0.0
        and (not repeat_available or float(metric["step_margin_ps"]) > 0.0)
    ]
    if go_taps:
        return (
            "GO",
            [
                "{} tap(s) have stable path order, strict measured monotonicity, and nonzero VDD movement.".format(len(go_taps)),
                "Existing repeat evidence is {} and is used only as a same-run consistency check.".format("available" if repeat_available else "unavailable"),
                "Authorize only real XOR-output pulse-width validation of the shortlist; no readout architecture is selected.",
            ],
        )
    conditional = [metric for metric in metrics if eligible_for_mapping(metric) and float(metric["span_ps"]) > 0.0]
    if conditional:
        return (
            "CONDITIONAL",
            [
                "At least one tap is directionally interpretable, but plateau, local movement, or repeat-margin evidence prevents a clean GO.",
                "Authorize only limited real XOR-output checks before any architecture discussion.",
            ],
        )
    return (
        "NO-GO",
        [
            "No tap has both stable lead order and an interpretable monotonic width mapping in the completed evidence.",
            "Do not add multi-tap decoding or new FTC hardware to force a pulse-width route.",
        ],
    )


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Write a stable review artifact after reducing analysis values to builtins."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def configure_plot_style() -> None:
    """Use one compact readable SVG style for all five required figures."""

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.labelsize": 10,
            "axes.titlesize": 11,
            "svg.fonttype": "none",
        }
    )


def save_figure(figure: Any, path: Path) -> None:
    """Save SVG output and normalize only harmless trailing render whitespace."""

    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, format="svg", bbox_inches="tight", metadata={"Date": None})
    plt.close(figure)
    normalized = "\n".join(line.rstrip() for line in path.read_text(encoding="utf-8").splitlines()) + "\n"
    path.write_text(normalized, encoding="utf-8")


def plot_heatmap(matrix: Sequence[Mapping[str, Any]], path: Path, field: str, title: str, color_label: str, color_map: str) -> None:
    """Render a tap-by-VDD physical value map without interpolation or smoothing."""

    configure_plot_style()
    grouped = matrix_by_tap(matrix)
    vdds = [float(row["vdd_v"]) for row in grouped[0]]
    image = [[float(row[field]) for row in grouped[tap_index]] for tap_index in range(TAP_COUNT)]
    figure, axis = plt.subplots(figsize=(8.2, 5.4))
    rendered = axis.imshow(image, aspect="auto", origin="lower", interpolation="none", cmap=color_map)
    tick_step = 5 if len(vdds) > len(COARSE_VDDS) else 1
    ticks = list(range(0, len(vdds), tick_step))
    axis.set_xticks(ticks)
    axis.set_xticklabels(["{:.2f}".format(vdds[index]) for index in ticks], rotation=45, ha="right")
    axis.set_yticks(range(0, TAP_COUNT, 5))
    axis.set_xlabel("VDD (V), descending evidence order")
    axis.set_ylabel("Tap index")
    axis.set_title(title)
    colorbar = figure.colorbar(rendered, ax=axis, pad=0.02)
    colorbar.set_label(color_label)
    save_figure(figure, path)


def plot_span(metrics: Sequence[Mapping[str, Any]], path: Path) -> None:
    """Show endpoint width movement per tap on its own axis and unit scale."""

    configure_plot_style()
    figure, axis = plt.subplots(figsize=(7.2, 3.8))
    axis.plot([row["tap_index"] for row in metrics], [row["abs_endpoint_delta_ps"] for row in metrics], "-o", color="#0072B2", markersize=3.5)
    axis.set_xlabel("Tap index")
    axis.set_ylabel("|W(0.75 V) - W(1.10 V)| (ps)")
    axis.set_title("Fig. 2. Proxy-width endpoint span versus tap")
    axis.grid(True, linewidth=0.5, alpha=0.35)
    save_figure(figure, path)


def plot_sensitivity(metrics: Sequence[Mapping[str, Any]], path: Path) -> None:
    """Show measured finite-difference sensitivity separately from span."""

    configure_plot_style()
    figure, axis = plt.subplots(figsize=(7.2, 3.8))
    axis.plot(
        [row["tap_index"] for row in metrics],
        [row["median_abs_sensitivity_ps_per_100mV"] for row in metrics],
        "-o",
        color="#D55E00",
        markersize=3.5,
    )
    axis.set_xlabel("Tap index")
    axis.set_ylabel("Median |dW/dVDD| (ps / 100 mV)")
    axis.set_title("Fig. 3. Proxy-width sensitivity versus tap")
    axis.grid(True, linewidth=0.5, alpha=0.35)
    save_figure(figure, path)


def plot_candidates(matrix: Sequence[Mapping[str, Any]], shortlist: Sequence[Mapping[str, Any]], path: Path) -> None:
    """Plot only the measured shortlist, never a visually cluttered 30-line chart."""

    configure_plot_style()
    figure, axis = plt.subplots(figsize=(7.2, 4.0))
    grouped = matrix_by_tap(matrix)
    if shortlist:
        for metric in shortlist:
            rows = sorted(grouped[int(metric["tap_index"])], key=lambda row: float(row["vdd_v"]))
            axis.plot(
                [row["vdd_v"] for row in rows],
                [row["xor_width_proxy_ps"] for row in rows],
                "-o",
                markersize=3.5,
                label="Tap {}".format(metric["tap_index"]),
            )
        axis.legend(loc="best")
        axis.grid(True, linewidth=0.5, alpha=0.35)
        axis.set_xlabel("VDD (V)")
        axis.set_ylabel("W_proxy (ps)")
    else:
        axis.text(0.5, 0.5, "No explainable tap qualified for a shortlist", ha="center", va="center", transform=axis.transAxes)
        axis.set_xticks([])
        axis.set_yticks([])
    axis.set_title("Fig. 4. Candidate proxy width versus VDD")
    save_figure(figure, path)


def markdown_table(headers: Sequence[str], rows: Iterable[Sequence[str]]) -> List[str]:
    """Create compact Markdown tables without an additional report dependency."""

    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(str(value) for value in row) + " |" for row in rows)
    return lines


def candidate_reason(metric: Mapping[str, Any], repeat_available: bool) -> str:
    """State the ranking evidence in report language without inventing a score."""

    fields = ["stable lead", str(metric["monotonic_class"]), "{} plateau(s)".format(metric["plateau_count"])]
    if repeat_available:
        fields.append("positive 50 mV margin" if float(metric["step_margin_ps"]) > 0.0 else "weak 50 mV margin")
    return "; ".join(fields)


def candidate_band_sensitivity(matrix: Sequence[Mapping[str, Any]], tap_index: int) -> Tuple[float, float]:
    """Compare measured high- and low-end slope magnitude for one candidate.

    This is a descriptive report check only.  It does not assume a global
    sensitivity model or extrapolate beyond the available VDD samples.
    """

    rows = matrix_by_tap(matrix)[tap_index]
    steps = [
        abs((float(later["xor_width_proxy_ps"]) - float(earlier["xor_width_proxy_ps"])) / (float(later["vdd_v"]) - float(earlier["vdd_v"])) * 0.1)
        for earlier, later in zip(rows, rows[1:])
    ]
    band_count = min(5, len(steps))
    return statistics.median(steps[:band_count]), statistics.median(steps[-band_count:])


def render_report(
    path: Path,
    source_kind: str,
    source_path: Path,
    matrix: Sequence[Mapping[str, Any]],
    metrics: Sequence[Mapping[str, Any]],
    shortlist: Sequence[Mapping[str, Any]],
    repeat_available: bool,
    repeat_source: Optional[Path],
    decision: str,
    decision_reasons: Sequence[str],
) -> None:
    """Render the required research report solely from computed task artifacts."""

    figure_root = "../analysis/xor_pulse_width_vdd"
    reversal_count = sum(int(metric["sign_flip_count"]) for metric in metrics)
    stable_count = sum(bool(metric["lead_sign_stable"]) for metric in metrics)
    grouped = matrix_by_tap(matrix)
    accumulates = all(
        float(grouped[tap_index + 1][vdd_index]["xor_width_proxy_ps"])
        > float(grouped[tap_index][vdd_index]["xor_width_proxy_ps"])
        for tap_index in range(TAP_COUNT - 1)
        for vdd_index in range(len(grouped[0]))
    )
    lines = [
        "# FTC XOR Pulse-Width Proxy to VDD Mapping",
        "",
        "## A. Motivation",
        "",
        "Fixed-time spatial snapshots previously exposed phase dependence and temporal blind windows. This analysis does not change capture phase or launch cadence; it checks whether existing RVT/LVT differential delay itself supplies a useful time-domain feature.",
        "",
        "## B. Input Evidence",
        "",
        "- Primary source: `{}` ({}; {} VDD points).".format(source_path, source_kind, len(grouped[0])),
        "- Repeat-phase consistency source: {}.".format("`{}`".format(repeat_source) if repeat_available else "not available"),
        "- Completed operating point: SMIC40LL TT/25 C, 4 RVT initial stages, 0 LVT initial stages, 30 observable stages, 300 ps capture phase.",
        "- No new HSPICE run, deck generation, FTC configuration change, or hardware change was performed.",
        "",
        "## C. Definition and Boundary",
        "",
        "For corresponding tap `i`, `Delta_i = t_RVT_i - t_LVT_i` and `W_proxy_i = |Delta_i|`, reported in ps. `W_proxy` is the path-crossing-derived ideal XOR input window; it is not the output pulse width of a real XOR cell and therefore excludes cell delay, rise/fall asymmetry, inertial filtering, loading, and short-pulse attenuation.",
        "",
        "## D. 30-tap Mapping",
        "",
        "![Fig. 1]({}/fig1_pulse_width_heatmap.svg)".format(figure_root),
        "",
        "![Fig. 2]({}/fig2_span_vs_tap.svg)".format(figure_root),
        "",
        "![Fig. 3]({}/fig3_sensitivity_vs_tap.svg)".format(figure_root),
        "",
        "![Fig. 5]({}/fig5_signed_delta_map.svg)".format(figure_root),
        "",
        "{} of 30 taps retain one nonzero lead sign across the measured range; total observed lead-path reversals are {}.".format(stable_count, reversal_count),
        "",
        "## E. Candidate Taps",
        "",
    ]
    lines.extend(
        markdown_table(
            ["Tap", "Lead path", "Monotonicity", "Span (ps)", "Sensitivity (ps/100 mV)", "Repeat margin (ps)", "Reason"],
            [
                [
                    metric["tap_index"],
                    metric["lead_path"],
                    metric["monotonic_class"],
                    "{:.3f}".format(float(metric["span_ps"])),
                    "{:.3f}".format(float(metric["median_abs_sensitivity_ps_per_100mV"])),
                    "{:.3f}".format(float(metric["step_margin_ps"])) if repeat_available else "n/a",
                    candidate_reason(metric, repeat_available),
                ]
                for metric in shortlist
            ],
        )
    )
    lines.extend(["", "![Fig. 4]({}/fig4_candidate_width_vs_vdd.svg)".format(figure_root), "", "## F. Physical Interpretation", ""])
    lines.append("- Differential proxy width {} along the 30 measured taps at every available VDD.".format("increases" if accumulates else "does not increase monotonically"))
    if shortlist:
        best = shortlist[0]
        high_band, low_band = candidate_band_sensitivity(matrix, int(best["tap_index"]))
        relation = "higher" if low_band > high_band else ("lower" if low_band < high_band else "equal")
        lines.extend(
            [
                "- Tap {} is the highest-ranked measured VDD-information location under the stated simple ranking order.".format(best["tap_index"]),
                "- Its median |dW/dVDD| is {:.3f} ps/100 mV over the high-end five steps and {:.3f} ps/100 mV over the low-end five steps; low-end sensitivity is {} in this evidence.".format(high_band, low_band, relation),
            ]
        )
    lines.extend(
        [
            "- No transistor-level mechanism is inferred beyond these measured crossing differences.",
            "",
            "## G. Final Decision: {}".format(decision),
            "",
        ]
    )
    lines.extend("- {}".format(reason) for reason in decision_reasons)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_analysis(fine_path: Path, coarse_path: Path, output_dir: Path, report_path: Path) -> Dict[str, Any]:
    """Execute the complete deterministic post-processing and write task outputs."""

    source_kind, source_path, records = load_primary_evidence(fine_path, coarse_path)
    matrix = build_proxy_matrix(records)
    metrics = metrics_from_matrix(matrix)
    add_50mv_step_metrics(metrics, matrix)
    repeat_rows, max_ranges = repeat_consistency(coarse_path)
    repeat_available = repeat_rows is not None
    if repeat_available:
        add_repeat_metrics(metrics, max_ranges)
    shortlist = rank_and_shortlist(metrics, repeat_available)
    decision, decision_reasons = decision_from_metrics(metrics, repeat_available)

    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "xor_pulse_width_matrix.csv", matrix, MATRIX_FIELDS)
    metric_fields = (
        "tap_index",
        "lead_sign_stable",
        "lead_path",
        "sign_flip_count",
        "monotonic_class",
        "monotonic_violation_count",
        "plateau_count",
        "span_ps",
        "endpoint_delta_ps",
        "abs_endpoint_delta_ps",
        "min_abs_step_ps",
        "median_abs_step_ps",
        "max_abs_step_ps",
        "min_abs_50mV_step_ps",
        "median_abs_sensitivity_ps_per_100mV",
        "min_abs_sensitivity_ps_per_100mV",
        "max_abs_sensitivity_ps_per_100mV",
        "max_repeat_range_ps",
        "step_margin_ps",
    )
    write_csv(output_dir / "tap_metrics.csv", metrics, metric_fields)
    if repeat_rows is not None:
        write_csv(
            output_dir / "repeat_consistency.csv",
            repeat_rows,
            ("vdd_v", "tap_index", "repeat_count", "repeat_min_ps", "repeat_max_ps", "repeat_range_ps"),
        )
    best_tap = int(shortlist[0]["tap_index"]) if shortlist else None
    summary = {
        "input_source": str(source_path),
        "input_evidence_kind": source_kind,
        "vdd_point_count": len(records),
        "used_new_hspice": False,
        "repeat_consistency_available": repeat_available,
        "repeat_consistency_source": str(coarse_path) if repeat_available else None,
        "best_tap": best_tap,
        "shortlisted_taps": [int(metric["tap_index"]) for metric in shortlist],
        "decision": decision,
        "decision_reason": decision_reasons,
    }
    write_json(output_dir / "summary.json", summary)
    plot_heatmap(matrix, output_dir / "fig1_pulse_width_heatmap.svg", "xor_width_proxy_ps", "Fig. 1. XOR input-window proxy across tap and VDD", "W_proxy (ps)", "viridis")
    plot_span(metrics, output_dir / "fig2_span_vs_tap.svg")
    plot_sensitivity(metrics, output_dir / "fig3_sensitivity_vs_tap.svg")
    plot_candidates(matrix, shortlist, output_dir / "fig4_candidate_width_vs_vdd.svg")
    plot_heatmap(matrix, output_dir / "fig5_signed_delta_map.svg", "delta_signed_ps", "Fig. 5. Signed RVT-LVT crossing difference and lead-path consistency", "Delta (ps)", "coolwarm")
    render_report(report_path, source_kind, source_path, matrix, metrics, shortlist, repeat_available, coarse_path if repeat_available else None, decision, decision_reasons)
    return {**summary, "output_dir": str(output_dir), "report_output": str(report_path)}


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Expose only completed evidence and output locations; no simulator options exist."""

    parser = argparse.ArgumentParser(description="analyze completed FTC XOR pulse-width proxy evidence")
    parser.add_argument("--fine-input", type=Path, default=DEFAULT_FINE_INPUT, help="completed 10 mV static crossing CSV")
    parser.add_argument("--coarse-input", type=Path, default=DEFAULT_COARSE_INPUT, help="committed coarse phase-diverse crossing CSV")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="task-owned analysis output directory")
    parser.add_argument("--report-output", type=Path, default=DEFAULT_REPORT_OUTPUT, help="research Markdown report path")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the post-processing flow and print a compact decision handoff."""

    args = parse_args(argv)
    result = run_analysis(args.fine_input.resolve(), args.coarse_input.resolve(), args.output_dir.resolve(), args.report_output.resolve())
    print("FTC_XOR_PULSE_WIDTH_VDD decision={} best_tap={}".format(result["decision"], result["best_tap"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
