"""Adversarial PR-01 regression cases: nested quantities, constraints, provenance."""

from __future__ import annotations

import sqlite3

import pytest

from bearing_agent_system import (
    SQLiteDesignBriefStore,
    TrustedContext,
    UpdateBatch,
)
from bearing_agent_system.models import DesignBrief, Requirement, Source


def send(service, message, changes, operation="set", session="s", message_id="user-1"):
    batch = UpdateBatch.model_validate({"operation": operation, "changes": changes})
    return service.update_design_brief(
        session, batch, TrustedContext(message_id=message_id, user_message=message)
    )


def item(path, value, evidence, unit=None, precision="exact", target_id=None):
    return {
        "path": path,
        "value": value,
        "unit": unit,
        "precision": precision,
        "evidence_span": evidence,
        "target_id": target_id,
    }


def geom(value, unit="mm", op="<=", field="dimensions.D_mm"):
    return {"field": field, "operator": op, "value": value, "unit": unit}


def test_locked_ball_diameter_converts_centimeters(service):
    result = send(service, "锁定钢球直径Dw=0.8cm", [
        item("optimization_slots.Dw_mm", {"mode": "locked", "value": 0.8},
             "钢球直径Dw=0.8cm", "cm")
    ])
    assert not result.rejected_changes
    assert service.get_brief("s")[0].optimization_slots.Dw_mm.value == 8.0


def test_ball_pitch_bounds_convert_both_endpoints(service):
    result = send(service, "钢球节圆直径Dpw在3到4cm之间优化", [
        item("optimization_slots.Dpw_mm", {"mode": "bounded", "bounds": [3, 4]},
             "钢球节圆直径Dpw在3到4cm之间优化", "cm", "range")
    ])
    assert not result.rejected_changes
    assert service.get_brief("s")[0].optimization_slots.Dpw_mm.bounds == (30.0, 40.0)


def test_wrong_slot_unit_rejected(service):
    out = send(service, "锁定Dw=0.8cm", [
        item("optimization_slots.Dw_mm", {"mode": "locked", "value": 0.8},
             "Dw=0.8cm", "mm")
    ])
    assert out.rejected_changes
    assert service.get_brief("s")[0].optimization_slots.Dw_mm.mode == "optimize"


def test_wrong_slot_range_unit_rejected(service):
    out = send(service, "Dw在0.7～0.9cm之间", [
        item("optimization_slots.Dw_mm", {"mode": "bounded", "bounds": [0.7, 0.9]},
             "Dw在0.7～0.9cm之间", "mm")
    ])
    assert out.rejected_changes


def test_ball_count_range_cannot_be_fabricated(service):
    result = send(service, "我还不知道球数", [
        item("optimization_slots.Z", {"mode": "bounded", "bounds": [10, 100]},
             "我还不知道球数")
    ])
    assert result.rejected_changes
    assert service.get_brief("s")[0].optimization_slots.Z.mode == "optimize"


def test_ball_count_range_cannot_change_one_endpoint(service):
    result = send(service, "球数在10到15之间", [
        item("optimization_slots.Z", {"mode": "bounded", "bounds": [10, 100]},
             "球数在10到15之间")
    ])
    assert result.rejected_changes


def test_ball_count_explicit_range_accepted(service):
    result = send(service, "球数在10到15之间", [
        item("optimization_slots.Z", {"mode": "bounded", "bounds": [10, 15]},
             "球数在10到15之间")
    ])
    assert not result.rejected_changes
    assert service.get_brief("s")[0].optimization_slots.Z.bounds == (10, 15)
    assert "optimization_slots.Z" in result.design_status.known


def test_ball_count_bounds_cannot_have_physical_unit(service):
    result = send(service, "球数10到15个", [
        item("optimization_slots.Z", {"mode": "bounded", "bounds": [10, 15]},
             "球数10到15个", "cm")
    ])
    assert result.rejected_changes


def test_dimensionless_coefficients_do_not_accept_length(service):
    out = send(service, "fi在0.50到0.53之间", [
        item("optimization_slots.fi", {"mode": "bounded", "bounds": [0.50, 0.53]},
             "fi在0.50到0.53之间", "mm")
    ])
    assert out.rejected_changes
    good = send(service, "fi在0.50到0.53之间", [
        item("optimization_slots.fi", {"mode": "bounded", "bounds": [0.50, 0.53]},
             "fi在0.50到0.53之间")
    ])
    assert not good.rejected_changes


def test_approximate_ball_diameter_cannot_be_locked(service):
    out = send(service, "球径大约8mm", [
        item("optimization_slots.Dw_mm", {"mode": "locked", "value": 8},
             "球径大约8mm", "mm", "approximate")
    ])
    assert out.rejected_changes
    assert service.get_brief("s")[0].optimization_slots.Dw_mm.value is None


def test_approximate_hidden_outside_evidence_is_still_rejected(service):
    out = send(service, "球径大约8mm", [
        item("optimization_slots.Dw_mm", {"mode": "locked", "value": 8},
             "8mm", "mm", "exact")
    ])
    assert out.rejected_changes


def test_approximate_range_cannot_become_hard_boundary(service):
    out = send(service, "球数大约10到15个", [
        item("optimization_slots.Z", {"mode": "bounded", "bounds": [10, 15]},
             "球数大约10到15个", None, "approximate")
    ])
    assert out.rejected_changes


def test_geometric_bound_wrong_unit_rejected(service):
    result = send(service, "外径不超过5.2mm", [
        item("requirements.geometric_bounds[]", geom(5.2, "cm"),
             "外径不超过5.2mm")
    ])
    assert result.rejected_changes
    assert service.get_brief("s")[0].requirements.geometric_bounds == []


def test_geometric_bound_converts_correct_centimeter(service):
    result = send(service, "外径不超过0.52cm", [
        item("requirements.geometric_bounds[]", geom(0.52, "cm"),
             "外径不超过0.52cm")
    ])
    assert not result.rejected_changes
    assert service.get_brief("s")[0].requirements.geometric_bounds[0].value == 5.2


@pytest.mark.parametrize("message,evidence", [
    ("外径≤52mm", "外径≤52mm"),
    ("外径不超过52mm", "52"),
    ("外径上限52mm", "外径上限52mm"),
    ("外径小于52mm", "外径小于52mm"),
])
def test_explicit_outer_diameter_limit_cannot_be_fixed_size(service, message, evidence):
    result = send(service, message, [item("dimensions.D_mm", 52, evidence, "mm")])
    assert result.rejected_changes
    assert service.get_brief("s")[0].dimensions.D_mm is None


def test_explicit_width_lower_bound_cannot_be_fixed_size(service):
    result = send(service, "宽度至少15mm", [
        item("dimensions.B_mm", 15, "宽度至少15mm", "mm")
    ])
    assert result.rejected_changes


def test_wrong_direction_of_geometric_bound_rejected(service):
    result = send(service, "外径不超过52mm", [
        item("requirements.geometric_bounds[]", geom(52, "mm", ">="),
             "外径不超过52mm")
    ])
    assert result.rejected_changes


def test_requirement_replace_then_old_limit_no_longer_conflicts(service):
    first = send(service, "外径不超过52mm", [
        item("requirements.geometric_bounds[]", geom(52), "外径不超过52mm")
    ])
    assert first.revision == 1
    brief, _ = service.get_brief("s")
    req_id = brief.requirements.geometric_bounds[0].id
    assert req_id and req_id.startswith("req-")
    assert first.design_status.known["requirements.geometric_bounds[]"][0]["id"] == req_id

    revised = send(service, "把外径上限改为60mm", [
        item("requirements.geometric_bounds[]", geom(60),
             "外径上限改为60mm", target_id=req_id)
    ], operation="replace", message_id="user-2")
    assert not revised.rejected_changes
    assert revised.revision == 2
    current, _ = service.get_brief("s")
    assert len(current.requirements.geometric_bounds) == 1
    assert current.requirements.geometric_bounds[0].id == req_id
    assert current.requirements.geometric_bounds[0].value == 60

    size = send(service, "外径采用58mm", [
        item("dimensions.D_mm", 58, "外径采用58mm", "mm")
    ], message_id="user-3")
    assert not size.rejected_changes
    assert not size.design_status.conflicts


def test_requirement_withdrawal_does_not_leave_conflict(service):
    send(service, "外径不超过52mm", [
        item("requirements.geometric_bounds[]", geom(52), "外径不超过52mm")
    ])
    req_id = service.get_brief("s")[0].requirements.geometric_bounds[0].id
    withdrawn = send(service, "取消之前的外径上限", [
        item("requirements.geometric_bounds[]", None,
             "取消之前的外径上限", target_id=req_id)
    ], operation="replace")
    assert not withdrawn.rejected_changes
    assert service.get_brief("s")[0].requirements.geometric_bounds == []
    result = send(service, "外径采用58mm", [
        item("dimensions.D_mm", 58, "外径采用58mm", "mm")
    ], message_id="user-2")
    assert not result.design_status.conflicts


def test_requirement_replace_without_target_id_is_rejected(service):
    send(service, "外径不超过52mm", [
        item("requirements.geometric_bounds[]", geom(52), "外径不超过52mm")
    ])
    result = send(service, "外径上限改为60mm", [
        item("requirements.geometric_bounds[]", geom(60), "外径上限改为60mm")
    ], operation="replace")
    assert result.rejected_changes


def test_requirement_set_different_limit_must_use_replace(service):
    send(service, "外径不超过52mm", [
        item("requirements.geometric_bounds[]", geom(52), "外径不超过52mm")
    ])
    result = send(service, "外径上限改为60mm", [
        item("requirements.geometric_bounds[]", geom(60), "外径上限改为60mm")
    ], operation="set")
    assert result.rejected_changes
    assert service.get_brief("s")[0].requirements.geometric_bounds[0].value == 52


def test_requirement_two_sided_bounds_have_distinct_ids(service):
    send(service, "外径不小于40mm", [
        item("requirements.geometric_bounds[]", geom(40, op=">="),
             "外径不小于40mm")
    ])
    send(service, "外径不超过60mm", [
        item("requirements.geometric_bounds[]", geom(60),
             "外径不超过60mm")
    ])
    ids = [r.id for r in service.get_brief("s")[0].requirements.geometric_bounds]
    assert len(ids) == 2
    assert len(set(ids)) == 2


def test_atomic_rollback_if_replacement_batch_has_wrong_unit(service):
    send(service, "外径不超过52mm", [
        item("requirements.geometric_bounds[]", geom(52), "外径不超过52mm")
    ])
    req_id = service.get_brief("s")[0].requirements.geometric_bounds[0].id
    result = send(service, "外径上限改为60mm，球径为0.8cm", [
        item("requirements.geometric_bounds[]", geom(60),
             "外径上限改为60mm", target_id=req_id),
        item("optimization_slots.Dw_mm", {"mode": "locked", "value": 0.8},
             "球径为0.8cm", "mm"),
    ], operation="replace")
    assert result.rejected_changes
    brief, revision = service.get_brief("s")
    assert revision == 1
    assert brief.requirements.geometric_bounds[0].value == 52
    assert brief.optimization_slots.Dw_mm.mode == "optimize"


def test_user_unit_evidence_for_quantitative_goal(service):
    result = send(service, "寿命至少10000小时", [
        item("requirements.constraints[]",
             {"field": "life_hours", "operator": ">=", "value": 10000, "unit": "h"},
             "寿命至少10000小时")
    ])
    assert not result.rejected_changes
    wrong = send(service, "寿命至少10000小时", [
        item("requirements.constraints[]",
             {"field": "life_hours", "operator": ">=", "value": 10000, "unit": "W"},
             "寿命至少10000小时")
    ])
    assert wrong.rejected_changes


def test_unknown_numeric_goal_is_not_silently_trusted(service):
    result = send(service, "未知指标不超过10mm", [
        item("requirements.constraints[]",
             {"field": "unknown_metric", "operator": "<=", "value": 10, "unit": "mm"},
             "未知指标不超过10mm")
    ])
    assert result.rejected_changes


def test_legacy_requirement_ids_migrate_without_content_revision(tmp_path):
    db = tmp_path / "old.sqlite3"
    store = SQLiteDesignBriefStore(db)
    brief = DesignBrief()
    brief.requirements.geometric_bounds.append(Requirement(
        field="dimensions.D_mm", operator="<=", value=52, unit="mm",
        source=Source(kind="user", message_id="old")
    ))
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO design_briefs(session_id,revision,payload_json) VALUES (?,?,?)",
            ("legacy", 3, brief.model_dump_json())
        )
    first, revision = store.get_brief("legacy")
    assert revision == 3
    assigned = first.requirements.geometric_bounds[0].id
    assert assigned
    next_read, same_revision = SQLiteDesignBriefStore(db).get_brief("legacy")
    assert same_revision == 3
    assert next_read.requirements.geometric_bounds[0].id == assigned


def test_plain_three_dimension_batch_remains_supported(service):
    result = send(service, "轴承尺寸25×52×15mm", [
        item("dimensions.d_mm", 25, "25×52×15mm", "mm"),
        item("dimensions.D_mm", 52, "25×52×15mm", "mm"),
        item("dimensions.B_mm", 15, "25×52×15mm", "mm"),
    ])
    assert not result.rejected_changes
    assert result.revision == 1


def test_locked_ball_diameter_range_centimeter_converts_both_ends(service):
    result = send(service, "Dw在0.7～0.9cm之间", [
        item("optimization_slots.Dw_mm", {"mode": "bounded", "bounds": [0.7, 0.9]},
             "Dw在0.7～0.9cm之间", "cm", "range")
    ])
    assert not result.rejected_changes
    assert service.get_brief("s")[0].optimization_slots.Dw_mm.bounds == (7.0, 9.0)


def test_approximate_dimension_cannot_be_confirmed_with_clipped_quote(service):
    result = send(service, "外径大约52mm", [
        item("dimensions.D_mm", 52, "52mm", "mm", "exact")
    ])
    assert result.rejected_changes
    assert service.get_brief("s")[0].dimensions.D_mm is None


def test_approximate_bound_cannot_become_hard_limit(service):
    result = send(service, "外径大约不超过52mm", [
        item("requirements.geometric_bounds[]", geom(52), "不超过52mm")
    ])
    assert result.rejected_changes
    assert service.get_brief("s")[0].requirements.geometric_bounds == []


def test_power_loss_kilowatts_converts_to_watts(service):
    result = send(service, "功率损耗不超过0.02kW", [
        item("requirements.constraints[]",
             {"field": "power_loss", "operator": "<=", "value": 0.02, "unit": "kW"},
             "功率损耗不超过0.02kW")
    ])
    assert not result.rejected_changes
    assert service.get_brief("s")[0].requirements.constraints[0].value == 20.0
