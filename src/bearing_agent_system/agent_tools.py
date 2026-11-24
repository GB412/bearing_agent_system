"""Bounded agent tools; brief writes and engineering knowledge remain separate."""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from typing import Any

from langchain_core.tools import BaseTool, tool
from pydantic import ValidationError

from .brief_service import DesignBriefService
from .knowledge import KnowledgeRepository
from .models import TrustedContext, UpdateBatch
from .parameter_catalog import FIELDS, InvalidChange


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

    @staticmethod
    def _authorize_recommendation(message: str, evidence: str, *, delegated: bool,
                                 paths: list[str]) -> None:
        """Small independent authorization guard; LLM handles intent nuances."""
        if not evidence or evidence not in message:
            raise InvalidChange("Approval evidence is not in the current user message")
        if re.search(r"如果|假如|比如|先不|暂不|不要|不采纳|不采用|不接受|不按|"
                     r"仅了解|只是问|[?？]", message):
            raise InvalidChange("Question, hypothetical or refusal cannot authorize adoption")
        if delegated:
            if not (re.search(r"你来|帮我|替我|交给你|由你", evidence)
                    and re.search(r"决定|确定|指定|选(?:择|定)?|推荐", evidence)):
                raise InvalidChange("User did not explicitly delegate selection")
            scopes = {
                "engineering.fits.": ("配合", "公差"),
                "engineering.clearance.": ("游隙",),
                "engineering.materials.": ("材料",),
                "engineering.cage.": ("保持架",),
                "engineering.lubrication.": ("润滑",),
            }
            for path in paths:
                if not any(
                    path.startswith(prefix) and any(term in evidence for term in terms)
                    for prefix, terms in scopes.items()
                ):
                    raise InvalidChange("Delegated scope does not cover " + path)
        elif not (
            re.search(r"按你|按推荐|照你|采纳|同意|采用|接受|就按|就用|就这样|"
                      r"就这个|确认采用|确认使用|可以|确定采用", evidence)
            or message.strip() in {"好", "好的", "行", "可以", "同意", "确认", "就这样"}
        ):
            raise InvalidChange("User has not approved the pending recommendation")

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
                result = self.knowledge.search(
                    args.get("query", ""), args.get("catalog_query")
                )
            else:
                try:
                    operation = args.get("operation")
                    if operation == "propose":
                        proposals = args.get("changes", [])
                        topics = {
                            "engineering.fits.": "fit",
                            "engineering.clearance.": "clearance",
                            "engineering.materials.": "material",
                            "engineering.cage.": "cage",
                            "engineering.lubrication.": "lubrication",
                        }
                        requested_topics = {
                            topic for entry in proposals if isinstance(entry, dict)
                            for prefix, topic in topics.items()
                            if str(entry.get("path", "")).startswith(prefix)
                        }
                        known_topics = {
                            record["id"]: record["topic"]
                            for record in getattr(self.knowledge, "_records", [])
                        }
                        sources = list(dict.fromkeys(
                            record_id for trace in self.trace
                            if trace["name"] == "lookup_engineering_knowledge"
                            and trace.get("knowledge_status") == "RELATED_EVIDENCE"
                            for record_id in trace.get("knowledge_ids", [])
                            if known_topics.get(record_id) in requested_topics
                        ))
                        result = {
                            "ok": True,
                            **self.service.store.propose_recommendation(
                                self.session_id, proposals, self.message_id, sources,
                            ),
                        }
                    elif operation in ("accept", "delegate"):
                        current = self.service.store.pending_recommendation(self.session_id)
                        target_id = args.get("proposal_id") or (
                            current["proposal_id"] if current else None
                        )
                        if not current or current["proposal_id"] != target_id:
                            raise InvalidChange("No matching pending recommendation")
                        delegated = operation == "delegate"
                        self._authorize_recommendation(
                            self.user_message, args.get("approval_evidence_span") or "",
                            delegated=delegated,
                            paths=[x["path"] for x in current["changes"]],
                        )
                        if not delegated and current["created_turn_id"] == self.message_id:
                            raise InvalidChange("New proposal requires a later user approval")
                        if delegated:
                            topic_by_id = {
                                record["id"]: record["topic"]
                                for record in getattr(self.knowledge, "_records", [])
                            }
                            topics = {
                                "engineering.fits.": "fit",
                                "engineering.clearance.": "clearance",
                                "engineering.materials.": "material",
                                "engineering.cage.": "cage",
                                "engineering.lubrication.": "lubrication",
                            }
                            for entry in current["changes"]:
                                topic = next((
                                    t for prefix, t in topics.items()
                                    if entry["path"].startswith(prefix)
                                ), None)
                                if topic not in {
                                    topic_by_id.get(record_id)
                                    for record_id in current["knowledge_ids"]
                                }:
                                    raise InvalidChange(
                                        "No relevant knowledge lookup for delegated "
                                        + entry["path"]
                                    )
                        outcome = self.service.store.adopt_recommendation(
                            self.session_id, target_id,
                            TrustedContext(
                                kind="user", message_id=self.message_id,
                                user_message=self.user_message,
                            ), delegated=delegated,
                        )
                        result = {
                            "ok": not outcome.rejected_changes,
                            **outcome.model_dump(mode="json"),
                            "proposal_id": target_id,
                            "decision_method": (
                                "agent_delegated" if delegated else "user_accepted"
                            ),
                        }
                    else:
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
                    item["source"]["url"]
                    for item in (result.get("results", []) + result.get("related_sources", []))
                    if (item.get("source") or {}).get("url")
                ] if name == "lookup_engineering_knowledge" else [],
                "knowledge_query_type": result.get("query_type")
                if name == "lookup_engineering_knowledge" else None,
                "retrieval_method": (
                    result.get("retrieval_method") or
                    ("exact" if result.get("query_type") == "catalog" else None)
                ) if name == "lookup_engineering_knowledge" else None,
                "proposal_id": result.get("proposal_id"),
            "decision_method": result.get("decision_method"),
            "knowledge_provenance": [
                    {
                        "record_id": item.get("id"),
                        "source_type": (
                            "robas_catalog" if result.get("query_type") == "catalog"
                            else (item.get("source") or {}).get("source_type", "manufacturer")
                        ),
                        "source_id": (
                            item.get("source") or result.get("catalog_source") or {}
                        ).get("id"),
                        "source_hash": (
                            item.get("source") or result.get("catalog_source") or {}
                        ).get("sha256"),
                        "source_url": (item.get("source") or {}).get("url"),
                        "source_field": list(item.get("source_fields", {})),
                        "source_row": item.get("source_row"),
                        "source_pk": item.get("source_pk"),
                    }
                    for item in (result.get("results", []) + result.get("related_sources", []))
                ] if name == "lookup_engineering_knowledge" else [],
            })
            return result

    def tools(self) -> list[BaseTool]:
        """Tools capture a trusted turn; the model sees neither identity nor source."""
        context = self

        @tool("update_design_brief")
        def update_design_brief(
            operation: str,
            changes: list[dict[str, Any]] | None = None,
            proposal_id: str | None = None,
            approval_evidence_span: str | None = None,
        ) -> dict[str, Any]:
            """Save/replace user-provided DGB values, requirements, and optimizer slots.

            Only cite exact text within the current user message in evidence_span.
            Each change has path, value, evidence_span, and optionally unit,
            precision and target_id. For requirement edits use replace with target_id.
            Model may not set session_id, message_id, source, or confirmed.
            operation=set/replace: changes need current-user evidence_span.
            operation=propose: changes contain only engineering path/value choices;
            stores one pending unverified recommendation, not a confirmed fact.
            operation=accept: use proposal_id and approval_evidence_span from this
            user turn to adopt the existing stored recommendation (no repeated values).
            operation=delegate: after a relevant knowledge lookup and propose in
            the same user turn, requires explicit delegation scope/evidence;
            stores provisional choices as unreviewed. Never guess engineering facts.
            This tool returns an authoritative write/proposal result.
            """
            return context._run(
                "update_design_brief", {
                    "operation": operation, "changes": changes or [],
                    "proposal_id": proposal_id,
                    "approval_evidence_span": approval_evidence_span,
                }
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
            "\npropose 示例：operation=propose，changes=[{\"path\":"
            "\"engineering.fits.inner_ring\",\"value\":\"k6\"}]；"
            "产生待采纳记录（仅推荐，不写 DesignBrief）。"
            "\naccept 示例：operation=accept，proposal_id=此前工具返回的ID，"
            "approval_evidence_span=当前用户说的\"按你推荐的来\"，changes=[]；"
            "程序从SQLite取值，禁止重造、重复当前用户没有说过的数值。"
            "\ndelegate 示例：在用户明确委托某字段决策后，先针对该领域调用知识工具，"
            "再 propose，最后用 operation=delegate 和当轮原文授权片段采纳；"
            "没有相关证据或条件不足时只推荐/说明，不调用 delegate。"
            "\n以上 evidence_span 仅是示例；真实调用必须引用当前用户消息的原文。"
        )

        @tool("get_design_status")
        def get_design_status() -> dict[str, Any]:
            """Read saved DGB values, requirement IDs, missing/pending/conflicting fields.

            Read-only. update_design_brief already returns the latest status on write.
            """
            return context._run("get_design_status", {})

        @tool("lookup_engineering_knowledge")
        def lookup_engineering_knowledge(
            query: str, catalog_query: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            """Read-only engineering knowledge and RoBAS source catalog.

            For concepts: pass query only; retrieval may decline low-relevance hits.
            For RoBAS data: pass catalog_query with entity_type
            (material/lubricant/bearing_model), operation (list/get), optional
            name and field. Exact catalog values come from installed source
            files; absence is not evidence that a product is unsupported.
            Evidence is never an automatic user parameter confirmation.
            """
            return context._run(
                "lookup_engineering_knowledge", {"query": query, "catalog_query": catalog_query}
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
