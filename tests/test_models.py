import math

import pytest
from pydantic import ValidationError

from bearing_agent_system.models import DesignBrief, OptimizationSlot, UpdateBatch


def test_empty_brief_has_five_unlocked_optimization_slots():
    brief = DesignBrief()
    assert brief.schema_version == "DGBDesignBrief/v1"
    assert brief.bearing.type == "DGB"
    for field in ("Dw_mm", "Z", "Dpw_mm", "fi", "fo"):
        slot = getattr(brief.optimization_slots, field)
        assert slot.mode == "optimize"
        assert slot.value is None
        assert slot.bounds is None
    assert brief.solver_context.mode == -1
    assert brief.solver_context.profile_ref is None


@pytest.mark.parametrize("bad", [
    {"mode": "locked", "value": None},
    {"mode": "locked", "value": float("nan")},
    {"mode": "bounded", "bounds": (10, 10)},
    {"mode": "bounded", "bounds": (math.inf, 10)},
    {"mode": "optimize", "value": 5},
    {"mode": "locked", "value": True},
    {"mode": "bounded", "bounds": (True, 10)},
])
def test_invalid_slot_rejected(bad):
    with pytest.raises(ValidationError):
        OptimizationSlot.model_validate(bad)


def test_unknown_model_field_forbidden():
    with pytest.raises(ValidationError):
        DesignBrief.model_validate({"mystery": 1})
    with pytest.raises(ValidationError):
        DesignBrief.model_validate({"bearing": {"type": "ACBB"}})


def test_tool_payload_cannot_set_confirmed_or_origin():
    with pytest.raises(ValidationError):
        UpdateBatch.model_validate({"operation": "set", "changes": [
            {"path": "dimensions.d_mm", "value": 25, "unit": "mm", "confirmed": True, "evidence_span": "25"}
        ]})
    with pytest.raises(ValidationError):
        UpdateBatch.model_validate({"operation": "set", "changes": [
            {"path": "dimensions.d_mm", "value": 25, "unit": "mm", "source": {"kind": "user"}, "evidence_span": "25"}
        ]})


def test_duplicate_batch_paths_forbidden():
    with pytest.raises(ValidationError):
        UpdateBatch.model_validate({"operation": "set", "changes": [
            {"path": "dimensions.d_mm", "value": 25, "unit": "mm", "evidence_span": "25"},
            {"path": "dimensions.d_mm", "value": 26, "unit": "mm", "evidence_span": "26"},
        ]})
