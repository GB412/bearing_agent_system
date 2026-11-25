"""Offline, source-layout-focused tests for the V1 DGB RoBAS DATA builder."""
from __future__ import annotations

import csv
import io
import hashlib

import pytest

from bearing_agent_system.models import (
    DesignBrief, ParameterValue, Source,
)
from bearing_agent_system.robas_dgb_input import (
    DGBProfile, LAYOUT, RoBASInputError, _read_reference, build_dgb_data,
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
    lubricant.write_text("oilName,density0\nVG32,863\nVG46,870\n",
                         encoding="utf-8-sig")
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
    matches = [i for i, (label, _) in enumerate(LAYOUT) if label == record]
    assert len(matches) == 1
    i = matches[0]
    return float(rows[i][LAYOUT[i][1].index(key) + 1])


def test_layout_contract_and_reference_roundtrip(source_files):
    assert len(LAYOUT) == 43
    assert sum(len(fields) for _, fields in LAYOUT) == 324
    rows, sha = _read_reference(source_files[0])
    assert len(rows) == 43
    assert sha == hashlib.sha256(reference_bytes()).hexdigest()
    assert rows[0][1] == "-1"


def test_builder_maps_original_fields_and_never_mutates_reference(source_files, tmp_path):
    before = source_files[0].read_bytes()
    result = build(source_files)
    assert source_files[0].read_bytes() == before
    rows = list(csv.reader(io.StringIO(result.payload.decode("utf-8"))))
    assert len(rows) == 43
    assert sum(len(row) - 1 for row in rows) == 324

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
    assert value(result.payload, "rec 8.6.1", "fcLP1") == 0

    assert result.manifest["analysis_inner_race_outside_diameter_mm"] == 71.0
    assert result.manifest["lubricant_data_mode"] == "original_model_defaults_preserved"
    file = result.write(tmp_path / "run")
    assert file.read_bytes() == result.payload


def test_only_ball_count_and_plot_indices_change(source_files):
    first = build(source_files)
    another = candidate()
    another["Z"] = 10
    second = build(source_files, choice=another)
    original = list(csv.reader(io.StringIO(first.payload.decode())))
    updated = list(csv.reader(io.StringIO(second.payload.decode())))
    changed = {(LAYOUT[i][0], LAYOUT[i][1][j - 1])
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
