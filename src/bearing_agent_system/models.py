"""Typed, versioned user-layer deep-groove ball bearing design brief."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Source(StrictModel):
    kind: Literal["user", "system", "catalog", "reviewed_rule", "derived"]
    message_id: str | None = None
    ref: str | None = None


class ParameterValue(StrictModel):
    value: Any
    unit: str | None = None
    confirmed: bool = False
    precision: Literal["exact", "approximate", "range", "unknown"] = "exact"
    source: Source
    note: str | None = None
    evidence_status: Literal["UNVERIFIED", "REVIEWED"] = "UNVERIFIED"


class Bearing(StrictModel):
    type: Literal["DGB"] = "DGB"
    application: ParameterValue | None = None
    model: ParameterValue | None = None


class Dimensions(StrictModel):
    d_mm: ParameterValue | None = None
    D_mm: ParameterValue | None = None
    B_mm: ParameterValue | None = None


class Operating(StrictModel):
    inner_speed_rpm: ParameterValue | None = None
    outer_speed_rpm: ParameterValue | None = None
    radial_load_n: ParameterValue | None = None
    axial_load_n: ParameterValue | None = None
    temperature_c: ParameterValue | None = None
    axial_load_direction: ParameterValue | None = None
    rotation_direction: ParameterValue | None = None
    misalignment: ParameterValue | None = None
    moments: ParameterValue | None = None
    mounting_orientation: ParameterValue | None = None


class Materials(StrictModel):
    inner_ring_id: ParameterValue | None = None
    outer_ring_id: ParameterValue | None = None
    ball_id: ParameterValue | None = None


class Cage(StrictModel):
    type: ParameterValue | None = None
    material_id: ParameterValue | None = None


class Lubrication(StrictModel):
    mode: ParameterValue | None = None
    lubricant_id: ParameterValue | None = None


class Clearance(StrictModel):
    group: ParameterValue | None = None
    initial_radial_clearance_mm: ParameterValue | None = None


class Fits(StrictModel):
    inner_ring: ParameterValue | None = None
    outer_ring: ParameterValue | None = None


class Engineering(StrictModel):
    materials: Materials = Field(default_factory=Materials)
    cage: Cage = Field(default_factory=Cage)
    lubrication: Lubrication = Field(default_factory=Lubrication)
    clearance: Clearance = Field(default_factory=Clearance)
    fits: Fits = Field(default_factory=Fits)


class Requirement(StrictModel):
    field: str
    operator: Literal["<", "<=", "=", ">=", ">", "minimize", "maximize", "text"]
    value: float | str | None = None
    unit: str | None = None
    source: Source

    @field_validator("value", mode="before")
    @classmethod
    def forbid_boolean(cls, value: float | str | None) -> float | str | None:
        if isinstance(value, bool):
            raise ValueError("Boolean is not a numeric requirement")
        return value


class Requirements(StrictModel):
    constraints: list[Requirement] = Field(default_factory=list)
    preferences: list[Requirement] = Field(default_factory=list)
    geometric_bounds: list[Requirement] = Field(default_factory=list)


class OptimizationSlot(StrictModel):
    @field_validator("value", mode="before")
    @classmethod
    def reject_boolean_value(cls, value: Any) -> Any:
        if isinstance(value, bool):
            raise ValueError("Optimization slot must not use a boolean")
        return value

    @field_validator("bounds", mode="before")
    @classmethod
    def reject_boolean_bounds(cls, bounds: Any) -> Any:
        if bounds is not None and isinstance(bounds, (list, tuple)) and any(isinstance(x, bool) for x in bounds):
            raise ValueError("Optimization bounds must be numerical")
        return bounds

    mode: Literal["optimize", "locked", "bounded"] = "optimize"
    value: float | int | None = None
    bounds: tuple[float, float] | None = None
    source_message_id: str | None = None

    @model_validator(mode="after")
    def check_mode(self) -> OptimizationSlot:
        import math

        if isinstance(self.value, bool) or (self.value is not None and not math.isfinite(self.value)):
            raise ValueError("Optimization slot value must be finite")
        if self.bounds is not None:
            lower, upper = self.bounds
            if not all(math.isfinite(x) for x in (lower, upper)) or lower >= upper:
                raise ValueError("Optimization bounds must be finite and increasing")
        if self.mode == "optimize" and (self.value is not None or self.bounds is not None):
            raise ValueError("Optimize slot must not have a fixed value or bounds")
        if self.mode == "locked" and (self.value is None or self.bounds is not None):
            raise ValueError("Locked slot requires exactly one value")
        if self.mode == "bounded" and (self.bounds is None or self.value is not None):
            raise ValueError("Bounded slot requires bounds and no fixed value")
        return self


class OptimizationSlots(StrictModel):
    Dw_mm: OptimizationSlot = Field(default_factory=OptimizationSlot)
    Z: OptimizationSlot = Field(default_factory=OptimizationSlot)
    Dpw_mm: OptimizationSlot = Field(default_factory=OptimizationSlot)
    fi: OptimizationSlot = Field(default_factory=OptimizationSlot)
    fo: OptimizationSlot = Field(default_factory=OptimizationSlot)


class SolverContext(StrictModel):
    mode: Literal[-1] = -1
    profile_ref: str | None = None


class DesignBrief(StrictModel):
    schema_version: Literal["DGBDesignBrief/v1"] = "DGBDesignBrief/v1"
    bearing: Bearing = Field(default_factory=Bearing)
    dimensions: Dimensions = Field(default_factory=Dimensions)
    operating: Operating = Field(default_factory=Operating)
    engineering: Engineering = Field(default_factory=Engineering)
    requirements: Requirements = Field(default_factory=Requirements)
    optimization_slots: OptimizationSlots = Field(default_factory=OptimizationSlots)
    solver_context: SolverContext = Field(default_factory=SolverContext)


class UpdateChange(StrictModel):
    path: str
    value: Any
    unit: str | None = None
    precision: Literal["exact", "approximate", "range"] = "exact"
    evidence_span: str = Field(min_length=1)
    note: str | None = None


class UpdateBatch(StrictModel):
    operation: Literal["set", "replace"]
    changes: list[UpdateChange] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_paths(self) -> UpdateBatch:
        paths = [c.path for c in self.changes]
        if len(paths) != len(set(paths)):
            raise ValueError("Duplicate paths in one update batch")
        return self


class TrustedContext(StrictModel):
    message_id: str = Field(min_length=1)
    user_message: str = Field(min_length=1)
    kind: Literal["user"] = "user"


class DesignStatus(StrictModel):
    known: dict[str, Any]
    missing: list[str]
    pending_confirmation: list[str]
    conflicts: list[str]


class UpdateResult(StrictModel):
    revision: int
    applied_changes: list[str] = Field(default_factory=list)
    rejected_changes: list[dict[str, str]] = Field(default_factory=list)
    design_status: DesignStatus
