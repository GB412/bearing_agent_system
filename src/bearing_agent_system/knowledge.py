"""Small, read-only, source-documented DGB engineering knowledge lookup.

This is deliberately a conservative catalog, not fuzzy retrieval, a recommender
or an engineering-approval mechanism. A relevant source is not automatically
sufficient to answer a request for an unsupported numerical engineering value.
"""

from __future__ import annotations

import json
import math
import re
from copy import deepcopy
from importlib.resources import files
from typing import Any
from urllib.parse import urlparse

TOPICS = ("bearing_model", "clearance", "material", "lubrication", "fit")
UNREVIEWED = "SOURCE_DOCUMENTED_NOT_ENGINEERING_REVIEWED"

# Narrow denial checks for *specific values* absent from this four-record
# catalog. Conceptual questions continue to use source-backed summaries.
UNSUPPORTED_VALUE_REQUESTS = {
    "bearing_model": re.compile(
        r"寿命|动载荷|静载荷|额定载荷|额定转速|极限转速|极限速度|"
        r"钢球.*(?:直径|数量|节圆)|沟曲率|保持架材料|公差|热膨胀|"
        r"load rating|rated life|speed limit", re.I
    ),
    "clearance": re.compile(
        r"具体.*(?:数值|范围|区间|大小|是多少)|(?:数值|数值范围|"
        r"微米|\\bum\\b|μm|µm|公差表|上下限|最大.*最小|"
        r"多少.*(?:mm|毫米|微米)|\\d+\\s*(?:mm|µm|μm))",
        re.I
    ),
    "fit": re.compile(
        r"\\b[HhKk]\\d+\\b|公差值|公差表|具体公差|"
        r"多少微米|配合量|过盈量|\\bIT\\d+\\b", re.I
    ),
    "lubrication": re.compile(
        r"黏度|粘度|牌号|补脂周期|寿命|转速极限|\\bcSt\\b|"
        r"\\bISO\\s*VG\\b|具体.*(?:温度|油脂|参数)", re.I
    ),
}
# 6206-2RS, 6206-ZZ etc. are not this catalog's exact SKF 6206 record.
VARIANT = re.compile(r"(?<![A-Za-z0-9])6206[-/](?:[A-Za-z0-9]+)", re.I)


def _has_term(query: str, term: str) -> bool:
    """Avoid matching 6206 in 62060 or C3 in C30; Chinese tokens remain substrings."""
    escaped = re.escape(term)
    left = r"(?<![A-Za-z0-9])" if term[0].isascii() and term[0].isalnum() else ""
    right = r"(?![A-Za-z0-9])" if term[-1].isascii() and term[-1].isalnum() else ""
    return re.search(left + escaped + right, query, flags=re.I) is not None


def _validate_catalog(payload: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    if payload.get("schema_version") != "EngineeringKnowledge/v1":
        raise ValueError("Unsupported engineering knowledge catalog version")
    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError("Knowledge records must be a list")
    seen: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Knowledge record must be a mapping")
        identity = record.get("id")
        if not isinstance(identity, str) or not identity or identity in seen:
            raise ValueError("Knowledge record must have a unique nonempty ID")
        seen.add(identity)
        if record.get("topic") not in TOPICS:
            raise ValueError(f"Unknown knowledge topic: {identity}")
        if record.get("review_status") != UNREVIEWED:
            raise ValueError("Catalog may not assert unverified engineering approval")
        for field in ("summary", "applicability"):
            if not isinstance(record.get(field), str) or not record[field].strip():
                raise ValueError(f"Knowledge record {identity} lacks {field}")
        if not isinstance(record.get("limitations"), list) or not record["limitations"]:
            raise ValueError(f"Knowledge record {identity} must state limitations")
        terms = record.get("match_terms")
        if not isinstance(terms, list) or not terms or not all(
            isinstance(t, str) and t.strip() for t in terms
        ):
            raise ValueError(f"Knowledge record {identity} must have match terms")
        source = record.get("source")
        if not isinstance(source, dict) or not all(
            isinstance(source.get(x), str) and source[x].strip()
            for x in ("publisher", "title", "url")
        ):
            raise ValueError(f"Knowledge record {identity} needs a named source")
        url = urlparse(source["url"])
        if url.scheme != "https" or not url.hostname:
            raise ValueError(f"Knowledge record {identity} needs an HTTPS source URL")
        facts = record.get("facts")
        if not isinstance(facts, list) or not facts:
            raise ValueError(f"Knowledge record {identity} has no facts")
        for fact in facts:
            if not isinstance(fact, dict) or not isinstance(fact.get("field"), str):
                raise ValueError(f"Knowledge record {identity} has invalid fact")
            value = fact.get("value")
            if value is None or isinstance(value, bool) or not isinstance(
                value, (int, float, str)
            ):
                raise ValueError(f"Knowledge record {identity} has invalid value")
            if isinstance(value, (int, float)) and (
                not math.isfinite(value) or not fact.get("unit")
            ):
                raise ValueError("Numerical engineering facts require finite values and units")
    return tuple(records)


class KnowledgeRepository:
    """Lookup the packaged catalog, preserving evidence and explicit limits."""

    def __init__(self) -> None:
        resource = files("bearing_agent_system").joinpath("knowledge_records.json")
        payload = json.loads(resource.read_text(encoding="utf-8"))
        self._records = _validate_catalog(payload)

    def lookup(self, topic: str, query: str) -> dict[str, Any]:
        if topic not in TOPICS:
            return {
                "ok": False, "status": "INVALID_TOPIC",
                "supported_topics": list(TOPICS), "results": [],
            }
        if not isinstance(query, str) or not query.strip() or len(query) > 500:
            return {"ok": False, "status": "INVALID_QUERY", "results": []}

        query = query.strip()
        matches = [
            record for record in self._records
            if record["topic"] == topic
            and any(_has_term(query, term) for term in record["match_terms"])
        ]
        if not matches:
            return {
                "ok": True, "status": "NOT_FOUND", "topic": topic, "results": [],
                "message": "本地暂无匹配且可追溯的工程数据；不要猜测数值或适用性。",
            }

        unsupported = (
            topic == "bearing_model" and VARIANT.search(query) is not None
        ) or (
            topic in UNSUPPORTED_VALUE_REQUESTS
            and UNSUPPORTED_VALUE_REQUESTS[topic].search(query) is not None
        )
        if unsupported:
            # Related sources can support general explanations, NOT the requested
            # specific numeric engineering value; avoid returning unrelated
            # numeric facts as a superficially successful answer.
            return {
                "ok": True, "status": "INSUFFICIENT_EVIDENCE", "topic": topic,
                "results": [],
                "related_sources": [
                    {
                        "id": record["id"],
                        "summary": record["summary"],
                        "source": record["source"],
                        "limitations": record["limitations"],
                        "review_status": record["review_status"],
                    }
                    for record in matches
                ],
                "message": (
                    "找到相关背景资料，但目录没有足够证据回答此次请求的具体数值、"
                    "公差、变体或适用结论。不得编造该数据或视为已通过工程审核。"
                ),
            }
        return {
            "ok": True, "status": "FOUND", "topic": topic,
            "results": deepcopy(matches),
            "message": (
                "这些是带出处的资料摘要，尚未经工程人员审核。"
                "只可引用实际提供的事实，不得推出未包含的标准数值、选型结论或校核结果。"
            ),
        }
