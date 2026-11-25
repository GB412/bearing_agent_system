"""PR-03: exact RoBAS names, canonical IDs and recommendation safety."""

from __future__ import annotations

import json

import pytest

from bearing_agent_system.agent_tools import TurnTools
from bearing_agent_system.catalog_choices import CatalogChoices
from bearing_agent_system.models import TrustedContext, UpdateBatch
from bearing_agent_system.parameter_catalog import InvalidChange


def user_update(service, path, name, message, operation="set", session="s"):
    return service.update_design_brief(
        session,
        UpdateBatch.model_validate({
            "operation": operation,
            "changes": [{"path": path, "value": name, "evidence_span": message}],
        }),
        TrustedContext(message_id="u1", user_message=message),
    )


def test_user_exact_name_resolves_to_database_id(service):
    result = user_update(
        service, "engineering.materials.inner_ring_id",
        "高碳铬轴承钢", "内圈采用高碳铬轴承钢"
    )
    assert result.applied_changes == ["engineering.materials.inner_ring_id"]
    assert not result.rejected_changes
    assert service.get_brief("s")[0].engineering.materials.inner_ring_id.value == (
        "material:高碳铬轴承钢"
    )


def test_exact_case_and_alias_are_not_silently_inferred(service):
    bad = user_update(
        service, "engineering.materials.inner_ring_id",
        "高碳鉻軸承鋼", "内圈采用高碳鉻軸承鋼"
    )
    assert bad.rejected_changes
    assert "CATALOG_NOT_FOUND" in bad.rejected_changes[0]["reason"]
    assert service.get_brief("s")[1] == 0
    # GCr15 is a separate fixture record; do not auto-conflate it with another
    # name merely because a model believes they may have similar properties.
    ok = user_update(
        service, "engineering.materials.inner_ring_id",
        "GCr15", "内圈采用GCr15"
    )
    assert not ok.rejected_changes
    assert service.get_brief("s")[0].engineering.materials.inner_ring_id.value == (
        "material:GCr15"
    )


def test_unlisted_material_cannot_enter_brief(service):
    bad = user_update(
        service, "engineering.materials.ball_id",
        "想象材料X", "钢球使用想象材料X",
    )
    assert bad.rejected_changes
    assert service.get_brief("s")[0].engineering.materials.ball_id is None


def test_material_id_cannot_be_used_as_lubricant(service):
    bad = user_update(
        service, "engineering.lubrication.lubricant_id",
        "material:GCr15", "润滑剂使用material:GCr15",
    )
    assert bad.rejected_changes


def test_lubricant_exact_name_is_saved_as_catalog_id(service):
    result = user_update(
        service, "engineering.lubrication.lubricant_id",
        "VG32", "润滑剂采用VG32",
    )
    assert not result.rejected_changes
    assert service.get_brief("s")[0].engineering.lubrication.lubricant_id.value == (
        "lubricant:VG32"
    )


def test_missing_catalog_blocks_only_catalog_choices(service, tmp_path):
    service.store.catalog_choices = CatalogChoices(tmp_path / "missing.json")
    failed = user_update(service, "engineering.materials.ball_id",
                         "GCr15", "钢球采用GCr15")
    assert "CATALOG_UNAVAILABLE" in failed.rejected_changes[0]["reason"]
    valid = service.update_design_brief(
        "s",
        UpdateBatch.model_validate({
            "operation": "set",
            "changes": [{"path": "dimensions.d_mm", "value": 25, "unit": "mm",
                         "evidence_span": "内径25mm"}],
        }),
        TrustedContext(message_id="u2", user_message="内径25mm"),
    )
    assert not valid.rejected_changes
    assert service.get_brief("s")[0].dimensions.d_mm.value == 25


def test_proposal_and_later_adoption_normalize_to_catalog_id(service):
    proposed = service.store.propose_recommendation(
        "s", [{"path": "engineering.materials.inner_ring_id",
               "value": "高碳铬轴承钢"}], "t1"
    )
    assert proposed["changes"][0]["value"] == "material:高碳铬轴承钢"
    assert service.get_brief("s")[0].engineering.materials.inner_ring_id is None

    accepted = service.store.adopt_recommendation(
        "s", proposed["proposal_id"],
        TrustedContext(message_id="t2", user_message="就按你推荐的来"),
    )
    assert accepted.applied_changes == ["engineering.materials.inner_ring_id"]
    assert service.get_brief("s")[0].engineering.materials.inner_ring_id.value == (
        "material:高碳铬轴承钢"
    )


def test_proposal_rejects_unlisted_material_and_lubricant(service):
    for path in ("engineering.materials.inner_ring_id",
                 "engineering.lubrication.lubricant_id",
                 "engineering.cage.material_id"):
        with pytest.raises(InvalidChange, match="CATALOG_NOT_FOUND"):
            service.store.propose_recommendation(
                "s", [{"path": path, "value": "fictional-X"}], "t1"
            )
    assert service.store.pending_recommendation("s") is None


def test_adoption_fails_if_catalog_record_removed(service, catalog_path):
    p = service.store.propose_recommendation(
        "s", [{"path": "engineering.lubrication.lubricant_id",
               "value": "VG32"}], "t1"
    )
    data = json.loads(catalog_path.read_text("utf-8"))
    data["lubricants"] = []
    catalog_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(InvalidChange, match="CATALOG_NOT_FOUND"):
        service.store.adopt_recommendation(
            "s", p["proposal_id"],
            TrustedContext(message_id="t2", user_message="就按你推荐的来"),
        )
    assert service.get_brief("s")[1] == 0


def test_duplicate_catalog_names_fail_closed(service, catalog_path):
    data = json.loads(catalog_path.read_text("utf-8"))
    data["materials"].append({
        "id": "material:duplicate", "name": "GCr15",
        "values_raw": {}, "source_fields": {},
    })
    catalog_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    result = user_update(service, "engineering.materials.ball_id",
                         "GCr15", "钢球采用GCr15")
    assert result.rejected_changes
    assert "CATALOG_ERROR" in result.rejected_changes[0]["reason"]
    assert service.get_brief("s")[1] == 0


def test_exact_selection_rejected_if_not_in_current_user_text(service):
    result = user_update(service, "engineering.materials.inner_ring_id",
                         "高碳铬轴承钢", "内圈材料已经决定")
    assert result.rejected_changes


def test_existing_lubrication_mode_does_not_need_catalog(service, tmp_path):
    service.store.catalog_choices = CatalogChoices(tmp_path / "missing.json")
    result = user_update(service, "engineering.lubrication.mode",
                         "grease", "选择脂润滑")
    assert not result.rejected_changes
    assert service.get_brief("s")[0].engineering.lubrication.mode.value == "grease"


def test_real_agent_tool_rejects_fictional_option(service):
    t = TurnTools(
        service=service, session_id="proposal-test", message_id="m1",
        user_message="帮我推荐材料",
    )
    result = t.tools()[0].invoke({
        "operation": "propose", "changes": [
            {"path": "engineering.materials.inner_ring_id", "value": "fictional-X"}
        ],
    })
    assert not result["ok"]
    assert service.get_brief("proposal-test")[1] == 0
