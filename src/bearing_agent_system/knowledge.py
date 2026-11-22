"""Small, read-only, source-documented DGB knowledge lookup.

This is not a recommender, an engineering approval workflow, or a RoBAS
material/lubricant database adapter. No remote network calls are made.
"""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

TOPICS = ("bearing_model", "clearance", "material", "lubrication", "fit")
UNREVIEWED = "SOURCE_DOCUMENTED_NOT_ENGINEERING_REVIEWED"


class KnowledgeRepository:
    """Lookup a tiny checked-in catalog; return source and applicability."""

    def __init__(self) -> None:
        resource = files("bearing_agent_system").joinpath("knowledge_records.json")
        payload = json.loads(resource.read_text(encoding="utf-8"))
        if payload.get("schema_version") != "EngineeringKnowledge/v1":
            raise ValueError("Unsupported engineering knowledge catalog version")
        self._records: tuple[dict[str, Any], ...] = tuple(payload["records"])

    def lookup(self, topic: str, query: str) -> dict[str, Any]:
        if topic not in TOPICS:
            return {
                "ok": False,
                "status": "INVALID_TOPIC",
                "supported_topics": list(TOPICS),
                "results": [],
            }
        if not isinstance(query, str) or not query.strip() or len(query) > 500:
            return {"ok": False, "status": "INVALID_QUERY", "results": []}

        needle = query.casefold()
        matches = [
            record for record in self._records
            if record["topic"] == topic
            and any(term.casefold() in needle for term in record["match_terms"])
        ]
        if not matches:
            return {
                "ok": True,
                "status": "NOT_FOUND",
                "topic": topic,
                "results": [],
                "message": "本地暂无匹配且可追溯的工程数据；不要猜测数值或适用性。",
            }
        return {
            "ok": True,
            "status": "FOUND",
            "topic": topic,
            "results": matches,
            "message": (
                "这些是带出处的资料摘要，尚未经工程人员审核。"
                "只可引用实际提供的事实，不得推出未包含的标准数值、选型结论或校核结果。"
            ),
        }
