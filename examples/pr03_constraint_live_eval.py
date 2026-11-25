"""Opt-in real DeepSeek evaluation of hard vs soft requirement semantics.

Run locally with a DeepSeek key (never part of CI):
    python examples/pr03_constraint_live_eval.py --model deepseek-flash --max-cases 6

Offline tests cannot establish that the model correctly classifies intent.
This suite checks actual persisted SQLite requirements after each conversation.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pr02_live_eval import evaluate

CASES = [
    {
        "id": "HS01",
        "turns": ["轴承寿命必须至少20000小时。"],
        "constraint_count": 1,
        "constraints": [{"field": "life_hours", "operator": ">=", "value": 20000}],
    },
    {
        "id": "HS02",
        "turns": ["最高轴承温度控制在95℃，这是不可突破的上限。"],
        "constraint_count": 1,
        "constraints": [{"field": "max_bearing_temperature_c",
                         "operator": "<=", "value": 95}],
    },
    {
        "id": "HS03",
        "turns": ["希望寿命越长越好，这是优化目标。"],
        "constraint_count": 0,
        "preference_count": 1,
        "prefs": [{"field": "life_hours", "operator": "maximize"}],
    },
    {
        "id": "HS04",
        "turns": ["我希望寿命达到20000小时，但只是期望目标，不是硬性限制。"],
        "constraint_count": 0,
        "preference_count": 1,
        "prefs": [{"field": "life_hours", "operator": "text"}],
    },
    {
        "id": "HS05",
        "turns": ["如果寿命至少20000小时，会影响设计难度吗？"
                  "我现在只是咨询，不要保存为设计约束。"],
        "constraint_count": 0,
        "preference_count": 0,
    },
    {
        "id": "HS06",
        "turns": ["希望寿命达到20000小时。"],
        "constraint_count": 0,
    },
    {
        "id": "HS07",
        "turns": ["摩擦功耗不能超过100W，最小油膜厚度至少0.2μm。"],
        "constraint_count": 2,
        "constraints": [
            {"field": "power_loss", "operator": "<=", "value": 100},
            {"field": "min_film_thickness", "operator": ">=", "value": 0.0002},
        ],
    },
]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Paid opt-in DeepSeek test: hard bounds vs soft goals."
    )
    parser.add_argument("--model", default="deepseek-flash")
    parser.add_argument("--max-cases", type=int, default=len(CASES))
    parser.add_argument(
        "--report", default="artifacts/pr03_live/constraint_semantics.json"
    )
    args = parser.parse_args()
    if not 1 <= args.max_cases <= len(CASES):
        parser.error(f"--max-cases must be between 1 and {len(CASES)}")
    report = evaluate(args.model, CASES[:args.max_cases])
    report["suite"] = "constraint_semantics"
    output = Path(args.report)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Live cases: {report['passed']}/{report['total']}. Report: {output}")
    if report["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
