"""Offline source-parity and invalid-candidate tests for CALC-01."""

from __future__ import annotations

from dataclasses import asdict

import pytest

from bearing_agent_system.dgb_geometry import (
    GEOMETRY_RULE_ID,
    DGBGeometryError,
    derive_dgb_geometry,
)

DIMS = {"d_mm": 50, "D_mm": 110, "B_mm": 27}
CANDIDATE = {"Dw_mm": 15.0, "Z": 11, "Dpw_mm": 80.0, "fi": 0.52, "fo": 0.54}


def derive(dimensions=None, candidate=None):
    return derive_dgb_geometry(
        DIMS if dimensions is None else dimensions,
        CANDIDATE if candidate is None else candidate,
    )


def test_reference_data_geometry_and_cage_match_csharp_source_trace():
    # Historical original DATA: d40/D68/B15, Dw=8.334, Z=11, Dpw=54.
    # Confirmed record-5A sidewalls 59.02/49 and record-7 cage OD/ID 58.92/53.92.
    result = derive_dgb_geometry(
        {"d_mm": 40, "D_mm": 68, "B_mm": 15},
        {"Dw_mm": 8.334, "Z": 11, "Dpw_mm": 54, "fi": 0.51, "fo": 0.53},
    )
    assert result.rule_id == GEOMETRY_RULE_ID
    assert result.c0_geometry_clearance_mm == 0.013
    assert result.inner_shoulder_diameter_mm == 49
    assert result.outer_shoulder_diameter_mm == 59.02
    assert result.analysis_inner_race_outside_diameter_mm == 49
    assert result.inner_groove_diameter_mm == 45.67
    assert result.outer_groove_diameter_mm == 62.35
    assert result.cage.pocket_diameter_mm == 8.5
    assert result.cage.guide_gap_mm == pytest.approx(0.0996)
    assert result.cage.outside_diameter_mm == 58.92
    assert result.cage.inside_diameter_mm == 53.92
    assert result.cage.width_mm == 11
    assert result.cage.pocket_radial_clearance_mm == pytest.approx(0.083)
    assert result.cage.inner_guide_clearance_mm == pytest.approx(4.92)
    assert result.cage.guide_width_mm == pytest.approx(2.42)
    assert result.cage.guide_position_mm == pytest.approx(5.5)
    assert result.plot_element_indices == (1, 12, 0, 0, 0, 0)


def test_50mm_bore_candidate_uses_17micron_c0_and_explicit_pitch_geometry():
    r = derive()
    assert r.ball_diameter_mm == 15
    assert r.pitch_diameter_mm == 80  # independent Dpw, not (50+110)/2 by fiat
    assert r.c0_geometry_clearance_mm == 0.017
    assert r.shoulder_factor == 0.40
    assert r.inner_groove_radius_mm == pytest.approx(7.8)
    assert r.outer_groove_radius_mm == pytest.approx(8.1)
    assert r.inner_groove_diameter_mm == 65
    assert r.outer_groove_diameter_mm == 95.02
    assert r.inner_shoulder_diameter_mm == 71
    assert r.outer_shoulder_diameter_mm == 89.02
    assert r.analysis_inner_race_outside_diameter_mm == r.inner_shoulder_diameter_mm
    assert r.cage.outside_diameter_mm == 88.90
    assert r.cage.inside_diameter_mm == 79.90
    assert r.cage.width_mm == 17.7
    assert r.cage.pocket_diameter_mm == 15.2
    assert r.cage.adjacent_pocket_bridge_mm > 0


def test_source_clearance_bore_boundaries_and_35_percent_small_bore():
    small = derive(
        {"d_mm": 25, "D_mm": 65, "B_mm": 15},
        {"Dw_mm": 8, "Z": 10, "Dpw_mm": 45, "fi": 0.51, "fo": 0.53},
    )
    assert small.shoulder_factor == 0.35
    assert small.c0_geometry_clearance_mm == 0.008
    assert small.inner_shoulder_diameter_mm == 39.8

    near = derive(
        {"d_mm": 49.99, "D_mm": 110, "B_mm": 27},
        CANDIDATE,
    )
    assert near.c0_geometry_clearance_mm == 0.013
    assert derive().c0_geometry_clearance_mm == 0.017


def test_independent_variables_update_only_expected_derived_fields():
    baseline = derive()
    ball = derive(candidate={**CANDIDATE, "Dw_mm": 14})
    assert ball.inner_shoulder_diameter_mm != baseline.inner_shoulder_diameter_mm
    assert ball.cage.pocket_diameter_mm != baseline.cage.pocket_diameter_mm

    count = derive(candidate={**CANDIDATE, "Z": 12})
    assert count.plot_element_indices == (1, 13, 0, 0, 0, 0)
    assert count.cage.adjacent_pocket_bridge_mm != baseline.cage.adjacent_pocket_bridge_mm
    assert count.inner_shoulder_diameter_mm == baseline.inner_shoulder_diameter_mm

    pitch = derive(candidate={**CANDIDATE, "Dpw_mm": 82})
    assert pitch.inner_groove_diameter_mm != baseline.inner_groove_diameter_mm
    assert pitch.outer_shoulder_diameter_mm != baseline.outer_shoulder_diameter_mm

    fi = derive(candidate={**CANDIDATE, "fi": 0.53})
    assert fi.inner_groove_radius_mm != baseline.inner_groove_radius_mm
    assert fi.outer_groove_radius_mm == baseline.outer_groove_radius_mm

    fo = derive(candidate={**CANDIDATE, "fo": 0.55})
    assert fo.outer_groove_radius_mm != baseline.outer_groove_radius_mm
    assert fo.inner_groove_radius_mm == baseline.inner_groove_radius_mm


def test_deterministic_plain_data_without_data_file_or_solver():
    first = derive()
    assert first == derive()
    assert asdict(first)["rule_id"] == GEOMETRY_RULE_ID
    assert all(isinstance(v, int) for v in first.plot_element_indices)


@pytest.mark.parametrize(
    ("dimensions", "candidate", "code"),
    [
        ({"d_mm": 110, "D_mm": 50, "B_mm": 27}, CANDIDATE, "INVALID_ENVELOPE"),
        (DIMS, {**CANDIDATE, "Z": 11.0}, "INVALID_BALL_COUNT"),
        (DIMS, {**CANDIDATE, "Z": True}, "INVALID_BALL_COUNT"),
        (DIMS, {**CANDIDATE, "Z": 65}, "INVALID_BALL_COUNT"),
        (DIMS, {**CANDIDATE, "Z": 1}, "BALL_OVERLAP"),
        (DIMS, {**CANDIDATE, "fi": 0.5}, "INVALID_CURVATURE"),
        (DIMS, {**CANDIDATE, "fo": 0.4}, "INVALID_CURVATURE"),
        (DIMS, {**CANDIDATE, "Dw_mm": 80}, "INVALID_ROUNDED_GEOMETRY"),
        (DIMS, {**CANDIDATE, "Dw_mm": float("nan")}, "INVALID_VALUE"),
        (DIMS, {**CANDIDATE, "Dpw_mm": float("inf")}, "INVALID_VALUE"),
        (DIMS, {**CANDIDATE, "Z": 36}, "BALL_OVERLAP"),
        (DIMS, {**CANDIDATE, "Dpw_mm": 61}, "RACEWAY_BREACH"),
        ({"d_mm": 200, "D_mm": 300, "B_mm": 27}, CANDIDATE, "C0_CLEARANCE_UNDEFINED"),
        (DIMS, {key: value for key, value in CANDIDATE.items() if key != "fo"}, "MISSING_VALUE"),
    ],
)
def test_reject_invalid_candidates_with_machine_readable_code(dimensions, candidate, code):
    with pytest.raises(DGBGeometryError) as exc:
        derive(dimensions=dimensions, candidate=candidate)
    assert exc.value.code == code


def test_no_hidden_dependent_source_override():
    # The legacy constructor is an initial-size preset, not a hard constraint
    # forcing the optimized pitch to be the d/D midpoint.
    r = derive(candidate={**CANDIDATE, "Dpw_mm": 81})
    assert r.pitch_diameter_mm == 81
    assert r.plot_element_indices[1] == CANDIDATE["Z"] + 1
