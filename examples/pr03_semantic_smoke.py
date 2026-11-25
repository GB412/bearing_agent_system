"""Real Chinese embedding smoke test, explicit model download opt-in only.

With a model already cached:
    python examples/pr03_semantic_smoke.py

To explicitly permit downloading weights (requires internet and model license):
    python examples/pr03_semantic_smoke.py --allow-download

This test does NOT use DeepSeek. DummyEncoder unit tests cannot replace it.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from bearing_agent_system.hybrid_knowledge import DEFAULT_MODEL, HybridKnowledge
from bearing_agent_system.knowledge import KnowledgeRepository

PROBES = [
    {
        "query": "轴上那个环会不会转着磨坏轴？",
        "expected_ids": ["ntn-ring-fit-and-creep", "ntn-shaft-housing-fit-principles"],
    },
    {
        "query": "C3的内部游隙比CN大还是小？",
        "expected_ids": ["ntn-clearance-classes", "ntn-clearance-c2-c3"],
    },
    {
        "query": "轴承装上轴以后为什么游隙会发生变化？",
        "expected_ids": ["nsk-fit-affects-clearance", "ntn-clearance-work-vs-initial"],
    },
    {
        "query": "火星探测器的通信协议",
        "expect_no_result": True,
    },
    {
        "query": "如何给蛋糕裱花",
        "expect_no_result": True,
    },
]


def run(model_name: str, allow_download: bool) -> int:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("未安装 sentence-transformers：执行 pip install -e '.[dev,semantic]'")
        return 2
    try:
        encoder = SentenceTransformer(
            model_name,
            device="cpu",
            local_files_only=not allow_download,
        )
    except (OSError, ValueError, TypeError) as exc:
        print("真实中文 Embedding 模型不可用：", type(exc).__name__)
        print("默认不联网下载；只有显式 --allow-download 才允许联网拉取模型。")
        return 2

    repository = KnowledgeRepository()
    hybrid = HybridKnowledge(
        records=list(repository._records),
        encoder=encoder,
        index_path=Path(".bearing_agent/knowledge_vectors_real.json"),
    )
    passed = 0
    for probe in PROBES:
        response = hybrid.search(probe["query"])
        ids = [x["id"] for x in response["results"]]
        relevant = (
            response["status"] == "NOT_FOUND" and not ids
            if probe.get("expect_no_result")
            else response["status"] == "RELATED_EVIDENCE"
            and bool(set(ids) & set(probe["expected_ids"]))
        )
        valid = relevant and response.get("retrieval_method") == "embedding"
        passed += int(valid)
        print(json.dumps({
            "query": probe["query"],
            "status": response["status"],
            "retrieval_method": response.get("retrieval_method"),
            "matches": [
                {"id": x["id"], "score": x.get("relevance")}
                for x in response["results"]
            ],
            "passed": valid,
        }, ensure_ascii=False))
    print(f"Real embedding probes: {passed}/{len(PROBES)} passed")
    return 0 if passed == len(PROBES) else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Real Chinese embedding retrieval smoke test")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--allow-download", action="store_true",
                        help="Explicitly allow model downloads; off by default")
    args = parser.parse_args()
    raise SystemExit(run(args.model, args.allow_download))


if __name__ == "__main__":
    main()
