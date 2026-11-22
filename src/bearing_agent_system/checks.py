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

    # Choice between group OR numerical clearance, not both required.
    if brief.engineering.clearance.group is None and brief.engineering.clearance.initial_radial_clearance_mm is None:
        missing.append("engineering.clearance")

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
