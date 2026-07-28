#!/usr/bin/env python3
"""Run queued traces from one tmux worker window.

One worker owns at most one HSPICE process. It delegates electrical parsing
to the dataset runner and deletes only approved raw products after compact
CSV/JSON checksums have been verified.
"""

from __future__ import print_function

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

import queue

ROOT = Path(__file__).resolve().parents[3]
SPICE_DIR = ROOT / "power_macro" / "tcn_detection" / "spice"
if str(SPICE_DIR) not in sys.path:
    sys.path.insert(0, str(SPICE_DIR))
import run_dataset_trace  # noqa: E402

RAW_SUFFIXES = {".tr0", ".lis", ".mt0", ".pa0", ".st0", ".ic0", ".sp"}
RAW_NAMES = {"trace.mt0.csv"}
FAILURE_LISTING_TAIL_BYTES = 64 * 1024


def retain_failure_listing_tail(attempt_dir, failure_dir, attempt):
    """Copy at most the final 64 KiB of a failed HSPICE listing.

    HSPICE's listing usually contains the actionable parser or convergence
    diagnostic near its end, while retaining a full listing defeats the raw
    waveform lifecycle rule.  The copy is made before raw cleanup and uses a
    seek from EOF, so a multi-gigabyte listing never has to be loaded into RAM.

    Args:
        attempt_dir: Task-private directory owned by the current worker.
        failure_dir: Persistent per-trace diagnostics directory.
        attempt: One-based retry number used to avoid overwriting evidence.

    Returns:
        The retained file name, or ``None`` when HSPICE did not produce a
        listing.  This is deliberately not a raw ``.lis`` extension, which
        prevents later cleanup tooling from treating it as a deletable product.
    """

    listing = attempt_dir / "trace.lis"
    if not listing.is_file():
        return None
    output = failure_dir / ("attempt_{}_lis_tail.txt".format(attempt))
    size = listing.stat().st_size
    with listing.open("rb") as source, output.open("wb") as destination:
        source.seek(max(0, size - FAILURE_LISTING_TAIL_BYTES))
        destination.write(source.read(FAILURE_LISTING_TAIL_BYTES))
    return output.name


def cleanup_raw(attempt_dir, compact_paths):
    """Delete only task-private HSPICE products and write a cleanup ledger."""

    ledger = []
    for path in sorted(attempt_dir.iterdir()):
        if not path.is_file():
            continue
        allowed = path.suffix.lower() in RAW_SUFFIXES or path.name in RAW_NAMES
        if path.name == "hspice_command.log":
            allowed = False
        if allowed:
            size = path.stat().st_size
            path.unlink()
            ledger.append({"path": path.name, "size": size, "deleted": not path.exists()})
    # The compact provenance needs the bounded command transcript, but no raw
    # waveform product.  Treat this one small text log as an allowed retained
    # diagnostic rather than deleting it or accidentally failing cleanup.
    remaining = [path.name for path in attempt_dir.iterdir() if path.is_file() and path.name not in ("cleanup.json", "hspice_command.log")]
    if remaining:
        raise RuntimeError("raw cleanup left unexpected files: {}".format(remaining))
    (attempt_dir / "cleanup.json").write_text(json.dumps({"files": ledger, "compact": [str(path) for path in compact_paths]}, indent=2) + "\n", encoding="utf-8")
    return ledger


def worker_loop(run_dir, worker_name):
    """Claim until the queue is exhausted, retaining bounded failure evidence."""

    database = queue.connect(run_dir / "queue.sqlite3")
    execution_path = ROOT / "power_macro" / "tcn_detection" / "config" / "execution_v1.json"
    phase2_config = ROOT / "power_macro" / "delay_chain" / "phase2_vernier" / "phase2_config.json"
    execution = json.loads(execution_path.read_text(encoding="utf-8"))
    while True:
        # The free-space gate is evaluated before a task claim so a completed
        # trace can still be compacted and cleaned while the remaining queue
        # is paused.  It reserves the declared raw-waveform headroom for every
        # active worker instead of assuming that output size is negligible.
        free_gib = shutil.disk_usage(str(run_dir)).free / float(1024 ** 3)
        if free_gib < float(execution["minimum_free_gib"]):
            (run_dir / "state" / (worker_name + "_disk_guard.rpt")).write_text(
                "status=PAUSED\nfree_gib={:.3f}\nminimum_free_gib={}\n".format(free_gib, execution["minimum_free_gib"]), encoding="ascii")
            return
        task = queue.claim(database, worker_name, int(execution["maximum_attempts"]))
        if task is None:
            return
        trace_id = task["trace_id"]
        attempt_dir = run_dir / "work" / trace_id / ("attempt_{}".format(task["attempt"]))
        try:
            database.execute("UPDATE tasks SET heartbeat=? WHERE trace_id=?", (time.time(), trace_id))
            result = run_dataset_trace.execute(Path(task["spec_path"]), phase2_config, execution_path, attempt_dir, run_dir / "compact", int(execution["trace_timeout_s"]))
            for path in (result["csv"], result["manifest"]):
                if not path.is_file() or path.stat().st_size == 0:
                    raise RuntimeError("compact artifact missing: {}".format(path))
            manifest = json.loads(result["manifest"].read_text(encoding="utf-8"))
            if manifest["compact_csv_sha256"] != run_dataset_trace.sha256_file(result["csv"]):
                raise RuntimeError("compact CSV checksum mismatch")
            cleanup_raw(attempt_dir, [result["csv"], result["manifest"]])
            queue.finish(database, trace_id, "SUCCESS", "compact_and_cleanup_pass")
        except Exception as error:
            failure_dir = run_dir / "failures" / trace_id
            failure_dir.mkdir(parents=True, exist_ok=True)
            # Preserve only a bounded listing tail before deleting this
            # attempt's raw products.  The JSON tells an operator exactly
            # whether diagnostic text exists without retaining a large `.lis`.
            listing_tail = retain_failure_listing_tail(attempt_dir, failure_dir, task["attempt"]) if attempt_dir.exists() else None
            (failure_dir / ("attempt_{}.json".format(task["attempt"]))).write_text(json.dumps(
                {"error": repr(error), "worker": worker_name, "listing_tail": listing_tail}, indent=2) + "\n", encoding="utf-8")
            if attempt_dir.exists():
                # Limit deletion to the suffix/name allowlist.  This protects
                # worker-owned evidence such as hspice_command.log while still
                # guaranteeing raw waveform, deck, measure, and listing files
                # cannot accumulate across retries.
                for path in attempt_dir.iterdir():
                    if path.is_file() and (path.suffix.lower() in RAW_SUFFIXES or path.name in RAW_NAMES):
                        try:
                            path.unlink()
                        except OSError:
                            pass
            state = "RETRY_PENDING" if task["attempt"] < int(execution["maximum_attempts"]) else "FAILED"
            queue.finish(database, trace_id, state, repr(error))
            if state == "RETRY_PENDING":
                time.sleep(int(execution["retry_delay_s"]))


def main():
    """Run one worker selected by tmux window name or explicit argument."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--worker", required=True)
    args = parser.parse_args()
    worker_loop(args.run_dir.resolve(), args.worker)


if __name__ == "__main__":
    main()
