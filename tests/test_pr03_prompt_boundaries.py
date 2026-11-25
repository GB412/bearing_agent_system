"""Behavioral guardrails for the compact DGB conversation prompt."""

from __future__ import annotations

from bearing_agent_system.agent_prompt import build_system_prompt


def test_complete_brief_guides_stage_transition_without_extra_questionnaire():
    status = {"known": {"dimensions.d_mm": {"value": 50}},
              "missing": [], "pending_confirmation": [], "conflicts": []}
    prompt = build_system_prompt(status, 4)
    assert "用户层需求草案已完整" in prompt
    assert "后续方案设计与校核" in prompt
    assert "不要反复追问" in prompt
    assert "已从用户层 DesignBrief 删除" not in prompt
    assert "由受信固定模板提供" not in prompt
    assert "不能宣称已完成优化" in prompt
    assert '"revision":4' in prompt


def test_missing_fields_and_pending_recommendation_are_still_in_trusted_snapshot():
    status = {"known": {}, "missing": ["dimensions.d_mm"],
              "pending_confirmation": ["operating.temperature_c"],
              "conflicts": []}
    recommendation = {"proposal_id": "rec-123", "changes": []}
    prompt = build_system_prompt(status, 7, recommendation)
    assert '"dimensions.d_mm"' in prompt
    assert '"operating.temperature_c"' in prompt
    assert '"proposal_id":"rec-123"' in prompt
    assert "先用写入工具" in prompt
    assert "用户后续明确同意用 accept" in prompt
    assert "[[DESIGN_STATUS]]" in prompt


def test_prompt_uses_only_active_tool_contract_and_no_new_required_fields():
    prompt = build_system_prompt(
        {"known": {}, "missing": [], "pending_confirmation": [], "conflicts": []},
        0,
    )
    for tool in ("update_design_brief", "get_design_status",
                 "lookup_engineering_knowledge"):
        assert tool in prompt
    assert "max_inner_speed_rpm" not in prompt
    assert "oil_supply_method" not in prompt
    assert len(prompt) < 3500
