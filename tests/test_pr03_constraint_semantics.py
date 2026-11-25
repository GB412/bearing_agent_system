"""LLM owns performance-requirement semantics; storage owns data integrity.

These are offline boundary tests, NOT evidence that DeepSeek classified the
underlying Chinese utterance correctly. That requires the opt-in live suite.
"""

from __future__ import annotations

from bearing_agent_system.agent_prompt import build_system_prompt
from bearing_agent_system.models import TrustedContext, UpdateBatch


def save(service, message, path, field, operator, value, unit, *,
         evidence=None, session="semantic"):
    batch = UpdateBatch.model_validate({
        "operation": "set",
        "changes": [{
            "path": path,
            "value": {
                "field": field,
                "operator": operator,
                "value": value,
                "unit": unit,
            },
            "evidence_span": evidence or message,
        }],
    })
    return service.update_design_brief(
        session, batch,
        TrustedContext(message_id="turn-1", user_message=message),
    )


def test_performance_limit_uses_llm_interpretation_without_fixed_keywords(service):
    result = save(
        service, "最高轴承温度控制在95℃",
        "requirements.constraints[]",
        "max_bearing_temperature_c", "<=", 95, "℃",
    )
    assert not result.rejected_changes
    constraint = service.get_brief("semantic")[0].requirements.constraints[0]
    assert (constraint.field, constraint.operator, constraint.value, constraint.unit) == (
        "max_bearing_temperature_c", "<=", 95, "degC",
    )


def test_numbered_soft_goal_is_not_forced_into_a_hard_bound(service):
    result = save(
        service, "我希望寿命达到20000小时，但这不是硬性限制",
        "requirements.preferences[]",
        "life_hours", "text", "希望寿命达到20000小时（非硬性要求）", None,
    )
    assert not result.rejected_changes
    brief = service.get_brief("semantic")[0]
    assert brief.requirements.constraints == []
    assert len(brief.requirements.preferences) == 1
    assert brief.requirements.preferences[0].operator == "text"


def test_backend_does_not_claim_to_validate_performance_comparator_semantics(service):
    # Deliberately wrong model interpretation: after removing the keyword
    # comparator gate this is structurally valid. Live LLM tests must catch it.
    result = save(
        service, "寿命至少20000小时",
        "requirements.constraints[]",
        "life_hours", "<=", 20000, "小时",
    )
    assert not result.rejected_changes
    assert service.get_brief("semantic")[0].requirements.constraints[0].operator == "<="


def test_numeric_unit_and_user_evidence_are_still_guarded(service):
    wrong_unit = save(
        service, "寿命至少20000小时",
        "requirements.constraints[]",
        "life_hours", ">=", 20000, "W",
    )
    assert wrong_unit.rejected_changes
    wrong_evidence = save(
        service, "寿命至少20000小时",
        "requirements.constraints[]",
        "life_hours", ">=", 20000, "小时",
        evidence="寿命至少30000小时",
    )
    assert wrong_evidence.rejected_changes
    assert service.get_brief("semantic")[0].requirements.constraints == []


def test_geometric_bound_retains_its_separate_safety_guard(service):
    wrong = save(
        service, "外径不超过52mm",
        "requirements.geometric_bounds[]",
        "dimensions.D_mm", ">=", 52, "mm",
    )
    assert wrong.rejected_changes
    assert service.get_brief("semantic")[0].requirements.geometric_bounds == []


def test_prompt_owns_hard_soft_and_hypothetical_decisions(service):
    status = service.get_design_status("semantic").model_dump(mode="json")
    prompt = build_system_prompt(status, 0)
    assert "硬约束" in prompt
    assert "软目标" in prompt
    assert "假设" in prompt
    assert "不一定是最低寿命限制" in prompt
    assert "preferences[]" in prompt
    assert "不应为了匹配数据结构转成硬约束" in prompt
