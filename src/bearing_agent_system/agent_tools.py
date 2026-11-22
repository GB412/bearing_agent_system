"""Only two model-visible tools; session identity and user evidence are server owned."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from typing import Any

from langchain_core.tools import BaseTool, tool
from pydantic import ValidationError

from .brief_service import DesignBriefService
from .models import TrustedContext, UpdateBatch


@dataclass
class TurnTools:
    service: DesignBriefService
    session_id: str
    message_id: str
    user_message: str
    max_calls: int = 6
    trace: list[dict[str, Any]] = field(default_factory=list)
    _seen: set[str] = field(default_factory=set, repr=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    def _admit(self, name: str, args: dict[str, Any]) -> dict[str, Any] | None:
        """No model-provided session ID or authentication context is accepted."""
        fingerprint = json.dumps([name, args], sort_keys=True, ensure_ascii=False, default=str)
        if len(self.trace) >= self.max_calls:
            return {"ok": False, "error": "TOOL_BUDGET_EXCEEDED"}
        if fingerprint in self._seen:
            return {"ok": False, "error": "REPEATED_TOOL_CALL"}
        self._seen.add(fingerprint)
        return None

    def _run(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            denied = self._admit(name, args)
            if denied is not None:
                self.trace.append({"name": name, "ok": False, "reason": denied["error"]})
                return denied
            if name == "get_design_status":
                brief, revision = self.service.get_brief(self.session_id)
                status = self.service.get_design_status(self.session_id)
                result = {
                    "ok": True,
                    "revision": revision,
                    "design_status": status.model_dump(mode="json"),
                    "schema_version": brief.schema_version,
                }
            else:
                try:
                    batch = UpdateBatch.model_validate(args)
                    context = TrustedContext(
                        kind="user", message_id=self.message_id,
                        user_message=self.user_message,
                    )
                    outcome = self.service.update_design_brief(
                        self.session_id, batch, context
                    )
                    result = {"ok": not outcome.rejected_changes,
                              **outcome.model_dump(mode="json")}
                except (ValidationError, ValueError, TypeError) as exc:
                    result = {"ok": False, "error": "INVALID_UPDATE",
                              "message": str(exc)[:600]}
            self.trace.append({
                "name": name,
                "ok": result["ok"],
                "revision": result.get("revision"),
                "applied_changes": result.get("applied_changes", []),
                "rejected_changes": result.get("rejected_changes", []),
                "error": result.get("error"),
            })
            return result

    def tools(self) -> list[BaseTool]:
        """Tools capture a trusted turn; the model sees neither identity nor source."""
        context = self

        @tool("update_design_brief")
        def update_design_brief(
            operation: str,
            changes: list[dict[str, Any]],
        ) -> dict[str, Any]:
            """Save/replace user-provided DGB values, requirements, and optimizer slots.

            Only cite exact text within the current user message in evidence_span.
            Each change has path, value, evidence_span, and optionally unit,
            precision and target_id. For requirement edits use replace with target_id.
            Model may not set session_id, message_id, source, or confirmed.
            This tool returns the authoritative write result and latest design status.
            """
            return context._run(
                "update_design_brief", {"operation": operation, "changes": changes}
            )

        @tool("get_design_status")
        def get_design_status() -> dict[str, Any]:
            """Read saved DGB values, requirement IDs, missing/pending/conflicting fields.

            Read-only. update_design_brief already returns the latest status on write.
            """
            return context._run("get_design_status", {})

        return [update_design_brief, get_design_status]

    @property
    def successful_paths(self) -> list[str]:
        return [
            path for entry in self.trace if entry["name"] == "update_design_brief"
            for path in entry.get("applied_changes", [])
        ]

    @property
    def failed_writes(self) -> list[dict[str, Any]]:
        return [
            entry for entry in self.trace
            if entry["name"] == "update_design_brief" and not entry["ok"]
        ]
