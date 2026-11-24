"""SQLite DesignBrief store with independent validation and atomic subset commits."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

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
        brief = DesignBrief.model_validate_json(row["payload_json"])
        # Existing PR-01 databases may contain requirements without IDs.
        if SQLiteDesignBriefStore._ensure_requirement_ids(brief):
            conn.execute(
                "UPDATE design_briefs SET payload_json=? WHERE session_id=?",
                (brief.model_dump_json(), session_id),
            )
        return brief, row["revision"]

    @staticmethod
    def _ensure_requirement_ids(brief: DesignBrief) -> bool:
        migrated = False
        for field in ("constraints", "preferences", "geometric_bounds"):
            for requirement in getattr(brief.requirements, field):
                if requirement.id is None:
                    requirement.id = f"req-{uuid4().hex[:16]}"
                    migrated = True
        return migrated

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
        """Validate each candidate independently; commit the valid subset once.

        A failed scalar/enum/requirement does not discard unrelated valid user
        parameters. Coupled bore/outer-diameter edits are held together until
        their final geometry is checked. A single SQLite transaction still
        commits the resulting DesignBrief atomically.
        """
        session_id = self._session_id(session_id)
        if not isinstance(batch, UpdateBatch) or not isinstance(context, TrustedContext):
            raise TypeError("Validated UpdateBatch and server-owned TrustedContext required")
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            original, revision = self._load(conn, session_id)
            edited = original.model_copy(deep=True)
            changed_paths: list[str] = []
            rejected: list[dict[str, str]] = []
            for change in batch.changes:
                # One candidate per field: even mutations of an existing
                # requirement list cannot leak out of a failed candidate.
                candidate = edited.model_copy(deep=True)
                try:
                    changed = self._apply_one(candidate, change, context, batch.operation)
                    candidate = DesignBrief.model_validate(candidate.model_dump())
                except (InvalidChange, ValueError, TypeError) as exc:
                    rejected.append({"path": change.path, "reason": str(exc)})
                    continue
                edited = candidate
                if changed:
                    changed_paths.append(change.path)

            try:
                self._check_geometry(edited)
            except InvalidChange as exc:
                # d and D form one coupled validation group. If their final
                # combination is invalid, neither changed dimension may commit;
                # unrelated width, load, requirements etc. can still succeed.
                conflicting = {"dimensions.d_mm", "dimensions.D_mm"} & set(changed_paths)
                for path in sorted(conflicting):
                    set_path_value(edited, path, get_path_value(original, path))
                    changed_paths.remove(path)
                    rejected.append({"path": path, "reason": str(exc)})
                self._check_geometry(edited)

            if changed_paths:
                revision += 1
                conn.execute(
                    "UPDATE design_briefs SET payload_json=?, revision=?, updated_at=CURRENT_TIMESTAMP WHERE session_id=?",
                    (edited.model_dump_json(), revision, session_id),
                )
            return UpdateResult(
                revision=revision,
                applied_changes=changed_paths,
                rejected_changes=rejected,
                design_status=get_design_status(edited),
            )

    @classmethod
    def _apply_one(
        cls, brief: DesignBrief, change, context: TrustedContext, operation: str
    ) -> bool:
        """Mutate only a disposable candidate; return whether it actually changed."""
        new_value = cls._new_value(change, context, operation)
        spec = FIELDS[change.path]
        previous = get_path_value(brief, change.path)
        if spec.kind == "requirement":
            if operation == "set":
                if change.target_id is not None:
                    raise InvalidChange("New requirement cannot specify a target_id")
                duplicate = any(
                    cls._requirement_signature(x) == cls._requirement_signature(new_value)
                    for x in previous
                )
                if duplicate:
                    return False
                if any(
                    x.field == new_value.field and x.operator == new_value.operator
                    for x in previous
                ):
                    raise InvalidChange(
                        "Requirement on this field/operator already exists; use replace"
                    )
                new_value.id = f"req-{uuid4().hex[:16]}"
                previous.append(new_value)
                return True
            if not change.target_id:
                raise InvalidChange("Requirement replace/withdraw needs target_id")
            matches = [
                i for i, item in enumerate(previous) if item.id == change.target_id
            ]
            if len(matches) != 1:
                raise InvalidChange("Requirement target_id not found or ambiguous")
            index = matches[0]
            if new_value is None:
                previous.pop(index)
                return True
            if cls._requirement_signature(previous[index]) != cls._requirement_signature(new_value):
                new_value.id = change.target_id
                previous[index] = new_value
                return True
            return False
        if change.target_id is not None:
            raise InvalidChange("target_id is only supported for requirement edits")
        is_empty = previous is None or (
            isinstance(previous, OptimizationSlot) and previous.mode == "optimize"
        )
        if operation == "set" and not is_empty and not cls._same_value(previous, new_value):
            raise InvalidChange(f"Cannot set occupied field {change.path}; use replace")
        if operation == "replace" and is_empty and new_value is not None:
            if spec.kind != "slot":
                raise InvalidChange(f"Cannot replace missing field {change.path}; use set")
        if cls._same_value(previous, new_value):
            return False
        set_path_value(brief, change.path, new_value)
        return True

    @staticmethod
    def _requirement_signature(value) -> tuple:
        return (value.field, value.operator, value.value, value.unit)

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
                x in change.evidence_span for x in (
                    "撤销", "取消", "不知道", "不确定", "清除", "删除", "移除", "不再限制"
                )
            ) or change.evidence_span not in context.user_message:
                raise InvalidChange("Clearing a value needs an explicit user withdrawal")
            return None
        return normalize_change(change, context)

    @staticmethod
    def _check_geometry(brief: DesignBrief) -> None:
        d, D = brief.dimensions.d_mm, brief.dimensions.D_mm
        if d is not None and D is not None and d.value >= D.value:
            raise InvalidChange("Bearing outer diameter D must exceed bore d")
