#!/usr/bin/env python3
"""Create one non-overwriting batch run directory and its SQLite queue."""

from __future__ import print_function

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import queue


ROOT = Path(__file__).resolve().parents[3]


def sha256_file(path):
    """Hash a compact import without loading an electrical trace into memory."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def import_legacy_compact(legacy_run, compact_dir):
    """Expose immutable Pilot compact evidence through read-only symlinks.

    The formal run deliberately owns no copied Pilot waveform data.  A link
    keeps the original checksum, cleanup ledger, and source location intact,
    while allowing label/window tools to read one unified ``compact`` view.
    New HSPICE jobs have unique trace IDs and therefore cannot overwrite a
    legacy link.
    """

    legacy_compact = Path(legacy_run) / "compact"
    sources = sorted(path for path in legacy_compact.iterdir() if path.suffix in {".csv", ".json"})
    if not sources:
        raise ValueError("legacy compact directory has no CSV/JSON evidence: {}".format(legacy_compact))
    imports = []
    for source in sources:
        destination = compact_dir / source.name
        if destination.exists() or destination.is_symlink():
            raise ValueError("legacy import would overwrite compact entry: {}".format(destination))
        destination.symlink_to(source.resolve())
        imports.append({"name": source.name, "source": str(source.resolve()), "sha256": sha256_file(source)})
    return imports


def main():
    """Materialize immutable per-trace specs before tmux workers are started."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--expected-task-count", required=True, type=int,
                        help="Exact extension-task count declared by the formal dataset configuration.")
    parser.add_argument("--formal-corpus", type=Path,
                        help="Combined authority containing legacy and extension rows for later labelling.")
    parser.add_argument("--legacy-run", type=Path,
                        help="Optional immutable Pilot run whose compact files are linked into this formal view.")
    args = parser.parse_args()
    run_dir = ROOT / "power_macro" / "tcn_detection" / "runs" / args.dataset_id
    if run_dir.exists():
        raise ValueError("refusing to overwrite batch run: {}".format(run_dir))
    specs = [json.loads(line) for line in args.corpus.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.expected_task_count <= 0 or len(specs) != args.expected_task_count or len({item["trace_id"] for item in specs}) != len(specs):
        raise ValueError("extension corpus does not match its declared unique task count")
    run_dir.mkdir(parents=True)
    for name in ("specs", "compact", "work", "logs", "failures", "state"):
        (run_dir / name).mkdir()
    database = queue.connect(run_dir / "queue.sqlite3")
    for spec in specs:
        path = run_dir / "specs" / (spec["trace_id"] + ".json")
        path.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        database.execute("INSERT INTO tasks(trace_id,base_waveform_id,split,spec_path,state) VALUES(?,?,?,?, 'PENDING')", (spec["trace_id"], spec["base_waveform_id"], spec["split"], str(path)))
    shutil.copy2(args.corpus, run_dir / "extension_corpus.jsonl")
    legacy_imports = []
    if args.legacy_run is not None:
        legacy_imports = import_legacy_compact(args.legacy_run, run_dir / "compact")
    if args.formal_corpus is not None:
        shutil.copy2(args.formal_corpus, run_dir / "formal_corpus.jsonl")
    (run_dir / "source_manifest.json").write_text(json.dumps(
        {"schema_version": 1, "extension_corpus": str(args.corpus.resolve()), "extension_task_count": len(specs),
         "formal_corpus": "" if args.formal_corpus is None else str(args.formal_corpus.resolve()),
         "legacy_run": "" if args.legacy_run is None else str(args.legacy_run.resolve()), "legacy_imports": legacy_imports},
        indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (run_dir / "run_config.json").write_text(json.dumps(
        {"dataset_id": args.dataset_id, "task_count": len(specs), "legacy_import_count": len(legacy_imports),
         "formal_trace_count": len(specs) + len({entry["name"].split(".")[0] for entry in legacy_imports if entry["name"].endswith(".csv")})},
        indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
