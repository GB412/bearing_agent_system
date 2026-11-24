"""PR-03 hybrid knowledge coverage: data identity, source integrity, and semantic retrieval."""
from __future__ import annotations

import json
from pathlib import Path

from bearing_agent_system import DesignBriefService, SQLiteDesignBriefStore
from bearing_agent_system.agent_tools import TurnTools
from bearing_agent_system.hybrid_knowledge import HybridKnowledge
from bearing_agent_system.knowledge import KnowledgeRepository


class DummyEncoder:
    def encode(self, sentences):
        if isinstance(sentences, str):
            sentences = [sentences]
        return [
            [1.0, 0.0] if ("配合" in sentence or "打滑" in sentence)
            else [0.0, 1.0]
            for sentence in sentences
        ]


def fixture(tmp_path: Path) -> Path:
    target = tmp_path / "catalog.json"
    target.write_text(json.dumps({
        "schema_version": "RoBASCatalog/v1",
        "sources": [{"id": "materials", "sha256": "test-sha"},
                    {"id": "lubricants", "sha256": "test-sha2"},
                    {"id": "bearing_models", "sha256": "test-sha3"}],
        "materials": [
            {"id": "material:高碳铬轴承钢", "name": "高碳铬轴承钢",
             "values_raw": {"poisson_ratio": "3.60E-07"},
             "source_fields": {"poisson_ratio": "poisson"},
             "source_row": 2, "data_status": "SOURCE_AS_IS"}
        ],
        "lubricants": [
            {"id": "lubricant:VG32", "name": "VG32",
             "values_raw": {"v1_m2_s": "3.20E-05"},
             "source_fields": {"v1_m2_s": "v1(m^2/s)"},
             "source_row": 7, "data_status": "SOURCE_AS_IS"}
        ],
        "bearing_models": [
            {"id": "T_SKFA01:100", "name": "6206 *",
             "values_raw": {"C0_source": 11.2},
             "source_fields": {"C0_source": "C0"},
             "source_pk": 100, "data_status": "SOURCE_AS_IS"}
        ],
    }, ensure_ascii=False), encoding="utf-8")
    return target


def test_catalog_does_not_adjust_original_physical_values(tmp_path):
    repository = HybridKnowledge(records=[], catalog_path=fixture(tmp_path))
    answer = repository.search(
        "原始泊松比", {"entity_type": "material", "operation": "get",
                       "name": "高碳铬轴承钢", "field": "poisson_ratio"}
    )
    assert answer["status"] == "FOUND"
    assert answer["results"][0]["values_raw"]["poisson_ratio"] == "3.60E-07"
    assert answer["results"][0]["source"]["sha256"] == "test-sha"
    assert repository.search(
        "支持材料", {"entity_type": "material", "operation": "list"}
    )["total"] == 1


def test_exact_model_lookup_and_no_fuzzy_suffix(tmp_path):
    repository = HybridKnowledge(records=[], catalog_path=fixture(tmp_path))
    expected = {"entity_type": "bearing_model", "operation": "get",
                "name": "6206", "field": "C0_source"}
    assert repository.search("6206", expected)["results"][0]["values_raw"]["C0_source"] == 11.2
    for wrong in ("62060", "16206", "6206-2RS"):
        assert repository.search("型号", {**expected, "name": wrong})["status"] == "NOT_FOUND"
    assert repository.search(
        "润滑剂", {"entity_type": "lubricant", "operation": "list"}
    )["results"][0]["name"] == "VG32"


def test_semantic_encoder_finds_fit_even_without_fit_keyword(tmp_path):
    records = [
        {"id": "fit-a", "title": "套圈配合与防蠕动", "summary": "内圈打滑防蠕动",
         "content": "轴承内圈与轴的配合。"},
        {"id": "lube-b", "title": "润滑剂选择", "summary": "润滑油与润滑脂",
         "content": "润滑油和润滑脂的选择。"},
    ]
    repository = HybridKnowledge(
        records=records, encoder=DummyEncoder(), catalog_path=fixture(tmp_path),
        index_path=tmp_path / "vectors.json"
    )
    result = repository.search("内圈会不会打滑？")
    assert result["status"] == "RELATED_EVIDENCE"
    assert result["retrieval_method"] == "embedding"
    assert result["results"][0]["id"] == "fit-a"


def test_missing_catalog_returns_unavailable_not_hallucinated(tmp_path):
    repository = HybridKnowledge(records=[], catalog_path=tmp_path / "not-found.json")
    assert repository.search(
        "支持哪些材料？", {"entity_type": "material", "operation": "list"}
    )["status"] == "CATALOG_UNAVAILABLE"


def test_original_knowledge_repository_remains_read_only():
    repository = KnowledgeRepository()
    result = repository.search("C3和普通游隙的关系")
    assert result["status"] == "RELATED_EVIDENCE"
    assert result["query_type"] == "concept"
    assert any("source" in record for record in result["results"])


def test_irrelevant_concept_does_not_return_top_three_without_relevance(tmp_path):
    repo = HybridKnowledge(
        records=list(KnowledgeRepository()._records),
        catalog_path=tmp_path / "absent.json",
        index_path=tmp_path / "absent-vectors.json",
    )
    repo._encoder_checked = True  # Force documented lexical fallback.
    outcome = repo.search("火星探测器的通信协议是什么？")
    assert outcome["status"] == "NOT_FOUND"
    assert outcome["results"] == []
    assert outcome["retrieval_method"] == "lexical_fallback"


def test_lexical_fallback_is_labelled_and_does_not_pretend_semantics(tmp_path):
    repo = HybridKnowledge(
        records=list(KnowledgeRepository()._records),
        catalog_path=tmp_path / "absent.json",
        index_path=tmp_path / "absent-vectors.json",
    )
    repo._encoder_checked = True
    answer = repo.search("C3和CN游隙有何区别")
    assert answer["status"] == "RELATED_EVIDENCE"
    assert answer["retrieval_method"] == "lexical_fallback"


class ZeroEncoder:
    def encode(self, sentences):
        return [[0.0, 0.0] for _ in sentences]


def test_embedding_with_no_relevant_vector_returns_not_found(tmp_path):
    repo = HybridKnowledge(
        records=[{"id": "a", "title": "套圈", "summary": "轴承配合"}],
        encoder=ZeroEncoder(), index_path=tmp_path / "embedding.json",
    )
    result = repo.search("无关问题")
    assert result["retrieval_method"] == "embedding"
    assert result["status"] == "NOT_FOUND"
    assert result["results"] == []


def test_robas_query_trace_preserves_source_hash_field_and_row(tmp_path):
    repository = KnowledgeRepository()
    repository._hybrid = HybridKnowledge(
        records=[], catalog_path=fixture(tmp_path),
        index_path=tmp_path / "vectors.json",
    )
    service = DesignBriefService(SQLiteDesignBriefStore(tmp_path / "brief.sqlite"))
    tools = TurnTools(
        service=service, session_id="s",
        message_id="m", user_message="查6206原始C0",
        knowledge=repository,
    )
    before = service.get_brief("s")
    exposed = tools.tools()[2]
    assert "topic" not in exposed.args_schema.model_json_schema()["properties"]
    result = exposed.invoke({
        "query": "查6206原始C0",
        "catalog_query": {
            "entity_type": "bearing_model", "operation": "get",
            "name": "6206", "field": "C0_source",
        },
    })
    assert result["status"] == "FOUND"
    receipt = tools.trace[-1]
    assert receipt["knowledge_query_type"] == "catalog"
    assert receipt["retrieval_method"] == "exact"
    assert receipt["knowledge_source_urls"] == []
    assert receipt["knowledge_ids"] == ["T_SKFA01:100"]
    assert receipt["knowledge_provenance"] == [{
        "record_id": "T_SKFA01:100",
        "source_type": "robas_catalog",
        "source_id": "bearing_models",
        "source_hash": "test-sha3",
        "source_url": None,
        "source_field": ["C0_source"],
        "source_row": None,
        "source_pk": 100,
    }]
    assert service.get_brief("s") == before
