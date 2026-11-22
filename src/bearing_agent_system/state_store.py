"""Small SQLite store: one trusted DesignBrief JSON per session, atomic updates."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .checks import get_design_status
from .models import (
    DesignBrief,
    OptimizationSlot,
    ParameterValue,
    TrustedContext,
    UpdateBatch,
    UpdateResult,
)
from .parameter_catalog import (
    FIELDS,
    InvalidChange,
    get_path_value,
    normalize_change,
    set_path_value,
)


class SQLiteDesignBriefStore:
    def __init__(self, database_path: str | Path):
        self.database_path = str(database_path)
        with self._connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS design_briefs (
                  session_id TEXT PRIMARY KEY,
                  revision INTEGER NOT NULL,
                  payload_json TEXT NOT NULL,
                  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )"""
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Commit/rollback the transaction and always release the SQLite handle."""
        conn = sqlite3.connect(self.database_path, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            # sqlite3.Connection.__exit__ does not close the connection.
            # On Windows, a leaked handle prevents TemporaryDirectory cleanup.
            conn.close()

    @staticmethod
    def _session_id(session_id: str) -> str:
        if not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("Non-empty session_id required")
        return session_id

    @staticmethod
    def _load(conn: sqlite3.Connection, session_id: str) -> tuple[DesignBrief, int]:
        row = conn.execute(
            "SELECT payload_json, revision FROM design_briefs WHERE session_id=?",
            (session_id,),
        ).fetchone()
        if row is None:
            brief = DesignBrief()
            conn.execute(
                "INSERT INTO design_briefs (session_id,revision,payload_json) VALUES (?,?,?)",
                (session_id, 0, brief.model_dump_json()),
            )
            return brief, 0
        return DesignBrief.model_validate_json(row["payload_json"]), row["revision"]

    def get_brief(self, session_id: str) -> tuple[DesignBrief, int]:
        session_id = self._session_id(session_id)
        with self._connect() as conn:
            return self._load(conn, session_id)

    def apply_updates(
        self,
        session_id: str,
        batch: UpdateBatch,
        context: TrustedContext,
    ) -> UpdateResult:
        session_id = self._session_id(session_id)
        if not isinstance(batch, UpdateBatch) or not isinstance(context, TrustedContext):
            raise TypeError("Validated UpdateBatch and server-owned TrustedContext required")
        with self._connect() as conn:
            # Serializes writes even if a future caller accidentally opens two connections.
            conn.execute("BEGIN IMMEDIATE")
            original, revision = self._load(conn, session_id)
            edited = original.model_copy(deep=True)
            changed_paths: list[str] = []
            try:
                for change in batch.changes:
                    new_value = self._new_value(change, context, batch.operation)
                    spec = FIELDS[change.path]
                    previous = get_path_value(edited, change.path)
                    if spec.kind == "requirement":
                        if batch.operation != "set":
                            raise InvalidChange("Requirement lists currently support append only")
                        if new_value not in previous:
                            previous.append(new_value)
                            changed_paths.append(change.path)
                        continue
                    is_empty = previous is None or (
                        isinstance(previous, OptimizationSlot) and previous.mode == "optimize"
                    )
                    if batch.operation == "set" and not is_empty and not self._same_value(previous, new_value):
                        raise InvalidChange(f"Cannot set occupied field {change.path}; use replace")
                    if batch.operation == "replace" and is_empty and new_value is not None:
                        # Initial optimization slot is an editable default, not a user fact.
                        if spec.kind != "slot":
                            raise InvalidChange(f"Cannot replace missing field {change.path}; use set")
                    if not self._same_value(previous, new_value):
                        set_path_value(edited, change.path, new_value)
                        changed_paths.append(change.path)
                # Type/geometry checks run on the finished batch, not midway through.
                edited = DesignBrief.model_validate(edited.model_dump())
                self._check_geometry(edited)
            except (InvalidChange, ValueError, TypeError) as exc:
                # No partial writes. The just-created empty brief is safe to persist.
                conn.execute("ROLLBACK")
                return UpdateResult(
                    revision=revision,
                    rejected_changes=[{"path": change.path, "reason": str(exc)}],
                    design_status=get_design_status(original),
                )
            if changed_paths:
                revision += 1
                conn.execute(
                    "UPDATE design_briefs SET payload_json=?, revision=?, updated_at=CURRENT_TIMESTAMP WHERE session_id=?",
                    (edited.model_dump_json(), revision, session_id),
                )
            return UpdateResult(
                revision=revision,
                applied_changes=changed_paths,
                design_status=get_design_status(edited),
            )

    @staticmethod
    def _same_value(previous: object, candidate: object) -> bool:
        if previous is None or candidate is None:
            return previous is candidate
        if isinstance(previous, ParameterValue) and isinstance(candidate, ParameterValue):
            return (previous.value, previous.unit, previous.precision, previous.confirmed) == (
                candidate.value, candidate.unit, candidate.precision, candidate.confirmed
            )
        if isinstance(previous, OptimizationSlot) and isinstance(candidate, OptimizationSlot):
            return (previous.mode, previous.value, previous.bounds) == (
                candidate.mode, candidate.value, candidate.bounds
            )
        return previous == candidate

    @staticmethod
    def _new_value(change, context: TrustedContext, operation: str):
        if change.path not in FIELDS:
            raise InvalidChange(f"Unknown or read-only parameter path: {change.path}")
        if change.value is None:
            if operation != "replace" or not any(
                x in change.evidence_span for x in ("撤销", "取消", "不知道", "不确定", "清除")
            ) or change.evidence_span not in context.user_message:
                raise InvalidChange("Clearing a value needs an explicit user withdrawal")
            if FIELDS[change.path].kind == "requirement":
                raise InvalidChange("Requirement list clearing not implemented in PR-01")
            return None
        return normalize_change(change, context)

    @staticmethod
    def _check_geometry(brief: DesignBrief) -> None:
        d, D = brief.dimensions.d_mm, brief.dimensions.D_mm
        if d is not None and D is not None and d.value >= D.value:
            raise InvalidChange("Bearing outer diameter D must exceed bore d")
