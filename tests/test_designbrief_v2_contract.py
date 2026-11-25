"""V2 user-layer contract: fitted/clearance parameters are not part of the brief."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from bearing_agent_system.agent_tools import TurnTools
from bearing_agent_system.models import Cage, DesignBrief, Engineering
from bearing_agent_system.parameter_catalog import FIELDS

REMOVED = (
    "engineering.cage.type",
    "engineering.clearance.group",
    "engineering.clearance.initial_radial_clearance_mm",
    "engineering.fits.inner_ring",
    "engineering.fits.outer_ring",
)


def test_new_brief_serialization_does_not_have_removed_subtrees(service):
    brief, revision = service.get_brief("new-session")
    assert revision == 0
    assert brief.schema_version == "DGBDesignBrief/v2"
    assert "type" not in brief.engineering.cage.model_dump()
    assert len(service.get_design_status("new-session").missing) == 14
    assert set(brief.model_dump(mode="json")["engineering"]) == {
        "materials", "cage", "lubrication"
    }
    assert all(path not in FIELDS for path in REMOVED)
    status = service.get_design_status("new-session")
    assert not any(
        path.startswith("engineering.clearance") or path.startswith("engineering.fits")
        for path in status.missing + status.pending_confirmation + list(status.known)
    )
    assert "requirements.constraints[]" in FIELDS
    assert "requirements.preferences[]" in FIELDS
    assert all("optimization_slots." + name in FIELDS
               for name in ("Dw_mm", "Z", "Dpw_mm", "fi", "fo"))


def test_v2_rejects_unknown_nested_keys_and_old_schema_version():
    for key, value in (
        ("clearance", {"group": None}),
        ("fits", {"inner_ring": None}),
    ):
        with pytest.raises(ValidationError):
            Engineering.model_validate({key: value})
    with pytest.raises(ValidationError):
        Cage.model_validate({"type": None})
    with pytest.raises(ValidationError):
        DesignBrief.model_validate({"schema_version": "DGBDesignBrief/v1"})


def test_tool_no_longer_advertises_deleted_fields(service):
    tools = TurnTools(
        service=service,
        session_id="s",
        message_id="m",
        user_message="设计目标是功耗最低",
    ).tools()
    write_description = tools[0].description
    assert all(path not in write_description for path in REMOVED)
    assert "requirements.constraints[]" in write_description
    assert "requirements.preferences[]" in write_description
    assert "optimization_slots.Dw_mm" in write_description


def test_deleted_choices_cannot_be_proposed_as_default(service):
    tools = TurnTools(
        service=service,
        session_id="s",
        message_id="m",
        user_message="配合你来推荐",
    ).tools()
    for path in REMOVED:
        result = tools[0].invoke({
            "operation": "propose", "changes": [
                {"path": path, "value": "CN"},
            ],
        })
        assert not result["ok"]
    assert service.store.pending_recommendation("s") is None
    assert service.get_brief("s")[1] == 0


@pytest.mark.parametrize("operation", ["set", "replace"])
def test_cage_type_cannot_be_written_but_material_can(service, operation):
    turn = TurnTools(
        service=service, session_id="cage-material", message_id="m",
        user_message="保持架类型采用stamping，保持架材料用GCr15",
    )
    result = turn.tools()[0].invoke({
        "operation": operation, "changes": [
            {"path": "engineering.cage.type", "value": "stamping",
             "evidence_span": "保持架类型采用stamping"},
        ],
    })
    assert not result["ok"]
    assert service.get_brief("cage-material")[1] == 0
    saved = turn.tools()[0].invoke({
        "operation": "set", "changes": [
            {"path": "engineering.cage.material_id", "value": "GCr15",
             "evidence_span": "保持架材料用GCr15"},
        ],
    })
    assert saved["ok"]
    cage = service.get_brief("cage-material")[0].engineering.cage
    assert cage.material_id.value == "material:GCr15"
    assert "type" not in cage.model_dump()
