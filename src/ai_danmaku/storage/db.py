from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Tuple


SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts INTEGER NOT NULL,
  role TEXT NOT NULL,
  text TEXT NOT NULL,
  source TEXT,
  extra_json TEXT
);
CREATE TABLE IF NOT EXISTS actions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts INTEGER NOT NULL,
  kind TEXT NOT NULL,
  ref_id INTEGER,
  status TEXT,
  info TEXT
);
CREATE TABLE IF NOT EXISTS tts_records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  msg_id INTEGER NOT NULL,
  path TEXT NOT NULL,
  duration_sec REAL,
  voice TEXT
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=ON;")
    for stmt in filter(None, SCHEMA.split(";\n")):
        conn.execute(stmt)
    conn.commit()
    return conn


def insert_message(conn: sqlite3.Connection, ts: int, role: str, text: str, source: str = "", extra_json: str = "") -> int:
    cur = conn.execute(
        "INSERT INTO messages(ts, role, text, source, extra_json) VALUES (?, ?, ?, ?, ?)",
        (ts, role, text, source, extra_json),
    )
    conn.commit()
    return int(cur.lastrowid)


def insert_action(conn: sqlite3.Connection, ts: int, kind: str, ref_id: Optional[int], status: str, info: str = "") -> int:
    cur = conn.execute(
        "INSERT INTO actions(ts, kind, ref_id, status, info) VALUES (?, ?, ?, ?, ?)",
        (ts, kind, ref_id, status, info),
    )
    conn.commit()
    return int(cur.lastrowid)


def insert_tts(conn: sqlite3.Connection, msg_id: int, path: Path, duration_sec: float, voice: str) -> int:
    cur = conn.execute(
        "INSERT INTO tts_records(msg_id, path, duration_sec, voice) VALUES (?, ?, ?, ?)",
        (msg_id, str(path), duration_sec, voice),
    )
    conn.commit()
    return int(cur.lastrowid)

