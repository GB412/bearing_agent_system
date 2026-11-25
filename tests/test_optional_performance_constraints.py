"""Five optional performance limits share the existing DesignBrief requirement list."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from bearing_agent_system.models import TrustedContext, UpdateBatch
from bearing_agent_system.parameter_catalog import EXTRA_QUANTITIES


def change(field, op, value, unit, evidence, *, target_id=None):
    return {
        "path": "requirements.constraints[]",
        "value": {"field": field, "operator": op, "value": value, "unit": unit},
        "evidence_span": evidence,
        **({"target_id": target_id} if target_id is not None else {}),
    }


def send(service, message, changes, *, session="limits", operation="set"):
    return service.update_design_brief(
        session,
        UpdateBatch.model_validate({"operation": operation, "changes": changes}),
        TrustedContext(message_id="t", user_message=message),
    )


def test_all_five_optional_limits_can_be_saved_in_one_batch(service):
    cases = [
        ("life_hours", ">=", 20000, "h", "寿命至少20000h", 20000.0, "h"),
        ("min_film_thickness", ">=", 0.2, "μm",
         "最小油膜厚度不低于0.2μm", 0.0002, "mm"),
        ("power_loss", "<=", 100, "W", "摩擦功耗不超过100W", 100.0, "W"),
        ("max_bearing_temperature_c", "<=", 95, "℃",
         "最高轴承温度不超过95℃", 95.0, "degC"),
        ("max_contact_stress", "<=", 1800, "MPa",
         "最大接触应力不超过1800MPa", 1800.0, "MPa"),
    ]
    message = "，".join(item[4] for item in cases)
    outcome = send(service, message, [
        change(field, op, value, unit, evidence)
        for field, op, value, unit, evidence, _, _ in cases
    ])
    assert not outcome.rejected_changes
    assert outcome.revision == 1
    assert outcome.applied_changes == ["requirements.constraints[]"]
    brief, rev = service.get_brief("limits")
    assert rev == 1
    assert len(brief.requirements.constraints) == 5
    for req, (field, op, _, _, _, number, unit) in zip(
        brief.requirements.constraints, cases, strict=True
    ):
        assert (req.field, req.operator, req.unit) == (field, op, unit)
        assert req.value == pytest.approx(number)
        assert req.id.startswith("req-")
        assert req.source.kind == "user"


def test_omitted_limits_create_no_placeholders_or_missing_flags(service):
    brief, revision = service.get_brief("blank")
    assert revision == 0
    assert brief.requirements.constraints == []
    status = service.get_design_status("blank")
    assert not any(field in str(status.missing) for field in EXTRA_QUANTITIES)
    assert "requirements.constraints[]" not in status.known


@pytest.mark.parametrize(("user_text", "field", "raw_unit", "expected"), [
    ("最小油膜厚度不低于0.2µm", "min_film_thickness", "µm", 0.0002),
    ("最小油膜厚度不低于0.2μm", "min_film_thickness", "μm", 0.0002),
    ("最小油膜厚度不低于0.2um", "min_film_thickness", "um", 0.0002),
    ("最小油膜厚度不低于0.2微米", "min_film_thickness", "微米", 0.0002),
    ("最大接触应力不超过1800兆帕", "max_contact_stress", "兆帕", 1800),
    ("最高轴承温度不超过95°C", "max_bearing_temperature_c", "°C", 95),
])
def test_unit_aliases_convert_to_canonical_units(
    service, user_text, field, raw_unit, expected
):
    result = send(
        service, user_text,
        [change(field, ">=" if field == "min_film_thickness" else "<=",
                0.2 if field == "min_film_thickness"
                else 95 if field == "max_bearing_temperature_c" else 1800,
                raw_unit, user_text)],
    )
    assert not result.rejected_changes
    assert service.get_brief("limits")[0].requirements.constraints[0].value == (
        pytest.approx(expected)
    )


def test_single_lifetime_limit_keeps_other_metrics_unset(service):
    result = send(service, "寿命至少20000小时", [
        change("life_hours", ">=", 20000, "小时", "寿命至少20000小时"),
    ])
    assert not result.rejected_changes
    saved = service.get_brief("limits")[0].requirements.constraints
    assert len(saved) == 1
    assert saved[0].field == "life_hours"
    assert saved[0].unit == "h"


def test_add_later_then_replace_and_withdraw_by_real_requirement_id(service):
    first = send(service, "寿命至少20000h", [
        change("life_hours", ">=", 20000, "h", "寿命至少20000h")
    ])
    assert first.revision == 1
    added = send(service, "摩擦功耗不超过100W", [
        change("power_loss", "<=", 100, "W", "摩擦功耗不超过100W")
    ])
    assert added.revision == 2
    current = service.get_brief("limits")[0].requirements.constraints
    life_id = next(x.id for x in current if x.field == "life_hours")
    power_id = next(x.id for x in current if x.field == "power_loss")
    replaced = send(
        service, "寿命改为至少30000h",
        [change("life_hours", ">=", 30000, "h", "寿命改为至少30000h",
                target_id=life_id)],
        operation="replace"
    )
    assert not replaced.rejected_changes
    assert replaced.revision == 3
    assert next(x for x in service.get_brief("limits")[0].requirements.constraints
                if x.id == life_id).value == 30000
    removed = send(service, "撤销摩擦功耗上限", [{
        "path": "requirements.constraints[]",
        "target_id": power_id,
        "value": None,
        "evidence_span": "撤销摩擦功耗上限",
    }], operation="replace")
    assert removed.revision == 4
    remaining = service.get_brief("limits")[0].requirements.constraints
    assert [(x.id, x.value) for x in remaining] == [(life_id, 30000.0)]


def test_duplicate_replay_and_conflicting_same_metric(service):
    item = change("life_hours", ">=", 20000, "h", "寿命至少20000h")
    first = send(service, "寿命至少20000h", [item])
    replay = send(service, "寿命至少20000h", [item])
    assert first.revision == replay.revision == 1
    assert len(service.get_brief("limits")[0].requirements.constraints) == 1
    denied = send(service, "寿命至少30000h", [
        change("life_hours", ">=", 30000, "h", "寿命至少30000h")
    ])
    assert denied.rejected_changes
    assert "use replace" in denied.rejected_changes[0]["reason"]


def test_wrong_unit_and_unsupported_metric_are_rejected_but_other_limit_commits(service):
    message = "寿命至少20000h，最大接触应力不超过1800MPa，未知指标不得超过3W"
    outcome = send(service, message, [
        change("life_hours", ">=", 20000, "h", "寿命至少20000h"),
        change("max_contact_stress", "<=", 1800, "W",
               "最大接触应力不超过1800MPa"),
        change("unknown_metric", "<=", 3, "W", "未知指标不得超过3W"),
    ])
    assert outcome.applied_changes == ["requirements.constraints[]"]
    assert len(outcome.rejected_changes) == 2
    saved = service.get_brief("limits")[0].requirements.constraints
    assert len(saved) == 1 and saved[0].field == "life_hours"


def test_unknown_user_threshold_is_not_a_zero_or_default(service):
    message = "最小油膜厚度暂时不知道具体数值"
    outcome = send(service, message, [
        change("min_film_thickness", ">=", None, "μm", message),
    ])
    assert outcome.rejected_changes
    assert service.get_brief("limits")[0].requirements.constraints == []


def test_numerical_limits_do_not_overwrite_operating_temperature(service):
    outcome = send(service, "最高轴承温度不超过95℃", [
        change("max_bearing_temperature_c", "<=", 95, "℃",
               "最高轴承温度不超过95℃")
    ])
    assert not outcome.rejected_changes
    brief, _ = service.get_brief("limits")
    assert brief.operating.temperature_c is None
    assert brief.requirements.constraints[0].field == "max_bearing_temperature_c"


def test_repeated_scalar_path_still_forbidden_and_replace_requires_unique_ids():
    with pytest.raises(ValidationError):
        UpdateBatch.model_validate({"operation": "set", "changes": [
            {"path": "dimensions.d_mm", "value": 50, "unit": "mm",
             "evidence_span": "内径50mm"},
            {"path": "dimensions.d_mm", "value": 60, "unit": "mm",
             "evidence_span": "内径60mm"},
        ]})
    with pytest.raises(ValidationError):
        UpdateBatch.model_validate({"operation": "replace", "changes": [
            change("life_hours", ">=", 20000, "h", "寿命至少20000h",
                   target_id="req-1"),
            change("life_hours", ">=", 30000, "h", "寿命至少30000h",
                   target_id="req-1"),
        ]})
