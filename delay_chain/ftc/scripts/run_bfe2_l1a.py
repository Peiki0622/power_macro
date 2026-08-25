#!/usr/bin/env python3
"""Run the bounded B-FE2-L1A real-safe-domain-latch experiment.

This runner deliberately performs only the L1A causal isolation experiment:

* the two immutable B-FE2.2C XOR waveforms are the only source-domain input;
* ``safe_d`` is an ideal, zero-delay source-domain threshold/restoration;
* thirty real ``LATQ_X0P5M_A9TR40`` cells are powered from a constant
  ``PD_SAFE=0.95 V`` rail;
* the common safe-domain G edge is fixed at the B-FE2-L0 close time.

The generated decks and all solver products live below the task-scoped
``runs/.../l1a`` directory.  No historical B-FE2 or B-FE2-L0 product is
overwritten.  This is an equivalent causal isolation, not an AMS co-sim:
the source-domain waveform is replayed as PWL voltage sources while the
capture cell itself is simulated with the vendor transistor-level model.
"""

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple


FTC_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FTC_ROOT / "scripts"))
import bfe1_frontend  # noqa: E402  # Frozen .tr0 parser and source labels.


ANALYSIS_ROOT = FTC_ROOT / "analysis" / "b_fe_frontend" / "bfe2_real_latch"
L1A_ROOT = ANALYSIS_ROOT / "l1a"
RUN_ROOT = FTC_ROOT / "runs" / "b_fe_frontend" / "bfe2_real_latch" / "l1a"
SOURCE_ROOT = FTC_ROOT / "runs" / "b_fe_frontend" / "bfe2_real_latch" / "real_snapshot" / "corrected_seed_534p525ps"
SOURCE_MANIFEST = ANALYSIS_ROOT / "real_snapshot" / "BFE2_2C_SCENARIO_MANIFEST.json"
CELLS_PATH = FTC_ROOT / "discovery" / "selected_cells.json"
CONFIG_PATH = FTC_ROOT / "ftc_config.json"
LATCH_AUDIT = ANALYSIS_ROOT / "BFE2_0_LATCH_CELL_AUDIT.json"
LATCH_CELL = "LATQ_X0P5M_A9TR40"
XOR_CELL = "XOR2_X0P5M_A9TL40"
SCENARIO_IDS = ("BFE2L-095-N", "BFE2L-095-L2")
FIXED_CLOSE_PS = 534.524618567
PD_SAFE_V = 0.95
TRAN_STEP_S = 1.0e-12
STOP_S = 7.0e-9
PWL_EPS_S = 1.0e-18


def sha256_file(path: Path) -> str:
    """Hash one evidence file without loading large waveform products at once."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> Dict[str, Any]:
    """Read an object-shaped JSON contract and reject accidental list inputs."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {}".format(path))
    return value


def spice(value: float) -> str:
    """Render a finite SI number in a locale-independent HSPICE form."""

    return "{:.12e}".format(float(value))


def source_trace_path(scenario_id: str) -> Path:
    """Return exactly the retained B-FE2.2C trace for one fixed scenario."""

    return SOURCE_ROOT / scenario_id.lower().replace("-", "_") / "bfe2c_corrected.tr0"


def source_deck_path(scenario_id: str) -> Path:
    """Return the immutable deck paired with a retained B-FE2.2C trace."""

    return source_trace_path(scenario_id).with_suffix(".sp")


def validate_inputs() -> List[Mapping[str, Any]]:
    """Freeze the L1A pair and reject close/topology/source drift before a run."""

    manifest = read_json(SOURCE_MANIFEST)
    entries = manifest.get("scenarios")
    if not isinstance(entries, list) or tuple(item.get("scenario_id") for item in entries) != SCENARIO_IDS:
        raise ValueError("L1A requires exactly the B-FE2.2C normal/L2 pair")
    if abs(float(manifest["requested_close_ps"]) - FIXED_CLOSE_PS) > 1.0e-6:
        raise ValueError("L1A close differs from the frozen B-FE2-L0 close")
    if manifest.get("total_bfe2_2_new_hspice_scenarios") != 8:
        raise ValueError("L1A source accounting is not the frozen eight-scenario B-FE2.2 total")
    for entry in entries:
        scenario_id = entry["scenario_id"]
        trace = source_trace_path(scenario_id)
        deck = source_deck_path(scenario_id)
        if not trace.is_file() or not deck.is_file():
            raise FileNotFoundError("missing immutable B-FE2.2C source for {}".format(scenario_id))
        if sha256_file(trace) != entry["tr0_sha256"] or sha256_file(deck) != entry["deck_sha256"]:
            raise ValueError("B-FE2.2C source SHA mismatch for {}".format(scenario_id))
        if float(entry["baseline_v"]) != 0.95:
            raise ValueError("L1A baseline must remain 0.95 V")
        if scenario_id.endswith("-L2") and float(entry["droop_v"]) != 0.86:
            raise ValueError("L1A L2 droop must remain 0.86 V")
    cells = read_json(CELLS_PATH)
    # L1A does not instantiate XOR cells.  The source XOR identity therefore
    # comes from the immutable B-FE2.2C electrical signature, not from a
    # possibly broader discovery summary whose role mapping may differ.
    if cells["latch"]["cell"] != LATCH_CELL:
        raise ValueError("selected real latch identity changed")
    if any(item.get("electrical_signature", {}).get("xor_cell") != XOR_CELL for item in entries):
        raise ValueError("frozen B-FE2.2C XOR identity changed")
    audit = read_json(LATCH_AUDIT)
    if audit["cell"] != LATCH_CELL or audit["cdl_ports"] != ["Q", "VDD", "VNW", "VPW", "VSS", "D", "G"]:
        raise ValueError("audited LATQ port contract changed")
    return entries


def source_columns(scenario_id: str) -> Tuple[Mapping[str, Any], List[float]]:
    """Load one source trace and return absolute time plus all named columns."""

    trace = bfe1_frontend.parse_ascii_tr0(source_trace_path(scenario_id))
    if trace["record_width"] != 124:
        raise ValueError("source trace width changed for {}".format(scenario_id))
    return trace["columns"], trace["columns"]["time"]


def interpolate_crossing(times: Sequence[float], values: Sequence[float], rail: Sequence[float]) -> List[Tuple[float, str]]:
    """Find source-domain VDD/2 crossings using the frozen linear rule.

    The return value contains absolute seconds and direction.  It is used only
    to place ideal PWL transitions at the same threshold event; no propagation
    delay or edge slew is inserted by this conversion.
    """

    delta = [value - 0.5 * supply for value, supply in zip(values, rail)]
    events: List[Tuple[float, str]] = []
    for index in range(1, len(delta)):
        left, right = delta[index - 1], delta[index]
        if left == 0.0:
            crossing = times[index - 1]
        elif left * right > 0.0 or right == left:
            continue
        else:
            crossing = times[index - 1] + (-left / (right - left)) * (times[index] - times[index - 1])
        direction = "rise" if right >= left else "fall"
        if not events or crossing - events[-1][0] > PWL_EPS_S:
            events.append((crossing, direction))
    return events


def binary_pwl(times: Sequence[float], values: Sequence[float], rail: Sequence[float], high: float) -> List[Tuple[float, float]]:
    """Create a zero-delay 0/full-swing PWL from source-domain threshold events."""

    if not times:
        raise ValueError("empty source waveform")
    events = interpolate_crossing(times, values, rail)
    points: List[Tuple[float, float]] = [(times[0], high if values[0] > 0.5 * rail[0] else 0.0)]
    current = points[0][1]
    for crossing, direction in events:
        next_value = high if direction == "rise" else 0.0
        if next_value != current:
            points.append((crossing, next_value))
            current = next_value
    points.append((times[-1], current))
    return points


def scalar_pwl(times: Sequence[float], values: Sequence[float]) -> List[Tuple[float, float]]:
    """Convert a retained waveform column into finite PWL points unchanged."""

    return list(zip(times, values))


def pwl_source(name: str, node: str, return_node: str, points: Iterable[Tuple[float, float]]) -> str:
    """Render one explicit voltage-source PWL with no hidden behavioral logic."""

    rendered = " ".join("{} {}".format(spice(time), spice(value)) for time, value in points)
    return "V_{} {} {} PWL({})".format(name.upper(), node, return_node, rendered)


def render_deck(scenario: Mapping[str, Any], hspice_model: str, cells: Mapping[str, Any]) -> str:
    """Render the L1A equivalent-causal-isolation transistor-level deck.

    Port comments are intentionally adjacent to every source and LATQ bank:
    ``Q VDD VNW VPW VSS D G`` follows the audited CDL positional contract.
    The real latches are the only nonlinear capture elements in this deck.
    """

    scenario_id = str(scenario["scenario_id"])
    columns, times = source_columns(scenario_id)
    sense = columns[bfe1_frontend.label_for("vdd_monitored")]
    lines = [
        "* B-FE2-L1A equivalent causal isolation; scenario={}.".format(scenario_id),
        "* Frozen source waveform + ideal threshold restoration + real LATQ at PD_SAFE.",
        "* This is not a complete AMS co-simulation or a physical level shifter.",
        ".option post=2 probe nomod measform=3 measdgt=10 runlvl=3",
        ".temp 2.500000000000e+01",
        '.include "{}"'.format(cells["source_files"]["rvt_cdl"]),
        '.include "{}"'.format(cells["source_files"]["lvt_cdl"]),
        '.include "{}"'.format(FTC_ROOT / "spice" / "empty_subckt.sp_cal"),
        '.lib "{}" tt'.format(hspice_model),
        ".param VDD_SAFE_VALUE=0.95",
        "V_VSS_SAFE vss_safe 0 DC=0",
        "V_VDD_SAFE vdd_safe vss_safe DC='VDD_SAFE_VALUE'",
    ]
    lines.append(pwl_source("vdd_sense", "vdd_sense", "vss_safe", scalar_pwl(times, sense)))
    for tap in range(30):
        xor = columns[bfe1_frontend.label_for("xor_{}".format(tap))]
        safe_points = binary_pwl(times, xor, sense, PD_SAFE_V)
        lines.append(pwl_source("xor_{:02d}".format(tap), "xor_{:02d}".format(tap), "vss_safe", scalar_pwl(times, xor)))
        lines.append(pwl_source("safe_d_{:02d}".format(tap), "safe_d_{:02d}".format(tap), "vss_safe", safe_points))
    close_s = bfe1_frontend.LAUNCH_S + FIXED_CLOSE_PS * 1.0e-12
    edge_s = 0.5e-12
    lines.append("* Safe-domain G: one fixed 1-ps falling edge centered at sample_close.")
    lines.append("V_LATCH_G latch_g vss_safe PWL(0 0 {} 'VDD_SAFE_VALUE' {} 'VDD_SAFE_VALUE' {} 0 {} 0)".format(
        spice(close_s - edge_s), spice(close_s - edge_s / 2.0), spice(close_s + edge_s / 2.0), spice(STOP_S)))
    lines.append("* LATQ port order: Q VDD VNW VPW VSS D G; all four supply/well ports are PD_SAFE.")
    for tap in range(30):
        lines.append("XLATCH_{:02d} q_{:02d} vdd_safe vdd_safe vss_safe vss_safe safe_d_{:02d} latch_g {}".format(
            tap, tap, tap, LATCH_CELL))
    probe_nodes = ["v(vdd_sense)", "v(vdd_safe)", "v(latch_g)"]
    probe_nodes += ["v(xor_{:02d})".format(tap) for tap in range(30)]
    probe_nodes += ["v(safe_d_{:02d})".format(tap) for tap in range(30)]
    probe_nodes += ["v(q_{:02d})".format(tap) for tap in range(30)]
    lines.extend([".probe tran {}".format(" ".join(probe_nodes)), ".tran {} {}".format(spice(TRAN_STEP_S), spice(STOP_S)), ".end", ""])
    return "\n".join(lines)


def validate_deck(deck: str) -> None:
    """Reject topology drift before HSPICE is invoked."""

    net = "\n".join(line.split("*", 1)[0] for line in deck.splitlines())
    if net.count("XLATCH_") != 30 or net.count(LATCH_CELL) != 30:
        raise ValueError("L1A requires exactly 30 real LATQ cells")
    if net.count("XOR2_") != 0:
        raise ValueError("L1A must replay XOR waveforms, not instantiate a second XOR bank")
    for forbidden in ("DFF", "VDD_MONITORED", "VDD_REF", "PD_CTRL", "hysteresis", "slew"):
        if forbidden.lower() in net.lower():
            raise ValueError("forbidden L1A topology token: {}".format(forbidden))
    if "V_VDD_SAFE vdd_safe vss_safe" not in net:
        raise ValueError("safe-domain supply wiring is malformed")
    if net.count("V_LATCH_G latch_g vss_safe PWL") != 1:
        raise ValueError("L1A requires exactly one fixed safe-domain G edge")
    if net.count("safe_d_") < 30 or net.count("q_") < 30:
        raise ValueError("L1A probe/source bank is incomplete")


def run_one(entry: Mapping[str, Any], hspice: Path, model: str, cells: Mapping[str, Any]) -> Dict[str, Any]:
    """Render and execute one electrically unique fixed L1A scenario."""

    scenario_id = str(entry["scenario_id"])
    directory = RUN_ROOT / scenario_id.lower().replace("-", "_")
    if directory.exists():
        # A prior tool-wrapper failure may leave only this stage's own deck or
        # log.  Reuse that isolated directory; a completed .tr0 is the only
        # artifact that makes a scenario immutable and therefore non-reusable.
        if (directory / "bfe2_l1a.tr0").is_file():
            # Re-analysis/republication is allowed only from the completed
            # same-stage product.  It performs no new physical simulation.
            deck_path = directory / "bfe2_l1a.sp"
            trace = directory / "bfe2_l1a.tr0"
            parsed = bfe1_frontend.parse_ascii_tr0(trace)
            if not deck_path.is_file() or parsed["record_width"] != 94:
                raise ValueError("completed L1A product is incomplete: {}".format(directory))
            run_dc_sweep = __import__("run_dc_sweep")
            return {
                "scenario_id": scenario_id,
                "baseline_v": entry["baseline_v"],
                "droop_v": entry["droop_v"],
                "requested_close_ps": FIXED_CLOSE_PS,
                "verification_mode": "equivalent causal isolation",
                "deck_sha256": sha256_file(deck_path),
                "tr0_sha256": sha256_file(trace),
                "source_tr0_sha256": sha256_file(source_trace_path(scenario_id)),
                "source_deck_sha256": sha256_file(source_deck_path(scenario_id)),
                "record_width": parsed["record_width"],
                "record_count": parsed["record_count"],
                "hspice_version": run_dc_sweep.hspice_version(hspice),
                "run_disposition": "reused",
            }
    else:
        directory.mkdir(parents=True)
    # The vendor LVT CDL resolves this compatibility include relative to the
    # simulator working directory.  Keep the copy task-local and never alter
    # the vendor library tree.
    shutil.copyfile(FTC_ROOT / "spice" / "empty_subckt.sp_cal", directory / "empty_subckt.sp_cal")
    deck = render_deck(entry, model, cells)
    validate_deck(deck)
    deck_path = directory / "bfe2_l1a.sp"
    deck_path.write_text(deck, encoding="ascii")
    command = [str(hspice), deck_path.name, "-o", "bfe2_l1a"]
    # The project HSPICE environment still exposes Python 3.6; use the
    # backward-compatible spelling instead of Python-3.7-only ``text``.
    result = subprocess.run(command, cwd=directory, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, check=False, timeout=900)
    (directory / "hspice_command.log").write_text("command={}\nreturncode={}\nstdout:\n{}\nstderr:\n{}\n".format(" ".join(command), result.returncode, result.stdout, result.stderr), encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError("L1A HSPICE failed for {}".format(scenario_id))
    listing = directory / "bfe2_l1a.lis"
    run_dc_sweep = __import__("run_dc_sweep")
    run_dc_sweep.validate_listing(listing)
    trace = directory / "bfe2_l1a.tr0"
    parsed = bfe1_frontend.parse_ascii_tr0(trace)
    if parsed["record_width"] != 94:
        raise ValueError("L1A probe contract changed: {}".format(parsed["record_width"]))
    return {
        "scenario_id": scenario_id,
        "baseline_v": entry["baseline_v"],
        "droop_v": entry["droop_v"],
        "requested_close_ps": FIXED_CLOSE_PS,
        "verification_mode": "equivalent causal isolation",
        "deck_sha256": sha256_file(deck_path),
        "tr0_sha256": sha256_file(trace),
        "source_tr0_sha256": sha256_file(source_trace_path(scenario_id)),
        "source_deck_sha256": sha256_file(source_deck_path(scenario_id)),
        "record_width": parsed["record_width"],
        "record_count": parsed["record_count"],
        "hspice_version": run_dc_sweep.hspice_version(hspice),
        "run_disposition": "new",
    }


def main() -> int:
    """Run exactly the two authorized L1A physical scenarios and stop."""

    entries = validate_inputs()
    config = read_json(CONFIG_PATH)
    cells = read_json(CELLS_PATH)
    hspice = Path(config["hspice"])
    model = config["model_library"]
    if config["expected_hspice_version"] not in __import__("run_dc_sweep").hspice_version(hspice):
        raise RuntimeError("unexpected HSPICE version")
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    results = [run_one(entry, hspice, model, cells) for entry in entries]
    L1A_ROOT.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "stage": "B-FE2-L1A",
        "verification_mode": "equivalent causal isolation",
        "gate_pending_analysis": True,
        "authorized_new_physical_scenarios": 2,
        "new_hspice_scenarios": len(results),
        "scenario_ids": list(SCENARIO_IDS),
        "fixed_sample_close_ps": FIXED_CLOSE_PS,
        "fixed_pd_safe_v": PD_SAFE_V,
        "restoration_rule": "xor > 0.5*VDD_SENSE ? 0.95 V : 0 V",
        "restoration_delay_slew_hysteresis_x_region": "none",
        "pwl_generation_contract": {
            "source": "immutable B-FE2.2C XOR/VDD_SENSE waveform",
            "threshold": "xor > 0.5*VDD_SENSE",
            "safe_d_low_v": 0.0,
            "safe_d_high_v": PD_SAFE_V,
            "additional_delay_ps": 0.0,
            "additional_slew_ps": 0.0,
            "hysteresis": "none",
            "x_region": "none",
        },
        "latch_cell": LATCH_CELL,
        "latch_cdl_sha256": read_json(LATCH_AUDIT)["cdl"]["sha256"],
        "latch_verilog_sha256": read_json(LATCH_AUDIT)["verilog"]["sha256"],
        "latch_liberty_sha256": read_json(LATCH_AUDIT)["liberty"]["sha256"],
        "model_sha256": sha256_file(Path(model)),
        "source_manifest_sha256": sha256_file(SOURCE_MANIFEST),
        "latch_audit_sha256": sha256_file(LATCH_AUDIT),
        "model_path": model,
        "results": results,
    }
    (L1A_ROOT / "BFE2_L1A_SCENARIO_MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("BFE2_L1A_PHYSICAL_PAIR_COMPLETE new=2")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
