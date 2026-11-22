"""Real DeepSeek API integration tests. Skipped unless explicitly opted in."""

from __future__ import annotations

import os

import pytest

from examples.pr02_live_eval import CASES, evaluate

pytestmark = pytest.mark.live


@pytest.mark.parametrize("case_id", ["D01", "D02", "D03", "D05", "D08"])
def test_live_deepseek_tool_workflow(case_id):
    if os.environ.get("RUN_DEEPSEEK_LIVE") != "1":
        pytest.skip("Set RUN_DEEPSEEK_LIVE=1 to use the paid DeepSeek API")
    if not os.environ.get("DEEPSEEK_API_KEY"):
        pytest.fail("RUN_DEEPSEEK_LIVE=1 needs DEEPSEEK_API_KEY")
    case = next(item for item in CASES if item["id"] == case_id)
    result = evaluate(os.environ.get("DEEPSEEK_MODEL", "deepseek-flash"), [case])
    assert result["results"][0]["passed"], result["results"][0]["errors"]

