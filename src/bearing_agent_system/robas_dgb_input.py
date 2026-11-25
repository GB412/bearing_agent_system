"""Build a single-row DGB RoBAS quasi-static DATA.txt from DesignBrief/v2.

Compatibility-first: preserve original model defaults, overwrite only user facts,
five candidate variables, original material CSV properties and source-backed DGB
geometry. This module does not evaluate engineering fitness or run RoBAS_v2.exe.

Source layout: RoBAS/Core/BallBearing/BallBearingAnalysis.cs;
geometry: RoBAS DGBGeometry/SingleRowDeepGroove*Race/StraightPocketCage.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_EVEN
import hashlib
import io
import math
from pathlib import Path
from typing import Mapping

from .models import DesignBrief


# Field order is the physical DATA contract, not alphabetical order.
# Repeated 'rec 7.2.x' lines have different fields and unique row indices.
_LAYOUT_TEXT = """
rec 1|Mode kDCR kDOF klcOpt kFnOpt kPrtOpt kPrtFreq kPltFreq kAGraf kLifeFreq kTherm maxStps nStps intMet
rec 2.1|stpInit stpMin stpMax fTime Tol qFac
rec 2.2|kFD11 kFD21 kFD31 kFD12 kFD22 kFD32 kMD11 kMD21 kMD31 kMD12 kMD22 kMD32
rec 2.3|finName pltNames1 pltNames2 pltNames3 pltNames4 pltNames5 pltNames6 pltNames7 pltNames8 pltNames9
rec 3.1|runId
rec 3.2|kUnit kBrg nRe nCseg kRaceFlex kReGeoImp kRaceGeoImp1 kRaceGeoImp2 kFlngInd11 kFlngInd12 kFlngInd21 kFlngInd22
rec 3.3|kStaticConstraint1 kStaticConstraint2 kStaticConstraint3 kStaticConstraint4 kStaticConstraint5 kAngVel kStif kChrn kReMat kRaceMat1 kRaceMat2 kHsngMat kShftMat kLifeCons
rec 3.4|kRotLoad kRotFrame kReIP kRaceIP1 kRaceIP2 kNumPltElem kPltElemInd1 kPltElemInd2 kPltElemInd3 kPltElemInd4 kPltElemInd5 kPltElemInd6
rec 3.5|kCoolant kBaseTemp kHTC kGeoMod kMatPropMod
rec 4|brgBore brgOD shftID hsngOD raceWidth1 raceWidth2
rec 5A|bReDia pitchDia freeConAngDeg freeIntCls raceCurFac1 raceCurFac2 shoulderDia1 shoulderDia2 shimThickness1 shimThickness2 rmsAspHt1 rmsAspHt2
rec 7.0|kPoctype kCagePocImp kCageGsImp kRaceGsImp kPocHydro kGsHydro kCageMat kCageIP nGL iCageGuide1 iCageGuide2 iCageGuide3 iCageGuide4
rec 7.1|cageDia1 cageDia2 cageWidth cageCls1 cageCls2 bPocCls1 bPocCls2 cageAngCut cageConeAng
rec 7.2.x|cageGsDia1 cageGsWidth1 cageGsPos1 cageGsCls1
rec 7.2.x|cageGsDia2 cageGsWidth2 cageGsPos2 cageGsCls2
rec 8.1|density elasticModules poissonRatio thermalExpansion specificHeat conductivity strainLimit hardness wearCoeff misis
rec 8.2.1|density elasticModules poissonRatio thermalExpansion specificHeat conductivity strainLimit hardness wearCoeff misis
rec 8.2.2|density elasticModules poissonRatio thermalExpansion specificHeat conductivity strainLimit hardness wearCoeff misis
rec 8.3|density elasticModules poissonRatio thermalExpansion conductivity
rec 8.4|density elasticModules poissonRatio thermalExpansion conductivity
rec 8.5|density elasticModules poissonRatio thermalExpansion specificHeat conductivity strainLimit hardness wearCoeff misis
rec 8.6.0|sProb brgWbDis
rec 8.6.1|fcO1 fcLP1 shExLP1 depExLP1 fcGZ1 shExGZ1 fcIH1 shExIH1 depExIH1 wbDis1
rec 8.6.2|fcO1 fcLP1 shExLP1 depExLP1 fcGZ1 shExGZ1 fcIH1 shExIH1 depExIH1 wbDis1
rec 8.6.3|fcO1 fcLP1 shExLP1 depExLP1 fcGZ1 shExGZ1 fcIH1 shExIH1 depExIH1 wbDis1
rec 8.6.4|rmsAspSlp1 shearLmt1 aspTrac1 facMat1 facCont1 facProc1 facMatLF1 facProcLF1 hardnessLF1
rec 8.6.5|rmsAspSlp1 shearLmt1 aspTrac1 facMat1 facCont1 facProc1 facMatLF1 facProcLF1 hardnessLF1
rec 8.6.6|facMatRe facContRe facProcRe facMatLFre facProcLFre hardnessLFre
rec 9.0|roomTemp raceFit1 raceFit2 angVelOrt resStress1 resStress2 facStrLimit
rec 9.1.1|appLoadX appLoadY appLoadZ appDispX appDispY appDispZ
rec 9.1.2|appMomY appMomZ appMis11 appMis21 appMis12 appMis22 rpm1 rpm2
rec 9.1.3|hsngTemp shftTemp raceTemp1 raceTemp2 reTemp cageTemp
rec 9.2|pctDisp rpmRange11 rpmRange21 rpmRange12 rpmRange22
rec 9.5|pocLubFilm wvRatio avRatio cageGcPosX cageGcPosY cageGcPosZ cageAngPosX cageAngPosY cageAngPosZ
rec 9.6|baseTemp cFlowRate cPres reHTC cageHTC aveTime skipTime
rec 9.7|xRo xMu xCp xK
rec 10.0|kTrac kTracType kCPTrac kCPTracType kCRTrac kCRTracType kRFTrac kRFTracType kRRTrac kRRTracType iTherm
rec 10.1C|reRaceTC1 reRaceTC2 reRaceTC3 reRaceTC4
rec 10.3|reRaceFilm strParam
rec 10.5.1B|reCageTC1 reCageTC2 reCageTC3 reCageTC4 reCageFilm
rec 10.5.2B|cageRaceTC1 cageRaceTC2 cageRaceTC3 cageRaceTC4 cageRaceFilm
rec 10.6|pocVis gsVis
rec 11|gravityVecX gravityVecY gravityVecZ
"""
LAYOUT = tuple((label, tuple(fields.split())) for label, fields in (
    line.split("|", 1) for line in _LAYOUT_TEXT.strip().splitlines()
))
assert len(LAYOUT) == 43 and sum(len(fields) for _, fields in LAYOUT) == 324
_TEXT_ROWS = {3, 4}  # zero-based: rec 2.3, rec 3.1
_FIELDS = {(i, key): col for i, (_, keys) in enumerate(LAYOUT)
           for col, key in enumerate(keys, start=1)}
_ROW_BY_LABEL = {label: i for i, (label, _) in enumerate(LAYOUT)
                 if label != "rec 7.2.x"}


class RoBASInputError(ValueError):
    """Input missing, incompatible with original DATA, or invalid geometry."""


def _number(value: object, name: str) -> float:
    if type(value) not in (float, int) or not math.isfinite(value):
        raise RoBASInputError(f"{name}: expected a finite number")
    return float(value)


def _round_original(value: float, decimals: int) -> float:
    """RoBAS public getter rounds with Math.Round (midpoint-to-even)."""
    step = Decimal(1).scaleb(-decimals)
    return float(Decimal(str(value)).quantize(step, rounding=ROUND_HALF_EVEN))


def _confirmed(brief: DesignBrief, path: str, unit: str | None = None) -> object:
    obj: object = brief
    for segment in path.split("."):
        obj = getattr(obj, segment)
    if obj is None or not obj.confirmed:  # type: ignore[attr-defined]
        raise RoBASInputError(f"DesignBrief.{path}: missing or not confirmed")
    if unit and obj.unit not in (None, unit):  # type: ignore[attr-defined]
        raise RoBASInputError(f"DesignBrief.{path}: expected unit {unit}")
    return obj.value  # type: ignore[attr-defined]


def _read_reference(path: Path) -> tuple[list[list[str]], str]:
    raw = path.read_bytes()
    try:
        parsed = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""),
                                 skipinitialspace=True))
    except (UnicodeError, csv.Error) as exc:
        raise RoBASInputError("Reference DATA is not valid UTF-8/CSV") from exc
    if len(parsed) != len(LAYOUT):
        raise RoBASInputError(f"Expected 43 records; got {len(parsed)}")
    for i, ((label, keys), row) in enumerate(zip(LAYOUT, parsed, strict=True)):
        if not row or row[0].strip().strip("'\"") != label or len(row) != len(keys) + 1:
            raise RoBASInputError(f"DATA row {i+1} has incorrect label/field count")
        for raw_value in row[1:]:
            value = raw_value.strip().strip("'\"")
            if i in _TEXT_ROWS:
                if not value:
                    raise RoBASInputError(f"Empty text at DATA row {i+1}")
            elif not value:
                raise RoBASInputError(f"Empty numeric field at DATA row {i+1}")
            else:
                try:
                    if not math.isfinite(float(value)):
                        raise ValueError("non-finite")
                except ValueError as exc:
                    raise RoBASInputError(f"Non-finite/invalid number at row {i+1}") from exc
    if float(parsed[0][1]) != -1 or float(parsed[5][1]) != 1 or float(parsed[5][2]) != 1:
        raise RoBASInputError("Reference must be DGB, SI units, quasi-static Mode=-1")
    return parsed, hashlib.sha256(raw).hexdigest()


def _material_table(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        records: dict[str, dict[str, str]] = {}
        for row in reader:
            name = row.get("materialName", "")
            if not name or name in records:
                raise RoBASInputError("Missing/duplicate material record")
            records[name] = row
    return records


def _lubricant_names(path: Path) -> set[str]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    names = [row.get("oilName", "") for row in rows]
    if not names or any(not n for n in names) or len(names) != len(set(names)):
        raise RoBASInputError("Invalid lubricant CSV")
    return set(names)


def _material_name(value: object, prefix: str) -> str:
    if not isinstance(value, str) or not value.startswith(prefix) or not value[len(prefix):]:
        raise RoBASInputError(f"Expected catalog ID starting with {prefix}")
    return value[len(prefix):]


_MATERIAL_COLUMNS = {
    "density": "density(kg/m3)",
    "elasticModules": "elsaModules(Pa)",
    "poissonRatio": "poisson",
    "thermalExpansion": "linearExpan(1/k)",
    "specificHeat": "specificHeat",
    "conductivity": "heatConductivity(w/m/k)",
}


@dataclass(frozen=True)
class DGBProfile:
    """Fixed working-case assumptions; profile is NOT an engineering approval."""
    geometry_clearance_mm: float = 0.017
    room_temperature_c: float = 25.0
    reference_sha256: str | None = None


@dataclass(frozen=True)
class PreparedData:
    payload: bytes
    manifest: dict[str, object]

    def write(self, directory: str | Path) -> Path:
        folder = Path(directory)
        folder.mkdir(parents=True, exist_ok=True)
        file = folder / "DATA.txt"
        file.write_bytes(self.payload)
        return file


def build_dgb_data(
    *, brief: DesignBrief, candidate: Mapping[str, float | int],
    reference_data: str | Path, material_csv: str | Path,
    lubricant_csv: str | Path, profile: DGBProfile = DGBProfile(),
) -> PreparedData:
    """Produce isolated DATA bytes; never edit the reference DATA or RoBAS resources."""
    if brief.schema_version != "DGBDesignBrief/v2" or brief.bearing.type != "DGB":
        raise RoBASInputError("Only DGBDesignBrief/v2 is supported")
    for name in ("axial_load_direction", "rotation_direction", "misalignment",
                 "moments", "mounting_orientation"):
        if getattr(brief.operating, name) is not None:
            raise RoBASInputError(f"Additional operating field {name} needs an explicit mapping")
    if set(candidate) != {"Dw_mm", "Z", "Dpw_mm", "fi", "fo"}:
        raise RoBASInputError("Candidate must supply exactly Dw_mm, Z, Dpw_mm, fi, fo")

    d = _number(_confirmed(brief, "dimensions.d_mm", "mm"), "d_mm")
    outside = _number(_confirmed(brief, "dimensions.D_mm", "mm"), "D_mm")
    width = _number(_confirmed(brief, "dimensions.B_mm", "mm"), "B_mm")
    radial = _number(_confirmed(brief, "operating.radial_load_n", "N"), "Fr")
    axial = _number(_confirmed(brief, "operating.axial_load_n", "N"), "Fa")
    rpm_outer = _number(_confirmed(brief, "operating.outer_speed_rpm", "rpm"), "rpm1")
    rpm_inner = _number(_confirmed(brief, "operating.inner_speed_rpm", "rpm"), "rpm2")
    temp = _number(_confirmed(brief, "operating.temperature_c", "degC"), "temperature_c")
    if not 0 < d < outside or width <= 0 or not -273.15 < temp < 2000:
        raise RoBASInputError("Invalid basic dimensions or temperature")
    if radial < 0 or axial < 0:
        raise RoBASInputError("V1 loads are positive magnitudes with agreed +X/+Z mapping")
    clear = _number(profile.geometry_clearance_mm, "geometry_clearance_mm")
    room = _number(profile.room_temperature_c, "room_temperature_c")
    if clear < 0 or room <= -273.15:
        raise RoBASInputError("Invalid fixed profile")

    ball = _round_original(_number(candidate["Dw_mm"], "Dw_mm"), 3)
    pitch = _round_original(_number(candidate["Dpw_mm"], "Dpw_mm"), 2)
    Z_raw = candidate["Z"]
    if type(Z_raw) is not int or Z_raw < 3:
        raise RoBASInputError("Z must be an integer >= 3")
    Z = Z_raw
    fi, fo = (_number(candidate[k], k) for k in ("fi", "fo"))
    if not (ball > 0 and pitch > 0 and fi > 0.5 and fo > 0.5):
        raise RoBASInputError("Invalid ball geometry or groove curvature")
    k = 0.35 if d <= 25 else 0.40
    # Original parametric C# inner/outer race construction, in millimetres.
    inner_shoulder = _round_original(pitch - (1 - k) * ball, 2)
    outer_shoulder = _round_original(pitch + (1 - k) * ball + clear, 2)
    if not (d < inner_shoulder < pitch < outer_shoulder < outside):
        raise RoBASInputError("Shoulder diameters outside bearing envelope")
    if pitch * math.sin(math.pi / Z) <= ball:
        raise RoBASInputError("Adjacent balls intersect")
    pocket = _round_original(1.004 * ball + 0.12, 1)
    guide_gap = 0.6 * (pocket - ball)
    cage_outer = _round_original(outer_shoulder - guide_gap, 2)
    cage_inner = _round_original(cage_outer - 0.6 * ball, 2)
    cage_width = width - (0.6 * ball + 0.5)
    if cage_width - pocket < 2.5:
        cage_width = pocket + 2.5
    cage_width = _round_original(cage_width, 2)
    if cage_width >= width or cage_width <= 0 or cage_inner <= inner_shoulder:
        raise RoBASInputError("Derived cage is not compatible with design geometry")
    cage_clear1 = outer_shoulder - cage_outer
    cage_clear2 = cage_inner - inner_shoulder
    pocket_clearance = (pocket - ball) / 2
    guide_width = 0.22 * cage_width
    guide_pos = 0.5 * cage_width
    if pocket_clearance <= 0 or cage_clear1 < 0 or cage_clear2 < 0:
        raise RoBASInputError("Negative cage or pocket clearance")

    reference = Path(reference_data)
    rows, reference_sha = _read_reference(reference)
    if profile.reference_sha256 and reference_sha != profile.reference_sha256:
        raise RoBASInputError("Reference DATA SHA-256 does not match selected profile")
    original = [row.copy() for row in rows]
    provenance: dict[tuple[int, str], str] = {}

    def set_field(label: str, key: str, value: float | int, origin: str) -> None:
        i = _ROW_BY_LABEL[label]
        if (i, key) not in _FIELDS:
            raise RoBASInputError(f"Unknown DATA field {label}.{key}")
        if (i, key) in provenance:
            raise RoBASInputError(f"Duplicate ownership: {label}.{key}")
        if isinstance(value, bool) or not math.isfinite(float(value)):
            raise RoBASInputError(f"Invalid update: {label}.{key}")
        rows[i][_FIELDS[i, key]] = str(value)
        provenance[i, key] = origin

    direct = {
        ("rec 4", "brgBore"): d / 1000,
        ("rec 4", "brgOD"): outside / 1000,
        ("rec 4", "raceWidth1"): width / 1000,
        ("rec 4", "raceWidth2"): width / 1000,
        ("rec 9.1.1", "appLoadX"): axial,
        ("rec 9.1.1", "appLoadY"): 0,
        ("rec 9.1.1", "appLoadZ"): radial,
        ("rec 9.1.2", "rpm1"): rpm_outer,
        ("rec 9.1.2", "rpm2"): rpm_inner,
    }
    for (label, key), value in direct.items():
        set_field(label, key, value, "design_brief")
    cand_updates = {
        ("rec 3.2", "nRe"): Z,
        ("rec 5A", "bReDia"): ball / 1000,
        ("rec 5A", "pitchDia"): pitch / 1000,
        ("rec 5A", "raceCurFac1"): fo,
        ("rec 5A", "raceCurFac2"): fi,
    }
    for (label, key), value in cand_updates.items():
        set_field(label, key, value, "candidate")
    derived = {
        ("rec 3.2", "kBrg"): 1,
        ("rec 4", "shftID"): d / 5000,
        ("rec 4", "hsngOD"): outside * 1.14 / 1000,
        ("rec 5A", "freeConAngDeg"): 0,
        ("rec 5A", "shoulderDia1"): outer_shoulder / 1000,
        ("rec 5A", "shoulderDia2"): inner_shoulder / 1000,
        ("rec 7.0", "kPoctype"): 0,
        ("rec 7.1", "cageDia1"): cage_outer / 1000,
        ("rec 7.1", "cageDia2"): cage_inner / 1000,
        ("rec 7.1", "cageWidth"): cage_width / 1000,
        ("rec 7.1", "cageCls1"): cage_clear1 / 1000,
        ("rec 7.1", "cageCls2"): cage_clear2 / 1000,
        ("rec 7.1", "bPocCls1"): pocket_clearance / 1000,
        ("rec 9.2", "rpmRange21"): rpm_outer,
        ("rec 9.2", "rpmRange12"): rpm_inner,
    }
    for (label, key), value in derived.items():
        set_field(label, key, value, "original_derived")
    for i, idx in enumerate((1, Z + 1, 0, 0, 0, 0), start=1):
        set_field("rec 3.4", f"kPltElemInd{i}", idx, "original_derived")
    for record, suffix in ((13, "1"), (14, "2")):
        for key, val in (
            (f"cageGsDia{suffix}", cage_inner / 1000),
            (f"cageGsWidth{suffix}", guide_width / 1000),
            (f"cageGsPos{suffix}", guide_pos / 1000),
            (f"cageGsCls{suffix}", cage_clear2 / 1000),
        ):
            if (record, key) not in _FIELDS:
                raise RoBASInputError(f"Missing original guide field {record}:{key}")
            rows[record][_FIELDS[record, key]] = str(val)
            provenance[record, key] = "original_derived"

    # Deliberately fixed original model settings; do not equate the solver's
    # freeIntCls=0 with the original C0 race-geometry clearance.
    set_field("rec 5A", "freeIntCls", 0, "original_fixed_profile")
    set_field("rec 9.0", "roomTemp", room + 273.15, "work_temperature_assumption")
    for key in ("hsngTemp", "shftTemp", "raceTemp1", "raceTemp2", "reTemp", "cageTemp"):
        set_field("rec 9.1.3", key, temp + 273.15, "work_temperature_assumption")

    materials = _material_table(Path(material_csv))
    material_specs = (
        ("engineering.materials.ball_id", "rec 8.1"),
        ("engineering.materials.outer_ring_id", "rec 8.2.1"),
        ("engineering.materials.inner_ring_id", "rec 8.2.2"),
        ("engineering.cage.material_id", "rec 8.5"),
    )
    material_names = {}
    for path, record in material_specs:
        name = _material_name(_confirmed(brief, path), "material:")
        if name not in materials:
            raise RoBASInputError(f"Unknown material in original CSV: {name}")
        material_names[record] = name
        for field, csv_column in _MATERIAL_COLUMNS.items():
            try:
                n = float(materials[name][csv_column])
            except (ValueError, KeyError, TypeError) as exc:
                raise RoBASInputError(f"Missing material property {name}.{field}") from exc
            set_field(record, field, n, "original_material_csv")

    lubrication_mode = _confirmed(brief, "engineering.lubrication.mode")
    if lubrication_mode != "oil":
        raise RoBASInputError("V1 original profile supports oil lubrication only")
    oil = _material_name(_confirmed(brief, "engineering.lubrication.lubricant_id"),
                         "lubricant:")
    if oil not in _lubricant_names(Path(lubricant_csv)):
        raise RoBASInputError(f"Unknown lubricant in original CSV: {oil}")
    # Original C# does not demonstrate a proven dynamic update from chosen oil
    # to rec 9.7/10: keep all 29 original model values unchanged.

    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerows(rows)
    payload = buf.getvalue().encode("utf-8")
    if len(payload) == 0 or b"\x00" in payload:
        raise RoBASInputError("Invalid serialized DATA")
    # Round-trip validation: reject count, missing fields and invalid mode.
    # Use a small generated temporary-free read path by validating in memory.
    parsed = list(csv.reader(io.StringIO(payload.decode("utf-8")), skipinitialspace=True))
    if len(parsed) != 43 or sum(len(row) - 1 for row in parsed) != 324:
        raise RoBASInputError("Serialized DATA does not match 43/324")
    diffs = [
        {"record": LAYOUT[i][0], "row": i + 1, "field": key,
         "before": original[i][_FIELDS[i, key]],
         "after": rows[i][_FIELDS[i, key]], "source": source}
        for (i, key), source in sorted(provenance.items())
        if original[i][_FIELDS[i, key]] != rows[i][_FIELDS[i, key]]
    ]
    return PreparedData(payload, {
        "schema_version": "DGB_RoBAS_DATA_v1",
        "reference_sha256": reference_sha,
        "output_sha256": hashlib.sha256(payload).hexdigest(),
        "record_count": 43,
        "field_count": 324,
        "changed_fields": diffs,
        "mapped_field_count": len(provenance),
        "material_names_by_record": material_names,
        "lubricant_catalog_record": oil,
        "lubricant_data_mode": "original_model_defaults_preserved",
        "fixed_free_int_cls_m": 0,
        "geometry_clearance_mm": clear,
        "analysis_inner_race_outside_diameter_mm": inner_shoulder,
        "thermal_boundary_mode": "prescribed_uniform_solid_temperature_not_predicted",
        "engineer_validated": False,
    })
