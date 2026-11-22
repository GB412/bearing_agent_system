from __future__ import annotations

from bearing_agent_system import TrustedContext, UpdateBatch


def up(service, path, value, evidence, unit=None, precision="exact"):
    return service.update_design_brief("case", UpdateBatch.model_validate({"operation": "set", "changes": [
        {"path": path, "value": value, "unit": unit, "precision": precision, "evidence_span": evidence}
    ]}), TrustedContext(message_id="msg", user_message=evidence))


def test_initial_missing_does_not_include_optimizer(service):
    status = service.get_design_status("case")
    assert "dimensions.d_mm" in status.missing
    assert "operating.axial_load_n" in status.missing
    assert "engineering.clearance" in status.missing
    assert not any(p.startswith("optimization_slots") for p in status.missing)
    assert not any(p.startswith("solver_context") for p in status.missing)
    assert status.known["bearing.type"] == "DGB"


def test_clearance_group_is_not_numeric_clearance(service):
    out = up(service, "engineering.clearance.group", "C3", "游隙C3")
    assert "engineering.clearance" not in out.design_status.missing
    assert "engineering.clearance.initial_radial_clearance_mm" not in out.design_status.known
    assert out.design_status.known["engineering.clearance.group"]["value"] == "C3"


def test_bound_not_fixed_dimension(service):
    out = up(service, "requirements.geometric_bounds[]", {
        "field": "dimensions.D_mm", "operator": "<=", "value": 52, "unit": "mm"
    }, "外径不超过52mm")
    assert not out.rejected_changes
    brief, _ = service.get_brief("case")
    assert brief.dimensions.D_mm is None
    assert brief.requirements.geometric_bounds[0].value == 52
    assert "dimensions.D_mm" in out.design_status.missing


def test_geometric_requirement_conflict_is_reported(service):
    up(service, "dimensions.D_mm", 60, "外径60mm", "mm")
    out = up(service, "requirements.geometric_bounds[]", {
        "field": "dimensions.D_mm", "operator": "<=", "value": 52, "unit": "mm"
    }, "外径不超过52mm")
    assert out.design_status.conflicts


def test_preferences_and_hard_constraints_have_separate_containers(service):
    target = up(service, "requirements.preferences[]", {
        "field": "power_loss", "operator": "minimize", "value": None
    }, "希望功耗尽可能低")
    assert not target.rejected_changes
    goal = up(service, "requirements.constraints[]", {
        "field": "life_hours", "operator": ">=", "value": 10000, "unit": "h"
    }, "寿命至少10000小时")
    assert not goal.rejected_changes
    brief, _ = service.get_brief("case")
    assert len(brief.requirements.preferences) == 1
    assert len(brief.requirements.constraints) == 1
    assert brief.requirements.constraints[0].value == 10000


def test_approximate_and_missing_are_distinct(service):
    out = up(service, "operating.temperature_c", 60, "工作温度大约60℃", "℃", "approximate")
    assert "operating.temperature_c" in out.design_status.pending_confirmation
    assert "operating.temperature_c" not in out.design_status.missing
    assert "operating.axial_load_n" in out.design_status.missing


def test_requirement_append_is_not_duplicate_on_replay(service):
    first = up(service, "requirements.geometric_bounds[]", {
        "field": "dimensions.D_mm", "operator": "<=", "value": 52, "unit": "mm"
    }, "外径不超过52mm")
    second = up(service, "requirements.geometric_bounds[]", {
        "field": "dimensions.D_mm", "operator": "<=", "value": 52, "unit": "mm"
    }, "外径不超过52mm")
    assert first.revision == second.revision == 1
    assert len(service.get_brief("case")[0].requirements.geometric_bounds) == 1
