"""SQLite persistence for tasks and their tracked time entries.

Timestamps are ISO 8601 naive-local-time text (e.g. "2026-07-02T14:33:07"),
which sorts and compares correctly as text and round-trips through
datetime.fromisoformat() with no parsing code.
"""
import os
import pathlib
import sqlite3
from datetime import datetime

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE TABLE IF NOT EXISTS time_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id),
    start_time TEXT NOT NULL,
    end_time TEXT
);
CREATE INDEX IF NOT EXISTS idx_time_entries_task_id ON time_entries(task_id);
CREATE INDEX IF NOT EXISTS idx_time_entries_open ON time_entries(task_id, end_time);
"""


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def get_db_path() -> pathlib.Path:
    appdata = os.environ["APPDATA"]
    directory = pathlib.Path(appdata) / "FocusOverlay"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "tasks.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA)
    return conn


def create_task(title: str) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO tasks (title, created_at, completed_at) VALUES (?, ?, NULL)",
            (title, now_iso()),
        )
        return cur.lastrowid


def rename_task(task_id: int, new_title: str) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE tasks SET title = ? WHERE id = ?", (new_title, task_id))


def complete_task(task_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE tasks SET completed_at = ? WHERE id = ?", (now_iso(), task_id)
        )


def list_open_tasks() -> list:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM tasks WHERE completed_at IS NULL ORDER BY id ASC"
        ).fetchall()


def get_task(task_id: int):
    with get_connection() as conn:
        return conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()


def open_time_entry(task_id: int) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO time_entries (task_id, start_time, end_time) VALUES (?, ?, NULL)",
            (task_id, now_iso()),
        )
        return cur.lastrowid


def close_open_time_entry(task_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE time_entries SET end_time = ? WHERE task_id = ? AND end_time IS NULL",
            (now_iso(), task_id),
        )


def get_open_time_entry_task_id():
    with get_connection() as conn:
        row = conn.execute(
            "SELECT task_id FROM time_entries WHERE end_time IS NULL LIMIT 1"
        ).fetchone()
        return row["task_id"] if row else None


def get_time_per_task(range_start, range_end) -> list:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT tasks.id AS id, tasks.title AS title,
                   SUM(strftime('%s', COALESCE(time_entries.end_time, datetime('now', 'localtime')))
                       - strftime('%s', time_entries.start_time)) AS total_seconds
            FROM time_entries
            JOIN tasks ON tasks.id = time_entries.task_id
            WHERE (:range_start IS NULL OR time_entries.start_time >= :range_start)
              AND (:range_end IS NULL OR time_entries.start_time < :range_end)
            GROUP BY tasks.id, tasks.title
            HAVING total_seconds > 0
            ORDER BY total_seconds DESC
            """,
            {"range_start": range_start, "range_end": range_end},
        ).fetchall()


def get_time_entries_for_chart(range_start, range_end) -> list:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT time_entries.task_id AS task_id, tasks.title AS title,
                   time_entries.start_time AS start_time, time_entries.end_time AS end_time
            FROM time_entries
            JOIN tasks ON tasks.id = time_entries.task_id
            WHERE (:range_start IS NULL OR time_entries.start_time >= :range_start)
              AND (:range_end IS NULL OR time_entries.start_time < :range_end)
            ORDER BY tasks.id, time_entries.start_time
            """,
            {"range_start": range_start, "range_end": range_end},
        ).fetchall()
