#!/usr/bin/env python3
"""Print queue and disk status for a running batch."""

from __future__ import print_function

import argparse
import shutil
from pathlib import Path

import queue


def main():
    """Report all task states without changing queue ownership."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    args = parser.parse_args()
    database = queue.connect(args.run_dir / "queue.sqlite3")
    rows = database.execute("SELECT state, COUNT(*) FROM tasks GROUP BY state ORDER BY state").fetchall()
    free = shutil.disk_usage(str(args.run_dir)).free / float(1024 ** 3)
    print("run_dir={}".format(args.run_dir.resolve()))
    print("free_gib={:.2f}".format(free))
    for state, count in rows:
        print("{}={}".format(state, count))


if __name__ == "__main__":
    main()
