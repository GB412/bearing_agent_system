"""Offline, source-layout-focused tests for the V1 DGB RoBAS DATA builder."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from pathlib import Path

import pytest

from bearing_agent_system.models import (
    DesignBrief,
    OptimizationSlot,
    ParameterValue,
    Source,
)
from bearing_agent_system.robas_dgb_cli import main as run_cli
from bearing_agent_system.robas_dgb_input import (
    LAYOUT,
    BUILTIN_LAYOUT,
    DGBProfile,
    RoBASInputError,
    _read_reference,
    build_dgb_data,
)


def fact(value, unit=None):
    return ParameterValue(value=value, unit=unit, confirmed=True,
                          source=Source(kind="user"))


def brief():
    return DesignBrief(
        dimensions={"d_mm": fact(50, "mm"), "D_mm": fact(110, "mm"),
                    "B_mm": fact(27, "mm")},
        operating={"inner_speed_rpm": fact(6000, "rpm"),
                   "outer_speed_rpm": fact(0, "rpm"),
                   "radial_load_n": fact(5000, "N"),
                   "axial_load_n": fact(1000, "N"),
                   "temperature_c": fact(80, "degC")},
        engineering={
            "materials": {
                "inner_ring_id": fact("material:高碳铬轴承钢"),
                "outer_ring_id": fact("material:高碳铬轴承钢"),
                "ball_id": fact("material:高碳铬轴承钢"),
            },
            "cage": {"material_id": fact("material:中碳合金钢碳")},
            "lubrication": {"mode": fact("oil"), "lubricant_id": fact("lubricant:VG32")},
        },
    )


def candidate():
    return {"Dw_mm": 15.0, "Z": 12, "Dpw_mm": 80.0, "fi": 0.52, "fo": 0.54}


def reference_bytes():
    rows = [[label, *("0" for _ in fields)] for label, fields in LAYOUT]
    rows[0][1] = "-1"
    rows[5][1:3] = ["1", "1"]
    stream = io.StringIO(newline="")
    csv.writer(stream, lineterminator="\r\n").writerows(rows)
    return stream.getvalue().encode("utf-8")


@pytest.fixture
def source_files(tmp_path):
    reference = tmp_path / "reference_DATA.txt"
    reference.write_bytes(reference_bytes())
    materials = tmp_path / "materialDB.csv"
    materials.write_text(
        "materialName,elsaModules(Pa),density(kg/m3),heatConductivity(w/m/k),"
        "linearExpan(1/k),poisson,specificHeat\n"
        "高碳铬轴承钢,2.1e11,7800,35,1.2e-5,0.3,460\n"
        "中碳合金钢碳,2e11,7800,20,1e-5,0.3,460\n",
        encoding="utf-8-sig",
    )
    lubricant = tmp_path / "lubricantDB.csv"
    lubricant.write_text(
        "oilName,density0,t1(degC),v1(m^2/s),t2(degC),v2(m^2/s),"
        "slopeDensity,specificHeat0(J/kg/degC),slopeCp\n"
        "VG32,863,40,3.20E-05,100,5.61E-06,-0.593,1815.8,4.396\n"
        "VG46,867,40,4.60E-05,100,7.16E-06,-0.593,1810.1,4.404\n",
        encoding="utf-8-sig",
    )
    return reference, materials, lubricant


def build(files, design=None, choice=None, profile=None):
    reference, material, lubricant = files
    return build_dgb_data(
        brief=design or brief(),
        candidate=choice or candidate(),
        reference_data=reference,
        material_csv=material,
        lubricant_csv=lubricant,
        profile=profile or DGBProfile(),
    )


def value(payload, record, key):
    rows = list(csv.reader(io.StringIO(payload.decode("utf-8"))))
    matches = [i for i, (label, _) in enumerate(BUILTIN_LAYOUT) if label == record]
    assert len(matches) == 1
    i = matches[0]
    return float(rows[i][BUILTIN_LAYOUT[i][1].index(key) + 1])


def test_layout_contract_and_reference_roundtrip(source_files):
    assert len(LAYOUT) == 43
    assert sum(len(fields) for _, fields in LAYOUT) == 324
    assert len(BUILTIN_LAYOUT) == 39
    assert sum(len(fields) for _, fields in BUILTIN_LAYOUT) == 292
    rows, sha = _read_reference(source_files[0])
    assert len(rows) == 43
    assert sha == hashlib.sha256(reference_bytes()).hexdigest()
    assert rows[0][1] == "-1"


def test_builder_maps_original_fields_and_never_mutates_reference(source_files, tmp_path):
    before = source_files[0].read_bytes()
    result = build(source_files)
    assert source_files[0].read_bytes() == before
    rows = list(csv.reader(io.StringIO(result.payload.decode("utf-8"))))
    assert len(rows) == 39
    assert sum(len(row) - 1 for row in rows) == 292
    assert all(row[0].strip("'") not in {"rec 8.6.0", "rec 8.6.1", "rec 8.6.2", "rec 8.6.3"} for row in rows)
    assert value(result.payload, "rec 3.3", "kLifeCons") == 0

    assert value(result.payload, "rec 4", "brgBore") == pytest.approx(0.050)
    assert value(result.payload, "rec 4", "brgOD") == pytest.approx(0.110)
    assert value(result.payload, "rec 3.2", "nRe") == 12
    assert value(result.payload, "rec 5A", "bReDia") == pytest.approx(0.015)
    assert value(result.payload, "rec 5A", "pitchDia") == pytest.approx(0.080)
    assert value(result.payload, "rec 5A", "raceCurFac1") == 0.54
    assert value(result.payload, "rec 5A", "raceCurFac2") == 0.52
    assert value(result.payload, "rec 5A", "shoulderDia2") == pytest.approx(0.071)
    assert value(result.payload, "rec 5A", "shoulderDia1") == pytest.approx(0.08902)
    assert value(result.payload, "rec 5A", "freeIntCls") == 0
    assert value(result.payload, "rec 9.1.1", "appLoadX") == 1000
    assert value(result.payload, "rec 9.1.1", "appLoadY") == 0
    assert value(result.payload, "rec 9.1.1", "appLoadZ") == 5000
    assert value(result.payload, "rec 9.1.2", "rpm2") == 6000
    assert value(result.payload, "rec 9.2", "rpmRange12") == 6000
    assert value(result.payload, "rec 9.0", "roomTemp") == pytest.approx(298.15)
    assert value(result.payload, "rec 9.1.3", "raceTemp2") == pytest.approx(353.15)
    assert value(result.payload, "rec 8.1", "density") == 7800
    assert value(result.payload, "rec 8.5", "density") == 7800
    assert value(result.payload, "rec 10.6", "pocVis") == 0
    assert value(result.payload, "rec 8.6.4", "shearLmt1") == 0

    assert result.manifest["analysis_inner_race_outside_diameter_mm"] == 71.0
    assert result.manifest["lubricant_data_mode"] == "properties_derived_model_defaults_preserved"
    assert result.manifest["lubricant_properties_written_to_data"] is False
    assert result.manifest["lubricant_properties_at_work_temperature"]["dynamic_viscosity_pa_s"] > 0
    file = result.write(tmp_path / "run")
    assert file.read_bytes() == result.payload


def test_only_ball_count_and_plot_indices_change(source_files):
    first = build(source_files)
    another = candidate()
    another["Z"] = 10
    second = build(source_files, choice=another)
    original = list(csv.reader(io.StringIO(first.payload.decode())))
    updated = list(csv.reader(io.StringIO(second.payload.decode())))
    changed = {(BUILTIN_LAYOUT[i][0], BUILTIN_LAYOUT[i][1][j - 1])
               for i, (a, b) in enumerate(zip(original, updated, strict=True))
               for j in range(1, len(a)) if a[j] != b[j]}
    assert changed == {("rec 3.2", "nRe"), ("rec 3.4", "kPltElemInd2")}


def test_lubricant_change_does_not_invent_solver_model_input(source_files):
    first = build(source_files)
    second_brief = brief()
    second_brief.engineering.lubrication.lubricant_id = fact("lubricant:VG46")
    second = build(source_files, design=second_brief)
    assert first.payload == second.payload
    assert second.manifest["lubricant_catalog_record"] == "VG46"
    a = first.manifest["lubricant_properties_at_work_temperature"]
    b = second.manifest["lubricant_properties_at_work_temperature"]
    assert a["dynamic_viscosity_pa_s"] != b["dynamic_viscosity_pa_s"]


def test_reference_sha_prevents_using_wrong_fixed_template(source_files):
    with pytest.raises(RoBASInputError, match="SHA-256"):
        build(source_files, profile=DGBProfile(reference_sha256="0" * 64))


@pytest.mark.parametrize("mutation,message", [
    ({"Dw_mm": 60.0}, "Shoulder diameters"),
    ({"Z": 24}, "Adjacent balls"),
    ({"fi": 0.49}, "Invalid ball geometry"),
    ({"Z": 12.0}, "integer"),
])
def test_invalid_candidate_blocks_before_solver(source_files, mutation, message):
    choice = candidate()
    choice.update(mutation)
    with pytest.raises(RoBASInputError, match=message):
        build(source_files, choice=choice)


def test_missing_required_user_fact_is_not_defaulted(source_files):
    draft = brief()
    draft.operating.axial_load_n = None
    with pytest.raises(RoBASInputError, match="axial_load_n"):
        build(source_files, design=draft)


def test_reference_wrong_record_count_is_rejected(source_files):
    source_files[0].write_bytes(reference_bytes() + b"rec extra,0\r\n")
    with pytest.raises(RoBASInputError, match="Expected 43 records"):
        build(source_files)


def test_optional_unmapped_moments_must_not_be_silently_ignored(source_files):
    draft = brief()
    draft.operating.moments = fact("user specified moment")
    with pytest.raises(RoBASInputError, match="moments"):
        build(source_files, design=draft)


def test_locked_and_bounded_candidate_requirements_are_respected(source_files):
    design = brief()
    design.optimization_slots.Z = OptimizationSlot(mode="locked", value=12)
    build(source_files, design=design)
    different = candidate()
    different["Z"] = 10
    with pytest.raises(RoBASInputError, match="locked"):
        build(source_files, design=design, choice=different)

    design = brief()
    design.optimization_slots.Dw_mm = OptimizationSlot(mode="bounded", bounds=(14.0, 16.0))
    build(source_files, design=design)
    outside_bounds = candidate()
    outside_bounds["Dw_mm"] = 17.0
    with pytest.raises(RoBASInputError, match="bounds"):
        build(source_files, design=design, choice=outside_bounds)


def test_uploaded_real_source_reference_when_supplied():
    """Optional integration regression; original DATA must remain outside public Git."""
    path = os.environ.get("ROBAS_DGB_REFERENCE_DATA")
    if not path:
        pytest.skip("Set ROBAS_DGB_REFERENCE_DATA to original DGB DATA.txt")
    raw = Path(path).read_bytes()
    rows, sha = _read_reference(Path(path))
    assert sha == "b6610d150b0b8b05f0d024fe0c6fb90c1d4b270d5ef20f95398d48a6aa165a0f"
    target = io.StringIO(newline="")
    csv.writer(target, lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL).writerows(rows)
    assert target.getvalue().encode("utf-8") == raw
    assert rows[5][3] == "11"
    assert rows[10][1] == "0.008334"
    assert rows[10][7] == "0.05902"
    assert rows[10][8] == "0.049"
    assert rows[12][1] == "0.05892"
    assert rows[12][2] == "0.05392"
    assert rows[12][3] == "0.011"
    # Original constructor leaves this scan endpoint different from Rpm2.
    # Do not silently rewrite the untouched reference during baseline replay.
    assert rows[30][8] == "20000"
    assert rows[32][4] == "0"


def test_cli_writes_original_verified_artifacts(source_files, tmp_path):
    design = tmp_path / "brief.json"
    design.write_text(brief().model_dump_json(), encoding="utf-8")
    choice = tmp_path / "candidate.json"
    choice.write_text(json.dumps(candidate()), encoding="utf-8")
    out = tmp_path / "output"
    result = run_cli([
        "--brief", str(design),
        "--candidate", str(choice),
        "--reference-data", str(source_files[0]),
        "--resources", str(tmp_path),
        "--reference-sha256", hashlib.sha256(reference_bytes()).hexdigest(),
        "--out", str(out),
    ])
    assert result == 0
    assert (out / "DATA.txt").is_file()
    assert (out / "input_manifest.json").is_file()
    assert (out / "field_diff.json").is_file()
    payload = json.loads((out / "input_manifest.json").read_text(encoding="utf-8"))
    diff = json.loads((out / "field_diff.json").read_text(encoding="utf-8"))
    assert payload["field_count"] == 292
    assert payload["record_count"] == 39
    assert payload["life_mode"] == "builtin_default"
    assert payload["changed_fields"] == diff
    assert diff

def test_default_life_record_layout(source_files):
    result = build(source_files)
    rows = list(csv.reader(io.StringIO(result.payload.decode("utf-8"))))
    assert [row[0].strip("'") for row in rows] == [name for name, _ in BUILTIN_LAYOUT]
    assert value(result.payload, "rec 3.3", "kLifeCons") == 0
    for record in ("rec 8.6.4", "rec 8.6.5", "rec 8.6.6"):
        assert record in [row[0].strip("'") for row in rows]


def test_optional_shaft_housing_material_profile(source_files):
    profile = DGBProfile(
        shaft_material_id="material:高碳铬轴承钢",
        housing_material_id="material:中碳合金钢碳",
    )
    result = build(source_files, profile=profile)
    assert value(result.payload, "rec 8.3", "density") == 7800
    assert value(result.payload, "rec 8.4", "elasticModules") == 2e11
    assert result.manifest["inherited_material_records"] == []
