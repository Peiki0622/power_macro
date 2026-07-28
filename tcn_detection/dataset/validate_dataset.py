#!/usr/bin/env python3
"""Perform the final, full-corpus acceptance audit for the TCN pilot data.

This validator deliberately reads every compact trace, every labelled copy,
and every L=8/16/32 window.  It is not a smoke test: its failure list is an
auditable statement that the immutable electrical facts, slack-derived labels,
causal windows, trace split, and HSPICE cleanup lifecycle still agree.
"""

from __future__ import print_function

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


HORIZON = 8
WARNING_SLACK_PS = 5.0
RAW_SUFFIXES = {".tr0", ".lis", ".mt0", ".pa0", ".st0", ".ic0", ".sp"}
RAW_NAMES = {"trace.mt0.csv"}
ONLINE_FEATURE_WIDTH = 5


def sha256_file(path):
    """Return a bounded-memory SHA256 for source and derived provenance checks."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_csv(path):
    """Read one small, fixed-length trace or one window index with UTF-8 CSV rules."""

    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def add_failure(report, message):
    """Accumulate errors so one full run reports all contract violations at once."""

    report["failures"].append(message)


def expected_feature(rows, index, baseline, stages):
    """Recompute one permitted online feature vector from a compact trace.

    The function is intentionally local to the validator.  Repeating the
    small formula independently of ``build_windows.py`` catches a future edit
    that accidentally adds measured VDD, configured PWL data, family metadata,
    or a future capture to the model input.
    """

    current = int(rows[index]["sensor_code"])
    previous = int(rows[index - 1]["sensor_code"]) if index else baseline
    return [(current - baseline) / float(stages - baseline),
            (current - previous) / float(stages),
            1.0 if current == stages else 0.0,
            float(rows[index]["bubble_count"]) / float(stages),
            1.0 if rows[index]["code_valid"].lower() == "true" else 0.0]


def validate_trace_layers(run_dir, label_dir, map_bounds, report):
    """Verify immutable compact evidence and its one-to-one derived label copy.

    A labelled row must reproduce every original compact CSV column byte-for-
    byte as parsed text.  Only the slack-derived columns may be appended.  The
    final eight captures have no complete future horizon and must therefore be
    explicitly blank and ineligible rather than silently classified Safe.
    """

    compact_paths = sorted((run_dir / "compact").glob("*.csv"))
    label_paths = sorted(label_dir.glob("*.csv"))
    compact_by_id = {path.stem: path for path in compact_paths}
    label_by_id = {path.stem: path for path in label_paths}
    report["compact_trace_count"] = len(compact_paths)
    report["label_trace_count"] = len(label_paths)
    if set(compact_by_id) != set(label_by_id):
        add_failure(report, "compact and label trace IDs differ")
    traces = {}
    label_tables = {}
    classes = Counter()
    class_bases = defaultdict(set)
    split_classes = defaultdict(Counter)
    low_vdd, high_vdd = map_bounds
    for trace_id in sorted(set(compact_by_id) & set(label_by_id)):
        compact_rows = read_csv(compact_by_id[trace_id])
        label_rows = read_csv(label_by_id[trace_id])
        traces[trace_id] = compact_rows
        # Keep the derived truth rows in memory once.  The full pilot is only
        # 48,000 rows, whereas re-opening a 500-row CSV for every window would
        # turn a full audit into over 100,000 redundant file parses.
        label_tables[trace_id] = label_rows
        if len(compact_rows) != 500 or len(label_rows) != 500:
            add_failure(report, "{} does not have 500 compact and label rows".format(trace_id))
            continue
        compact_columns = set(compact_rows[0])
        required_label_columns = {"mapped_slack_ps", "future_min_slack_ps", "time_to_violation_samples",
                                  "raw_label", "hysteresis_label", "label_eligible"}
        if not required_label_columns.issubset(label_rows[0]):
            add_failure(report, "{} is missing required label columns".format(trace_id))
            continue
        for index, (source, labelled) in enumerate(zip(compact_rows, label_rows)):
            # This is the read-only electrical-fact contract: derived labels
            # cannot mutate a capture, an ID, a split assignment, or VDD.
            if any(labelled.get(column) != source[column] for column in compact_columns):
                add_failure(report, "{} label row {} changed compact evidence".format(trace_id, index))
                break
            if source["sample_done"].lower() != "true" or not source["raw_code"]:
                add_failure(report, "{} compact row {} is not a complete DFF capture".format(trace_id, index))
                break
            measured = float(source["measured_vdd_a_v"])
            if not low_vdd <= measured <= high_vdd:
                add_failure(report, "{} row {} lies outside slack-map bounds".format(trace_id, index))
                break
            eligible = labelled["label_eligible"].lower() == "true"
            if index >= len(label_rows) - HORIZON:
                if eligible or any(labelled[column] for column in ("future_min_slack_ps", "time_to_violation_samples",
                                                                    "raw_label", "hysteresis_label")):
                    add_failure(report, "{} tail row {} fabricates an incomplete future label".format(trace_id, index))
                continue
            if not eligible:
                add_failure(report, "{} eligible row {} is unexpectedly blank".format(trace_id, index))
                continue
            future_slack = float(labelled["future_min_slack_ps"])
            raw_label = int(labelled["raw_label"])
            expected_raw = 2 if future_slack <= 0.0 else 1 if future_slack <= WARNING_SLACK_PS else 0
            if raw_label != expected_raw or labelled["hysteresis_label"] not in {"0", "1", "2"}:
                add_failure(report, "{} row {} violates slack-derived label thresholds".format(trace_id, index))
                continue
            classes[labelled["hysteresis_label"]] += 1
            class_bases[labelled["hysteresis_label"]].add(source["base_waveform_id"])
            split_classes[source["split"]][labelled["hysteresis_label"]] += 1
    report["label_class_counts"] = dict(sorted(classes.items()))
    report["label_class_base_waveform_counts"] = {key: len(value) for key, value in sorted(class_bases.items())}
    report["label_class_counts_by_split"] = {key: dict(sorted(value.items())) for key, value in sorted(split_classes.items())}
    return traces, label_tables


def validate_cleanup(run_dir, trace_ids, report):
    """Check that every successful trace has a complete deletion ledger and no raw residue."""

    ledgers = list((run_dir / "work").glob("*/attempt_*/cleanup.json"))
    report["cleanup_ledger_count"] = len(ledgers)
    ledger_ids = set()
    for path in ledgers:
        ledger_ids.add(path.parents[1].name)
        ledger = json.loads(path.read_text(encoding="utf-8"))
        files = ledger.get("files", [])
        if not files or not all(entry.get("deleted") for entry in files):
            add_failure(report, "cleanup ledger is incomplete: {}".format(path))
    if ledger_ids != set(trace_ids):
        add_failure(report, "cleanup-ledger trace IDs do not match compact trace IDs")
    raw_residuals = []
    for path in (run_dir / "work").rglob("*"):
        if path.is_file() and (path.name in RAW_NAMES or path.suffix in RAW_SUFFIXES):
            raw_residuals.append(str(path.relative_to(run_dir)))
    report["raw_hspice_residual_count"] = len(raw_residuals)
    if raw_residuals:
        add_failure(report, "raw HSPICE files remain: {}".format(raw_residuals[:10]))


def validate_provenance(run_dir, label_dir, windows_dir, corpus_sha256, report):
    """Bind derived artifacts to their published manifests and source digests.

    The label manifest captures both the canonical corpus and every copied
    compact/label pair.  The window manifest captures each aggregate index.
    Checking these hashes prevents an otherwise well-formed but manually
    replaced CSV from being accepted as reproducible pilot evidence.
    """

    provenance_path = label_dir.parent / "provenance.json"
    window_manifest_path = windows_dir / "windows_manifest_v1.json"
    if not provenance_path.is_file():
        add_failure(report, "missing label provenance manifest")
    else:
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        if provenance.get("corpus_sha256") != corpus_sha256:
            add_failure(report, "label provenance references a different corpus")
        if provenance.get("source_trace_count") != 96:
            add_failure(report, "label provenance has an unexpected trace count")
        for entry in provenance.get("traces", []):
            source = run_dir / "compact" / entry["source_csv"]
            labelled = label_dir / entry["label_csv"]
            if not source.is_file() or not labelled.is_file() or entry.get("source_sha256") != sha256_file(source) or entry.get("label_sha256") != sha256_file(labelled):
                add_failure(report, "label provenance digest mismatch for {}".format(entry.get("trace_id", "unknown")))
    if not window_manifest_path.is_file():
        add_failure(report, "missing window manifest")
    else:
        manifest = json.loads(window_manifest_path.read_text(encoding="utf-8"))
        for filename, entry in manifest.get("files", {}).items():
            path = windows_dir / filename
            if not path.is_file() or entry.get("sha256") != sha256_file(path):
                add_failure(report, "window manifest digest mismatch for {}".format(filename))


def validate_windows(windows_dir, label_tables, traces, baseline, stages, report):
    """Reconstruct expected causal endpoints and validate all three window indexes."""

    total_by_length = {}
    for length in (8, 16, 32):
        path = windows_dir / "windows_L{}.csv".format(length)
        if not path.is_file():
            add_failure(report, "missing {}".format(path.name))
            continue
        rows = read_csv(path)
        seen_ids = set()
        by_trace = defaultdict(list)
        for row in rows:
            window_id = row.get("window_id", "")
            if not window_id or window_id in seen_ids:
                add_failure(report, "{} has a duplicate or empty window ID".format(path.name))
                continue
            seen_ids.add(window_id)
            trace_id = row.get("trace_id", "")
            if trace_id not in traces:
                add_failure(report, "{} references unknown trace {}".format(path.name, trace_id))
                continue
            end = int(row["end_index"])
            if int(row["length"]) != length or int(row["baseline_code"]) != baseline:
                add_failure(report, "{} has an inconsistent length or baseline".format(window_id))
            if int(row["target_start_index"]) != end + 1 or int(row["target_end_index"]) != end + HORIZON:
                add_failure(report, "{} violates the e+1..e+8 target contract".format(window_id))
            source_rows = traces[trace_id]
            if end < length - 1 or end >= len(source_rows) - HORIZON:
                add_failure(report, "{} crosses history or future trace bounds".format(window_id))
                continue
            try:
                features = json.loads(row["features_json"])
            except json.JSONDecodeError:
                add_failure(report, "{} contains invalid features_json".format(window_id))
                continue
            expected = [expected_feature(source_rows, index, baseline, stages)
                        for index in range(end - length + 1, end + 1)]
            if len(features) != length or any(len(vector) != ONLINE_FEATURE_WIDTH for vector in features):
                add_failure(report, "{} does not contain an Lx5 online feature tensor".format(window_id))
            elif any(abs(float(actual) - wanted) > 1.0e-12
                     for actual_vector, wanted_vector in zip(features, expected)
                     for actual, wanted in zip(actual_vector, wanted_vector)):
                add_failure(report, "{} contains non-causal or non-contract features".format(window_id))
            # The label at endpoint e is the sole target; never use label e+1
            # as it would move the declared timing horizon forward by one.
            # The in-memory table was populated only after the one-to-one
            # compact/label layer check above.  Reading it here binds every
            # window target to its endpoint without excessive disk traffic.
            target = label_tables[trace_id][end]["hysteresis_label"]
            if row["target_label"] != target:
                add_failure(report, "{} target differs from endpoint label".format(window_id))
            by_trace[trace_id].append(end)
        for trace_id, source_rows in traces.items():
            split = source_rows[0]["split"]
            stride = 2 if split == "train" else 1
            expected_ends = list(range(length - 1, len(source_rows) - HORIZON, stride))
            if split == "train":
                expected_ends = expected_ends[:240]
            if sorted(by_trace[trace_id]) != expected_ends:
                add_failure(report, "{} window endpoints disagree for {}".format(path.name, trace_id))
        total_by_length[str(length)] = len(rows)
    report["window_counts_by_length"] = total_by_length


def validate_hard_pairs(corpus_rows, traces, report):
    """Verify that each difficult pair shares real measured sensor history before its decision point."""

    pairs = defaultdict(list)
    for row in corpus_rows:
        if row.get("hard_pair_id"):
            pairs[row["hard_pair_id"]].append(row)
    for pair_id, members in pairs.items():
        if len(members) != 2:
            add_failure(report, "{} lacks exactly two corpus members".format(pair_id))
            continue
        decision_points = {int(member["hard_pair_decision_index"]) for member in members}
        if len(decision_points) != 1:
            add_failure(report, "{} has inconsistent decision indices".format(pair_id))
            continue
        point = decision_points.pop()
        first, second = (traces[member["trace_id"]] for member in members)
        observable = ("sensor_code", "bubble_count", "code_valid")
        if any(first[index][column] != second[index][column]
               for index in range(point) for column in observable):
            add_failure(report, "{} measured prefix differs before decision index {}".format(pair_id, point))
    report["hard_pair_count"] = len(pairs)


def main():
    """Run the full final audit and emit JSON plus concise Markdown evidence."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--label-dir", required=True, type=Path)
    parser.add_argument("--windows-dir", required=True, type=Path)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--slack-map", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--markdown-output", required=True, type=Path)
    args = parser.parse_args()
    map_rows = read_csv(args.slack_map)
    map_voltages = [float(row["vdd_a_v"]) for row in map_rows]
    report = {"schema_version": 1, "status": "FAIL", "failures": [], "corpus_sha256": sha256_file(args.corpus),
              "slack_map_sha256": sha256_file(args.slack_map), "slack_map_bounds_v": [min(map_voltages), max(map_voltages)]}
    corpus_rows = [json.loads(line) for line in args.corpus.read_text(encoding="utf-8").splitlines() if line.strip()]
    traces, label_tables = validate_trace_layers(args.run_dir, args.label_dir, report["slack_map_bounds_v"], report)
    corpus_ids = {row["trace_id"] for row in corpus_rows}
    if corpus_ids != set(traces):
        add_failure(report, "authoritative corpus trace IDs do not match compact trace IDs")
    validate_cleanup(args.run_dir, traces, report)
    validate_provenance(args.run_dir, args.label_dir, args.windows_dir, report["corpus_sha256"], report)
    validate_windows(args.windows_dir, label_tables, traces, 15, 32, report)
    validate_hard_pairs(corpus_rows, traces, report)
    report["status"] = "PASS" if not report["failures"] else "FAIL"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.write_text(
        "# Dataset Validation V1\n\n"
        "- Status: **{}**\n"
        "- Compact / labelled traces: {} / {}\n"
        "- Cleanup ledgers / raw residuals: {} / {}\n"
        "- Label classes: {}\n"
        "- Distinct base waveforms per class: {}\n"
        "- Window counts (L=8/16/32): {}\n"
        "- Hard pairs with equal measured prefix: {}\n"
        "- Failures: {}\n".format(report["status"], report.get("compact_trace_count", 0), report.get("label_trace_count", 0),
                                   report.get("cleanup_ledger_count", 0), report.get("raw_hspice_residual_count", 0),
                                   report.get("label_class_counts", {}), report.get("label_class_base_waveform_counts", {}),
                                   report.get("window_counts_by_length", {}), report.get("hard_pair_count", 0),
                                   "none" if not report["failures"] else "; ".join(report["failures"])), encoding="utf-8")
    if report["status"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
