"""Minimal SQLite conversation history, separate from trusted DesignBrief state."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TurnRecord:
    session_id: str
    turn_id: str
    user_message: str
    assistant_message: str | None
    status: str
    trace: list[dict[str, Any]]


class ConversationStore:
    """Stores turns, not a second editable copy of engineering parameters."""

    def __init__(self, database_path: str | Path):
        self.database_path = str(database_path)
        with self._connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS conversation_turns (
                  session_id TEXT NOT NULL,
                  turn_id TEXT NOT NULL,
                  user_message TEXT NOT NULL,
                  assistant_message TEXT,
                  status TEXT NOT NULL DEFAULT 'started',
                  trace_json TEXT NOT NULL DEFAULT '[]',
                  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  PRIMARY KEY (session_id, turn_id)
                )"""
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.database_path, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def get_turn(self, session_id: str, turn_id: str) -> TurnRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM conversation_turns WHERE session_id=? AND turn_id=?",
                (session_id, turn_id),
            ).fetchone()
        return self._from_row(row) if row else None

    def begin_turn(self, session_id: str, turn_id: str, user_message: str) -> bool:
        """Return false for existing ID; never rerun an uncertain write after retry."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT user_message FROM conversation_turns WHERE session_id=? AND turn_id=?",
                (session_id, turn_id),
            ).fetchone()
            if row:
                if row["user_message"] != user_message:
                    raise ValueError("turn_id cannot be reused with different content")
                return False
            conn.execute(
                "INSERT INTO conversation_turns(session_id, turn_id, user_message) "
                "VALUES (?,?,?)",
                (session_id, turn_id, user_message),
            )
        return True

    def finish_turn(
        self, session_id: str, turn_id: str, reply: str,
        trace: list[dict[str, Any]], *, failed: bool = False,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE conversation_turns SET assistant_message=?, trace_json=?, status=? "
                "WHERE session_id=? AND turn_id=? AND status='started'",
                (reply, json.dumps(trace, ensure_ascii=False),
                 "failed" if failed else "finished", session_id, turn_id),
            )

    def history(self, session_id: str, max_turns: int = 10) -> list[dict[str, str]]:
        """Recent completed natural-language turns; never treat them as saved facts."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT user_message,assistant_message FROM conversation_turns "
                "WHERE session_id=? AND status='finished' "
                "ORDER BY rowid DESC LIMIT ?",
                (session_id, max_turns),
            ).fetchall()
        messages: list[dict[str, str]] = []
        for row in reversed(rows):
            messages.extend([
                {"role": "user", "content": row["user_message"]},
                {"role": "assistant", "content": row["assistant_message"]},
            ])
        return messages

    def latest_trace(self, session_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT trace_json FROM conversation_turns WHERE session_id=? "
                "ORDER BY rowid DESC LIMIT 1", (session_id,),
            ).fetchone()
        return json.loads(row["trace_json"]) if row else []

    @staticmethod
    def _from_row(row: sqlite3.Row) -> TurnRecord:
        return TurnRecord(
            session_id=row["session_id"],
            turn_id=row["turn_id"],
            user_message=row["user_message"],
            assistant_message=row["assistant_message"],
            status=row["status"],
            trace=json.loads(row["trace_json"]),
        )
