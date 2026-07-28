#!/usr/bin/env python3
"""Materialize and audit immutable trace-level dataset splits."""

from __future__ import print_function

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


def sha256_file(path):
    """Return the source corpus digest stored in each split report."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_audit(rows):
    """Validate grouping, OOD isolation, hard pairs, and coverage metadata.

    The corpus is already assigned to named splits before electrical
    simulation.  This function deliberately audits that immutable assignment
    rather than reshuffling traces, because a later random split would leak
    base-waveform variants into validation or test data.
    """

    groups = defaultdict(set)
    pairs = defaultdict(set)
    pair_splits = defaultdict(set)
    split_counts = Counter()
    background_counts = Counter()
    duty_counts = Counter()
    train_families = set()
    ood_families = set()
    for row in rows:
        groups[row["base_waveform_id"]].add(row["split"])
        split_counts[row["split"]] += 1
        background_counts[row["background_mode"]] += 1
        duty_counts[str(row.get("event_duty_cycle"))] += 1
        # ``background`` is the deliberate no-event placeholder shared by all
        # partitions.  It is not an OOD waveform family, so excluding it here
        # preserves valid safe-background coverage while still rejecting every
        # actual OOD droop family from training.
        if row["split"] == "train" and row["waveform_family_id"] != "background":
            train_families.add(row["waveform_family_id"])
        if row["split"] == "ood_test" and row["waveform_family_id"] != "background":
            ood_families.add(row["waveform_family_id"])
        if row.get("hard_pair_id"):
            pairs[row["hard_pair_id"]].add(row["trace_id"])
            pair_splits[row["hard_pair_id"]].add(row["split"])
    leaked = {key: sorted(value) for key, value in groups.items() if len(value) != 1}
    bad_pairs = {key: sorted(value) for key, value in pairs.items() if len(value) != 2}
    misplaced_pairs = {key: sorted(value) for key, value in pair_splits.items() if value != {"ood_test"}}
    if leaked:
        raise ValueError("base_waveform_id crosses split: {}".format(leaked))
    if bad_pairs:
        raise ValueError("hard pairs must contain exactly two trace IDs: {}".format(bad_pairs))
    if misplaced_pairs:
        raise ValueError("hard pairs must be entirely assigned to ood_test: {}".format(misplaced_pairs))
    if ood_families & train_families:
        raise ValueError("OOD waveform families appear in train: {}".format(sorted(ood_families & train_families)))
    return {"trace_count": len(rows), "base_waveform_count": len(groups), "split_counts": dict(sorted(split_counts.items())),
            "background_counts": dict(sorted(background_counts.items())), "event_duty_cycle_counts": dict(sorted(duty_counts.items())),
            "hard_pair_members": {key: sorted(value) for key, value in sorted(pairs.items())},
            "hard_pair_splits": {key: sorted(value) for key, value in sorted(pair_splits.items())},
            "train_families": sorted(train_families), "ood_families": sorted(ood_families), "leaked_base_ids": leaked}


def main():
    """Write machine-readable split membership plus a human audit summary."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--split-output", required=True, type=Path)
    parser.add_argument("--markdown-output", required=True, type=Path)
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.corpus.read_text(encoding="utf-8").splitlines() if line.strip()]
    report = build_audit(rows)
    report["corpus_sha256"] = sha256_file(args.corpus)
    report["status"] = "PASS"
    membership = {"schema_version": 1, "corpus_sha256": report["corpus_sha256"], "splits": {}}
    for split in ("train", "validation", "iid_test", "ood_test"):
        membership["splits"][split] = [{key: row.get(key, "") for key in ("trace_id", "base_waveform_id", "waveform_family_id", "hard_pair_id", "background_mode", "event_duty_cycle")}
                                       for row in rows if row["split"] == split]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.split_output.parent.mkdir(parents=True, exist_ok=True)
    args.split_output.write_text(json.dumps(membership, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.write_text(
        "# Split Audit V1\n\n"
        "- Corpus SHA256: `{}`\n"
        "- Traces / base waveforms: {} / {}\n"
        "- Split counts: {}\n"
        "- Base-waveform leakage: none\n"
        "- Hard pairs: {} complete pairs, all in OOD test\n"
        "- OOD families excluded from train: {}\n"
        "- Background coverage: {}\n"
        "- Event-duty coverage: {}\n".format(report["corpus_sha256"], report["trace_count"], report["base_waveform_count"],
                                                 report["split_counts"], len(report["hard_pair_members"]), report["ood_families"],
                                                 report["background_counts"], report["event_duty_cycle_counts"]), encoding="utf-8")


if __name__ == "__main__":
    main()
