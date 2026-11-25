"""Source-backed DGB geometry for one RoBAS quasi-static analysis candidate.

This module reproduces the selected original single-row DGB construction path:
DGBGeometry, SingleRowDeepGroove{Inner,Outer}Race and StraightPocketCage.
It does not implement RoBAS's optimizer, a full CAD model, or a manufacturing
approval. All lengths in this module are millimetres; DATA conversion is CALC-02.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

GEOMETRY_RULE_ID = "robas-dgb-c0-source-v1"

# RoBAS/DGBOptimizer.cs:566-604: integer midpoints in micrometres, returned
# in millimetres. Do not silently accept the original zero fallback.
_C0_TABLE = (
    (10, 18, 4, 11),
    (18, 30, 5, 12),
    (30, 50, 9, 17),
    (50, 80, 12, 22),
    (80, 120, 18, 30),
    (120, 160, 24, 38),
    (160, 180, 30, 45),
    (180, 200, 36, 53),
)


class DGBGeometryError(ValueError):
    """An invalid candidate or an unsupported legacy-geometry assumption."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True)
class DerivedCageGeometry:
    """StraightPocketCage analysis envelope, not a stamped manufacturing cage."""

    pocket_diameter_mm: float
    guide_gap_mm: float
    outside_diameter_mm: float
    inside_diameter_mm: float
    width_mm: float
    pocket_radial_clearance_mm: float
    outer_guide_clearance_mm: float
    inner_guide_clearance_mm: float
    guide_width_mm: float
    guide_position_mm: float
    adjacent_pocket_bridge_mm: float


@dataclass(frozen=True)
class DerivedDGBGeometry:
    """Pure numerical results; the DATA writer chooses record positions."""

    rule_id: str
    bore_d_mm: float
    outside_d_mm: float
    bearing_width_mm: float
    ball_diameter_mm: float
    ball_count: int
    pitch_diameter_mm: float
    fi: float
    fo: float
    c0_geometry_clearance_mm: float
    shoulder_factor: float
    inner_groove_radius_mm: float
    outer_groove_radius_mm: float
    inner_groove_diameter_mm: float
    outer_groove_diameter_mm: float
    inner_shoulder_diameter_mm: float
    outer_shoulder_diameter_mm: float
    analysis_inner_race_outside_diameter_mm: float
    adjacent_ball_center_distance_mm: float
    plot_element_indices: tuple[int, int, int, int, int, int]
    cage: DerivedCageGeometry


def _finite_positive(mapping: Mapping[str, object], key: str) -> float:
    if key not in mapping:
        raise DGBGeometryError("MISSING_VALUE", f"Missing {key}")
    value = mapping[key]
    if type(value) not in (float, int) or not math.isfinite(value) or value <= 0:
        raise DGBGeometryError("INVALID_VALUE", f"{key} must be a finite positive number")
    return float(value)


def _dotnet_round(value: float, digits: int) -> float:
    """Match the numeric .NET Math.Round getter pattern used by the legacy adapter."""
    scale = 10**digits
    scaled = value * scale
    if not math.isfinite(scaled) or abs(scaled) >= 1e16:
        raise DGBGeometryError("INVALID_VALUE", "Dimension is outside rounding range")
    return round(scaled) / scale


def _c0_clearance_mm(bore_d_mm: float) -> float:
    for lower, upper, low_um, high_um in _C0_TABLE:
        if lower <= bore_d_mm < upper:
            return ((low_um + high_um) // 2) / 1000
    raise DGBGeometryError(
        "C0_CLEARANCE_UNDEFINED",
        "Legacy RoBAS C0 geometry table only covers 10 <= d < 200 mm",
    )


def derive_dgb_geometry(
    dimensions: Mapping[str, object],
    candidate: Mapping[str, object],
) -> DerivedDGBGeometry:
    """Derive one DGB geometry without using RoBAS EXE or optimization software.

    dimensions: d_mm, D_mm, B_mm
    candidate: Dw_mm, Z (integer), Dpw_mm, fi, fo

    The legacy C0 groove-geometry clearance is *not* RoBAS freeIntCls.
    The chosen scalar race constructor permits varying Dpw, unlike the
    DGBGeometry initial-preset constructor which sets (d + D) / 2.
    """
    d = _finite_positive(dimensions, "d_mm")
    outside = _finite_positive(dimensions, "D_mm")
    width = _finite_positive(dimensions, "B_mm")
    ball = _finite_positive(candidate, "Dw_mm")
    pitch = _finite_positive(candidate, "Dpw_mm")
    fi = _finite_positive(candidate, "fi")
    fo = _finite_positive(candidate, "fo")
    z = candidate.get("Z")
    if type(z) is not int or not 1 <= z <= 64:
        raise DGBGeometryError("INVALID_BALL_COUNT", "Z must be an integer from 1 to 64")
    if not d < outside:
        raise DGBGeometryError("INVALID_ENVELOPE", "Require d_mm < D_mm")

    # Original public C# getters round source mm values BEFORE building the
    # subsequent dependent geometry and the RoBAS input. This prevents
    # optimizing sub-precision changes that the solver never receives.
    d = _dotnet_round(d, 2)
    outside = _dotnet_round(outside, 2)
    width = _dotnet_round(width, 2)
    ball = _dotnet_round(ball, 3)
    pitch = _dotnet_round(pitch, 2)
    if not (0 < d < outside and width > 0 and 0 < ball < pitch):
        raise DGBGeometryError("INVALID_ROUNDED_GEOMETRY", "Invalid dimensions after source rounding")
    if fi <= 0.5 or fo <= 0.5:
        raise DGBGeometryError(
            "INVALID_CURVATURE", "Both groove radii must exceed the ball radius",
        )

    clearance = _c0_clearance_mm(d)
    k = 0.35 if d <= 25 else 0.40

    # Scalar SingleRowDeepGrooveRace constructors: use the corrected mm
    # path, NOT DGBGeometry's metre + millimetre clearance bug.
    inner_groove = _dotnet_round(pitch - ball, 2)
    outer_groove = _dotnet_round(pitch + ball + clearance, 2)
    inner_shoulder = _dotnet_round(inner_groove + k * ball, 2)
    outer_shoulder = _dotnet_round(outer_groove - k * ball, 2)
    inner_radius = fi * ball
    outer_radius = fo * ball
    if not (d < inner_shoulder < pitch < outer_shoulder < outside):
        raise DGBGeometryError("INVALID_SHOULDERS", "Race shoulders do not fit the DGB envelope")
    if pitch / 2 - inner_radius <= d / 2 or pitch / 2 + outer_radius >= outside / 2:
        raise DGBGeometryError("RACEWAY_BREACH", "Groove cuts through bore or outer envelope")
    if not (
        pitch - 2 * inner_radius < inner_shoulder < pitch - ball + 2 * inner_radius
        and pitch + ball - 2 * outer_radius < outer_shoulder < pitch + 2 * outer_radius
    ):
        raise DGBGeometryError("GROOVE_SHOULDER_CONFLICT", "Shoulder misses the raceway section")

    spacing = pitch * math.sin(math.pi / z)
    if spacing <= ball:
        raise DGBGeometryError("BALL_OVERLAP", "Adjacent balls intersect at this pitch and count")

    # StraightPocketCage.cs:39-50,113-129; follow the original getter
    # rounding sequence, as in Bearing_CAD/robas_ball_input.py.
    pocket = _dotnet_round(1.004 * ball + 0.12, 1)
    guide_gap = 0.6 * (pocket - ball)
    cage_outer = _dotnet_round(outer_shoulder - guide_gap, 2)
    cage_inner = _dotnet_round(cage_outer - 0.6 * ball, 2)
    cage_width = width - (0.6 * ball + 0.5)
    if cage_width - pocket < 2.5:
        cage_width = pocket + 2.5
    cage_width = _dotnet_round(cage_width, 2)
    pocket_radial_clearance = (pocket - ball) / 2
    pocket_bridge = spacing - pocket
    if not (
        guide_gap > 0
        and pocket_radial_clearance > 0
        and inner_shoulder < cage_inner < cage_outer < outer_shoulder
        and 0 < cage_width <= width
        and pocket_bridge > 0
    ):
        raise DGBGeometryError(
            "INVALID_CAGE",
            "Source StraightPocketCage dimensions, guidance or pocket spacing are infeasible",
        )

    cage = DerivedCageGeometry(
        pocket_diameter_mm=pocket,
        guide_gap_mm=guide_gap,
        outside_diameter_mm=cage_outer,
        inside_diameter_mm=cage_inner,
        width_mm=cage_width,
        pocket_radial_clearance_mm=pocket_radial_clearance,
        outer_guide_clearance_mm=outer_shoulder - cage_outer,
        inner_guide_clearance_mm=cage_inner - inner_shoulder,
        guide_width_mm=0.22 * cage_width,
        guide_position_mm=0.5 * cage_width,
        adjacent_pocket_bridge_mm=pocket_bridge,
    )
    return DerivedDGBGeometry(
        rule_id=GEOMETRY_RULE_ID,
        bore_d_mm=d,
        outside_d_mm=outside,
        bearing_width_mm=width,
        ball_diameter_mm=ball,
        ball_count=z,
        pitch_diameter_mm=pitch,
        fi=fi,
        fo=fo,
        c0_geometry_clearance_mm=clearance,
        shoulder_factor=k,
        inner_groove_radius_mm=inner_radius,
        outer_groove_radius_mm=outer_radius,
        inner_groove_diameter_mm=inner_groove,
        outer_groove_diameter_mm=outer_groove,
        inner_shoulder_diameter_mm=inner_shoulder,
        outer_shoulder_diameter_mm=outer_shoulder,
        analysis_inner_race_outside_diameter_mm=inner_shoulder,
        adjacent_ball_center_distance_mm=spacing,
        plot_element_indices=(1, z + 1, 0, 0, 0, 0),
        cage=cage,
    )
