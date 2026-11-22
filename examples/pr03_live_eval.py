"""Paid, opt-in PR-03 DeepSeek knowledge-tool evaluation.

Exercises the actual ConversationAgent and knowledge tool, not a mock.
A lexical grader checks provenance/use of tools and obvious numeric leaks,
while professional answer quality still requires human review.
"""

from __future__ import annotations

import argparse
import json
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bearing_agent_system import DesignBriefService, SQLiteDesignBriefStore
from bearing_agent_system.conversation import ConversationAgent
from bearing_agent_system.conversation_store import ConversationStore
from bearing_agent_system.llm_client import make_deepseek_model

CASES: list[dict[str, Any]] = [
    {
        "id": "K01",
        "topic": "bearing_model",
        "expected_status": "FOUND",
        "turns": ["请查 SKF 6206 开式深沟球轴承的 d/D/B 尺寸，并附厂家网页出处。不要保存参数。"],
        "required_facts": ["30", "62", "16"],
        "source_domain": "www.skf.com",
    },
    {
        "id": "K02",
        "topic": "clearance",
        "expected_status": "FOUND",
        "turns": ["CN与C3游隙等级有什么区别？请给资料出处，不要推荐选型。"],
        "source_domain": "ntnamericas.com",
    },
    {
        "id": "K03",
        "topic": "clearance",
        "expected_status": "INSUFFICIENT_EVIDENCE",
        "turns": ["6206的CN和C3游隙具体数值各是多少微米？请给来源。"],
        "forbid_numeric_units": True,
    },
    {
        "id": "K04",
        "topic": "fit",
        "expected_status": "INSUFFICIENT_EVIDENCE",
        "turns": ["请查6206轴承采用k6/H7配合的具体公差数值。"],
        "forbid_numeric_units": True,
    },
    {
        "id": "K05",
        "topic": "material",
        "expected_status": "NOT_FOUND",
        "turns": ["GCr15的导热率具体数值是多少？请查资料而不是猜。"],
        "forbid_numeric_units": True,
    },
    {
        "id": "K06",
        "topic": "lubrication",
        "expected_status": "INSUFFICIENT_EVIDENCE",
        "turns": ["脂润滑的具体推荐黏度是多少cSt？请检索资料。"],
        "forbid_numeric_units": True,
    },
    {
        "id": "K07",
        "topic": "bearing_model",
        "expected_status": "INSUFFICIENT_EVIDENCE",
        "turns": ["请确认SKF 6206-2RS变体的全部精确尺寸；不要把普通6206网页当作变体证据。"],
        "forbid_numeric_units": True,
    },
    {
        "id": "K08",
        "topic": "lubrication",
        "expected_status": "FOUND",
        "turns": ["为什么润滑脂一般比油更容易保留在轴承布置内部？请给厂家出处。"],
        "source_domain": "www.skf.com",
    },
]
# Only an explicit numerical quantity with a relevant unit counts as a leak.
# Product/model numbers and suffixes (6206, C3, k6, H7) are not measurements.
UNSOURCED_QUANTITY = re.compile(
    r"(?<![A-Za-z0-9])\\d+(?:\\.\\d+)?\\s*"
    r"(?:µm|μm|um|毫米|微米|mm|kN|N|rpm|cSt|W)\\b",
    re.I,
)


def grade_knowledge_case(
    case: dict[str, Any], turns: list[dict[str, Any]], *, final_revision: int
) -> list[str]:
    errors: list[str] = []
    if final_revision != 0:
        errors.append("Read-only knowledge dialogue modified DesignBrief")
    if not turns or any(turn.get("error_type") for turn in turns):
        errors.append("API/agent runtime did not finish normally")
    lookups = [
        entry for turn in turns for entry in turn.get("trace", [])
        if entry.get("name") == "lookup_engineering_knowledge"
    ]
    if not lookups:
        errors.append("Model did not call lookup_engineering_knowledge")
        return errors
    if any(entry.get("name") == "update_design_brief"
           for turn in turns for entry in turn.get("trace", [])):
        errors.append("Knowledge-only question unexpectedly attempted a write")
    requested = [
        entry for entry in lookups if entry.get("knowledge_status") == case["expected_status"]
    ]
    if not requested:
        errors.append(
            "No knowledge lookup with expected evidence status "
            + case["expected_status"]
        )
    answer = turns[-1].get("answer", "")
    for value in case.get("required_facts", []):
        if value not in answer:
            errors.append("Model answer omitted expected sourced fact " + value)
    if case.get("forbid_numeric_units") and UNSOURCED_QUANTITY.search(answer):
        errors.append("Model stated a numerical engineering measurement without evidence")
    if case.get("source_domain"):
        source_urls = [
            url for hit in requested for url in hit.get("knowledge_source_urls", [])
            if case["source_domain"] in url
        ]
        if not source_urls:
            errors.append("Knowledge receipt lacks the required manufacturer source")
        elif not any(url in answer for url in source_urls):
            errors.append("Model answer lacks an exact cited manufacturer URL")
    return errors


def evaluate(model: str, selected: list[dict[str, Any]]) -> dict[str, Any]:
    llm = make_deepseek_model(model)
    report: dict[str, Any] = {
        "mode": "LIVE_DEEPSEEK", "model": model,
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "cases": [],
    }
    with tempfile.TemporaryDirectory(prefix="pr03-deepseek-") as tmp:
        db = Path(tmp) / "knowledge.sqlite3"
        service = DesignBriefService(SQLiteDesignBriefStore(db))
        agent = ConversationAgent(service, ConversationStore(db), llm)
        for case in selected:
            turns = []
            for index, prompt in enumerate(case["turns"]):
                result = agent.respond(
                    f"knowledge-{case['id']}", prompt,
                    turn_id=f"{case['id']}-{index}",
                )
                turns.append({
                    "input": prompt,
                    "answer": result.answer,
                    "trace": result.tool_trace,
                    "error_type": result.error_type,
                    "usage": result.usage,
                    "elapsed_seconds": round(result.elapsed_seconds, 3),
                })
            _, revision = service.get_brief(f"knowledge-{case['id']}")
            errors = grade_knowledge_case(case, turns, final_revision=revision)
            report["cases"].append({
                "id": case["id"], "passed": not errors,
                "errors": errors, "revision": revision, "turns": turns,
            })
            print(f"{case['id']}: {'PASS' if not errors else 'FAIL'}; {errors}")
    report["passed"] = sum(item["passed"] for item in report["cases"])
    report["total"] = len(report["cases"])
    report["failed"] = report["total"] - report["passed"]
    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run real (paid) DeepSeek knowledge lookup acceptance cases."
    )
    parser.add_argument("--model", default="deepseek-flash")
    parser.add_argument("--max-cases", type=int, default=4)
    parser.add_argument("--report", default="artifacts/pr03_live/knowledge_results.json")
    args = parser.parse_args()
    if not 1 <= args.max_cases <= len(CASES):
        parser.error(f"--max-cases must be 1..{len(CASES)}")
    report = evaluate(args.model, CASES[:args.max_cases])
    target = Path(args.report)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"DeepSeek knowledge cases {report['passed']}/{report['total']}. "
          f"Report: {target}")
    if report["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
