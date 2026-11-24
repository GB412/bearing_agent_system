"""Deterministic, minimal known/missing/pending/conflicts checker."""

from __future__ import annotations

from .models import DesignBrief, DesignStatus, ParameterValue
from .parameter_catalog import FIELDS, get_path_value


def get_design_status(brief: DesignBrief) -> DesignStatus:
    known: dict[str, object] = {"bearing.type": "DGB"}
    missing: list[str] = []
    pending: list[str] = []
    conflicts: list[str] = []

    for path, spec in FIELDS.items():
        if spec.kind in ("requirement", "slot"):
            continue
        value = get_path_value(brief, path)
        if value is None:
            if spec.required:
                missing.append(path)
            continue
        if isinstance(value, ParameterValue):
            known[path] = {
                "value": value.value,
                "unit": value.unit,
                "precision": value.precision,
                "confirmed": value.confirmed,
            }
            if not value.confirmed or value.precision != "exact":
                pending.append(path)

    # Expose active constraints with server-owned IDs so future Agent turns can
    # replace/withdraw the correct item without treating history as business state.
    for group in ("constraints", "preferences", "geometric_bounds"):
        values = getattr(brief.requirements, group)
        if values:
            known[f"requirements.{group}[]"] = [
                {"id": item.id, "field": item.field, "operator": item.operator,
                 "value": item.value, "unit": item.unit}
                for item in values
            ]
    for name in ("Dw_mm", "Z", "Dpw_mm", "fi", "fo"):
        slot = getattr(brief.optimization_slots, name)
        if slot.mode != "optimize":
            known[f"optimization_slots.{name}"] = {
                "mode": slot.mode, "value": slot.value, "bounds": slot.bounds
            }

    d, D = brief.dimensions.d_mm, brief.dimensions.D_mm
    if d is not None and D is not None and d.value >= D.value:
        conflicts.append("dimensions.d_mm must be smaller than dimensions.D_mm")
    for bound in brief.requirements.geometric_bounds:
        actual = get_path_value(brief, bound.field)
        if actual is None or not actual.confirmed or bound.value is None:
            continue
        lhs, rhs = actual.value, bound.value
        valid = {
            "<": lhs < rhs, "<=": lhs <= rhs, "=": lhs == rhs,
            ">=": lhs >= rhs, ">": lhs > rhs,
        }[bound.operator]
        if not valid:
            conflicts.append(f"{bound.field} contradicts user geometric bound {bound.operator}{rhs}")

    return DesignStatus(known=known, missing=missing, pending_confirmation=pending, conflicts=conflicts)
