"""Bounded agent tools; brief writes and engineering knowledge remain separate."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from typing import Any

from langchain_core.tools import BaseTool, tool
from pydantic import ValidationError

from .brief_service import DesignBriefService
from .knowledge import KnowledgeRepository
from .models import TrustedContext, UpdateBatch
from .parameter_catalog import FIELDS


@dataclass
class TurnTools:
    service: DesignBriefService
    session_id: str
    message_id: str
    user_message: str
    max_calls: int = 6
    knowledge: KnowledgeRepository = field(default_factory=KnowledgeRepository)
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
            elif name == "lookup_engineering_knowledge":
                result = self.knowledge.lookup(args.get("topic", ""), args.get("query", ""))
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
            # Record field identity even for schema validation failures.
            # Do not persist rejected proposed values or model-supplied evidence.
            attempted_paths = []
            if name == "update_design_brief" and isinstance(args.get("changes"), list):
                attempted_paths = list(dict.fromkeys(
                    item["path"] for item in args["changes"]
                    if isinstance(item, dict) and isinstance(item.get("path"), str)
                ))
            self.trace.append({
                "name": name,
                "ok": result["ok"],
                "revision": result.get("revision"),
                "attempted_paths": attempted_paths,
                "applied_changes": result.get("applied_changes", []),
                "rejected_changes": result.get("rejected_changes", []),
                "error": result.get("error"),
                # Retain minimal auditable knowledge receipts without storing
                # free-form model queries or copying the entire catalog into trace.
                "knowledge_status": result.get("status") if name == "lookup_engineering_knowledge"
                else None,
                "knowledge_ids": [
                    item["id"] for item in (
                        result.get("results", []) + result.get("related_sources", [])
                    )
                ] if name == "lookup_engineering_knowledge" else [],
                "knowledge_source_urls": [
                    item["source"]["url"] for item in (
                        result.get("results", []) + result.get("related_sources", [])
                    )
                ] if name == "lookup_engineering_knowledge" else [],
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

        # One source of truth: show the model exactly the paths the validator accepts.
        update_design_brief.description += (
            "\n可写 path（必须完整匹配，不能写容器名或自造字段）："
            + "、".join(FIELDS)
            + "\n几何上限示例 changes 项："
            '{"path":"requirements.geometric_bounds[]",'
            '"value":{"field":"dimensions.D_mm","operator":"<=","value":62,"unit":"mm"},'
            '"evidence_span":"外径不能超过62mm"}'
            "\n寿命下限示例 changes 项："
            '{"path":"requirements.constraints[]",'
            '"value":{"field":"life_hours","operator":">=","value":20000,"unit":"h"},'
            '"evidence_span":"寿命至少20000小时"}'
            "\n游隙示例 changes 项："
            '{"path":"engineering.clearance.group","value":"CN",'
            '"evidence_span":"游隙选CN"}'
            "\n以上 evidence_span 仅是示例；真实调用必须引用当前用户消息的原文。"
        )

        @tool("get_design_status")
        def get_design_status() -> dict[str, Any]:
            """Read saved DGB values, requirement IDs, missing/pending/conflicting fields.

            Read-only. update_design_brief already returns the latest status on write.
            """
            return context._run("get_design_status", {})

        @tool("lookup_engineering_knowledge")
        def lookup_engineering_knowledge(topic: str, query: str) -> dict[str, Any]:
            """Look up source-documented DGB engineering facts (read-only).

            Topics: bearing_model, clearance, material, lubrication, fit.
            Look up manufacturer-specific numbers before quoting them.
            FOUND results contain source, applicability, limitations and review_status.
            All included records are NOT engineering-reviewed; never treat them as
            verified recommendations or use them as automatic user confirmation.
            NOT_FOUND means no match. INSUFFICIENT_EVIDENCE means a relevant
            record exists but does not answer the requested specific value or
            variant. In either case do not invent numeric engineering data.
            """
            return context._run(
                "lookup_engineering_knowledge", {"topic": topic, "query": query}
            )

        return [update_design_brief, get_design_status, lookup_engineering_knowledge]

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
