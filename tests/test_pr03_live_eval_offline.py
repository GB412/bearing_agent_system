"""Offline evaluation checks for the *opt-in* paid PR-03 DeepSeek test runner."""

from __future__ import annotations

from examples.pr03_live_eval import CASES, grade_knowledge_case


def _turn(
    *, answer: str, status: str, ids: list[str], sources: list[str],
    write: bool = False,
) -> dict:
    trace = [{
        "name": "lookup_engineering_knowledge",
        "ok": True,
        "knowledge_status": status,
        "knowledge_ids": ids,
        "knowledge_source_urls": sources,
    }]
    if write:
        trace.append({"name": "update_design_brief", "ok": True})
    return {"answer": answer, "trace": trace, "error_type": None}


def test_live_grader_accepts_sourced_6206_dimensions_without_write():
    case = CASES[0]
    url = "https://www.skf.com/si/products/rolling-bearings/ball-bearings/deep-groove-ball-bearings/productid-6206"
    answer = "SKF 6206 主要尺寸30×62×16 mm，来源：" + url
    turns = [_turn(
        answer=answer, status="FOUND",
        ids=["skf-6206-dimensions"], sources=[url],
    )]
    assert grade_knowledge_case(case, turns, final_revision=0) == []


def test_live_grader_rejects_missing_tool_or_citation():
    case = CASES[0]
    assert "did not call" in " ".join(grade_knowledge_case(
        case, [{"answer": "SKF 6206 30×62×16", "trace": [], "error_type": None}],
        final_revision=0,
    ))
    url = "https://www.skf.com/si/products/example"
    turns = [_turn(
        answer="SKF 6206 30×62×16", status="FOUND",
        ids=["skf-6206-dimensions"], sources=[url],
    )]
    assert "lacks an exact cited manufacturer URL" in " ".join(
        grade_knowledge_case(case, turns, final_revision=0)
    )


def test_live_grader_catches_numeric_clearance_and_knowledge_write():
    case = CASES[2]
    turns = [_turn(
        answer="该6206的C3游隙是25 µm",
        status="INSUFFICIENT_EVIDENCE",
        ids=["ntn-clearance-classes"],
        sources=["https://ntnamericas.com/technical-resources/faqs/"],
        write=True,
    )]
    errors = grade_knowledge_case(case, turns, final_revision=1)
    assert any("numerical engineering" in line for line in errors)
    assert any("modified DesignBrief" in line for line in errors)
    assert any("attempted a write" in line for line in errors)


def test_live_grader_does_not_treat_part_number_as_numeric_measurement():
    case = CASES[3]
    turns = [_turn(
        answer="当前资料不足，无法确认6206 k6/H7的具体公差。",
        status="INSUFFICIENT_EVIDENCE", ids=["ntn-shaft-housing-fit-principles"],
        sources=["https://ntnamericas.com/technical-resources/shaft-housing-fits/"],
    )]
    assert grade_knowledge_case(case, turns, final_revision=0) == []


def test_6206_product_number_does_not_satisfy_missing_62_mm_measurement():
    case = CASES[0]
    url = "https://www.skf.com/si/products/rolling-bearings/ball-bearings/deep-groove-ball-bearings/productid-6206"
    turns = [_turn(
        answer="SKF 6206的尺寸是30×16mm，来源：" + url,
        status="FOUND", ids=["skf-6206-dimensions"], sources=[url],
    )]
    errors = grade_knowledge_case(case, turns, final_revision=0)
    assert any("62" in error for error in errors)


def test_live_grader_detects_micron_value_before_chinese_suffix():
    case = CASES[2]
    turns = [_turn(
        answer="按经验该型号CN游隙是25µm的范围。",
        status="INSUFFICIENT_EVIDENCE",
        ids=["ntn-clearance-classes"],
        sources=["https://ntnamericas.com/technical-resources/faqs/"],
    )]
    errors = grade_knowledge_case(case, turns, final_revision=0)
    assert any("numerical engineering" in error for error in errors)
