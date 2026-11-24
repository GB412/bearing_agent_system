"""PR-03 partial validation: preserve trusted independent updates and geometry."""

from __future__ import annotations

from bearing_agent_system.models import TrustedContext, UpdateBatch
from bearing_agent_system.reply_guard import reconcile_writes, verified_reply


def send(service, message, changes, operation="set", session="partial"):
    batch = UpdateBatch.model_validate({"operation": operation, "changes": changes})
    return service.update_design_brief(
        session, batch, TrustedContext(message_id="test", user_message=message)
    )


def ch(path, value, evidence, unit=None):
    return {"path": path, "value": value, "unit": unit, "evidence_span": evidence}


def test_exact_real_dialogue_saves_eight_valid_fields_if_clearance_bad(service):
    message = (
        "内圈转速 18000 rpm，宽度10mm,套圈和球材料用 GCr15，"
        "保持架也用这个，内外圈配合K6,游隙组别CN"
    )
    # User intended 8 unambiguous values. The candidate for CN is intentionally
    # wrong; accepting the others must not depend on whether the LLM fixes CN.
    changes = [
        ch("operating.inner_speed_rpm", 18000, "内圈转速 18000 rpm", "rpm"),
        ch("dimensions.B_mm", 10, "宽度10mm", "mm"),
        ch("engineering.materials.inner_ring_id", "GCr15", "套圈和球材料用 GCr15"),
        ch("engineering.materials.outer_ring_id", "GCr15", "套圈和球材料用 GCr15"),
        ch("engineering.materials.ball_id", "GCr15", "套圈和球材料用 GCr15"),
        ch("engineering.cage.material_id", "GCr15", "保持架也用这个"),
        ch("engineering.fits.inner_ring", "K6", "内外圈配合K6"),
        ch("engineering.fits.outer_ring", "K6", "内外圈配合K6"),
        ch("engineering.clearance.group", "C3", "游隙组别CN"),
    ]
    result = send(service, message, changes)
    assert result.revision == 1
    assert result.applied_changes
    assert result.rejected_changes
    assert result.rejected_changes[0]["path"] == "engineering.clearance.group"
    saved, revision = service.get_brief("partial")
    assert revision == 1
    assert saved.operating.inner_speed_rpm.value == 18000
    assert saved.dimensions.B_mm.value == 10
    assert saved.engineering.materials.inner_ring_id.value == "GCr15"
    assert saved.engineering.clearance.group is None


def test_failed_unit_and_good_load_commit_in_same_revision(service):
    result = send(service, "内径25mm，外径52mm，载荷300N", [
        ch("dimensions.d_mm", 25, "内径25mm", "cm"),
        ch("dimensions.D_mm", 52, "外径52mm", "mm"),
        ch("operating.radial_load_n", 300, "载荷300N", "N"),
    ])
    assert result.revision == 1
    assert result.applied_changes == ["dimensions.D_mm", "operating.radial_load_n"]
    assert result.rejected_changes[0]["path"] == "dimensions.d_mm"
    brief, _ = service.get_brief("partial")
    assert brief.dimensions.d_mm is None
    assert brief.dimensions.D_mm.value == 52
    assert brief.operating.radial_load_n.value == 300


def test_coupled_dimensions_roll_back_without_losing_unrelated_width(service):
    result = send(service, "内径52mm，外径25mm，宽10mm", [
        ch("dimensions.d_mm", 52, "内径52mm", "mm"),
        ch("dimensions.D_mm", 25, "外径25mm", "mm"),
        ch("dimensions.B_mm", 10, "宽10mm", "mm"),
    ])
    assert result.applied_changes == ["dimensions.B_mm"]
    assert set(item["path"] for item in result.rejected_changes) == {
        "dimensions.d_mm", "dimensions.D_mm",
    }
    brief, revision = service.get_brief("partial")
    assert revision == 1
    assert brief.dimensions.d_mm is None
    assert brief.dimensions.D_mm is None
    assert brief.dimensions.B_mm.value == 10


def test_simultaneous_dimension_replacement_checks_final_geometry(service):
    first = send(service, "内径25mm，外径52mm", [
        ch("dimensions.d_mm", 25, "内径25mm", "mm"),
        ch("dimensions.D_mm", 52, "外径52mm", "mm"),
    ])
    assert first.revision == 1
    result = send(service, "内径60mm，外径72mm", [
        ch("dimensions.d_mm", 60, "内径60mm", "mm"),
        ch("dimensions.D_mm", 72, "外径72mm", "mm"),
    ], operation="replace")
    assert result.revision == 2
    assert not result.rejected_changes
    brief, _ = service.get_brief("partial")
    assert brief.dimensions.d_mm.value == 60
    assert brief.dimensions.D_mm.value == 72


def test_mixed_result_receipt_does_not_claim_everything_failed():
    trace = [{
        "name": "update_design_brief", "ok": False,
        "attempted_paths": ["dimensions.B_mm", "engineering.clearance.group"],
        "applied_changes": ["dimensions.B_mm"],
        "rejected_changes": [{
            "path": "engineering.clearance.group", "reason": "unconfirmed"
        }],
    }]
    outcome = reconcile_writes(trace)
    assert outcome.applied == ("dimensions.B_mm",)
    assert outcome.unresolved == (("engineering.clearance.group", "unconfirmed"),)
    result = verified_reply(
        "我需要再确认游隙。", trace,
        {"known": {"dimensions.B_mm": {
            "value": 10, "unit": "mm", "confirmed": True, "precision": "exact"
        }}, "missing": [], "pending_confirmation": [], "conflicts": []},
    )
    assert "本轮实际已写入：宽度 B=10mm" in result
    assert "本轮仍未保存：engineering.clearance.group" in result
    assert "同批更新未通过校验" not in result
