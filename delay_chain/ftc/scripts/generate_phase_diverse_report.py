#!/usr/bin/env python3
"""Render the FTC phase-diverse result report from committed compact evidence.

This script has no simulator dependency and never changes raw HSPICE evidence.
It exists so every figure in the NO-GO report can be regenerated from the CSV
and JSON contracts created by the reviewed characterization and analysis tools.
"""

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


FTC_ROOT = Path(__file__).resolve().parents[1]
SCREEN = FTC_ROOT / "runs/phase_diverse_screen"
STATIC = FTC_ROOT / "runs/phase_diverse_static"
GLITCH = FTC_ROOT / "runs/phase_diverse_glitch"
FIGURES = FTC_ROOT / "analysis/phase_diverse/figures"
REPORT = FTC_ROOT / "reports/FTC_PHASE_DIVERSE_SAMPLING_RESULT.md"


def rows(path: Path) -> List[Dict[str, str]]:
    """Read a required compact table and reject a report made from no evidence."""

    with path.open(newline="", encoding="utf-8") as stream:
        result = list(csv.DictReader(stream))
    if not result:
        raise ValueError("report input is empty: {}".format(path))
    return result


def data(path: Path) -> Dict[str, Any]:
    """Load a required result object while preserving the published values exactly."""

    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("report input is not an object: {}".format(path))
    return value


def save(figure: plt.Figure, name: str) -> None:
    """Save a publication figure only under the task-owned analysis directory."""

    FIGURES.mkdir(parents=True, exist_ok=True)
    figure.tight_layout()
    figure.savefig(FIGURES / name, dpi=180)
    plt.close(figure)


def phase_order(table: Sequence[Mapping[str, str]]) -> List[str]:
    """Return phase IDs in physical capture-time order rather than lexical order."""

    timing = {}
    for row in table:
        timing[row["phase_id"]] = float(row["capture_phase_s"])
    return [item[0] for item in sorted(timing.items(), key=lambda item: item[1])]


def plot_candidate_static(coarse: Sequence[Mapping[str, str]]) -> None:
    """Draw Fig. 1 without interpolating the measured encoded start indices."""

    phases = phase_order(coarse)
    figure, axis = plt.subplots(figsize=(7.1, 3.6))
    for phase in phases:
        group = sorted((row for row in coarse if row["phase_id"] == phase), key=lambda row: float(row["vdd_v"]), reverse=True)
        axis.plot([float(row["vdd_v"]) for row in group], [int(row["start_index"]) for row in group], marker="o", linewidth=1.2, label=phase)
    axis.set_xlabel("VDD (V)")
    axis.set_ylabel("encoded start index")
    axis.set_title("Fig. 1  Candidate phase static encoded-state map")
    axis.grid(True, linewidth=0.4)
    axis.legend(ncol=3, fontsize=7)
    save(figure, "fig1_candidate_static_map.png")


def plot_detection_heatmap(scored: Sequence[Mapping[str, str]], phases: Sequence[str]) -> None:
    """Draw Fig. 2 directly from binary jitter-aware detection bins, with no smoothing."""

    onsets = sorted({float(row["glitch_onset_rel_s"]) for row in scored})
    matrix = []
    for phase in phases:
        by_onset = {float(row["glitch_onset_rel_s"]): int(row["jitter_aware_detected"]) for row in scored if row["phase_id"] == phase}
        matrix.append([by_onset[onset] for onset in onsets])
    figure, axis = plt.subplots(figsize=(7.1, 2.6))
    image = axis.imshow(matrix, aspect="auto", interpolation="nearest", cmap="RdYlGn", vmin=0, vmax=1)
    axis.set_yticks(range(len(phases)), phases)
    tick_positions = list(range(0, len(onsets), max(1, len(onsets) // 7)))
    axis.set_xticks(tick_positions, ["{:.0f}".format(onsets[index] * 1e12) for index in tick_positions])
    axis.set_xlabel("glitch onset relative to launch (ps)")
    axis.set_ylabel("capture phase")
    axis.set_title("Fig. 2  Jitter-aware detection heatmap, 200 mV / 200 ps")
    figure.colorbar(image, ax=axis, ticks=[0, 1], label="detected")
    save(figure, "fig2_glitch_phase_heatmap.png")


def plot_blind_intervals(map_summary: Mapping[str, Any], phases: Sequence[str]) -> None:
    """Draw Fig. 3 as explicit measured blind bars rather than fitted boundaries."""

    groups = {item["phase_id"]: item for item in map_summary["groups"]}
    figure, axis = plt.subplots(figsize=(7.1, 2.3))
    for index, phase in enumerate(phases):
        for interval in groups[phase]["blind_intervals"]:
            axis.broken_barh([(interval["start_s"] * 1e12, interval["duration_s"] * 1e12)], (index - 0.32, 0.64), facecolors="tab:red")
    axis.set_yticks(range(len(phases)), phases)
    axis.set_xlabel("glitch onset relative to launch (ps)")
    axis.set_ylabel("capture phase")
    axis.set_title("Fig. 3  Per-phase measured blind intervals")
    axis.grid(True, axis="x", linewidth=0.4)
    save(figure, "fig3_blind_intervals.png")


def best_by_count(ranking: Sequence[Mapping[str, Any]], count: int) -> Mapping[str, Any]:
    """Return the lexicographically ranked best result of the requested phase count."""

    matches = [item for item in ranking if int(item["phase_count"]) == count]
    if not matches:
        raise ValueError("phase-set ranking lacks {}-phase result".format(count))
    return matches[0]


def plot_common_blind(ranking: Sequence[Mapping[str, Any]]) -> None:
    """Draw Fig. 4 from true same-launch OR/common-blind calculations."""

    selected = [best_by_count(ranking, count) for count in (1, 2, 3)]
    figure, axis = plt.subplots(figsize=(6.2, 3.2))
    axis.bar(["1 phase", "2 phases", "3 phases"], [item["worst_longest_common_blind_s"] * 1e12 for item in selected], color=["#7f8c8d", "#c0392b", "#9b59b6"])
    axis.set_ylabel("longest common blind interval (ps)")
    axis.set_title("Fig. 4  Same-launch common blind interval")
    axis.grid(True, axis="y", linewidth=0.4)
    save(figure, "fig4_common_blind_comparison.png")


def plot_jitter_coverage(raw_ranking: Sequence[Mapping[str, Any]], jitter_ranking: Sequence[Mapping[str, Any]]) -> None:
    """Draw Fig. 5 using the same measured pair before and after jitter scoring."""

    raw_pair = best_by_count(raw_ranking, 2)
    jitter_pair = best_by_count(jitter_ranking, 2)
    figure, axis = plt.subplots(figsize=(6.2, 3.2))
    axis.bar(["raw virtual union", "jitter-aware union"], [raw_pair["worst_detection_fraction"], jitter_pair["worst_detection_fraction"]], color=["#2980b9", "#d35400"])
    axis.set_ylim(0.0, 1.0)
    axis.set_ylabel("worst-family detection fraction")
    axis.set_title("Fig. 5  Jitter-aware coverage comparison")
    axis.grid(True, axis="y", linewidth=0.4)
    save(figure, "fig5_jitter_aware_coverage.png")


def plot_static_shortlist(coarse: Sequence[Mapping[str, str]], phases: Sequence[str]) -> None:
    """Draw Fig. 6 from final candidate data and label the N-branch limitation."""

    figure, axis = plt.subplots(figsize=(7.1, 3.6))
    for phase in phases:
        group = sorted((row for row in coarse if row["phase_id"] == phase), key=lambda row: float(row["vdd_v"]), reverse=True)
        axis.step([float(row["vdd_v"]) for row in group], [int(row["end_index"]) for row in group], where="mid", label=phase)
    axis.set_xlabel("VDD (V)")
    axis.set_ylabel("encoded end index")
    axis.set_title("Fig. 6  Qualified candidate static transfer (NO-GO, no packaged phase set)")
    axis.grid(True, linewidth=0.4)
    axis.legend(ncol=3, fontsize=7)
    save(figure, "fig6_candidate_static_transfer.png")


def plot_baseline_vs_union(raw: Sequence[Mapping[str, str]]) -> None:
    """Draw Fig. 7 contrasting the 300 ps baseline and virtual best-pair map."""

    onsets = sorted({float(row["glitch_onset_rel_s"]) for row in raw})
    baseline = {float(row["glitch_onset_rel_s"]): int(row["encoded_state_changed"]) for row in raw if row["phase_id"] == "phi_p00"}
    pair = {}
    for onset in onsets:
        pair[onset] = max(int(row["encoded_state_changed"]) for row in raw if float(row["glitch_onset_rel_s"]) == onset and row["phase_id"] in {"phi_m04", "phi_p04"})
    figure, axis = plt.subplots(figsize=(7.1, 2.8))
    axis.step([value * 1e12 for value in onsets], [baseline[value] for value in onsets], where="post", label="300 ps baseline", linewidth=1.4)
    axis.step([value * 1e12 for value in onsets], [pair[value] for value in onsets], where="post", label="virtual phi_m04 + phi_p04", linewidth=1.4)
    axis.set_ylim(-0.1, 1.1)
    axis.set_xlabel("glitch onset relative to launch (ps)")
    axis.set_ylabel("encoded state changed")
    axis.set_title("Fig. 7  Baseline versus virtual phase-diverse transient map")
    axis.grid(True, linewidth=0.4)
    axis.legend(fontsize=8)
    save(figure, "fig7_baseline_vs_virtual_pair.png")


def table(lines: List[str], headings: Sequence[str], body: Sequence[Sequence[str]]) -> None:
    """Append one compact Markdown table with no hidden formatting assumptions."""

    lines.append("| " + " | ".join(headings) + " |")
    lines.append("| " + " | ".join("---" for _ in headings) + " |")
    for row in body:
        # JSON evidence intentionally retains numeric types; Markdown needs a
        # textual representation but must not round or otherwise reinterpret
        # those physical values while rendering the report.
        lines.append("| " + " | ".join(str(value) for value in row) + " |")


def main() -> int:
    """Generate all report figures and the A--O NO-GO evidence document."""

    coarse = rows(SCREEN / "phase_candidate_coarse.csv")
    raw_map = rows(GLITCH / "glitch_phase_map.csv")
    jitter_map = rows(GLITCH / "glitch_phase_map_jitter_aware.csv")
    candidate_summary = data(SCREEN / "phase_candidate_summary.json")
    baselines = data(STATIC / "phase_baselines.json")
    raw_summary = data(GLITCH / "glitch_phase_map_summary.json")
    raw_selection = data(GLITCH / "phase_set_selection.json")
    jitter_summary = data(GLITCH / "phase_jitter_summary.json")
    jitter_selection = data(GLITCH / "phase_set_selection_jitter_aware.json")
    sequential = data(GLITCH / "sequential_schedule_summary.json")
    shortlisted = ["phi_m04", "phi_m02", "phi_p00", "phi_p02", "phi_p04"]
    selected_pair = ["phi_m04", "phi_p04"]

    plot_candidate_static(coarse)
    plot_detection_heatmap(jitter_map, selected_pair)
    plot_blind_intervals(raw_summary, selected_pair)
    plot_common_blind(raw_selection["ranking"])
    plot_jitter_coverage(raw_selection["ranking"], jitter_selection["ranking"])
    plot_static_shortlist(coarse, shortlisted)
    plot_baseline_vs_union(raw_map)

    raw_one = best_by_count(raw_selection["ranking"], 1)
    raw_two = best_by_count(raw_selection["ranking"], 2)
    raw_three = best_by_count(raw_selection["ranking"], 3)
    jitter_two = best_by_count(jitter_selection["ranking"], 2)
    schedule = sequential["results"][0]
    # This generator renders only the completed historical study.  Its 0.75 V
    # records are preserved evidence, not replacements for the current 0.80 V
    # lower endpoint; the published current-range report is re-issued by the
    # data-only range re-publication tool instead of by this historical flow.
    lines = ["# FTC Phase-Diverse Sampling Result", "", "## Historical-Evidence Boundary", "", "This report generator renders a completed 1.10/0.90/0.75 V study. It contains no physical 0.80 V phase measurement and therefore cannot establish 0.80--1.10 V coverage; its NO-GO result is retained only as bounded historical evidence.", "", "## A. Motivation From The NO-GO Result", "", "The completed single-snapshot study measured acute voltage/phase angles of 5.04 deg (1.10 V), 15.42 deg (0.90 V), and 26.57 deg (0.75 V); its 15.42 deg median was below the 30 deg screening gate. The historical C/W projection remains closed.", "", "## B. Phase-Diversity Hypothesis", "", "This study did not attempt another algebraic phase-rejection transform. It held the shared RVT/LVT/XOR physical front-end fixed and tested whether deliberately separated capture phases have complementary physical transient apertures.", "", "## C. Candidate Phase Qualification", "", "Nine phases from 245.126260 ps to 354.873740 ps were physically measured. All nine were valid at the historical 1.10/0.90/0.75 V anchors and all eight historical coarse points; five evenly distributed phases were used for bounded transient screening.", ""]
    lines.append("Table 1. Candidate phases and static qualification.")
    table(lines, ["Phase", "Anchor valid", "Coarse valid", "States", "Largest jump", "Boundary points"], [[item["phase_id"], item["anchor_valid"], item["coarse_valid"], str(item["distinct_start_end_states"]), str(item["largest_adjacent_encoded_jump"]), str(item["boundary_points"])] for item in candidate_summary["candidates"]])
    lines.extend(["", "![Fig. 1](../analysis/phase_diverse/figures/fig1_candidate_static_map.png)", "", "## D. Phase-Specific Nominal States", ""])
    table(lines, ["Phase", "Capture phase (ps)", "Captured word", "Start", "End", "Length"], [[item["phase_id"], "{:.6f}".format(item["capture_phase_s"] * 1e12), "`{}`".format(item["captured_xor_word"]), str(item["nominal_start"]), str(item["nominal_end"]), str(item["nominal_length"])] for item in baselines["phases"]])
    lines.extend(["", "## E. Glitch Phase Map", "", "The physical map uses a 200 mV, 200 ps droop and 13.718435 ps coarse onset bins. No inferred C/W geometry was used.", "", "![Fig. 2](../analysis/phase_diverse/figures/fig2_glitch_phase_heatmap.png)", "", "## F. Blind-Window Complementarity", "", "The post-capture blind interval is shared by all tested phases. The raw best pair `phi_m04 + phi_p04` retains a 438.990 ps longest common blind interval, equal to the best individual phase; this is the decisive absence of useful physical complementarity.", "", "![Fig. 3](../analysis/phase_diverse/figures/fig3_blind_intervals.png)", "", "![Fig. 4](../analysis/phase_diverse/figures/fig4_common_blind_comparison.png)", "", "## G. Phase-Set Selection", ""])
    table(lines, ["Set size", "Best phase set", "Longest common blind (ps)", "Worst detection"], [["1", "+".join(raw_one["phase_ids"]), "{:.3f}".format(raw_one["worst_longest_common_blind_s"] * 1e12), "{:.4f}".format(raw_one["worst_detection_fraction"])], ["2", "+".join(raw_two["phase_ids"]), "{:.3f}".format(raw_two["worst_longest_common_blind_s"] * 1e12), "{:.4f}".format(raw_two["worst_detection_fraction"])], ["3", "+".join(raw_three["phase_ids"]), "{:.3f}".format(raw_three["worst_longest_common_blind_s"] * 1e12), "{:.4f}".format(raw_three["worst_detection_fraction"])]])
    lines.extend(["", "Table 2. All measured two-phase virtual same-launch combinations.", ""])
    table(lines, ["Phase pair", "Longest common blind (ps)", "Worst detection"], [["+".join(item["phase_ids"]), "{:.3f}".format(item["worst_longest_common_blind_s"] * 1e12), "{:.4f}".format(item["worst_detection_fraction"])] for item in raw_selection["ranking"] if int(item["phase_count"]) == 2])
    lines.extend(["", "A third phase gives no reduction in the measured longest common blind interval; no four-phase or LFSR expansion was attempted.", "", "## H. Jitter-Aware Result", "", "At 1.10 V, both `phi_m04` and `phi_p04` have a measured maximum no-glitch boundary movement of two taps. After applying those envelopes, their pair retains a 452.708 ps common blind interval, again identical to its best individual member.", "", "![Fig. 5](../analysis/phase_diverse/figures/fig5_jitter_aware_coverage.png)", "", "## I. Sequential Versus Parallel", "", "`A,B,A,B...` is reported separately. For the 200 ps one-shot map, unknown-parity sequential coverage is {:.4f}, worst-phase coverage is {:.4f}, and it does not use same-launch OR. Persistent two-cycle coverage was not measured because the stimulus is shorter than the 6 ns sampling period.".format(schedule["single_event_detection_fraction_unknown_parity"], schedule["single_event_worst_phase_detection_fraction"]), "", "## J. Physical Phase Generation", "", "Not implemented: the ideal-phase data failed the complementarity decision gate, so a real-cell phase generator would add unvalidated cost and would violate the minimum-hardware rule.", "", "## K. Static Sensing Preservation", "", "All candidates preserved valid static sensing at the historical 1.10/0.90/0.75 V anchors. This result is not a 0.80--1.10 V coverage claim because 0.80 V phase evidence was not measured.", "", "![Fig. 6](../analysis/phase_diverse/figures/fig6_candidate_static_transfer.png)", "", "## L. Final Transient Coverage", "", "No packaged phase-diverse hardware exists. Fig. 7 compares the 300 ps baseline with the virtual best pair solely to show why final hardware characterization was not authorized. The full-cycle sequential report also gives a 5.253 ns unobserved-interval lower bound.", "", "![Fig. 7](../analysis/phase_diverse/figures/fig7_baseline_vs_virtual_pair.png)", "", "## M. Hardware Cost", ""])
    lines.append("Table 3. Selected architecture hardware cost.")
    table(lines, ["Item", "Baseline", "Phase-diverse packaged addition"], [["RVT delay buffers", "34", "0 (NO-GO)"], ["LVT delay buffers", "30", "0 (NO-GO)"], ["XOR cells", "30", "0 (NO-GO)"], ["Capture latches", "30", "0 (NO-GO)"], ["Capture FFs", "30", "0 (NO-GO)"], ["Phase-generator cells / baseline registers / fusion", "0", "0 (not implemented)"]])
    lines.extend(["", "No DC timing/area or PVT batch was run because the plan requires those only after an architecture and real-cell phase generator are selected.", "", "## N. Limitations", "", "The result covers TT/25 C, five bounded ideal capture phases, and one physically measured medium glitch family. It does not claim that phase diversity removes cadence blind windows; short glitches can still occur outside the aperture. A future direction must change cadence, use asynchronous/event-driven capture, or change the physical aperture rather than add more phases indefinitely.", "", "## O. Final Architectural Conclusion", "", "**NO-GO: phase diversity does not materially reduce measured blind windows.** The best raw two-phase virtual union has the same 438.990 ps longest common blind interval as the best single phase; after measured jitter tolerance, the best pair still has the same 452.708 ps longest common blind interval as its best individual member. Therefore no parallel capture RTL, phase generator, boot calibration hardware, final static sweep, PVT study, or synthesis cost claim is justified.", ""])
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
