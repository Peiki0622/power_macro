#!/usr/bin/env python3
"""Generate auditable OOD hard-pair metadata from existing corpus requests.

Hard pairs share the observed PWL prefix through their declared decision index
and then diverge only in the future.  This module records the intended pair
contract; electrical validation after HSPICE compares the real sensor-code
prefix before any model result may cite the pair.
"""

from __future__ import print_function

import argparse
import json
from pathlib import Path


def main():
    """Attach four OOD pair IDs without moving any trace across a split."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.corpus.read_text(encoding="utf-8").splitlines() if line.strip()]
    ood = [row for row in rows if row["split"] == "ood_test" and row.get("event")]
    pairs = []
    for index in range(0, min(8, len(ood) - 1), 2):
        left, right = ood[index:index + 2]
        pair_id = "hard_pair_{:02d}".format(index // 2)
        left["hard_pair_id"] = pair_id
        right["hard_pair_id"] = pair_id
        pairs.append({"hard_pair_id": pair_id, "members": [left["trace_id"], right["trace_id"]], "split": "ood_test",
                      "decision_index": min(left["event"]["start_index"], right["event"]["start_index"])})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    args.output.with_suffix(".hard_pairs.json").write_text(json.dumps(pairs, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
