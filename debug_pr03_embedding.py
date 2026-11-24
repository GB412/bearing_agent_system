from sentence_transformers import SentenceTransformer

from bearing_agent_system.hybrid_knowledge import _cosine
from bearing_agent_system.knowledge import KnowledgeRepository

model = SentenceTransformer(
    "BAAI/bge-small-zh-v1.5",
    local_files_only=True
)

records = list(KnowledgeRepository()._records)

docs = [
    r.get("title", "") + "。" + r.get("content", r["summary"])
    for r in records
]

vectors = model.encode(docs)

queries = [
    "轴上那个环会不会转着磨坏轴？",
    "轴承内圈配合与蠕动问题",
    "火星探测器的通信协议",
    "如何给蛋糕裱花",
]

# 确认 Python 接收到的中文没有损坏
assert "轴上那个环" in queries[0]

for query in queries:
    qvec = model.encode([query])[0]

    scores = sorted(
        [
            (_cosine(list(qvec), list(vec)), r["id"])
            for vec, r in zip(vectors, records, strict=True)
        ],
        reverse=True,
    )

    print("\n问题：", query)
    for score, name in scores[:5]:
        print(f"  {score:.4f}  {name}")
