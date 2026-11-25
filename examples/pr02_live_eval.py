"""Live DeepSeek golden dialogue runner (explicit API opt-in; never in routine CI).

Usage:
    python examples/pr02_live_eval.py --model deepseek-flash --max-cases 5
    python examples/pr02_live_eval.py --model deepseek-v4-pro --max-cases 20

Writes reproducible results locally; does not report a passing score for mock calls.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bearing_agent_system import DesignBriefService, SQLiteDesignBriefStore
from bearing_agent_system.conversation import ConversationAgent
from bearing_agent_system.conversation_store import ConversationStore
from bearing_agent_system.llm_client import make_deepseek_model
from bearing_agent_system.parameter_catalog import get_path_value

# A test task is kept together across its turns. No training/test split within task.
CASES: list[dict[str, Any]] = [
    {"id": "D01", "turns": ["设计深沟球轴承，尺寸25×52×15mm。"],
     "expected": {"dimensions.d_mm": 25, "dimensions.D_mm": 52, "dimensions.B_mm": 15}},
    {"id": "D02", "turns": ["内圈转速18000rpm，外圈固定。"],
     "expected": {"operating.inner_speed_rpm": 18000, "operating.outer_speed_rpm": 0}},
    {"id": "D03", "turns": ["径向载荷300N，没有轴向载荷。"],
     "expected": {"operating.radial_load_n": 300, "operating.axial_load_n": 0}},
    {"id": "D04", "turns": ["轴承工作温度大概60℃。"],
     "expected": {"operating.temperature_c": 60},
     "pending": ["operating.temperature_c"]},
    {"id": "D05", "turns": ["外径不超过52mm。"],
     "missing": ["dimensions.D_mm"],
     "bounds": [{"field": "dimensions.D_mm", "operator": "<=", "value": 52}]},
    {"id": "D06", "turns": ["电机转速15000rpm，轴承哪一圈转动还不知道。"],
     "missing": ["operating.inner_speed_rpm"]},
    {"id": "D07", "turns": ["轴径25mm，但轴承尺寸还没确定。"],
     "missing": ["dimensions.d_mm"]},
    {"id": "D08", "turns": ["我还不知道球数，请先保持待优化。"],
     "slots": {"Z": "optimize"}},
    {"id": "D09", "turns": ["钢球直径大约8mm，不要锁定。"],
     "slots": {"Dw_mm": "optimize"}},
    {"id": "D10", "turns": ["锁定Dw钢球直径0.8cm。"],
     "slots": {"Dw_mm": "locked"},
     "slot_values": {"Dw_mm": 8}},
    {"id": "D11", "turns": ["钢球个数Z在10到15个之间优化。"],
     "slots": {"Z": "bounded"},
     "slot_bounds": {"Z": [10, 15]}},
    {"id": "D12", "turns": ["希望功率损耗尽可能低。"],
     "prefs": [{"field": "power_loss", "operator": "minimize"}]},
    {"id": "D13", "turns": ["内圈转速15000rpm。", "把内圈转速改为18000rpm。"],
     "expected": {"operating.inner_speed_rpm": 18000}},
    {"id": "D14", "turns": ["外径上限52mm。", "外径上限改为60mm。"],
     "bounds": [{"field": "dimensions.D_mm", "operator": "<=", "value": 60}],
     "bound_count": 1},
    {"id": "D15", "turns": ["外径上限52mm。", "取消之前的外径上限。"],
     "bound_count": 0},
    {"id": "D16", "turns": ["先解释一下什么是径向游隙。"],
     "missing": ["engineering.clearance.group", "dimensions.d_mm"]},
    {"id": "D17", "turns": ["尺寸25×52×15mm。", "我目前已经确定了什么？"],
     "expected": {"dimensions.d_mm": 25, "dimensions.D_mm": 52, "dimensions.B_mm": 15}},
    {"id": "D18", "turns": ["径向载荷300N。", "内径25mm、外径52mm，宽15mm。"],
     "expected": {"operating.radial_load_n": 300, "dimensions.d_mm": 25,
                  "dimensions.D_mm": 52, "dimensions.B_mm": 15}},
    {"id": "D19", "turns": ["轴承内径2.5cm，径向载荷0.3kN。"],
     "expected": {"dimensions.d_mm": 25, "operating.radial_load_n": 300}},
    {"id": "D20", "turns": ["寿命至少10000小时，功耗尽可能低。"],
     "constraints": [{"field": "life_hours", "operator": ">=", "value": 10000}],
     "prefs": [{"field": "power_loss", "operator": "minimize"}]},
]


def _close(actual: Any, wanted: Any) -> bool:
    if isinstance(actual, (int, float)) and isinstance(wanted, (int, float)):
        return abs(float(actual) - float(wanted)) < 1e-7
    return actual == wanted


def grade(brief: Any, case: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for path, wanted in case.get("expected", {}).items():
        value = get_path_value(brief, path)
        if value is None or not _close(value.value, wanted):
            errors.append(f"{path}: expected {wanted}, got {None if value is None else value.value}")
    for path in case.get("missing", []):
        if get_path_value(brief, path) is not None:
            errors.append(f"{path}: should remain unknown")
    for path in case.get("pending", []):
        value = get_path_value(brief, path)
        if value is None or value.confirmed or value.precision == "exact":
            errors.append(f"{path}: approximate value must remain pending")
    for name, mode in case.get("slots", {}).items():
        slot = getattr(brief.optimization_slots, name)
        if slot.mode != mode:
            errors.append(f"slot {name}: expected mode={mode}, got {slot.mode}")
    for name, value in case.get("slot_values", {}).items():
        if not _close(getattr(brief.optimization_slots, name).value, value):
            errors.append(f"slot {name}: wrong fixed value")
    for name, bounds in case.get("slot_bounds", {}).items():
        real = getattr(brief.optimization_slots, name).bounds
        if real is None or len(real) != 2 or not all(_close(a, b) for a, b in zip(real, bounds, strict=True)):
            errors.append(f"slot {name}: wrong bounds")
    actual_bounds = brief.requirements.geometric_bounds
    if "bound_count" in case and len(actual_bounds) != case["bound_count"]:
        errors.append(f"bound count: expected {case['bound_count']}, got {len(actual_bounds)}")
    for expected in case.get("bounds", []):
        if not any(b.field == expected["field"] and b.operator == expected["operator"]
                   and _close(b.value, expected["value"]) for b in actual_bounds):
            errors.append(f"missing geometric bound {expected}")
    for group, attr in (("prefs", "preferences"), ("constraints", "constraints")):
        existing = getattr(brief.requirements, attr)
        count_key = "preference_count" if group == "prefs" else "constraint_count"
        if count_key in case and len(existing) != case[count_key]:
            errors.append(f"{attr} count: expected {case[count_key]}, got {len(existing)}")
        for expected in case.get(group, []):
            if not any(b.field == expected["field"] and b.operator == expected["operator"]
                       and ("value" not in expected or _close(b.value, expected["value"]))
                       for b in existing):
                errors.append(f"missing {group}: {expected}")
    return errors


def evaluate(model_name: str, cases: list[dict[str, Any]]) -> dict[str, Any]:
    model = make_deepseek_model(model_name)
    report: dict[str, Any] = {
        "mode": "LIVE_DEEPSEEK", "model": model_name,
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "results": [],
    }
    with tempfile.TemporaryDirectory(prefix="pr02-live-") as folder:
        db = Path(folder) / "brief.sqlite3"
        service = DesignBriefService(SQLiteDesignBriefStore(db))
        agent = ConversationAgent(service, ConversationStore(db), model)
        for case in cases:
            session = f"live-{case['id']}"
            turns = []
            for idx, prompt in enumerate(case["turns"]):
                reply = agent.respond(session, prompt, turn_id=f"{case['id']}-{idx}")
                turns.append({
                    "user": prompt, "answer": reply.answer,
                    "revision": reply.revision, "trace": reply.tool_trace,
                    "usage": reply.usage, "seconds": round(reply.elapsed_seconds, 3),
                    "error_type": reply.error_type,
                })
            brief, revision = service.get_brief(session)
            errors = grade(brief, case)
            if any(turn["error_type"] for turn in turns):
                errors.append("an API/agent runtime error occurred")
            report["results"].append({
                "case_id": case["id"], "passed": not errors,
                "errors": errors, "turns": turns,
                "final_revision": revision,
                "final_brief": brief.model_dump(mode="json"),
            })
            print(f"{case['id']}: {'PASS' if not errors else 'FAIL'}; "
                  f"turns={len(turns)} errors={errors}")
    passed = sum(1 for item in report["results"] if item["passed"])
    report["total"] = len(report["results"])
    report["passed"] = passed
    report["failed"] = len(report["results"]) - passed
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="deepseek-flash")
    parser.add_argument("--max-cases", type=int, default=5)
    parser.add_argument("--report", default="artifacts/pr02_live/live_results.json")
    args = parser.parse_args()
    if not 1 <= args.max_cases <= len(CASES):
        parser.error("--max-cases must be between 1 and 20")
    report = evaluate(args.model, CASES[:args.max_cases])
    path = Path(args.report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Live cases: {report['passed']}/{report['total']} passed. Report: {path}")
    if report["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
