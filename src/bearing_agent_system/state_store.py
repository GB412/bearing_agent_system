"""SQLite DesignBrief store with independent validation and atomic subset commits."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from .catalog_choices import CATALOG_FIELDS, CatalogChoices
from .checks import get_design_status
from .models import (
    DesignBrief,
    OptimizationSlot,
    ParameterValue,
    Source,
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
    def __init__(
        self, database_path: str | Path, *, catalog_choices: CatalogChoices | None = None
    ):
        self.database_path = str(database_path)
        self.catalog_choices = catalog_choices or CatalogChoices()
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
            conn.execute(
                """CREATE TABLE IF NOT EXISTS design_recommendations (
                  session_id TEXT NOT NULL,
                  proposal_id TEXT NOT NULL,
                  base_revision INTEGER NOT NULL,
                  created_turn_id TEXT NOT NULL,
                  changes_json TEXT NOT NULL,
                  knowledge_ids_json TEXT NOT NULL,
                  status TEXT NOT NULL DEFAULT 'pending',
                  PRIMARY KEY (session_id, proposal_id)
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

    def _apply_one(
        self, brief: DesignBrief, change, context: TrustedContext, operation: str
    ) -> bool:
        """Mutate only a disposable candidate; return whether it actually changed."""
        new_value = self._new_value(change, context, operation)
        if change.path in CATALOG_FIELDS and new_value is not None:
            canonical_id = self.catalog_choices.resolve(change.path, new_value.value)
            new_value = new_value.model_copy(update={"value": canonical_id})
        spec = FIELDS[change.path]
        previous = get_path_value(brief, change.path)
        if spec.kind == "requirement":
            if operation == "set":
                if change.target_id is not None:
                    raise InvalidChange("New requirement cannot specify a target_id")
                duplicate = any(
                    self._requirement_signature(x) == self._requirement_signature(new_value)
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
            if self._requirement_signature(previous[index]) != self._requirement_signature(new_value):
                new_value.id = change.target_id
                previous[index] = new_value
                return True
            return False
        if change.target_id is not None:
            raise InvalidChange("target_id is only supported for requirement edits")
        is_empty = previous is None or (
            isinstance(previous, OptimizationSlot) and previous.mode == "optimize"
        )
        if operation == "set" and not is_empty and not self._same_value(previous, new_value):
            raise InvalidChange(f"Cannot set occupied field {change.path}; use replace")
        if operation == "replace" and is_empty and new_value is not None:
            if spec.kind != "slot":
                raise InvalidChange(f"Cannot replace missing field {change.path}; use set")
        if self._same_value(previous, new_value):
            return False
        set_path_value(brief, change.path, new_value)
        return True

    def propose_recommendation(
        self, session_id: str, changes: list[dict], turn_id: str,
        knowledge_ids: list[str] | None = None,
    ) -> dict:
        """Store a small selection proposal, never a confirmed design fact.

        Only non-numeric engineering choice fields are eligible in PR-03.
        Numeric optimization and constraints must still use trusted user facts.
        """
        allowed = {
            path for path, spec in FIELDS.items()
            if path.startswith("engineering.") and spec.kind in ("enum", "string")
        }
        if not isinstance(changes, list) or not 1 <= len(changes) <= 8:
            raise InvalidChange("Recommendation needs 1 to 8 engineering choices")
        proposals: list[dict[str, str]] = []
        seen: set[str] = set()
        for entry in changes:
            if not isinstance(entry, dict) or set(entry) - {"path", "value"}:
                raise InvalidChange("Recommendation accepts path and value only")
            path, value = entry.get("path"), entry.get("value")
            if path not in allowed or path in seen:
                raise InvalidChange("Unsupported or repeated recommendation field")
            if not isinstance(value, str) or not value.strip() or len(value) > 80:
                raise InvalidChange("Recommendation needs a short nonempty choice")
            if FIELDS[path].kind == "enum" and value not in FIELDS[path].choices:
                raise InvalidChange("Unsupported recommendation enum value")
            if path in CATALOG_FIELDS:
                value = self.catalog_choices.resolve(path, value)
            proposals.append({"path": path, "value": value.strip()})
            seen.add(path)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            _, revision = self._load(conn, session_id)
            # There is at most one actionable recommendation per session.
            conn.execute(
                "UPDATE design_recommendations SET status='superseded' "
                "WHERE session_id=? AND status='pending'", (session_id,),
            )
            proposal_id = "rec-" + uuid4().hex[:12]
            conn.execute(
                "INSERT INTO design_recommendations "
                "(session_id,proposal_id,base_revision,created_turn_id,"
                "changes_json,knowledge_ids_json) VALUES (?,?,?,?,?,?)",
                (session_id, proposal_id, revision, turn_id,
                 json.dumps(proposals, ensure_ascii=False),
                 json.dumps(knowledge_ids or [], ensure_ascii=False)),
            )
        return {
            "proposal_id": proposal_id, "base_revision": revision,
            "changes": proposals, "knowledge_ids": knowledge_ids or [],
            "status": "PROPOSED", "review_status": "UNVERIFIED",
        }

    def pending_recommendation(self, session_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT proposal_id, base_revision, created_turn_id, "
                "changes_json, knowledge_ids_json FROM design_recommendations "
                "WHERE session_id=? AND status='pending' ORDER BY rowid DESC LIMIT 1",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "proposal_id": row["proposal_id"],
            "base_revision": row["base_revision"],
            "created_turn_id": row["created_turn_id"],
            "changes": json.loads(row["changes_json"]),
            "knowledge_ids": json.loads(row["knowledge_ids_json"]),
        }

    def adopt_recommendation(
        self, session_id: str, proposal_id: str, context: TrustedContext,
        *, delegated: bool = False,
    ) -> UpdateResult:
        """Commit only server-stored recommended values after verified consent.

        The current user turn authorizes adoption, not the recommendation's
        numbers. A stale or previously consumed proposal cannot be replayed.
        """
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            original, revision = self._load(conn, session_id)
            row = conn.execute(
                "SELECT * FROM design_recommendations WHERE "
                "session_id=? AND proposal_id=? AND status='pending'",
                (session_id, proposal_id),
            ).fetchone()
            if row is None:
                raise InvalidChange("No pending recommendation with that ID")
            if row["base_revision"] != revision:
                raise InvalidChange("Recommendation is stale; regenerate after design changes")
            entries = json.loads(row["changes_json"])
            if delegated:
                if row["created_turn_id"] != context.message_id:
                    raise InvalidChange("Delegated adoption must be proposed this user turn")
                if not json.loads(row["knowledge_ids_json"]):
                    raise InvalidChange("Delegated choice requires queried engineering evidence")
            edited = original.model_copy(deep=True)
            changed: list[str] = []
            for entry in entries:
                path, value = entry["path"], entry["value"]
                if path in CATALOG_FIELDS:
                    value = self.catalog_choices.resolve(path, value)
                previous = get_path_value(edited, path)
                if previous is not None and previous.value != value:
                    raise InvalidChange(f"Cannot overwrite existing user choice: {path}")
                if previous is not None:
                    continue
                source = Source(kind="derived", message_id=context.message_id, ref=proposal_id)
                note = (
                    "用户授权Agent确定的初步选择；未经工程校核"
                    if delegated else "用户采纳Agent推荐；未经工程校核"
                )
                set_path_value(edited, path, ParameterValue(
                    value=value, unit=None, confirmed=True,
                    source=source, note=note, evidence_status="UNVERIFIED",
                ))
                changed.append(path)
            edited = DesignBrief.model_validate(edited.model_dump())
            self._check_geometry(edited)
            if changed:
                revision += 1
                conn.execute(
                    "UPDATE design_briefs SET payload_json=?, revision=?, "
                    "updated_at=CURRENT_TIMESTAMP WHERE session_id=?",
                    (edited.model_dump_json(), revision, session_id),
                )
            conn.execute(
                "UPDATE design_recommendations SET status='accepted' "
                "WHERE session_id=? AND proposal_id=?",
                (session_id, proposal_id),
            )
        return UpdateResult(
            revision=revision, applied_changes=changed,
            design_status=get_design_status(edited),
        )

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
