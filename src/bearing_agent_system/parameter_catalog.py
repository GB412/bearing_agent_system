"""Single authoritative user-facing DGB field catalog and value normalization."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Literal

from .models import (
    OptimizationSlot,
    ParameterValue,
    Requirement,
    Source,
    TrustedContext,
    UpdateChange,
)


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
    "mm": {"mm": 1.0, "cm": 10.0, "m": 1000.0, "um": 0.001, "µm": 0.001,
           "毫米": 1.0, "厘米": 10.0, "微米": 0.001},
    "N": {"N": 1.0, "kN": 1000.0},
    "rpm": {"rpm": 1.0, "rps": 60.0},
    "degC": {"degC": 1.0, "℃": 1.0, "°C": 1.0, "C": 1.0},
    "h": {"h": 1.0, "小时": 1.0, "hour": 1.0, "hours": 1.0},
    "W": {"W": 1.0, "kW": 1000.0},
}

NUMERIC_LITERAL = re.compile(r"(?<![A-Za-z0-9])[-+]?\d+(?:\.\d+)?")
NUMERIC_WITH_UNIT = re.compile(
    r"(?<![A-Za-z0-9])([-+]?\\d+(?:\\.\\d+)?)\\s*"
    r"(hours|hour|小时|毫米|厘米|微米|degC|rpm|rps|kN|kW|mm|cm|µm|um|°C|℃|N|W|h|m|K)"
    r"(?![A-Za-z])"
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


def _evidence_numbers(text: str) -> list[float]:
    """Read literal values. In '7-9', the dash between digits is a range separator."""
    values: list[float] = []
    for hit in NUMERIC_LITERAL.finditer(text):
        value = float(hit.group())
        if hit.group().startswith("-") and hit.start() > 0 and text[hit.start() - 1].isdigit():
            value = abs(value)
        values.append(value)
    return values


def _has_number(text: str, value: float) -> bool:
    return any(math.isclose(value, n, rel_tol=1e-9, abs_tol=1e-9)
               for n in _evidence_numbers(text))


def _check_unit_against_evidence(change: UpdateChange, spec: FieldSpec) -> None:
    """Reject explicit mismatch, including for nested bounds and optimizer values."""
    matches = [(float(num), unit) for num, unit in NUMERIC_WITH_UNIT.findall(change.evidence_span)]
    if spec.unit is None:
        if change.unit is not None:
            raise InvalidChange("Dimensionless quantity must not carry a unit")
        if isinstance(change.value, (int, float)):
            if any(math.isclose(float(change.value), n, abs_tol=1e-9)
                   for n, _ in matches):
                raise InvalidChange("Dimensionless quantity has a physical unit in evidence")
        return
    if change.unit is None:
        raise InvalidChange(f"Explicit unit required for {spec.unit}")
    if not matches:
        return
    value = float(change.value)
    observed = [unit for n, unit in matches if math.isclose(value, n, abs_tol=1e-9)]
    if not observed:
        # A range can state its shared unit once, after its last endpoint.
        known = set(UNIT_FACTORS.get(spec.unit, {})) | ({"K"} if spec.unit == "degC" else set())
        observed = [unit for _, unit in matches if unit in known]
    for observed_unit in observed:
        if spec.unit == "degC" and observed_unit == change.unit == "K":
            continue
        aliases = UNIT_FACTORS.get(spec.unit, {})
        if (observed_unit not in aliases or change.unit not in aliases
                or not math.isclose(aliases[observed_unit], aliases[change.unit])):
            raise InvalidChange("Proposed unit conflicts with explicit unit in user evidence")


def _checked_quantity(raw: Any, unit: str | None, spec: FieldSpec,
                      evidence: str) -> float:
    """Use one evidence, unit, and numeric gate for scalar, bounds, and slots."""
    value = _finite_number(raw)
    if not _has_number(evidence, value):
        raise InvalidChange("Quantity has no matching number in cited user evidence")
    proxy = UpdateChange(path="quantity", value=value, unit=unit, evidence_span=evidence)
    _check_unit_against_evidence(proxy, spec)
    return _normalize_number(value, unit, spec)


def _nearby_operator(text: str, value: float) -> str | None:
    """Conservative check of *explicit* comparison operators near this literal."""
    patterns: tuple[tuple[str, str], ...] = (
        (r"(?:不超过|不能超过|不大于|小于等于|至多|最多|上限|最大|≤|<=)", "<="),
        (r"(?:不少于|不低于|不小于|大于等于|至少|下限|最小|≥|>=)", ">="),
        (r"(?:小于|低于|<)", "<"),
        (r"(?:大于|超过|>)", ">"),
        (r"(?:等于|固定为|确定为|采用|=)", "="),
    )
    for match in NUMERIC_LITERAL.finditer(text):
        if not math.isclose(float(match.group()), value, rel_tol=1e-9, abs_tol=1e-9):
            continue
        prefix = re.split(r"[，,。；;\\n]", text[max(0, match.start() - 24):match.start()])[-1]
        for expression, operator in patterns:
            if re.search(expression + r"\\s*(?:为|是)?\\s*$", prefix):
                return operator
    return None


def _approximate_near(text: str, value: float) -> bool:
    for match in NUMERIC_LITERAL.finditer(text):
        if not math.isclose(float(match.group()), value, rel_tol=1e-9, abs_tol=1e-9):
            continue
        left = re.split(r"[，,。；;\\n]", text[max(0, match.start() - 16):match.start()])[-1]
        right = text[match.end():match.end() + 5]
        if any(word in left for word in APPROXIMATE_MARKERS + ("可能", "暂定")):
            return True
        if any(word in right for word in ("左右", "上下", "左右浮动")):
            return True
    return False


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


# Only these additional quantitative goals have explicit user-layer unit contracts.
EXTRA_QUANTITIES = {
    "life_hours": FieldSpec("number", "h", nonnegative=True),
    "power_loss": FieldSpec("number", "W", nonnegative=True),
}
SLOT_HINTS: dict[str, tuple[str, ...]] = {
    "Dw_mm": ("Dw", "dw", "球径", "钢球直径"),
    "Dpw_mm": ("Dpw", "dpw", "节圆直径", "钢球节圆"),
    "Z": ("Z", "球数", "钢球数量", "钢球个数"),
    "fi": ("fi", "内圈沟曲率", "内沟曲率"),
    "fo": ("fo", "外圈沟曲率", "外沟曲率"),
}


def _make_requirement(change: UpdateChange, source: Source,
                      context: TrustedContext) -> Requirement:
    if not isinstance(change.value, dict):
        raise InvalidChange("Requirement must be a structured record")
    if change.unit is not None:
        raise InvalidChange("Requirement unit belongs in nested value.unit")
    allowed = {"field", "operator", "value", "unit"}
    if set(change.value) - allowed:
        raise InvalidChange("Unsupported requirement keys")
    try:
        raw = change.value
        field = raw["field"]
        operator = raw["operator"]
        value = raw.get("value")
        unit = raw.get("unit")
        if change.path == "requirements.geometric_bounds[]":
            if field not in ("dimensions.d_mm", "dimensions.D_mm", "dimensions.B_mm"):
                raise InvalidChange("Geometric bound must reference d, D or B")
            if operator not in ("<", "<=", "=", ">=", ">"):
                raise InvalidChange("Geometric bound needs a comparison operator")
        if change.path == "requirements.preferences[]" and operator not in (
                "minimize", "maximize", "text"):
            raise InvalidChange("Preference needs minimize/maximize/text")
        if operator in ("minimize", "maximize", "text"):
            if value is not None and not isinstance(value, str):
                raise InvalidChange("Preference/text requirement cannot assert a number")
            if unit is not None:
                raise InvalidChange("Non-numeric requirement must not carry a unit")
        else:
            if value is None:
                raise InvalidChange("Numeric bound requires a user-supplied value")
            spec = FIELDS.get(field) or EXTRA_QUANTITIES.get(field)
            if spec is None or spec.kind != "number":
                raise InvalidChange("Unregistered quantitative requirement field")
            raw_value = _finite_number(value)
            value = _checked_quantity(raw_value, unit, spec, change.evidence_span)
            unit = spec.unit
            observed_op = _nearby_operator(context.user_message, raw_value)
            if observed_op is not None and observed_op != operator:
                raise InvalidChange("Requirement comparator conflicts with user wording")
            if change.path == "requirements.geometric_bounds[]" and observed_op is None:
                raise InvalidChange("Geometric bound needs explicit comparison evidence")
        return Requirement(field=field, operator=operator, value=value, unit=unit, source=source)
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidChange(f"Invalid requirement: {exc}") from exc


def _make_slot(change: UpdateChange, source: Source,
               context: TrustedContext) -> OptimizationSlot:
    if not isinstance(change.value, dict):
        raise InvalidChange("Optimization slot must be a structured record")
    if set(change.value) - {"mode", "value", "bounds"}:
        raise InvalidChange("Unsupported optimization slot keys")
    data = change.value.copy()
    mode = data.get("mode")
    spec = FIELDS[change.path]
    label = change.path.rsplit(".", 1)[-1]
    if mode in ("locked", "bounded"):
        if not any(hint in change.evidence_span for hint in SLOT_HINTS[label]):
            raise InvalidChange("Optimization slot evidence must identify this variable")
        if change.precision == "approximate":
            raise InvalidChange("Approximate user value cannot become a locked/bounded slot")
    if mode == "locked":
        if change.precision == "range":
            raise InvalidChange("A range cannot be locked to a single value")
        raw = data.get("value")
        if label == "Z":
            if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
                raise InvalidChange("Ball count Z must be a positive integer")
        value = _checked_quantity(raw, change.unit, spec, change.evidence_span)
        if value <= 0:
            raise InvalidChange("Locked optimization variable must be positive")
        if _approximate_near(context.user_message, float(raw)):
            raise InvalidChange("Approximate wording cannot authorize a locked value")
        data["value"] = int(value) if label == "Z" else value
    elif mode == "bounded":
        bounds = data.get("bounds")
        if not isinstance(bounds, (list, tuple)) or len(bounds) != 2:
            raise InvalidChange("Bounded slot requires exactly two endpoints")
        if not any(marker in change.evidence_span
                   for marker in ("到", "至", "～", "~", "-", "—", "之间", "范围", "∈", "区间")):
            raise InvalidChange("No explicit range relation in optimization evidence")
        if "不知道" in change.evidence_span or "不确定" in change.evidence_span:
            raise InvalidChange("Unknown user value is not an authorized numeric range")
        normalized: list[float] = []
        for endpoint in bounds:
            if label == "Z" and (isinstance(endpoint, bool) or not isinstance(endpoint, int)
                                  or endpoint <= 0):
                raise InvalidChange("Ball-count bounds must be positive integers")
            value = _checked_quantity(endpoint, change.unit, spec, change.evidence_span)
            if value <= 0:
                raise InvalidChange("Optimization bounds must be positive")
            if _approximate_near(context.user_message, float(endpoint)):
                raise InvalidChange("Approximate bounds need confirmation before use")
            normalized.append(value)
        if normalized[0] >= normalized[1]:
            raise InvalidChange("Optimization bounds must be increasing")
        data["bounds"] = (int(normalized[0]), int(normalized[1])) if label == "Z" else tuple(normalized)
    elif mode == "optimize":
        if change.unit is not None:
            raise InvalidChange("An unconstrained optimizer slot must not include a unit")
    else:
        raise InvalidChange("Invalid optimization slot mode")
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
        return _make_requirement(change, source, context)
    if spec.kind == "slot":
        return _make_slot(change, source, context)
    if spec.kind == "number":
        value = _checked_quantity(change.value, change.unit, spec, change.evidence_span)
        if change.path.startswith("dimensions."):
            operator = _nearby_operator(context.user_message, float(change.value))
            if operator in ("<", "<=", ">", ">="):
                raise InvalidChange("A dimension limit must be saved as a requirement, not a fixed size")
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
