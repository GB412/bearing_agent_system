"""Read-only RoBAS catalog lookup and optional embedding knowledge retrieval.

Precise engineering values always come from source records; vector similarity
only retrieves potentially relevant explanations, never approves a design.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

CATALOG_TYPES = {
    "material": "materials",
    "lubricant": "lubricants",
    "bearing_model": "bearing_models",
}
DEFAULT_MODEL = "BAAI/bge-small-zh-v1.5"


def _cosine(a: list[float], b: list[float]) -> float:
    numerator = sum(x * y for x, y in zip(a, b, strict=True))
    denominator = math.sqrt(sum(x * x for x in a) * sum(y * y for y in b))
    return numerator / denominator if denominator else 0.0


class HybridKnowledge:
    """One tool backend for structured records and source-backed knowledge."""

    def __init__(
        self,
        *,
        records: list[dict[str, Any]] | None = None,
        catalog_path: str | Path | None = None,
        encoder: Any = None,
        index_path: str | Path | None = None,
    ) -> None:
        if records is None:
            data = json.loads(
                Path(__file__).with_name("knowledge_records.json").read_text("utf-8")
            )
            records = data["records"]
        self.records = records
        self.catalog_path = Path(
            catalog_path or os.getenv("ROBAS_CATALOG_PATH", ".bearing_agent/robas_catalog.json")
        )
        self.index_path = Path(
            index_path or os.getenv("BEARING_KNOWLEDGE_INDEX_PATH",
                                  ".bearing_agent/knowledge_vectors.json")
        )
        self._encoder = encoder
        self._encoder_checked = encoder is not None
        self._vectors: list[list[float]] | None = None

    def search(self, query: str, catalog_query: dict[str, Any] | None = None) -> dict:
        if not isinstance(query, str) or not query.strip() or len(query) > 500:
            return {"ok": False, "status": "INVALID_QUERY", "results": []}
        return self._catalog(catalog_query) if catalog_query is not None else self._concept(query)

    def _catalog(self, request: dict[str, Any]) -> dict:
        if not isinstance(request, dict):
            return {"ok": False, "status": "INVALID_QUERY", "results": []}
        kind, action = request.get("entity_type"), request.get("operation")
        if kind not in CATALOG_TYPES or action not in {"list", "get"}:
            return {"ok": False, "status": "INVALID_QUERY", "results": []}
        if not self.catalog_path.is_file():
            return {
                "ok": True, "status": "CATALOG_UNAVAILABLE", "results": [],
                "message": "本机未安装RoBAS数据目录；不能猜测系统支持项或具体数据库数值。",
            }
        try:
            data = json.loads(self.catalog_path.read_text("utf-8"))
            if data.get("schema_version") != "RoBASCatalog/v1":
                raise ValueError("Unexpected catalog version")
            rows = data[CATALOG_TYPES[kind]]
            if not isinstance(rows, list):
                raise ValueError("Invalid catalog rows")
        except (OSError, KeyError, ValueError, TypeError) as exc:
            return {
                "ok": False, "status": "CATALOG_ERROR", "results": [],
                "message": f"目录读取失败：{type(exc).__name__}",
            }

        if action == "list":
            try:
                offset = int(request.get("offset", 0))
            except (ValueError, TypeError):
                return {"ok": False, "status": "INVALID_QUERY", "results": []}
            if offset < 0:
                return {"ok": False, "status": "INVALID_QUERY", "results": []}
            page = rows[offset:offset + 50]
            return {
                "ok": True, "status": "FOUND" if page else "NOT_FOUND",
                "query_type": "catalog", "entity_type": kind,
                "total": len(rows), "offset": offset,
                "next_offset": offset + len(page) if offset + len(page) < len(rows) else None,
                "results": [{"id": row["id"], "name": row["name"]} for row in page],
            }

        name, field = request.get("name"), request.get("field")
        if not isinstance(name, str) or not name.strip():
            return {"ok": False, "status": "INVALID_QUERY", "results": []}
        hits = [
            row for row in rows
            if name.casefold() in {row["id"].casefold(), row["name"].casefold()}
        ]
        if not hits and kind == "bearing_model":
            # The RoBAS table uses a trailing "*" for some base designations.
            hits = [row for row in rows
                    if row["name"].rstrip(" *").casefold() == name.casefold()]
        if not hits:
            return {"ok": True, "status": "NOT_FOUND",
                    "query_type": "catalog", "results": []}
        if len(hits) > 1:
            return {
                "ok": True, "status": "AMBIGUOUS", "query_type": "catalog",
                "results": [{"id": row["id"], "name": row["name"]} for row in hits],
            }
        row = hits[0]
        if field is not None and (not isinstance(field, str) or field not in row["values_raw"]):
            return {
                "ok": True, "status": "INSUFFICIENT_EVIDENCE",
                "query_type": "catalog", "results": [],
                "available_fields": list(row["values_raw"]),
            }
        source = next((source for source in data.get("sources", [])
                       if source["id"] == CATALOG_TYPES[kind]), None)
        return {
            "ok": True, "status": "FOUND", "query_type": "catalog",
            "results": [{
                "id": row["id"], "name": row["name"],
                "values_raw": row["values_raw"] if field is None
                              else {field: row["values_raw"][field]},
                "source_fields": row["source_fields"] if field is None
                                 else {field: row["source_fields"][field]},
                "source": source, "data_status": row["data_status"],
                "source_row": row.get("source_row"), "source_pk": row.get("source_pk"),
            }],
            "message": (
                "按RoBAS原表原样读取，不修改数值。目录存在不等于设计适用；"
                "C、C0、nmax原表单位未独立核对，不应自行转换。"
            ),
        }

    def _load_encoder(self) -> Any:
        if not self._encoder_checked:
            self._encoder_checked = True
            try:
                from sentence_transformers import SentenceTransformer

                model = os.getenv("BEARING_KNOWLEDGE_EMBEDDING_MODEL", DEFAULT_MODEL)
                self._encoder = SentenceTransformer(
                    model, device="cpu", local_files_only=True
                )
            except (ImportError, OSError, ValueError, TypeError):
                self._encoder = None
        return self._encoder

    def _documents(self) -> list[str]:
        return [
            record.get("title", "") + "。" + record.get(
                "content", record["summary"]
            )
            for record in self.records
        ]

    def _index(self) -> list[list[float]]:
        if self._vectors is not None:
            return self._vectors
        documents = self._documents()
        checksum = hashlib.sha256(
            json.dumps(documents, ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        model = os.getenv("BEARING_KNOWLEDGE_EMBEDDING_MODEL", DEFAULT_MODEL)
        if self.index_path.is_file():
            try:
                cached = json.loads(self.index_path.read_text("utf-8"))
                if cached["content_sha256"] == checksum and cached["model"] == model:
                    self._vectors = cached["vectors"]
                    return self._vectors
            except (OSError, ValueError, TypeError, KeyError):
                pass
        encoder = self._load_encoder()
        if encoder is None:
            return []
        self._vectors = [
            list(map(float, row)) for row in encoder.encode(documents)
        ]
        try:
            self.index_path.parent.mkdir(parents=True, exist_ok=True)
            self.index_path.write_text(
                json.dumps({
                    "model": model, "content_sha256": checksum,
                    "vectors": self._vectors,
                }), encoding="utf-8"
            )
        except OSError:
            pass
        return self._vectors

    @staticmethod
    def _keyword_support(query: str, document: str) -> bool:
        """Lexical fallback cannot pretend to infer Chinese paraphrases.

        Require a meaningful explicit domain token (or model designation).
        Unrelated questions must not receive whichever three records happen
        to be ranked highest by a string-distance algorithm.
        """
        import re

        stop = {"轴承", "工作", "情况", "条件", "怎么", "什么", "是多少"}
        tokens = re.findall(r"[A-Za-z]+\d*|\d{4,}|[\u4e00-\u9fff]{2,4}", query)
        document_lower = document.casefold()
        return any(
            token.casefold() in document_lower
            for token in tokens if token not in stop and len(token) > 1
        )

    def _concept(self, query: str) -> dict:
        if not self.records:
            return {"ok": True, "status": "NOT_FOUND", "results": [],
                    "query_type": "concept"}
        vectors = self._index()
        encoder = self._load_encoder()
        if vectors and encoder is not None and len(vectors) == len(self.records):
            question = list(map(float, encoder.encode([query])[0]))
            scores = [_cosine(question, row) for row in vectors]
            method = "embedding"
            # Conservative provisional cutoff. Real Chinese model acceptance must
            # calibrate this value on paraphrase/negative test queries.
            threshold = 0.60
        else:
            documents = self._documents()
            scores = [
                max(0.22, SequenceMatcher(None, query.casefold(),
                                               document.casefold()).ratio())
                if self._keyword_support(query, document) else 0.0
                for document in documents
            ]
            method = "lexical_fallback"
            threshold = 0.12
        indices = [
            i for i in sorted(range(len(self.records)),
                              key=lambda i: scores[i], reverse=True)
            if math.isfinite(scores[i]) and scores[i] >= threshold
        ][:3]
        if not indices:
            return {
                "ok": True, "status": "NOT_FOUND", "query_type": "concept",
                "retrieval_method": method, "results": [],
                "message": (
                    "检索相关度不足，没有可靠匹配。"
                    "当前方法可能漏掉同义改写；不能依据无关记录编造工程数值。"
                ),
            }
        return {
            "ok": True, "status": "RELATED_EVIDENCE", "query_type": "concept",
            "retrieval_method": method,
            "results": [
                {**self.records[i], "relevance": round(scores[i], 4)}
                for i in indices
            ],
            "message": (
                "检索命中只表示可能相关，不代表所问答案已经有充分证据"
                "或已通过工程审核。缺少资料中的具体数值时应明确说明。"
            ),
        }
