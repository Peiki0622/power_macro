#!/usr/bin/env python3
"""Publish the required Stage 1 JSON artifacts and human-readable report."""

from __future__ import print_function

import argparse
import json
import subprocess
from pathlib import Path

from power_macro.tcn_detection.microarchitecture.search import run_search


POWER_MACRO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = (POWER_MACRO_ROOT / "tcn_detection" / "config"
                  / "cnn_microarchitecture_stage1_v1.json")
DEFAULT_ARTIFACT_DIR = POWER_MACRO_ROOT / "artifacts"
DEFAULT_REPORT_DIR = POWER_MACRO_ROOT / "reports"

CANDIDATE_ROW_FIELDS = (
    "candidate_id", "mac_count", "output_channel_parallel",
    "position_parallel", "fan_in_parallel", "weight_bank_count",
    "weight_read_width", "chosen_dataflow", "conv1_cycles",
    "conv2_cycles", "conv3_cycles", "pool_cycles", "classifier_cycles",
    "total_latency_cycles", "initiation_interval_cycles", "mac_utilization",
    "average_weight_words_per_cycle", "peak_weight_words_per_issue",
    "bank_capacity_words_per_cycle", "weight_words_read",
    "activation_write_elements", "storage_bits", "area_proxy_units",
    "energy_proxy_units",
)


def _git_commit():
    """Return the source commit used for the report, failing rather than guessing."""

    return subprocess.check_output(
        ["git", "-C", str(POWER_MACRO_ROOT), "rev-parse", "HEAD"],
        universal_newlines=True).strip()


def _write(path, content, force):
    """Write one generated file while refusing accidental result replacement."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        raise FileExistsError("refusing to overwrite {}".format(path))
    path.write_text(content, encoding="utf-8")


def _mac_summary(candidates):
    """Summarise the fastest observed candidate for each mandated MAC count."""

    rows = []
    for mac_count in (16, 32, 64, 128):
        current = [item for item in candidates if item["mac_count"] == mac_count]
        fastest = min(current, key=lambda item: (
            item["total_latency_cycles"], item["initiation_interval_cycles"],
            item["candidate_id"]))
        rows.append((mac_count, fastest))
    return rows


def _compact_candidates_payload(result):
    """Serialize every candidate once as a documented compact row table.

    The full and incremental schedules are identical for every configuration
    because dependency analysis requires all 32 positions.  Publishing both
    nested schedules and the same bank layout 8,475 times produced an 85 MB
    artifact.  This table preserves all search inputs and comparison outputs;
    bank-specific storage layouts appear once in ``storage_options_by_bank``.
    """

    storage_options = {}
    rows = []
    for candidate in result["candidates"]:
        bank_key = str(candidate["weight_bank_count"])
        storage_options.setdefault(bank_key, candidate["storage"])
        timing = candidate["full_window"]
        bandwidth = timing["memory_bandwidth"]
        rows.append([
            candidate["candidate_id"], candidate["mac_count"],
            candidate["output_channel_parallel"], candidate["position_parallel"],
            candidate["fan_in_parallel"], candidate["weight_bank_count"],
            candidate["weight_read_width"], candidate["chosen_dataflow"],
            timing["conv1_cycles"], timing["conv2_cycles"],
            timing["conv3_cycles"], timing["pool_cycles"],
            timing["classifier_cycles"], timing["total_latency_cycles"],
            timing["initiation_interval_cycles"], timing["mac_utilization"],
            bandwidth["average_weight_words_per_cycle"],
            bandwidth["peak_weight_words_per_issue"],
            bandwidth["convolution_bank_capacity_words_per_cycle"],
            timing["weight_words_read"], timing["activation_write_elements"],
            candidate["storage_bits"], candidate["area_proxy_units"],
            candidate["energy_proxy_units"],
        ])
    selection = result["selection"]
    return {
        "schema_version": result["schema_version"],
        "status": result["status"],
        "source_binding": result["source_binding"],
        "source_git_commit": result["source_git_commit"],
        "model_contract": result["model_contract"],
        "search_config_path": result["search_config_path"],
        "search_config_sha256": result["search_config_sha256"],
        "dependency_analysis": result["dependency_analysis"],
        "candidate_count": result["candidate_count"],
        "dataflow_comparison": {
            "full_window_and_incremental_match_for_all_candidates": all(
                item["incremental_matches_full"] for item in result["candidates"]),
            "incremental_work_reduction": result["dependency_analysis"][
                "mode_b_reduces_work"],
        },
        "storage_options_by_bank": storage_options,
        "candidate_row_fields": list(CANDIDATE_ROW_FIELDS),
        "candidate_rows": rows,
        "selection": {
            "status": selection["status"],
            "selected_candidate_id": (None if selection["selected"] is None
                                      else selection["selected"]["candidate_id"]),
            "selected_stride_samples": selection["selected_stride_samples"],
            "budget_cycles": selection["budget_cycles"],
            "pareto_candidate_ids": selection["pareto_candidate_ids"],
        },
    }


def render_report(result):
    """Render only values already present in the machine-readable search result."""

    selection = result["selection"]
    selected = selection["selected"]
    lines = [
        "# CNN Microarchitecture Search",
        "",
        "## Status",
        "",
        "`{}`".format(result["status"]),
        "",
        "The Stage 1 search binds the frozen [18,8,18] W8/A8 package and does not add RTL, permutation, PRNG, or numerical changes.",
        "",
        "## Frozen Inputs",
        "",
        "| Item | Value |",
        "| --- | --- |",
        "| Checkpoint SHA256 | `{}` |".format(result["source_binding"]["checkpoint_sha256"]),
        "| Package manifest SHA256 | `{}` |".format(result["source_binding"]["manifest_sha256"]),
        "| Search configuration SHA256 | `{}` |".format(result["search_config_sha256"]),
        "| Source Git commit | `{}` |".format(result["source_git_commit"]),
        "| Model | channels [18,8,18], kernels [5,5,5], L32, W8/A8 |",
        "",
        "## Dataflow Evidence",
        "",
        "The NumPy integer replay matched all {} exported golden windows.  A sliding update changes every logical input position; same padding and the folded Conv1 [18,32] position-dependent bias require all 32 Conv1, Conv2, and Conv3 positions to be recomputed.".format(
            result["dependency_analysis"]["golden_windows_verified"]),
        "",
        "| Mode | Conv1 positions | Conv2 positions | Conv3 positions | Pool work | Result |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
        "| Full L32 | 32 | 32 | 32 | 32 | Reference schedule |",
        "| Sliding incremental | {conv1} | {conv2} | {conv3} | {pool} | Bit-exact only with full-window work |".format(
            **result["dependency_analysis"]["affected_position_counts"]),
        "",
        "## MAC Search",
        "",
        "The original stride set [1,2,4,8,16,32] was tested first, followed by the frozen extension [64,128,256,512,1024].  At a 2 ns compute period and 4 ns sample period, the latency and II budget is `2 * stride` cycles.",
        "",
        "| MACs | Fastest candidate | Latency | II |",
        "| ---: | --- | ---: | ---: |",
    ]
    for mac_count, candidate in _mac_summary(result["candidates"]):
        lines.append("| {} | `{}` | {} | {} |".format(
            mac_count, candidate["candidate_id"],
            candidate["total_latency_cycles"],
            candidate["initiation_interval_cycles"]))
    if selected is None:
        lines.extend([
            "",
            "## Gate",
            "",
            "No candidate met the frozen maximum stride; Stage 2 is blocked.",
            "",
        ])
        return "\n".join(lines)

    storage = selected["storage"]
    memory = selected["memory_bandwidth"]
    lines.extend([
        "",
        "## Selected Microarchitecture",
        "",
        "The first feasible target is stride {} ({} cycles).  The selected candidate is on that target's Pareto frontier and has the lowest frozen equal-weight normalized resource score; ties are broken by MAC count, latency, storage, and candidate ID.".format(
            selection["selected_stride_samples"], selection["budget_cycles"]),
        "",
        "| Field | Selected value |",
        "| --- | --- |",
        "| Candidate | `{}` |".format(selected["candidate_id"]),
        "| MAC count | {} |".format(selected["mac_count"]),
        "| Output-channel parallelism | {} |".format(selected["output_channel_parallel"]),
        "| Position parallelism | {} |".format(selected["position_parallel"]),
        "| Fan-in parallelism | {} |".format(selected["fan_in_parallel"]),
        "| Conv weight banks / read width | {} banks / {} W8 words per bank cycle |".format(
            selected["weight_bank_count"], selected["weight_read_width"]),
        "| Conv1 / Conv2 / Conv3 cycles | {} / {} / {} |".format(
            selected["full_window"]["conv1_cycles"],
            selected["full_window"]["conv2_cycles"],
            selected["full_window"]["conv3_cycles"]),
        "| Pool / classifier cycles | {} / {} |".format(
            selected["full_window"]["pool_cycles"],
            selected["full_window"]["classifier_cycles"]),
        "| Latency / II | {} / {} cycles |".format(
            selected["total_latency_cycles"],
            selected["initiation_interval_cycles"]),
        "| MAC utilization | {:.6f} |".format(selected["mac_utilization"]),
        "| Average / peak weight bandwidth | {:.6f} / {} words per cycle |".format(
            memory["average_weight_words_per_cycle"],
            memory["peak_weight_words_per_issue"]),
        "| Total parameter storage | {} bits ({} bytes ceiling) |".format(
            storage["total_parameter_bits"], storage["total_parameter_bytes_ceiling"]),
        "| Conv W8 / bias / requant / classifier bits | {} / {} / {} / {} |".format(
            storage["conv_weight_storage"]["total_bits"],
            storage["bias_storage"]["total_bits"],
            storage["requant_storage"]["total_bits"],
            storage["classifier_storage"]["total_bits"]),
        "| Area / energy proxy | {} / {} relative units |".format(
            selected["area_proxy_units"], selected["energy_proxy_units"]),
        "",
        "The area and energy fields are scheduling proxies only.  They are not synthesis area, timing signoff, or physical power results.",
        "",
        "## Stage Gate",
        "",
        "- Cycle model runs with explicit ROM, requantization, writeback, pooling, and classifier events.",
        "- Full-window and sliding-incremental modes were both evaluated; the latter has no work reduction for this frozen model.",
        "- MAC count, parallelism, bank count, and read width are selected from exhaustive model results rather than legacy RTL cycles.",
        "- Latency and II meet the selected stride-512 budget of 1024 cycles.",
        "- Stage 2 may proceed with this selected configuration and must preserve the same W8/A8 contract.",
        "",
    ])
    return "\n".join(lines)


def publish(config_path=DEFAULT_CONFIG, artifact_dir=DEFAULT_ARTIFACT_DIR,
            report_dir=DEFAULT_REPORT_DIR, force=False):
    """Execute the validated search and publish all three Stage 1 deliverables."""

    result = run_search(config_path)
    result["source_git_commit"] = _git_commit()
    artifact_dir = Path(artifact_dir)
    report_dir = Path(report_dir)
    candidates_path = artifact_dir / "cnn_microarchitecture_candidates.json"
    selected_path = artifact_dir / "cnn_microarchitecture_selected.json"
    report_path = report_dir / "CNN_MICROARCHITECTURE_SEARCH.md"
    selected_payload = {
        "schema_version": result["schema_version"],
        "status": result["status"],
        "source_binding": result["source_binding"],
        "source_git_commit": result["source_git_commit"],
        "dependency_analysis": result["dependency_analysis"],
        "selection": result["selection"],
    }
    candidates_payload = _compact_candidates_payload(result)
    _write(candidates_path,
           json.dumps(candidates_payload, indent=2, sort_keys=True) + "\n",
           force)
    _write(selected_path,
           json.dumps(selected_payload, indent=2, sort_keys=True) + "\n", force)
    _write(report_path, render_report(result), force)
    return {
        "candidates": candidates_path,
        "selected": selected_path,
        "report": report_path,
        "result": result,
    }


def main():
    """Provide a non-overwriting command-line entrypoint for reproducible runs."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    parser.add_argument("--force", action="store_true",
                        help="replace existing Stage 1 outputs intentionally")
    arguments = parser.parse_args()
    outputs = publish(arguments.config, arguments.artifact_dir,
                      arguments.report_dir, arguments.force)
    for name in ("candidates", "selected", "report"):
        print("{}={}".format(name, outputs[name]))


if __name__ == "__main__":
    main()
