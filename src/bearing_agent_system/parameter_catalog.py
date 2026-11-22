"""Single authoritative user-facing DGB field catalog and value normalization."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Literal

from .models import OptimizationSlot, ParameterValue, Requirement, Source, TrustedContext, UpdateChange


@dataclass(frozen=True)
class FieldSpec:
    kind: Literal["number", "integer", "string", "enum", "slot", "requirement"]
    unit: str | None = None
    required: bool = False
    choices: tuple[str, ...] = ()
    positive: bool = False
    nonnegative: bool = False


# No RoBAS DATA record positions or solver defaults belong in this catalog.
FIELDS: dict[str, FieldSpec] = {
    "bearing.application": FieldSpec("string"),
    "bearing.model": FieldSpec("string"),
    "dimensions.d_mm": FieldSpec("number", "mm", required=True, positive=True),
    "dimensions.D_mm": FieldSpec("number", "mm", required=True, positive=True),
    "dimensions.B_mm": FieldSpec("number", "mm", required=True, positive=True),
    "operating.inner_speed_rpm": FieldSpec("number", "rpm", required=True, nonnegative=True),
    "operating.outer_speed_rpm": FieldSpec("number", "rpm", required=True, nonnegative=True),
    "operating.radial_load_n": FieldSpec("number", "N", required=True, nonnegative=True),
    "operating.axial_load_n": FieldSpec("number", "N", required=True, nonnegative=True),
    "operating.temperature_c": FieldSpec("number", "degC", required=True),
    "operating.axial_load_direction": FieldSpec("string"),
    "operating.rotation_direction": FieldSpec("string"),
    "operating.misalignment": FieldSpec("string"),
    "operating.moments": FieldSpec("string"),
    "operating.mounting_orientation": FieldSpec("string"),
    "engineering.materials.inner_ring_id": FieldSpec("string", required=True),
    "engineering.materials.outer_ring_id": FieldSpec("string", required=True),
    "engineering.materials.ball_id": FieldSpec("string", required=True),
    "engineering.cage.type": FieldSpec("string", required=True),
    "engineering.cage.material_id": FieldSpec("string", required=True),
    "engineering.lubrication.mode": FieldSpec("enum", choices=("oil", "grease", "other"), required=True),
    "engineering.lubrication.lubricant_id": FieldSpec("string", required=True),
    "engineering.clearance.group": FieldSpec("enum", choices=("C2", "CN", "C3", "C4", "C5")),
    "engineering.clearance.initial_radial_clearance_mm": FieldSpec("number", "mm", nonnegative=True),
    "engineering.fits.inner_ring": FieldSpec("string", required=True),
    "engineering.fits.outer_ring": FieldSpec("string", required=True),
    "requirements.constraints[]": FieldSpec("requirement"),
    "requirements.preferences[]": FieldSpec("requirement"),
    "requirements.geometric_bounds[]": FieldSpec("requirement"),
    "optimization_slots.Dw_mm": FieldSpec("slot", "mm"),
    "optimization_slots.Z": FieldSpec("slot"),
    "optimization_slots.Dpw_mm": FieldSpec("slot", "mm"),
    "optimization_slots.fi": FieldSpec("slot"),
    "optimization_slots.fo": FieldSpec("slot"),
}

# Allowed unit aliases. Do not guess missing units from user natural language.
UNIT_FACTORS: dict[str, dict[str, float]] = {
    "mm": {"mm": 1.0, "cm": 10.0, "m": 1000.0, "um": 0.001, "µm": 0.001},
    "N": {"N": 1.0, "kN": 1000.0},
    "rpm": {"rpm": 1.0, "rps": 60.0},
    "degC": {"degC": 1.0, "℃": 1.0, "°C": 1.0, "C": 1.0},
}

NUMERIC_LITERAL = re.compile(r"(?<![A-Za-z0-9])[-+]?\d+(?:\.\d+)?")
NUMERIC_WITH_UNIT = re.compile(
    r"(?<![A-Za-z0-9])([-+]?\d+(?:\.\d+)?)\s*(rpm|rps|kN|mm|cm|µm|um|degC|°C|℃|N|m|K)(?![A-Za-z])"
)
APPROXIMATE_MARKERS = ("大约", "大概", "约", "左右", "估计", "差不多", "approx", "roughly", "about")


class InvalidChange(ValueError):
    """A proposed edit is not a valid trusted user-layer update."""


def require_evidence(change: UpdateChange, context: TrustedContext) -> None:
    """Only a cheap guard; full natural-language semantic extraction is PR-02."""
    if change.evidence_span not in context.user_message:
        raise InvalidChange("Evidence span is not present in the trusted user message")
    if change.precision == "exact" and any(m in change.evidence_span.lower() for m in APPROXIMATE_MARKERS):
        raise InvalidChange("Approximate language cannot be silently promoted to an exact value")
    if change.path == "dimensions.d_mm" and "轴径" in change.evidence_span and "轴承内径" not in change.evidence_span:
        raise InvalidChange("Shaft diameter is not automatically the bearing bore")
    if change.path == "operating.inner_speed_rpm" and "电机" in change.evidence_span and "内圈" not in change.evidence_span:
        raise InvalidChange("Motor speed alone does not establish inner-ring speed")
    numbers = [float(m.group(0)) for m in NUMERIC_LITERAL.finditer(change.evidence_span)]
    if isinstance(change.value, (float, int)) and not isinstance(change.value, bool):
        if not any(math.isclose(float(change.value), n, abs_tol=1e-9) for n in numbers):
            zero_facts = (
                (change.path == "operating.axial_load_n" and any(t in change.evidence_span for t in ("无轴向载荷", "没有轴向载荷")))
                or (change.path == "operating.outer_speed_rpm" and any(t in change.evidence_span for t in ("外圈固定", "外圈不动")))
            )
            if not (change.value == 0 and zero_facts):
                raise InvalidChange("Numeric value is not supported by the cited text")


def _check_unit_against_evidence(change: UpdateChange, spec: FieldSpec) -> None:
    """Reject explicit unit contradictions, without inferring missing units in PR-01."""
    if spec.unit is None or change.unit is None or isinstance(change.value, bool):
        return
    matches = [(float(num), unit) for num, unit in NUMERIC_WITH_UNIT.findall(change.evidence_span)]
    if not matches:
        return
    observed = [unit for num, unit in matches if isinstance(change.value, (int, float))
                and math.isclose(float(change.value), num, abs_tol=1e-9)]
    if not observed:
        # Bearing-size triple '25×52×15mm' may carry one unit at the end.
        relevant = set(UNIT_FACTORS.get(spec.unit, {})) | ({"K"} if spec.unit == "degC" else set())
        observed = [unit for _, unit in matches if unit in relevant]
    if observed and any(unit != change.unit for unit in observed):
        # '°C', '℃' and 'degC' are equivalent representations, unlike K.
        aliases = {"°C", "℃", "C", "degC"}
        if spec.unit != "degC" or not all(unit in aliases and change.unit in aliases for unit in observed):
            raise InvalidChange("Proposed unit conflicts with explicit unit in trusted user text")


def _finite_number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise InvalidChange("Expected a numeric JSON value, not text or boolean")
    if not math.isfinite(value):
        raise InvalidChange("Non-finite numeric values are forbidden")
    return float(value)


def _normalize_number(value: Any, unit: str | None, spec: FieldSpec) -> float:
    number = _finite_number(value)
    if spec.unit == "degC" and unit == "K":
        number -= 273.15
    elif spec.unit is not None:
        if unit is None or unit not in UNIT_FACTORS[spec.unit]:
            raise InvalidChange(f"Explicit recognized unit required for {spec.unit}: {unit!r}")
        number *= UNIT_FACTORS[spec.unit][unit]
    elif unit is not None:
        raise InvalidChange("This field must not include a physical unit")
    if spec.positive and number <= 0:
        raise InvalidChange("Value must be positive")
    if spec.nonnegative and number < 0:
        raise InvalidChange("Value must not be negative")
    return number


def _make_requirement(change: UpdateChange, source: Source) -> Requirement:
    if not isinstance(change.value, dict):
        raise InvalidChange("Requirements must be structured records")
    allowed = {"field", "operator", "value", "unit"}
    if set(change.value) - allowed:
        raise InvalidChange("Unsupported requirement keys")
    try:
        raw = change.value
        field = raw["field"]
        operator = raw["operator"]
        v = raw.get("value")
        unit = raw.get("unit")
        if change.path == "requirements.geometric_bounds[]":
            if field not in ("dimensions.d_mm", "dimensions.D_mm", "dimensions.B_mm"):
                raise InvalidChange("Geometric bound must reference a known dimension")
            if operator not in ("<", "<=", "=", ">=", ">"):
                raise InvalidChange("Geometric bound requires a comparison operator")
            v = _normalize_number(v, unit, FIELDS[field])
            unit = "mm"
            # Require both numeric evidence and relevant dimension; semantic parsing remains PR-02.
            literal = change.value.get("value")
            nums = [float(m.group()) for m in NUMERIC_LITERAL.finditer(change.evidence_span)]
            if not any(math.isclose(float(literal), x, abs_tol=1e-9) for x in nums):
                raise InvalidChange("Bound number not found in cited evidence")
        if change.path == "requirements.preferences[]" and operator not in ("minimize", "maximize", "text"):
            raise InvalidChange("Preference requires minimize/maximize/text")
        if isinstance(v, (float, int)):
            if isinstance(v, bool) or not math.isfinite(v):
                raise InvalidChange("Requirement numeric value must be finite")
            nums = [float(m.group()) for m in NUMERIC_LITERAL.finditer(change.evidence_span)]
            literal = raw.get("value")
            if literal is not None and not any(math.isclose(float(literal), n, abs_tol=1e-9) for n in nums):
                raise InvalidChange("Requirement number not supported by cited user text")
        return Requirement(field=field, operator=operator, value=v, unit=unit, source=source)
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidChange(f"Invalid requirement: {exc}") from exc


def _make_slot(change: UpdateChange, source: Source) -> OptimizationSlot:
    if not isinstance(change.value, dict):
        raise InvalidChange("Optimization slot must be a structured record")
    if set(change.value) - {"mode", "value", "bounds"}:
        raise InvalidChange("Unsupported optimization slot keys")
    data = change.value.copy()
    mode = data.get("mode")
    if mode == "locked":
        raw = data.get("value")
        if change.path.endswith(".Z"):
            if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
                raise InvalidChange("Ball count Z must be a positive integer")
            value = raw
        else:
            value = _finite_number(raw)
            if value <= 0:
                raise InvalidChange("Locked geometry variable must be positive")
        data["value"] = value
        if not any(math.isclose(float(value), float(m.group()), abs_tol=1e-9) for m in NUMERIC_LITERAL.finditer(change.evidence_span)):
            raise InvalidChange("Locked slot value not found in user evidence")
    if mode == "bounded":
        bounds = data.get("bounds")
        if not isinstance(bounds, (list, tuple)) or len(bounds) != 2:
            raise InvalidChange("Bounds require two numbers")
        if change.path.endswith(".Z") and (any(isinstance(x, bool) or not isinstance(x, int) or x <= 0 for x in bounds)):
            raise InvalidChange("Ball-count bounds require positive integers")
    try:
        return OptimizationSlot(**data, source_message_id=source.message_id)
    except ValueError as exc:
        raise InvalidChange(str(exc)) from exc


def normalize_change(change: UpdateChange, context: TrustedContext) -> ParameterValue | OptimizationSlot | Requirement:
    """Whitelist every edit, normalize units, attach source from server context."""
    spec = FIELDS.get(change.path)
    if spec is None:
        raise InvalidChange(f"Unknown or read-only parameter path: {change.path}")
    require_evidence(change, context)
    source = Source(kind="user", message_id=context.message_id)
    if change.precision == "range" and spec.kind not in ("requirement", "slot"):
        raise InvalidChange("Use a structured bound instead of a scalar 'range' value")
    if spec.kind in ("string", "enum") and change.unit is not None:
        raise InvalidChange("Text/choice fields must not have a physical unit")
    if spec.kind == "requirement":
        return _make_requirement(change, source)
    if spec.kind == "slot":
        return _make_slot(change, source)
    if spec.kind == "number":
        _check_unit_against_evidence(change, spec)
        value = _normalize_number(change.value, change.unit, spec)
    elif spec.kind == "string":
        if not isinstance(change.value, str) or not change.value.strip():
            raise InvalidChange("Expected a nonempty string")
        value = change.value.strip()
        if spec.required and change.path.startswith("engineering.") and value not in context.user_message:
            raise InvalidChange("A user-selected catalog ID needs explicit text evidence")
    elif spec.kind == "enum":
        if not isinstance(change.value, str) or change.value not in spec.choices:
            raise InvalidChange(f"Must be one of {spec.choices}")
        value = change.value
    else:
        raise InvalidChange("Unsupported field type")
    return ParameterValue(
        value=value,
        unit=spec.unit,
        precision=change.precision,
        confirmed=change.precision == "exact",
        source=source,
        note=change.note,
    )


def get_path_value(brief: Any, path: str) -> Any:
    parts = path.removesuffix("[]").split(".")
    result = brief
    for p in parts:
        result = getattr(result, p)
    return result


def set_path_value(brief: Any, path: str, value: Any) -> None:
    parts = path.split(".")
    target = brief
    for p in parts[:-1]:
        target = getattr(target, p)
    setattr(target, parts[-1], value)
