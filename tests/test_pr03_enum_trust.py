"""Security regressions: a syntactically valid enum is not a user decision."""

from __future__ import annotations

import pytest

from bearing_agent_system.models import TrustedContext, UpdateBatch


def update(service, message: str, path: str, value: str, evidence: str | None = None):
    batch = UpdateBatch.model_validate({
        "operation": "set",
        "changes": [{
            "path": path, "value": value, "evidence_span": evidence or message,
            "precision": "exact",
        }],
    })
    return service.update_design_brief(
        "enum-case", batch, TrustedContext(message_id="m1", user_message=message)
    )


@pytest.mark.parametrize("message,path,value,evidence", [
    ("采用脂润滑", "engineering.lubrication.mode", "oil", None),
    ("油润滑和脂润滑有什么区别？", "engineering.lubrication.mode", "oil", "油润滑"),
    ("游隙还没确定，只想了解C3", "engineering.clearance.group", "C3", "C3"),
    ("我不想采用C3", "engineering.clearance.group", "C3", None),
    ("暂时不选择润滑方式，先了解脂润滑", "engineering.lubrication.mode",
     "grease", "脂润滑"),
    ("C3是什么意思？", "engineering.clearance.group", "C3", "C3"),
    ("我还没确定游隙，C3是什么？", "engineering.clearance.group", "C3", "C3"),
    ("不要采用油润滑", "engineering.lubrication.mode", "oil", None),
])
def test_untrusted_enum_choice_rejected(service, message, path, value, evidence):
    result = update(service, message, path, value, evidence)
    assert result.rejected_changes
    assert result.revision == 0
    assert service.get_brief("enum-case")[1] == 0
    assert service.get_brief("enum-case")[0].engineering.lubrication.mode is None
    assert service.get_brief("enum-case")[0].engineering.clearance.group is None


@pytest.mark.parametrize("message,path,value,evidence", [
    ("采用脂润滑", "engineering.lubrication.mode", "grease", None),
    ("采用油润滑", "engineering.lubrication.mode", "oil", None),
    ("润滑方式：脂润滑", "engineering.lubrication.mode", "grease", None),
    ("油润滑", "engineering.lubrication.mode", "oil", None),
    ("游隙就选C3", "engineering.clearance.group", "C3", None),
    ("游隙选CN", "engineering.clearance.group", "CN", None),
    ("不选C3，游隙选CN", "engineering.clearance.group", "CN", "游隙选CN"),
])
def test_user_selected_enum_accepted(service, message, path, value, evidence):
    result = update(service, message, path, value, evidence)
    assert not result.rejected_changes, result.rejected_changes
    assert result.revision == 1
    stored = service.get_brief("enum-case")[0]
    item = (stored.engineering.lubrication.mode if "lubrication" in path
            else stored.engineering.clearance.group)
    assert item.value == value
    assert item.confirmed
