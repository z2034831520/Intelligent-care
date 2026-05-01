from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List


class EventStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    level TEXT,
                    timestamp TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )

    def insert_event(self, kind: str, timestamp: str, payload: Dict[str, Any], level: str = "") -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO events(kind, level, timestamp, payload) VALUES (?, ?, ?, ?)",
                (kind, level, timestamp, json.dumps(payload, ensure_ascii=False)),
            )

    def latest_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, kind, level, timestamp, payload FROM events ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        results = []
        for row in rows:
            results.append(
                {
                    "id": row[0],
                    "kind": row[1],
                    "level": row[2],
                    "timestamp": row[3],
                    "payload": json.loads(row[4]),
                }
            )
        return results
