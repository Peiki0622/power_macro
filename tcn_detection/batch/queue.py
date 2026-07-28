#!/usr/bin/env python3
"""SQLite queue operations for independently restartable HSPICE traces."""

from __future__ import print_function

import sqlite3
import time


SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
 trace_id TEXT PRIMARY KEY, base_waveform_id TEXT NOT NULL, split TEXT NOT NULL,
 spec_path TEXT NOT NULL, state TEXT NOT NULL, attempt INTEGER NOT NULL DEFAULT 0,
 worker TEXT, heartbeat REAL, started REAL, finished REAL, detail TEXT
)
"""


def connect(path):
    """Open a WAL database so independent tmux workers can claim safely."""

    connection = sqlite3.connect(str(path), timeout=30.0, isolation_level=None)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=30000")
    connection.execute(SCHEMA)
    return connection


def claim(connection, worker, maximum_attempts):
    """Atomically claim exactly one retryable trace, or return None when done."""

    connection.execute("BEGIN IMMEDIATE")
    row = connection.execute("SELECT trace_id, spec_path, attempt FROM tasks WHERE state IN ('PENDING','RETRY_PENDING') AND attempt < ? ORDER BY trace_id LIMIT 1", (maximum_attempts,)).fetchone()
    if row is None:
        connection.execute("COMMIT")
        return None
    now = time.time()
    connection.execute("UPDATE tasks SET state='RUNNING', attempt=attempt+1, worker=?, heartbeat=?, started=? WHERE trace_id=?", (worker, now, now, row[0]))
    connection.execute("COMMIT")
    return {"trace_id": row[0], "spec_path": row[1], "attempt": row[2] + 1}


def finish(connection, trace_id, state, detail):
    """Publish terminal or retryable state only after the attempt has ended."""

    connection.execute("UPDATE tasks SET state=?, detail=?, finished=?, heartbeat=? WHERE trace_id=?", (state, detail, time.time(), time.time(), trace_id))
