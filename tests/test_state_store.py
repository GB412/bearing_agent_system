from __future__ import annotations

import pytest

from bearing_agent_system import SQLiteDesignBriefStore, TrustedContext, UpdateBatch
from bearing_agent_system.models import ParameterValue


def update(service, changes, message, operation="set", message_id="m1", session="s1"):
    return service.update_design_brief(
        session,
        UpdateBatch.model_validate({"operation": operation, "changes": changes}),
        TrustedContext(message_id=message_id, user_message=message),
    )


def ch(path, value, evidence, unit=None, precision="exact"):
    return {"path": path, "value": value, "unit": unit, "precision": precision, "evidence_span": evidence}


def test_create_default_and_persistence(service, tmp_path):
    brief, revision = service.get_brief("persist")
    assert revision == 0
    assert brief.dimensions.d_mm is None
    result = update(service, [ch("dimensions.d_mm", 25, "内径25mm", "mm")], "轴承内径25mm", session="persist")
    assert result.revision == 1
    again = SQLiteDesignBriefStore(tmp_path / "brief.sqlite3")
    restored, revision = again.get_brief("persist")
    assert revision == 1
    assert restored.dimensions.d_mm.value == 25
    assert restored.dimensions.d_mm.source.message_id == "m1"


def test_batch_three_dimensions_one_revision(service):
    evidence = "25×52×15"
    out = update(service, [
        ch("dimensions.d_mm", 25, evidence, "mm"),
        ch("dimensions.D_mm", 52, evidence, "mm"),
        ch("dimensions.B_mm", 15, evidence, "mm"),
    ], "深沟球轴承尺寸25×52×15")
    assert out.revision == 1
    assert out.applied_changes == ["dimensions.d_mm", "dimensions.D_mm", "dimensions.B_mm"]
    brief, _ = service.get_brief("s1")
    assert [brief.dimensions.d_mm.value, brief.dimensions.D_mm.value, brief.dimensions.B_mm.value] == [25, 52, 15]


def test_equal_value_no_revision_growth(service):
    data = [ch("dimensions.d_mm", 25, "内径25", "mm")]
    first = update(service, data, "内径25")
    second = update(service, data, "内径25", message_id="m2")
    assert first.revision == 1 and second.revision == 1
    assert not second.applied_changes


def test_replace_value_updates_revision(service):
    update(service, [ch("operating.inner_speed_rpm", 15000, "内圈15000rpm", "rpm")], "内圈15000rpm")
    changed = update(service, [ch("operating.inner_speed_rpm", 18000, "内圈转速改为18000rpm", "rpm")],
                     "内圈转速改为18000rpm", operation="replace", message_id="m2")
    assert changed.revision == 2
    assert service.get_brief("s1")[0].operating.inner_speed_rpm.value == 18000


def test_set_occupied_field_rejected(service):
    update(service, [ch("dimensions.d_mm", 25, "内径25", "mm")], "内径25")
    out = update(service, [ch("dimensions.d_mm", 30, "内径30", "mm")], "内径30")
    assert out.revision == 1
    assert out.rejected_changes
    assert service.get_brief("s1")[0].dimensions.d_mm.value == 25


def test_replace_missing_rejected(service):
    out = update(service, [ch("dimensions.d_mm", 25, "内径25", "mm")], "内径25", operation="replace")
    assert out.revision == 0 and out.rejected_changes


def test_atomic_reject_invalid_mid_batch(service):
    out = update(service, [
        ch("dimensions.d_mm", 25, "内径25", "mm"),
        ch("dimensions.D_mm", 52, "外径52", "mm"),
        ch("engineering.magic_parameter", 1, "1"),
    ], "内径25 外径52 1")
    assert out.revision == 0
    brief, revision = service.get_brief("s1")
    assert revision == 0 and brief.dimensions.d_mm is None


def test_atomic_reject_geometry_inconsistency(service):
    out = update(service, [ch("dimensions.d_mm", 52, "内径52", "mm"),
                           ch("dimensions.D_mm", 25, "外径25", "mm")], "内径52 外径25")
    assert out.rejected_changes
    assert service.get_brief("s1")[0].dimensions.d_mm is None


def test_unknown_vs_explicit_zero(service):
    assert "operating.axial_load_n" in service.get_design_status("s1").missing
    out = update(service, [ch("operating.axial_load_n", 0, "无轴向载荷", "N")], "无轴向载荷")
    assert out.revision == 1
    assert out.design_status.known["operating.axial_load_n"]["value"] == 0
    assert "operating.axial_load_n" not in out.design_status.missing


def test_outer_ring_fixed_is_zero_not_fabrication(service):
    out = update(service, [ch("operating.outer_speed_rpm", 0, "外圈固定", "rpm")], "外圈固定")
    assert not out.rejected_changes
    assert out.design_status.known["operating.outer_speed_rpm"]["value"] == 0


def test_approximate_is_not_confirmed(service):
    out = update(service, [ch("operating.inner_speed_rpm", 18000, "大约18000rpm", "rpm", "approximate")], "内圈大约18000rpm")
    assert out.design_status.known["operating.inner_speed_rpm"]["precision"] == "approximate"
    assert not out.design_status.known["operating.inner_speed_rpm"]["confirmed"]
    assert "operating.inner_speed_rpm" in out.design_status.pending_confirmation


def test_exact_misreads_approximate_rejected(service):
    out = update(service, [ch("operating.inner_speed_rpm", 18000, "大约18000rpm", "rpm")], "内圈大约18000rpm")
    assert out.rejected_changes


def test_no_unsupported_numeric_evidence(service):
    out = update(service, [ch("operating.inner_speed_rpm", 18000, "内圈15000rpm", "rpm")], "内圈15000rpm")
    assert out.rejected_changes


def test_bore_cannot_be_inferred_from_shaft_diameter(service):
    out = update(service, [ch("dimensions.d_mm", 25, "轴径25", "mm")], "轴径25")
    assert out.rejected_changes


def test_motor_speed_cannot_be_inner_speed_without_ring_context(service):
    out = update(service, [ch("operating.inner_speed_rpm", 15000, "电机15000转", "rpm")], "电机15000转")
    assert out.rejected_changes


def test_no_evidence_no_confirmation(service):
    out = update(service, [ch("dimensions.d_mm", 25, "内径25", "mm")], "电机15000转")
    assert out.rejected_changes


def test_units_normalized_without_guessed_defaults(service):
    out = update(service, [ch("dimensions.d_mm", 2.5, "内径2.5cm", "cm"),
                           ch("operating.radial_load_n", 0.3, "径向载荷0.3kN", "kN")],
                 "轴承内径2.5cm,径向载荷0.3kN")
    assert out.design_status.known["dimensions.d_mm"]["value"] == 25
    assert out.design_status.known["operating.radial_load_n"]["value"] == pytest.approx(300)
    fail = update(service, [ch("dimensions.B_mm", 15, "宽15")], "宽15")
    assert fail.rejected_changes


@pytest.mark.parametrize("bad", [True, -10, float("nan"), float("inf"), "25"])
def test_numeric_invalid_inputs(service, bad):
    out = update(service, [ch("dimensions.d_mm", bad, "内径25", "mm")], "内径25")
    assert out.rejected_changes


def test_clear_requires_explicit_withdrawal(service):
    update(service, [ch("dimensions.d_mm", 25, "内径25", "mm")], "内径25")
    yes = update(service, [ch("dimensions.d_mm", None, "内径撤销", "mm")], "内径撤销", operation="replace")
    assert yes.revision == 2
    assert service.get_brief("s1")[0].dimensions.d_mm is None
    no = update(service, [ch("dimensions.d_mm", None, "不想", "mm")], "不想", operation="replace")
    assert no.rejected_changes


def test_optimization_slots_lock_and_keep_rest(service):
    out = update(service, [ch("optimization_slots.Z", {"mode": "locked", "value": 10}, "Z=10")], "锁定Z=10")
    assert out.revision == 1
    brief, _ = service.get_brief("s1")
    assert brief.optimization_slots.Z.mode == "locked"
    assert brief.optimization_slots.Z.value == 10
    assert all(getattr(brief.optimization_slots, k).mode == "optimize" for k in ("Dw_mm", "Dpw_mm", "fi", "fo"))


def test_invalid_ball_count_rejected(service):
    out = update(service, [ch("optimization_slots.Z", {"mode": "locked", "value": 10.5}, "Z=10.5")], "Z=10.5")
    assert out.rejected_changes


def test_unknown_or_system_field_rejected(service):
    out = update(service, [ch("solver_context.mode", -1, "mode -1")], "mode -1")
    assert out.rejected_changes
    assert service.get_brief("s1")[0].solver_context.mode == -1


def test_multiple_sessions_isolated(service):
    update(service, [ch("dimensions.d_mm", 25, "内径25", "mm")], "内径25", session="a")
    assert service.get_brief("b")[0].dimensions.d_mm is None


def test_source_is_server_owned(service):
    out = update(service, [ch("dimensions.d_mm", 25, "内径25", "mm")], "内径25", message_id="trusted-id")
    assert out.revision == 1
    brief, _ = service.get_brief("s1")
    assert isinstance(brief.dimensions.d_mm, ParameterValue)
    assert brief.dimensions.d_mm.source.message_id == "trusted-id"
    assert brief.dimensions.d_mm.source.kind == "user"


def test_wrong_unit_cannot_transform_explicit_mm_into_cm(service):
    out = update(service, [ch("dimensions.d_mm", 25, "轴承内径25mm", "cm")], "轴承内径25mm")
    assert out.rejected_changes
    assert service.get_brief("s1")[0].dimensions.d_mm is None


def test_wrong_temperature_unit_rejected(service):
    out = update(service, [ch("operating.temperature_c", 60, "温度60℃", "K")], "温度60℃")
    assert out.rejected_changes


def test_correct_unit_conversion_respects_explicit_evidence(service):
    out = update(service, [ch("dimensions.d_mm", 2.5, "内径2.5cm", "cm")], "轴承内径2.5cm")
    assert out.revision == 1
    assert out.design_status.known["dimensions.d_mm"]["value"] == 25
